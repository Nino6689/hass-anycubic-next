"""Config and options flows (BEHAVIOUR §5.8, §5.9; step ids in COMPAT §1).

This release is the LAN half of 3.0: the LAN setup path, DHCP discovery,
reconfigure and the options that apply to LAN. The cloud steps keep their
ids and explain that cloud support arrives in a later 3.0 release.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from anycubic_lan import (
    AnycubicLanError,
    LanModeDisabledError,
    PrinterConnectionInfo,
    UnsupportedPrinterError,
    handshake,
)
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.core import callback
from homeassistant.helpers import device_registry as dr, selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import format_mac
import voluptuous as vol

from .const import (
    CARD_CONFIG_BOOL_KEYS,
    CARD_CONFIG_LIST_KEYS,
    CARD_CONFIG_NUMBER_KEYS,
    CARD_CONFIG_STR_KEYS,
    CONF_CARD_CONFIG,
    CONF_DEBUG_API_CALLS,
    CONF_DEBUG_DEPRECATED,
    CONF_DEBUG_MQTT_MSG,
    CONF_DRYING_PRESET_DURATION,
    CONF_DRYING_PRESET_TEMPERATURE,
    CONF_LAN_HOST,
    CONF_LAN_MODE_ENABLED,
    CONF_MQTT_CONNECT_MODE,
    CONF_PRINTER_IDS,
    DEFAULT_MQTT_CONNECT_MODE,
    DOMAIN,
    DRYING_PRESETS,
    MQTT_CONNECT_MODES,
)
from .identity import entry_unique_id_for_lan, is_cloud_entry, lan_printer_id

if TYPE_CHECKING:
    from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo

_LOGGER = logging.getLogger(__name__)

ABORT_CLOUD_PENDING = "cloud_not_supported_yet"


async def _async_try_handshake(
    flow: ConfigFlow | OptionsFlowWithReload, host: str
) -> tuple[PrinterConnectionInfo | None, dict[str, str]]:
    """Validate a printer address; errors as in BEHAVIOUR §5.8 ``local``."""
    if not host.strip():
        return None, {CONF_LAN_HOST: "lan_host_required"}
    try:
        info = await handshake(async_get_clientsession(flow.hass), host.strip())
    except LanModeDisabledError:
        return None, {"base": "lan_printer_in_cloud_mode"}
    except UnsupportedPrinterError:
        return None, {"base": "lan_unsupported_printer"}
    except AnycubicLanError:
        return None, {"base": "lan_unreachable"}
    except Exception:
        _LOGGER.exception("Unexpected error during the LAN handshake")
        return None, {"base": "lan_unreachable"}
    return info, {}


def _lan_schema(enabled: bool, host: str) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_LAN_MODE_ENABLED, default=enabled): bool,
            vol.Optional(CONF_LAN_HOST, default=host): str,
        }
    )


class AnycubicConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up a printer."""

    VERSION = 1
    MINOR_VERSION = 1

    def __init__(self) -> None:
        self._discovered_host: str | None = None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> AnycubicOptionsFlow:
        return AnycubicOptionsFlow()

    # -- new entries -----------------------------------------------------------

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return self.async_show_menu(step_id="user", menu_options=["cloud", "local"])

    async def async_step_cloud(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return self.async_abort(reason=ABORT_CLOUD_PENDING)

    async def async_step_local(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        host = self._discovered_host or ""
        if user_input is not None:
            host = user_input.get(CONF_LAN_HOST, "").strip()
            info, errors = await _async_try_handshake(self, host)
            if info is not None:
                return await self._async_create_lan_entry(info, host)
        return self.async_show_form(
            step_id="local",
            data_schema=vol.Schema({vol.Optional(CONF_LAN_HOST, default=host): str}),
            errors=errors,
        )

    async def _async_create_lan_entry(
        self, info: PrinterConnectionInfo, host: str
    ) -> ConfigFlowResult:
        await self.async_set_unique_id(entry_unique_id_for_lan(info.mac, host))
        if existing := self.hass.config_entries.async_entry_for_domain_unique_id(
            DOMAIN, self.unique_id or ""
        ):
            self._async_update_host(existing, host)
            return self.async_abort(reason="already_configured")
        title = info.discovery.model_name or f"Anycubic ({host})"
        return self.async_create_entry(
            title=title,
            data={
                CONF_LAN_HOST: host,
                CONF_PRINTER_IDS: [lan_printer_id(info.device_id)],
            },
            options={CONF_LAN_MODE_ENABLED: True, CONF_LAN_HOST: host},
        )

    @callback
    def _async_update_host(self, entry: ConfigEntry, host: str) -> None:
        """Move an entry to a new address - the one the connection reads (G24)."""
        options = dict(entry.options)
        if entry.options.get(CONF_LAN_HOST) == host:
            return
        options[CONF_LAN_HOST] = host
        data = dict(entry.data)
        if CONF_LAN_HOST in data or not is_cloud_entry(entry):
            data[CONF_LAN_HOST] = host
        self.hass.config_entries.async_update_entry(entry, data=data, options=options)
        self.hass.config_entries.async_schedule_reload(entry.entry_id)

    # -- DHCP discovery ----------------------------------------------------------

    async def async_step_dhcp(
        self, discovery_info: DhcpServiceInfo
    ) -> ConfigFlowResult:
        """A printer seen by DHCP (matchers confirmed, DECISIONS round 2, Q9.2)."""
        mac = format_mac(discovery_info.macaddress)
        host = discovery_info.ip
        await self.async_set_unique_id(mac)
        if existing := self.hass.config_entries.async_entry_for_domain_unique_id(
            DOMAIN, mac
        ):
            if existing.options.get(CONF_LAN_MODE_ENABLED):
                self._async_update_host(existing, host)
            return self.async_abort(reason="already_configured")
        # A printer of a cloud entry is keyed by account, not MAC: look for
        # the MAC among this integration's devices (B27).
        registry = dr.async_get(self.hass)
        connection = (dr.CONNECTION_NETWORK_MAC, mac)
        if any(
            connection in device.connections
            for entry in self.hass.config_entries.async_entries(DOMAIN)
            for device in dr.async_entries_for_config_entry(registry, entry.entry_id)
        ):
            return self.async_abort(reason="already_configured")
        self._discovered_host = host
        self.context["title_placeholders"] = {"name": f"Anycubic ({host})"}
        return await self.async_step_confirm_discovery()

    async def async_step_confirm_discovery(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return await self.async_step_user()
        return self.async_show_form(
            step_id="confirm_discovery",
            description_placeholders={"host": self._discovered_host or ""},
        )

    # -- re-authentication and reconfigure ---------------------------------------

    async def async_step_reauth(self, entry_data: Any = None) -> ConfigFlowResult:
        return self.async_abort(reason=ABORT_CLOUD_PENDING)

    async def async_step_printer(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return self.async_abort(reason=ABORT_CLOUD_PENDING)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self.async_step_reauth_or_choose_printer()

    async def async_step_reauth_or_choose_printer(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reconfigure_entry()
        # G21: no account steps for LAN-only entries.
        options = (
            ["reauth", "printer", "connection"]
            if is_cloud_entry(entry)
            else ["connection"]
        )
        return self.async_show_menu(
            step_id="reauth_or_choose_printer", menu_options=options
        )

    async def async_step_connection(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """LAN settings of the entry being reconfigured (V14, G5)."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        enabled = bool(entry.options.get(CONF_LAN_MODE_ENABLED, False))
        host = str(
            entry.options.get(CONF_LAN_HOST) or entry.data.get(CONF_LAN_HOST) or ""
        )
        if user_input is not None:
            enabled = user_input[CONF_LAN_MODE_ENABLED]
            host = user_input.get(CONF_LAN_HOST, "").strip()
            if enabled:
                info, errors = await _async_try_handshake(self, host)
                if info is not None and not self._same_printer(entry, info, host):
                    errors = {"base": "lan_different_printer"}
            if not errors:
                options = {**entry.options, CONF_LAN_MODE_ENABLED: enabled}
                data = dict(entry.data)
                if enabled:
                    options[CONF_LAN_HOST] = host
                    if not is_cloud_entry(entry):
                        data[CONF_LAN_HOST] = host
                return self.async_update_reload_and_abort(
                    entry,
                    data=data,
                    options=options,
                    reason="reconfigure_successful",
                )
        return self.async_show_form(
            step_id="connection", data_schema=_lan_schema(enabled, host), errors=errors
        )

    @staticmethod
    def _same_printer(
        entry: ConfigEntry, info: PrinterConnectionInfo, host: str
    ) -> bool:
        """A LAN-only entry must keep talking to the printer it was set up for.

        Checked by MAC when the entry is keyed by one, else by the printer id
        derived from the broker's device id (COMPAT §2).
        """
        if is_cloud_entry(entry):
            return True
        unique_id = entry.unique_id or ""
        if unique_id and not unique_id.startswith("lan-") and info.mac:
            return unique_id == entry_unique_id_for_lan(info.mac, host)
        printer_ids = entry.data.get(CONF_PRINTER_IDS) or []
        if printer_ids:
            return lan_printer_id(info.device_id) == int(printer_ids[0])
        return True


def _card_value_ok(key: str, item: object) -> bool:
    if key in CARD_CONFIG_BOOL_KEYS:
        return isinstance(item, bool)
    if key in CARD_CONFIG_STR_KEYS:
        return isinstance(item, str)
    if key in CARD_CONFIG_LIST_KEYS:
        return isinstance(item, str) or (
            isinstance(item, list) and all(isinstance(i, str) for i in item)
        )
    if key in CARD_CONFIG_NUMBER_KEYS:
        return isinstance(item, int | float) and not isinstance(item, bool)
    return False


def sanitize_card_config(value: dict[str, Any]) -> dict[str, Any]:
    """Keep the known card keys of the right type (BEHAVIOUR §5.9).

    ``false``, ``0``, empty values and whole-number ``scaleFactor`` are kept
    (DECISIONS frontend 3); a bare string list value is passed through.
    """
    return {key: item for key, item in value.items() if _card_value_ok(key, item)}


class AnycubicOptionsFlow(OptionsFlowWithReload):
    """Options; every save merges into the existing options and reloads."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self.async_step_options_menu()

    def _save(
        self, changes: dict[str, Any], removed: tuple[str, ...] = ()
    ) -> ConfigFlowResult:
        options = {**self.config_entry.options, **changes}
        for key in removed:
            options.pop(key, None)
        return self.async_create_entry(data=options)

    def _has_no_ace(self) -> bool:
        """True only when the running printer is known to have no ACE (G21)."""
        coordinator = getattr(self.config_entry, "runtime_data", None)
        if coordinator is None or not coordinator.has_printer:
            return False
        printer = coordinator.printer
        return not printer.supports_ace and printer.peripherals.get("ace") is False

    async def async_step_options_menu(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        options: list[str] = []
        if is_cloud_entry(self.config_entry):
            options.append("mqtt")
        if not self._has_no_ace():
            options.append("drying")
        options += ["local", "card_config", "debug"]
        return self.async_show_menu(step_id="options_menu", menu_options=options)

    async def async_step_mqtt(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self._save(
                {CONF_MQTT_CONNECT_MODE: int(user_input[CONF_MQTT_CONNECT_MODE])}
            )
        current = self.config_entry.options.get(
            CONF_MQTT_CONNECT_MODE, DEFAULT_MQTT_CONNECT_MODE
        )
        schema = vol.Schema(
            {
                vol.Required(CONF_MQTT_CONNECT_MODE, default=str(current)): (
                    selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[str(mode) for mode in MQTT_CONNECT_MODES],
                            translation_key=CONF_MQTT_CONNECT_MODE,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    )
                )
            }
        )
        return self.async_show_form(step_id="mqtt", data_schema=schema)

    async def async_step_drying(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        keys = [
            key.format(number)
            for number in DRYING_PRESETS
            for key in (CONF_DRYING_PRESET_DURATION, CONF_DRYING_PRESET_TEMPERATURE)
        ]
        if user_input is not None:
            changes = {key: int(user_input[key]) for key in keys if key in user_input}
            removed = tuple(key for key in keys if key not in user_input)
            return self._save(changes, removed)
        fields: dict[vol.Marker, Any] = {}
        for key in keys:
            current = self.config_entry.options.get(key)
            marker = vol.Optional(
                key,
                description={"suggested_value": current}
                if current is not None
                else None,
            )
            fields[marker] = vol.All(vol.Coerce(int), vol.Range(min=0))
        return self.async_show_form(step_id="drying", data_schema=vol.Schema(fields))

    async def async_step_local(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self.config_entry
        errors: dict[str, str] = {}
        enabled = bool(entry.options.get(CONF_LAN_MODE_ENABLED, False))
        host = str(
            entry.options.get(CONF_LAN_HOST) or entry.data.get(CONF_LAN_HOST) or ""
        )
        if user_input is not None:
            enabled = user_input[CONF_LAN_MODE_ENABLED]
            host = user_input.get(CONF_LAN_HOST, "").strip()
            if not enabled:
                return self._save({CONF_LAN_MODE_ENABLED: False})
            info, errors = await _async_try_handshake(self, host)
            if info is not None:
                return self._save({CONF_LAN_MODE_ENABLED: True, CONF_LAN_HOST: host})
        return self.async_show_form(
            step_id="local", data_schema=_lan_schema(enabled, host), errors=errors
        )

    async def async_step_card_config(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            value = user_input.get(CONF_CARD_CONFIG) or {}
            if isinstance(value, dict):
                return self._save({CONF_CARD_CONFIG: sanitize_card_config(value)})
            errors[CONF_CARD_CONFIG] = "invalid_card_config"
        current = self.config_entry.options.get(CONF_CARD_CONFIG) or {}
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_CARD_CONFIG, description={"suggested_value": current}
                ): selector.ObjectSelector()
            }
        )
        return self.async_show_form(
            step_id="card_config", data_schema=schema, errors=errors
        )

    async def async_step_debug(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self._save(
                {
                    CONF_DEBUG_MQTT_MSG: bool(user_input[CONF_DEBUG_MQTT_MSG]),
                    CONF_DEBUG_API_CALLS: bool(user_input[CONF_DEBUG_API_CALLS]),
                }
            )
        options = self.config_entry.options
        legacy = bool(options.get(CONF_DEBUG_DEPRECATED, False))
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_DEBUG_MQTT_MSG,
                    default=bool(options.get(CONF_DEBUG_MQTT_MSG, legacy)),
                ): bool,
                vol.Required(
                    CONF_DEBUG_API_CALLS,
                    default=bool(options.get(CONF_DEBUG_API_CALLS, legacy)),
                ): bool,
            }
        )
        return self.async_show_form(step_id="debug", data_schema=schema)
