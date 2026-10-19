"""Beta 3: field reports, 2026-10-15 to 2026-10-19 (ACCEPTANCE.md D9-D20).

Each test is named after the item it accepts. Printer messages run through
the libraries' own parsers: anycubic-lan for LAN (the fake LAN client) and
anycubic-cloud-client for the cloud MQTT (the fake link).
"""

from __future__ import annotations

import json
import logging
from typing import Any
from unittest.mock import PropertyMock, patch

from anycubic_cloud_client import AnycubicCloudError
from anycubic_lan import (
    AceBox,
    AceSlot,
    FeedSource,
    FilamentFeed,
    LanModeDisabledError,
    PrinterUnreachableError,
)
from freezegun.api import FrozenDateTimeFactory
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.anycubic_cloud.const import DOMAIN
from custom_components.anycubic_cloud.coordinator import AnycubicCoordinator
from custom_components.anycubic_cloud.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.anycubic_cloud.filament import grams_from_length
from custom_components.anycubic_cloud.lan import IntegrationLanClient
from custom_components.anycubic_cloud.ledger import FilamentLedger
from custom_components.anycubic_cloud.model import Printer, box_and_slot_for_feed
from custom_components.anycubic_cloud.redact import (
    REDACTED,
    is_sensitive_key,
    redact_data,
    redact_payload,
    redact_text,
)

from . import cloud_payloads as cp, payloads
from .cloud_fakes import FakeCloud
from .conftest import MockPrinter, account_entry, lan_entry, setup_entry
from .test_ledger import feed, make_printer

P = "anycubic_kobra_s1"
A = "anycubic_kobra_s1_ace_pro"
C = "kobra_s1_cloud"
JWT = cp.jwt(email="someone@example.com", phone="+391234", id=1, scope="all")


async def _settle(hass: HomeAssistant) -> None:
    await hass.async_block_till_done(wait_background_tasks=True)


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
    return await setup_entry(hass, lan_entry())


async def _cloud(hass: HomeAssistant, **options: Any) -> MockConfigEntry:
    entry = account_entry()
    return await setup_entry(
        hass,
        account_entry(options={**entry.options, "mqtt_connect_mode": 4, **options}),
    )


def _entity(hass: HomeAssistant, entry: MockConfigEntry, key: str) -> str | None:
    """The entity id of ``key`` on the entry's printer (by unique id)."""
    for item in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id):
        if item.unique_id.endswith(f"-{key}"):
            return item.entity_id
    return None


async def _poll(entry: MockConfigEntry) -> None:
    """A cloud refresh now: the printer record and the job list."""
    entry.runtime_data.cloud._next_due = None
    await entry.runtime_data.primary.async_refresh()


# -- D9: diagnostics carry no credential or personal data -------------------------

PROJECT_RECORD = {
    "name": "secret_part_name.gcode",
    "task_name": "secret_task_name",
    "filename": "secret_filename.gcode",
    "display_filename": "secret_display",
    "gcode_name": "secret_gcode_name.gcode",
    "temp_gcode": "/useremain/tmp/secret_temp.gcode",
    "img": "https://cdn.example.invalid/secret-image.png",
    "image_id": "secret/image/id.png",
}


async def test_d9_cloud_diagnostics_hide_tokens_and_personal_data(
    hass: HomeAssistant, cloud: FakeCloud
) -> None:
    cloud.user |= {
        "casdoor_user_token": JWT,
        "tourist_device_id": "TOURIST-DEVICE-SECRET",
        "user_activation_key": "ACTIVATION-SECRET",
        "user_url": "https://example.invalid/u/SECRET-URL",
        "some_new_token": "NEW-CREDENTIAL-SECRET",
        "api_secret": "API-SECRET-VALUE",
        "account_password": "PASSWORD-SECRET",
        "nested": {"anything": JWT, "empty_token": "", "null_token": None},
    }
    detail = cp.detail()
    detail["base"]["description"] = "53455249414c2d534543524554"  # hex serial
    cloud.printers[cp.PRINTER_ID] = detail
    cloud.jobs = [cp.job(**PROJECT_RECORD)]
    entry = await _cloud(hass)
    await entry.runtime_data.cloud.async_fetch_cloud_files()
    result = await async_get_config_entry_diagnostics(hass, entry)
    dump = json.dumps(result)
    for secret in (
        JWT,
        "eyJ",
        "TOURIST-DEVICE-SECRET",
        "ACTIVATION-SECRET",
        "SECRET-URL",
        "NEW-CREDENTIAL-SECRET",
        "API-SECRET-VALUE",
        "PASSWORD-SECRET",
        "53455249414c2d534543524554",
        cp.EMAIL,
        cp.PRINTER_KEY,
        str(cp.PRINTER_ID),
        "benchy",
        *PROJECT_RECORD.values(),
    ):
        assert secret not in dump, secret
    # A JSON document carried as text is redacted inside, and kept readable.
    assert "relative/image/path.png" not in dump
    slice_param = json.loads(result["printers"][0]["cloud"]["job"]["slice_param"])
    assert slice_param["image_id"] == REDACTED
    assert slice_param["layer_height"] == 0.2
    account = result["cloud"]["account"]
    assert account["casdoor_user_token"] == REDACTED
    assert account["tourist_device_id"] == REDACTED
    # Empty or null values may stay visible.
    assert account["nested"]["empty_token"] == ""
    assert account["nested"]["null_token"] is None
    assert account["mobile"] == ""
    # Print history stays, without names or images: status is what is debugged.
    job = result["printers"][0]["cloud"]["job"]
    assert job["print_status"] == 1
    assert job["progress"] == 69
    assert job["name"] == REDACTED
    # A printer id reads as the same placeholder in every block.
    assert result["entry"]["data"]["printer_ids"] == ["printer_1"]
    assert result["printers"][0]["printer"]["identity"]["printer_id"] == "printer_1"
    assert job["printer_id"] == "printer_1"
    assert result["printers"][0]["cloud"]["detail"]["id"] == "printer_1"


async def test_d9_lan_diagnostics_and_ledger(
    hass: HomeAssistant, lan: MockConfigEntry, printer: MockPrinter
) -> None:
    pid = lan.runtime_data.primary.printer_id
    printer.client.feed(payloads.info(project=payloads.job(supplies_usage=300)))
    printer.client.feed(payloads.ace(payloads.box(0, loaded_slot=0)))
    await _settle(hass)
    printer.client.feed(payloads.info(project=None))
    await _settle(hass)
    result = await async_get_config_entry_diagnostics(hass, lan)
    dump = json.dumps(result)
    for secret in (str(pid), "Wolf_plate", payloads.HOST, payloads.MAC):
        assert secret not in dump, secret
    ledger = result["ledger"]
    assert list(ledger["printers"]) == ["printer_1"]
    # The job history keeps its figures, not the file names.
    assert list(ledger["jobs"]) == ["job_1"]
    assert result["capabilities"]["printers"] == {"printer_1": {"light_types": [2]}}
    state = result["printers"][0]["printer"]["state"]
    assert state["camera_url"] == REDACTED
    assert state["ip"] == REDACTED
    assert state["firmware_version"] == "2.7.2.7"  # not mistaken for an address


def test_d9_rules() -> None:
    assert is_sensitive_key("casdoor_user_token")
    assert is_sensitive_key("anyNewSecret")
    assert is_sensitive_key("PASSWORD")
    assert not is_sensitive_key("print_status")
    assert not is_sensitive_key(3)
    document = {
        "a": [{"b": f"Bearer {JWT}"}, JWT, ("x", 1)],
        "sn": "SERIAL",
        "token": "",
        "42424": {"id": 42424, "text": "printer 42424 and 424240"},
    }
    assert redact_data(document, [42424]) == {
        "a": [{"b": f"Bearer {REDACTED}"}, REDACTED, ["x", 1]],
        "sn": REDACTED,
        "token": "",
        "printer_1": {"id": "printer_1", "text": "printer printer_1 and 424240"},
    }
    # A short id names its key, never an ordinary figure.
    assert redact_data({"7": {"n": 7, "s": "SKU7"}, "flag": True}, [7]) == {
        "printer_1": {"n": 7, "s": "SKU7"},
        "flag": True,
    }


# -- D10: filament-change steps, counted per box -----------------------------------


def _boxes(count: int) -> tuple[AceBox, ...]:
    return tuple(
        AceBox(id=i, slots=tuple(AceSlot(index=s) for s in range(4)))
        for i in range(count)
    )


def _feed(source: FeedSource, channel: int, **fields: Any) -> FilamentFeed:
    return FilamentFeed(source, channel - 1, **fields)


@pytest.mark.parametrize(
    ("feed", "boxes", "model_id", "ace_fitted", "expected"),
    [
        # One box: that box, whatever the report.
        (_feed(FeedSource.PRINTER_FEEDER, 2), 1, 20030, False, (0, 1)),
        (_feed(FeedSource.CHANNEL, 4), 1, 20030, False, (0, 3)),
        (_feed(FeedSource.ACE, 3, unit_no=1), 1, 20025, True, (0, 2)),
        (_feed(FeedSource.CURRENT_FILAMENT, 4, box=0), 1, 20028, False, (0, 3)),
        # A Kobra X with an ACE: unchanged until the mapping is confirmed.
        (_feed(FeedSource.ACE, 1, unit_no=1), 1, 20030, True, None),
        (_feed(FeedSource.PRINTER_FEEDER, 1), 1, 20030, True, None),
        (_feed(FeedSource.PRINTER_FEEDER, 1), 2, 20030, False, None),
        (_feed(FeedSource.ACE, 2, unit_no=1), 2, 20030, True, None),
        (_feed(FeedSource.CURRENT_FILAMENT, 1, box=0), 2, 20030, False, None),
        # Every box an ACE (an S1 with two): unit U is ACE U.
        (_feed(FeedSource.ACE, 3, unit_no=2), 2, 20025, True, (1, 2)),
        (_feed(FeedSource.ACE, 1, unit_no=1), 2, 20025, True, (0, 0)),
        (_feed(FeedSource.ACE, 1, unit_no=3), 2, 20025, True, None),
        (_feed(FeedSource.ACE, 1), 2, 20025, True, None),
        (_feed(FeedSource.CURRENT_FILAMENT, 2, box=1), 2, 20025, False, (1, 1)),
        (_feed(FeedSource.CHANNEL, 2), 2, 20025, False, None),
        # Nothing to name, or past the box's slots.
        (_feed(FeedSource.CHANNEL, 1), 0, 20025, False, None),
        (_feed(FeedSource.CHANNEL, 5), 1, 20025, False, None),
    ],
)
def test_d10_box_mapping(
    feed: FilamentFeed,
    boxes: int,
    model_id: int,
    ace_fitted: bool,
    expected: tuple[int, int] | None,
) -> None:
    assert (
        box_and_slot_for_feed(
            feed, _boxes(boxes), model_id=model_id, ace_fitted=ace_fitted
        )
        == expected
    )


def _step(state: str, **data: Any) -> dict[str, Any]:
    return cp.mqtt("print", "start", state, data)


async def test_d10_kobra_x_without_ace_follows_its_own_feeder(
    hass: HomeAssistant, cloud: FakeCloud, caplog: pytest.LogCaptureFixture
) -> None:
    cloud.printers[cp.PRINTER_ID]["machine_type"] = 20030
    cloud.printers[cp.PRINTER_ID]["is_printing"] = 2
    await _cloud(hass)
    sensor = f"sensor.{C}_ace_pro_ace_loaded_slot"
    assert _state(hass, sensor) == "2"
    caplog.clear()
    with caplog.at_level(logging.DEBUG):
        for state, data, shown in (
            ("extfilbox_filament_feeding", {"channel_no": 1, "taskid": "-1"}, "1"),
            ("nozzle_purging", {"channel_no": 3, "taskid": "-1"}, "1"),
            ("extfilbox_filament_unfeeding", {"channel_no": 3, "taskid": "-1"}, "1"),
            ("extfilbox_filament_feeding", {"channel_no": 3, "taskid": "-1"}, "3"),
        ):
            cloud.feed(_step(state, **data))
            await _settle(hass)
            assert _state(hass, sensor) == shown, state
    # Steps are not job states, and nothing is logged above debug.
    assert _state(hass, f"sensor.{C}_job_state") == "printing"
    _no_warnings(caplog)


async def test_d10_kobra_x_with_an_ace_leaves_the_loaded_slot(
    hass: HomeAssistant, cloud: FakeCloud
) -> None:
    cloud.printers[cp.PRINTER_ID]["machine_type"] = 20030
    await _cloud(hass)
    sensor = f"sensor.{C}_ace_pro_ace_loaded_slot"
    assert _state(hass, sensor) == "2"
    # The observed sequence: own feeder 1 → 1 → 2, then ACE unit 1 ch 1, ch 2.
    for state, data in (
        ("ace_filament_feeding", {"channel_no": 1, "taskid": 9, "unit_no": 1}),
        ("extfilbox_filament_feeding", {"channel_no": 1, "taskid": 9}),
        ("extfilbox_filament_feeding", {"channel_no": 2, "taskid": 9}),
        ("ace_filament_feeding", {"channel_no": 2, "taskid": 9, "unit_no": 1}),
    ):
        cloud.feed(_step(state, **data))
        await _settle(hass)
        assert _state(hass, sensor) == "2", state


async def test_d10_kobra_x_with_two_boxes_ignores_the_bare_channel(
    hass: HomeAssistant, cloud: FakeCloud
) -> None:
    """Corrects Beta 2's D4 test: channel 6 no longer names box 2."""
    cloud.printers[cp.PRINTER_ID]["machine_type"] = 20030
    cloud.printers[cp.PRINTER_ID]["multi_color_box"] = [cp.ace_box(0), cp.ace_box(1)]
    await _cloud(hass)
    first = f"sensor.{C}_ace_pro_ace_loaded_slot"
    second = f"sensor.{C}_ace_pro_2_secondary_ace_loaded_slot"
    for channel in (6, 3):
        cloud.feed(cp.mqtt("print", "update", "updated", {"channel_no": channel}))
        await _settle(hass)
        assert (_state(hass, first), _state(hass, second)) == ("2", "2")


async def test_d10_s1_with_two_aces_unit_selects_the_ace(
    hass: HomeAssistant, cloud: FakeCloud
) -> None:
    cloud.printers[cp.PRINTER_ID]["multi_color_box"] = [cp.ace_box(0), cp.ace_box(1)]
    await _cloud(hass)
    first = f"sensor.{C}_ace_pro_ace_loaded_slot"
    second = f"sensor.{C}_ace_pro_2_secondary_ace_loaded_slot"
    cloud.feed(_step("ace_filament_feeding", channel_no=3, taskid=9, unit_no=2))
    await _settle(hass)
    # ACE 2 feeds its slot 3; ACE 1 feeds nothing now.
    assert (_state(hass, first), _state(hass, second)) == (STATE_UNAVAILABLE, "3")
    cloud.feed(_step("ace_filament_feeding", channel_no=4, taskid=9, unit_no=1))
    await _settle(hass)
    assert (_state(hass, first), _state(hass, second)) == ("4", STATE_UNAVAILABLE)
    # An unknown unit changes nothing.
    cloud.feed(_step("ace_filament_feeding", channel_no=1, taskid=9, unit_no=5))
    await _settle(hass)
    assert (_state(hass, first), _state(hass, second)) == ("4", STATE_UNAVAILABLE)


async def test_d10_lan_steps(
    hass: HomeAssistant,
    lan: MockConfigEntry,
    printer: MockPrinter,
    caplog: pytest.LogCaptureFixture,
) -> None:
    printer.client.feed(payloads.info(project=payloads.job(task_id="-1")))
    await _settle(hass)
    sensor = f"sensor.{A}_ace_loaded_slot"
    caplog.clear()
    with caplog.at_level(logging.DEBUG):
        for state, data, shown in (
            ("ace_filament_feeding", {"channel_no": 2, "unit_no": 1}, "2"),
            ("nozzle_purging", {"channel_no": 4}, "2"),
            ("ace_filament_feeding", {"channel_no": 4, "unit_no": 1}, "4"),
        ):
            printer.client.feed(
                payloads.envelope(
                    "print", data | {"taskid": "-1"}, action="start", state=state
                )
            )
            await _settle(hass)
            assert _state(hass, sensor) == shown, state
    assert _state(hass, f"sensor.{P}_job_state") == "printing"
    _no_warnings(caplog)


# -- D11: ACE 2 Pro drying report without a temperature -----------------------------

DRYING = {
    "duration": 14400,
    "humidity": 28,
    "remain_time": 162,
    "status": 1,
    "target_temp": 50,
}


@pytest.mark.parametrize(
    "data",
    [
        {"multi_color_box": [{"id": 0, "drying_status": DRYING}]},
        {"id": 0, "drying_status": DRYING},
    ],
)
async def test_d11_lan_drying_report_keeps_the_temperature(
    hass: HomeAssistant,
    lan: MockConfigEntry,
    printer: MockPrinter,
    caplog: pytest.LogCaptureFixture,
    data: dict[str, Any],
) -> None:
    printer.client.feed(payloads.ace(payloads.box(0, temp=31)))
    await _settle(hass)
    temperature = f"sensor.{A}_ace_current_temperature"
    assert _state(hass, temperature) == "31.0"
    caplog.clear()
    with caplog.at_level(logging.DEBUG):
        printer.client.feed(
            payloads.envelope(
                "multiColorBox", data, action="autoUpdateDryStatus", state="success"
            )
        )
        await _settle(hass)
    assert _state(hass, temperature) == "31.0"
    assert _state(hass, f"binary_sensor.{A}_drying_active") == "on"
    assert _state(hass, f"sensor.{A}_drying_target_temperature") == "50.0"
    assert _state(hass, f"sensor.{A}_drying_total_duration") == "14400"
    assert _state(hass, f"sensor.{A}_drying_remaining_time") == "162"
    spools = hass.states.get(f"sensor.{A}_ace_spools")
    assert spools is not None
    assert spools.attributes["box_info"]["humidity"] == 28
    _no_warnings(caplog)


async def test_d11_cloud_drying_report_keeps_the_temperature(
    hass: HomeAssistant, cloud: FakeCloud, caplog: pytest.LogCaptureFixture
) -> None:
    await _cloud(hass)
    temperature = f"sensor.{C}_ace_pro_ace_current_temperature"
    assert _state(hass, temperature) == "33.0"
    spools = f"sensor.{C}_ace_pro_ace_spools"
    assert hass.states.get(spools).attributes["box_info"]["humidity"] == 12
    caplog.clear()
    with caplog.at_level(logging.DEBUG):
        cloud.feed(
            cp.mqtt(
                "multiColorBox",
                "autoUpdateDryStatus",
                "success",
                {"multi_color_box": [{"id": 0, "drying_status": DRYING}]},
            )
        )
        await _settle(hass)
    assert _state(hass, temperature) == "33.0"
    assert _state(hass, f"binary_sensor.{C}_ace_pro_drying_active") == "on"
    assert _state(hass, f"sensor.{C}_ace_pro_drying_remaining_time") == "162"
    assert hass.states.get(spools).attributes["box_info"]["humidity"] == 28
    _no_warnings(caplog)


# -- D12: a cloud refresh must not overwrite the slot the printer reported ---------


async def test_d12_cloud_refresh_keeps_the_reported_slot(
    hass: HomeAssistant, cloud: FakeCloud
) -> None:
    cloud.printers[cp.PRINTER_ID]["machine_type"] = 20030
    cloud.printers[cp.PRINTER_ID]["is_printing"] = 2
    entry = await _cloud(hass)
    sensor = f"sensor.{C}_ace_pro_ace_loaded_slot"
    temperature = f"sensor.{C}_ace_pro_ace_current_temperature"
    # No printer report yet: the cloud's value.
    assert _state(hass, sensor) == "2"
    cloud.feed(cp.mqtt("print", "update", "updated", {"channel_no": 4}))
    await _settle(hass)
    assert _state(hass, sensor) == "4"
    # The periodic refresh: the record still says slot 2, but is warmer.
    cloud.printers[cp.PRINTER_ID]["multi_color_box"] = cp.ace_box(0, temp=40)
    await _poll(entry)
    await _settle(hass)
    assert _state(hass, sensor) == "4"
    assert _state(hass, temperature) == "40.0"
    # The printer's next report does change it.
    cloud.feed(cp.mqtt("print", "update", "updated", {"channel_no": 3}))
    await _settle(hass)
    assert _state(hass, sensor) == "3"


async def test_d12_box_report_survives_the_refresh(
    hass: HomeAssistant, cloud: FakeCloud
) -> None:
    entry = await _cloud(hass)
    sensor = f"sensor.{C}_ace_pro_ace_loaded_slot"
    cloud.feed(
        cp.mqtt("multiColorBox", "autoUpdateInfo", "done", {"id": 0, "loaded_slot": 3})
    )
    await _settle(hass)
    assert _state(hass, sensor) == "4"
    await _poll(entry)
    await _settle(hass)
    assert _state(hass, sensor) == "4"
    # A refused box reply is not a report of the slot.
    cloud.feed(
        cp.mqtt(
            "multiColorBox",
            "setInfo",
            "failed",
            {"multi_color_box": [{"id": 0, "loaded_slot": 0}]},
            code=10500,
        )
    )
    await _settle(hass)
    assert entry.runtime_data.primary.printer.reported_loaded_slots == {0: 3}
    # A newer report of the box's own does change it.
    cloud.feed(
        cp.mqtt("multiColorBox", "autoUpdateInfo", "done", {"id": 0, "loaded_slot": 0})
    )
    await _settle(hass)
    assert _state(hass, sensor) == "1"


async def test_d12_box_report_retires_a_feed_only_when_it_changes(
    hass: HomeAssistant, lan: MockConfigEntry, printer: MockPrinter
) -> None:
    sensor = f"sensor.{A}_ace_loaded_slot"
    printer.client.feed(payloads.ace(payloads.box(0, loaded_slot=0)))
    printer.client.feed(
        payloads.envelope("print", {"channel_no": 3}, action="update", state="updated")
    )
    await _settle(hass)
    assert _state(hass, sensor) == "3"
    # A Kobra X repeats its stale slot: the feed stands.
    printer.client.feed(payloads.ace(payloads.box(0, loaded_slot=0)))
    await _settle(hass)
    assert _state(hass, sensor) == "3"
    printer.client.feed(
        payloads.ace(payloads.box(0, loaded_slot=1), action="autoUpdateInfo")
    )
    await _settle(hass)
    assert _state(hass, sensor) == "2"


# -- D13: the printer's own current_filament report ---------------------------------


def _current(value: object) -> dict[str, Any]:
    return cp.mqtt("extfilbox", "auto", "done", {"current_filament": value})


async def test_d13_cloud_current_filament(
    hass: HomeAssistant, cloud: FakeCloud
) -> None:
    await _cloud(hass)
    sensor = f"sensor.{C}_ace_pro_ace_loaded_slot"
    for value, shown in (("0-3", "4"), ("", "4"), ("x-y", "4"), ("0-0", "1")):
        cloud.feed(_current(value))
        await _settle(hass)
        assert _state(hass, sensor) == shown, value


async def test_d13_several_boxes(hass: HomeAssistant, cloud: FakeCloud) -> None:
    cloud.printers[cp.PRINTER_ID]["multi_color_box"] = [cp.ace_box(0), cp.ace_box(1)]
    await _cloud(hass)
    first = f"sensor.{C}_ace_pro_ace_loaded_slot"
    second = f"sensor.{C}_ace_pro_2_secondary_ace_loaded_slot"
    cloud.feed(_current("1-2"))
    await _settle(hass)
    assert (_state(hass, first), _state(hass, second)) == (STATE_UNAVAILABLE, "3")


async def test_d13_kobra_x_with_an_ace(hass: HomeAssistant, cloud: FakeCloud) -> None:
    cloud.printers[cp.PRINTER_ID]["machine_type"] = 20030
    cloud.printers[cp.PRINTER_ID]["multi_color_box"] = [cp.ace_box(0), cp.ace_box(1)]
    await _cloud(hass)
    cloud.feed(_current("0-3"))
    await _settle(hass)
    assert _state(hass, f"sensor.{C}_ace_pro_ace_loaded_slot") == "2"


async def test_d13_lan_current_filament_keeps_the_holder(
    hass: HomeAssistant, printer: MockPrinter
) -> None:
    printer.connect_payloads.append(
        payloads.extfilbox(id=1, type="PETG", color=[1, 2, 3], loaded=1)
    )
    await setup_entry(hass, lan_entry())
    holder = f"binary_sensor.{P}_external_spool_loaded"
    er.async_get(hass).async_update_entity(holder, disabled_by=None)
    sensor = f"sensor.{A}_ace_loaded_slot"
    printer.client.feed(
        payloads.envelope(
            "extfilbox", {"current_filament": "0-2"}, action="auto", state="done"
        )
    )
    await _settle(hass)
    assert _state(hass, sensor) == "3"
    coordinator = hass.config_entries.async_entries(DOMAIN)[0].runtime_data.primary
    spool = coordinator.printer.external_spool
    assert spool is not None
    assert spool.material == "PETG"


# -- D14: logs carry no printer identifiers ---------------------------------------


def test_d14_lan_message_log(caplog: pytest.LogCaptureFixture) -> None:
    client = IntegrationLanClient(
        payloads.connection_info(),
        report_callback=lambda report: None,
        debug_messages=True,
    )
    topic = (
        f"anycubic/anycubicCloud/v1/printer/public/20025/{payloads.DEVICE_ID}"
        "/buried/report"
    )
    buried = {
        "type": "buried",
        "action": "PrintStart",
        "state": "done",
        "data": {
            "cn_code": "CN-CODE-SECRET",
            "sn": "SERIAL-SECRET",
            "mac": payloads.MAC,
            "ip": payloads.HOST,
            "printer_key": "PRINTER-KEY-SECRET",
            "session_token": "TOKEN-SECRET",
            "client_secret": "CLIENT-SECRET",
            "password": "PASSWORD-SECRET",
            "note": f"see {JWT} at mqtts://{payloads.HOST}:9883 from {payloads.MAC}",
            "progress": 42,
        },
    }
    caplog.set_level(logging.DEBUG, logger="custom_components.anycubic_cloud.lan")
    client._handle_message(topic, json.dumps(buried).encode())
    client._handle_message(topic, b"not json from 10.1.2.3:18910 a4:e8:8d:00:00:01")
    text = caplog.text
    for secret in (
        "CN-CODE-SECRET",
        "SERIAL-SECRET",
        payloads.MAC,
        payloads.HOST,
        "PRINTER-KEY-SECRET",
        "TOKEN-SECRET",
        "CLIENT-SECRET",
        "PASSWORD-SECRET",
        "eyJ",
        payloads.DEVICE_ID,
        "10.1.2.3",
        "a4:e8:8d:00:00:01",
    ):
        assert secret not in text, secret
    assert '"progress":42' in text


async def test_d14_no_address_or_identifier_in_any_log_line(
    hass: HomeAssistant,
    printer: MockPrinter,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    entry = await setup_entry(hass, lan_entry())
    printer.handshake_error = PrinterUnreachableError(
        f"Printer did not answer at {payloads.HOST}"
    )
    printer.client.lose()
    for _ in range(2):
        freezer.tick(16)
        async_fire_time_changed(hass)
        await _settle(hass)
    printer.handshake_error = None
    freezer.tick(16)
    async_fire_time_changed(hass)
    await _settle(hass)
    assert entry.runtime_data.primary.lan_connected
    for secret in (payloads.HOST, payloads.MAC, payloads.MAC_UID, payloads.DEVICE_ID):
        assert secret not in caplog.text, secret


def test_d14_shared_rules() -> None:
    assert redact_text("http://10.0.0.5:18088/flv") == f"http://{REDACTED}:18088/flv"
    assert redact_text("version 2.7.2.7") == "version 2.7.2.7"
    assert redact_text("at 10.0.0.5:18910") == f"at {REDACTED}:18910"
    assert redact_text("at 10.0.0.5", "10.0.0.5") == f"at {REDACTED}"
    assert redact_text("x?X-Amz-Signature=1") == REDACTED
    assert redact_payload('{"cn_code": "C"}') == f'{{"cn_code":"{REDACTED}"}}'


# -- D15: job numbers that arrive as text, and job -1 --------------------------------


async def test_d15_lan_job_numbered_minus_one(
    hass: HomeAssistant, lan: MockConfigEntry, printer: MockPrinter
) -> None:
    printer.client.feed(
        payloads.info(
            project=payloads.job(task_id="-1"),
            last_project={
                "task_id": "131189709",
                "localtask": "x",
                "state": "finished",
            },
        )
    )
    await _settle(hass)
    coordinator = lan.runtime_data.primary
    job = coordinator.printer.job
    assert job is not None
    assert job.task_id == -1
    assert job.job_id is None
    assert coordinator.printer.state.last_job is not None
    assert coordinator.printer.state.last_job.job_id == 131189709
    assert _state(hass, f"sensor.{P}_job_state") == "printing"
    # Pause sends the number the printer gave the job.
    await hass.services.async_call(
        "button", "press", {"entity_id": f"button.{P}_pause_print"}, blocking=True
    )
    assert printer.client.commands[-1] == ("print", "pause", {"taskid": "-1"})


# -- D16: LAN prints are charged without relying on a job number --------------------

LENGTH = 309  # mm; about 0.9 g of PLA


def _slot4_used(entry: MockConfigEntry) -> float:
    pid = entry.runtime_data.primary.printer_id
    slots = entry.runtime_data.ledger.data["printers"][str(pid)]["slots"]
    return float(slots["3"]["filament_used_g"])


def _lan_print(
    printer: MockPrinter, *, task_id: Any = "-1", name: str = "cube"
) -> None:
    project = payloads.job(
        task_id=task_id, filename=f"{name}.gcode", supplies_usage=0, progress=1
    )
    printer.client.feed(payloads.info(project=project))
    printer.client.feed(payloads.info(project=project | {"supplies_usage": LENGTH}))
    ended = {
        "task_id": task_id,
        "filename": f"{name}.gcode",
        "state": "finished",
        "print_status": 2,
        "supplies_usage": LENGTH,
    }
    printer.client.feed(payloads.info(project=None, last_project=ended))


async def _lan_slot4(hass: HomeAssistant, printer: MockPrinter) -> MockConfigEntry:
    printer.connect_payloads[1] = payloads.ace(payloads.box(0, loaded_slot=3))
    return await setup_entry(hass, lan_entry())


async def test_d16_two_lan_prints_numbered_minus_one(
    hass: HomeAssistant, printer: MockPrinter
) -> None:
    entry = await _lan_slot4(hass, printer)
    one = grams_from_length(LENGTH, "PLA")
    assert round(one, 1) == 0.9
    _lan_print(printer, name="first")
    await _settle(hass)
    assert _slot4_used(entry) == pytest.approx(one, abs=0.01)
    _lan_print(printer, name="second")
    await _settle(hass)
    assert _slot4_used(entry) == pytest.approx(2 * one, abs=0.02)
    # A number never charged is not stored as the last charged job.
    pid = entry.runtime_data.primary.printer_id
    assert "last_job_id" not in entry.runtime_data.ledger.data["printers"][str(pid)]
    assert entry.runtime_data.ledger.last_job_filament(pid) == 0.9


async def test_d16_the_same_file_twice(
    hass: HomeAssistant, printer: MockPrinter
) -> None:
    entry = await _lan_slot4(hass, printer)
    one = grams_from_length(LENGTH, "PLA")
    _lan_print(printer)
    _lan_print(printer)
    await _settle(hass)
    assert _slot4_used(entry) == pytest.approx(2 * one, abs=0.02)
    # Reports of the finished record do not charge it again.
    for _ in range(3):
        printer.client.feed(
            payloads.info(
                project=None,
                last_project={"task_id": "-1", "state": "finished", "print_status": 2},
            )
        )
    await _settle(hass)
    assert _slot4_used(entry) == pytest.approx(2 * one, abs=0.02)


async def test_d16_a_print_never_watched_running(
    hass: HomeAssistant, printer: MockPrinter
) -> None:
    ended = {
        "task_id": "-1",
        "filename": "a.gcode",
        "state": "finished",
        "print_status": 2,
    }
    printer.connect_payloads[0] = payloads.info(last_project=ended)
    finished = payloads.job(
        task_id="-1", print_status=2, state="finished", supplies_usage=LENGTH
    )
    printer.poll_payloads = [payloads.info(project=finished)]
    entry = await _lan_slot4(hass, printer)
    await entry.runtime_data.primary.async_refresh()
    printer.client.feed(payloads.info(project=None, last_project=ended))
    await _settle(hass)
    assert _slot4_used(entry) == 0


async def test_d16_a_restart_mid_print_charges_the_watched_part_once(
    hass: HomeAssistant, printer: MockPrinter
) -> None:
    """What a restart leaves: the print is seen running, then ending, once."""
    running = payloads.job(task_id="-1", supplies_usage=200)
    printer.connect_payloads[0] = payloads.info(project=running)
    entry = await _lan_slot4(hass, printer)
    printer.client.feed(payloads.info(project=running | {"supplies_usage": LENGTH}))
    printer.client.feed(payloads.info(project=None))
    await _settle(hass)
    assert _slot4_used(entry) == pytest.approx(
        grams_from_length(LENGTH, "PLA"), abs=0.01
    )


async def test_d16_beta2_store_loads_unchanged(
    hass: HomeAssistant, printer: MockPrinter, hass_storage: dict[str, Any]
) -> None:
    entry = lan_entry()
    stored = {
        "printers": {
            str(payloads.PRINTER_ID): {
                "slots": {
                    "3": {
                        "spool_weight_g": 1000.0,
                        "filament_used_g": 12.5,
                        "spool_signature": "PLA|#0080FF|SKU3",
                    }
                },
                "last_job_id": 614707220,
                "totals": {
                    "material_totals": {"PLA": 12.5},
                    "last_job_grams": 12.5,
                    "last_job_cost": None,
                    "cost_total": 0.0,
                },
                "nozzle": {"nozzle_total_g": 12.5, "nozzle_abrasive_g": 0.0},
                "axis_step": 10,
            }
        },
        "spools": {
            "PLA|#0080FF|SKU3": {"filament_used_g": 12.5, "spool_weight_g": 1000.0}
        },
        "jobs": {"cube": [12.5]},
    }
    hass_storage[f"anycubic_cloud.filament.{entry.entry_id}"] = {
        "version": 1,
        "minor_version": 1,
        "key": f"anycubic_cloud.filament.{entry.entry_id}",
        "data": json.loads(json.dumps(stored)),
    }
    # Loaded as stored: the ledger is read, not rewritten.
    ledger = FilamentLedger(hass, entry.entry_id)
    await ledger.async_load()
    assert ledger.data == stored
    printer.connect_payloads[1] = payloads.ace(payloads.box(0, loaded_slot=3))
    await setup_entry(hass, entry)
    data = entry.runtime_data.ledger.data
    kept = data["printers"][str(payloads.PRINTER_ID)]
    for key, value in stored["printers"][str(payloads.PRINTER_ID)].items():
        if key != "slots":
            assert kept[key] == value, key
    assert (
        kept["slots"]["3"] == stored["printers"][str(payloads.PRINTER_ID)]["slots"]["3"]
    )
    assert data["jobs"] == stored["jobs"]
    # The job numbered 614707220 was charged by beta.2: not again.
    printer.client.feed(payloads.info(project=payloads.job(supplies_usage=LENGTH)))
    printer.client.feed(payloads.info(project=None))
    await _settle(hass)
    assert _slot4_used(entry) == 12.5
    # A -1 print is.
    _lan_print(printer)
    await _settle(hass)
    assert _slot4_used(entry) == pytest.approx(
        12.5 + grams_from_length(LENGTH, "PLA"), abs=0.01
    )


async def test_d16_lan_to_cloud_and_back(
    hass: HomeAssistant, cloud: FakeCloud, printer: MockPrinter
) -> None:
    # The cloud's newest job: a September print, finished and charged then.
    september = cp.job(print_status=2, end_time=1790009999)
    september["settings"] = json.dumps({"supplies_usage": 5000, "state": "finished"})
    cloud.jobs = [september]
    printer.connect_payloads[1] = payloads.ace(payloads.box(0, loaded_slot=3))
    entry = await setup_entry(hass, account_entry(lan=True))
    coordinator = entry.runtime_data.primary
    assert coordinator.lan_connected
    pid = coordinator.printer_id
    ledger = entry.runtime_data.ledger
    ledger.data["printers"].setdefault(str(pid), {})["last_job_id"] = cp.JOB_ID
    one = grams_from_length(LENGTH, "PLA")

    def nozzle() -> float:
        return float(ledger.data["printers"][str(pid)]["nozzle"]["nozzle_total_g"])

    _lan_print(printer)
    await _settle(hass)
    assert nozzle() == pytest.approx(one, abs=0.01)

    # LAN Mode off: the printer is read from the cloud, which re-reports its
    # newest job, finished and then (a stale record) running and finished.
    printer.handshake_error = LanModeDisabledError("cloud mode")
    printer.client.lose()
    await coordinator.async_refresh()
    await _settle(hass)
    assert coordinator.uses_cloud
    for status in (1, 2, 1, 2):
        cloud.jobs = [september | {"print_status": status}]
        await _poll(entry)
        await _settle(hass)
    assert nozzle() == pytest.approx(one, abs=0.01)

    # Back to LAN: the finished -1 job is still in last_project.
    printer.handshake_error = None
    printer.connect_payloads[0] = payloads.info(
        last_project={"task_id": "-1", "state": "finished", "print_status": 2}
    )
    await coordinator.async_refresh()
    await _settle(hass)
    assert coordinator.lan_connected
    assert nozzle() == pytest.approx(one, abs=0.01)


async def test_d16_numbered_job_seen_on_both_sources_is_charged_once(
    hass: HomeAssistant, cloud: FakeCloud, printer: MockPrinter
) -> None:
    """A Kobra S1 numbers LAN prints; the cloud may report the same job."""
    cloud.jobs = [cp.job(print_status=2, end_time=1790009999)]
    printer.connect_payloads[1] = payloads.ace(payloads.box(0, loaded_slot=3))
    entry = await setup_entry(hass, account_entry(lan=True))
    coordinator = entry.runtime_data.primary
    pid = coordinator.printer_id
    ledger = entry.runtime_data.ledger
    job = payloads.job(task_id=cp.JOB_ID, supplies_usage=LENGTH)
    printer.client.feed(payloads.info(project=job))
    await _settle(hass)
    # The LAN drops mid-print; the cloud shows the same job running and ending.
    printer.handshake_error = PrinterUnreachableError("gone")
    printer.client.lose()
    cloud.jobs = [cp.job()]
    await coordinator.async_refresh()
    await _settle(hass)
    assert coordinator.uses_cloud
    cloud.jobs = [cp.job(print_status=2, end_time=1790009999)]
    await _poll(entry)
    await _settle(hass)
    charged = float(ledger.data["printers"][str(pid)]["nozzle"]["nozzle_total_g"])
    assert charged > 0
    # LAN comes back and shows the job ending: not charged again.
    printer.handshake_error = None
    printer.connect_payloads[0] = payloads.info(project=None)
    await coordinator.async_refresh()
    await _settle(hass)
    assert coordinator.lan_connected
    assert (
        float(ledger.data["printers"][str(pid)]["nozzle"]["nozzle_total_g"]) == charged
    )
    assert ledger.data["printers"][str(pid)]["last_job_id"] == cp.JOB_ID


# -- D18: a "LAN Mode active" sensor ------------------------------------------------


async def test_d18_lan_mode_sensor_follows_the_connection_outcome(
    hass: HomeAssistant, cloud: FakeCloud, printer: MockPrinter
) -> None:
    entry = await setup_entry(hass, account_entry(lan=True))
    coordinator = entry.runtime_data.primary
    sensor = _entity(hass, entry, "lan_mode_active")
    assert sensor is not None
    assert _state(hass, sensor) == "on"
    handshakes = printer.handshakes
    # The printer switches to cloud mode: its port refuses the next attempt.
    printer.handshake_error = PrinterUnreachableError("refused")
    printer.client.lose()
    await coordinator.async_refresh()
    await _settle(hass)
    assert _state(hass, sensor) == "off"
    # Every outcome is the coordinator's own reconnect: one handshake per
    # refresh, and no client beyond the one connection.
    assert printer.handshakes == handshakes + 1
    printer.handshake_error = LanModeDisabledError("cloud")
    await coordinator.async_refresh()
    await _settle(hass)
    assert _state(hass, sensor) == "off"
    clients = len(printer.clients)
    printer.handshake_error = None
    await coordinator.async_refresh()
    await _settle(hass)
    assert _state(hass, sensor) == "on"
    assert len(printer.clients) == clients + 1
    assert sum(not c.disconnected for c in printer.clients) == 1


async def test_d18_lan_only_entry_in_cloud_mode_is_not_unavailable(
    hass: HomeAssistant, printer: MockPrinter, freezer: FrozenDateTimeFactory
) -> None:
    entry = await setup_entry(hass, lan_entry())
    sensor = "binary_sensor.anycubic_kobra_s1_lan_mode_active"
    printer.handshake_error = LanModeDisabledError("cloud")
    printer.client.lose()
    for _ in range(3):
        freezer.tick(16)
        async_fire_time_changed(hass)
        await _settle(hass)
    assert _state(hass, f"sensor.{P}_nozzle_temperature") == STATE_UNAVAILABLE
    assert _state(hass, sensor) == "off"
    assert not entry.runtime_data.primary.last_update_success


async def test_d18_not_created_without_a_lan_address(
    hass: HomeAssistant, cloud: FakeCloud
) -> None:
    entry = await _cloud(hass)
    assert _entity(hass, entry, "lan_mode_active") is None
    assert _entity(hass, entry, "mqtt_connection_active") is not None


# -- D19: firmware version in LAN Mode -----------------------------------------------


async def test_d19_lan_firmware_and_cloud_only_entities(
    hass: HomeAssistant, cloud: FakeCloud, printer: MockPrinter
) -> None:
    entry = await setup_entry(hass, account_entry(lan=True))
    assert entry.runtime_data.primary.printer.source == "lan"
    firmware_id = _entity(hass, entry, "fw_version")
    assert firmware_id is not None
    firmware = hass.states.get(firmware_id)
    assert firmware is not None
    assert firmware.attributes["installed_version"] == "2.7.2.7"
    # The latest version stays unknown on LAN (U5/G10).
    assert firmware.attributes["latest_version"] is None
    for key in (
        "cloud_camera",
        "request_file_list_local",
        "request_file_list_udisk",
    ):
        entity_id = _entity(hass, entry, key)
        assert entity_id is not None, key
        assert _state(hass, entity_id) == STATE_UNAVAILABLE, key


# -- D20: every coordinator is built with its config entry -----------------------------


async def test_d20_coordinators_have_their_entry(
    hass: HomeAssistant, cloud: FakeCloud, printer: MockPrinter
) -> None:
    cloud.printers[7] = cp.detail(7, name="Second")
    base = account_entry(lan=True)
    entry = account_entry(
        lan=True, data={**base.data, "printer_ids": [cp.PRINTER_ID, 7]}
    )
    await setup_entry(hass, entry)
    coordinators = list(entry.runtime_data.coordinators.values())
    assert len(coordinators) == 2
    for coordinator in coordinators:
        assert isinstance(coordinator, AnycubicCoordinator)
        assert coordinator.config_entry is entry
    lan_only = await setup_entry(hass, lan_entry())
    assert lan_only.runtime_data.primary.config_entry is lan_only


async def test_d16_ledger_follows_each_source_apart(hass: HomeAssistant) -> None:
    """Unit view: runs per source, a number that arrives later, hand-over,
    and numbers charged since setup."""
    ledger = FilamentLedger(hass, "entry")
    await ledger.async_load()
    printer = make_printer()
    pid = printer.printer_id
    one = grams_from_length(LENGTH, "PLA")

    def used() -> float:
        return float(ledger.data["printers"][str(pid)]["nozzle"]["nozzle_total_g"])

    def show(source: str, project: dict[str, Any] | None) -> None:
        printer.source = source  # type: ignore[assignment]
        feed(printer, payloads.info(project=project))
        ledger.update(printer)

    feed(printer, payloads.ace(payloads.box(0, loaded_slot=3)))
    # The cloud shows a job before its number is known (G9), then the number;
    # LAN follows the same numbered job, then ends it: one charge, at the
    # longest length either source saw.
    show("cloud", payloads.job(task_id=None, supplies_usage=100))
    show("cloud", payloads.job(task_id=5, supplies_usage=LENGTH))
    show("lan", payloads.job(task_id=5, supplies_usage=200))
    show("lan", None)
    assert used() == pytest.approx(one, abs=0.01)
    show("cloud", payloads.job(task_id=5, print_status=2, state="finished"))
    show("cloud", None)
    assert used() == pytest.approx(one, abs=0.01)
    # Another numbered job, then a stale cloud record of job 5 running and
    # ending: 5 was charged since setup, so not again.
    show("lan", payloads.job(task_id=6, supplies_usage=LENGTH))
    show("lan", None)
    assert ledger.data["printers"][str(pid)]["last_job_id"] == 6
    show("cloud", payloads.job(task_id=5, supplies_usage=LENGTH))
    show("cloud", None)
    assert used() == pytest.approx(2 * one, abs=0.02)
    # While LAN follows a -1 print, the cloud's view does not end it.
    show("lan", payloads.job(task_id="-1", supplies_usage=LENGTH))
    show("cloud", None)
    show("lan", payloads.job(task_id="-1", supplies_usage=2 * LENGTH))
    show("lan", None)
    assert used() == pytest.approx(4 * one, abs=0.04)


async def test_d14_cloud_error_messages_are_redacted(
    hass: HomeAssistant, cloud: FakeCloud
) -> None:
    entry = await _cloud(hass)
    cloud.printer_errors[cp.PRINTER_ID] = AnycubicCloudError(f"refused {JWT}")
    await _poll(entry)
    error = entry.runtime_data.primary.last_exception
    assert error is not None
    assert "eyJ" not in str(error.translation_placeholders)


async def test_d16_shares_length_and_late_number(hass: HomeAssistant) -> None:
    """A multi-colour cloud run still records its length; its split survives
    the end on LAN; a number first seen on the end record is adopted."""
    ledger = FilamentLedger(hass, "entry")
    await ledger.async_load()
    printer = make_printer()
    pid = printer.printer_id
    feed(printer, payloads.ace(payloads.box(0, loaded_slot=3)))
    shares = {0: 0.5, 1: 0.5}

    def show(source: str, project: dict[str, Any] | None) -> None:
        printer.source = source  # type: ignore[assignment]
        feed(printer, payloads.info(project=project))
        ledger.update(printer)

    def used(slot: str) -> float:
        slots = ledger.data["printers"][str(pid)]["slots"]
        return float(slots.get(slot, {}).get("filament_used_g", 0.0))

    with patch.object(Printer, "job_paint_shares", new_callable=PropertyMock) as paint:
        paint.return_value = shares
        show("cloud", payloads.job(task_id=5, supplies_usage=LENGTH))
        paint.return_value = {}
        show("lan", payloads.job(task_id=5, supplies_usage=100))
        show("lan", None)
    half = grams_from_length(LENGTH / 2, "PLA")
    assert used("0") == pytest.approx(half, abs=0.01)
    assert used("1") == pytest.approx(half, abs=0.01)
    # An unnumbered run whose end record carries the number: it is adopted,
    # so the other source's run of that number is not charged again.
    show("cloud", payloads.job(task_id=8, supplies_usage=LENGTH))
    show("lan", payloads.job(task_id=None, supplies_usage=LENGTH))
    show("lan", payloads.job(task_id=8, print_status=2, state="finished"))
    assert ledger.data["printers"][str(pid)]["last_job_id"] == 8
    before = used("3")
    show("cloud", None)
    assert used("3") == before
