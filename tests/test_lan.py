"""The LAN link and client subclass (BEHAVIOUR §5.3)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
import json
import logging
from typing import Any
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


def _published_link() -> tuple[LanLink, MagicMock]:
    """A link whose real client publishes into a mock MQTT client."""
    client = IntegrationLanClient(
        payloads.connection_info(), report_callback=MagicMock()
    )
    mqtt = MagicMock()
    mqtt.publish.return_value.rc = 0
    client._mqtt = mqtt
    client._connected = True
    link = LanLink(
        MagicMock(),
        payloads.HOST,
        on_state=MagicMock(),
        on_report=MagicMock(),
        on_connection=MagicMock(),
    )
    link.client = client
    return link, mqtt


def _published(mqtt: MagicMock) -> tuple[str, dict[str, Any]]:
    topic, text = mqtt.publish.call_args.args
    return topic, json.loads(text)


@pytest.mark.parametrize(
    ("order", "kind", "action", "data"),
    [
        (
            lambda link: link.async_set_temperatures(nozzle=210),
            "tempature",
            "set",
            {"type": 0, "target_nozzle_temp": 210, "target_hotbed_temp": 0},
        ),
        (
            lambda link: link.async_set_temperatures(bed=60),
            "tempature",
            "set",
            {"type": 1, "target_nozzle_temp": 0, "target_hotbed_temp": 60},
        ),
        (
            lambda link: link.async_set_temperatures(nozzle=200, bed=55),
            "tempature",
            "set",
            {"type": 2, "target_nozzle_temp": 200, "target_hotbed_temp": 55},
        ),
        (
            lambda link: link.async_set_fan("aux_fan_speed_pct", 30),
            "fan",
            "setSpeed",
            {"aux_fan_speed_pct": 30},
        ),
        (
            lambda link: link.async_move_axis(4, 2, 0),
            "axis",
            "move",
            {"axis": 4, "move_type": 2, "distance": 0},
        ),
        (lambda link: link.async_motors_off(), "axis", "turnOff", None),
        (lambda link: link.async_start_camera(), "video", "startCapture", {}),
        (
            lambda link: link.async_ace_dry(1, 1, 55, 240),
            "multiColorBox",
            "setDry",
            {
                "multi_color_box": [
                    {
                        "id": 1,
                        "drying_status": {
                            "status": 1,
                            "target_temp": 55,
                            "duration": 240,
                            "remain_time": None,
                        },
                    }
                ]
            },
        ),
        (
            lambda link: link.async_ace_dry(0, 0, 0, 0),
            "multiColorBox",
            "setDry",
            {
                "multi_color_box": [
                    {
                        "id": 0,
                        "drying_status": {
                            "status": 0,
                            "target_temp": 0,
                            "duration": 0,
                            "remain_time": None,
                        },
                    }
                ]
            },
        ),
        (
            lambda link: link.async_ace_feed(0, 2, 1),
            "multiColorBox",
            "feedFilament",
            {
                "multi_color_box": [
                    {"id": 0, "feed_status": {"slot_index": 2, "type": 1}}
                ]
            },
        ),
        (
            lambda link: link.async_ace_set_slot(0, 1, "PLA", [255, 0, 0]),
            "multiColorBox",
            "setInfo",
            {
                "multi_color_box": [
                    {
                        "id": 0,
                        "slots": [{"index": 1, "type": "PLA", "color": [255, 0, 0]}],
                    }
                ]
            },
        ),
        (
            lambda link: link.async_ace_auto_feed(1, True),
            "multiColorBox",
            "setAutoFeed",
            {"multi_color_box": [{"id": 1, "auto_feed": 1}]},
        ),
    ],
)
async def test_published_orders(
    order: Callable[[LanLink], Awaitable[None]],
    kind: str,
    action: str,
    data: Any,
) -> None:
    """The exact objects of anycubic-lan PROTOCOL.md §7.2 (round 2, Q1)."""
    link, mqtt = _published_link()
    await order(link)
    topic, payload = _published(mqtt)
    assert topic.endswith(f"/{kind}")
    assert set(payload) == {"type", "action", "timestamp", "msgid", "data"}
    assert (payload["type"], payload["action"]) == (kind, action)
    assert payload["data"] == data
    assert isinstance(payload["timestamp"], int)
    assert payload["msgid"]


async def test_temperature_needs_a_figure() -> None:
    link, mqtt = _published_link()
    with pytest.raises(ValueError, match="No temperature"):
        await link.async_set_temperatures()
    mqtt.publish.assert_not_called()
