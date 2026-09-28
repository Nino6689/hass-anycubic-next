"""Availability (BEHAVIOUR §5.5, #38) and pending ACE entities (§1.7, #41)."""

from __future__ import annotations

from datetime import timedelta

from anycubic_lan import (
    LanModeDisabledError,
    PrinterUnreachableError,
    UnsupportedPrinterError,
)
from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.anycubic_cloud.const import DOMAIN

from . import payloads
from .conftest import MockPrinter, find_device, lan_entry, setup_entry

NOZZLE = "sensor.anycubic_kobra_s1_nozzle_temperature"
ONLINE = "binary_sensor.anycubic_kobra_s1_printer_online"
LIGHT = "light.anycubic_kobra_s1_printer_light"
PAUSE = "button.anycubic_kobra_s1_pause_print"


def _entity_states(hass: HomeAssistant, entry_id: str) -> dict[str, str]:
    registry = er.async_get(hass)
    return {
        item.entity_id: state.state
        for item in er.async_entries_for_config_entry(registry, entry_id)
        if (state := hass.states.get(item.entity_id)) is not None
    }


async def _tick(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    freezer.tick(timedelta(seconds=16))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)


async def test_printer_off_goes_unavailable_once_and_stays(
    hass: HomeAssistant, printer: MockPrinter, freezer: FrozenDateTimeFactory
) -> None:
    """#38: every entity unavailable at once, no flapping, back on return."""
    entry = await setup_entry(hass, lan_entry())
    assert hass.states.get(NOZZLE).state == "34.0"

    changes: list[str] = []

    @callback
    def _record(event: Event[EventStateChangedData]) -> None:
        if event.data["entity_id"] == NOZZLE and event.data["new_state"]:
            changes.append(event.data["new_state"].state)

    hass.bus.async_listen("state_changed", _record)

    first = printer.client
    printer.handshake_error = PrinterUnreachableError("switched off")
    first.lose()
    await hass.async_block_till_done(wait_background_tasks=True)
    states = _entity_states(hass, entry.entry_id)
    assert set(states.values()) == {STATE_UNAVAILABLE}

    for _ in range(5):
        await _tick(hass, freezer)
    assert changes == [STATE_UNAVAILABLE]
    assert set(_entity_states(hass, entry.entry_id).values()) == {STATE_UNAVAILABLE}
    # Every refresh ran the full handshake again (G2).
    assert printer.handshakes >= 6

    printer.handshake_error = None
    await _tick(hass, freezer)
    assert printer.client is not first
    assert first.disconnected
    assert hass.states.get(NOZZLE).state == "34.0"
    assert hass.states.get(ONLINE).state == "on"
    assert changes == [STATE_UNAVAILABLE, "34.0"]


async def test_connection_restored_by_the_library(
    hass: HomeAssistant, printer: MockPrinter
) -> None:
    """The library's own reconnect brings entities back with its reports."""
    await setup_entry(hass, lan_entry())
    client = printer.client
    client.lose()
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get(NOZZLE).state == STATE_UNAVAILABLE
    client.restore()
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get(NOZZLE).state == STATE_UNAVAILABLE
    client.feed(payloads.info())
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get(NOZZLE).state == "34.0"


async def test_reports_before_info_are_held(
    hass: HomeAssistant, printer: MockPrinter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After a reconnect nothing is applied until `info` names the job."""
    monkeypatch.setattr(
        "custom_components.anycubic_cloud.coordinator.LAN_INFO_TIMEOUT", 0.01
    )
    printer.connect_payloads = [payloads.info(project=payloads.job())]
    entry = await setup_entry(hass, lan_entry())
    printer.client.lose()
    await hass.async_block_till_done(wait_background_tasks=True)
    # The new connection sends a fan report first, then nothing: no info.
    printer.connect_payloads = [payloads.envelope("fan", {"fan_speed_pct": 10})]
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get(NOZZLE).state == STATE_UNAVAILABLE
    assert printer.client.disconnected


async def test_query_failure_marks_unavailable(
    hass: HomeAssistant, printer: MockPrinter, freezer: FrozenDateTimeFactory
) -> None:
    await setup_entry(hass, lan_entry())
    client = printer.client
    client.is_connected = False  # dropped without a callback yet
    printer.handshake_error = PrinterUnreachableError("gone")
    await _tick(hass, freezer)
    assert hass.states.get(NOZZLE).state == STATE_UNAVAILABLE


async def test_periodic_poll_sends_the_query_set(
    hass: HomeAssistant, printer: MockPrinter, freezer: FrozenDateTimeFactory
) -> None:
    await setup_entry(hass, lan_entry())
    printer.poll_payloads = [
        payloads.envelope("tempature", {"curr_nozzle_temp": 200}, action="query")
    ]
    await _tick(hass, freezer)
    # One set at the first refresh, one per 15 s after.
    assert printer.client.queries == ["all", "all"]
    assert hass.states.get(NOZZLE).state == "200.0"


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (PrinterUnreachableError("x"), "lan_unreachable"),
        (LanModeDisabledError("x"), "lan_mode_disabled"),
        (UnsupportedPrinterError("x"), "lan_unsupported_printer"),
    ],
)
async def test_setup_not_ready(
    hass: HomeAssistant,
    printer: MockPrinter,
    error: Exception,
    reason: str,
) -> None:
    printer.handshake_error = error
    entry = await setup_entry(hass, lan_entry())
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_setup_waits_for_info(
    hass: HomeAssistant, printer: MockPrinter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No `info` within the wait: not ready, and the client is closed."""
    monkeypatch.setattr(
        "custom_components.anycubic_cloud.coordinator.LAN_INFO_TIMEOUT", 0.01
    )
    printer.connect_payloads = []
    entry = await setup_entry(hass, lan_entry())
    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert printer.client.disconnected


async def test_connect_error_is_not_ready(
    hass: HomeAssistant, printer: MockPrinter
) -> None:
    printer.connect_error = PrinterUnreachableError("broker")
    entry = await setup_entry(hass, lan_entry())
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_ace_entities_wait_for_the_ace(
    hass: HomeAssistant, printer: MockPrinter
) -> None:
    """#41: a LAN printer learns of its ACE after setup; nothing is dropped."""
    printer.connect_payloads = [payloads.info(), payloads.peripherals()]
    entry = await setup_entry(hass, lan_entry())
    registry = er.async_get(hass)
    keys = {
        item.unique_id.removeprefix(f"{payloads.MAC_UID}-")
        for item in er.async_entries_for_config_entry(registry, entry.entry_id)
    }
    assert "ace_slot_1" not in keys
    assert "curr_nozzle_temp" in keys

    printer.client.feed(payloads.ace(payloads.box(0)))
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get("sensor.anycubic_kobra_s1_ace_pro_ace_slot_1").state == "PLA"
    assert (
        registry.async_get_entity_id(
            "button", DOMAIN, f"{payloads.MAC_UID}-secondary_drying_stop"
        )
        is None
    )

    printer.client.feed(payloads.ace(payloads.box(0), payloads.box(1, model_id=40002)))
    await hass.async_block_till_done(wait_background_tasks=True)
    stop = registry.async_get_entity_id(
        "button", DOMAIN, f"{payloads.MAC_UID}-secondary_drying_stop"
    )
    assert stop == "button.anycubic_kobra_s1_ace_2_secondary_drying_stop"
    second = find_device(hass, f"None-{payloads.PRINTER_ID}-ace1")
    assert second is not None
    assert second.name == "Anycubic Kobra S1 ACE 2"
    assert second.model == "ACE"


async def test_ace_unplugged_keeps_entities(
    hass: HomeAssistant, printer: MockPrinter
) -> None:
    await setup_entry(hass, lan_entry())
    printer.client.feed(payloads.ace())
    await hass.async_block_till_done(wait_background_tasks=True)
    assert (
        hass.states.get(
            "sensor.anycubic_kobra_s1_ace_pro_ace_current_temperature"
        ).state
        == "0.0"
    )
    assert (
        hass.states.get("sensor.anycubic_kobra_s1_ace_pro_ace_slot_1").state
        == STATE_UNAVAILABLE
    )


async def test_preset_buttons_follow_options(
    hass: HomeAssistant, printer: MockPrinter
) -> None:
    options = {
        "lan_mode_enabled": True,
        "lan_host": payloads.HOST,
        "drying_preset_duration_2": 240,
        "drying_preset_temperature_2": 55,
        "drying_preset_duration_3": 240,
    }
    entry = await setup_entry(hass, lan_entry(options=options))
    registry = er.async_get(hass)
    keys = {
        item.unique_id.removeprefix(f"{payloads.MAC_UID}-")
        for item in er.async_entries_for_config_entry(registry, entry.entry_id)
    }
    assert "drying_start_preset_2" in keys
    assert "drying_start_preset_3" not in keys
    state = hass.states.get("button.anycubic_kobra_s1_ace_pro_start_drying_preset_2")
    assert state is not None
    assert state.attributes["duration"] == 240
    assert state.attributes["temperature"] == 55


async def test_resin_or_unknown_printer_has_no_filament_entities(
    hass: HomeAssistant, printer: MockPrinter
) -> None:
    """``fdm`` entities: dropped for resin, pending while unknown (G14)."""
    for device_type in ("lcd", None):
        printer.info = payloads.connection_info(device_type=device_type)
        entry = await setup_entry(hass, lan_entry())
        registry = er.async_get(hass)
        keys = {
            item.unique_id.removeprefix(f"{payloads.MAC_UID}-")
            for item in er.async_entries_for_config_entry(registry, entry.entry_id)
        }
        assert "curr_nozzle_temp" not in keys
        assert "current_status" in keys
        await hass.config_entries.async_remove(entry.entry_id)
        await hass.async_block_till_done(wait_background_tasks=True)
