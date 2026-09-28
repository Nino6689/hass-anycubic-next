"""The printer camera (BEHAVIOUR §2.18)."""

from __future__ import annotations

from http import HTTPStatus
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from anycubic_lan import NotConnectedError
from homeassistant.components.camera import async_get_image, async_get_stream_source
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.setup import async_setup_component
import pytest
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from . import payloads
from .conftest import MockPrinter, lan_entry, setup_entry

CAMERA = "camera.anycubic_kobra_s1_camera"
STREAM = f"http://{payloads.HOST}:18088/flv"


async def test_stream_source_starts_capture(
    hass: HomeAssistant, printer: MockPrinter
) -> None:
    await setup_entry(hass, lan_entry())
    assert hass.states.get(CAMERA).state == "idle"
    assert await async_get_stream_source(hass, CAMERA) == STREAM
    assert printer.client.commands[-1] == ("video", "startCapture", {})

    # A failed start request is not fatal.
    printer.client.is_connected = False
    printer.client.restore = lambda: None  # type: ignore[method-assign]
    printer.client.is_connected = True
    with patch.object(printer.client, "send_command", side_effect=NotConnectedError):
        assert await async_get_stream_source(hass, CAMERA) == STREAM


async def test_default_url_and_availability(
    hass: HomeAssistant, printer: MockPrinter
) -> None:
    printer.connect_payloads[0] = payloads.info(urls={})
    await setup_entry(hass, lan_entry())
    assert await async_get_stream_source(hass, CAMERA) == STREAM
    printer.client.lose()
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get(CAMERA).state == STATE_UNAVAILABLE


async def test_still_comes_from_the_stream(
    hass: HomeAssistant, printer: MockPrinter
) -> None:
    """B24: never a second connection for a still."""
    entry = await setup_entry(hass, lan_entry())
    with pytest.raises(HomeAssistantError):
        await async_get_image(hass, CAMERA)
    camera = hass.data["camera"].get_entity(CAMERA)
    stream = MagicMock()
    stream.async_get_image = AsyncMock(return_value=b"jpeg")
    camera.stream = stream
    image = await async_get_image(hass, CAMERA)
    assert image.content == b"jpeg"
    assert entry.state.value == "loaded"


async def test_kobra_x_relay(
    hass: HomeAssistant,
    printer: MockPrinter,
    hass_client_no_auth: Any,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """B25: the Kobra X stream is relayed with status 200."""
    printer.info = payloads.connection_info(model_id=20030)
    assert await async_setup_component(hass, "http", {})
    await setup_entry(hass, lan_entry())
    source = await async_get_stream_source(hass, CAMERA)
    assert source is not None
    assert (
        "/api/anycubic_cloud/camera_relay/camera.anycubic_kobra_s1_camera?token="
        in source
    )
    path = source[source.index("/api/") :]

    aioclient_mock.get(
        STREAM,
        status=HTTPStatus.PARTIAL_CONTENT,
        content=b"FLV-bytes",
        headers={"Content-Type": "video/x-flv"},
    )
    client = await hass_client_no_auth()
    response = await client.get(path)
    assert response.status == HTTPStatus.OK
    assert await response.read() == b"FLV-bytes"
    assert response.headers["Cache-Control"] == "no-cache, no-store"

    bad = await client.get(path.split("?")[0] + "?token=wrong")
    assert bad.status == HTTPStatus.NOT_FOUND
    missing = await client.get("/api/anycubic_cloud/camera_relay/camera.nope?token=x")
    assert missing.status == HTTPStatus.NOT_FOUND

    aioclient_mock.clear_requests()
    aioclient_mock.get(STREAM, exc=TimeoutError())
    failed = await client.get(path)
    assert failed.status == HTTPStatus.BAD_GATEWAY


async def test_kobra_x_relay_without_internal_url(
    hass: HomeAssistant, printer: MockPrinter
) -> None:
    printer.info = payloads.connection_info(model_id=20030)
    await setup_entry(hass, lan_entry())
    from homeassistant.helpers.network import NoURLAvailableError

    with patch(
        "custom_components.anycubic_cloud.camera.get_url",
        side_effect=NoURLAvailableError,
    ):
        source = await async_get_stream_source(hass, CAMERA)
    assert source is not None
    assert source.startswith("http://127.0.0.1:8123/api/anycubic_cloud/")
