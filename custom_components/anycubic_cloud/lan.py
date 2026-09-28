"""LAN Mode transport, built on anycubic-lan (BEHAVIOUR §5.3).

Order payloads for the kinds that anycubic-lan has no helper for follow the
shapes of the printer's own reports; see QUESTIONS.md Q1 for the field names
the specification does not yet confirm.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from enum import StrEnum
import logging
import re
import secrets
from typing import TYPE_CHECKING, Any, cast

from anycubic_lan import (
    AnycubicLanClient,
    NotConnectedError,
    PrinterConnectionInfo,
    PrinterState,
    Report,
    ReportKind,
    handshake,
    parse_message,
)

if TYPE_CHECKING:
    import aiohttp

_LOGGER = logging.getLogger(__name__)

# The printer's device id appears in every topic; logs never show it (§5.9).
# It is the segment after the model id: ``.../printer/public/<model>/<id>/...``
# (reports) or ``.../web/printer/<model>/<id>/...`` (orders).
_TOPIC_DEVICE = re.compile(r"(/printer/(?:public/)?[^/]+/)[^/]+")
# The signed upload URL authorises uploads to the printer (anycubic-lan HW4).
_SIGNED_UPLOAD = re.compile(rb"[^\s\"']*gcode_upload\?s=[^\s\"']*")

type ReportCallback = Callable[[Report], None]


class ExtraKind(StrEnum):
    """Command kinds anycubic-lan does not list (BEHAVIOUR §2.18)."""

    VIDEO = "video"


def redact_topic(topic: str) -> str:
    """Hide the printer's device id in a topic."""
    return _TOPIC_DEVICE.sub(r"\1**REDACTED**", topic)


def redact_payload(payload: bytes) -> bytes:
    """Hide the signed upload URL in a raw message before it is logged."""
    return _SIGNED_UPLOAD.sub(b"**REDACTED**", payload)


class IntegrationLanClient(AnycubicLanClient):
    """anycubic-lan's client, also handing every parsed report to a callback.

    The merged ``PrinterState`` does not keep the ``axis``/``move`` state
    (``doing``/``done``/``failed``) that the axis binary sensors need
    (BEHAVIOUR §1.8), so the raw report is passed on before it is merged.
    anycubic-lan 0.1.0 has no public hook for this (QUESTIONS.md Q2).
    """

    def __init__(
        self,
        connection: PrinterConnectionInfo,
        *,
        report_callback: ReportCallback,
        debug_messages: bool = False,
    ) -> None:
        super().__init__(connection, client_id=f"ha-{secrets.token_hex(6)}")
        self._report_callback = report_callback
        self._debug_messages = debug_messages

    def _handle_message(self, topic: str, payload: bytes) -> None:
        if self._debug_messages:
            _LOGGER.debug(
                "LAN message on %s: %s",
                redact_topic(topic),
                redact_payload(payload)[:2000],
            )
        report = parse_message(payload, topic)
        if report is not None:
            try:
                self._report_callback(report)
            except Exception:
                _LOGGER.exception("Error handling a LAN report")
        super()._handle_message(topic, payload)


class LanLink:
    """One LAN connection to one printer: handshake, client and orders."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        *,
        on_state: Callable[[PrinterState], None],
        on_report: ReportCallback,
        on_connection: Callable[[bool], None],
        debug_messages: bool = False,
    ) -> None:
        self._session = session
        self.host = host
        self._on_state = on_state
        self._on_report = on_report
        self._on_connection = on_connection
        self._debug_messages = debug_messages
        self.client: AnycubicLanClient | None = None
        self.info: PrinterConnectionInfo | None = None

    @property
    def connected(self) -> bool:
        return self.client is not None and self.client.is_connected

    async def async_connect(self) -> PrinterConnectionInfo:
        """Run the full handshake and connect (§5.3; a fresh handshake every
        time, since the printer rotates its credentials - G2)."""
        await self.async_disconnect()
        info = await handshake(self._session, self.host)
        client = IntegrationLanClient(
            info,
            report_callback=self._on_report,
            debug_messages=self._debug_messages,
        )
        client.add_state_listener(self._on_state)
        client.add_connection_listener(self._on_connection)
        await client.connect()
        self.client, self.info = client, info
        return info

    async def async_disconnect(self) -> None:
        client, self.client = self.client, None
        if client is not None:
            await client.disconnect()

    def _require_client(self) -> AnycubicLanClient:
        if self.client is None:
            raise NotConnectedError("Not connected to the printer")
        return self.client

    # -- queries -------------------------------------------------------------

    async def async_query_all(self) -> None:
        await self._require_client().query_all()

    async def async_query(self, kind: ReportKind) -> None:
        await self._require_client().query(kind)

    # -- orders (BEHAVIOUR §5.3 table) ---------------------------------------

    async def async_send(
        self, kind: ReportKind | ExtraKind, action: str, data: Mapping[str, Any]
    ) -> str:
        # send_command only reads ``kind.value``; ExtraKind has one too.
        return await self._require_client().send_command(
            cast("ReportKind", kind), action, data
        )

    async def async_pause(self) -> None:
        await self._require_client().pause()

    async def async_resume(self) -> None:
        await self._require_client().resume()

    async def async_stop(self) -> None:
        await self._require_client().stop()

    async def async_set_light(self, on: bool, light_type: int) -> None:
        # On: status 1 brightness 100; off: status 0 brightness 0 (§2.16).
        await self._require_client().set_light(
            on, 100 if on else 0, light_type=light_type
        )

    async def async_start_camera(self) -> None:
        await self.async_send(ExtraKind.VIDEO, "startCapture", {})

    async def async_set_temperature(self, key: str, value: int) -> None:
        # Only the figure being changed is sent (Q1): sending the other as 0
        # without the cloud's heat type could switch that heater off.
        await self.async_send(ReportKind.TEMPERATURE, "set", {key: value})

    async def async_set_fan(self, key: str, value: int) -> None:
        await self.async_send(ReportKind.FAN, "setSpeed", {key: value})

    async def async_move_axis(self, axis: int, move_type: int, distance: int) -> None:
        await self.async_send(
            ReportKind.AXIS,
            "move",
            {"axis": axis, "move_type": move_type, "distance": distance},
        )

    async def async_motors_off(self) -> None:
        await self.async_send(ReportKind.AXIS, "turnOff", {})

    async def async_ace_command(self, action: str, box: Mapping[str, Any]) -> None:
        """An ACE order, addressed like the printer's own box reports."""
        await self.async_send(
            ReportKind.MULTI_COLOR_BOX, action, {"multi_color_box": [dict(box)]}
        )

    async def async_ace_dry(
        self, box_id: int, status: int, temperature: int, duration: int
    ) -> None:
        await self.async_ace_command(
            "setDry",
            {
                "id": box_id,
                "drying_status": {
                    "status": status,
                    "target_temp": temperature,
                    "duration": duration,
                },
            },
        )

    async def async_ace_feed(
        self, box_id: int, slot_index: int, feed_type: int
    ) -> None:
        await self.async_ace_command(
            "feedFilament",
            {
                "id": box_id,
                "feed_status": {"slot_index": slot_index, "type": feed_type},
            },
        )

    async def async_ace_set_slot(
        self, box_id: int, slot_index: int, material: str, color: list[int]
    ) -> None:
        await self.async_ace_command(
            "setInfo",
            {
                "id": box_id,
                "slots": [{"index": slot_index, "type": material, "color": color}],
            },
        )

    async def async_ace_auto_feed(self, box_id: int, enabled: bool) -> None:
        await self.async_ace_command(
            "setAutoFeed", {"id": box_id, "auto_feed": 1 if enabled else 0}
        )
