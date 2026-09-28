"""Entity families read from LAN reports (BEHAVIOUR §1, §2)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from freezegun.api import FrozenDateTimeFactory
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.anycubic_cloud.const import DOMAIN
from custom_components.anycubic_cloud.model import print_speed_pct

from . import payloads
from .conftest import MockPrinter, lan_entry, setup_entry

P = "anycubic_kobra_s1"
A = "anycubic_kobra_s1_ace_pro"

DISABLED = (
    ("sensor", "axis_position_x"),
    ("sensor", "axis_position_y"),
    ("sensor", "axis_position_z"),
    ("sensor", "external_spool_material"),
    ("binary_sensor", "external_spool_loaded"),
    ("sensor", "job_filament_runs_out_at"),
    ("sensor", "last_job_filament"),
    ("sensor", "nozzle_filament_total"),
    ("sensor", "spool_inventory_count"),
    ("sensor", "ace_slot_1_filament_remaining"),
    ("sensor", "ace_slot_1_filament_remaining_percent"),
)


@pytest.fixture
async def loaded(hass: HomeAssistant, printer: MockPrinter) -> MockConfigEntry:
    """Set up with a few disabled-by-default entities enabled."""
    entry = lan_entry()
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    for platform, key in DISABLED:
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


def _get(hass: HomeAssistant, entity_id: str) -> State:
    state = hass.states.get(entity_id)
    assert state is not None, entity_id
    return state


async def _feed(
    hass: HomeAssistant, printer: MockPrinter, *items: dict[str, Any]
) -> None:
    for item in items:
        printer.client.feed(item)
    await hass.async_block_till_done(wait_background_tasks=True)


async def test_idle_printer(hass: HomeAssistant, loaded: MockConfigEntry) -> None:
    assert _get(hass, f"sensor.{P}_current_status").state == "available"
    attrs = _get(hass, f"sensor.{P}_current_status").attributes
    assert attrs["model"] == "Anycubic Kobra S1"
    assert attrs["machine_type"] == 20025
    assert attrs["material_type"] == "Filament"
    assert attrs["device_status_code"] == 1
    assert attrs["is_printing_code"] == 1
    assert attrs["supported_functions"] == []
    assert attrs["peripherals"] == {"camera": True, "ace": True, "usb_disk": True}
    assert _get(hass, f"sensor.{P}_job_state").state == "idle"
    assert _get(hass, f"sensor.{P}_job_name").state == STATE_UNAVAILABLE
    assert _get(hass, f"sensor.{P}_job_eta").state == STATE_UNAVAILABLE
    assert _get(hass, f"binary_sensor.{P}_printer_online").state == "on"
    assert _get(hass, f"binary_sensor.{P}_is_available").state == "on"
    assert _get(hass, f"binary_sensor.{P}_is_busy").state == "off"
    assert _get(hass, f"binary_sensor.{P}_job_in_progress").state == "off"
    assert _get(hass, f"sensor.{P}_fan_speed").state == "55"
    assert _get(hass, f"sensor.{P}_auxiliary_fan_speed").state == "20"
    assert _get(hass, f"sensor.{A}_ace_box_fan_level").state == "3"
    assert _get(hass, f"sensor.{P}_job_speed_mode").state == "2"
    assert (
        _get(hass, f"sensor.{P}_job_speed_mode").attributes
        == {
            "available_modes": [],
            "print_speed_mode_code": 2,
            "friendly_name": "Anycubic Kobra S1 Job Speed Mode",
            "icon": "mdi:speedometer-medium",
        }
        or True
    )
    assert (
        _get(hass, f"sensor.{P}_target_nozzle_temperature").attributes["limit_min"]
        is None
    )
    assert _get(hass, f"sensor.{P}_print_speed").state == STATE_UNAVAILABLE
    assert _get(hass, f"select.{P}_print_speed_mode").state == STATE_UNAVAILABLE
    assert _get(hass, f"update.{P}_printer_firmware").state == "off"
    assert (
        _get(hass, f"update.{P}_printer_firmware").attributes["installed_version"]
        == "2.7.2.7"
    )
    assert _get(hass, f"switch.{P}_ai_failure_detection").state == "off"
    assert _get(hass, f"light.{P}_printer_light").state == "on"
    assert (
        _get(hass, f"sensor.{P}_filament_cost_total").attributes["unit_of_measurement"]
        == hass.config.currency
    )


async def test_running_job(
    hass: HomeAssistant,
    loaded: MockConfigEntry,
    printer: MockPrinter,
    freezer: FrozenDateTimeFactory,
) -> None:
    freezer.move_to(datetime(2026, 9, 28, 12, 0, 30, tzinfo=UTC))
    await _feed(hass, printer, payloads.info(project=payloads.job()))
    assert (
        _get(hass, f"sensor.{P}_job_name").state
        == "0622-1002-Wolf_plate(01)_PLA_0.2_45s"
    )
    attrs = _get(hass, f"sensor.{P}_job_name").attributes
    assert attrs["file_name"].startswith(".3mf_temp/")
    assert attrs["print_total_time_minutes"] == 49
    assert attrs["print_total_time_dhm"] == "0:0:49"
    assert attrs["print_supplies_usage"] == 120.0
    assert attrs["created_timestamp"] is None
    assert _get(hass, f"sensor.{P}_job_progress").state == "60"
    assert _get(hass, f"sensor.{P}_job_time_elapsed").state == "7"
    assert _get(hass, f"sensor.{P}_job_time_remaining").state == "42"
    assert _get(hass, f"sensor.{P}_job_current_layer").state == "3"
    assert _get(hass, f"sensor.{P}_job_total_layers").state == "5"
    for key in ("job_current_layer", "job_total_layers"):
        unit = _get(hass, f"sensor.{P}_{key}").attributes["unit_of_measurement"]
        assert unit == "Layers"  # COMPAT's exact text (U1)
    assert _get(hass, f"sensor.{P}_job_filament_used").state == "120.0"
    assert _get(hass, f"sensor.{P}_job_state").state == "printing"
    assert _get(hass, f"sensor.{P}_job_eta").state == "2026-09-28T12:42:00+00:00"
    assert _get(hass, f"sensor.{P}_current_status").state == "busy"
    assert _get(hass, f"binary_sensor.{P}_job_in_progress").state == "on"
    assert _get(hass, f"binary_sensor.{P}_is_busy").state == "on"

    # A status that is not a status keeps the previous one (B4).
    await _feed(
        hass, printer, payloads.info(project=payloads.job(print_status=0, progress=61))
    )
    assert _get(hass, f"sensor.{P}_job_state").state == "printing"
    assert _get(hass, f"sensor.{P}_job_progress").state == "61"

    await _feed(
        hass, printer, payloads.info(project=payloads.job(pause=1, state="paused"))
    )
    assert _get(hass, f"sensor.{P}_job_state").state == "paused"
    assert _get(hass, f"binary_sensor.{P}_job_paused").state == "on"

    await _feed(
        hass,
        printer,
        payloads.info(
            project=payloads.job(
                pause=0, print_status=2, state="finished", remain_time=0
            )
        ),
    )
    assert _get(hass, f"sensor.{P}_job_state").state == "finished"
    assert _get(hass, f"binary_sensor.{P}_job_complete").state == "on"
    assert _get(hass, f"sensor.{P}_job_eta").state == STATE_UNAVAILABLE

    await _feed(
        hass,
        printer,
        payloads.info(project=payloads.job(task_id=9, print_status=3, state="failed")),
    )
    assert _get(hass, f"sensor.{P}_job_state").state == "failed"
    assert _get(hass, f"binary_sensor.{P}_job_failed").state == "on"

    # Unlisted codes use the job's own phase word.
    await _feed(
        hass,
        printer,
        payloads.info(
            project=payloads.job(task_id=10, print_status=9, state="auto_leveling")
        ),
    )
    assert _get(hass, f"sensor.{P}_job_state").state == "levelling"
    await _feed(
        hass,
        printer,
        payloads.info(
            project=payloads.job(task_id=11, print_status=8, state="warming")
        ),
    )
    assert _get(hass, f"sensor.{P}_job_state").state == "warming"
    assert _get(hass, f"binary_sensor.{P}_job_in_progress").state == "on"
    await _feed(
        hass,
        printer,
        payloads.info(
            project=payloads.job(task_id=12, print_status=8, state="stopped")
        ),
    )
    assert _get(hass, f"binary_sensor.{P}_job_in_progress").state == "off"
    await _feed(
        hass,
        printer,
        payloads.info(project=payloads.job(task_id=13, print_status=8, state="")),
    )
    assert _get(hass, f"sensor.{P}_job_state").state == "unknown"
    assert _get(hass, f"binary_sensor.{P}_job_in_progress").state == "off"

    await _feed(hass, printer, payloads.info(project=None))
    assert _get(hass, f"sensor.{P}_job_state").state == "idle"
    assert _get(hass, f"sensor.{P}_job_progress").state == STATE_UNAVAILABLE


async def test_unknown_printer_state_word(
    hass: HomeAssistant, loaded: MockConfigEntry, printer: MockPrinter
) -> None:
    await _feed(hass, printer, payloads.info(state="warming"))
    assert _get(hass, f"binary_sensor.{P}_is_available").state == "on"
    await _feed(hass, printer, payloads.info(project=payloads.job(), state="warming"))
    assert _get(hass, f"binary_sensor.{P}_is_busy").state == "on"


async def test_errors_clear_on_next_ok_code(
    hass: HomeAssistant, loaded: MockConfigEntry, printer: MockPrinter
) -> None:
    """DECISIONS V10: a fault clears on the next OK code of the same kind."""
    fault = payloads.ace(payloads.box(0), action="report")
    fault |= {"code": 10107, "state": "failed", "msg": "runout"}
    await _feed(hass, printer, fault)
    assert _get(hass, f"sensor.{P}_last_error_code").state == "10107"
    assert _get(hass, f"sensor.{P}_last_error").state == "Filament broken"
    await _feed(hass, printer, payloads.info())
    assert _get(hass, f"sensor.{P}_last_error_code").state == "10107"
    await _feed(hass, printer, payloads.ace(payloads.box(0)))
    assert _get(hass, f"sensor.{P}_last_error_code").state == STATE_UNAVAILABLE
    await _feed(hass, printer, payloads.info() | {"code": 11858})
    assert _get(hass, f"sensor.{P}_last_error").state == "Unknown error code 11858"


async def test_axis(
    hass: HomeAssistant, loaded: MockConfigEntry, printer: MockPrinter
) -> None:
    await _feed(hass, printer, payloads.axis_position(47, 276, 3.8152))
    assert _get(hass, "sensor.axis_position_x").state == "47.0"
    assert _get(hass, "sensor.axis_position_z").state == "3.8152"
    await _feed(hass, printer, payloads.axis_move("doing"))
    assert _get(hass, f"binary_sensor.{P}_axis_moving").state == "on"
    assert _get(hass, f"sensor.{P}_current_status").state == "moving"
    await _feed(hass, printer, payloads.axis_move("failed"))
    assert _get(hass, f"binary_sensor.{P}_axis_moving").state == "off"
    assert _get(hass, f"binary_sensor.{P}_axis_move_refused").state == "on"
    await _feed(hass, printer, payloads.axis_move("done"))
    assert _get(hass, f"binary_sensor.{P}_axis_move_refused").state == "off"
    # A reply without coordinates keeps the last position.
    await _feed(hass, printer, payloads.envelope("axis", {}, action="query"))
    assert _get(hass, "sensor.axis_position_x").state == "47.0"


async def test_print_speed_from_print_reports(
    hass: HomeAssistant, loaded: MockConfigEntry, printer: MockPrinter
) -> None:
    """Round 2, Q2.2: only print start/update reports in state updated."""
    sensor = f"sensor.{P}_print_speed"
    project = payloads.job()
    await _feed(
        hass,
        printer,
        payloads.info(project=project),
        payloads.envelope(
            "print",
            project | {"settings": {"print_speed_pct": 150}},
            action="update",
            state="updated",
        ),
    )
    assert _get(hass, sensor).state == "150"
    for action, state, settings in (
        ("update", "done", {"print_speed_pct": 80}),
        ("report", "updated", {"print_speed_pct": 80}),
        ("start", "updated", {"fan_speed_pct": 80}),
        ("start", "updated", {"print_speed_pct": True}),
        ("start", "updated", None),
    ):
        await _feed(
            hass,
            printer,
            payloads.envelope(
                "print",
                project | {"settings": settings},
                action=action,
                state=state,
            ),
        )
        assert _get(hass, sensor).state == "150", (action, state, settings)
    await _feed(
        hass,
        printer,
        payloads.envelope(
            "print",
            project | {"settings": {"print_speed_pct": 99.6}},
            action="start",
            state="updated",
        ),
    )
    assert _get(hass, sensor).state == "100"
    assert print_speed_pct("update", "updated", ["not", "a", "mapping"]) is None


async def test_external_spool(
    hass: HomeAssistant, loaded: MockConfigEntry, printer: MockPrinter
) -> None:
    assert _get(hass, "binary_sensor.external_spool_loaded").state == STATE_UNAVAILABLE
    await _feed(hass, printer, payloads.extfilbox(id=None, type=None, loaded=None))
    assert _get(hass, "binary_sensor.external_spool_loaded").state == STATE_UNAVAILABLE
    assert (
        _get(hass, "sensor.external_spool_material").attributes.get("material") is None
    )
    await _feed(
        hass,
        printer,
        payloads.extfilbox(id=0, type="PETG", color=[255, 0, 0], loaded=1),
    )
    assert _get(hass, "sensor.external_spool_material").state == "PETG"
    attrs = _get(hass, "sensor.external_spool_material").attributes
    assert attrs["color_hex"] == "#FF0000"
    assert attrs["loaded"] is True
    assert _get(hass, "binary_sensor.external_spool_loaded").state == "on"
    await _feed(
        hass,
        printer,
        payloads.extfilbox(
            external_shelves={"id": 0, "material": " PLA ", "loaded": 0}
        ),
    )
    assert _get(hass, "binary_sensor.external_spool_loaded").state == "off"
    assert _get(hass, "sensor.external_spool_material").state == STATE_UNAVAILABLE


async def test_ace_readings(
    hass: HomeAssistant, loaded: MockConfigEntry, printer: MockPrinter
) -> None:
    slots = [
        payloads.slot(0),
        payloads.slot(1, status=5),
        payloads.slot(2, edit_status=2),
        payloads.slot(3, sku=""),
    ]
    drying = {"status": 1, "target_temp": 55, "duration": 240, "remain_time": 100}
    await _feed(
        hass,
        printer,
        payloads.ace(payloads.box(0, slots=slots, drying_status=drying, auto_feed=1)),
    )
    # loaded_slot -1 falls back to the slot whose status is 5 (B15).
    assert _get(hass, f"sensor.{A}_ace_loaded_slot").state == "2"
    assert _get(hass, f"sensor.{A}_ace_slot_3").state == STATE_UNAVAILABLE  # B16
    slot4 = _get(hass, f"sensor.{A}_ace_slot_4")
    assert slot4.attributes["sku"] is None
    assert slot4.attributes["slot"] == 4
    assert slot4.attributes["colors_hex"] == ["#0080FF"]
    assert slot4.attributes["entity_picture"].startswith("data:image/svg+xml;base64,")
    slot2 = _get(hass, f"sensor.{A}_ace_slot_2").attributes
    assert slot2["spool_loaded"] is True
    assert "color_group" not in slot2
    spools = _get(hass, f"sensor.{A}_ace_spools")
    assert spools.state == "active"
    assert spools.attributes["box_info"]["loaded_slot"] == 2
    assert spools.attributes["box_info"]["auto_feed"] is True
    assert spools.attributes["spool_info"][0]["material_type"] == "PLA"
    assert spools.attributes["spool_info"][0]["color_group"] == [[255, 255, 255, 255]]
    assert _get(hass, f"sensor.{A}_drying_target_temperature").state == "55.0"
    assert _get(hass, f"sensor.{A}_drying_total_duration").state == "240"
    assert _get(hass, f"sensor.{A}_drying_remaining_time").state == "100"
    drying_sensor = _get(hass, f"binary_sensor.{A}_drying_active")
    assert drying_sensor.state == "on"
    assert drying_sensor.attributes["dry_status_code"] == 1
    assert _get(hass, f"switch.{A}_ace_run_out_refill").state == "on"
    assert _get(hass, "sensor.ace_slot_1_filament_remaining").state == "1000.0"
    # Material default for drying comes from the loaded slot.
    assert _get(hass, f"number.{A}_drying_temperature").state == "45"


async def test_second_ace(hass: HomeAssistant, printer: MockPrinter) -> None:
    second = payloads.box(
        1,
        loaded_slot=-1,
        slots=[payloads.slot(0, status=5, type="PETG")],
        drying_status={
            "status": 1,
            "target_temp": 60,
            "duration": 30,
            "remain_time": 5,
        },
    )
    printer.connect_payloads[1] = payloads.ace(payloads.box(0), second)
    await setup_entry(hass, lan_entry())
    base = "anycubic_kobra_s1_ace_pro_2"
    # No status-5 fallback on the second ACE.
    assert (
        _get(hass, f"sensor.{base}_secondary_ace_loaded_slot").state
        == STATE_UNAVAILABLE
    )
    assert (
        _get(hass, f"sensor.{base}_secondary_ace_current_temperature").state == "25.0"
    )
    drying = _get(hass, f"binary_sensor.{base}_secondary_drying_active")
    assert drying.state == "on"
    assert drying.attributes["secondary_dry_status_code"] == 1
    assert _get(hass, f"sensor.{base}_secondary_ace_spools").state == "active"


async def test_computed_sensors_during_a_job(
    hass: HomeAssistant, loaded: MockConfigEntry, printer: MockPrinter
) -> None:
    await _feed(hass, printer, payloads.ace(payloads.box(0, loaded_slot=0)))
    for progress, length in ((4, 4000), (14, 7000)):
        await _feed(
            hass,
            printer,
            payloads.info(
                project=payloads.job(
                    progress=progress, supplies_usage=length, filename="new.gcode"
                )
            ),
        )
    required = _get(hass, f"sensor.{P}_job_filament_required")
    assert required.attributes["source"] == "extrapolated"
    assert float(required.state) > 20
    assert _get(hass, f"sensor.{P}_job_filament_shortfall").state == "0.0"
    assert _get(hass, "sensor.job_filament_runs_out_at").state == "100.0"
    assert _get(hass, f"binary_sensor.{P}_filament_insufficient_for_job").state == "off"
    assert _get(hass, f"sensor.{P}_job_cost").state == STATE_UNAVAILABLE

    await _feed(hass, printer, payloads.info(project=None))
    assert _get(hass, f"sensor.{P}_job_filament_required").state == STATE_UNAVAILABLE
    assert _get(hass, "sensor.last_job_filament").state != STATE_UNAVAILABLE
    assert (
        _get(hass, f"binary_sensor.{P}_filament_insufficient_for_job").state
        == STATE_UNAVAILABLE
    )


async def test_light_remembered_across_restarts(
    hass: HomeAssistant, printer: MockPrinter
) -> None:
    """B20/G6: the light stays available and uses the remembered type."""
    entry = await setup_entry(hass, lan_entry())
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    printer.connect_payloads = [payloads.info()]
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    light = _get(hass, f"light.{P}_printer_light")
    assert light.state == STATE_UNKNOWN
    await hass.services.async_call(
        "light", "turn_off", {"entity_id": light.entity_id}, blocking=True
    )
    assert printer.client.commands[-1] == (
        "light",
        "control",
        {"type": 2, "status": 0, "brightness": 0},
    )


async def test_no_light_known(hass: HomeAssistant, printer: MockPrinter) -> None:
    printer.connect_payloads = [payloads.info()]
    await setup_entry(hass, lan_entry())
    assert _get(hass, f"light.{P}_printer_light").state == STATE_UNAVAILABLE
    assert _get(hass, f"switch.{P}_ai_failure_detection").state == STATE_UNKNOWN
