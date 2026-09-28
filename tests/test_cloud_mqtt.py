"""The cloud MQTT link: when it runs, and what its messages do.

BEHAVIOUR §5.2 (connect modes, actions, manual switch, idle release, wake,
refresh button, failures), §2.1 (``mqtt_connection_active``) and §1.4, §3.14
(faults, capability polling), PROTOCOL C §6.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from anycubic_cloud_client import MqttAuthError, MqttConnectionError
from homeassistant.const import (
    EVENT_HOMEASSISTANT_STOP,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
import homeassistant.util.dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from . import cloud_payloads as cp
from .cloud_fakes import FakeCloud
from .conftest import account_entry, setup_entry

ACTIVE = "binary_sensor.kobra_s1_cloud_mqtt_connection_active"
MANUAL = "switch.kobra_s1_cloud_manual_mqtt_connection_enabled"
REFRESH = "button.kobra_s1_cloud_refresh_mqtt_connection"


class Clock:
    def __init__(self) -> None:
        self.now = 5000.0

    def __call__(self) -> float:
        return self.now


async def _setup(hass: HomeAssistant, connect_mode: int, **kw: Any) -> MockConfigEntry:
    entry = account_entry(**kw)
    entry = account_entry(
        options={**entry.options, "mqtt_connect_mode": connect_mode}, **kw
    )
    return await setup_entry(hass, entry)


def _clock(entry: MockConfigEntry) -> Clock:
    clock = Clock()
    account = entry.runtime_data.cloud
    account._clock = clock
    account.mqtt._clock = clock
    return clock


async def _poll(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    account = entry.runtime_data.cloud
    account._next_due = None
    await entry.runtime_data.primary.async_refresh()
    await hass.async_block_till_done()


def _busy(cloud: FakeCloud, busy: bool = True) -> None:
    cloud.printers[cp.PRINTER_ID]["is_printing"] = 2 if busy else 1


def _idle(cloud: FakeCloud) -> None:
    _busy(cloud, False)
    cloud.jobs = [cp.job(print_status=2, end_time=1790009999)]


async def test_printing_only_mode(hass: HomeAssistant, cloud: FakeCloud) -> None:
    """Mode 1: held while any printer is busy; released after 15 min idle."""
    _idle(cloud)
    entry = await _setup(hass, 1)
    assert not cloud.links
    assert hass.states.get(ACTIVE).state == STATE_OFF
    clock = _clock(entry)
    _busy(cloud)
    await _poll(hass, entry)
    assert cloud.link.connects == 1
    assert cloud.link.subscribed == {cp.PRINTER_KEY: cp.MACHINE_TYPE}
    assert hass.states.get(ACTIVE).state == STATE_ON
    _idle(cloud)
    await _poll(hass, entry)  # the idle clock starts
    clock.now += 800
    await _poll(hass, entry)
    assert cloud.link.disconnects == 0
    clock.now += 200
    await _poll(hass, entry)
    assert cloud.link.disconnects == 1
    assert hass.states.get(ACTIVE).state == STATE_OFF


async def test_printing_and_drying_mode(hass: HomeAssistant, cloud: FakeCloud) -> None:
    _idle(cloud)
    cloud.printers[cp.PRINTER_ID]["multi_color_box"] = cp.ace_box(
        0, drying_status={"status": 1, "target_temp": 45, "duration": 60}
    )
    await _setup(hass, 2)
    assert cloud.link.connects == 1


async def test_device_online_mode(hass: HomeAssistant, cloud: FakeCloud) -> None:
    _idle(cloud)
    entry = await _setup(hass, 3)
    assert cloud.link.connects == 1
    clock = _clock(entry)
    cloud.printers[cp.PRINTER_ID]["device_status"] = 2
    await _poll(hass, entry)
    clock.now += 901
    await _poll(hass, entry)
    assert cloud.link.disconnects == 1


async def test_always_mode(hass: HomeAssistant, cloud: FakeCloud) -> None:
    _idle(cloud)
    entry = await _setup(hass, 4)
    clock = _clock(entry)
    await _poll(hass, entry)
    clock.now += 5000
    await _poll(hass, entry)
    assert cloud.link.connects == 1
    assert cloud.link.disconnects == 0


async def test_unknown_mode_starts_only_for_reasons(
    hass: HomeAssistant, cloud: FakeCloud
) -> None:
    entry = await _setup(hass, 9)
    assert not cloud.links
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": MANUAL}, blocking=True
    )
    assert cloud.link.connects == 1
    clock = _clock(entry)
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": MANUAL}, blocking=True
    )
    clock.now += 5000
    await _poll(hass, entry)
    await _poll(hass, entry)
    assert cloud.link.disconnects == 0  # never released for idling


async def test_never_mode(hass: HomeAssistant, cloud: FakeCloud) -> None:
    """Mode 5: never - not even for actions or the manual switch."""
    _busy(cloud)
    await _setup(hass, 5)
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": MANUAL}, blocking=True
    )
    # A control that wakes the link sends its order at once.
    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": "button.kobra_s1_cloud_pause_print"},
        blocking=True,
    )
    assert not cloud.links
    assert cloud.orders[-1][0] == "pause_print"
    assert hass.states.get(ACTIVE).attributes["supports_mqtt_login"] is True


async def test_web_token_never_connects(hass: HomeAssistant, cloud: FakeCloud) -> None:
    _busy(cloud)
    await _setup(hass, 4, mode=1)
    assert not cloud.links
    state = hass.states.get(ACTIVE)
    assert state.state == STATE_OFF
    assert state.attributes == state.attributes | {
        "supports_mqtt_login": False,
        "last_error": None,
    }


async def test_manual_switch(hass: HomeAssistant, cloud: FakeCloud) -> None:
    """Held open while on, whatever the mode; in memory only."""
    _idle(cloud)
    entry = await _setup(hass, 1)
    clock = _clock(entry)
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": MANUAL}, blocking=True
    )
    assert hass.states.get(MANUAL).state == STATE_ON
    assert cloud.link.connects == 1
    await _poll(hass, entry)
    clock.now += 2000
    await _poll(hass, entry)
    assert cloud.link.disconnects == 0
    # Off: released within 15 min, at the first idle check after them.
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": MANUAL}, blocking=True
    )
    await _poll(hass, entry)
    assert cloud.link.disconnects == 0
    clock.now += 901
    await _poll(hass, entry)
    assert cloud.link.disconnects == 1
    # Reload: back to off.
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(MANUAL).state == STATE_OFF


async def test_wake_for_an_action(hass: HomeAssistant, cloud: FakeCloud) -> None:
    """A waking control brings the link up first and holds it 5 minutes."""
    _idle(cloud)
    entry = await _setup(hass, 1)
    clock = _clock(entry)
    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": "button.kobra_s1_cloud_ace_pro_refresh_ace_spools"},
        blocking=True,
    )
    assert cloud.link.connects == 1
    assert ("ace_get_info", (cp.PRINTER_ID,), {}) in cloud.orders
    clock.now += 200
    await _poll(hass, entry)
    clock.now += 50
    await _poll(hass, entry)
    assert cloud.link.disconnects == 0  # the action holds it
    clock.now += 100  # past 5 minutes: the idle clock starts now
    await _poll(hass, entry)
    clock.now += 901
    await _poll(hass, entry)
    assert cloud.link.disconnects == 1


async def test_wake_times_out(hass: HomeAssistant, cloud: FakeCloud) -> None:
    """B12: a failed connect is reported with its reason, blocks nothing
    later, and the waking order is not sent."""
    _idle(cloud)
    entry = await _setup(hass, 1)
    cloud.mqtt_error = MqttConnectionError(
        "TimeoutError: timed out (host=mqtt-universe.anycubic.com:8883)"
    )
    orders = len(cloud.orders)
    with pytest.raises(HomeAssistantError) as err:
        await hass.services.async_call(
            "button",
            "press",
            {"entity_id": "button.kobra_s1_cloud_ace_pro_refresh_ace_spools"},
            blocking=True,
        )
    assert err.value.translation_key == "mqtt_connect_timeout"
    assert len(cloud.orders) == orders
    await hass.async_block_till_done()
    state = hass.states.get(ACTIVE)
    assert state.state == STATE_OFF  # B13: not on for a failed client
    assert state.attributes["last_error"] == (
        "MqttConnectionError: TimeoutError: timed out "
        "(host=mqtt-universe.anycubic.com:8883)"
    )
    # The next attempt is not blocked.
    cloud.mqtt_error = None
    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": "button.kobra_s1_cloud_ace_pro_refresh_ace_spools"},
        blocking=True,
    )
    assert cloud.link.connects == 2
    assert hass.states.get(ACTIVE).attributes["last_error"] is None
    assert entry.state.recoverable


async def test_refresh_button(hass: HomeAssistant, cloud: FakeCloud) -> None:
    """Restart the link at most once per 5 minutes; reconnect only when the
    mode, the manual switch or a recent action calls for it."""
    _busy(cloud)
    entry = await _setup(hass, 1)
    clock = _clock(entry)
    link = cloud.link
    await hass.services.async_call(
        "button", "press", {"entity_id": REFRESH}, blocking=True
    )
    assert link.disconnects == 1
    assert link.connects == 2
    await hass.services.async_call(
        "button", "press", {"entity_id": REFRESH}, blocking=True
    )
    assert link.disconnects == 1  # inside the 5 minutes: ignored
    # Idle printer, mode 1: disconnects and does not reconnect.
    _idle(cloud)
    await _poll(hass, entry)
    clock.now += 301
    await hass.services.async_call(
        "button", "press", {"entity_id": REFRESH}, blocking=True
    )
    assert link.disconnects == 2
    assert link.connects == 2
    # Not connected: a failed attempt is cleared and the check runs.
    entry.runtime_data.cloud.mqtt.last_error = "old"
    clock.now += 301
    await hass.services.async_call(
        "button", "press", {"entity_id": REFRESH}, blocking=True
    )
    assert entry.runtime_data.cloud.mqtt.last_error is None


async def test_link_gives_up(hass: HomeAssistant, cloud: FakeCloud) -> None:
    _busy(cloud)
    await _setup(hass, 1)
    cloud.link.drop()  # an unexpected drop: the library reconnects itself
    await hass.async_block_till_done()
    assert hass.states.get(ACTIVE).state == STATE_ON
    cloud.link.drop(MqttAuthError("The broker refused the login: Not authorized"))
    await hass.async_block_till_done()
    state = hass.states.get(ACTIVE)
    assert state.state == STATE_OFF
    assert state.attributes["last_error"].startswith("MqttAuthError: ")


async def test_stopped_on_unload_and_stop(
    hass: HomeAssistant, cloud: FakeCloud
) -> None:
    _busy(cloud)
    entry = await _setup(hass, 1)
    link = cloud.link
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert link.disconnects >= 1
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    link = cloud.link
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STOP)
    await hass.async_block_till_done()
    assert link.disconnects >= 1


async def test_capability_queries(hass: HomeAssistant, cloud: FakeCloud) -> None:
    """§3.14: 10 s after subscribing, and after polls while the link is up
    for online printers still missing an answer, at most 3 times."""
    _busy(cloud)
    entry = await _setup(hass, 1)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=11))
    await hass.async_block_till_done()
    names = cloud.order_names()
    assert names.count("query_peripherals") == 1 + 1  # after the first poll too
    assert names.count("query_light_status") == 2
    for _ in range(4):
        await _poll(hass, entry)
    assert cloud.order_names().count("query_peripherals") == 1 + 3
    # Offline, then back: the budget is restored.
    cloud.printers[cp.PRINTER_ID]["device_status"] = 2
    await _poll(hass, entry)
    cloud.printers[cp.PRINTER_ID]["device_status"] = 1
    await _poll(hass, entry)
    assert cloud.order_names().count("query_peripherals") == 1 + 4
    # Answered: no more questions.
    cloud.feed(
        cp.mqtt("peripherie", "query", "done", {"camera": 1, "multiColorBox": 1})
    )
    cloud.feed(
        cp.mqtt("light", "query", "done", {"lights": [{"type": 2, "status": 1}]})
    )
    await _poll(hass, entry)
    assert cloud.order_names().count("query_peripherals") == 1 + 4


async def test_messages_update_the_printer(
    hass: HomeAssistant, cloud: FakeCloud, hass_storage: dict[str, Any]
) -> None:
    _busy(cloud)
    entry = await _setup(hass, 1)
    # Temperatures and fans, parsed with anycubic-lan's LAN parser.
    cloud.feed(
        cp.mqtt(
            "tempature",
            "report",
            "done",
            {"curr_nozzle_temp": 215, "curr_hotbed_temp": 59},
        )
    )
    cloud.feed(cp.mqtt("fan", "report", "done", {"fan_speed_pct": 40}))
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get("sensor.kobra_s1_cloud_nozzle_temperature").state == "215.0"
    assert hass.states.get("sensor.kobra_s1_cloud_fan_speed").state == "40"
    # A fault code is recorded even when the message is not understood (B35),
    # and cleared by the next OK code of that kind (DECISIONS V10).
    cloud.feed(cp.mqtt("event", "fault", "report", {}, code=10101, msg="bad"))
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get("sensor.kobra_s1_cloud_last_error_code").state == "10101"
    cloud.feed(cp.mqtt("event", "fault", "report", {}, code=200))
    await hass.async_block_till_done(wait_background_tasks=True)
    assert (
        hass.states.get("sensor.kobra_s1_cloud_last_error_code").state
        == STATE_UNAVAILABLE
    )
    # Online, offline.
    cloud.feed(cp.mqtt("lastWill", "onlineReport", "offline"))
    await hass.async_block_till_done(wait_background_tasks=True)
    assert (
        hass.states.get("binary_sensor.kobra_s1_cloud_printer_online").state
        == STATE_OFF
    )
    # A light report makes the light available and is remembered (§3.13).
    cloud.feed(
        cp.mqtt("light", "query", "done", {"lights": [{"type": 2, "status": 1}]})
    )
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get("light.kobra_s1_cloud_printer_light").state == STATE_ON
    # Axis moves.
    cloud.feed(cp.mqtt("axis", "move", "doing"))
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get("binary_sensor.kobra_s1_cloud_axis_moving").state == STATE_ON
    # Messages for another printer key are dropped.
    cloud.feed(
        cp.mqtt("fan", "report", "done", {"fan_speed_pct": 99}), key="someone-else"
    )
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get("sensor.kobra_s1_cloud_fan_speed").state == "40"
    await hass.config_entries.async_unload(entry.entry_id)
    stored = hass_storage[f"anycubic_cloud.capabilities.{entry.entry_id}"]["data"]
    assert stored["printers"][str(cp.PRINTER_ID)]["light_types"] == [2]


async def test_print_reports(hass: HomeAssistant, cloud: FakeCloud) -> None:
    """PROTOCOL C §4.4: the known job updates live; another task waits (G9);
    free -> busy refreshes 5 s later."""
    entry = await _setup(hass, 4)
    state = "sensor.kobra_s1_cloud_job_progress"
    cloud.feed(
        cp.mqtt(
            "print",
            "start",
            "printing",
            {"taskid": cp.JOB_ID, "progress": 70, "curr_layer": 130},
        )
    )
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get(state).state == "70"
    assert hass.states.get("sensor.kobra_s1_cloud_job_current_layer").state == "130"
    cloud.feed(cp.mqtt("print", "start", "printing", {"taskid": 1, "progress": 5}))
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get(state).state == "70"
    cloud.feed(cp.mqtt("print", "pause", "paused", {"taskid": cp.JOB_ID}))
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get("sensor.kobra_s1_cloud_job_state").state == "paused"
    cloud.feed(
        cp.mqtt(
            "print",
            "update",
            "updated",
            {
                "taskid": cp.JOB_ID,
                "curr_nozzle_temp": 221,
                "curr_hotbed_temp": 61,
                "settings": {
                    "fan_speed_pct": 55,
                    "print_speed_pct": 110,
                    "print_speed_mode": 3,
                    "target_nozzle_temp": 225,
                    "target_hotbed_temp": 65,
                },
            },
        )
    )
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get("sensor.kobra_s1_cloud_print_speed").state == "110"
    assert hass.states.get("sensor.kobra_s1_cloud_job_speed_mode").state == "Sport"
    assert (
        hass.states.get("sensor.kobra_s1_cloud_target_nozzle_temperature").state
        == "225.0"
    )
    assert hass.states.get("sensor.kobra_s1_cloud_fan_speed").state == "55"
    cloud.feed(cp.mqtt("print", "start", "failed", {"taskid": cp.JOB_ID}, msg="jam"))
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get("sensor.kobra_s1_cloud_job_state").state == "failed"
    assert (
        hass.states.get("sensor.kobra_s1_cloud_job_name").attributes[
            "print_status_message"
        ]
        == "jam"
    )
    # Free -> busy: the job list is read again 5 s later.
    reads = cloud.printer_reads
    cloud.feed(cp.mqtt("status", "workReport", "free"))
    cloud.feed(cp.mqtt("status", "workReport", "busy"))
    await hass.async_block_till_done(wait_background_tasks=True)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=6))
    await hass.async_block_till_done(wait_background_tasks=True)
    assert cloud.printer_reads == reads + 1
    assert entry.runtime_data.primary.last_update_success


async def test_downloading_and_file_lists(
    hass: HomeAssistant, cloud: FakeCloud
) -> None:
    _busy(cloud)
    await _setup(hass, 1)
    cloud.feed(cp.mqtt("print", "start", "downloading", {"taskid": 1, "progress": 42}))
    await hass.async_block_till_done(wait_background_tasks=True)
    status = hass.states.get("sensor.kobra_s1_cloud_current_status")
    assert status.attributes["job_download_progress"] == 42
    local = "sensor.kobra_s1_cloud_file_list_local"
    assert hass.states.get(local).state == STATE_UNAVAILABLE
    records = [
        {"filename": "part.gcode", "timestamp": 1, "size": 2_000_000, "is_dir": False}
    ]
    cloud.feed(cp.mqtt("file", "listLocal", "done", {"records": records}))
    await hass.async_block_till_done(wait_background_tasks=True)
    state = hass.states.get(local)
    assert state.state == "1"
    assert state.attributes["file_info"] == [{"name": "part.gcode", "size_mb": 2.0}]
    assert state.attributes["unit_of_measurement"] == "files"
    # A reply without a list keeps the last one; an empty list reads 0 (G12).
    cloud.feed(cp.mqtt("file", "listLocal", "done", {}))
    cloud.feed(cp.mqtt("file", "listUdisk", "done", {"records": []}))
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get(local).state == "1"
    assert hass.states.get("sensor.kobra_s1_cloud_file_list_usb_disk").state == "0"
