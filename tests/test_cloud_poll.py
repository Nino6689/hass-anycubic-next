"""Cloud polling: cadence, back-off and never-flap (BEHAVIOUR §5.1, §5.5)."""

from __future__ import annotations

from typing import Any

from anycubic_cloud_client import (
    AuthMode,
    CredentialsRejectedError,
    PrinterRemovedError,
    ServiceUnavailableError,
    TokenState,
)
from homeassistant.config_entries import SOURCE_REAUTH
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from . import cloud_payloads as cp
from .cloud_fakes import FakeCloud
from .conftest import MockPrinter, account_entry, setup_entry

NOZZLE = "sensor.kobra_s1_cloud_nozzle_temperature"
RATE_LIMITED = "请求过于频繁。请稍后再试"


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
async def loaded(hass: HomeAssistant, cloud: FakeCloud) -> MockConfigEntry:
    return await setup_entry(hass, account_entry())


@pytest.fixture
def clock(loaded: MockConfigEntry) -> Clock:
    clock = Clock()
    account = loaded.runtime_data.cloud
    account._clock = clock
    account.mqtt._clock = clock
    account._next_due = clock.now + 60
    return clock


async def _refresh(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    await entry.runtime_data.primary.async_refresh()
    await hass.async_block_till_done()


def _reauth(hass: HomeAssistant) -> list[Any]:
    return [
        f
        for f in hass.config_entries.flow.async_progress()
        if f["context"].get("source") == SOURCE_REAUTH
    ]


async def test_polls_at_most_every_minute(
    hass: HomeAssistant, loaded: MockConfigEntry, cloud: FakeCloud, clock: Clock
) -> None:
    reads = cloud.printer_reads
    clock.now += 15
    await _refresh(hass, loaded)
    assert cloud.printer_reads == reads  # the 15 s tick in between
    clock.now += 50
    cloud.printers[cp.PRINTER_ID]["parameter"]["curr_nozzle_temp"] = 199
    await _refresh(hass, loaded)
    assert cloud.printer_reads == reads + 1
    assert hass.states.get(NOZZLE).state == "199.0"


async def test_control_forces_a_poll_then_ten_seconds(
    hass: HomeAssistant, loaded: MockConfigEntry, cloud: FakeCloud, clock: Clock
) -> None:
    reads = cloud.printer_reads
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": "number.kobra_s1_cloud_set_fan_speed", "value": 20},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert cloud.orders[-1] == (
        "set_fan_speed",
        (cp.PRINTER_ID,),
        {"fan_speed_pct": 20},
    )
    assert cloud.printer_reads == reads + 1
    assert loaded.runtime_data.cloud._next_due == clock.now + 10


async def test_outage_backs_off_and_never_flaps(
    hass: HomeAssistant,
    loaded: MockConfigEntry,
    cloud: FakeCloud,
    clock: Clock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    account = loaded.runtime_data.cloud
    checks = cloud.checks
    cloud.check_errors = [ServiceUnavailableError("down")] * 3
    for failure in range(3):
        clock.now += 61
        await _refresh(hass, loaded)
        assert hass.states.get(NOZZLE).state == STATE_UNAVAILABLE
        # Between polls the failure stands: no stale values (§5.5).
        clock.now += 15
        await _refresh(hass, loaded)
        assert hass.states.get(NOZZLE).state == STATE_UNAVAILABLE
        if failure < 2:
            assert account._next_due == clock.now - 15 + 60
    # After 3 failures polling pauses for about 5 minutes.
    assert account._next_due == clock.now - 15 + 300
    clock.now += 100
    await _refresh(hass, loaded)
    assert cloud.checks == checks + 3  # the paused poll is skipped
    # A pushed report does not bring stale entities back while polls fail.
    account.mqtt.possible  # noqa: B018 - the link is not started in mode 1
    clock.now += 300
    await _refresh(hass, loaded)
    assert hass.states.get(NOZZLE).state == "31.0"
    ours = [r for r in caplog.records if r.name.endswith("anycubic_cloud.cloud")]
    outage = [r for r in ours if "not answering" in r.getMessage()]
    recovery = [r for r in ours if "answering again" in r.getMessage()]
    assert len(outage) == 1
    assert outage[0].levelname == "WARNING"
    assert len(recovery) == 1
    assert recovery[0].levelname == "INFO"
    assert not _reauth(hass)


async def test_rate_limit_during_a_poll_is_transient(
    hass: HomeAssistant, loaded: MockConfigEntry, cloud: FakeCloud, clock: Clock
) -> None:
    cloud.check_errors = [
        CredentialsRejectedError("slow down", server_message=RATE_LIMITED)
    ]
    clock.now += 61
    await _refresh(hass, loaded)
    assert hass.states.get(NOZZLE).state == STATE_UNAVAILABLE
    assert not _reauth(hass)


async def test_rejected_token_during_a_poll_asks_for_reauth(
    hass: HomeAssistant, loaded: MockConfigEntry, cloud: FakeCloud, clock: Clock
) -> None:
    cloud.check_errors = [CredentialsRejectedError("revoked")]
    clock.now += 61
    await _refresh(hass, loaded)
    assert len(_reauth(hass)) == 1
    # Until the new token arrives, no stale values between polls either.
    clock.now += 15
    await _refresh(hass, loaded)
    assert hass.states.get(NOZZLE).state == STATE_UNAVAILABLE


async def test_unexpected_error_during_a_poll_is_not_reauth(
    hass: HomeAssistant, loaded: MockConfigEntry, cloud: FakeCloud, clock: Clock
) -> None:
    cloud.check_errors = [RuntimeError("bug")]
    clock.now += 61
    await _refresh(hass, loaded)
    assert hass.states.get(NOZZLE).state == STATE_UNAVAILABLE
    assert not _reauth(hass)


async def test_printer_removed_during_a_poll(
    hass: HomeAssistant, cloud: FakeCloud
) -> None:
    """1007 makes that printer unavailable; never re-authentication (B8)."""
    cloud.printers[7] = cp.detail(7, name="Second")
    entry = account_entry()
    entry = await setup_entry(
        hass, account_entry(data={**entry.data, "printer_ids": [cp.PRINTER_ID, 7]})
    )
    clock = Clock()
    entry.runtime_data.cloud._clock = clock
    cloud.printer_errors[7] = PrinterRemovedError("deleted")
    entry.runtime_data.cloud._next_due = None
    await entry.runtime_data.coordinators[7].async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get("sensor.second_current_status").state == STATE_UNAVAILABLE
    assert hass.states.get(NOZZLE).state == "31.0"
    # Polled by the other printer's refresh, too.
    clock.now += 61
    await entry.runtime_data.coordinators[cp.PRINTER_ID].async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get("sensor.second_current_status").state == STATE_UNAVAILABLE
    assert not _reauth(hass)


async def test_other_printers_follow_a_failed_poll(
    hass: HomeAssistant, cloud: FakeCloud
) -> None:
    cloud.printers[7] = cp.detail(7, name="Second")
    entry = account_entry()
    entry = await setup_entry(
        hass, account_entry(data={**entry.data, "printer_ids": [cp.PRINTER_ID, 7]})
    )
    cloud.check_errors = [ServiceUnavailableError("down")]
    entry.runtime_data.cloud._next_due = None
    await entry.runtime_data.coordinators[cp.PRINTER_ID].async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get("sensor.second_current_status").state == STATE_UNAVAILABLE


async def test_changed_tokens_are_saved(
    hass: HomeAssistant,
    loaded: MockConfigEntry,
    cloud: FakeCloud,
    clock: Clock,
    hass_storage: dict[str, Any],
) -> None:
    """Rule 5: saved again whenever a poll changed the tokens."""
    cloud.exchanged_tokens = TokenState(
        auth_token="re-exchanged", auth_mode=AuthMode.SLICER
    )
    clock.now += 61
    await _refresh(hass, loaded)
    stored = hass_storage[f"anycubic_cloud.{loaded.entry_id}"]["data"]
    assert stored["auth_token"] == "re-exchanged"


async def test_hybrid_entry_does_not_poll_while_lan_is_up(
    hass: HomeAssistant, cloud: FakeCloud, printer: MockPrinter
) -> None:
    """§5.4: while LAN is connected there is no cloud poll at all."""
    entry = await setup_entry(hass, account_entry(lan=True))
    coordinator = entry.runtime_data.primary
    assert coordinator.lan_connected
    checks = cloud.checks
    entry.runtime_data.cloud._next_due = None
    await coordinator.async_refresh()
    assert cloud.checks == checks
    # LAN lost: the next refresh reads the cloud.
    printer.client.lose()
    printer.handshake_error = __import__("anycubic_lan").AnycubicLanError("gone")
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert cloud.checks == checks + 1
    assert coordinator.printer.source == "cloud"
    assert coordinator.last_update_success
