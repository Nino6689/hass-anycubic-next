"""The ledger over the cloud (BEHAVIOUR §3.1, §3.5, G1), the MQTT check at
start-up, and the drying options of a cloud printer without an ACE."""

from __future__ import annotations

import json
from typing import Any

from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import CoreState, HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.anycubic_cloud.filament import grams_from_length

from . import cloud_payloads as cp
from .cloud_fakes import FakeCloud
from .conftest import account_entry, setup_entry


def _slice(*paints: tuple[int, float]) -> str:
    return json.dumps(
        {
            "paint_infos": [
                {"paint_index": index, "material_type": "PLA", "filament_used": grams}
                for index, grams in paints
            ]
        }
    )


async def _finish(hass: HomeAssistant, entry: Any, cloud: FakeCloud) -> None:
    cloud.jobs[0]["print_status"] = 2
    entry.runtime_data.cloud._next_due = None
    await entry.runtime_data.primary.async_refresh()
    await hass.async_block_till_done()


async def test_single_colour_job_charged_to_the_feeding_slot(
    hass: HomeAssistant, cloud: FakeCloud
) -> None:
    entry = await setup_entry(hass, account_entry())
    await _finish(hass, entry, cloud)
    ledger = entry.runtime_data.ledger
    used = ledger.data["printers"][str(cp.PRINTER_ID)]["slots"]["1"]["filament_used_g"]
    assert used == round(grams_from_length(31783, "PLA"), 2)
    assert ledger.last_job_filament(cp.PRINTER_ID) == round(used, 1)
    assert ledger.history_estimate("benchy_PLA_0.2") == round(used, 1)
    # Charged once only.
    await _finish(hass, entry, cloud)
    assert (
        ledger.data["printers"][str(cp.PRINTER_ID)]["slots"]["1"]["filament_used_g"]
        == used
    )


async def test_multi_colour_job_split_between_slots(
    hass: HomeAssistant, cloud: FakeCloud
) -> None:
    cloud.jobs = [cp.job(slice_param=_slice((0, 30.0), (2, 10.0), (2, -1)))]
    entry = await setup_entry(hass, account_entry())
    ledger = entry.runtime_data.ledger
    ledger.set_slot_price(cp.PRINTER_ID, 2, 20.0)  # slot index 1
    await _finish(hass, entry, cloud)
    slots = ledger.data["printers"][str(cp.PRINTER_ID)]["slots"]
    assert slots["0"]["filament_used_g"] == round(
        grams_from_length(31783 * 0.75, "PLA"), 2
    )
    assert slots["2"]["filament_used_g"] == round(
        grams_from_length(31783 * 0.25, "PLA"), 2
    )
    assert slots.get("1", {}).get("filament_used_g", 0.0) == 0.0
    # Slot 1 fed nothing, so its price counts for nothing.
    assert ledger.last_job_cost(cp.PRINTER_ID) is None


async def test_mqtt_waits_for_home_assistant_to_start(
    hass: HomeAssistant, cloud: FakeCloud
) -> None:
    hass.set_state(CoreState.not_running)
    entry = account_entry()
    await setup_entry(
        hass, account_entry(options={**entry.options, "mqtt_connect_mode": 4})
    )
    assert not cloud.links
    hass.set_state(CoreState.running)
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STARTED)
    await hass.async_block_till_done()
    assert cloud.link.connects == 1


async def test_drying_options_hidden_without_an_ace(
    hass: HomeAssistant, cloud: FakeCloud
) -> None:
    cloud.printers[cp.PRINTER_ID]["multi_color_box"] = []
    cloud.printers[cp.PRINTER_ID]["type_function_ids"] = [2]
    entry = await setup_entry(hass, account_entry())
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.MENU
    assert "drying" not in result["menu_options"]
