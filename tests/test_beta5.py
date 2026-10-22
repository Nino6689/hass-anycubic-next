"""Beta 5: decisions and field reports from 2026-10-22 (ACCEPTANCE.md D25).

Each test is named after the item it accepts. Printer messages run through
the libraries' own parsers: anycubic-lan for LAN (the fake LAN client) and
anycubic-cloud-client for the cloud record and MQTT (the fake account).
"""

from __future__ import annotations

from typing import Any

from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from . import cloud_payloads as cp, payloads
from .cloud_fakes import FakeCloud
from .conftest import MockPrinter, account_entry, lan_entry, setup_entry

P = "anycubic_kobra_s1"
C = "kobra_s1_cloud"
BOX_INFO_KEYS = {
    "box_id",
    "model_id",
    "status",
    "temperature",
    "humidity",
    "auto_feed",
    "loaded_slot",
    "feed_status",
}
DRYING = {"status": 1, "target_temp": 50, "duration": 240, "remain_time": 162}


async def _settle(hass: HomeAssistant) -> None:
    await hass.async_block_till_done(wait_background_tasks=True)


async def _feed(hass: HomeAssistant, printer: MockPrinter, *items: Any) -> None:
    for item in items:
        printer.client.feed(item)
    await _settle(hass)


def _box_info(hass: HomeAssistant, entity_id: str) -> dict[str, Any]:
    state = hass.states.get(entity_id)
    assert state is not None, entity_id
    info: dict[str, Any] = state.attributes["box_info"]
    assert set(info) == BOX_INFO_KEYS  # nothing else in box_info changes
    return info


def _keys(hass: HomeAssistant, entry: MockConfigEntry) -> set[str]:
    return {
        item.unique_id.split("-")[-1]
        for item in er.async_entries_for_config_entry(
            er.async_get(hass), entry.entry_id
        )
    }


async def _cloud(hass: HomeAssistant) -> MockConfigEntry:
    entry = account_entry()
    return await setup_entry(
        hass, account_entry(options={**entry.options, "mqtt_connect_mode": 4})
    )


async def _poll(entry: MockConfigEntry) -> None:
    entry.runtime_data.cloud._next_due = None
    await entry.runtime_data.primary.async_refresh()


def _push(cloud: FakeCloud, *boxes: dict[str, Any], action: str = "getInfo") -> None:
    cloud.feed(
        cp.mqtt("multiColorBox", action, "success", {"multi_color_box": list(boxes)})
    )


# -- D25: box_info humidity reads null until there is a real reading ---------------


async def test_d25_lan_box_that_only_reports_0_reads_null(
    hass: HomeAssistant, printer: MockPrinter
) -> None:
    printer.connect_payloads[1] = payloads.ace(
        payloads.box(0, humidity=0), payloads.box(1, humidity=0)
    )
    entry = await setup_entry(hass, lan_entry())
    first = f"sensor.{P}_ace_pro_ace_spools"
    second = f"sensor.{P}_ace_pro_2_secondary_ace_spools"
    for _ in range(3):
        await _feed(
            hass,
            printer,
            payloads.ace(payloads.box(0, humidity=0), payloads.box(1, humidity=0)),
        )
        assert _box_info(hass, first)["humidity"] is None
        assert _box_info(hass, second)["humidity"] is None
    # A box that never sends the key at all reads null too.
    await _feed(hass, printer, payloads.ace(payloads.box(0), payloads.box(1)))
    assert _box_info(hass, first)["humidity"] is None
    # The humidity sensors are still not created for such a box (D22).
    assert not _keys(hass, entry) & {"ace_humidity", "secondary_ace_humidity"}


async def test_d25_lan_real_reading_is_shown_and_kept_through_partial_reports(
    hass: HomeAssistant, printer: MockPrinter
) -> None:
    await setup_entry(hass, lan_entry())
    first = f"sensor.{P}_ace_pro_ace_spools"
    await _feed(
        hass, printer, payloads.ace(payloads.box(0, humidity=0, temp=31, auto_feed=1))
    )
    before = _box_info(hass, first)
    assert before["humidity"] is None

    await _feed(hass, printer, payloads.ace(payloads.box(0, humidity=41, temp=31)))
    info = _box_info(hass, first)
    assert info["humidity"] == 41
    # Only the humidity differs from the report without a reading.
    assert {k: v for k, v in info.items() if k != "humidity"} == {
        k: v for k, v in before.items() if k != "humidity"
    } | {"auto_feed": False}

    # Partial reports that leave humidity out keep it, like everything else.
    await _feed(
        hass,
        printer,
        payloads.ace({"id": 0, "loaded_slot": 2}, action="autoUpdateInfo"),
        payloads.ace({"id": 0, "temp": 35}, action="autoUpdateInfo"),
        payloads.ace(
            {"id": 0, "drying_status": DRYING | {"status": 0}},
            action="autoUpdateDryStatus",
        ),
    )
    info = _box_info(hass, first)
    assert info["humidity"] == 41
    assert info["loaded_slot"] == 3
    assert info["temperature"] == 35
    assert hass.states.get(f"sensor.{P}_ace_pro_ace_humidity").state == "41.0"

    # An explicit 0 is no reading, as for the sensor (D22): null again.
    await _feed(hass, printer, payloads.ace(payloads.box(0, humidity=0)))
    assert _box_info(hass, first)["humidity"] is None
    assert (
        hass.states.get(f"sensor.{P}_ace_pro_ace_humidity").state == STATE_UNAVAILABLE
    )


async def test_d25_lan_drying_report_reading_counts(
    hass: HomeAssistant, printer: MockPrinter
) -> None:
    await setup_entry(hass, lan_entry())
    first = f"sensor.{P}_ace_pro_ace_spools"
    assert _box_info(hass, first)["humidity"] is None
    await _feed(
        hass,
        printer,
        payloads.ace(
            {"id": 0, "drying_status": DRYING | {"humidity": 28}},
            action="autoUpdateDryStatus",
        ),
    )
    assert _box_info(hass, first)["humidity"] == 28
    # A later box report without its own reading keeps the drying reading.
    await _feed(
        hass, printer, payloads.ace({"id": 0, "temp": 44}, action="autoUpdateInfo")
    )
    assert _box_info(hass, first)["humidity"] == 28


async def test_d25_lan_second_ace(hass: HomeAssistant, printer: MockPrinter) -> None:
    await setup_entry(hass, lan_entry())
    first = f"sensor.{P}_ace_pro_ace_spools"
    second = f"sensor.{P}_ace_pro_2_secondary_ace_spools"
    await _feed(
        hass,
        printer,
        payloads.ace(payloads.box(0, humidity=0), payloads.box(1, humidity=58)),
    )
    assert _box_info(hass, first)["humidity"] is None
    assert _box_info(hass, second)["humidity"] == 58
    await _feed(
        hass,
        printer,
        payloads.ace(
            {"id": 1, "drying_status": DRYING | {"humidity": 33}},
            action="autoUpdateDryStatus",
        ),
    )
    assert _box_info(hass, first)["humidity"] is None
    assert _box_info(hass, second)["humidity"] == 33


async def test_d25_cloud_box_that_only_reports_0_reads_null(
    hass: HomeAssistant, cloud: FakeCloud
) -> None:
    cloud.printers[cp.PRINTER_ID] = cp.detail(multi_color_box=cp.ace_box(0, humidity=0))
    entry = await _cloud(hass)
    spools = f"sensor.{C}_ace_pro_ace_spools"
    assert _box_info(hass, spools)["humidity"] is None
    _push(cloud, cp.ace_box(0, humidity=0))
    await _settle(hass)
    await _poll(entry)
    await _settle(hass)
    assert _box_info(hass, spools)["humidity"] is None
    assert "ace_humidity" not in _keys(hass, entry)


async def test_d25_cloud_real_reading_is_shown_and_kept(
    hass: HomeAssistant, cloud: FakeCloud
) -> None:
    cloud.printers[cp.PRINTER_ID] = cp.detail(multi_color_box=cp.ace_box(0, humidity=0))
    entry = await _cloud(hass)
    spools = f"sensor.{C}_ace_pro_ace_spools"
    before = _box_info(hass, spools)
    assert before["humidity"] is None

    _push(cloud, cp.ace_box(0, humidity=70))
    await _settle(hass)
    info = _box_info(hass, spools)
    assert info["humidity"] == 70
    assert {k: v for k, v in info.items() if k != "humidity"} == {
        k: v for k, v in before.items() if k != "humidity"
    }

    # A partial push without humidity keeps it.
    _push(cloud, {"id": 0, "temp": 40}, action="autoUpdateInfo")
    await _settle(hass)
    assert _box_info(hass, spools)["humidity"] == 70

    # The drying report's reading counts, over the cloud too.
    _push(
        cloud,
        {"id": 0, "drying_status": DRYING | {"humidity": 28}},
        action="autoUpdateDryStatus",
    )
    await _settle(hass)
    assert _box_info(hass, spools)["humidity"] == 28

    # The record, on the next poll.
    cloud.printers[cp.PRINTER_ID] = cp.detail(
        multi_color_box=cp.ace_box(0, humidity=61)
    )
    await _poll(entry)
    await _settle(hass)
    assert _box_info(hass, spools)["humidity"] == 61
    assert hass.states.get(f"sensor.{C}_ace_pro_ace_humidity").state == "61.0"


async def test_d25_cloud_second_ace(hass: HomeAssistant, cloud: FakeCloud) -> None:
    cloud.printers[cp.PRINTER_ID] = cp.detail(
        multi_color_box=[cp.ace_box(0, humidity=0), cp.ace_box(1, humidity=0)]
    )
    await _cloud(hass)
    first = f"sensor.{C}_ace_pro_ace_spools"
    second = f"sensor.{C}_ace_pro_2_secondary_ace_spools"
    assert _box_info(hass, first)["humidity"] is None
    assert _box_info(hass, second)["humidity"] is None
    _push(cloud, cp.ace_box(0, humidity=0), cp.ace_box(1, humidity=47))
    await _settle(hass)
    assert _box_info(hass, first)["humidity"] is None
    assert _box_info(hass, second)["humidity"] == 47
