"""Actions (BEHAVIOUR §4, COMPAT §4)."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.setup import async_setup_component
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
import voluptuous as vol

from custom_components.anycubic_cloud.const import DOMAIN
from custom_components.anycubic_cloud.services import SERVICES

from . import payloads
from .conftest import MockPrinter, cloud_entry, find_device, lan_entry, setup_entry

CLOUD_ONLY = (
    (
        "print_and_upload_save_in_cloud",
        {"uploaded_gcode_file": "abc", "slot_number": 1},
    ),
    ("print_and_upload_no_cloud_save", {"uploaded_gcode_file": "abc"}),
    ("print_local_file", {"filename": "a.gcode"}),
    ("delete_file_local", {"filename": "a.gcode"}),
    ("delete_file_udisk", {"filename": "a.gcode"}),
    ("delete_file_cloud", {"file_id": 5}),
    ("change_print_bottom_layers", {"layers": 3}),
    ("change_print_bottom_time", {"time": 1.5}),
    ("change_print_off_time", {"time": 1}),
    ("change_print_on_time", {"time": 2}),
)


@pytest.fixture
async def loaded(hass: HomeAssistant, printer: MockPrinter) -> MockConfigEntry:
    return await setup_entry(hass, lan_entry())


def _device_id(hass: HomeAssistant, suffix: str = "") -> str:
    device = find_device(hass, f"None-{payloads.PRINTER_ID}{suffix}")
    assert device is not None
    return device.id


async def _call(hass: HomeAssistant, service: str, data: dict[str, Any]) -> None:
    await hass.services.async_call(DOMAIN, service, data, blocking=True)
    await hass.async_block_till_done(wait_background_tasks=True)


async def test_all_actions_registered_without_entries(hass: HomeAssistant) -> None:
    assert await async_setup_component(hass, DOMAIN, {})
    assert len(SERVICES) == 27
    for name in SERVICES:
        assert hass.services.has_service(DOMAIN, name), name


async def test_printer_selector(
    hass: HomeAssistant, loaded: MockConfigEntry, printer: MockPrinter
) -> None:
    base = {"config_entry": loaded.entry_id, "temperature": 200}
    service = "change_print_target_nozzle_temperature"
    # The frontend sends both; device_id wins.
    await _call(hass, service, base | {"device_id": _device_id(hass), "printer_id": 1})
    await _call(hass, service, base | {"device_id": [_device_id(hass)]})
    await _call(hass, service, base | {"printer_id": payloads.PRINTER_ID})
    assert len(printer.client.commands) == 3

    with pytest.raises(vol.Invalid):
        await _call(hass, service, base)
    for data, key in (
        (base | {"printer_id": 1}, "printer_not_found"),
        (base | {"device_id": "nope"}, "printer_not_found"),
        (base | {"device_id": _device_id(hass, "-ace0")}, "printer_not_found"),
        (base | {"device_id": [_device_id(hass), "x"]}, "one_printer_at_a_time"),
        (
            {**base, "config_entry": "missing", "printer_id": 1},
            "config_entry_not_found",
        ),
    ):
        with pytest.raises(ServiceValidationError) as err:
            await _call(hass, service, data)
        assert err.value.translation_key == key


async def test_entry_not_loaded(hass: HomeAssistant, printer: MockPrinter) -> None:
    entry = await setup_entry(hass, cloud_entry(lan=False))
    with pytest.raises(ServiceValidationError) as err:
        await _call(
            hass,
            "change_print_fan_speed",
            {"config_entry": entry.entry_id, "printer_id": 1, "speed": 5},
        )
    assert err.value.translation_key == "config_entry_not_loaded"
    other = MockConfigEntry(domain="other")
    other.add_to_hass(hass)
    with pytest.raises(ServiceValidationError) as err:
        await _call(
            hass,
            "change_print_fan_speed",
            {"config_entry": other.entry_id, "printer_id": 1, "speed": 5},
        )
    assert err.value.translation_key == "config_entry_not_found"


async def test_lan_actions(
    hass: HomeAssistant, loaded: MockConfigEntry, printer: MockPrinter
) -> None:
    target = {"config_entry": loaded.entry_id, "printer_id": payloads.PRINTER_ID}
    await _call(
        hass,
        "multi_color_box_set_slot_pla_se",
        target
        | {
            "box_id": 1,
            "slot_number": 2,
            "slot_color_red": 10,
            "slot_color_green": 20,
            "slot_color_blue": 30,
        },
    )
    assert printer.client.commands[-1] == (
        "multiColorBox",
        "setInfo",
        {
            "multi_color_box": [
                {
                    "id": 1,
                    "slots": [{"index": 1, "type": "PLA SE", "color": [10, 20, 30]}],
                }
            ]
        },
    )
    await _call(
        hass,
        "multi_color_box_filament_extrude",
        target | {"slot_number": 3, "finished": True},
    )
    assert printer.client.commands[-1][2] == {
        "multi_color_box": [{"id": 0, "feed_status": {"slot_index": 2, "type": 3}}]
    }
    sent = len(printer.client.commands)
    await _call(
        hass,
        "multi_color_box_set_slot_pla",
        target
        | {
            "slot_number": 0,
            "slot_color_red": 1,
            "slot_color_green": 2,
            "slot_color_blue": 3,
        },
    )
    assert len(printer.client.commands) == sent
    await _call(hass, "multi_color_box_filament_extrude", target | {"slot_number": 3})
    assert (
        printer.client.commands[-1][2]["multi_color_box"][0]["feed_status"]["type"] == 1
    )
    await _call(hass, "multi_color_box_filament_retract", target)
    assert printer.client.commands[-1][2]["multi_color_box"][0]["feed_status"] == {
        "slot_index": -1,
        "type": 2,
    }
    for service, data, expected in (
        (
            "change_print_target_hotbed_temperature",
            {"temperature": 65},
            ("tempature", "set", {"target_hotbed_temp": 65}),
        ),
        (
            "change_print_fan_speed",
            {"speed": 70},
            ("fan", "setSpeed", {"fan_speed_pct": 70}),
        ),
        (
            "change_print_aux_fan_speed",
            {"speed": 10},
            ("fan", "setSpeed", {"aux_fan_speed_pct": 10}),
        ),
        (
            "change_print_box_fan_speed",
            {"speed": 1},
            ("fan", "setSpeed", {"box_fan_level": 1}),
        ),
    ):
        await _call(hass, service, target | data)
        assert printer.client.commands[-1] == expected


async def test_extrude_without_ace_sends_nothing(
    hass: HomeAssistant, printer: MockPrinter
) -> None:
    printer.connect_payloads = [payloads.info()]
    entry = await setup_entry(hass, lan_entry())
    target = {"config_entry": entry.entry_id, "printer_id": payloads.PRINTER_ID}
    await _call(hass, "multi_color_box_filament_extrude", target | {"slot_number": 1})
    await _call(hass, "multi_color_box_filament_retract", target)
    await _call(hass, "multi_color_box_filament_extrude", target | {"slot_number": 0})
    assert printer.client.commands == []


@pytest.mark.parametrize(("service", "data"), CLOUD_ONLY)
async def test_cloud_only_actions(
    hass: HomeAssistant,
    loaded: MockConfigEntry,
    printer: MockPrinter,
    service: str,
    data: dict[str, Any],
) -> None:
    target = {"config_entry": loaded.entry_id, "printer_id": payloads.PRINTER_ID}
    with pytest.raises(ServiceValidationError) as err:
        await _call(hass, service, target | data)
    assert err.value.translation_key == "cloud_only_action"
    assert err.value.translation_placeholders == {"action": service}
    assert printer.client.commands == []


async def test_speed_mode_checks_in_order(
    hass: HomeAssistant, loaded: MockConfigEntry, printer: MockPrinter
) -> None:
    target = {
        "config_entry": loaded.entry_id,
        "printer_id": payloads.PRINTER_ID,
        "speed_mode": 2,
    }

    async def refused() -> str | None:
        with pytest.raises(ServiceValidationError) as err:
            await _call(hass, "change_print_speed_mode", target)
        return err.value.translation_key

    assert await refused() == "printer_not_busy"
    printer.client.feed(payloads.info(state="busy"))
    assert await refused() == "no_job"
    printer.client.feed(
        payloads.info(
            project=payloads.job(print_status=2, state="finished"), state="busy"
        )
    )
    assert await refused() == "job_not_in_progress"
    printer.client.feed(payloads.info(project=payloads.job()))
    # LAN lists no speed modes, so every code is refused.
    assert await refused() == "speed_mode_unavailable"
