"""Upgrade of a 2.x cloud entry (COMPAT §1-§3, §6; CLOUD.md §3 test 1).

The entry, its registry and its stores are seeded exactly as a live 2.x
install holds them: every entity of COMPAT §3.1 under its unique id (the
three 2.x disabled stay disabled), both devices, the 2.x token store with
Anycubic's app keys, and the filament ledger. 3.0 must reattach every
entity - the 16 cloud-only ones the LAN build did not provide included -
keep the devices, use and keep the token store, and leave the ledger alone.
"""

from __future__ import annotations

import copy
from pathlib import Path
import re
from typing import Any

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from custom_components.anycubic_cloud.const import DOMAIN

from . import cloud_payloads as cp, payloads
from .cloud_fakes import FakeCloud
from .conftest import account_entry, find_device

COMPAT = Path(__file__).parent.parent / "docs" / "COMPAT.md"
PID = str(cp.PRINTER_ID)

# The 16 entities ACCEPTANCE.md's upgrade test U lists as "not provided" on
# LAN: provided again from the cloud (CLOUD.md §2).
CLOUD_ONLY = {
    "mqtt_connection_active": "off",
    "refresh_mqtt_connection": "unknown",
    "manual_mqtt_connection_enabled": "off",
    "file_list_cloud": STATE_UNAVAILABLE,
    "file_list_local": STATE_UNAVAILABLE,
    "file_list_udisk": STATE_UNAVAILABLE,
    "cloud_camera": "idle",
    "job_z_thick": "0.2",
    "material_used_total": "18.17",
    "print_time_total_hrs": "798",
    "print_count_total": "174",
    "multi_color_box_fw_version": "off",
}

LEDGER = {
    "printers": {
        PID: {
            "slots": {
                "0": {
                    "spool_weight_g": 1000.0,
                    "filament_used_g": 250.5,
                    "spool_signature": "PLA|#FFFFFF|SKU0",
                    "spool_price_per_kg": 20.0,
                }
            },
            "last_job_id": 111,
            "totals": {
                "material_totals": {"PLA": 1234.5},
                "last_job_grams": 50.3,
                "last_job_cost": 1.01,
                "cost_total": 24.69,
            },
            "nozzle": {"nozzle_total_g": 1500.2, "nozzle_abrasive_g": 250.0},
            "axis_step": 15,
        }
    },
    "spools": {"PETG|#00FF00|": {"filament_used_g": 100.0, "spool_weight_g": 1000.0}},
    "jobs": {"Wolf_plate(01)_PLA_0.2_45s": [50.34, 49.49, 49.49]},
}


def compat_rows() -> list[tuple[str, str, bool]]:
    """(key, platform, enabled by default) of every COMPAT §3.1 row."""
    text = COMPAT.read_text()
    section = text[text.index("### 3.1") : text.index("### 3.2")]
    rows = []
    for line in section.splitlines():
        match = re.match(r"\| `([a-z0-9_]+)` \| (\w+) \|(.*)", line)
        if match:
            cells = [c.strip() for c in match.group(3).split("|")]
            rows.append((match.group(1), match.group(2), cells[6] == "yes"))
    return rows


def _seed_store(hass_storage: dict[str, Any], key: str, data: Any) -> None:
    hass_storage[key] = {
        "version": 1,
        "minor_version": 1,
        "key": key,
        "data": copy.deepcopy(data),
    }


async def test_2x_cloud_entry_upgrade(
    hass: HomeAssistant, cloud: FakeCloud, hass_storage: dict[str, Any]
) -> None:
    token = cp.slicer_token()
    entry = account_entry(
        token=token,
        options={
            "mqtt_connect_mode": 1,
            "drying_preset_duration_1": 240,
            "drying_preset_temperature_1": 55,
            "card_config": {"vertical": False, "scaleFactor": 1},
            "debug": False,
        },
    )
    entry.add_to_hass(hass)
    data, options = copy.deepcopy(dict(entry.data)), copy.deepcopy(dict(entry.options))
    # The 2.x token store: Anycubic's app keys beside the session.
    _seed_store(
        hass_storage,
        f"anycubic_cloud.{entry.entry_id}",
        {
            "app_client_id": "2x-client-id",
            "app_id": "2x-app-id",
            "app_version": "V3.0.0",
            "app_secret": "2x-app-secret",
            "auth_token": "2x-user-token",
            "device_id": None,
            "auth_access_token": token,
            "auth_mode": 3,
        },
    )
    ledger_key = f"anycubic_cloud.filament.{entry.entry_id}"
    _seed_store(hass_storage, ledger_key, LEDGER)

    devices = dr.async_get(hass)
    printer_device = devices.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, f"{cp.USER_ID}-{PID}")},
        manufacturer="Anycubic",
        name="Kobra S1 Cloud",
        model="Anycubic Kobra S1",
    )
    ace_device = devices.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, f"{cp.USER_ID}-{PID}-ace0")},
        manufacturer="Anycubic",
        name="Kobra S1 Cloud ACE Pro",
        model="ACE Pro",
    )
    registry = er.async_get(hass)
    seeded: dict[str, tuple[str, bool]] = {}
    rows = compat_rows()
    assert len(rows) > 125
    for key, platform, enabled in rows:
        item = registry.async_get_or_create(
            platform,
            DOMAIN,
            f"{payloads.MAC_UID}-{key}",
            config_entry=entry,
            suggested_object_id=f"2x_{key}",
            disabled_by=None if enabled else er.RegistryEntryDisabler.INTEGRATION,
        )
        seeded[key] = (item.entity_id, enabled)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert entry.state is ConfigEntryState.LOADED

    # The entry is untouched.
    assert dict(entry.data) == data
    assert dict(entry.options) == options
    assert entry.version == 1
    assert entry.minor_version == 1

    # No entity id changes, and every seeded entity is provided again.
    ours = er.async_entries_for_config_entry(registry, entry.entry_id)
    by_unique_id = {e.unique_id: e for e in ours}
    for key, (entity_id, enabled) in seeded.items():
        item = by_unique_id[f"{payloads.MAC_UID}-{key}"]
        assert item.entity_id == entity_id, key
        if not enabled:
            assert item.disabled_by is er.RegistryEntryDisabler.INTEGRATION, key
            continue
        state = hass.states.get(entity_id)
        assert state is not None, key
        assert not state.attributes.get("restored"), f"{key} is not provided"
    # The cloud-only entities come back with values.
    for key, expected in CLOUD_ONLY.items():
        assert hass.states.get(seeded[key][0]).state == expected, key
    preview = hass.states.get(seeded["job_image_url"][0])
    assert preview.state != STATE_UNAVAILABLE
    # 3.0 adds only what COMPAT names for this printer: the preset button.
    extra = sorted(
        e.unique_id.removeprefix(f"{payloads.MAC_UID}-")
        for e in ours
        if e.unique_id.removeprefix(f"{payloads.MAC_UID}-") not in seeded
    )
    assert extra == ["drying_start_preset_1"]

    # Both devices are kept, with their identifiers.
    printer = find_device(hass, f"{cp.USER_ID}-{PID}")
    assert printer is not None
    assert printer.id == printer_device.id
    assert printer.sw_version == "2.7.2.7"
    ace = find_device(hass, f"{cp.USER_ID}-{PID}-ace0")
    assert ace is not None
    assert ace.id == ace_device.id
    assert ace.via_device_id == printer.id
    assert ace.model == "ACE Pro"

    # The token store was used (no fresh exchange) and is kept.
    assert cloud.clients[0].user_token == "2x-user-token"
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    stored = hass_storage[f"anycubic_cloud.{entry.entry_id}"]["data"]
    assert stored["auth_token"] == "2x-user-token"
    assert stored["auth_access_token"] == token
    assert stored["auth_mode"] == 3
    assert not any(key.startswith("app_") for key in stored)

    # The ledger survives: nothing is charged again, figures unchanged.
    ledger = hass_storage[ledger_key]["data"]
    assert ledger["printers"][PID]["last_job_id"] == 111
    assert ledger["printers"][PID]["totals"] == LEDGER["printers"][PID]["totals"]
    assert ledger["printers"][PID]["nozzle"] == LEDGER["printers"][PID]["nozzle"]
    assert ledger["jobs"] == LEDGER["jobs"]
    assert ledger["spools"]["PETG|#00FF00|"] == LEDGER["spools"]["PETG|#00FF00|"]
