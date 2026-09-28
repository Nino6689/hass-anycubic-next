"""The cloud forms of controls and actions (BEHAVIOUR §2.12-§2.16, §4)."""

from __future__ import annotations

from collections.abc import Iterator
import contextlib
from pathlib import Path
from typing import Any
from unittest.mock import patch

from anycubic_cloud_client import (
    AnycubicCloudError,
    Axis,
    FileSource,
    MoveType,
    OrderRefusedError,
    PaintInfo,
    PrintStartResult,
    SlotAssignment,
    SlotMappingError,
    StorageFullError,
    UploadError,
)
from homeassistant.core import Event, HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
)

from custom_components.anycubic_cloud.const import DOMAIN

from . import cloud_payloads as cp
from .cloud_fakes import FakeCloud
from .conftest import account_entry, find_device, setup_entry

P = "kobra_s1_cloud"
PID = cp.PRINTER_ID


@pytest.fixture
async def loaded(hass: HomeAssistant, cloud: FakeCloud) -> MockConfigEntry:
    """A busy printer with a running job; the link is up (mode 1)."""
    cloud.printers[PID]["is_printing"] = 2
    return await setup_entry(hass, account_entry())


def _target(entry: MockConfigEntry) -> dict[str, Any]:
    return {"config_entry": entry.entry_id, "printer_id": PID}


async def _call(hass: HomeAssistant, service: str, data: dict[str, Any]) -> None:
    await hass.services.async_call(DOMAIN, service, data, blocking=True)
    await hass.async_block_till_done()


async def _press(hass: HomeAssistant, key: str) -> None:
    await hass.services.async_call(
        "button", "press", {"entity_id": f"button.{P}_{key}"}, blocking=True
    )
    await hass.async_block_till_done()


def _last(cloud: FakeCloud, name: str) -> tuple[tuple[Any, ...], dict[str, Any]]:
    for order, args, kwargs in reversed(cloud.orders):
        if order == name:
            return args, kwargs
    raise AssertionError(f"{name} not sent: {cloud.order_names()}")


async def test_job_buttons(
    hass: HomeAssistant, loaded: MockConfigEntry, cloud: FakeCloud
) -> None:
    for key, order in (
        ("pause_print", "pause_print"),
        ("resume_print", "resume_print"),
        ("cancel_print", "cancel_print"),
    ):
        await _press(hass, key)
        assert _last(cloud, order) == ((PID, cp.JOB_ID), {})


async def test_job_buttons_without_a_job(hass: HomeAssistant, cloud: FakeCloud) -> None:
    cloud.jobs = []
    await setup_entry(hass, account_entry())
    await _press(hass, "pause_print")
    assert "pause_print" not in cloud.order_names()


async def test_axis_and_position(hass: HomeAssistant, cloud: FakeCloud) -> None:
    cloud.jobs = [cp.job(print_status=2)]
    entry = await setup_entry(hass, account_entry())
    await _press(hass, "move_x_plus")
    assert _last(cloud, "move_axis") == ((PID, Axis.X, MoveType(1), 1), {})
    await _press(hass, "home_z_axis")
    assert _last(cloud, "move_axis") == ((PID, Axis.Z, MoveType.HOME, 0), {})
    await _press(hass, "release_motors")
    assert _last(cloud, "motors_off") == ((PID,), {})
    # Disabled by default: pressed through its control.
    from custom_components.anycubic_cloud import control

    await control.async_request_position(entry.runtime_data.primary)
    assert _last(cloud, "query_axis_position") == ((PID,), {})


async def test_numbers_and_light(
    hass: HomeAssistant, loaded: MockConfigEntry, cloud: FakeCloud
) -> None:
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": f"number.{P}_set_nozzle_temperature", "value": 230},
        blocking=True,
    )
    assert _last(cloud, "set_temperature") == ((PID,), {"nozzle": 230, "bed": None})
    await _call(
        hass,
        "change_print_target_hotbed_temperature",
        _target(loaded) | {"temperature": 70},
    )
    assert _last(cloud, "set_temperature") == ((PID,), {"nozzle": None, "bed": 70})
    await _call(hass, "change_print_box_fan_speed", _target(loaded) | {"speed": 3})
    assert _last(cloud, "set_fan_speed") == ((PID,), {"box_fan_level": 3})
    cloud.feed(
        cp.mqtt("light", "query", "done", {"lights": [{"type": 2, "status": 0}]})
    )
    await hass.async_block_till_done(wait_background_tasks=True)
    await hass.services.async_call(
        "light", "turn_on", {"entity_id": f"light.{P}_printer_light"}, blocking=True
    )
    assert _last(cloud, "set_light") == (
        (PID, True, 100),
        {"light_type": 2, "job_id": cp.JOB_ID},
    )


async def test_ace_controls(
    hass: HomeAssistant, loaded: MockConfigEntry, cloud: FakeCloud
) -> None:
    await _press(hass, "ace_pro_start_drying")
    assert _last(cloud, "ace_start_drying") == (
        (PID, 0),
        {"target_temp": 45, "duration": 360},
    )
    await _press(hass, "ace_pro_drying_stop")
    assert _last(cloud, "ace_stop_drying") == ((PID, [0]), {})
    await _press(hass, "ace_pro_ace_retract_filament")
    assert _last(cloud, "ace_retract") == ((PID,), {"box_id": 0})
    await hass.services.async_call(
        "switch",
        "turn_off",
        {"entity_id": f"switch.{P}_ace_pro_ace_run_out_refill"},
        blocking=True,
    )
    assert _last(cloud, "ace_set_auto_refill") == ((PID, 0, False), {})
    target = _target(loaded)
    await _call(
        hass,
        "multi_color_box_set_slot_petg",
        target
        | {
            "slot_number": 2,
            "slot_color_red": 1,
            "slot_color_green": 2,
            "slot_color_blue": 3,
        },
    )
    assert _last(cloud, "ace_set_slot") == ((PID, 0, 1, [1, 2, 3], "PETG"), {})
    await _call(hass, "multi_color_box_filament_extrude", target | {"slot_number": 3})
    assert _last(cloud, "ace_feed") == ((PID, 2), {"box_id": 0})
    await _call(
        hass,
        "multi_color_box_filament_extrude",
        target | {"slot_number": 3, "finished": True},
    )
    assert _last(cloud, "ace_finish_feed") == ((PID, 2), {"box_id": 0})
    await _call(hass, "multi_color_box_filament_retract", target)
    assert _last(cloud, "ace_retract") == ((PID,), {"box_id": 0})


async def test_drying_preset_wakes(hass: HomeAssistant, cloud: FakeCloud) -> None:
    entry = account_entry()
    entry = account_entry(
        options={
            **entry.options,
            "drying_preset_duration_1": 120,
            "drying_preset_temperature_1": 50,
        }
    )
    await setup_entry(hass, entry)
    assert not cloud.links
    await _press(hass, "ace_pro_start_drying_preset_1")
    assert cloud.link.connects == 1
    assert _last(cloud, "ace_start_drying") == (
        (PID, 0),
        {"target_temp": 50, "duration": 120},
    )


async def test_ai_detection(
    hass: HomeAssistant, loaded: MockConfigEntry, cloud: FakeCloud
) -> None:
    entity = f"switch.{P}_ai_failure_detection"
    assert hass.states.get(entity).state == "unknown"
    ai = {"status": 0, "type": 1, "count": 30, "sensitivity_level": [2, 2]}
    cloud.feed(cp.mqtt("aiSettings", "query", "done", {"ai_settings": ai}))
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get(entity).state == "off"
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": entity}, blocking=True
    )
    args, _ = _last(cloud, "set_ai_detection")
    assert args[:2] == (PID, True)
    assert args[2]["count"] == 30
    assert args[2]["sensitivity_level"] == [2, 2]
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": entity}, blocking=True
    )
    assert _last(cloud, "set_ai_detection")[0][1] is False


async def test_order_refused_and_cloud_errors(
    hass: HomeAssistant, loaded: MockConfigEntry, cloud: FakeCloud
) -> None:
    cloud.order_error = OrderRefusedError(
        "refused", server_message="Print task does not exist"
    )
    with pytest.raises(HomeAssistantError) as err:
        await _press(hass, "ace_pro_start_drying")
    assert err.value.translation_key == "printer_error"
    assert err.value.translation_placeholders == {
        "message": "Print task does not exist"
    }
    cloud.order_error = AnycubicCloudError("boom")
    with pytest.raises(HomeAssistantError) as err:
        await _press(hass, "ace_pro_start_drying")
    assert err.value.translation_key == "cloud_error"


async def test_speed_mode(
    hass: HomeAssistant, loaded: MockConfigEntry, cloud: FakeCloud
) -> None:
    await _call(hass, "change_print_speed_mode", _target(loaded) | {"speed_mode": 3})
    assert _last(cloud, "set_print_settings") == (
        (PID, cp.JOB_ID, {"print_speed_mode": 3}),
        {},
    )
    with pytest.raises(ServiceValidationError) as err:
        await _call(
            hass, "change_print_speed_mode", _target(loaded) | {"speed_mode": 9}
        )
    assert err.value.translation_key == "speed_mode_unavailable"
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": f"select.{P}_print_speed_mode", "option": "Silent"},
        blocking=True,
    )
    assert _last(cloud, "set_print_settings")[0][2] == {"print_speed_mode": 1}
    select = hass.data["entity_components"]["select"].get_entity(
        f"select.{P}_print_speed_mode"
    )
    with pytest.raises(ServiceValidationError):
        await select.async_select_option("Ludicrous")


async def test_speed_mode_refused_while_idle(
    hass: HomeAssistant, cloud: FakeCloud
) -> None:
    """The list survives the job: available while idle, but refuses (§2.14)."""
    cloud.jobs = [cp.job(print_status=2)]
    entry = await setup_entry(hass, account_entry())
    assert hass.states.get(f"select.{P}_print_speed_mode").state == "Standard"
    with pytest.raises(ServiceValidationError) as err:
        await _call(hass, "change_print_speed_mode", _target(entry) | {"speed_mode": 1})
    assert err.value.translation_key == "printer_not_busy"


async def test_resin_settings(
    hass: HomeAssistant, loaded: MockConfigEntry, cloud: FakeCloud
) -> None:
    await _call(hass, "change_print_bottom_layers", _target(loaded) | {"layers": 6})
    assert _last(cloud, "set_print_settings")[0] == (
        PID,
        cp.JOB_ID,
        {"bottom_layers": 6},
    )
    await _call(hass, "change_print_on_time", _target(loaded) | {"time": 2.5})
    assert _last(cloud, "set_print_settings")[0][2] == {"on_time": 2.5}


async def test_print_local_file(hass: HomeAssistant, cloud: FakeCloud) -> None:
    cloud.jobs = [cp.job(print_status=2)]
    entry = await setup_entry(hass, account_entry())
    await _call(hass, "print_local_file", _target(entry) | {"filename": "part.gcode"})
    assert _last(cloud, "start_print_printer_file") == (
        (PID, "part.gcode", FileSource.LOCAL),
        {},
    )


async def test_print_local_file_refused_while_busy(
    hass: HomeAssistant, loaded: MockConfigEntry, cloud: FakeCloud
) -> None:
    with pytest.raises(ServiceValidationError) as err:
        await _call(hass, "print_local_file", _target(loaded) | {"filename": "a"})
    assert err.value.translation_key == "printer_busy"


async def test_delete_printer_files(
    hass: HomeAssistant, loaded: MockConfigEntry, cloud: FakeCloud
) -> None:
    """Order 104/102, then the list is asked for 2 s and 7 s later (§4.5)."""
    await _call(hass, "delete_file_udisk", _target(loaded) | {"filename": "x.gcode"})
    assert _last(cloud, "delete_printer_file") == (
        (PID, FileSource.UDISK, "x.gcode"),
        {},
    )
    await hass.async_block_till_done(wait_background_tasks=True)
    lists = [o for o in cloud.orders if o[0] == "request_file_list"]
    assert lists == [
        ("request_file_list", (PID, FileSource.UDISK), {}),
        ("request_file_list", (PID, FileSource.UDISK), {}),
    ]


async def test_delete_cloud_file(
    hass: HomeAssistant, loaded: MockConfigEntry, cloud: FakeCloud
) -> None:
    await _call(hass, "delete_file_cloud", _target(loaded) | {"file_id": 700001})
    assert _last(cloud, "delete_cloud_files") == (([700001],), {})
    await hass.async_block_till_done(wait_background_tasks=True)
    # Fetched again after the delete (5 s later; no delay in tests).
    assert hass.states.get(f"sensor.{P}_file_list_cloud").state == "1"
    cloud.order_error = OrderRefusedError("no", server_message="no")
    with pytest.raises(HomeAssistantError) as err:
        await _call(hass, "delete_file_cloud", _target(loaded) | {"file_id": 1})
    assert err.value.translation_key == "cloud_file_delete_failed"
    cloud.order_error = AnycubicCloudError("down")
    with pytest.raises(HomeAssistantError) as err:
        await _call(hass, "delete_file_cloud", _target(loaded) | {"file_id": 1})
    assert err.value.translation_key == "cloud_error"


async def test_file_list_buttons(
    hass: HomeAssistant, loaded: MockConfigEntry, cloud: FakeCloud
) -> None:
    """F3: available whenever the list can be fetched."""
    for name in ("local", "usb_disk", "cloud"):
        state = hass.states.get(f"button.{P}_request_file_list_{name}")
        assert state.state != "unavailable", name
    await _press(hass, "request_file_list_cloud")
    state = hass.states.get(f"sensor.{P}_file_list_cloud")
    assert state.state == "1"
    (info,) = state.attributes["file_info"]
    assert info == {
        "id": 700001,
        "name": "benchy.gcode",
        "size_mb": 1.234567,
        "thumbnail": cp.cloud_file()["thumbnail"],
        "estimate_seconds": 3600,
        "material": "PLA",
        "layer_height": 0.2,
        "filament_mm": 4567,
        "dimensions": {"x": 60.0, "y": 31.0, "z": 48.0},
    }
    await _press(hass, "request_file_list_usb_disk")
    assert _last(cloud, "request_file_list") == ((PID, FileSource.UDISK), {})


async def test_local_file_list_retry(
    hass: HomeAssistant, loaded: MockConfigEntry, cloud: FakeCloud
) -> None:
    """No list 5 s after the press: the link restarts once and asks again."""
    link = cloud.link
    await _press(hass, "request_file_list_local")
    await hass.async_block_till_done(wait_background_tasks=True)
    lists = [o for o in cloud.orders if o[0] == "request_file_list"]
    assert len(lists) == 2
    assert link.disconnects == 1
    # With a list, no retry.
    cloud.feed(cp.mqtt("file", "listLocal", "done", {"records": []}))
    await hass.async_block_till_done(wait_background_tasks=True)
    await _press(hass, "request_file_list_local")
    await hass.async_block_till_done(wait_background_tasks=True)
    assert len([o for o in cloud.orders if o[0] == "request_file_list"]) == 3


async def test_local_file_list_retry_is_single_flight(
    hass: HomeAssistant, loaded: MockConfigEntry, cloud: FakeCloud
) -> None:
    coordinator = loaded.runtime_data.primary
    coordinator.local_list_retry_pending = True
    await _press(hass, "request_file_list_local")
    await hass.async_block_till_done(wait_background_tasks=True)
    assert len([o for o in cloud.orders if o[0] == "request_file_list"]) == 1


@pytest.fixture
def upload(tmp_path: Path) -> Iterator[Path]:
    path = tmp_path / "cube.gcode"
    path.write_bytes(b"; gcode")

    @contextlib.contextmanager
    def fake(hass: HomeAssistant, file_id: str) -> Iterator[Path]:
        if file_id == "missing":
            raise ValueError("File does not exist")
        yield path

    with (
        patch("custom_components.anycubic_cloud.upload.process_uploaded_file", fake),
        patch("custom_components.anycubic_cloud.upload.UPLOAD_READ_DELAY", 0),
    ):
        yield path


def _result() -> PrintStartResult:
    return PrintStartResult(
        msgid="msg-1",
        printer_id=PID,
        saved_in_cloud=True,
        file_name="cube.gcode",
        cloud_file_id=11,
        gcode_id=12,
        colors=(PaintInfo(0, "PLA", 3.2, raw={"paint_index": 0}),),
        mapping=(SlotAssignment(1, 0, "PLA", 3.2, (1, 2, 3), (1, 2, 3)),),
    )


async def test_print_and_upload(
    hass: HomeAssistant,
    loaded: MockConfigEntry,
    cloud: FakeCloud,
    upload: Path,
) -> None:
    events: list[Event] = []
    hass.bus.async_listen(DOMAIN, events.append)
    cloud.upload_result = _result()
    await _call(
        hass,
        "print_and_upload_save_in_cloud",
        _target(loaded) | {"uploaded_gcode_file": "abc", "slot_number": 2},
    )
    args, kwargs = _last(cloud, "upload_and_print")
    assert args == (PID, "cube.gcode", b"; gcode")
    assert kwargs["save_in_cloud"] is True
    assert kwargs["slots"] == [1]
    assert len(kwargs["ace_units"]) == 1
    (event,) = events
    device = find_device(hass, f"{cp.USER_ID}-{PID}")
    assert event.data == {
        "printer_id": PID,
        "printer_name": "Kobra S1 Cloud",
        "device_id": device.id,
        "type": "print_cloud_start",
        "event_data": {
            "order_msg_id": "msg-1",
            "printer_id": PID,
            "saved_in_cloud": True,
            "file_name": "cube.gcode",
            "cloud_file_id": 11,
            "gcode_id": 12,
            "material_list": [{"paint_index": 0}],
            "ams_box_mapping": [
                {
                    "ams_color": [1, 2, 3],
                    "ams_index": 1,
                    "filament_used": 3.2,
                    "material_type": "PLA",
                    "paint_color": [1, 2, 3],
                    "paint_index": 0,
                }
            ],
        },
    }
    cloud.upload_result = PrintStartResult(
        msgid=None,
        printer_id=PID,
        saved_in_cloud=False,
        file_name="cube.gcode",
        cloud_file_id=11,
    )
    await _call(
        hass,
        "print_and_upload_no_cloud_save",
        _target(loaded) | {"uploaded_gcode_file": "abc", "slot_number": [2, 1]},
    )
    assert _last(cloud, "upload_and_print")[1]["save_in_cloud"] is False
    assert events[-1].data["event_data"]["ams_box_mapping"] is None


@pytest.mark.parametrize(
    ("data", "key"),
    [
        ({"uploaded_gcode_file": "abc"}, "slots_required"),
        ({"uploaded_gcode_file": "abc", "slot_number": 9}, "slot_not_on_ace"),
        ({"uploaded_gcode_file": "missing", "slot_number": 1}, "gcode_read_failed"),
    ],
)
async def test_print_and_upload_validation(
    hass: HomeAssistant,
    loaded: MockConfigEntry,
    cloud: FakeCloud,
    upload: Path,
    data: dict[str, Any],
    key: str,
) -> None:
    with pytest.raises(ServiceValidationError) as err:
        await _call(hass, "print_and_upload_save_in_cloud", _target(loaded) | data)
    assert err.value.translation_key == key
    assert "upload_and_print" not in cloud.order_names()


async def test_print_and_upload_without_ace(
    hass: HomeAssistant, cloud: FakeCloud, upload: Path
) -> None:
    cloud.printers[PID]["multi_color_box"] = []
    cloud.printers[PID]["type_function_ids"] = [2]
    entry = await setup_entry(hass, account_entry())
    with pytest.raises(ServiceValidationError) as err:
        await _call(
            hass,
            "print_and_upload_save_in_cloud",
            _target(entry) | {"uploaded_gcode_file": "abc", "slot_number": 1},
        )
    assert err.value.translation_key == "slots_not_allowed"
    cloud.upload_result = _result()
    await _call(
        hass,
        "print_and_upload_save_in_cloud",
        _target(entry) | {"uploaded_gcode_file": "abc"},
    )
    assert _last(cloud, "upload_and_print")[1]["slots"] is None


@pytest.mark.parametrize(
    ("error", "key"),
    [
        (SlotMappingError("not enough"), "slot_mapping_failed"),
        (StorageFullError("full"), "cloud_storage_full"),
        (UploadError("claim"), "cloud_error"),
    ],
)
async def test_print_and_upload_failures(
    hass: HomeAssistant,
    loaded: MockConfigEntry,
    cloud: FakeCloud,
    upload: Path,
    error: Exception,
    key: str,
) -> None:
    cloud.upload_result = error
    with pytest.raises(HomeAssistantError) as err:
        await _call(
            hass,
            "print_and_upload_no_cloud_save",
            _target(loaded) | {"uploaded_gcode_file": "abc", "slot_number": 1},
        )
    assert err.value.translation_key == key


async def test_actions_by_device(
    hass: HomeAssistant, loaded: MockConfigEntry, cloud: FakeCloud
) -> None:
    device = find_device(hass, f"{cp.USER_ID}-{PID}")
    await _call(
        hass,
        "change_print_fan_speed",
        {"config_entry": loaded.entry_id, "device_id": device.id, "speed": 30},
    )
    assert _last(cloud, "set_fan_speed") == ((PID,), {"fan_speed_pct": 30})
    with pytest.raises(ServiceValidationError) as err:
        await _call(
            hass,
            "change_print_fan_speed",
            {"config_entry": loaded.entry_id, "printer_id": 1, "speed": 30},
        )
    assert err.value.translation_key == "printer_not_found"
