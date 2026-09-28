"""Anycubic's app credentials, loaded by name at run time (CLOUD.md §1).

The real ``anycubic-cloud-api`` package is never needed: a fake module and
fake resource files stand in for it.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
import pytest

from custom_components.anycubic_cloud import credentials
from custom_components.anycubic_cloud.const import DOMAIN
from custom_components.anycubic_cloud.credentials import (
    ISSUE_CREDENTIALS,
    CredentialsUnavailableError,
    async_get_cloud_secrets,
    load_cloud_secrets,
)

from . import payloads
from .cloud_fakes import fake_secrets
from .conftest import MockPrinter, account_entry, setup_entry

ATTRIBUTES = {
    "AC_KNOWN_AID": "fake-aid",
    "AC_KNOWN_SEC": "fake-sec",
    "AC_KNOWN_CID_WEB": "fake-web",
    "AC_KNOWN_CID_APP": "fake-app",
}


def _package(tmp_path: Path, files: dict[str, bytes]) -> Path:
    resources = tmp_path / "resources"
    resources.mkdir()
    for name, content in files.items():
        (resources / name).write_bytes(content)
    return tmp_path


def _files() -> dict[str, bytes]:
    secrets = fake_secrets()
    return {
        "anycubic_mqqt_tls_ca.crt": secrets.mqtt_ca_pem,
        "anycubic_mqqt_tls_client.crt": secrets.mqtt_client_cert_pem,
        "anycubic_mqqt_tls_client.key": secrets.mqtt_client_key_pem,
    }


def _load(tmp_path: Path, module: Any, files: dict[str, bytes]) -> Any:
    root = _package(tmp_path, files)
    with (
        patch.object(credentials.importlib, "import_module", return_value=module),
        patch.object(credentials.resources, "files", return_value=root),
    ):
        return load_cloud_secrets()


def test_loads_every_item_by_name(tmp_path: Path) -> None:
    secrets = _load(tmp_path, SimpleNamespace(**ATTRIBUTES), _files())
    assert secrets.app_id == "fake-aid"
    assert secrets.client_id_app == "fake-app"
    assert secrets.mqtt_ca_pem == fake_secrets().mqtt_ca_pem
    # Never shown.
    assert "fake-sec" not in repr(secrets)


def test_missing_package(tmp_path: Path) -> None:
    with (
        patch.object(
            credentials.importlib, "import_module", side_effect=ImportError("none")
        ),
        pytest.raises(CredentialsUnavailableError, match="not installed"),
    ):
        load_cloud_secrets()


def test_missing_attribute(tmp_path: Path) -> None:
    module = SimpleNamespace(
        **{k: v for k, v in ATTRIBUTES.items() if k != "AC_KNOWN_SEC"}
    )
    with pytest.raises(CredentialsUnavailableError, match="AC_KNOWN_SEC"):
        _load(tmp_path, module, _files())


def test_missing_file(tmp_path: Path) -> None:
    files = _files()
    del files["anycubic_mqqt_tls_client.key"]
    with pytest.raises(CredentialsUnavailableError, match=r"tls_client\.key"):
        _load(tmp_path, SimpleNamespace(**ATTRIBUTES), files)


def test_rejected_by_cloud_secrets(tmp_path: Path) -> None:
    files = _files() | {"anycubic_mqqt_tls_ca.crt": b"not a certificate"}
    with pytest.raises(CredentialsUnavailableError, match="mqtt_ca_pem"):
        _load(tmp_path, SimpleNamespace(**ATTRIBUTES), files)


async def test_loaded_once_and_issue_removed(hass: HomeAssistant) -> None:
    ir.async_create_issue(
        hass,
        DOMAIN,
        ISSUE_CREDENTIALS,
        is_fixable=False,
        severity=ir.IssueSeverity.ERROR,
        translation_key=ISSUE_CREDENTIALS,
    )
    with patch.object(
        credentials, "load_cloud_secrets", return_value=fake_secrets()
    ) as loader:
        assert await async_get_cloud_secrets(hass) is fake_secrets()
        assert await async_get_cloud_secrets(hass) is fake_secrets()
    assert loader.call_count == 1
    assert ir.async_get(hass).async_get_issue(DOMAIN, ISSUE_CREDENTIALS) is None


async def test_unavailable_raises_repair_once(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    assert await async_get_cloud_secrets(hass) is None
    assert await async_get_cloud_secrets(hass) is None
    issue = ir.async_get(hass).async_get_issue(DOMAIN, ISSUE_CREDENTIALS)
    assert issue is not None
    assert issue.translation_placeholders == {"package": "anycubic-cloud-api"}
    warnings = [r for r in caplog.records if "app credentials" in r.getMessage()]
    assert len(warnings) == 1
    assert warnings[0].levelname == "WARNING"


async def test_hybrid_entry_keeps_working_on_lan(
    hass: HomeAssistant, printer: MockPrinter
) -> None:
    """Without the credentials a hybrid entry runs on LAN; data untouched."""
    entry = account_entry(lan=True)
    data = dict(entry.data)
    await setup_entry(hass, entry)
    assert entry.state is ConfigEntryState.LOADED
    assert dict(entry.data) == data
    assert entry.runtime_data.cloud is None
    assert hass.states.get("sensor.anycubic_kobra_s1_nozzle_temperature") is not None
    assert ir.async_get(hass).async_get_issue(DOMAIN, ISSUE_CREDENTIALS)
    assert printer.handshakes == 1
    assert entry.options["lan_host"] == payloads.HOST
