"""Beta 4: field reports, 2026-10-19 to 2026-10-20 (ACCEPTANCE.md D21-D23).

Each test is named after the item it accepts. Printer messages run through
the libraries' own parsers: anycubic-lan for LAN (the fake LAN client) and
anycubic-cloud-client for the cloud record and MQTT (the fake account).
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import PERCENTAGE, STATE_UNAVAILABLE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.anycubic_cloud.const import DOMAIN

from . import cloud_payloads as cp, payloads
from .cloud_fakes import FakeCloud
from .conftest import MockPrinter, account_entry, lan_entry, setup_entry

P = "anycubic_kobra_s1"
C = "kobra_s1_cloud"
PID = f"None-{payloads.PRINTER_ID}"  # a LAN-only entry's device (Q4)
CHAMBERLESS = {"curr_hotbed_temp": 31, "curr_nozzle_temp": 34, "curr_chamber_temp": 0}


async def _settle(hass: HomeAssistant) -> None:
    await hass.async_block_till_done(wait_background_tasks=True)


async def _feed(hass: HomeAssistant, printer: MockPrinter, *items: Any) -> None:
    for item in items:
        printer.client.feed(item)
    await _settle(hass)


def _keys(hass: HomeAssistant, entry: MockConfigEntry) -> set[str]:
    """The keys of every entity the entry has registered."""
    return {
        item.unique_id.split("-")[-1]
        for item in er.async_entries_for_config_entry(
            er.async_get(hass), entry.entry_id
        )
    }


def _item(hass: HomeAssistant, entry: MockConfigEntry, key: str) -> er.RegistryEntry:
    for item in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id):
        if item.unique_id.endswith(f"-{key}"):
            return item
    raise AssertionError(key)


def _device(hass: HomeAssistant, item: er.RegistryEntry) -> dr.DeviceEntry:
    assert item.device_id is not None
    device = dr.async_get(hass).async_get(item.device_id)
    assert device is not None
    return device


def _temp(chamber: float | None) -> dict[str, Any]:
    data: dict[str, Any] = {"curr_hotbed_temp": 60, "curr_nozzle_temp": 220}
    if chamber is not None:
        data["curr_chamber_temp"] = chamber
    return payloads.envelope("tempature", data, action="auto")


async def _cloud(hass: HomeAssistant) -> MockConfigEntry:
    entry = account_entry()
    return await setup_entry(
        hass, account_entry(options={**entry.options, "mqtt_connect_mode": 4})
    )


async def _poll(entry: MockConfigEntry) -> None:
    entry.runtime_data.cloud._next_due = None
    await entry.runtime_data.primary.async_refresh()


def _parameter(chamber: float) -> dict[str, Any]:
    return {
        "curr_hotbed_temp": 28,
        "curr_nozzle_temp": 31,
        "curr_chamber_temp": chamber,
    }


# -- D21: chamber temperature, where the printer has a sensor ----------------------


async def test_d21_lan_chamber_temperature_on_first_non_zero_reading(
    hass: HomeAssistant, printer: MockPrinter
) -> None:
    printer.connect_payloads[0] = payloads.info(temp=CHAMBERLESS)
    entry = await setup_entry(hass, lan_entry())
    await _feed(hass, printer, _temp(0), _temp(None), _temp(0))
    assert "chamber_temperature" not in _keys(hass, entry)
    assert hass.states.get(f"sensor.{P}_chamber_temperature") is None

    # A Kobra S1 Max: created now, without a reload.
    await _feed(hass, printer, _temp(32))
    item = _item(hass, entry, "chamber_temperature")
    assert item.unique_id == f"{payloads.MAC_UID}-chamber_temperature"
    assert item.entity_id == f"sensor.{P}_chamber_temperature"
    assert _device(hass, item).identifiers == {(DOMAIN, PID)}
    state = hass.states.get(item.entity_id)
    assert state is not None
    assert state.state == "32.0"
    assert state.attributes["unit_of_measurement"] == UnitOfTemperature.CELSIUS
    assert state.attributes["device_class"] == SensorDeviceClass.TEMPERATURE
    assert state.attributes["friendly_name"] == "Anycubic Kobra S1 Chamber Temperature"

    # 0 is no reading, not 0 °C; the entity stays.
    await _feed(hass, printer, _temp(0))
    assert hass.states.get(item.entity_id).state == STATE_UNAVAILABLE
    await _feed(
        hass, printer, payloads.info(temp=CHAMBERLESS | {"curr_chamber_temp": 35})
    )
    assert hass.states.get(item.entity_id).state == "35.0"


async def test_d21_lan_printer_reporting_nothing_gets_no_chamber_sensor(
    hass: HomeAssistant, printer: MockPrinter
) -> None:
    entry = await setup_entry(hass, lan_entry())
    await _feed(hass, printer, _temp(None), payloads.info())
    assert "chamber_temperature" not in _keys(hass, entry)
    await hass.config_entries.async_reload(entry.entry_id)
    await _settle(hass)
    assert "chamber_temperature" not in _keys(hass, entry)


async def test_d21_cloud_chamber_temperature_from_the_record_and_mqtt(
    hass: HomeAssistant, cloud: FakeCloud
) -> None:
    cloud.printers[cp.PRINTER_ID] = cp.detail(parameter=_parameter(0))
    entry = await _cloud(hass)
    await _poll(entry)
    assert "chamber_temperature" not in _keys(hass, entry)
    cloud.feed(cp.mqtt("tempature", "auto", "done", _parameter(0)))
    await _settle(hass)
    assert "chamber_temperature" not in _keys(hass, entry)

    cloud.printers[cp.PRINTER_ID] = cp.detail(parameter=_parameter(32))
    await _poll(entry)
    await _settle(hass)
    entity_id = f"sensor.{C}_chamber_temperature"
    assert _item(hass, entry, "chamber_temperature").entity_id == entity_id
    assert hass.states.get(entity_id).state == "32.0"
    cloud.feed(cp.mqtt("tempature", "auto", "done", _parameter(33)))
    await _settle(hass)
    assert hass.states.get(entity_id).state == "33.0"


async def test_d21_cloud_chamber_temperature_from_mqtt_first(
    hass: HomeAssistant, cloud: FakeCloud
) -> None:
    entry = await _cloud(hass)
    assert "chamber_temperature" not in _keys(hass, entry)
    cloud.feed(cp.mqtt("tempature", "auto", "done", _parameter(31)))
    await _settle(hass)
    assert hass.states.get(f"sensor.{C}_chamber_temperature").state == "31.0"


# -- D22: ACE humidity, where the box has a sensor ---------------------------------


async def test_d22_lan_ace_humidity_on_first_non_zero_reading(
    hass: HomeAssistant, printer: MockPrinter
) -> None:
    printer.connect_payloads[1] = payloads.ace(
        payloads.box(0, humidity=0), payloads.box(1, humidity=0)
    )
    entry = await setup_entry(hass, lan_entry())
    await _feed(hass, printer, payloads.ace(payloads.box(0), payloads.box(1)))
    keys = _keys(hass, entry)
    assert "secondary_ace_current_temperature" in keys  # the second ACE is there
    assert not keys & {"ace_humidity", "secondary_ace_humidity"}

    # The second box reports first: only its sensor appears, on its device.
    await _feed(
        hass,
        printer,
        payloads.ace(payloads.box(0, humidity=0), payloads.box(1, humidity=58)),
    )
    assert "ace_humidity" not in _keys(hass, entry)
    second = _item(hass, entry, "secondary_ace_humidity")
    assert _device(hass, second).identifiers == {(DOMAIN, f"{PID}-ace1")}
    state = hass.states.get(second.entity_id)
    assert state.state == "58.0"
    assert state.attributes["unit_of_measurement"] == PERCENTAGE
    assert state.attributes["device_class"] == SensorDeviceClass.HUMIDITY

    await _feed(
        hass,
        printer,
        payloads.ace(payloads.box(0, humidity=84), action="autoUpdateInfo"),
    )
    first = _item(hass, entry, "ace_humidity")
    assert first.unique_id == f"{payloads.MAC_UID}-ace_humidity"
    assert _device(hass, first).identifiers == {(DOMAIN, f"{PID}-ace0")}
    assert hass.states.get(first.entity_id).state == "84.0"
    spools = hass.states.get(f"sensor.{P}_ace_pro_ace_spools")
    assert spools.attributes["box_info"]["humidity"] == 84

    # 0 afterwards is no reading.
    await _feed(hass, printer, payloads.ace(payloads.box(0, humidity=0)))
    assert hass.states.get(first.entity_id).state == STATE_UNAVAILABLE


async def test_d22_lan_drying_report_humidity_creates_the_sensor(
    hass: HomeAssistant, printer: MockPrinter
) -> None:
    entry = await setup_entry(hass, lan_entry())
    assert "ace_humidity" not in _keys(hass, entry)
    drying = {"status": 1, "target_temp": 50, "duration": 240, "remain_time": 162}
    await _feed(
        hass,
        printer,
        payloads.ace(
            {"id": 0, "drying_status": drying | {"humidity": 28}},
            action="autoUpdateDryStatus",
        ),
    )
    assert hass.states.get(f"sensor.{P}_ace_pro_ace_humidity").state == "28.0"


async def test_d22_cloud_ace_humidity(hass: HomeAssistant, cloud: FakeCloud) -> None:
    cloud.printers[cp.PRINTER_ID] = cp.detail(multi_color_box=cp.ace_box(0, humidity=0))
    entry = await _cloud(hass)
    assert "ace_humidity" not in _keys(hass, entry)

    # A pushed box report carries it (parsed by anycubic-lan).
    cloud.feed(
        cp.mqtt(
            "multiColorBox",
            "getInfo",
            "success",
            {"multi_color_box": [cp.ace_box(0, humidity=70)]},
        )
    )
    await _settle(hass)
    entity_id = f"sensor.{C}_ace_pro_ace_humidity"
    assert hass.states.get(entity_id).state == "70.0"
    # And the record, on the next poll.
    cloud.printers[cp.PRINTER_ID] = cp.detail(
        multi_color_box=cp.ace_box(0, humidity=61)
    )
    await _poll(entry)
    await _settle(hass)
    assert hass.states.get(entity_id).state == "61.0"
    assert "secondary_ace_humidity" not in _keys(hass, entry)


async def test_d22_cloud_record_humidity_at_setup(
    hass: HomeAssistant, cloud: FakeCloud
) -> None:
    entry = await _cloud(hass)  # the fixture's box reads 12 %
    assert (
        _item(hass, entry, "ace_humidity").entity_id
        == f"sensor.{C}_ace_pro_ace_humidity"
    )
    assert hass.states.get(f"sensor.{C}_ace_pro_ace_humidity").state == "12.0"


# -- D23: the box fan is the printer's enclosure fan --------------------------------


async def test_d23_chamber_fan_on_the_printer(
    hass: HomeAssistant, printer: MockPrinter
) -> None:
    printer.connect_payloads[1] = payloads.ace(payloads.box(0), payloads.box(1))
    entry = await setup_entry(hass, lan_entry())
    item = _item(hass, entry, "box_fan_level")
    assert item.unique_id == f"{payloads.MAC_UID}-box_fan_level"
    assert item.entity_id == f"sensor.{P}_chamber_fan_level"
    assert _device(hass, item).identifiers == {(DOMAIN, PID)}
    state = hass.states.get(item.entity_id)
    assert state.state == "3"
    assert state.attributes["friendly_name"] == "Anycubic Kobra S1 Chamber Fan Level"
    await _feed(hass, printer, payloads.envelope("fan", {"box_fan_level": 60}))
    assert hass.states.get(item.entity_id).state == "60"

    number = _item(hass, entry, "set_box_fan_level")
    assert number.entity_id == f"number.{P}_set_chamber_fan_level"
    assert _device(hass, number).identifiers == {(DOMAIN, PID)}
    friendly = hass.states.get(number.entity_id).attributes["friendly_name"]
    assert friendly == "Anycubic Kobra S1 Set chamber fan level"
    # A second ACE gets no copy.
    assert "secondary_ace_current_temperature" in _keys(hass, entry)
    assert [k for k in _keys(hass, entry) if "fan" in k and "secondary" in k] == []


async def test_d23_chamber_fan_created_when_first_reported(
    hass: HomeAssistant, printer: MockPrinter
) -> None:
    info = payloads.info()
    del info["data"]["box_fan_level"]
    printer.connect_payloads[0] = info
    entry = await setup_entry(hass, lan_entry())
    await _feed(hass, printer, payloads.envelope("fan", {"fan_speed_pct": 40}))
    assert "box_fan_level" not in _keys(hass, entry)
    await _feed(hass, printer, payloads.envelope("fan", {"box_fan_level": 80}))
    assert hass.states.get(f"sensor.{P}_chamber_fan_level").state == "80"


async def test_d23_existing_box_fan_moves_to_the_printer(
    hass: HomeAssistant, printer: MockPrinter
) -> None:
    """From 2.9.9: same unique id and entity id, the printer's device."""
    entry = lan_entry()
    entry.add_to_hass(hass)
    devices = dr.async_get(hass)
    ace = devices.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, f"{PID}-ace0")},
        name="Anycubic Kobra S1 ACE Pro",
    )
    registry = er.async_get(hass)
    old = registry.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{payloads.MAC_UID}-box_fan_level",
        config_entry=entry,
        device_id=ace.id,
        suggested_object_id="anycubic_kobra_s1_ace_pro_ace_box_fan_level",
    )
    # Not reported yet: the entry still moves at setup.
    info = payloads.info()
    del info["data"]["box_fan_level"]
    printer.connect_payloads[0] = info
    await hass.config_entries.async_setup(entry.entry_id)
    await _settle(hass)
    item = registry.async_get(old.entity_id)
    assert item is not None
    assert item.entity_id == "sensor.anycubic_kobra_s1_ace_pro_ace_box_fan_level"
    assert _device(hass, item).identifiers == {(DOMAIN, PID)}
    await _feed(hass, printer, payloads.envelope("fan", {"box_fan_level": 60}))
    assert hass.states.get(old.entity_id).state == "60"
    assert registry.async_get(old.entity_id).device_id == item.device_id
