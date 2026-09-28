"""Coordinator: one LAN-connected printer per config entry.

Push first: every report the printer sends is applied at once (BEHAVIOUR
§5.1). The 15 s refresh sends the LAN query set while connected, and runs the
full handshake again while not (G2). Availability follows BEHAVIOUR §5.5:
when the connection is lost every entity becomes unavailable once and stays
so until the printer answers again - never alternating with stale values.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from anycubic_lan import (
    AnycubicLanError,
    LanModeDisabledError,
    PrinterState,
    Report,
    ReportKind,
    UnsupportedPrinterError,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_DEBUG_DEPRECATED,
    CONF_DEBUG_MQTT_MSG,
    CONF_DRYING_PRESET_DURATION,
    CONF_DRYING_PRESET_TEMPERATURE,
    CONF_PRINTER_IDS,
    DOMAIN,
    DRYING_PRESETS,
    LAN_INFO_TIMEOUT,
    STORE_CAPABILITIES,
    STORE_VERSION,
    UPDATE_INTERVAL,
)
from .identity import NO_MAC, lan_printer_id, unique_id_mac
from .lan import LanLink
from .ledger import FilamentLedger, Forecast
from .model import (
    Printer,
    PrinterIdentity,
    material_type_from_device_type,
    print_speed_pct,
)

if TYPE_CHECKING:
    from anycubic_lan import PrinterConnectionInfo
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

# Pushed reports arrive in bursts (one per kind after each query set); the
# entities are told once per burst.
PUSH_COOLDOWN = 1.0

type AnycubicConfigEntry = ConfigEntry[AnycubicCoordinator]


class AnycubicCoordinator(DataUpdateCoordinator[Printer]):
    """Keeps one printer's readings, ledger and capability memory."""

    config_entry: AnycubicConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: AnycubicConfigEntry, host: str
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {host}",
            update_interval=UPDATE_INTERVAL,
        )
        options = entry.options
        self.link = LanLink(
            async_get_clientsession(hass),
            host,
            on_state=self._handle_state,
            on_report=self._handle_report,
            on_connection=self._handle_connection,
            debug_messages=bool(
                options.get(CONF_DEBUG_MQTT_MSG, options.get(CONF_DEBUG_DEPRECATED))
            ),
        )
        self.ledger = FilamentLedger(hass, entry.entry_id)
        self._capabilities: Store[dict[str, Any]] = Store(
            hass, STORE_VERSION, f"{STORE_CAPABILITIES}.{entry.entry_id}"
        )
        self._capability_data: dict[str, Any] = {"printers": {}}
        self._printer: Printer | None = None
        self.forecast: Forecast | None = None
        # The job is only trusted once the current connection sent `info`.
        self._info_seen = asyncio.Event()
        self._push_pending = False

    # -- setup ---------------------------------------------------------------

    async def async_setup(self) -> None:
        """Connect and build the printer (BEHAVIOUR §5.3); not ready on failure."""
        await self.ledger.async_load()
        stored = await self._capabilities.async_load()
        if isinstance(stored, dict) and isinstance(stored.get("printers"), dict):
            self._capability_data = stored
        try:
            info = await self._async_connect_and_wait()
        except LanModeDisabledError as err:
            raise ConfigEntryNotReady(
                translation_domain=DOMAIN, translation_key="lan_mode_disabled"
            ) from err
        except UnsupportedPrinterError as err:
            raise ConfigEntryNotReady(
                translation_domain=DOMAIN, translation_key="lan_unsupported_printer"
            ) from err
        except (AnycubicLanError, TimeoutError) as err:
            raise ConfigEntryNotReady(
                translation_domain=DOMAIN,
                translation_key="lan_unreachable",
                translation_placeholders={"host": self.link.host},
            ) from err
        printer = self._printer = Printer(identity=self._build_identity(info))
        printer.remembered_light_types = frozenset(
            self._remembered_light_types(printer.printer_id)
        )
        printer.info_seen = True
        if self.link.client is not None:
            self._handle_state(self.link.client.state)

    async def _async_connect_and_wait(self) -> PrinterConnectionInfo:
        """Handshake, connect, then wait up to 20 s for an ``info`` report."""
        self._info_seen.clear()
        info = await self.link.async_connect()
        try:
            async with asyncio.timeout(LAN_INFO_TIMEOUT):
                await self._info_seen.wait()
        except TimeoutError:
            await self.link.async_disconnect()
            raise
        return info

    def _build_identity(self, info: PrinterConnectionInfo) -> PrinterIdentity:
        entry = self.config_entry
        state = self.link.client.state if self.link.client else PrinterState()
        printer_ids = entry.data.get(CONF_PRINTER_IDS) or []
        if printer_ids:
            # The configured id (COMPAT §2). An entry covering several cloud
            # printers can reach only one over LAN: the first (Q5).
            printer_id = int(printer_ids[0])
            if len(printer_ids) > 1:
                _LOGGER.warning(
                    "Entry %s lists %d printers; LAN Mode reaches only printer %s",
                    entry.title,
                    len(printer_ids),
                    printer_id,
                )
        else:
            printer_id = lan_printer_id(info.device_id)
        model_name = info.discovery.model_name or state.model or info.model_name
        # Without a MAC, 2.x formatted the missing value as the text "None",
        # so unique ids are ``None-<key>`` (compatibility; round 2, Q4).
        mac = unique_id_mac(info.mac) if info.mac else NO_MAC
        return PrinterIdentity(
            printer_id=printer_id,
            mac=mac,
            name=state.printer_name or model_name,
            model_name=model_name,
            model_id=info.model_id,
            material_type=material_type_from_device_type(info.discovery.device_type),
            host=self.link.host,
            serial=info.serial,
            connection_mac=info.mac,
        )

    @property
    def has_printer(self) -> bool:
        return self._printer is not None

    @property
    def printer(self) -> Printer:
        """The printer; entities and actions exist only once it is built."""
        if self._printer is None:  # pragma: no cover - setup builds it first
            raise RuntimeError("Printer not set up")
        return self._printer

    async def async_shutdown(self) -> None:
        """Close the connection and write the ledger (BEHAVIOUR §5.7)."""
        await super().async_shutdown()
        await self.link.async_disconnect()
        await self.ledger.async_flush()
        if self._printer is not None:
            # The capability memory was read at setup; write it back now.
            await self._capabilities.async_save(self._capability_data)

    # -- refresh ---------------------------------------------------------------

    async def _async_update_data(self) -> Printer:
        printer = self.printer
        if self.link.connected:
            try:
                await self.link.async_query_all()
            except AnycubicLanError as err:
                raise UpdateFailed(
                    translation_domain=DOMAIN,
                    translation_key="lan_connection_lost",
                    translation_placeholders={"host": self.link.host},
                ) from err
            return printer
        # Not connected: the whole handshake again (G2), then wait for info.
        try:
            await self._async_connect_and_wait()
        except (AnycubicLanError, TimeoutError) as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="lan_connection_lost",
                translation_placeholders={"host": self.link.host},
            ) from err
        return printer

    # -- pushed reports --------------------------------------------------------

    def _handle_report(self, report: Report) -> None:
        """Facts anycubic-lan does not merge into its state."""
        envelope = report.envelope
        if envelope.kind == ReportKind.INFO:
            self._info_seen.set()
        elif (
            envelope.kind == ReportKind.AXIS
            and envelope.action == "move"
            and envelope.state
            and self._printer is not None
        ):
            self._printer.axis_move_state = envelope.state
        elif envelope.kind == ReportKind.PRINT and self._printer is not None:
            speed = print_speed_pct(envelope.action, envelope.state, envelope.data)
            if speed is not None:
                self._printer.print_speed_pct = speed

    def _handle_state(self, state: PrinterState) -> None:
        printer = self._printer
        if printer is None:
            return
        printer.state = state
        if not self._info_seen.is_set():
            # A fresh connection: the job is not known until `info` arrives,
            # so neither the ledger nor the entities may treat it as absent.
            return
        self._remember_light_types(printer)
        self.ledger.update(printer)
        self.forecast = self.ledger.forecast(printer)
        if self.link.connected:
            self.last_update_success = True
            self.last_exception = None
        if not self._push_pending:
            self._push_pending = True
            self.config_entry.async_create_task(
                self.hass, self._async_push_listeners(), "anycubic_cloud push"
            )

    async def _async_push_listeners(self) -> None:
        """Tell the entities once per burst of reports."""
        await asyncio.sleep(PUSH_COOLDOWN)
        self._push_pending = False
        self.async_update_listeners()

    def _handle_connection(self, connected: bool) -> None:
        if connected:
            return  # the reports that follow bring it back
        # Unavailable at once, and until the printer answers again (§5.5).
        self._info_seen.clear()
        if self.last_update_success:
            self.last_update_success = False
            self.async_update_listeners()

    # -- capability memory (BEHAVIOUR §3.13) -----------------------------------

    def _remembered_light_types(self, printer_id: int) -> list[int]:
        printers = self._capability_data.get("printers", {})
        entry = printers.get(str(printer_id)) if isinstance(printers, dict) else None
        types = entry.get("light_types") if isinstance(entry, dict) else None
        return [t for t in types or [] if isinstance(t, int)]

    def _remember_light_types(self, printer: Printer) -> None:
        live = {light.type for light in printer.state.lights if light.type is not None}
        remembered = self._remembered_light_types(printer.printer_id)
        new = sorted(live - set(remembered))
        if not new:
            return
        printers = self._capability_data.setdefault("printers", {})
        printers.setdefault(str(printer.printer_id), {})["light_types"] = [
            *remembered,
            *new,
        ]
        printer.remembered_light_types = frozenset([*remembered, *new])
        self._capabilities.async_delay_save(lambda: self._capability_data, 5.0)

    # -- file lists (DECISIONS round 2, F3) ------------------------------------

    # The file lists have no LAN form (BEHAVIOUR §2.2, §2.12): the printer's
    # lists arrive as replies over CMQTT and the cloud list over HTTP. This
    # coordinator's connection is LAN only, so none can be fetched.
    file_list_sources: frozenset[str] = frozenset()

    def can_fetch_file_list(self, source: str) -> bool:
        """Whether ``source``'s list can be fetched over this connection."""
        return source in self.file_list_sources

    @property
    def capability_data(self) -> dict[str, Any]:
        return self._capability_data

    # -- options ---------------------------------------------------------------

    def drying_preset(self, number: int) -> tuple[int, int] | None:
        """(minutes, °C) of preset ``number`` when both are > 0 (§3.11)."""
        options = self.config_entry.options
        duration = options.get(CONF_DRYING_PRESET_DURATION.format(number))
        temperature = options.get(CONF_DRYING_PRESET_TEMPERATURE.format(number))
        if not isinstance(duration, int | float) or not isinstance(
            temperature, int | float
        ):
            return None
        if duration <= 0 or temperature <= 0:
            return None
        return int(duration), int(temperature)

    @property
    def configured_presets(self) -> list[int]:
        return [n for n in DRYING_PRESETS if self.drying_preset(n) is not None]
