"""The LAN link and client subclass (BEHAVIOUR §5.3)."""

from __future__ import annotations

import json
import logging
from unittest.mock import AsyncMock, MagicMock, patch

from anycubic_lan import NotConnectedError, Report
from homeassistant.core import HomeAssistant
import pytest

from custom_components.anycubic_cloud.lan import IntegrationLanClient, LanLink

from . import payloads


def test_client_passes_reports_on(caplog: pytest.LogCaptureFixture) -> None:
    """The raw report reaches the callback before anycubic-lan merges it."""
    seen: list[Report] = []
    client = IntegrationLanClient(
        payloads.connection_info(),
        report_callback=seen.append,
        debug_messages=True,
    )
    topic = (
        f"anycubic/anycubicCloud/v1/printer/public/20025/{payloads.DEVICE_ID}"
        "/axis/report"
    )
    caplog.set_level(logging.DEBUG, logger="custom_components.anycubic_cloud.lan")
    client._handle_message(topic, json.dumps(payloads.axis_move("doing")).encode())
    assert seen[0].envelope.action == "move"
    assert seen[0].envelope.state == "doing"
    assert payloads.DEVICE_ID not in caplog.text
    client._handle_message(topic, json.dumps(payloads.info()).encode())
    assert "gcode_upload?s=" not in caplog.text
    assert "SIGNEDSECRET" not in caplog.text
    # Nothing to report for an empty message; a failing callback is contained.
    client._handle_message(topic, b'{"msgid": ""}')
    assert len(seen) == 2
    broken = IntegrationLanClient(
        payloads.connection_info(),
        report_callback=MagicMock(side_effect=RuntimeError),
    )
    broken._handle_message(topic, json.dumps(payloads.info()).encode())
    assert "Error handling a LAN report" in caplog.text
    assert broken.state.firmware_version == "2.7.2.7"


async def test_link_requires_a_client(hass: HomeAssistant) -> None:
    link = LanLink(
        MagicMock(),
        payloads.HOST,
        on_state=MagicMock(),
        on_report=MagicMock(),
        on_connection=MagicMock(),
    )
    assert not link.connected
    with pytest.raises(NotConnectedError):
        await link.async_query_all()
    await link.async_disconnect()


async def test_link_connect_builds_the_client(hass: HomeAssistant) -> None:
    client = MagicMock()
    client.connect = AsyncMock()
    with (
        patch(
            "custom_components.anycubic_cloud.lan.handshake",
            AsyncMock(return_value=payloads.connection_info()),
        ),
        patch(
            "custom_components.anycubic_cloud.lan.IntegrationLanClient",
            return_value=client,
        ) as factory,
    ):
        link = LanLink(
            MagicMock(),
            payloads.HOST,
            on_state=MagicMock(),
            on_report=MagicMock(),
            on_connection=MagicMock(),
            debug_messages=True,
        )
        info = await link.async_connect()
    assert info.device_id == payloads.DEVICE_ID
    assert factory.call_args.kwargs["debug_messages"] is True
    client.add_state_listener.assert_called_once()
    client.add_connection_listener.assert_called_once()
