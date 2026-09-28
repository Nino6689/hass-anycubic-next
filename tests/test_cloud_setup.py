"""Cloud entries: setup, the token store and re-authentication.

BEHAVIOUR §5.6-§5.7 and the seven rules of PROTOCOL A §5.3. Only a
credentials verdict leads to re-authentication; a rate limit, an outage, an
unreadable answer or a printer removed from the account (1007) never does.
"""

from __future__ import annotations

from typing import Any

from anycubic_cloud_client import (
    AuthMode,
    CredentialsRejectedError,
    PrinterRemovedError,
    ServiceUnavailableError,
    TokenState,
    UnexpectedResponseError,
)
from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, issue_registry as ir
import pytest

from custom_components.anycubic_cloud.cloud import async_hand_off_sign_in
from custom_components.anycubic_cloud.const import DOMAIN

from . import cloud_payloads as cp, payloads
from .cloud_fakes import FakeCloud
from .conftest import MockPrinter, account_entry, find_device, setup_entry

RATE_LIMITED = "请求过于频繁。请稍后再试"


def _store(hass_storage: dict[str, Any], entry_id: str) -> dict[str, Any] | None:
    stored = hass_storage.get(f"anycubic_cloud.{entry_id}")
    return stored["data"] if stored else None


def _seed(hass_storage: dict[str, Any], key: str, data: dict[str, Any]) -> None:
    hass_storage[key] = {"version": 1, "minor_version": 1, "key": key, "data": data}


def _reauth_flows(hass: HomeAssistant) -> list[Any]:
    return [
        flow
        for flow in hass.config_entries.flow.async_progress()
        if flow["context"].get("source") == SOURCE_REAUTH
    ]


async def test_setup_saves_the_token_store(
    hass: HomeAssistant, cloud: FakeCloud, hass_storage: dict[str, Any]
) -> None:
    """Rule 5: saved after every successful setup, with no app credentials."""
    entry = await setup_entry(hass, account_entry())
    assert entry.state is ConfigEntryState.LOADED
    stored = _store(hass_storage, entry.entry_id)
    assert stored is not None
    assert set(stored) == {"auth_token", "auth_access_token", "device_id", "auth_mode"}
    assert stored["auth_mode"] == 3
    assert cloud.client.store is None  # first setup: nothing stored yet
    assert cloud.client.auth_mode is AuthMode.SLICER


async def test_stored_session_is_used(
    hass: HomeAssistant, cloud: FakeCloud, hass_storage: dict[str, Any]
) -> None:
    entry = account_entry()
    token = entry.data["user_token"]
    _seed(
        hass_storage,
        f"anycubic_cloud.{entry.entry_id}",
        {
            "auth_token": "stored-user-token",
            "auth_access_token": token,
            "device_id": None,
            "auth_mode": 3,
            "app_id": "ignored",
        },
    )
    await setup_entry(hass, entry)
    assert entry.state is ConfigEntryState.LOADED
    assert cloud.clients[0].store is not None
    assert cloud.clients[0].user_token == "stored-user-token"


async def test_refused_store_retries_from_the_entry(
    hass: HomeAssistant, cloud: FakeCloud, hass_storage: dict[str, Any]
) -> None:
    """Rule 3: refused stored tokens -> once more with only the entry's token;
    the success overwrites the store (the 2.x B7 bug must not recur)."""
    entry = account_entry()
    token = entry.data["user_token"]
    _seed(
        hass_storage,
        f"anycubic_cloud.{entry.entry_id}",
        {"auth_token": "revoked", "auth_access_token": token, "auth_mode": 3},
    )
    cloud.reject_stored = True
    await setup_entry(hass, entry)
    assert entry.state is ConfigEntryState.LOADED
    assert cloud.clients[0].store is not None
    assert cloud.clients[1].store is None
    assert _store(hass_storage, entry.entry_id)["auth_token"] != "revoked"
    assert not _reauth_flows(hass)


async def test_legacy_store_is_read_and_copied(
    hass: HomeAssistant, cloud: FakeCloud, hass_storage: dict[str, Any]
) -> None:
    """Rule 2: the un-suffixed store of older versions, copied per entry."""
    entry = account_entry()
    _seed(
        hass_storage,
        "anycubic_cloud",
        {
            "auth_token": "legacy-user-token",
            "auth_access_token": entry.data["user_token"],
            "auth_mode": 3,
        },
    )
    await setup_entry(hass, entry)
    assert cloud.clients[0].user_token == "legacy-user-token"
    assert _store(hass_storage, entry.entry_id) is not None
    assert "anycubic_cloud" in hass_storage  # never removed


async def test_store_of_another_token_is_ignored(
    hass: HomeAssistant, cloud: FakeCloud, hass_storage: dict[str, Any]
) -> None:
    """Hardening of §5.3: a store written for another pasted token."""
    entry = account_entry()
    _seed(
        hass_storage,
        f"anycubic_cloud.{entry.entry_id}",
        {"auth_token": "old", "auth_access_token": "an-older-paste", "auth_mode": 3},
    )
    await setup_entry(hass, entry)
    assert cloud.clients[0].store is None


async def test_web_token_saved_as_slicer_loads(
    hass: HomeAssistant, cloud: FakeCloud, hass_storage: dict[str, Any]
) -> None:
    """PROTOCOL A §2.8: 2.x kept mode 3 on the entry and the web fallback's
    mode 1 in the store. Such entries load, as web clients (no cloud MQTT)."""
    token = "eyJ.web-user-token"
    entry = account_entry(token=token, mode=3)
    _seed(
        hass_storage,
        f"anycubic_cloud.{entry.entry_id}",
        {"auth_token": token, "auth_access_token": None, "auth_mode": 1},
    )
    await setup_entry(hass, entry)
    assert entry.state is ConfigEntryState.LOADED
    assert cloud.clients[0].auth_mode is AuthMode.WEB
    state = hass.states.get("binary_sensor.kobra_s1_cloud_mqtt_connection_active")
    assert state.attributes["supports_mqtt_login"] is False
    assert entry.data["user_auth_mode"] == 3  # never rewritten


async def test_sign_in_handoff_avoids_a_second_exchange(
    hass: HomeAssistant, cloud: FakeCloud, hass_storage: dict[str, Any]
) -> None:
    """A setup straight after the flow reuses its tokens (acceptance L2),
    and never reads an older store (rule 6)."""
    entry = account_entry()
    token = entry.data["user_token"]
    _seed(
        hass_storage,
        f"anycubic_cloud.{entry.entry_id}",
        {"auth_token": "stale", "auth_access_token": token, "auth_mode": 3},
    )
    async_hand_off_sign_in(
        hass,
        token,
        TokenState(
            auth_token="fresh-user-token",
            auth_access_token=token,
            auth_mode=AuthMode.SLICER,
        ),
    )
    await setup_entry(hass, entry)
    assert cloud.clients[0].user_token == "fresh-user-token"
    assert len(cloud.clients) == 1


async def test_rejected_token_asks_for_reauthentication(
    hass: HomeAssistant, cloud: FakeCloud
) -> None:
    cloud.check_errors = [CredentialsRejectedError("refused")]
    entry = await setup_entry(hass, account_entry())
    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert len(_reauth_flows(hass)) == 1


async def test_entry_without_token_asks_for_reauthentication(
    hass: HomeAssistant, cloud: FakeCloud
) -> None:
    entry = account_entry()
    entry = account_entry(data={**entry.data, "user_token": ""})
    await setup_entry(hass, entry)
    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert len(_reauth_flows(hass)) == 1


@pytest.mark.parametrize(
    "error",
    [
        CredentialsRejectedError("rate limited", server_message=RATE_LIMITED),
        ServiceUnavailableError("request error"),
    ],
)
async def test_transient_answers_are_retried_never_reauth(
    hass: HomeAssistant, cloud: FakeCloud, error: Exception
) -> None:
    """3 retries at setup, then not ready; a rate limit is transient (L2)."""
    cloud.check_errors = [error] * 4
    entry = await setup_entry(hass, account_entry())
    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert cloud.checks == 4
    assert not _reauth_flows(hass)


async def test_transient_answer_then_success(
    hass: HomeAssistant, cloud: FakeCloud
) -> None:
    cloud.check_errors = [ServiceUnavailableError("down")] * 2
    entry = await setup_entry(hass, account_entry())
    assert entry.state is ConfigEntryState.LOADED


@pytest.mark.parametrize(
    ("error", "fragment"),
    [
        (UnexpectedResponseError("shape"), "could not read"),
        (RuntimeError("unclassified"), None),
    ],
)
async def test_other_errors_are_not_ready(
    hass: HomeAssistant, cloud: FakeCloud, error: Exception, fragment: str | None
) -> None:
    """B5, B6: never re-authentication for a fault or an unclassified error."""
    if isinstance(error, RuntimeError):
        from anycubic_cloud_client import AnycubicCloudError

        error = AnycubicCloudError("unclassified")
    cloud.check_errors = [error]
    entry = await setup_entry(hass, account_entry())
    assert entry.state is ConfigEntryState.SETUP_RETRY
    if fragment:
        assert fragment in (entry.reason or "")
    assert not _reauth_flows(hass)


async def test_printer_removed_is_not_ready_not_reauth(
    hass: HomeAssistant, cloud: FakeCloud
) -> None:
    """B8: code 1007 (what LAN Mode does) is not an authentication failure."""
    cloud.printer_errors[cp.PRINTER_ID] = PrinterRemovedError("deleted")
    entry = await setup_entry(hass, account_entry())
    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert "LAN Mode" in (entry.reason or "")
    assert not _reauth_flows(hass)


@pytest.mark.parametrize(
    "error", [UnexpectedResponseError("shape"), ServiceUnavailableError("down")]
)
async def test_first_printer_record_failing(
    hass: HomeAssistant, cloud: FakeCloud, error: Exception
) -> None:
    cloud.printer_errors[cp.PRINTER_ID] = error
    entry = await setup_entry(hass, account_entry())
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_second_printer_failing_is_not_ready(
    hass: HomeAssistant, cloud: FakeCloud
) -> None:
    """G23: every printer is retried, not only the first."""
    cloud.printers[7] = cp.detail(7)
    cloud.printer_errors[7] = UnexpectedResponseError("shape")
    entry = account_entry()
    entry = account_entry(data={**entry.data, "printer_ids": [cp.PRINTER_ID, 7]})
    await setup_entry(hass, entry)
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_two_printers(hass: HomeAssistant, cloud: FakeCloud) -> None:
    cloud.printers[7] = cp.detail(7, name="Second")
    entry = account_entry()
    entry = account_entry(data={**entry.data, "printer_ids": [cp.PRINTER_ID, 7]})
    await setup_entry(hass, entry)
    assert entry.state is ConfigEntryState.LOADED
    assert find_device(hass, f"{cp.USER_ID}-{cp.PRINTER_ID}")
    assert find_device(hass, f"{cp.USER_ID}-7")
    # A printer without a MAC gets the literal "None" unique ids (round 2, Q4).
    assert hass.states.get("sensor.second_current_status") is not None


async def test_unselected_printer_devices_leave_the_entry(
    hass: HomeAssistant, cloud: FakeCloud
) -> None:
    """§1.7: devices of printers no longer selected are removed, ACEs too."""
    entry = account_entry()
    entry.add_to_hass(hass)
    registry = dr.async_get(hass)
    for identifier in (f"{cp.USER_ID}-999", f"{cp.USER_ID}-999-ace0"):
        registry.async_get_or_create(
            config_entry_id=entry.entry_id, identifiers={(DOMAIN, identifier)}
        )
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert find_device(hass, f"{cp.USER_ID}-999") is None
    assert find_device(hass, f"{cp.USER_ID}-999-ace0") is None
    assert find_device(hass, f"{cp.USER_ID}-{cp.PRINTER_ID}") is not None


@pytest.mark.parametrize(("days", "expected"), [(5.5, "5"), (-3, "0")])
async def test_expiry_repair(
    hass: HomeAssistant, cloud: FakeCloud, days: float, expected: str
) -> None:
    """§5.6: within 14 days (also expired) a warning names the days left."""
    entry = await setup_entry(hass, account_entry(token=cp.slicer_token(days)))
    issue = ir.async_get(hass).async_get_issue(
        DOMAIN, f"token_expiring_{entry.entry_id}"
    )
    assert issue is not None
    placeholders = issue.translation_placeholders
    assert placeholders["days"] == expected
    assert placeholders["name"] == cp.EMAIL
    assert set(placeholders) == {
        "days",
        "name",
        "reauth_url",
        "tool_macos",
        "tool_windows",
        "tool_browser",
    }
    assert issue.severity is ir.IssueSeverity.WARNING
    assert not issue.is_fixable
    assert issue.learn_more_url

    await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()
    assert (
        ir.async_get(hass).async_get_issue(DOMAIN, f"token_expiring_{entry.entry_id}")
        is None
    )


@pytest.mark.parametrize("token", [cp.slicer_token(60), "opaque-web-token"])
async def test_no_expiry_repair(
    hass: HomeAssistant, cloud: FakeCloud, token: str
) -> None:
    """Far from expiry, or no readable ``exp``: nothing (and a stale one goes)."""
    entry = account_entry(token=token)
    entry.add_to_hass(hass)
    ir.async_create_issue(
        hass,
        DOMAIN,
        f"token_expiring_{entry.entry_id}",
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key="token_expiring",
    )
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert (
        ir.async_get(hass).async_get_issue(DOMAIN, f"token_expiring_{entry.entry_id}")
        is None
    )


async def test_hybrid_entry_uses_lan_for_a_removed_printer(
    hass: HomeAssistant, cloud: FakeCloud, printer: MockPrinter
) -> None:
    """§5.4: the cloud first; a printer in LAN Mode (1007) is built from LAN."""
    cloud.printer_errors[cp.PRINTER_ID] = PrinterRemovedError("deleted")
    entry = await setup_entry(hass, account_entry(lan=True))
    assert entry.state is ConfigEntryState.LOADED
    coordinator = entry.runtime_data.primary
    assert coordinator.lan_connected
    assert coordinator.printer.cloud is None
    assert coordinator.printer.identity.printer_id == cp.PRINTER_ID
    # The cloud-only entities come back from the account (CLOUD.md §2).
    assert hass.states.get("binary_sensor.anycubic_kobra_s1_mqtt_connection_active")
    assert printer.handshakes == 1


async def test_hybrid_entry_several_printers_lan_for_the_missing_one(
    hass: HomeAssistant, cloud: FakeCloud, printer: MockPrinter
) -> None:
    cloud.printers[7] = cp.detail(7, name="Second")
    cloud.printer_errors[cp.PRINTER_ID] = PrinterRemovedError("deleted")
    entry = account_entry(lan=True)
    entry = account_entry(
        lan=True, data={**entry.data, "printer_ids": [7, cp.PRINTER_ID]}
    )
    await setup_entry(hass, entry)
    assert entry.state is ConfigEntryState.LOADED
    runtime = entry.runtime_data
    assert runtime.coordinators[cp.PRINTER_ID].lan_connected
    assert runtime.coordinators[7].uses_cloud


async def test_hybrid_entry_several_printers_none_missing(
    hass: HomeAssistant, cloud: FakeCloud, printer: MockPrinter
) -> None:
    """Every printer in the cloud: LAN Mode is tried for the first (Q5)."""
    cloud.printers[7] = cp.detail(7, name="Second")
    printer.handshake_error = __import__("anycubic_lan").LanModeDisabledError("off")
    entry = account_entry(lan=True)
    entry = account_entry(
        lan=True, data={**entry.data, "printer_ids": [cp.PRINTER_ID, 7]}
    )
    await setup_entry(hass, entry)
    assert entry.state is ConfigEntryState.LOADED
    runtime = entry.runtime_data
    assert runtime.coordinators[cp.PRINTER_ID].link is not None
    assert runtime.coordinators[cp.PRINTER_ID].uses_cloud
    assert runtime.coordinators[7].link is None


async def test_hybrid_lan_address_of_another_printer_is_refused(
    hass: HomeAssistant,
    cloud: FakeCloud,
    printer: MockPrinter,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The LAN address answers with another MAC than the cloud's: its reports
    are never taken for this printer, which runs on the cloud."""
    detail = cp.detail()
    detail["base"]["machine_mac"] = "11-22-33-44-55-66"
    cloud.printers[cp.PRINTER_ID] = detail
    entry = await setup_entry(hass, account_entry(lan=True))
    assert entry.state is ConfigEntryState.LOADED
    coordinator = entry.runtime_data.primary
    assert not coordinator.lan_connected
    assert coordinator.uses_cloud
    assert coordinator.printer.source == "cloud"
    assert coordinator.printer.identity.mac == "11-22-33-44-55-66"
    # The cloud's figures stand (LAN would report 34 °C for the nozzle).
    assert coordinator.printer.state.temperatures.nozzle == 31
    assert printer.handshakes >= 1
    assert "is not printer" in caplog.text


async def test_hybrid_entry_with_rejected_token_runs_on_lan(
    hass: HomeAssistant, cloud: FakeCloud, printer: MockPrinter
) -> None:
    cloud.check_errors = [CredentialsRejectedError("refused")]
    entry = await setup_entry(hass, account_entry(lan=True))
    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data.cloud is None
    assert len(_reauth_flows(hass)) == 1


async def test_hybrid_entry_with_cloud_down_runs_on_lan(
    hass: HomeAssistant, cloud: FakeCloud, printer: MockPrinter
) -> None:
    cloud.check_errors = [ServiceUnavailableError("down")] * 4
    entry = await setup_entry(hass, account_entry(lan=True))
    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data.cloud is None
    assert not _reauth_flows(hass)


async def test_hybrid_lan_failure_falls_back_to_cloud(
    hass: HomeAssistant, cloud: FakeCloud, printer: MockPrinter
) -> None:
    """LAN Mode off at the printer: the cloud supplies it (§5.4)."""
    from anycubic_lan import AnycubicLanError, LanModeDisabledError

    for error in (
        LanModeDisabledError("off"),
        __import__("anycubic_lan").UnsupportedPrinterError("old"),
        AnycubicLanError("gone"),
    ):
        printer.handshake_error = error
        entry = await setup_entry(hass, account_entry(lan=True))
        assert entry.state is ConfigEntryState.LOADED
        coordinator = entry.runtime_data.primary
        assert coordinator.uses_cloud
        assert coordinator.printer.source == "cloud"
        await hass.config_entries.async_unload(entry.entry_id)
        await hass.config_entries.async_remove(entry.entry_id)
    assert payloads.HOST
