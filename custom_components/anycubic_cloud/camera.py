"""The printer's own camera (BEHAVIOUR §2.18). ``cloud_camera`` is cloud only.

The printer serves one HTTP-FLV stream and no snapshot endpoint, so stills
are taken from the running stream (B24). Before every stream request the
printer is told to start capturing (DECISIONS V15). A Kobra X answers the
stream with HTTP 206, which stream readers refuse; its stream is relayed
through a Home Assistant endpoint that answers 200 (B25).
"""

from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus
import logging
import secrets
from typing import TYPE_CHECKING, Any

import aiohttp
from aiohttp import web
from anycubic_lan import AnycubicLanError
from homeassistant.components.camera import (
    Camera,
    CameraEntityDescription,
    CameraEntityFeature,
)
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.http import KEY_HASS, HomeAssistantView
from homeassistant.helpers.network import NoURLAvailableError, get_url

from .const import DOMAIN, MODEL_ID_KOBRA_X
from .entity import AnycubicEntity, AnycubicEntityDescription, async_add_when_ready

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from .coordinator import AnycubicConfigEntry, AnycubicCoordinator

_LOGGER = logging.getLogger(__name__)

RELAY_URL = "/api/anycubic_cloud/camera_relay/{entity_id}"
_RELAYS = f"{DOMAIN}_camera_relays"
_DEFAULT_CONTENT_TYPE = "video/x-flv"
_CHUNK = 64 * 1024


@dataclass(frozen=True, kw_only=True)
class AnycubicCameraDescription(AnycubicEntityDescription, CameraEntityDescription):
    """The printer camera."""


CAMERA = AnycubicCameraDescription(key="camera")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AnycubicConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the camera of a config entry."""
    if _RELAYS not in hass.data:
        hass.data[_RELAYS] = {}
        hass.http.register_view(CameraRelayView())
    async_add_when_ready(
        entry.runtime_data, (CAMERA,), PrinterCamera, async_add_entities
    )


class PrinterCamera(AnycubicEntity, Camera):
    """The printer's HTTP-FLV stream."""

    entity_description: AnycubicCameraDescription
    _attr_supported_features = CameraEntityFeature.STREAM

    def __init__(
        self, coordinator: AnycubicCoordinator, description: AnycubicCameraDescription
    ) -> None:
        AnycubicEntity.__init__(self, coordinator, description)
        Camera.__init__(self)
        self._relay_token = secrets.token_urlsafe(24)

    @property
    def available(self) -> bool:
        """Only while the LAN link is up (B33)."""
        return super().available and self.coordinator.link.connected

    @property
    def _needs_relay(self) -> bool:
        return self.printer.identity.model_id == MODEL_ID_KOBRA_X

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.hass.data[_RELAYS][self.entity_id] = self

        def _forget() -> None:
            self.hass.data[_RELAYS].pop(self.entity_id, None)

        self.async_on_remove(_forget)

    def relay_allowed(self, token: str | None) -> bool:
        return token is not None and secrets.compare_digest(token, self._relay_token)

    @property
    def printer_stream_url(self) -> str:
        return self.printer.camera_url

    async def stream_source(self) -> str | None:
        try:
            await self.coordinator.link.async_start_camera()
        except AnycubicLanError as err:
            _LOGGER.debug("Could not ask the printer to start its camera: %s", err)
        if not self._needs_relay:
            return self.printer_stream_url
        try:
            base = get_url(self.hass, allow_external=False, allow_cloud=False)
        except NoURLAvailableError:
            base = "http://127.0.0.1:8123"
        path = RELAY_URL.format(entity_id=self.entity_id)
        return f"{base}{path}?token={self._relay_token}"

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """A still from the running stream, never a second connection."""
        if self.stream is None:
            return None
        return await self.stream.async_get_image(width, height)


class CameraRelayView(HomeAssistantView):
    """Relays a Kobra X stream unchanged but with status 200 (B25).

    Protected by a random per-entity token instead of a login, because the
    stream reader inside Home Assistant opens it like any other URL.
    """

    url = RELAY_URL
    name = "api:anycubic_cloud:camera_relay"
    requires_auth = False

    async def get(self, request: web.Request, entity_id: str) -> web.StreamResponse:
        hass = request.app[KEY_HASS]
        camera: PrinterCamera | None = hass.data.get(_RELAYS, {}).get(entity_id)
        if camera is None or not camera.relay_allowed(request.query.get("token")):
            return web.Response(status=HTTPStatus.NOT_FOUND)
        session = async_get_clientsession(hass)
        try:
            upstream = await session.get(
                camera.printer_stream_url,
                timeout=aiohttp.ClientTimeout(total=None, sock_connect=10),
            )
        except (aiohttp.ClientError, TimeoutError):
            return web.Response(status=HTTPStatus.BAD_GATEWAY)
        headers: dict[str, Any] = {
            "Content-Type": upstream.headers.get("Content-Type", _DEFAULT_CONTENT_TYPE),
            "Cache-Control": "no-cache, no-store",
        }
        response = web.StreamResponse(status=HTTPStatus.OK, headers=headers)
        try:
            await response.prepare(request)
            async for chunk in upstream.content.iter_chunked(_CHUNK):
                await response.write(chunk)
        except (aiohttp.ClientError, ConnectionResetError, TimeoutError):
            _LOGGER.debug("Camera relay for %s ended", entity_id)
        finally:
            upstream.release()
        return response
