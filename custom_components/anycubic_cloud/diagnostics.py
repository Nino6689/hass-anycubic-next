"""Diagnostics with every secret redacted (COMPAT §6, anycubic-lan HW4).

Redacted: the pasted token and cloud session fields, LAN broker credentials,
the discovery token, the serial number, the MAC, and the signed upload URL -
by key (``fileUploadurl``/``file_upload_url``) and, as a second net, any
string containing ``gcode_upload?s=`` wherever it appears.
"""

from __future__ import annotations

from collections.abc import Mapping
import dataclasses
from enum import Enum
from typing import TYPE_CHECKING, Any

from homeassistant.components.diagnostics import REDACTED, async_redact_data

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .coordinator import AnycubicConfigEntry

TO_REDACT = {
    # cloud entry data and session store (COMPAT §1, §6)
    "user_token",
    "user_device_id",
    "auth_token",
    "auth_access_token",
    "app_secret",
    "app_client_id",
    "app_id",
    # LAN handshake and discovery document
    "token",
    "username",
    "password",
    "cn",
    "usn",
    "serial",
    "fileUploadurl",
    "fileuploadurl",
    "file_upload_url",
    # identifiers
    "mac",
    "connection_mac",
    "device_id",
    "deviceId",
}

_SIGNED_UPLOAD = "gcode_upload?s="


def _plain(value: Any) -> Any:
    """Frozen dataclasses, mapping proxies and enums as plain JSON values."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _plain(getattr(value, field.name))
            for field in dataclasses.fields(value)
        }
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, list | tuple | set | frozenset):
        return [_plain(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    return value


def _scrub(value: Any) -> Any:
    """Replace any string that carries a signed upload URL."""
    if isinstance(value, str):
        return REDACTED if _SIGNED_UPLOAD in value else value
    if isinstance(value, dict):
        return {key: _scrub(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_scrub(item) for item in value]
    return value


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: AnycubicConfigEntry
) -> dict[str, Any]:
    """Diagnostics of a config entry."""
    coordinator = entry.runtime_data
    link = coordinator.link
    info = link.info
    printer = coordinator.printer if coordinator.has_printer else None
    result: dict[str, Any] = {
        "entry": {
            "title": entry.title,
            "version": entry.version,
            "minor_version": entry.minor_version,
            "data": dict(entry.data),
            "options": dict(entry.options),
        },
        "connection": {
            "connected": link.connected,
            "last_update_success": coordinator.last_update_success,
            "discovery": info.discovery.as_redacted_dict() if info else None,
            "model_id": info.model_id if info else None,
            "broker": (
                {
                    "host": info.credentials.host,
                    "port": info.credentials.port,
                    "scheme": info.credentials.scheme,
                }
                if info
                else None
            ),
        },
        "printer": (
            {
                "identity": _plain(printer.identity),
                "info_seen": printer.info_seen,
                "axis_move_state": printer.axis_move_state,
                "state": _plain(printer.state),
            }
            if printer
            else None
        ),
        "forecast": _plain(coordinator.forecast),
        "ledger": coordinator.ledger.data,
        "capabilities": coordinator.capability_data,
    }
    return _scrub(async_redact_data(result, TO_REDACT))  # type: ignore[no-any-return]
