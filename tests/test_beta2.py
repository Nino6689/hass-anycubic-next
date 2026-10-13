"""Beta 2: field reports from 2.x users, 2026-10-13 (ACCEPTANCE.md D1-D8).

Each test is named after the item it accepts. Printer messages run through
the libraries' own parsers: anycubic-lan for LAN (the fake LAN client) and
anycubic-cloud-client for the cloud MQTT (the fake link).
"""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from anycubic_cloud_client import AnycubicCloudError
from anycubic_lan import AceBox, AceSlot, PrinterState
from homeassistant.core import HomeAssistant
import homeassistant.util.dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.anycubic_cloud.control import drying_temperature
from custom_components.anycubic_cloud.model import (
    Printer,
    PrinterIdentity,
    ace_slot_for_channel,
)

from . import cloud_payloads as cp, payloads
from .cloud_fakes import FakeCloud
from .conftest import MockPrinter, account_entry, lan_entry, setup_entry

P = "anycubic_kobra_s1"
A = "anycubic_kobra_s1_ace_pro"
C = "kobra_s1_cloud"

KOBRA_X_PROGRESS: dict[str, Any] = {
    "curr_layer": 4,
    "file_root_path": "/useremain/app/gk/gcodes",
    "filename": "cube.gcode",
    "filetype": 1,
    "print_time": 9,
    "progress": 71,
    "remain_time": 30,
    "settings": {"light": 0},
    "supplies_usage": 150,
    "total_layers": 5,
}
S1_PROGRESS_EXTRAS: dict[str, Any] = {
    "display_filename": "cube",
    "origin3mf": "cube.3mf",
    "source_info": {"source": "local"},
    "temp_gcode": "/useremain/tmp/cube.gcode",
}


async def _settle(hass: HomeAssistant) -> None:
    await hass.async_block_till_done(wait_background_tasks=True)


async def _press(hass: HomeAssistant, entity_id: str) -> None:
    await hass.services.async_call(
        "button", "press", {"entity_id": entity_id}, blocking=True
    )
    await _settle(hass)


def _state(hass: HomeAssistant, entity_id: str) -> str:
    state = hass.states.get(entity_id)
    assert state is not None, entity_id
    return state.state


def _no_warnings(caplog: pytest.LogCaptureFixture) -> None:
    noisy = [
        r
        for r in caplog.records
        if r.levelno >= logging.WARNING and "turbojpeg" not in r.getMessage()
    ]
    assert not noisy, [r.getMessage() for r in noisy]


@pytest.fixture
async def lan(hass: HomeAssistant, printer: MockPrinter) -> MockConfigEntry:
    options = {
        "lan_mode_enabled": True,
        "lan_host": payloads.HOST,
        "drying_preset_duration_1": 120,
        "drying_preset_temperature_1": 70,
    }
    return await setup_entry(hass, lan_entry(options=options))


async def _cloud(hass: HomeAssistant, mode: int = 4) -> MockConfigEntry:
    entry = account_entry()
    options = {
        **entry.options,
        "mqtt_connect_mode": mode,
        "drying_preset_duration_1": 240,
        "drying_preset_temperature_1": 65,
    }
    return await setup_entry(hass, account_entry(options=options))


# -- D1: ACE Pro drying limit ---------------------------------------------------


def _drying_sent(printer: MockPrinter) -> dict[str, Any]:
    kind, action, data = printer.client.commands[-1]
    assert (kind, action) == ("multiColorBox", "setDry")
    drying: dict[str, Any] = data["multi_color_box"][0]["drying_status"]
    return drying


async def test_d1_ace_pro_drying_is_capped_at_55(
    hass: HomeAssistant, lan: MockConfigEntry, printer: MockPrinter
) -> None:
    petg = [payloads.slot(i, type="PETG") for i in range(4)]
    printer.client.feed(payloads.ace(payloads.box(0, slots=petg)))
    await _settle(hass)
    # A material default above the limit (PETG 65 °C).
    assert _state(hass, f"number.{A}_drying_temperature") == "55.0"
    await _press(hass, f"button.{A}_start_drying")
    assert _drying_sent(printer)["target_temp"] == 55
    # A preset above the limit (70 °C).
    await _press(hass, f"button.{A}_start_drying_preset_1")
    assert _drying_sent(printer)["target_temp"] == 55
    assert _drying_sent(printer)["duration"] == 120
    # A value the user set.
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": f"number.{A}_drying_temperature", "value": 62},
        blocking=True,
    )
    await _settle(hass)
    assert _state(hass, f"number.{A}_drying_temperature") == "55.0"
    await _press(hass, f"button.{A}_start_drying")
    assert _drying_sent(printer)["target_temp"] == 55
    # Below the limit nothing changes.
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": f"number.{A}_drying_temperature", "value": 50},
        blocking=True,
    )
    await _press(hass, f"button.{A}_start_drying")
    assert _drying_sent(printer)["target_temp"] == 50


async def test_d1_other_ace_models_are_sent_what_was_asked(
    hass: HomeAssistant, lan: MockConfigEntry, printer: MockPrinter
) -> None:
    petg = [payloads.slot(i, type="PETG") for i in range(4)]
    printer.client.feed(payloads.ace(payloads.box(0, model_id=40002, slots=petg)))
    await _settle(hass)
    assert _state(hass, f"number.{A}_drying_temperature") == "65.0"
    await _press(hass, f"button.{A}_start_drying")
    assert _drying_sent(printer)["target_temp"] == 65
    await _press(hass, f"button.{A}_start_drying_preset_1")
    assert _drying_sent(printer)["target_temp"] == 70


def test_d1_limit_by_model_id() -> None:
    identity = PrinterIdentity(1, "MAC", "P", "Kobra S1", 20025, "Filament", "h")
    printer = Printer(identity=identity)
    assert drying_temperature(printer, 0, 70) == 70  # no ACE known
    for model_id, expected in ((40001, 55), (40002, 70), (None, 70)):
        printer.state = PrinterState(ace_boxes=(AceBox(id=0, model_id=model_id),))
        assert drying_temperature(printer, 0, 70) == expected
    assert drying_temperature(printer, 0, 45) == 45


async def test_d1_cloud_drying_is_capped(hass: HomeAssistant, cloud: FakeCloud) -> None:
    await _cloud(hass)
    await _press(hass, f"button.{C}_ace_pro_start_drying_preset_1")
    _, args, kwargs = next(o for o in cloud.orders if o[0] == "ace_start_drying")
    assert args == (cp.PRINTER_ID, 0)
    assert kwargs == {"target_temp": 55, "duration": 240}


# -- D2: a refused drying start is visible --------------------------------------


@pytest.mark.parametrize(
    "refusal",
    [
        {"state": "failed", "code": 11505},
        {"state": "failed", "code": 200, "data": {"code": 11505}},
    ],
)
async def test_d2_lan_refused_drying_start(
    hass: HomeAssistant,
    lan: MockConfigEntry,
    printer: MockPrinter,
    caplog: pytest.LogCaptureFixture,
    refusal: dict[str, Any],
) -> None:
    await _press(hass, f"button.{A}_start_drying")
    order = {"id": 0, "drying_status": {"status": 1, "target_temp": 45}}
    reply = payloads.ace(order, action="setDry") | refusal
    with caplog.at_level(logging.WARNING):
        printer.client.feed(reply)
        await _settle(hass)
    assert "error 11505" in caplog.text
    assert "The drying request did not enter the target temperature" in caplog.text
    assert _state(hass, f"sensor.{P}_last_error_code") == "11505"
    assert _state(hass, f"sensor.{P}_last_error") == (
        "The drying request did not enter the target temperature"
    )
    # The ACE does not read as drying.
    assert _state(hass, f"binary_sensor.{A}_drying_active") == "off"


@pytest.mark.parametrize(
    ("code", "data"),
    [(11505, {}), (200, {"code": 11505, "msg": "x"})],
)
async def test_d2_cloud_refused_drying_start(
    hass: HomeAssistant,
    cloud: FakeCloud,
    caplog: pytest.LogCaptureFixture,
    code: int,
    data: dict[str, Any],
) -> None:
    await _cloud(hass)
    await _press(hass, f"button.{C}_ace_pro_start_drying_preset_1")
    with caplog.at_level(logging.WARNING):
        cloud.feed(cp.mqtt("multiColorBox", "setDry", "failed", data, code=code))
        await _settle(hass)
    assert "The ACE refused the drying order: error 11505" in caplog.text
    assert _state(hass, f"sensor.{C}_last_error_code") == "11505"
    assert _state(hass, f"binary_sensor.{C}_ace_pro_drying_active") == "off"


# -- D3: the second ACE after a restart ------------------------------------------


async def test_d3_cloud_asks_for_boxes_once_per_connection(
    hass: HomeAssistant, cloud: FakeCloud
) -> None:
    cloud.printers[cp.PRINTER_ID]["multi_color_box"] = [cp.ace_box(0), cp.ace_box(1)]
    entry = await _cloud(hass)
    assert cloud.link.connects == 1
    assert cloud.order_names().count("ace_get_info") == 1
    assert ("ace_get_info", (cp.PRINTER_ID,), {}) in cloud.orders
    # A poll, or the link dropping, sends nothing; coming back is a new
    # connection and asks once more.
    await entry.runtime_data.primary.async_refresh()
    cloud.link.drop()
    await _settle(hass)
    assert cloud.order_names().count("ace_get_info") == 1
    await cloud.link.connect()
    await _settle(hass)
    assert cloud.order_names().count("ace_get_info") == 2


async def test_d3_never_opens_or_holds_the_cloud_link(
    hass: HomeAssistant, cloud: FakeCloud
) -> None:
    """Mode 1 (while printing), idle: no link, so no request; once a link is
    up and the printer idles, it is released on the usual 15-minute clock."""
    cloud.jobs = [cp.job(print_status=2, end_time=1790009999)]
    entry = await _cloud(hass, mode=1)
    assert not cloud.links
    assert "ace_get_info" not in cloud.order_names()
    mqtt = entry.runtime_data.cloud.mqtt
    now = [5000.0]
    mqtt._clock = lambda: now[0]
    cloud.printers[cp.PRINTER_ID]["is_printing"] = 2
    entry.runtime_data.cloud._next_due = None
    await entry.runtime_data.primary.async_refresh()
    await _settle(hass)
    assert cloud.link.connects == 1
    assert cloud.order_names().count("ace_get_info") == 1
    # The request is not an action: nothing extends the link's life.
    assert mqtt._last_action is None
    cloud.printers[cp.PRINTER_ID]["is_printing"] = 1
    for step in (0, 800, 101):
        now[0] += step
        entry.runtime_data.cloud._next_due = None
        await entry.runtime_data.primary.async_refresh()
        await _settle(hass)
    assert cloud.link.disconnects == 1
    assert cloud.link.connects == 1


async def test_d3_cloud_request_skips_printers_without_ace_and_errors(
    hass: HomeAssistant, cloud: FakeCloud
) -> None:
    cloud.printers[cp.PRINTER_ID]["multi_color_box"] = None
    cloud.printers[cp.PRINTER_ID]["type_function_ids"] = []
    await _cloud(hass)
    assert "ace_get_info" not in cloud.order_names()
    cloud.printers[cp.PRINTER_ID]["multi_color_box"] = [cp.ace_box(0)]
    cloud.printers[cp.PRINTER_ID]["type_function_ids"] = [2006]
    entry = hass.config_entries.async_entries("anycubic_cloud")[0]
    entry.runtime_data.cloud._next_due = None
    await entry.runtime_data.primary.async_refresh()
    cloud.order_error = AnycubicCloudError("down")
    cloud.link.drop()
    await cloud.link.connect()
    await _settle(hass)
    assert cloud.order_names().count("ace_get_info") == 1  # failed, logged


async def test_d3_lan_connection_asks_for_boxes(
    hass: HomeAssistant, lan: MockConfigEntry, printer: MockPrinter
) -> None:
    """Over LAN, anycubic-lan sends every query, the box list among them,
    on each connection (its test ``test_box_report_requested_once_per_
    connection``); the integration's refresh asks again while connected."""
    printer.client.feed(payloads.ace(payloads.box(0), payloads.box(1)))
    await _settle(hass)
    assert _state(hass, f"sensor.{P}_ace_pro_2_secondary_ace_loaded_slot") is not None
    await lan.runtime_data.primary.async_refresh()
    assert printer.client.queries[-1] == "all"


# -- D4: active channel on the Kobra X ---------------------------------------------


def _boxes(*sizes: int) -> tuple[AceBox, ...]:
    return tuple(
        AceBox(id=i, slots=tuple(AceSlot(index=s) for s in range(size)))
        for i, size in enumerate(sizes)
    )


def test_d4_channel_numbering() -> None:
    """The inferred numbering: from 1, across every box in order."""
    one = _boxes(4)
    assert ace_slot_for_channel(one, 3) == (0, 2)
    assert ace_slot_for_channel(one, 4) == (0, 3)
    assert ace_slot_for_channel(one, 0) is None
    assert ace_slot_for_channel(one, 5) is None
    two = _boxes(4, 4)
    assert ace_slot_for_channel(two, 5) == (1, 0)
    assert ace_slot_for_channel(two, 8) == (1, 3)
    assert ace_slot_for_channel(_boxes(0, 4), 6) == (1, 1)  # unlisted: 4 slots


def _channel(channel: int) -> dict[str, Any]:
    return {"channel_no": channel, "settings": {"light": 0}}


async def test_d4_lan_loaded_slot_follows_channel_no(
    hass: HomeAssistant, lan: MockConfigEntry, printer: MockPrinter
) -> None:
    printer.client.feed(payloads.ace(payloads.box(0, loaded_slot=0)))
    printer.client.feed(payloads.info(project=payloads.job()))
    await _settle(hass)
    sensor = f"sensor.{A}_ace_loaded_slot"
    assert _state(hass, sensor) == "1"
    for channel, shown in ((3, "3"), (4, "4")):
        printer.client.feed(
            payloads.envelope(
                "print", _channel(channel), action="update", state="updated"
            )
        )
        # The box list repeats its stale loaded slot: the channel still wins.
        printer.client.feed(payloads.ace(payloads.box(0, loaded_slot=0)))
        await _settle(hass)
        assert _state(hass, sensor) == shown
    # The ACE reports a change of its own again: it speaks for itself.
    printer.client.feed(
        payloads.ace(payloads.box(0, loaded_slot=1), action="autoUpdateInfo")
    )
    await _settle(hass)
    assert _state(hass, sensor) == "2"


async def test_d4_second_box_and_cloud_channel(
    hass: HomeAssistant, cloud: FakeCloud
) -> None:
    cloud.printers[cp.PRINTER_ID]["machine_type"] = 20030
    cloud.printers[cp.PRINTER_ID]["multi_color_box"] = [cp.ace_box(0), cp.ace_box(1)]
    await _cloud(hass)
    first = f"sensor.{C}_ace_pro_ace_loaded_slot"
    second = f"sensor.{C}_ace_pro_2_secondary_ace_loaded_slot"
    assert (_state(hass, first), _state(hass, second)) == ("2", "2")
    cloud.feed(cp.mqtt("print", "update", "updated", _channel(6)))
    await _settle(hass)
    # Channel 6 is the second box's slot 2; the first box feeds nothing.
    assert _state(hass, second) == "2"
    assert _state(hass, first) == "unavailable"
    cloud.feed(cp.mqtt("print", "update", "updated", _channel(3)))
    await _settle(hass)
    assert (_state(hass, first), _state(hass, second)) == ("3", "unavailable")
    # A channel past every slot names none: the boxes' own readings stand.
    cloud.feed(cp.mqtt("print", "update", "updated", _channel(9)))
    await _settle(hass)
    assert (_state(hass, first), _state(hass, second)) == ("2", "2")


# -- D5: progress-only print updates ------------------------------------------------


@pytest.mark.parametrize("extras", [{}, S1_PROGRESS_EXTRAS])
async def test_d5_lan_progress_without_task_id(
    hass: HomeAssistant,
    lan: MockConfigEntry,
    printer: MockPrinter,
    caplog: pytest.LogCaptureFixture,
    extras: dict[str, Any],
) -> None:
    printer.client.feed(payloads.info(project=payloads.job()))
    await _settle(hass)
    caplog.clear()
    with caplog.at_level(logging.DEBUG):
        printer.client.feed(
            payloads.envelope(
                "print", KOBRA_X_PROGRESS | extras, action="update", state="updated"
            )
        )
        await _settle(hass)
    assert _state(hass, f"sensor.{P}_job_progress") == "71"
    assert _state(hass, f"sensor.{P}_job_current_layer") == "4"
    assert _state(hass, f"sensor.{P}_job_time_remaining") == "30"
    assert _state(hass, f"sensor.{P}_job_state") == "printing"
    _no_warnings(caplog)


@pytest.mark.parametrize("extras", [{}, S1_PROGRESS_EXTRAS])
async def test_d5_cloud_progress_without_task_id(
    hass: HomeAssistant,
    cloud: FakeCloud,
    caplog: pytest.LogCaptureFixture,
    extras: dict[str, Any],
) -> None:
    cloud.printers[cp.PRINTER_ID]["is_printing"] = 2
    await _cloud(hass)
    caplog.clear()
    with caplog.at_level(logging.DEBUG):
        cloud.feed(cp.mqtt("print", "update", "updated", KOBRA_X_PROGRESS | extras))
        await _settle(hass)
    assert _state(hass, f"sensor.{C}_job_progress") == "71"
    assert _state(hass, f"sensor.{C}_job_current_layer") == "4"
    assert _state(hass, f"sensor.{C}_job_time_remaining") == "30"
    _no_warnings(caplog)


# -- D6: LAN print speed presets -------------------------------------------------------


async def test_d6_lan_speed_presets(
    hass: HomeAssistant, lan: MockConfigEntry, printer: MockPrinter
) -> None:
    select = f"select.{P}_print_speed_mode"
    state = hass.states.get(select)
    assert state is not None
    assert state.attributes["options"] == ["Silent", "Standard", "Sport"]
    assert state.state == "Standard"
    printer.client.feed(payloads.info(project=payloads.job()))
    await _settle(hass)
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": select, "option": "Sport"},
        blocking=True,
    )
    assert printer.client.commands[-1] == (
        "print",
        "update",
        {"taskid": "614707220", "settings": {"print_speed_mode": 3}},
    )


async def test_d6_a_reported_list_wins(hass: HomeAssistant, cloud: FakeCloud) -> None:
    cloud.printers[cp.PRINTER_ID]["is_printing"] = 2
    await _cloud(hass)
    state = hass.states.get(f"select.{C}_print_speed_mode")
    assert state is not None
    detail_modes = cp.job_detail()["print_speed_model_des"]
    assert state.attributes["options"] == [m["title"] for m in detail_modes]


def test_d6_no_presets_for_resin_or_an_unknown_code() -> None:
    identity = PrinterIdentity(1, "MAC", "P", "Photon", 1, "Resin", "h")
    assert Printer(identity=identity).selectable_speed_modes == []


# -- D7: Kobra 4 camera (see also test_camera.test_kobra_x_relay) --------------------


async def test_d7_kobra_4_stream_is_relayed(
    hass: HomeAssistant, printer: MockPrinter
) -> None:
    printer.info = payloads.connection_info(model_id=20028)
    entry = await setup_entry(hass, lan_entry())
    camera = hass.data["camera"].get_entity(f"camera.{P}_camera")
    assert camera is not None
    assert camera._needs_relay
    assert entry.runtime_data.primary.printer.identity.model_id == 20028


# -- D8: a finished LAN job reads finished -------------------------------------------


@pytest.mark.parametrize(
    ("last", "expected"),
    [
        ({"state": "finished", "print_status": 2}, "finished"),
        ({"state": "stoped", "print_status": 3}, "cancelled"),
        ({"state": "stopped"}, "cancelled"),
        ({"state": None, "print_status": 3}, "cancelled"),
        ({"state": "failed"}, "failed"),
        ({"state": None, "print_status": 2}, "finished"),
        ({"state": "printing", "print_status": 1}, "idle"),
    ],
)
async def test_d8_lan_job_that_ended_reads_finished(
    hass: HomeAssistant,
    lan: MockConfigEntry,
    printer: MockPrinter,
    last: dict[str, Any],
    expected: str,
) -> None:
    job_state = f"sensor.{P}_job_state"
    # Since setup the printer has run no job.
    assert _state(hass, job_state) == "idle"
    printer.client.feed(payloads.info(project=payloads.job()))
    await _settle(hass)
    assert _state(hass, job_state) == "printing"
    ended = {"task_id": 614707220, "filename": "cube.gcode"} | last
    printer.client.feed(payloads.info(project=None, last_project=ended))
    await _settle(hass)
    assert _state(hass, job_state) == expected
    # The next job replaces it.
    printer.client.feed(payloads.info(project=payloads.job(task_id=7)))
    await _settle(hass)
    assert _state(hass, job_state) == "printing"


async def test_d8_cloud_keeps_its_own_last_job(
    hass: HomeAssistant, cloud: FakeCloud
) -> None:
    cloud.jobs = [cp.job(print_status=2, end_time=1790009999)]
    await _cloud(hass)
    assert _state(hass, f"sensor.{C}_job_state") == "finished"
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=61))
    await _settle(hass)
    assert _state(hass, f"sensor.{C}_job_state") == "finished"
