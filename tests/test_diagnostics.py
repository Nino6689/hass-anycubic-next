"""Diagnostics redact every secret (COMPAT §6, anycubic-lan HW4)."""

from __future__ import annotations

import json
import re

from homeassistant.core import HomeAssistant

from custom_components.anycubic_cloud.diagnostics import (
    async_get_config_entry_diagnostics,
)

from . import payloads
from .cloud_fakes import FakeCloud
from .conftest import MockPrinter, account_entry, cloud_entry, setup_entry


async def test_diagnostics_redact_secrets(
    hass: HomeAssistant, printer: MockPrinter
) -> None:
    # A value that carries the signed URL under an unexpected key too.
    printer.connect_payloads.append(
        payloads.extfilbox(note=f"see {payloads.UPLOAD_URL}")
    )
    entry = await setup_entry(hass, cloud_entry(lan=True))
    result = await async_get_config_entry_diagnostics(hass, entry)
    dump = json.dumps(result)

    for secret in (
        "gcode_upload?s=",
        "SIGNEDSECRET",
        payloads.DISCOVERY_TOKEN,
        "printer-user",
        "printer-pass",
        "SERIAL123",
        "A4-E8-8D-80-54-C8",
        "a4:e8:8d:80:54:c8",
        payloads.DEVICE_ID,
        "eyJhbGciOiJSUzI1NiJ9",
    ):
        assert secret not in dump, secret

    assert result["entry"]["data"]["user_token"] == "**REDACTED**"
    assert result["entry"]["title"] == "**REDACTED**"
    assert result["cloud"] is None  # the app credentials are not installed
    (printer_diag,) = result["printers"]
    connection = printer_diag["connection"]
    assert connection["discovery"]["fileUploadurl"] == "**REDACTED**"
    assert connection["discovery"]["modelName"] == "Anycubic Kobra S1"
    assert connection["broker"]["port"] == 9883
    assert connection["source"] == "lan"
    state = printer_diag["printer"]["state"]
    assert state["file_upload_url"] == "**REDACTED**"
    assert state["firmware_version"] == "2.7.2.7"
    assert printer_diag["printer"]["identity"]["mac"] == "**REDACTED**"
    assert state["ace_boxes"][0]["slots"][0]["material"] == "PLA"
    assert result["capabilities"] == {"printers": {"42424242": {"light_types": [2]}}}
    assert printer_diag["forecast"] is None
    assert printer_diag["cloud"] is None
    assert "printers" in result["ledger"]


async def test_cloud_diagnostics_redact_account_and_printer(
    hass: HomeAssistant, cloud: FakeCloud
) -> None:
    """Tokens, e-mail, printer key, MAC, serial and signed URLs are hidden."""
    from . import cloud_payloads as cp

    entry = await setup_entry(hass, account_entry())
    account = entry.runtime_data.cloud
    await account.async_fetch_cloud_files()
    result = await async_get_config_entry_diagnostics(hass, entry)
    dump = json.dumps(result)
    for secret in (
        entry.data["user_token"],
        cp.EMAIL,
        cp.PRINTER_KEY,
        "A4-E8-8D-80-54-C8",
        "SERIAL",
        "X-Amz-Signature",
        "1990-01-01",
        "fake-app-secret",
    ):
        assert secret not in dump, secret
    assert not re.search(rf"\b{cp.USER_ID}\b", dump)
    cloud_diag = result["cloud"]
    assert cloud_diag["region"] == "international"
    assert cloud_diag["auth_mode"] == 3
    assert cloud_diag["last_poll_ok"] is True
    assert cloud_diag["mqtt"]["possible"] is True
    assert cloud_diag["cloud_files"][0]["name"] == "benchy.gcode"
    (printer,) = result["printers"]
    assert printer["connection"]["source"] == "cloud"
    assert printer["cloud"]["detail"]["model"] == "Anycubic Kobra S1"
    assert printer["cloud"]["job"]["gcode_name"] == "benchy_PLA_0.2.gcode"
    assert printer["cloud"]["job_detail"]["z_thick"] == 0.2
    assert printer["cloud"]["firmware"]["installed_version"] == "2.7.2.7"
