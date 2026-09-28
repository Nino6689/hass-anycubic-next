"""Fixtures: a fake anycubic-lan printer behind the library's public API."""

from __future__ import annotations

from collections.abc import Callable, Generator, Mapping
import json
from typing import Any
from unittest.mock import AsyncMock, patch

from anycubic_lan import (
    NoActiveJobError,
    NotConnectedError,
    PrinterConnectionInfo,
    PrinterState,
    Report,
    ReportKind,
    parse_message,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.anycubic_cloud.const import DOMAIN
from custom_components.anycubic_cloud.credentials import CredentialsUnavailableError

from . import cloud_payloads as cp, payloads
from .cloud_fakes import FakeClient, FakeCloud, FakeLink, fake_secrets

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    enable_custom_integrations: None,
) -> Generator[None]:
    """Load the integration from custom_components."""
    return


class FakeLanClient:
    """Stands in for anycubic-lan's client, at its public API.

    Reports are real printer payloads run through anycubic-lan's own parser
    and ``PrinterState.apply``, so the merge rules are the library's.
    """

    def __init__(
        self,
        connection: PrinterConnectionInfo,
        *,
        report_callback: Callable[[Report], None],
        debug_messages: bool = False,
        printer: MockPrinter,
    ) -> None:
        self.connection = connection
        self._report_callback = report_callback
        self.state = PrinterState()
        self.is_connected = False
        self._state_listeners: list[Callable[[PrinterState], None]] = []
        self._connection_listeners: list[Callable[[bool], None]] = []
        self.printer = printer
        self.commands: list[tuple[str, str, Any]] = []
        self.queries: list[str] = []
        self.disconnected = False

    def add_state_listener(self, callback: Callable[[PrinterState], None]) -> Any:
        self._state_listeners.append(callback)
        return lambda: None

    def add_connection_listener(self, callback: Callable[[bool], None]) -> Any:
        self._connection_listeners.append(callback)
        return lambda: None

    async def connect(self) -> None:
        if self.printer.connect_error is not None:
            raise self.printer.connect_error
        self.is_connected = True
        for payload in self.printer.connect_payloads:
            self.feed(payload)

    async def disconnect(self) -> None:
        self.is_connected = False
        self.disconnected = True

    def feed(self, payload: Mapping[str, Any]) -> None:
        topic = (
            f"anycubic/anycubicCloud/v1/printer/public/20025/{payloads.DEVICE_ID}/"
            f"{payload.get('type')}/report"
        )
        report = parse_message(json.dumps(payload).encode(), topic)
        if report is None:
            return
        self._report_callback(report)
        self.state = self.state.apply(report)
        for callback in list(self._state_listeners):
            callback(self.state)

    def lose(self) -> None:
        self.is_connected = False
        for callback in list(self._connection_listeners):
            callback(False)

    def restore(self) -> None:
        self.is_connected = True
        for callback in list(self._connection_listeners):
            callback(True)

    def _require(self) -> None:
        if not self.is_connected:
            raise NotConnectedError("not connected")

    async def query_all(self) -> None:
        self._require()
        self.queries.append("all")
        for payload in self.printer.poll_payloads:
            self.feed(payload)

    async def query(self, kind: ReportKind) -> None:
        self._require()
        self.queries.append(kind.value)

    async def send_command(
        self, kind: ReportKind, action: str, data: Mapping[str, Any] | None = None
    ) -> str:
        self._require()
        if self.printer.command_error is not None:
            raise self.printer.command_error
        self.commands.append((kind.value, action, dict(data or {})))
        return "msgid"

    async def send_order(
        self, kind: Any, action: str, data: Mapping[str, Any] | None
    ) -> str:
        """The integration's own orders: ``data`` recorded exactly as sent."""
        self._require()
        if self.printer.command_error is not None:
            raise self.printer.command_error
        self.commands.append((kind.value, action, dict(data) if data else data))
        return "msgid"

    async def _job(self, action: str) -> str:
        job = self.state.job
        if job is None or job.task_id is None:
            raise NoActiveJobError("no job")
        return await self.send_command(
            ReportKind.PRINT, action, {"taskid": str(job.task_id)}
        )

    async def pause(self) -> str:
        return await self._job("pause")

    async def resume(self) -> str:
        return await self._job("resume")

    async def stop(self) -> str:
        return await self._job("stop")

    async def set_light(
        self, on: bool, brightness: int | None = None, *, light_type: int = 2
    ) -> str:
        return await self.send_command(
            ReportKind.LIGHT,
            "control",
            {"type": light_type, "status": int(on), "brightness": brightness},
        )


class MockPrinter:
    """What the fake printer answers."""

    def __init__(self) -> None:
        self.info = payloads.connection_info()
        self.handshake_error: Exception | None = None
        self.connect_error: Exception | None = None
        self.command_error: Exception | None = None
        self.connect_payloads: list[dict[str, Any]] = [
            payloads.info(),
            payloads.ace(payloads.box(0)),
            payloads.lights(payloads.light(2, 1)),
            payloads.peripherals(),
            payloads.ai_settings(0),
        ]
        self.poll_payloads: list[dict[str, Any]] = []
        self.clients: list[FakeLanClient] = []
        self.handshakes = 0

    @property
    def client(self) -> FakeLanClient:
        return self.clients[-1]

    async def handshake(self, session: Any, host: str) -> PrinterConnectionInfo:
        self.handshakes += 1
        if self.handshake_error is not None:
            raise self.handshake_error
        return self.info

    def make_client(
        self, connection: PrinterConnectionInfo, **kwargs: Any
    ) -> FakeLanClient:
        client = FakeLanClient(connection, printer=self, **kwargs)
        self.clients.append(client)
        return client


@pytest.fixture(autouse=True)
def no_cloud_credentials() -> Generator[None]:
    """By default the Anycubic app credentials are not installed (CLOUD.md §1):
    CI never needs the real package. Cloud tests use the ``cloud`` fixture."""
    with patch(
        "custom_components.anycubic_cloud.credentials.load_cloud_secrets",
        side_effect=CredentialsUnavailableError("anycubic_cloud_api is not installed"),
    ):
        yield


@pytest.fixture
def cloud(monkeypatch: pytest.MonkeyPatch) -> Generator[FakeCloud]:
    """A fake Anycubic account behind anycubic-cloud-client's public API."""
    fake = FakeCloud()
    for name in (
        "CLOUD_SETUP_RETRY_DELAY",
        "MQTT_WAKE_SETTLE",
        "MQTT_REFRESH_PAUSE",
    ):
        monkeypatch.setattr(f"custom_components.anycubic_cloud.cloud.{name}", 0)
    with (
        patch(
            "custom_components.anycubic_cloud.credentials.load_cloud_secrets",
            return_value=fake_secrets(),
        ),
        patch(
            "custom_components.anycubic_cloud.cloud.AnycubicCloudClient",
            FakeClient.factory(fake),
        ),
        patch(
            "custom_components.anycubic_cloud.config_flow.AnycubicCloudClient",
            FakeClient.factory(fake),
        ),
        patch(
            "custom_components.anycubic_cloud.cloud.CloudMqttClient",
            side_effect=FakeLink.factory(fake),
        ),
    ):
        yield fake


@pytest.fixture(autouse=True)
def no_push_cooldown(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pushed reports reach entities within the test's event loop turn."""
    monkeypatch.setattr("custom_components.anycubic_cloud.coordinator.PUSH_COOLDOWN", 0)


@pytest.fixture
def printer() -> Generator[MockPrinter]:
    """Patch anycubic-lan's handshake and client with the fake printer."""
    mock = MockPrinter()
    with (
        patch(
            "custom_components.anycubic_cloud.lan.handshake",
            AsyncMock(side_effect=mock.handshake),
        ),
        patch(
            "custom_components.anycubic_cloud.config_flow.handshake",
            AsyncMock(side_effect=mock.handshake),
        ),
        patch(
            "custom_components.anycubic_cloud.lan.IntegrationLanClient",
            side_effect=mock.make_client,
        ),
    ):
        yield mock


def lan_entry(**overrides: Any) -> MockConfigEntry:
    """A LAN-only entry exactly as 2.x stores it (COMPAT §1)."""
    params: dict[str, Any] = {
        "domain": DOMAIN,
        "version": 1,
        "minor_version": 1,
        "unique_id": payloads.MAC,
        "title": "Anycubic Kobra S1",
        "data": {
            "lan_host": payloads.HOST,
            "printer_ids": [payloads.PRINTER_ID],
        },
        "options": {"lan_mode_enabled": True, "lan_host": payloads.HOST},
    }
    params.update(overrides)
    return MockConfigEntry(**params)


CLOUD_USER_ID = "123456"
CLOUD_PRINTER_ID = 42424242


def cloud_entry(*, lan: bool, **overrides: Any) -> MockConfigEntry:
    """A 2.x cloud entry (COMPAT §1), with or without LAN Mode switched on."""
    options: dict[str, Any] = {
        "mqtt_connect_mode": 1,
        "drying_preset_duration_1": 240,
        "drying_preset_temperature_1": 55,
        "card_config": {"vertical": False, "scaleFactor": 1},
        "debug": False,
    }
    if lan:
        options |= {"lan_mode_enabled": True, "lan_host": payloads.HOST}
    params: dict[str, Any] = {
        "domain": DOMAIN,
        "version": 1,
        "minor_version": 1,
        "unique_id": CLOUD_USER_ID,
        "title": "someone@example.com",
        "data": {
            "user_token": "eyJhbGciOiJSUzI1NiJ9.eyJleHAiOjF9.c2ln",
            "user_auth_mode": 1,
            "user_device_id": None,
            "region": "international",
            "printer_ids": [CLOUD_PRINTER_ID],
        },
        "options": options,
    }
    params.update(overrides)
    return MockConfigEntry(**params)


def account_entry(
    *, lan: bool = False, mode: int = 3, token: str | None = None, **overrides: Any
) -> MockConfigEntry:
    """A cloud entry of the fake account, slicer mode by default."""
    options: dict[str, Any] = {"mqtt_connect_mode": 1}
    if lan:
        options |= {"lan_mode_enabled": True, "lan_host": payloads.HOST}
    params: dict[str, Any] = {
        "domain": DOMAIN,
        "version": 1,
        "minor_version": 1,
        "unique_id": str(cp.USER_ID),
        "title": cp.EMAIL,
        "data": {
            "user_token": token or cp.slicer_token(),
            "user_auth_mode": mode,
            "user_device_id": None,
            "region": "international",
            "printer_ids": [cp.PRINTER_ID],
        },
        "options": options,
    }
    params.update(overrides)
    return MockConfigEntry(**params)


def find_device(hass: HomeAssistant, identifier: str) -> dr.DeviceEntry | None:
    """The device with ``(anycubic_cloud, identifier)``, on any HA version."""
    registry = dr.async_get(hass)
    for entry in hass.config_entries.async_entries(DOMAIN):
        for device in dr.async_entries_for_config_entry(registry, entry.entry_id):
            if (DOMAIN, identifier) in device.identifiers:
                return device
    return None


async def setup_entry(hass: HomeAssistant, entry: MockConfigEntry) -> MockConfigEntry:
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    return entry


@pytest.fixture
def entry() -> MockConfigEntry:
    return lan_entry()
