"""Config flow, cloud steps (BEHAVIOUR §5.8, COMPAT §1, PROTOCOL A §2.9, §5.3)."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock, patch

from anycubic_cloud_client import (
    AnycubicCloudError,
    AuthMode,
    CredentialsRejectedError,
    PrinterRemovedError,
    RejectReason,
    ServiceUnavailableError,
    SignatureCheck,
    SignatureStatus,
    UnexpectedResponseError,
)
from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.anycubic_cloud.cloud import DATA_SIGN_IN
from custom_components.anycubic_cloud.const import DOMAIN

from . import cloud_payloads as cp
from .cloud_fakes import FakeCloud, sign_in_result
from .conftest import account_entry, setup_entry

TOKEN = cp.slicer_token()


class SignIn:
    """Stands in for ``sign_in_any``: records calls, answers or raises."""

    def __init__(self, cloud: FakeCloud) -> None:
        self.cloud = cloud
        self.error: Exception | None = None
        self.calls: list[dict[str, Any]] = []

    async def __call__(
        self,
        session: Any,
        secrets: Any,
        token: str,
        *,
        device_id: str | None = None,
        region: Any = None,
    ) -> Any:
        self.calls.append({"token": token, "device_id": device_id, "region": region})
        if self.error is not None:
            raise self.error
        mode = AuthMode.ANDROID if device_id else AuthMode.SLICER
        return sign_in_result(self.cloud, token, mode)


@pytest.fixture
def sign_in(cloud: FakeCloud) -> Generator[SignIn]:
    fake = SignIn(cloud)
    with (
        patch("custom_components.anycubic_cloud.config_flow.sign_in_any", fake),
        patch(
            "custom_components.anycubic_cloud.config_flow.verify_token_signature",
            AsyncMock(
                side_effect=lambda _s, token: SignatureCheck(
                    SignatureStatus.VALID, token
                )
            ),
        ),
    ):
        yield fake


async def _cloud_form(hass: HomeAssistant) -> Any:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "cloud"}
    )


async def _submit(hass: HomeAssistant, result: Any, **fields: Any) -> Any:
    data = {"user_token": TOKEN, "region": "international"} | fields
    return await hass.config_entries.flow.async_configure(result["flow_id"], data)


async def test_new_cloud_entry(
    hass: HomeAssistant, cloud: FakeCloud, sign_in: SignIn
) -> None:
    cloud.printers[7] = cp.detail(7, name="Second")
    result = await _cloud_form(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "cloud"
    assert set(result["data_schema"].schema) == {
        "user_token",
        "user_device_id",
        "region",
    }
    # Pasted inside a Slicer Next configuration fragment: the JWT is found.
    result = await _submit(
        hass, result, user_token=f'{{"anycubic_cloud": {{"access_token": "{TOKEN}"}}}}'
    )
    assert sign_in.calls[-1] == {
        "token": TOKEN,
        "device_id": None,
        "region": "international",
    }
    assert result["step_id"] == "printer"
    options = result["data_schema"].schema["printer_ids"].config["options"]
    assert {o["value"] for o in options} == {str(cp.PRINTER_ID), "7"}
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"printer_ids": [str(cp.PRINTER_ID)]}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == cp.EMAIL
    assert result["data"] == {
        "user_token": TOKEN,
        "user_auth_mode": 3,
        "user_device_id": None,
        "region": "international",
        "printer_ids": [cp.PRINTER_ID],
    }
    assert result["options"] == {}
    entry = result["result"]
    assert entry.unique_id == str(cp.USER_ID)
    await hass.async_block_till_done(wait_background_tasks=True)
    # The setup reused the sign-in's tokens: one client, no second exchange.
    assert cloud.client.user_token != TOKEN
    assert TOKEN not in hass.data.get(DATA_SIGN_IN, {})


async def test_android_and_china(
    hass: HomeAssistant, cloud: FakeCloud, sign_in: SignIn
) -> None:
    result = await _cloud_form(hass)
    result = await _submit(hass, result, user_device_id=" 0123abc ", region="china")
    assert sign_in.calls[-1] == {
        "token": TOKEN,
        "device_id": "0123abc",
        "region": "china",
    }
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"printer_ids": [str(cp.PRINTER_ID)]}
    )
    assert result["data"]["user_auth_mode"] == 2
    assert result["data"]["user_device_id"] == "0123abc"
    assert result["data"]["region"] == "china"


@pytest.mark.parametrize(
    ("pasted", "error"),
    [
        ("two words", "invalid_token_format"),
        (cp.jwt(exp=1, tokenType="access-token"), "token_expired"),
    ],
)
async def test_local_token_checks(
    hass: HomeAssistant, sign_in: SignIn, pasted: str, error: str
) -> None:
    result = await _cloud_form(hass)
    result = await _submit(hass, result, user_token=pasted)
    assert result["errors"] == {"user_token": error}
    assert not sign_in.calls


@pytest.mark.parametrize("status", [SignatureStatus.CORRUPTED, SignatureStatus.INVALID])
async def test_damaged_signature(
    hass: HomeAssistant, sign_in: SignIn, status: SignatureStatus
) -> None:
    with patch(
        "custom_components.anycubic_cloud.config_flow.verify_token_signature",
        AsyncMock(return_value=SignatureCheck(status, TOKEN)),
    ):
        result = await _cloud_form(hass)
        result = await _submit(hass, result)
    assert result["errors"] == {"user_token": "token_corrupted"}


async def test_trimmed_signature_is_used(hass: HomeAssistant, sign_in: SignIn) -> None:
    long_token = TOKEN + "extra"
    with patch(
        "custom_components.anycubic_cloud.config_flow.verify_token_signature",
        AsyncMock(return_value=SignatureCheck(SignatureStatus.TRIMMED, TOKEN)),
    ):
        result = await _cloud_form(hass)
        await _submit(hass, result, user_token=long_token)
    assert sign_in.calls[-1]["token"] == TOKEN


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (CredentialsRejectedError("no"), "invalid_auth"),
        (
            CredentialsRejectedError("no", reason=RejectReason.WRONG_TOKEN_TYPE),
            "wrong_token_type",
        ),
        (
            CredentialsRejectedError("slow", server_message="请求过于频繁。请稍后再试"),
            "cannot_connect",
        ),
        (UnexpectedResponseError("shape"), "cannot_read_response"),
        (ServiceUnavailableError("down"), "cannot_connect"),
        (RuntimeError("bug"), "cannot_connect"),
    ],
)
async def test_sign_in_errors(
    hass: HomeAssistant, sign_in: SignIn, error: Exception, expected: str
) -> None:
    sign_in.error = error
    result = await _cloud_form(hass)
    result = await _submit(hass, result)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": expected}


async def test_account_already_configured(
    hass: HomeAssistant, cloud: FakeCloud, sign_in: SignIn
) -> None:
    account_entry().add_to_hass(hass)
    result = await _cloud_form(hass)
    result = await _submit(hass, result)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


@pytest.mark.parametrize(
    ("setup", "error"),
    [
        ("empty", "no_printers"),
        ("list_shape", "cannot_read_response"),
        ("list_down", "cannot_connect"),
    ],
)
async def test_printer_list_problems(
    hass: HomeAssistant, cloud: FakeCloud, sign_in: SignIn, setup: str, error: str
) -> None:
    if setup == "empty":
        cloud.printers = {}
    elif setup == "list_shape":
        cloud.list_error = UnexpectedResponseError("shape")
    else:
        cloud.list_error = ServiceUnavailableError("down")
    result = await _cloud_form(hass)
    result = await _submit(hass, result)
    assert result["step_id"] == "printer"
    assert result["errors"] == {"base": error}


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (PrinterRemovedError("gone"), "invalid_printer"),
        (UnexpectedResponseError("shape"), "cannot_read_response"),
        (ServiceUnavailableError("down"), "cannot_connect"),
        (CredentialsRejectedError("no"), "invalid_auth"),
        (RuntimeError("bug"), "cannot_connect"),
    ],
)
async def test_chosen_printer_problems(
    hass: HomeAssistant,
    cloud: FakeCloud,
    sign_in: SignIn,
    error: Exception,
    expected: str,
) -> None:
    result = await _cloud_form(hass)
    result = await _submit(hass, result)
    cloud.printer_errors[cp.PRINTER_ID] = error
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"printer_ids": [str(cp.PRINTER_ID)]}
    )
    assert result["errors"] == {"base": expected}


async def test_no_printer_chosen(
    hass: HomeAssistant, cloud: FakeCloud, sign_in: SignIn
) -> None:
    result = await _cloud_form(hass)
    result = await _submit(hass, result)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"printer_ids": []}
    )
    assert result["errors"] == {"base": "no_printers"}


async def test_reauth_replaces_token_deletes_store_and_reloads(
    hass: HomeAssistant,
    cloud: FakeCloud,
    sign_in: SignIn,
    hass_storage: dict[str, Any],
) -> None:
    """PROTOCOL A §5.3 rule 4, in order: entry, store deleted, reload, done."""
    entry = account_entry()
    entry = await setup_entry(
        hass, account_entry(data={**entry.data, "region": "china"})
    )
    assert f"anycubic_cloud.{entry.entry_id}" in hass_storage
    result = await entry.start_reauth_flow(hass)
    assert result["step_id"] == "cloud"
    new_token = cp.slicer_token(80)
    clients = len(cloud.clients)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"user_token": new_token, "region": "international"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    await hass.async_block_till_done(wait_background_tasks=True)
    assert entry.data["user_token"] == new_token
    assert entry.data["user_auth_mode"] == 3
    assert entry.data["region"] == "international"
    assert entry.data["printer_ids"] == [cp.PRINTER_ID]
    # Reloaded, with the new sign-in's tokens - never the old session.
    setup_client = cloud.clients[clients + 1]
    assert setup_client.token == new_token
    assert setup_client.user_token == "derived-user-token"
    stored = hass_storage[f"anycubic_cloud.{entry.entry_id}"]["data"]
    assert stored["auth_token"] == "derived-user-token"


async def test_reauth_region_is_prefilled(
    hass: HomeAssistant, cloud: FakeCloud, sign_in: SignIn
) -> None:
    entry = account_entry()
    entry = account_entry(data={**entry.data, "region": "china"})
    entry.add_to_hass(hass)
    result = await entry.start_reauth_flow(hass)
    region = next(k for k in result["data_schema"].schema if k == "region")
    assert region.default() == "china"


async def test_reauth_with_another_account(
    hass: HomeAssistant, cloud: FakeCloud, sign_in: SignIn
) -> None:
    entry = account_entry(unique_id="999")
    entry.add_to_hass(hass)
    result = await entry.start_reauth_flow(hass)
    result = await _submit(hass, result)
    assert result["reason"] == "wrong_account"


async def _reconfigure(hass: HomeAssistant, entry: MockConfigEntry, step: str) -> Any:
    result = await entry.start_reconfigure_flow(hass)
    assert result["menu_options"] == ["reauth", "printer", "connection"]
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": step}
    )


async def test_reconfigure_reauth(
    hass: HomeAssistant, cloud: FakeCloud, sign_in: SignIn
) -> None:
    entry = await setup_entry(hass, account_entry())
    result = await _reconfigure(hass, entry, "reauth")
    assert result["step_id"] == "cloud"
    result = await _submit(hass, result, user_token=cp.slicer_token(70))
    assert result["reason"] == "reauth_successful"
    await hass.async_block_till_done(wait_background_tasks=True)


async def test_reconfigure_printers_uses_the_stored_session(
    hass: HomeAssistant,
    cloud: FakeCloud,
    sign_in: SignIn,
    hass_storage: dict[str, Any],
) -> None:
    """Rule 6: reconfigure -> printer uses the entry's token with its store."""
    cloud.printers[7] = cp.detail(7, name="Second")
    entry = await setup_entry(hass, account_entry())
    result = await _reconfigure(hass, entry, "printer")
    assert result["step_id"] == "printer"
    flow_client = cloud.client
    assert flow_client.store is not None
    default = result["data_schema"].schema["printer_ids"]
    assert result["data_schema"]({"printer_ids": ["7"]})
    assert default is not None
    from anycubic_cloud_client import TokenState

    cloud.exchanged_tokens = TokenState(auth_token="exchanged-in-the-flow")
    await flow_client.check()
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"printer_ids": [str(cp.PRINTER_ID), "7"]}
    )
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done(wait_background_tasks=True)
    assert entry.data["printer_ids"] == [cp.PRINTER_ID, 7]
    assert entry.data["user_token"]  # unchanged
    stored = hass_storage[f"anycubic_cloud.{entry.entry_id}"]["data"]
    assert stored["auth_token"] == "exchanged-in-the-flow"


async def test_reconfigure_printers_sign_in_failure(
    hass: HomeAssistant, cloud: FakeCloud, sign_in: SignIn
) -> None:
    entry = await setup_entry(hass, account_entry())
    cloud.check_errors = [AnycubicCloudError("down")]
    cloud.list_error = ServiceUnavailableError("down")
    result = await _reconfigure(hass, entry, "printer")
    assert result["errors"] == {"base": "cannot_connect"}


async def test_legacy_fixed_mode_steps(
    hass: HomeAssistant, cloud: FakeCloud, sign_in: SignIn
) -> None:
    """Kept for their step ids, reached by no menu (DECISIONS V9)."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "auth_mode_pick"}
    )
    assert result["type"] is FlowResultType.MENU
    assert result["menu_options"] == [
        "auth_mode_web",
        "auth_mode_slicer",
        "auth_mode_android",
    ]
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "auth_mode_android"}
    )
    assert set(result["data_schema"].schema) == {"user_token", "user_device_id"}
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"user_token": '"tok"', "user_device_id": "dev"}
    )
    assert cloud.client.token == "tok"
    assert cloud.client.auth_mode is AuthMode.ANDROID
    assert result["step_id"] == "printer"
    for step in ("auth_mode_web", "auth_mode_slicer"):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "auth_mode_pick"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"next_step_id": step}
        )
        assert set(result["data_schema"].schema) == {"user_token"}
    cloud.check_errors = [CredentialsRejectedError("no")]
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"user_token": "bad"}
    )
    assert result["errors"] == {"base": "invalid_auth"}


async def test_legacy_reauth_keeps_store_and_does_not_reload(
    hass: HomeAssistant,
    cloud: FakeCloud,
    sign_in: SignIn,
    hass_storage: dict[str, Any],
) -> None:
    entry = await setup_entry(hass, account_entry())
    flow = hass.config_entries.flow
    result = await entry.start_reauth_flow(hass)
    flow_id = result["flow_id"]
    handler = flow._progress[flow_id]
    result = await handler.async_step_auth_mode_web({"user_token": "web-tok"})
    assert result["reason"] == "reauth_successful"
    assert entry.data["user_token"] == "web-tok"
    assert entry.data["user_auth_mode"] == 1
    assert f"anycubic_cloud.{entry.entry_id}" in hass_storage


async def test_options_menu_of_a_cloud_entry(
    hass: HomeAssistant, cloud: FakeCloud
) -> None:
    entry = await setup_entry(hass, account_entry())
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["menu_options"] == ["mqtt", "drying", "local", "card_config", "debug"]
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "mqtt"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"mqtt_connect_mode": "4"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done(wait_background_tasks=True)
    assert entry.options["mqtt_connect_mode"] == 4
    # Reloaded: mode 4 holds the link open.
    assert cloud.link.connects == 1
