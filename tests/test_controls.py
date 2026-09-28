"""Buttons, numbers, selects, switches and the light (BEHAVIOUR §2.12-§2.16)."""

from __future__ import annotations

from typing import Any

from anycubic_lan import RequestRejectedError
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.anycubic_cloud.const import DOMAIN

from . import payloads
from .conftest import MockPrinter, lan_entry

P = "anycubic_kobra_s1"
A = "anycubic_kobra_s1_ace_pro"

ENABLE = (
    ("button", "request_axis_position"),
    ("button", "reset_nozzle_wear"),
    ("button", "ace_slot_2_feed"),
    ("button", "ace_slot_1_reset_spool"),
    ("number", "ace_slot_1_spool_weight"),
    ("number", "ace_slot_1_spool_price"),
    ("sensor", "ace_slot_1_filament_remaining"),
    ("sensor", "nozzle_filament_total"),
)


@pytest.fixture
async def loaded(hass: HomeAssistant, printer: MockPrinter) -> MockConfigEntry:
    options = {
        "lan_mode_enabled": True,
        "lan_host": payloads.HOST,
        "drying_preset_duration_1": 120,
        "drying_preset_temperature_1": 50,
    }
    entry = lan_entry(options=options)
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    for platform, key in ENABLE:
        registry.async_get_or_create(
            platform,
            DOMAIN,
            f"{payloads.MAC_UID}-{key}",
            config_entry=entry,
            suggested_object_id=key,
        )
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    return entry


async def _press(hass: HomeAssistant, entity_id: str) -> None:
    await hass.services.async_call(
        "button", "press", {"entity_id": entity_id}, blocking=True
    )
    await hass.async_block_till_done(wait_background_tasks=True)


def _last(printer: MockPrinter) -> tuple[str, str, dict[str, Any]]:
    return printer.client.commands[-1]


async def test_job_buttons(
    hass: HomeAssistant, loaded: MockConfigEntry, printer: MockPrinter
) -> None:
    # Without a job nothing is sent.
    await _press(hass, f"button.{P}_pause_print")
    assert printer.client.commands == []
    printer.client.feed(payloads.info(project=payloads.job()))
    for key, action in (
        ("pause_print", "pause"),
        ("resume_print", "resume"),
        ("cancel_print", "stop"),
    ):
        await _press(hass, f"button.{P}_{key}")
        assert _last(printer) == ("print", action, {"taskid": "614707220"})


async def test_axis_buttons(
    hass: HomeAssistant, loaded: MockConfigEntry, printer: MockPrinter
) -> None:
    await _press(hass, f"button.{P}_home_x_and_y")
    assert _last(printer) == (
        "axis",
        "move",
        {"axis": 4, "move_type": 2, "distance": 0},
    )
    await _press(hass, f"button.{P}_home_z_axis")
    assert _last(printer) == (
        "axis",
        "move",
        {"axis": 3, "move_type": 2, "distance": 0},
    )
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": f"select.{P}_axis_step_size", "option": "15 mm"},
        blocking=True,
    )
    assert hass.states.get(f"select.{P}_axis_step_size").state == "15 mm"
    await _press(hass, f"button.{P}_move_y_minus")
    assert _last(printer) == (
        "axis",
        "move",
        {"axis": 2, "move_type": 0, "distance": 15},
    )
    await _press(hass, f"button.{P}_move_x_plus")
    assert _last(printer) == (
        "axis",
        "move",
        {"axis": 1, "move_type": 1, "distance": 15},
    )
    await _press(hass, f"button.{P}_release_motors")
    assert _last(printer) == ("axis", "turnOff", None)
    await _press(hass, "button.request_axis_position")
    assert "axis" in printer.client.queries

    printer.client.feed(payloads.info(project=payloads.job()))
    with pytest.raises(ServiceValidationError):
        await _press(hass, f"button.{P}_move_z_plus")


async def test_home_all_waits_for_xy(
    hass: HomeAssistant,
    loaded: MockConfigEntry,
    printer: MockPrinter,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """X/Y first, then Z once the pushed move state says done (G8)."""
    monkeypatch.setattr("custom_components.anycubic_cloud.control.HOME_ALL_POLL", 0)
    client = printer.client
    client.feed(payloads.axis_move("doing"))
    polls = 0
    import asyncio

    real_sleep = asyncio.sleep

    async def fake_sleep(delay: float) -> None:
        nonlocal polls
        polls += 1
        if polls == 3:
            client.feed(payloads.axis_move("done"))
        await real_sleep(0)

    monkeypatch.setattr(
        "custom_components.anycubic_cloud.control.asyncio.sleep", fake_sleep
    )
    await _press(hass, f"button.{P}_home_all_axes")
    moves = [c for c in client.commands if c[1] == "move"]
    assert moves == [
        ("axis", "move", {"axis": 4, "move_type": 2, "distance": 0}),
        ("axis", "move", {"axis": 3, "move_type": 2, "distance": 0}),
    ]
    assert polls >= 3


async def test_home_all_gives_up_after_the_timeout(
    hass: HomeAssistant,
    loaded: MockConfigEntry,
    printer: MockPrinter,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("custom_components.anycubic_cloud.control.HOME_ALL_POLL", 0)
    monkeypatch.setattr(
        "custom_components.anycubic_cloud.control.HOME_ALL_TIMEOUT", 0.05
    )
    printer.client.feed(payloads.axis_move("doing"))
    await _press(hass, f"button.{P}_home_all_axes")
    assert _last(printer) == (
        "axis",
        "move",
        {"axis": 3, "move_type": 2, "distance": 0},
    )


async def test_home_all_ignores_a_stale_done(
    hass: HomeAssistant,
    loaded: MockConfigEntry,
    printer: MockPrinter,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A "done" left from an earlier jog does not end the wait."""
    monkeypatch.setattr("custom_components.anycubic_cloud.control.HOME_ALL_POLL", 0)
    monkeypatch.setattr(
        "custom_components.anycubic_cloud.control.HOME_ALL_TIMEOUT", 0.05
    )
    printer.client.feed(payloads.axis_move("done"))
    import asyncio

    polls = 0
    real_sleep = asyncio.sleep

    async def fake_sleep(delay: float) -> None:
        nonlocal polls
        polls += 1
        await real_sleep(0.01)

    monkeypatch.setattr(
        "custom_components.anycubic_cloud.control.asyncio.sleep", fake_sleep
    )
    await _press(hass, f"button.{P}_home_all_axes")
    assert polls > 1
    assert loaded.runtime_data.printer.axis_move_state is None


async def test_ace_buttons(
    hass: HomeAssistant, loaded: MockConfigEntry, printer: MockPrinter
) -> None:
    await _press(hass, f"button.{A}_refresh_ace_spools")
    assert "multiColorBox" in printer.client.queries
    await _press(hass, "button.ace_slot_2_feed")
    assert _last(printer) == (
        "multiColorBox",
        "feedFilament",
        {"multi_color_box": [{"id": 0, "feed_status": {"slot_index": 1, "type": 1}}]},
    )
    await _press(hass, f"button.{A}_ace_retract_filament")
    assert _last(printer)[2] == {
        "multi_color_box": [{"id": 0, "feed_status": {"slot_index": -1, "type": 2}}]
    }
    # Defaults: the first ACE's PLA (45 °C, 6 h).
    await _press(hass, f"button.{A}_start_drying")
    assert _last(printer) == (
        "multiColorBox",
        "setDry",
        {
            "multi_color_box": [
                {
                    "id": 0,
                    "drying_status": {
                        "status": 1,
                        "target_temp": 45,
                        "duration": 360,
                        "remain_time": None,
                    },
                }
            ]
        },
    )
    await _press(hass, f"button.{A}_start_drying_preset_1")
    assert _last(printer)[2]["multi_color_box"][0]["drying_status"] == {
        "status": 1,
        "target_temp": 50,
        "duration": 120,
        "remain_time": None,
    }
    # V11: stop the first ACE only.
    await _press(hass, f"button.{A}_drying_stop")
    assert _last(printer)[2] == {
        "multi_color_box": [
            {
                "id": 0,
                "drying_status": {
                    "status": 0,
                    "target_temp": 0,
                    "duration": 0,
                    "remain_time": None,
                },
            }
        ]
    }


async def test_drying_uses_stored_settings_and_the_dried_ace(
    hass: HomeAssistant, loaded: MockConfigEntry, printer: MockPrinter
) -> None:
    """B11: the second ACE dries by its own material."""
    second = payloads.box(1, loaded_slot=0, slots=[payloads.slot(0, type="PETG")])
    printer.client.feed(payloads.ace(payloads.box(0), second))
    await hass.async_block_till_done(wait_background_tasks=True)
    await _press(hass, f"button.{A}_2_secondary_drying_start")
    assert _last(printer)[2]["multi_color_box"][0] == {
        "id": 1,
        "drying_status": {
            "status": 1,
            "target_temp": 65,
            "duration": 360,
            "remain_time": None,
        },
    }
    await _press(hass, f"button.{A}_2_secondary_drying_stop")
    assert _last(printer)[2]["multi_color_box"][0]["id"] == 1
    await _press(hass, f"button.{A}_2_secondary_ace_retract")
    assert _last(printer)[2]["multi_color_box"][0]["id"] == 1

    for key, value in (("temperature", 60), ("duration", 90)):
        await hass.services.async_call(
            "number",
            "set_value",
            {"entity_id": f"number.{A}_drying_{key}", "value": value},
            blocking=True,
        )
    assert hass.states.get(f"number.{A}_drying_temperature").state == "60.0"
    await _press(hass, f"button.{A}_2_secondary_drying_start")
    assert _last(printer)[2]["multi_color_box"][0]["drying_status"] == {
        "status": 1,
        "target_temp": 60,
        "duration": 90,
        "remain_time": None,
    }


async def test_ledger_buttons_and_numbers(
    hass: HomeAssistant, loaded: MockConfigEntry, printer: MockPrinter
) -> None:
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": "number.ace_slot_1_spool_weight", "value": 500},
        blocking=True,
    )
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": "number.ace_slot_1_spool_price", "value": 19.99},
        blocking=True,
    )
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get("number.ace_slot_1_spool_weight").state == "500.0"
    assert hass.states.get("number.ace_slot_1_spool_price").state == "19.99"
    assert (
        hass.states.get("number.ace_slot_1_spool_price").attributes[
            "unit_of_measurement"
        ]
        == hass.config.currency
    )
    assert hass.states.get("sensor.ace_slot_1_filament_remaining").state == "500.0"
    ledger = loaded.runtime_data.ledger
    ledger._slot(payloads.PRINTER_ID, 0)["filament_used_g"] = 100.0
    await _press(hass, "button.ace_slot_1_reset_spool")
    assert hass.states.get("sensor.ace_slot_1_filament_remaining").state == "500.0"

    nozzle = ledger._printer(payloads.PRINTER_ID).setdefault("nozzle", {})
    nozzle["nozzle_total_g"] = 42.0
    await _press(hass, "button.reset_nozzle_wear")
    assert hass.states.get("sensor.nozzle_filament_total").state == "0.0"
    assert printer.client.commands == []


async def test_printer_numbers(
    hass: HomeAssistant, loaded: MockConfigEntry, printer: MockPrinter
) -> None:
    for entity, value, expected in (
        (
            "set_nozzle_temperature",
            210,
            (
                "tempature",
                "set",
                {"type": 0, "target_nozzle_temp": 210, "target_hotbed_temp": 0},
            ),
        ),
        (
            "set_bed_temperature",
            60,
            (
                "tempature",
                "set",
                {"type": 1, "target_nozzle_temp": 0, "target_hotbed_temp": 60},
            ),
        ),
        ("set_fan_speed", 40, ("fan", "setSpeed", {"fan_speed_pct": 40})),
        ("set_auxiliary_fan_speed", 30, ("fan", "setSpeed", {"aux_fan_speed_pct": 30})),
        ("set_box_fan_level", 2, ("fan", "setSpeed", {"box_fan_level": 2})),
    ):
        await hass.services.async_call(
            "number",
            "set_value",
            {"entity_id": f"number.{P}_{entity}", "value": value},
            blocking=True,
        )
        assert _last(printer) == expected


async def test_switches(
    hass: HomeAssistant, loaded: MockConfigEntry, printer: MockPrinter
) -> None:
    refill = f"switch.{A}_ace_run_out_refill"
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": refill}, blocking=True
    )
    assert printer.client.commands == []  # already off: nothing sent
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": refill}, blocking=True
    )
    assert _last(printer) == (
        "multiColorBox",
        "setAutoFeed",
        {"multi_color_box": [{"id": 0, "auto_feed": 1}]},
    )
    assert hass.states.get(refill).state == "on"
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": refill}, blocking=True
    )
    assert len(printer.client.commands) == 1
    printer.client.feed(payloads.ace(payloads.box(0, auto_feed=1)))
    await hass.async_block_till_done(wait_background_tasks=True)
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": refill}, blocking=True
    )
    assert _last(printer)[2] == {"multi_color_box": [{"id": 0, "auto_feed": 0}]}

    ai = f"switch.{P}_ai_failure_detection"
    for service in ("turn_on", "turn_off"):
        with pytest.raises(ServiceValidationError):
            await hass.services.async_call(
                "switch", service, {"entity_id": ai}, blocking=True
            )


async def test_light(
    hass: HomeAssistant, loaded: MockConfigEntry, printer: MockPrinter
) -> None:
    light = f"light.{P}_printer_light"
    await hass.services.async_call(
        "light", "turn_off", {"entity_id": light}, blocking=True
    )
    assert _last(printer) == (
        "light",
        "control",
        {"type": 2, "status": 0, "brightness": 0},
    )
    await hass.services.async_call(
        "light", "turn_on", {"entity_id": light}, blocking=True
    )
    assert _last(printer) == (
        "light",
        "control",
        {"type": 2, "status": 1, "brightness": 100},
    )


async def test_printer_errors_surface(
    hass: HomeAssistant, loaded: MockConfigEntry, printer: MockPrinter
) -> None:
    printer.command_error = RequestRejectedError("nope")
    with pytest.raises(HomeAssistantError, match="nope"):
        await _press(hass, f"button.{P}_release_motors")
    printer.command_error = None
    printer.client.is_connected = False
    with pytest.raises(HomeAssistantError) as err:
        await _press(hass, f"button.{P}_release_motors")
    assert err.value.translation_key == "printer_not_connected"


async def test_controls_without_an_ace(
    hass: HomeAssistant, loaded: MockConfigEntry, printer: MockPrinter
) -> None:
    """Nothing is sent to an ACE that has gone."""
    printer.client.feed(payloads.ace())
    await hass.async_block_till_done(wait_background_tasks=True)
    for button in (
        f"button.{A}_start_drying",
        f"button.{A}_drying_stop",
        f"button.{A}_ace_retract_filament",
        "button.ace_slot_2_feed",
    ):
        await _press(hass, button)
    assert printer.client.commands == []


async def test_file_list_buttons_follow_the_connection(
    hass: HomeAssistant, loaded: MockConfigEntry, printer: MockPrinter
) -> None:
    """Round 2, F3: unavailable while the list cannot be fetched."""
    coordinator = loaded.runtime_data
    names = {"local": "local", "udisk": "usb_disk", "cloud": "cloud"}
    for source, name in names.items():
        state = hass.states.get(f"button.{P}_request_file_list_{name}")
        assert state is not None
        assert state.state == STATE_UNAVAILABLE
        assert not coordinator.can_fetch_file_list(source)
    # Pressing it anyway (as the entity would be) is refused, nothing sent.
    button = hass.data["entity_components"]["button"].get_entity(
        f"button.{P}_request_file_list_local"
    )
    with pytest.raises(ServiceValidationError) as err:
        await button.async_press()
    assert err.value.translation_key == "file_list_unavailable"
    assert printer.client.commands == []

    # A connection that can fetch a list makes its button available.
    coordinator.file_list_sources = frozenset({"cloud"})
    coordinator.async_update_listeners()
    await hass.async_block_till_done()
    assert hass.states.get(f"button.{P}_request_file_list_cloud").state != (
        STATE_UNAVAILABLE
    )
    assert hass.states.get(f"button.{P}_request_file_list_local").state == (
        STATE_UNAVAILABLE
    )
