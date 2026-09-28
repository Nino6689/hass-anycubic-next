"""The cloud-sourced entities (BEHAVIOUR §2): values, attributes, cameras,
firmware updates, the job preview and resin printers."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from unittest.mock import patch

from anycubic_cloud_client import AgoraError, NoCameraCredentialsError
from homeassistant.components.camera import async_get_image
from homeassistant.components.camera.webrtc import (
    WebRTCAnswer,
    WebRTCError,
    WebRTCMessage,
)
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
import homeassistant.util.dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from webrtc_models import RTCIceCandidateInit

from custom_components.anycubic_cloud.placeholder import placeholder_png

from . import cloud_payloads as cp
from .cloud_fakes import FakeCloud
from .conftest import MockPrinter, account_entry, lan_entry, setup_entry

P = "kobra_s1_cloud"


@pytest.fixture
async def loaded(hass: HomeAssistant, cloud: FakeCloud) -> MockConfigEntry:
    return await setup_entry(hass, account_entry())


def _state(hass: HomeAssistant, entity_id: str) -> Any:
    state = hass.states.get(entity_id)
    assert state is not None, entity_id
    return state


async def test_status_and_job_attributes(
    hass: HomeAssistant, loaded: MockConfigEntry
) -> None:
    status = _state(hass, f"sensor.{P}_current_status")
    assert status.attributes["supported_functions"] == [
        "FILE_MANAGER",
        "FDM_AXIS_MOVE",
        "FDM_PEER_VIDEO",
        "TIME_LAPSE",
        "BOX_LIGHT",
        "MULTI_COLOR_BOX",
    ]
    assert status.attributes["total_material_used"] == "18.17kg"
    assert status.attributes["total_print_time_hrs"] == 798
    assert status.attributes["total_print_time_dhm"] == "33:6:29"
    assert status.attributes["model"] == "Anycubic Kobra S1"
    assert status.attributes["machine_type"] == cp.MACHINE_TYPE
    job = _state(hass, f"sensor.{P}_job_name")
    assert job.state == "benchy_PLA_0.2"
    assert job.attributes == job.attributes | {
        "file_name": "benchy_PLA_0.2.gcode",
        "source": "slicer",
        "slicer": "Slicer Next",
        "printer_profile": "Kobra S1 0.4",
        "layer_height": 0.2,
        "filament_types": ["PLA", "PETG"],
        "nozzle_temperature": 220,
        "fill_density": "15%",
        "travel_speed": 300,
        "model_size_mm": [60.0, 31.0, 48.0],
        "estimated_filament": 94.5,
        "created_timestamp": 1790000000,
        "finished_timestamp": None,
        "print_total_time": "2hour17min",
        "print_total_time_minutes": 137,
        "print_total_time_dhm": "0:2:17",
        "print_supplies_usage": 31783.0,
        "print_status_message": None,
    }
    # Slicer values of -1 or empty are left out.
    assert "bed_temperature" not in job.attributes
    assert "brim_type" not in job.attributes
    target = _state(hass, f"sensor.{P}_target_nozzle_temperature")
    assert target.state == "220.0"
    assert target.attributes == target.attributes | {
        "limit_min": 185.0,
        "limit_max": 320.0,
    }
    speed = _state(hass, f"sensor.{P}_job_speed_mode")
    assert speed.attributes["available_modes"] == [
        {"description": "Silent", "mode": 1},
        {"description": "Standard", "mode": 2},
        {"description": "Sport", "mode": 3},
    ]
    assert _state(hass, f"sensor.{P}_job_z_thickness").state == "0.2"
    assert _state(hass, f"sensor.{P}_total_material_used").state == "18.17"
    assert _state(hass, f"sensor.{P}_total_print_time").state == "798"
    assert _state(hass, f"sensor.{P}_total_print_count").state == "174"
    slot = _state(hass, f"sensor.{P}_ace_pro_ace_slot_2")
    assert slot.attributes["colors_hex"] == ["#FFC3FF"]
    assert slot.attributes["spool_loaded"] is True
    assert slot.attributes["consumables_percent"] == 0
    spools = _state(hass, f"sensor.{P}_ace_pro_ace_spools")
    assert spools.attributes["box_info"]["humidity"] == 12
    assert spools.attributes["box_info"]["feed_status"] == {
        "code": 200,
        "type": 1,
        "current_status": 0,
        "slot": 2,
    }
    assert spools.attributes["spool_info"][0]["icon_type"] == 0


async def test_finished_job(hass: HomeAssistant, cloud: FakeCloud) -> None:
    """§1.6: a finished job's ETA is its finish time; the job stays."""
    cloud.jobs = [cp.job(print_status=2, end_time=1790009999, remain_time=0)]
    await setup_entry(hass, account_entry())
    expected = dt_util.utc_from_timestamp(1790009999).isoformat()
    assert _state(hass, f"sensor.{P}_job_eta").state == expected
    assert _state(hass, f"sensor.{P}_job_state").state == "finished"
    assert _state(hass, f"binary_sensor.{P}_job_complete").state == STATE_ON


async def test_no_job(hass: HomeAssistant, cloud: FakeCloud) -> None:
    cloud.jobs = []
    await setup_entry(hass, account_entry())
    assert _state(hass, f"sensor.{P}_job_state").state == "idle"
    assert _state(hass, f"sensor.{P}_job_eta").state == STATE_UNAVAILABLE
    assert _state(hass, f"sensor.{P}_job_z_thickness").state == STATE_UNAVAILABLE
    assert _state(hass, f"image.{P}_job_preview").state == STATE_UNAVAILABLE


async def test_poll_does_not_move_a_finished_job_back(
    hass: HomeAssistant, loaded: MockConfigEntry, cloud: FakeCloud
) -> None:
    coordinator = loaded.runtime_data.primary
    from anycubic_cloud_client import Job, JobDetail

    from custom_components.anycubic_cloud import cloud_state

    printer = coordinator.printer
    cloud_state.apply_job(printer, Job.from_data(cp.job(print_status=2)), None)
    assert printer.job_complete
    cloud_state.apply_job(printer, Job.from_data(cp.job(print_status=1)), None)
    assert printer.job_complete
    # A new job replaces it.
    cloud_state.apply_job(
        printer, Job.from_data(cp.job(id=2, print_status=1)), JobDetail.from_data({})
    )
    assert printer.job_in_progress


async def test_job_preview(
    hass: HomeAssistant, loaded: MockConfigEntry, cloud: FakeCloud
) -> None:
    entity = hass.data["entity_components"]["image"].get_entity(
        f"image.{P}_job_preview"
    )
    assert entity.image_url == "https://cdn.example.invalid/preview.png"
    before = entity.image_last_updated
    entity._cached_image = object()
    # A job without an absolute URL uses the region's image base.
    cloud.jobs = [cp.job(img="")]
    loaded.runtime_data.cloud._next_due = None
    await loaded.runtime_data.primary.async_refresh()
    await hass.async_block_till_done()
    assert entity.image_url == (
        "https://workbentch.s3.us-east-2.amazonaws.com/relative/image/path.png"
    )
    assert entity._cached_image is None
    assert entity.image_last_updated > before


async def test_lan_only_entry_has_no_cloud_entities(
    hass: HomeAssistant, printer: MockPrinter
) -> None:
    """DECISIONS round 2, Q8: never created on LAN-only entries."""
    await setup_entry(hass, lan_entry())
    for entity_id in (
        "binary_sensor.anycubic_kobra_s1_mqtt_connection_active",
        "camera.anycubic_kobra_s1_cloud_camera",
        "image.anycubic_kobra_s1_job_preview",
        "sensor.anycubic_kobra_s1_file_list_cloud",
        "update.anycubic_kobra_s1_ace_pro_ace_firmware",
    ):
        assert hass.states.get(entity_id) is None, entity_id


async def test_resin_printer(hass: HomeAssistant, cloud: FakeCloud) -> None:
    """§2.11: resin sensors from the cloud job; no filament entities."""
    detail = cp.detail()
    detail["base"]["material_type"] = "resin"
    detail["multi_color_box"] = None
    detail["type_function_ids"] = [1, 2]
    cloud.printers[cp.PRINTER_ID] = detail
    cloud.jobs = [
        cp.job(
            settings=(
                '{"curr_layer": 3, "total_layers": 90, "model_hight": 41.5,'
                ' "anti_count": 4, "settings": {"on_time": 2.5, "off_time": 0.5,'
                ' "bottom_time": 30, "bottom_layers": 6, "z_up_height": 6,'
                ' "z_up_speed": 2, "z_down_speed": 3}}'
            )
        )
    ]
    await setup_entry(hass, account_entry())
    assert _state(hass, f"sensor.{P}_job_on_time").state == "2.5"
    assert _state(hass, f"sensor.{P}_job_off_time").state == "0.5"
    assert _state(hass, f"sensor.{P}_job_bottom_time").state == "30"
    assert (
        _state(hass, f"sensor.{P}_job_bottom_layers").attributes["unit_of_measurement"]
        == "Layers"
    )
    assert _state(hass, f"sensor.{P}_job_model_height").state == "41.5"
    assert _state(hass, f"sensor.{P}_job_anti_alias").state == "4"
    assert _state(hass, f"sensor.{P}_job_z_up_height").state == "6"
    assert _state(hass, f"sensor.{P}_job_z_up_speed").state == "2"
    assert _state(hass, f"sensor.{P}_job_z_down_speed").state == "3"
    assert hass.states.get(f"sensor.{P}_nozzle_temperature") is None
    assert hass.states.get(f"button.{P}_home_all_axes") is None


async def test_firmware(
    hass: HomeAssistant, loaded: MockConfigEntry, cloud: FakeCloud
) -> None:
    """§2.17, V17: no update offered - the installed version is the latest."""
    fw = _state(hass, f"update.{P}_printer_firmware")
    assert fw.state == STATE_OFF
    assert fw.attributes["installed_version"] == "2.7.2.7"
    assert fw.attributes["latest_version"] == "2.7.2.7"
    ace = _state(hass, f"update.{P}_ace_pro_ace_firmware")
    assert ace.attributes["installed_version"] == "1.3.863"
    # Install with nothing offered does nothing.
    entity = hass.data["domain_entities"]["update"][f"update.{P}_printer_firmware"]
    await entity.async_install(None, False)
    assert "update_printer_firmware" not in cloud.order_names()


async def test_firmware_install_and_progress(
    hass: HomeAssistant, cloud: FakeCloud
) -> None:
    detail = cp.detail()
    detail["version"] |= {"need_update": 1, "target_version": "2.8.0.0"}
    detail["multi_color_box_version"][0] |= {
        "need_update": 1,
        "target_version": "1.4.0",
    }
    cloud.printers[cp.PRINTER_ID] = detail
    await setup_entry(hass, account_entry())
    entity = f"update.{P}_printer_firmware"
    assert _state(hass, entity).state == STATE_ON
    assert _state(hass, entity).attributes["latest_version"] == "2.8.0.0"
    await hass.services.async_call(
        "update", "install", {"entity_id": entity}, blocking=True
    )
    assert "update_printer_firmware" in cloud.order_names()
    assert cloud.link.connects == 1  # woke the link for the progress
    cloud.feed(cp.mqtt("ota", "update", "downloading", {"progress": 40}))
    await hass.async_block_till_done(wait_background_tasks=True)
    state = _state(hass, entity)
    assert state.attributes["in_progress"] is True
    assert state.attributes["update_percentage"] == 20
    cloud.feed(cp.mqtt("ota", "update", "updating", {"current_progress": 50}))
    await hass.async_block_till_done(wait_background_tasks=True)
    assert _state(hass, entity).attributes["update_percentage"] == 75
    cloud.feed(cp.mqtt("ota", "reportVersion", "done", {"firmware_version": "2.8.0.0"}))
    await hass.async_block_till_done(wait_background_tasks=True)
    state = _state(hass, entity)
    assert state.attributes["in_progress"] is False
    assert state.attributes["installed_version"] == "2.8.0.0"
    ace = f"update.{P}_ace_pro_ace_firmware"
    await hass.services.async_call(
        "update", "install", {"entity_id": ace}, blocking=True
    )
    assert "update_ace_firmware" in cloud.order_names()


class FakeSession:
    """Stands in for anycubic-cloud-client's ``AgoraCameraSession``."""

    sessions: list[FakeSession] = []
    error: Exception | None = None

    def __init__(self, http: Any, credentials: Any, *, on_close: Any = None) -> None:
        self.credentials = credentials
        self.candidates: list[str] = []
        self.on_close = on_close
        self.closed = False
        FakeSession.sessions.append(self)

    def add_ice_candidate(self, candidate: str) -> None:
        self.candidates.append(candidate)

    async def answer(self, offer: str, session_id: str) -> str:
        if FakeSession.error is not None:
            raise FakeSession.error
        return f"answer-to-{offer}"

    async def close(self) -> None:
        self.closed = True
        if self.on_close:
            self.on_close("closed")


@pytest.fixture
def agora() -> Iterator[type[FakeSession]]:
    FakeSession.sessions = []
    FakeSession.error = None
    with patch(
        "custom_components.anycubic_cloud.camera.AgoraCameraSession", FakeSession
    ):
        yield FakeSession


async def _offer(hass: HomeAssistant, session_id: str = "s1") -> list[WebRTCMessage]:
    camera = hass.data["domain_entities"]["camera"][f"camera.{P}_cloud_camera"]
    messages: list[WebRTCMessage] = []
    await camera.async_handle_async_webrtc_offer("offer", session_id, messages.append)
    return messages


async def test_cloud_camera(
    hass: HomeAssistant,
    loaded: MockConfigEntry,
    cloud: FakeCloud,
    agora: type[FakeSession],
) -> None:
    assert _state(hass, f"camera.{P}_cloud_camera").state != STATE_UNAVAILABLE
    camera = hass.data["domain_entities"]["camera"][f"camera.{P}_cloud_camera"]
    # A candidate before the offer is kept for the session.
    await camera.async_on_webrtc_candidate("s1", RTCIceCandidateInit("cand-1"))
    (message,) = await _offer(hass)
    assert isinstance(message, WebRTCAnswer)
    assert message.answer == "answer-to-offer"
    (session,) = agora.sessions
    assert session.candidates == ["cand-1"]
    assert session.credentials.client_uid == 6001
    await camera.async_on_webrtc_candidate("s1", RTCIceCandidateInit("cand-2"))
    assert session.candidates == ["cand-1", "cand-2"]
    # Fresh credentials for every session.
    await _offer(hass, "s2")
    assert cloud.order_names().count("open_camera") == 2
    camera.close_webrtc_session("s1")
    await hass.async_block_till_done()
    assert session.closed
    image = await async_get_image(hass, f"camera.{P}_cloud_camera")
    assert image.content == placeholder_png()
    assert placeholder_png().startswith(b"\x89PNG")


async def test_cloud_camera_failures(
    hass: HomeAssistant,
    loaded: MockConfigEntry,
    cloud: FakeCloud,
    agora: type[FakeSession],
) -> None:
    cloud.camera = NoCameraCredentialsError("none")
    (message,) = await _offer(hass)
    assert isinstance(message, WebRTCError)
    assert message.code == "no_camera"
    cloud.camera = __import__("anycubic_cloud_client").ServiceUnavailableError("down")
    (message,) = await _offer(hass)
    assert message.code == "cloud_error"
    cloud.camera = cp.camera_reply()
    agora.error = AgoraError("no gateway")
    (message,) = await _offer(hass)
    assert message.code == "agora_error"
    assert "no gateway" in message.message


async def test_cloud_camera_availability(
    hass: HomeAssistant, loaded: MockConfigEntry, cloud: FakeCloud
) -> None:
    """Unavailable once the printer says it has no camera (§2.18)."""
    cloud.printers[cp.PRINTER_ID]["is_printing"] = 2
    loaded.runtime_data.cloud._next_due = None
    await loaded.runtime_data.primary.async_refresh()
    await hass.async_block_till_done()
    cloud.feed(cp.mqtt("peripherie", "query", "done", {"camera": 0}))
    await hass.async_block_till_done(wait_background_tasks=True)
    assert _state(hass, f"camera.{P}_cloud_camera").state == STATE_UNAVAILABLE


async def test_cloud_camera_removed_closes_sessions(
    hass: HomeAssistant,
    loaded: MockConfigEntry,
    agora: type[FakeSession],
) -> None:
    await _offer(hass)
    await hass.config_entries.async_unload(loaded.entry_id)
    await hass.async_block_till_done()
    assert agora.sessions[0].closed
