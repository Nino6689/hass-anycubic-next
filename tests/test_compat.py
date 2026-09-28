"""Compatibility with 2.x installs (COMPAT §1-§3, §6)."""

from __future__ import annotations

import copy
from typing import Any

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import (
    device_registry as dr,
    entity_registry as er,
    issue_registry as ir,
)
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.anycubic_cloud.const import DOMAIN
from custom_components.anycubic_cloud.identity import lan_printer_id

from . import payloads
from .conftest import (
    CLOUD_PRINTER_ID,
    CLOUD_USER_ID,
    MockPrinter,
    cloud_entry,
    find_device,
    lan_entry,
    setup_entry,
)

PID = str(payloads.PRINTER_ID)

# A ledger as 2.x writes it (COMPAT §6), values made up.
LEDGER_2X: dict[str, Any] = {
    "printers": {
        PID: {
            "slots": {
                "0": {
                    "spool_weight_g": 1000.0,
                    "filament_used_g": 250.5,
                    "spool_signature": "PLA|#FFFFFF|SKU0",
                    "spool_price_per_kg": 20.0,
                },
                "1": {
                    "spool_weight_g": 334.0,
                    "filament_used_g": 51.0,
                    "spool_signature": "PLA|#000000|SKU1",
                },
                "2": {
                    "spool_weight_g": 1000.0,
                    "filament_used_g": 0.0,
                    "spool_signature": "PLA|#FF0000|SKU2",
                    "spool_price_per_kg": 0.0,
                },
                "3": {
                    "spool_weight_g": 5000.0,
                    "filament_used_g": 0.0,
                    "spool_signature": "PLA|#0080FF|SKU3",
                },
            },
            "last_job_id": 111,
            "totals": {
                "material_totals": {"PLA": 1234.5, "PETG": 10.0},
                "last_job_grams": 50.3,
                "last_job_cost": 1.01,
                "cost_total": 24.69,
            },
            "nozzle": {"nozzle_total_g": 1500.2, "nozzle_abrasive_g": 250.0},
            "axis_step": 15,
            "drying_settings": {"temperature": 50.0, "duration": 300.0},
            "feeding_slot": 2,
        }
    },
    "spools": {
        "PETG|#00FF00|": {
            "filament_used_g": 100.0,
            "spool_weight_g": 1000.0,
            "spool_price_per_kg": 25.0,
        },
    },
    "jobs": {"Wolf_plate(01)_PLA_0.2_45s": [50.34, 49.49, 49.49]},
}


def _store(hass_storage: dict[str, Any], entry: MockConfigEntry, data: Any) -> str:
    key = f"anycubic_cloud.filament.{entry.entry_id}"
    hass_storage[key] = {
        "version": 1,
        "minor_version": 1,
        "key": key,
        "data": copy.deepcopy(data),
    }
    return key


def _state(hass: HomeAssistant, entity_id: str) -> str:
    state = hass.states.get(entity_id)
    assert state is not None, entity_id
    return state.state


def test_lan_printer_id_rule() -> None:
    """Digits up to 15 kept; otherwise BLAKE2b digest_size=6, big-endian."""
    import hashlib

    assert lan_printer_id("123456789012345") == 123456789012345
    long_digits = "1234567890123456"
    expected = int.from_bytes(
        hashlib.blake2b(long_digits.encode(), digest_size=6).digest(), "big"
    )
    assert lan_printer_id(long_digits) == expected
    assert lan_printer_id(payloads.DEVICE_ID) == payloads.PRINTER_ID
    assert payloads.PRINTER_ID < 2**48


async def test_lan_only_entry_identity(
    hass: HomeAssistant, printer: MockPrinter
) -> None:
    """Devices keep the literal ``None-`` prefix; unique ids are MAC-based."""
    entry = await setup_entry(hass, lan_entry())
    assert entry.state is ConfigEntryState.LOADED

    device = find_device(hass, f"None-{PID}")
    assert device is not None
    assert device.manufacturer == "Anycubic"
    assert device.model == "Anycubic Kobra S1"
    assert device.name == "Anycubic Kobra S1"
    assert device.sw_version == "2.7.2.7"
    assert device.serial_number == PID
    assert (dr.CONNECTION_NETWORK_MAC, payloads.MAC) in device.connections
    assert device.via_device_id is None

    ace = find_device(hass, f"None-{PID}-ace0")
    assert ace is not None
    assert ace.via_device_id == device.id
    assert ace.name == "Anycubic Kobra S1 ACE Pro"
    assert ace.model == "ACE Pro"

    entities = er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    assert len(entities) > 100
    for item in entities:
        key = item.unique_id.removeprefix(f"{payloads.MAC_UID}-")
        assert key != item.unique_id, item.unique_id
        # The frontend finds entities by translation key == key.
        assert item.translation_key == key
        assert item.has_entity_name

    # New installs get the same entity ids as 2.x (device + entity name).
    assert _state(hass, "sensor.anycubic_kobra_s1_nozzle_temperature") == "34.0"
    assert _state(hass, "sensor.anycubic_kobra_s1_ace_pro_ace_slot_1") == "PLA"
    assert _state(hass, "binary_sensor.anycubic_kobra_s1_axis_move_refused") == "off"


async def test_existing_registry_entries_are_reused(
    hass: HomeAssistant, printer: MockPrinter
) -> None:
    """Entities keep the ids (and user choices) 2.x left in the registry."""
    entry = lan_entry()
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    renamed = registry.async_get_or_create(
        Platform.SENSOR,
        DOMAIN,
        f"{payloads.MAC_UID}-ace_slot_1_filament_remaining",
        config_entry=entry,
        suggested_object_id="my_white_reel",
    )
    assert renamed.disabled_by is None
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert _state(hass, renamed.entity_id) == "1000.0"


async def test_2x_ledger_loads_and_keeps_working(
    hass: HomeAssistant, printer: MockPrinter, hass_storage: dict[str, Any]
) -> None:
    """A 2.x filament ledger is read as-is and written back in its shape."""
    entry = lan_entry()
    key = _store(hass_storage, entry, LEDGER_2X)
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    for suffix in (
        "ace_slot_1_filament_remaining",
        "ace_slot_1_filament_remaining_percent",
        "ace_slot_2_filament_remaining",
        "ace_slot_2_filament_remaining_percent",
        "ace_slot_4_filament_remaining_percent",
        "ace_slot_1_spool_weight",
        "ace_slot_1_spool_price",
        "last_job_filament",
        "nozzle_filament_total",
        "spool_inventory_count",
    ):
        platform = (
            "number" if "spool_" in suffix and "remaining" not in suffix else "sensor"
        )
        if suffix == "spool_inventory_count":
            platform = "sensor"
        registry.async_get_or_create(
            platform,
            DOMAIN,
            f"{payloads.MAC_UID}-{suffix}",
            config_entry=entry,
            suggested_object_id=suffix,
        )
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)

    assert _state(hass, "sensor.ace_slot_1_filament_remaining") == "749.5"
    assert _state(hass, "sensor.ace_slot_1_filament_remaining_percent") == "75.0"
    # 334 g entered, 51 g used: 283 g of a full 1000 g reel (BEHAVIOUR §3.4).
    assert _state(hass, "sensor.ace_slot_2_filament_remaining") == "283.0"
    assert _state(hass, "sensor.ace_slot_2_filament_remaining_percent") == "28.3"
    # A 5 kg reel is measured against itself.
    assert _state(hass, "sensor.ace_slot_4_filament_remaining_percent") == "100.0"
    assert _state(hass, "number.ace_slot_1_spool_weight") == "1000.0"
    assert _state(hass, "number.ace_slot_1_spool_price") == "20.0"
    assert _state(hass, "sensor.last_job_filament") == "50.3"
    assert _state(hass, "sensor.anycubic_kobra_s1_last_job_cost") == "1.01"
    total = hass.states.get("sensor.anycubic_kobra_s1_filament_cost_total")
    assert total is not None
    assert total.state == "24.69"
    assert total.attributes["by_material_g"] == {"PLA": 1234.5, "PETG": 10.0}
    assert _state(hass, "sensor.nozzle_filament_total") == "1500.2"
    assert _state(hass, "sensor.anycubic_kobra_s1_nozzle_abrasive_filament") == "250.0"
    assert _state(hass, "sensor.anycubic_kobra_s1_nozzle_wear") == "25.0"
    assert _state(hass, "select.anycubic_kobra_s1_axis_step_size") == "15 mm"
    assert _state(hass, "number.anycubic_kobra_s1_ace_pro_drying_temperature") == "50"
    assert _state(hass, "number.anycubic_kobra_s1_ace_pro_drying_duration") == "300"

    # A second report banks each slot under its signature (BEHAVIOUR §3.3).
    printer.client.feed(payloads.ace(payloads.box(0)))
    await hass.async_block_till_done(wait_background_tasks=True)
    assert _state(hass, "sensor.spool_inventory_count") == "5"

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    stored = hass_storage[key]["data"]
    assert stored["printers"][PID] == LEDGER_2X["printers"][PID]
    assert stored["jobs"] == LEDGER_2X["jobs"]
    assert stored["spools"]["PETG|#00FF00|"] == LEDGER_2X["spools"]["PETG|#00FF00|"]
    assert stored["spools"]["PLA|#FFFFFF|SKU0"] == {
        "filament_used_g": 250.5,
        "spool_weight_g": 1000.0,
        "spool_price_per_kg": 20.0,
    }
    assert hass_storage[key]["version"] == 1


async def test_ledger_not_overwritten_when_setup_fails(
    hass: HomeAssistant, printer: MockPrinter, hass_storage: dict[str, Any]
) -> None:
    """An entry that never loads must leave the stored ledger alone."""
    from anycubic_lan import PrinterUnreachableError

    printer.handshake_error = PrinterUnreachableError("off")
    entry = lan_entry()
    key = _store(hass_storage, entry, LEDGER_2X)
    await setup_entry(hass, entry)
    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert hass_storage[key]["data"] == LEDGER_2X


async def test_hybrid_2x_cloud_entry_runs_on_lan(
    hass: HomeAssistant, printer: MockPrinter
) -> None:
    """A cloud entry with LAN Mode on keeps its account-based identifiers."""
    entry = await setup_entry(hass, cloud_entry(lan=True))
    assert entry.state is ConfigEntryState.LOADED
    identifier = f"{CLOUD_USER_ID}-{CLOUD_PRINTER_ID}"
    assert find_device(hass, identifier) is not None
    assert find_device(hass, f"{identifier}-ace0") is not None
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(
        "sensor", DOMAIN, f"{payloads.MAC_UID}-curr_nozzle_temp"
    )
    assert entity_id is not None


async def test_2x_cloud_entry_waits_without_touching_data(
    hass: HomeAssistant, printer: MockPrinter
) -> None:
    """Without LAN Mode a cloud entry is not ready, explained, and unchanged."""
    entry = cloud_entry(lan=False)
    data, options = copy.deepcopy(dict(entry.data)), copy.deepcopy(dict(entry.options))
    await setup_entry(hass, entry)
    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert entry.reason is not None
    assert "cloud" in entry.reason
    assert dict(entry.data) == data
    assert dict(entry.options) == options
    issue = ir.async_get(hass).async_get_issue(
        DOMAIN, f"cloud_not_supported_yet_{entry.entry_id}"
    )
    assert issue is not None
    assert issue.translation_placeholders == {"name": entry.title}
    assert printer.handshakes == 0

    await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert (
        ir.async_get(hass).async_get_issue(
            DOMAIN, f"cloud_not_supported_yet_{entry.entry_id}"
        )
        is None
    )


async def test_lan_only_entry_with_lan_switched_off(
    hass: HomeAssistant, printer: MockPrinter
) -> None:
    entry = lan_entry(options={"lan_mode_enabled": False, "lan_host": payloads.HOST})
    await setup_entry(hass, entry)
    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert printer.handshakes == 0


async def test_entry_without_printer_ids_derives_the_id(
    hass: HomeAssistant, printer: MockPrinter
) -> None:
    entry = lan_entry(data={"lan_host": payloads.HOST})
    await setup_entry(hass, entry)
    assert find_device(hass, f"None-{PID}")


async def test_entry_with_several_printers_uses_the_first(
    hass: HomeAssistant, printer: MockPrinter
) -> None:
    entry = cloud_entry(lan=True)
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=CLOUD_USER_ID,
        data={**entry.data, "printer_ids": [7, 8]},
        options=dict(entry.options),
    )
    await setup_entry(hass, entry)
    assert find_device(hass, f"{CLOUD_USER_ID}-7")


async def test_printer_without_mac(hass: HomeAssistant, printer: MockPrinter) -> None:
    """Without a MAC unique ids are the literal ``None-<key>`` (round 2, Q4)."""
    printer.info = payloads.connection_info(usn=None)
    entry = await setup_entry(hass, lan_entry(unique_id=f"lan-{payloads.HOST}"))
    registry = er.async_get(hass)
    assert registry.async_get_entity_id("sensor", DOMAIN, "None-curr_nozzle_temp")
    assert registry.async_get_entity_id("light", DOMAIN, "None-printer_light")
    ours = er.async_entries_for_config_entry(registry, entry.entry_id)
    assert ours
    assert all(e.unique_id.startswith("None-") for e in ours)
    assert not any(payloads.DEVICE_ID.upper() in e.unique_id for e in ours)
    device = find_device(hass, f"None-{PID}")
    assert device is not None
    assert device.connections == set()
    assert entry.state is ConfigEntryState.LOADED
