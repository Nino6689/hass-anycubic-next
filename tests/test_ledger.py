"""The filament ledger (BEHAVIOUR §3.1-§3.10, G1, DECISIONS V3)."""

from __future__ import annotations

import json
from typing import Any

from anycubic_lan import PrinterState, parse_message
from homeassistant.core import HomeAssistant
import pytest

from custom_components.anycubic_cloud.filament import grams_from_length
from custom_components.anycubic_cloud.ledger import FilamentLedger
from custom_components.anycubic_cloud.model import Printer, PrinterIdentity

from . import payloads

PID = 1234


def make_printer() -> Printer:
    return Printer(
        identity=PrinterIdentity(
            printer_id=PID,
            mac=payloads.MAC_UID,
            name="Kobra",
            model_name="Anycubic Kobra S1",
            model_id=20025,
            material_type="Filament",
            host=payloads.HOST,
        ),
        info_seen=True,
    )


def feed(printer: Printer, *items: dict[str, Any]) -> None:
    state = printer.state
    for item in items:
        report = parse_message(json.dumps(item).encode())
        assert report is not None
        state = state.apply(report)
    printer.state = state


@pytest.fixture
async def ledger(hass: HomeAssistant) -> FilamentLedger:
    ledger = FilamentLedger(hass, "entry")
    await ledger.async_load()
    return ledger


def loaded_box(slot_index: int = 0, **changes: Any) -> dict[str, Any]:
    return payloads.box(0, loaded_slot=slot_index, **changes)


async def test_job_charged_when_it_ends_on_lan(ledger: FilamentLedger) -> None:
    """G1: LAN clears the job when idle; the last length seen is charged."""
    printer = make_printer()
    ledger.set_slot_price(PID, 1, 20.0)
    feed(printer, payloads.ace(loaded_box(0)))
    ledger.update(printer)
    feed(printer, payloads.info(project=payloads.job(progress=10, supplies_usage=1000)))
    ledger.update(printer)
    assert ledger.feeding_slot(PID) == 0
    feed(
        printer, payloads.info(project=payloads.job(progress=90, supplies_usage=30000))
    )
    ledger.update(printer)
    # The ACE stops reporting a loaded slot as the job ends.
    feed(printer, payloads.ace(payloads.box(0)), payloads.info(project=None))
    ledger.update(printer)

    grams = grams_from_length(30000, "PLA")
    assert ledger.last_job_filament(PID) == round(grams, 1)
    assert ledger.slot_remaining(printer, 1) == round(1000 - round(grams, 2), 1)
    assert ledger.last_job_cost(PID) == round(grams / 1000 * 20, 2)
    assert ledger.cost_total(PID) == round(grams / 1000 * 20, 2)
    assert ledger.material_totals(PID) == {"PLA": round(grams, 2)}
    assert ledger.nozzle_total(PID) == round(grams, 1)
    assert ledger.nozzle_abrasive(PID) == 0
    assert ledger.feeding_slot(PID) is None
    assert ledger.data["jobs"] == {"Wolf_plate(01)_PLA_0.2_45s": [round(grams, 1)]}
    assert ledger.data["printers"][str(PID)]["last_job_id"] == 614707220

    # Not charged twice.
    ledger.update(printer)
    assert ledger.last_job_filament(PID) == round(grams, 1)


async def test_completed_job_charged_once(ledger: FilamentLedger) -> None:
    printer = make_printer()
    feed(
        printer,
        payloads.ace(
            loaded_box(
                1,
                slots=[
                    payloads.slot(0),
                    payloads.slot(1, type="PACF"),
                    payloads.slot(2),
                    payloads.slot(3),
                ],
            )
        ),
    )
    feed(printer, payloads.info(project=payloads.job(supplies_usage=2000)))
    ledger.update(printer)
    # Complete, with a slightly larger final figure.
    feed(
        printer,
        payloads.info(
            project=payloads.job(print_status=2, supplies_usage=2100, state="finished")
        ),
    )
    ledger.update(printer)
    grams = grams_from_length(2100, "PACF")
    assert ledger.last_job_filament(PID) == round(grams, 1)
    assert ledger.last_job_cost(PID) is None  # unpriced is never free
    assert ledger.nozzle_abrasive(PID) == round(grams, 1)
    feed(printer, payloads.info(project=None))
    ledger.update(printer)
    assert ledger.nozzle_total(PID) == round(grams, 1)


async def test_job_finished_before_setup_is_not_charged(
    ledger: FilamentLedger,
) -> None:
    """DECISIONS V3: accounting starts with the first job seen running."""
    printer = make_printer()
    feed(
        printer,
        payloads.ace(loaded_box(0)),
        payloads.info(project=payloads.job(print_status=2, state="finished")),
    )
    ledger.update(printer)
    feed(printer, payloads.info(project=None))
    ledger.update(printer)
    assert ledger.last_job_filament(PID) is None
    assert ledger.cost_total(PID) == 0


async def test_unattributable_job(ledger: FilamentLedger) -> None:
    """No feeding slot: nothing charged, but the job id is stored."""
    printer = make_printer()
    feed(printer, payloads.info(project=payloads.job()))
    ledger.update(printer)
    feed(printer, payloads.info(project=None))
    ledger.update(printer)
    assert ledger.last_job_filament(PID) is None
    assert ledger.data["printers"][str(PID)]["last_job_id"] == 614707220


async def test_job_without_length_is_not_charged(ledger: FilamentLedger) -> None:
    printer = make_printer()
    feed(printer, payloads.ace(loaded_box(0)))
    feed(printer, payloads.info(project=payloads.job(supplies_usage=0)))
    ledger.update(printer)
    feed(printer, payloads.info(project=None))
    ledger.update(printer)
    assert "last_job_id" not in ledger.data["printers"].get(str(PID), {})


async def test_new_task_replaces_running_job(ledger: FilamentLedger) -> None:
    printer = make_printer()
    feed(printer, payloads.ace(loaded_box(0)))
    feed(printer, payloads.info(project=payloads.job(task_id=1, supplies_usage=500)))
    ledger.update(printer)
    feed(printer, payloads.info(project=payloads.job(task_id=2, supplies_usage=100)))
    ledger.update(printer)
    feed(printer, payloads.info(project=payloads.job(task_id=2, supplies_usage=50)))
    ledger.update(printer)
    feed(printer, payloads.info(project=None))
    ledger.update(printer)
    assert ledger.last_job_filament(PID) == round(grams_from_length(100, "PLA"), 1)


async def test_reel_memory(ledger: FilamentLedger) -> None:
    """Swapped reels find their own history; new reels start fresh (§3.3)."""
    printer = make_printer()
    white = payloads.slot(0)
    black = payloads.slot(1)
    feed(printer, payloads.ace(payloads.box(0, slots=[white, black])))
    ledger.update(printer)
    ledger.set_slot_weight(PID, 1, 800)
    ledger._slot(PID, 0)["filament_used_g"] = 100.0
    ledger.set_slot_price(PID, 2, 30)
    ledger.update(printer)  # banks both reels

    # Swap them.
    feed(
        printer,
        payloads.ace(
            payloads.box(0, slots=[{**black, "index": 0}, {**white, "index": 1}])
        ),
    )
    ledger.update(printer)
    assert ledger.slot_weight(PID, 2) == 800
    assert ledger.slot_remaining(printer, 2) == 700
    assert ledger.slot_price(PID, 1) == 30
    assert ledger.slot_remaining(printer, 1) == 1000

    # A never-seen reel in slot 1 starts at 1000 g, unpriced.
    feed(
        printer,
        payloads.ace(
            payloads.box(0, slots=[payloads.slot(0, type="PETG", color=[1, 2, 3])])
        ),
    )
    ledger.update(printer)
    assert ledger.slot_weight(PID, 1) == 1000
    assert ledger.slot_price(PID, 1) == 0
    assert ledger.spool_inventory_count() == 2

    # Empty slots keep reporting their reel: stored figures stay.
    feed(
        printer,
        payloads.ace(
            payloads.box(
                0, slots=[payloads.slot(0, type="PETG", color=[1, 2, 3], edit_status=2)]
            )
        ),
    )
    ledger.update(printer)
    assert ledger.slot_remaining(printer, 1) is None
    assert ledger.slot_remaining_percent(printer, 1) is None


async def test_reset_slot_forgets_the_reel(ledger: FilamentLedger) -> None:
    printer = make_printer()
    feed(printer, payloads.ace(payloads.box(0)))
    ledger.update(printer)
    ledger._slot(PID, 0)["filament_used_g"] = 300.0
    ledger.update(printer)
    assert "PLA|#FFFFFF|SKU0" in ledger.data["spools"]
    ledger.reset_slot(PID, 1)
    assert ledger.slot_remaining(printer, 1) == 1000
    assert "PLA|#FFFFFF|SKU0" not in ledger.data["spools"]
    ledger.update(printer)
    assert ledger.data["spools"]["PLA|#FFFFFF|SKU0"]["filament_used_g"] == 0


async def test_spool_inventory(ledger: FilamentLedger) -> None:
    ledger.data["spools"].update(
        {
            "PLA|#FFFFFF|": {"filament_used_g": 900.0, "spool_weight_g": 1000.0},
            "PETG||X": {
                "filament_used_g": 0.0,
                "spool_weight_g": 1000.0,
                "spool_price_per_kg": 20.0,
            },
            "broken": "not a dict",
        }
    )
    spools = [spool.as_dict() for spool in ledger.spool_inventory()]
    assert spools == [
        {
            "material": "PLA",
            "color_hex": "#FFFFFF",
            "sku": None,
            "remaining_g": 100.0,
            "remaining_percent": 10.0,
            "spool_price_per_kg": None,
        },
        {
            "material": "PETG",
            "color_hex": None,
            "sku": "X",
            "remaining_g": 1000.0,
            "remaining_percent": 100.0,
            "spool_price_per_kg": 20.0,
        },
    ]
    assert ledger.spool_inventory_remaining() == 1100.0
    assert ledger.spool_inventory_count() == 3


async def test_forecast_two_observations(ledger: FilamentLedger) -> None:
    """Rate between an anchor ≥ 3 % and a point 5 points later (§3.6, B18)."""
    printer = make_printer()
    feed(printer, payloads.ace(loaded_box(0)))
    ledger.update(printer)

    def at(progress: int, length: int) -> None:
        feed(
            printer,
            payloads.info(
                project=payloads.job(
                    progress=progress, supplies_usage=length, filename="new.gcode"
                )
            ),
        )

    at(2, 3000)  # purge still running: no anchor
    assert ledger.forecast(printer) is None
    at(4, 4000)  # sets the anchor, no answer
    assert ledger.forecast(printer) is None
    at(8, 5000)  # under 5 points past the anchor
    assert ledger.forecast(printer) is None
    at(14, 7000)
    forecast = ledger.forecast(printer)
    assert forecast is not None
    rate = grams_from_length(3000, "PLA") / 10
    expected = round(grams_from_length(7000, "PLA") + rate * 86, 1)
    assert forecast.required == expected
    assert forecast.source == "extrapolated"
    assert forecast.shortfall == 0
    assert forecast.runs_out_at == 100
    assert not forecast.insufficient
    assert forecast.cost is None

    # A short reel: shortfall and the run-out point.
    ledger.set_slot_weight(PID, 1, 50)
    ledger.set_slot_price(PID, 1, 25)
    forecast = ledger.forecast(printer)
    assert forecast is not None
    assert forecast.insufficient
    assert forecast.shortfall == round(expected - 50, 1)
    assert forecast.runs_out_at == round(50 / expected * 100, 1)
    assert forecast.cost == round(expected / 1000 * 25, 2)


async def test_forecast_edge_cases(ledger: FilamentLedger) -> None:
    printer = make_printer()
    assert ledger.forecast(printer) is None  # no job
    feed(printer, payloads.info(project=payloads.job(progress=50)))
    assert ledger.forecast(printer) is None  # no slot
    feed(printer, payloads.ace(loaded_box(0)))
    feed(printer, payloads.info(project=payloads.job(progress=0, supplies_usage=10)))
    assert ledger.forecast(printer) is None
    feed(printer, payloads.info(project=payloads.job(progress=50, supplies_usage=0)))
    assert ledger.forecast(printer) is None
    # Length going backwards after the anchor gives no answer.
    feed(printer, payloads.info(project=payloads.job(progress=10, supplies_usage=900)))
    assert ledger.forecast(printer) is None
    feed(printer, payloads.info(project=payloads.job(progress=20, supplies_usage=800)))
    assert ledger.forecast(printer) is None


async def test_forecast_from_history(ledger: FilamentLedger) -> None:
    printer = make_printer()
    ledger.data["jobs"]["Wolf_plate(01)_PLA_0.2_45s"] = [50.34, 49.49, 49.49, -1]
    feed(printer, payloads.ace(loaded_box(2)))
    feed(printer, payloads.info(project=payloads.job(progress=1)))
    forecast = ledger.forecast(printer)
    assert forecast is not None
    assert forecast.required == 49.8
    assert forecast.source == "history"
    ledger.data["jobs"]["Wolf_plate(01)_PLA_0.2_45s"] = "junk"
    assert ledger.history_estimate("Wolf_plate(01)_PLA_0.2_45s") is None
    ledger.data["jobs"]["Wolf_plate(01)_PLA_0.2_45s"] = [0]
    assert ledger.history_estimate("Wolf_plate(01)_PLA_0.2_45s") is None


async def test_history_keeps_five_samples(ledger: FilamentLedger) -> None:
    printer = make_printer()
    feed(printer, payloads.ace(loaded_box(0)))
    for task in range(7):
        feed(
            printer,
            payloads.info(
                project=payloads.job(task_id=task + 1, supplies_usage=1000 * (task + 1))
            ),
        )
        ledger.update(printer)
        feed(printer, payloads.info(project=None))
        ledger.update(printer)
    samples = ledger.data["jobs"]["Wolf_plate(01)_PLA_0.2_45s"]
    assert len(samples) == 5
    assert samples[-1] == round(grams_from_length(7000, "PLA"), 1)


async def test_settings(ledger: FilamentLedger) -> None:
    assert ledger.axis_step(PID) == 1
    ledger.set_axis_step(PID, 50)
    assert ledger.axis_step(PID) == 50
    ledger.data["printers"][str(PID)]["axis_step"] = 7
    assert ledger.axis_step(PID) == 1
    assert ledger.drying_setting(PID, "temperature") is None
    ledger.set_drying_setting(PID, "temperature", 60)
    assert ledger.drying_setting(PID, "temperature") == 60
    ledger.reset_nozzle(PID)
    assert ledger.nozzle_total(PID) == 0
    assert ledger.nozzle_wear(PID) == 0


async def test_malformed_ledger_is_tolerated(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    hass_storage["anycubic_cloud.filament.bad"] = {
        "version": 1,
        "key": "anycubic_cloud.filament.bad",
        "data": {
            "printers": {
                str(PID): {
                    "slots": "oops",
                    "totals": [],
                    "nozzle": None,
                    "drying_settings": [],
                }
            },
            "spools": [],
        },
    }
    ledger = FilamentLedger(hass, "bad")
    await ledger.async_load()
    printer = make_printer()
    assert ledger.cost_total(PID) == 0
    assert ledger.material_totals(PID) == {}
    assert ledger.nozzle_wear(PID) == 0
    assert ledger.drying_setting(PID, "duration") is None
    assert ledger.spool_inventory() == []
    feed(printer, payloads.ace(payloads.box(0)))
    ledger.update(printer)
    assert ledger.slot_remaining(printer, 1) == 1000


async def test_update_never_raises(
    ledger: FilamentLedger, caplog: pytest.LogCaptureFixture
) -> None:
    printer = make_printer()
    printer.state = "not a state"  # type: ignore[assignment]
    ledger.update(printer)
    assert "Filament ledger update failed" in caplog.text
    printer.state = PrinterState()
