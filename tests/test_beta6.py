"""Beta 6: field reports from 2026-10-27 to 2026-11-10 (ACCEPTANCE.md D26-D32).

Each test is named after the item it accepts. Printer messages run through
anycubic-cloud-client's own parser (the fake account). The Kinesis Video
signalling itself (SigV4, the websocket flow) is tested in that library
against AWS's published examples and a fake websocket; here the camera's
use of it is tested with a stand-in session. D32 is tested in
``frontend/tests/format.test.ts``.
"""

from __future__ import annotations

import json
import logging
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from anycubic_cloud_client import (
    IceCandidate,
    KinesisCredentials,
    KinesisError,
    NoCameraCredentialsError,
    PaintInfo,
)
from anycubic_cloud_client.client import INCOMPLETE_CAMERA_MESSAGE
from anycubic_lan import AceSlot
from homeassistant.components.camera.webrtc import (
    WebRTCAnswer,
    WebRTCCandidate,
    WebRTCError,
    WebRTCMessage,
)
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr, entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from webrtc_models import RTCIceCandidateInit

from custom_components.anycubic_cloud import async_remove_config_entry_device
from custom_components.anycubic_cloud.const import DOMAIN
from custom_components.anycubic_cloud.energy import (
    EnergyMeter,
    EnergySettings,
    job_key,
    reading_kwh,
)
from custom_components.anycubic_cloud.filament import grams_from_length
from custom_components.anycubic_cloud.model import paint_slot_map

from . import cloud_payloads as cp
from .cloud_fakes import FakeCloud
from .conftest import account_entry, find_device, setup_entry

C = "kobra_s1_cloud"
LENGTH = 31783  # the job's extruded millimetres (cloud_payloads.job)
# The fake ACE's slot colours: slot i is [255, 255 - 60 * i, 255].
WHITE, PINK1, PINK2, PINK3 = (
    (255, 255, 255),
    (255, 195, 255),
    (255, 135, 255),
    (
        255,
        75,
        255,
    ),
)


async def _settle(hass: HomeAssistant) -> None:
    await hass.async_block_till_done(wait_background_tasks=True)


def _state(hass: HomeAssistant, entity_id: str) -> str:
    state = hass.states.get(entity_id)
    assert state is not None, entity_id
    return state.state


def _no_warnings(caplog: pytest.LogCaptureFixture) -> None:
    noisy = [
        r
        for r in caplog.records
        if r.levelno >= logging.WARNING and "turbojpeg" not in r.getMessage()
    ]
    assert not noisy, [r.getMessage() for r in noisy]


async def _cloud(hass: HomeAssistant, **options: Any) -> MockConfigEntry:
    entry = account_entry()
    return await setup_entry(
        hass,
        account_entry(options={**entry.options, "mqtt_connect_mode": 4, **options}),
    )


async def _poll(entry: MockConfigEntry) -> None:
    entry.runtime_data.cloud._next_due = None
    await entry.runtime_data.primary.async_refresh()


async def _finish(
    hass: HomeAssistant, entry: MockConfigEntry, cloud: FakeCloud
) -> None:
    cloud.jobs[0]["print_status"] = 2
    await _poll(entry)
    await _settle(hass)


def _entity(hass: HomeAssistant, entry: MockConfigEntry, key: str) -> str | None:
    for item in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id):
        if item.unique_id.endswith(f"-{key}"):
            return item.entity_id
    return None


def _paint(index: int, grams: float, color: Any, material: str | None = "PLA") -> dict:
    paint: dict[str, Any] = {"paint_index": index, "filament_used": grams}
    if color is not None:
        paint["paint_color"] = list(color)
    if material is not None:
        paint["material_type"] = material
    return paint


def _slice(*paints: dict[str, Any]) -> str:
    return json.dumps({"paint_infos": list(paints)})


def _slots(entry: MockConfigEntry) -> dict[str, Any]:
    return entry.runtime_data.ledger.data["printers"][str(cp.PRINTER_ID)]["slots"]


def _used(entry: MockConfigEntry, index: int) -> float:
    return float(_slots(entry).get(str(index), {}).get("filament_used_g", 0.0))


def _grams(share: float) -> float:
    return round(grams_from_length(LENGTH * share, "PLA"), 2)


# -- D26: a slice-parameter reply is read, not reported as an error ------------------

SLICE_REPLY = {
    "ams_settings": {"use_ams": True},
    "file_key": "0123abcd",
    "taskid": str(cp.JOB_ID),
    "slice_param": {
        "bed_temperature": 60,
        "brim_type": "auto_brim",
        "filament_retract_length": 0.8,
        "filament_type": ";PLA",
        "fill_density": "15%",
        "layer_height": 0.2,
        "paint_infos": [
            _paint(0, 30.0, PINK2, ";PLA"),
            _paint(1, 10.0, WHITE, "pla "),
        ],
        "perimeter_speed": 200,
        "printer_settings_id": "Anycubic Kobra 3",
        "remain_time": 60,
        "size_x": 1,
        "size_y": 2,
        "size_z": 3,
        "support_material_auto": True,
        "temperature": 210,
        "travel_speed": 300,
        "a_key_nobody_knows": {"x": [1]},
    },
}


async def test_d26_slice_param_reply_is_quiet(
    hass: HomeAssistant, cloud: FakeCloud, caplog: pytest.LogCaptureFixture
) -> None:
    cloud.jobs = [cp.job(slice_param=json.dumps({"layer_height": 0.2}))]
    entry = await _cloud(hass)
    caplog.clear()
    caplog.set_level(logging.DEBUG)
    cloud.feed(cp.mqtt("print", "getSliceParam", "done", SLICE_REPLY))
    await _settle(hass)
    _no_warnings(caplog)
    assert "not understood" not in caplog.text
    printer = entry.runtime_data.primary.printer
    assert printer.cloud is not None
    assert printer.cloud.faults == {}
    # Its breakdown is the running job's (the job's own slice data has none).
    assert [p.paint_index for p in printer.job_paints] == [0, 1]
    assert printer.job_paint_shares == {0: 0.75, 1: 0.25}


async def test_d26_reply_for_another_task_is_not_this_job(
    hass: HomeAssistant, cloud: FakeCloud
) -> None:
    cloud.jobs = [cp.job(slice_param=json.dumps({}))]
    entry = await _cloud(hass)
    printer = entry.runtime_data.primary.printer
    cloud.feed(cp.mqtt("print", "getSliceParam", "done", SLICE_REPLY | {"taskid": "9"}))
    await _settle(hass)
    assert printer.job_paints == ()
    # A reply that names no task serves the running job.
    untagged = {k: v for k, v in SLICE_REPLY.items() if k != "taskid"}
    cloud.feed(cp.mqtt("print", "getSliceParam", "done", untagged))
    await _settle(hass)
    assert len(printer.job_paints) == 2


async def test_d26_the_jobs_own_breakdown_wins(
    hass: HomeAssistant, cloud: FakeCloud
) -> None:
    entry = await _cloud(hass)
    cloud.feed(cp.mqtt("print", "getSliceParam", "done", SLICE_REPLY))
    await _settle(hass)
    printer = entry.runtime_data.primary.printer
    # cloud_payloads.job carries one paint of 94.5 g.
    assert [p.filament_used for p in printer.job_paints] == [94.5]


async def test_d26_d29_pushed_breakdown_charges_by_colour(
    hass: HomeAssistant, cloud: FakeCloud
) -> None:
    cloud.jobs = [cp.job(slice_param=json.dumps({}))]
    entry = await _cloud(hass)
    cloud.feed(cp.mqtt("print", "getSliceParam", "done", SLICE_REPLY))
    await _settle(hass)
    await _poll(entry)  # the ledger sees the job running with its breakdown
    await _finish(hass, entry, cloud)
    # paint 0 (pink 2, 75 %) sits in slot 2, paint 1 (white) in slot 0.
    assert _used(entry, 2) == _grams(0.75)
    assert _used(entry, 0) == _grams(0.25)
    assert _used(entry, 1) == 0.0


# -- D27: the cloud camera over Kinesis Video --------------------------------------

TOKEN = {
    "region": "eu-west-3",
    "tmpSecretId": "ASIAFAKEKEYID000",
    "tmpSecretKey": "fakeSecretKey/000",
    "sessionToken": "fakeSessionToken000",
    "expiration": 1790000000,
}


class FakeKinesis:
    """Stands in for anycubic-cloud-client's ``KinesisViewerSession``."""

    sessions: list[FakeKinesis] = []
    error: Exception | None = None

    def __init__(self, http: Any, credentials: Any, channel: str, **kw: Any) -> None:
        self.credentials = credentials
        self.channel = channel
        self.kw = kw
        self.video_states: list[str | None] = [kw.get("video_state")]
        self.candidates: list[IceCandidate] = []
        self.offer: str | None = None
        self.closed = False
        FakeKinesis.sessions.append(self)

    def notify_video_state(self, state: str | None) -> None:
        self.video_states.append(state)

    def add_ice_candidate(self, candidate: IceCandidate) -> None:
        self.candidates.append(candidate)

    async def start(self, offer: str) -> None:
        if FakeKinesis.error is not None:
            raise FakeKinesis.error
        self.offer = offer

    async def close(self) -> None:
        self.closed = True
        self.kw["on_close"]("closed")


@pytest.fixture
def kinesis() -> Any:
    FakeKinesis.sessions = []
    FakeKinesis.error = None
    with patch(
        "custom_components.anycubic_cloud.camera.KinesisViewerSession", FakeKinesis
    ):
        yield FakeKinesis


def _camera(hass: HomeAssistant) -> Any:
    return hass.data["domain_entities"]["camera"][f"camera.{C}_cloud_camera"]


async def _offer(hass: HomeAssistant, session_id: str = "s1") -> list[WebRTCMessage]:
    messages: list[WebRTCMessage] = []
    await _camera(hass).async_handle_async_webrtc_offer(
        "offer-sdp", session_id, messages.append
    )
    return messages


async def test_d27_token_only_streams_over_kinesis(
    hass: HomeAssistant, cloud: FakeCloud, kinesis: Any
) -> None:
    entry = await _cloud(hass)
    coordinator = entry.runtime_data.primary
    cloud.camera = {"msgid": "m", "token": dict(TOKEN)}
    # An earlier video state is forgotten when the order is sent (D28).
    cloud.feed(cp.mqtt("video", "startCapture", "pushStopped"))
    await _settle(hass)
    camera = _camera(hass)
    await camera.async_on_webrtc_candidate(
        "s1", RTCIceCandidateInit("cand-early", sdp_mid="0", sdp_m_line_index=0)
    )
    messages = await _offer(hass)
    assert messages == []  # the answer comes later, from the printer
    (session,) = kinesis.sessions
    assert isinstance(session.credentials, KinesisCredentials)
    assert session.channel == cp.PRINTER_KEY  # the channel is the printer's key
    assert session.offer == "offer-sdp"
    assert session.video_states == [None]
    assert session.candidates == [IceCandidate("cand-early", "0", 0)]
    # The printer's video reports reach the session.
    cloud.feed(cp.mqtt("video", "startCapture", "initSuccess"))
    cloud.feed(cp.mqtt("video", "startCapture", "pushStarted"))
    await _settle(hass)
    assert session.video_states == [None, "initSuccess", "pushStarted"]
    assert coordinator.printer.cloud.video_state == "pushStarted"
    # Answer and candidates go back to the browser; browser candidates out.
    session.kw["on_answer"]("answer-sdp")
    session.kw["on_candidate"](IceCandidate("cand-printer", "0", 0))
    session.kw["on_error"]("The printer reported pushFailed")
    sent: list[WebRTCMessage] = []
    await camera.async_on_webrtc_candidate(
        "s1", RTCIceCandidateInit("cand-late", sdp_mid="1", sdp_m_line_index=1)
    )
    assert session.candidates[-1] == IceCandidate("cand-late", "1", 1)
    assert sent == []
    # Closing ends the session and stops the video reports reaching it.
    camera.close_webrtc_session("s1")
    await _settle(hass)
    assert session.closed
    assert not coordinator.video_listeners
    cloud.feed(cp.mqtt("video", "startCapture", "pushStopped"))
    await _settle(hass)
    assert session.video_states[-1] == "pushStarted"


async def test_d27_messages_to_the_browser(
    hass: HomeAssistant, cloud: FakeCloud, kinesis: Any
) -> None:
    await _cloud(hass)
    cloud.camera = {"msgid": "m", "token": dict(TOKEN)}
    messages = await _offer(hass)
    (session,) = kinesis.sessions
    session.kw["on_answer"]("answer-sdp")
    session.kw["on_candidate"](IceCandidate("cand-printer", "0", 0))
    session.kw["on_error"]("The printer reported initFailed")
    answer, candidate, error = messages
    assert isinstance(answer, WebRTCAnswer)
    assert answer.answer == "answer-sdp"
    assert isinstance(candidate, WebRTCCandidate)
    assert candidate.candidate.candidate == "cand-printer"
    assert candidate.candidate.sdp_mid == "0"
    assert isinstance(error, WebRTCError)
    assert error.code == "kinesis_error"
    assert "initFailed" in error.message


async def test_d27_agora_wins_when_both_come_back(
    hass: HomeAssistant, cloud: FakeCloud, kinesis: Any
) -> None:
    await _cloud(hass)
    cloud.camera = cp.camera_reply() | {"token": dict(TOKEN)}
    with patch("custom_components.anycubic_cloud.camera.AgoraCameraSession") as agora:
        agora.return_value.answer.return_value = "agora-answer"
        agora.return_value.answer.side_effect = None

        async def answer(*_args: Any) -> str:
            return "agora-answer"

        agora.return_value.answer = answer
        messages = await _offer(hass)
    assert kinesis.sessions == []
    (message,) = messages
    assert isinstance(message, WebRTCAnswer)
    assert message.answer == "agora-answer"


async def test_d27_aws_refusal_is_named(
    hass: HomeAssistant,
    cloud: FakeCloud,
    kinesis: Any,
    caplog: pytest.LogCaptureFixture,
) -> None:
    entry = await _cloud(hass)
    cloud.camera = {"msgid": "m", "token": dict(TOKEN)}
    kinesis.error = KinesisError(
        "Amazon Kinesis Video refused the camera: The security token included "
        "in the request is expired"
    )
    caplog.set_level(logging.DEBUG)
    (message,) = await _offer(hass)
    assert isinstance(message, WebRTCError)
    assert message.code == "kinesis_error"
    assert "security token included in the request is expired" in message.message
    assert not entry.runtime_data.primary.video_listeners
    for secret in TOKEN.values():
        if isinstance(secret, str) and secret != "eu-west-3":
            assert secret not in caplog.text
            assert secret not in message.message


async def test_d27_incomplete_and_missing_credentials(
    hass: HomeAssistant, cloud: FakeCloud, kinesis: Any
) -> None:
    await _cloud(hass)
    cloud.camera = NoCameraCredentialsError(INCOMPLETE_CAMERA_MESSAGE)
    (message,) = await _offer(hass)
    assert message.code == "no_camera"
    assert "incomplete" in message.message
    assert "another Anycubic session" not in message.message
    cloud.camera = NoCameraCredentialsError("none")
    (message,) = await _offer(hass)
    assert "no camera credentials" in message.message
    assert kinesis.sessions == []


async def test_d27_needs_the_printer_key(
    hass: HomeAssistant, cloud: FakeCloud, kinesis: Any
) -> None:
    entry = await _cloud(hass)
    entry.runtime_data.primary.printer.identity.key = None
    cloud.camera = {"msgid": "m", "token": dict(TOKEN)}
    (message,) = await _offer(hass)
    assert message.code == "no_camera"
    assert kinesis.sessions == []


async def test_d27_sessions_closed_with_the_entity(
    hass: HomeAssistant, cloud: FakeCloud, kinesis: Any
) -> None:
    entry = await _cloud(hass)
    cloud.camera = {"msgid": "m", "token": dict(TOKEN)}
    await _offer(hass)
    await hass.config_entries.async_unload(entry.entry_id)
    await _settle(hass)
    assert kinesis.sessions[0].closed


# -- D28: the printer's video reports are read ----------------------------------------


async def test_d28_video_reports_are_quiet(
    hass: HomeAssistant, cloud: FakeCloud, caplog: pytest.LogCaptureFixture
) -> None:
    entry = await _cloud(hass)
    caplog.clear()
    caplog.set_level(logging.DEBUG)
    printer = entry.runtime_data.primary.printer
    for state in ("initSuccess", "pushStarted", "pushStopped", "pushFailed"):
        cloud.feed(cp.mqtt("video", "startCapture", state))
        await _settle(hass)
        assert printer.cloud.video_state == state
    cloud.feed(cp.mqtt("video", "startCapture", "initFailed", code=10001, msg="x"))
    await _settle(hass)
    assert printer.cloud.video_state == "initFailed"
    _no_warnings(caplog)
    assert "not understood" not in caplog.text


# -- D29: a multi-colour job's filament goes to the slot holding each colour ---------


def _ace_slots(*specs: tuple[tuple[int, int, int] | None, str | None, int]) -> list:
    return [
        (index, AceSlot(index=index, material=material, color=color, edit_status=edit))
        for index, (color, material, edit) in enumerate(specs)
    ]


FOUR = _ace_slots(
    (WHITE, "PLA", 0), (PINK1, "PLA", 0), (PINK2, "PETG", 0), (PINK3, "PLA", 0)
)


def _paints(*specs: tuple[int, float, Any, str | None]) -> list[PaintInfo]:
    out = []
    for index, grams, color, material in specs:
        info = PaintInfo.from_data(_paint(index, grams, color, material))
        assert info is not None
        out.append(info)
    return out


@pytest.mark.parametrize(
    ("paints", "slots", "expected"),
    [
        # Colour and material decide, not the order of the slicer's list.
        (_paints((0, 5, PINK3, "PLA"), (1, 5, WHITE, "PLA")), FOUR, {0: 3, 1: 0}),
        # Case, spaces and a stray ";" do not count.
        (_paints((0, 5, PINK2, " ;petg"), (1, 5, PINK1, "Pla")), FOUR, {0: 2, 1: 1}),
        # An unnamed material on either side matches any.
        (_paints((0, 5, PINK2, None), (1, 5, PINK1, "")), FOUR, {0: 2, 1: 1}),
        (
            _paints((0, 5, PINK2, "PLA"), (1, 5, WHITE, "PLA")),
            _ace_slots((WHITE, None, 0), (PINK1, "PLA", 0), (PINK2, None, 0)),
            {0: 2, 1: 0},
        ),
        # A material mismatch: no slot for paint 0, so no mapping.
        (_paints((0, 5, PINK2, "PLA"), (1, 5, WHITE, "PLA")), FOUR, None),
        # A colour no slot holds.
        (_paints((0, 5, (1, 2, 3), "PLA"), (1, 5, WHITE, "PLA")), FOUR, None),
        # A paint without a colour.
        (_paints((0, 5, None, "PLA"), (1, 5, WHITE, "PLA")), FOUR, None),
        # Two materials in one slot.
        (_paints((0, 5, WHITE, "PLA"), (1, 5, WHITE, None)), FOUR, None),
        # Two slots of the same colour and material: paint_index decides when
        # it is one of them, else nothing does.
        (
            _paints((1, 5, WHITE, "PLA"), (2, 5, PINK2, "PLA")),
            _ace_slots((WHITE, "PLA", 0), (WHITE, "PLA", 0), (PINK2, "PLA", 0)),
            {1: 1, 2: 2},
        ),
        (
            _paints((3, 5, WHITE, "PLA"), (2, 5, PINK2, "PLA")),
            _ace_slots((WHITE, "PLA", 0), (WHITE, "PLA", 0), (PINK2, "PLA", 0)),
            None,
        ),
        # Empty slots are not candidates.
        (
            _paints((0, 5, WHITE, "PLA"), (1, 5, PINK1, "PLA")),
            _ace_slots((WHITE, "PLA", 2), (PINK1, "PLA", 0), (WHITE, "PLA", 0)),
            {0: 2, 1: 1},
        ),
        # Entries without filament are not materials of the job.
        (
            _paints(
                (0, 5, PINK3, "PLA"), (1, 0, (9, 9, 9), "PLA"), (2, 5, WHITE, None)
            ),
            FOUR,
            {0: 3, 2: 0},
        ),
        (_paints((0, 0, WHITE, "PLA")), FOUR, None),
    ],
)
def test_d29_slot_map(
    paints: list[PaintInfo], slots: list, expected: dict[int, int] | None
) -> None:
    assert paint_slot_map(paints, slots) == expected


async def test_d29_job_charged_to_the_slots_holding_its_colours(
    hass: HomeAssistant, cloud: FakeCloud
) -> None:
    """Paint 0 is pink 3 (slot 3), paint 1 white (slot 0): split by
    ``paint_index`` they would have gone to slots 0 and 1 (#47)."""
    cloud.jobs = [
        cp.job(slice_param=_slice(_paint(0, 30, PINK3), _paint(1, 10, WHITE)))
    ]
    entry = await _cloud(hass)
    await _finish(hass, entry, cloud)
    assert _used(entry, 3) == _grams(0.75)
    assert _used(entry, 0) == _grams(0.25)
    assert _used(entry, 1) == 0.0


async def test_d29_no_clean_match_splits_by_paint_index(
    hass: HomeAssistant, cloud: FakeCloud
) -> None:
    cloud.jobs = [
        cp.job(slice_param=_slice(_paint(0, 30, PINK3), _paint(1, 10, (1, 2, 3))))
    ]
    entry = await _cloud(hass)
    await _finish(hass, entry, cloud)
    assert _used(entry, 0) == _grams(0.75)
    assert _used(entry, 1) == _grams(0.25)
    assert _used(entry, 3) == 0.0


async def test_d29_single_material_job_unchanged(
    hass: HomeAssistant, cloud: FakeCloud
) -> None:
    """One material: the slot that fed it (D24), whatever its colour."""
    cloud.jobs = [cp.job(slice_param=_slice(_paint(0, 30, PINK3)))]
    entry = await _cloud(hass)
    await _finish(hass, entry, cloud)
    assert _used(entry, 1) == _grams(1.0)  # the fake ACE's loaded slot
    assert _used(entry, 3) == 0.0


# -- D30: Kobra X filament boxes -----------------------------------------------


def _kobra_x(cloud: FakeCloud) -> None:
    cloud.printers[cp.PRINTER_ID]["machine_type"] = 20030
    cloud.printers[cp.PRINTER_ID]["multi_color_box"] = [
        cp.ace_box(0, model_id=None),
        cp.ace_box(1, model_id=40002),
    ]


def _step(state: str, **data: Any) -> dict[str, Any]:
    return cp.mqtt("print", "start", state, {"taskid": cp.JOB_ID, **data})


async def test_d30_feeder_and_ace_devices(
    hass: HomeAssistant, cloud: FakeCloud
) -> None:
    _kobra_x(cloud)
    await _cloud(hass)
    feeder = find_device(hass, f"{cp.USER_ID}-{cp.PRINTER_ID}-ace0")
    ace = find_device(hass, f"{cp.USER_ID}-{cp.PRINTER_ID}-ace1")
    assert feeder is not None
    assert ace is not None
    assert feeder.name == "Kobra S1 Cloud Feeder"
    assert feeder.model == "Built-in feeder"
    assert ace.name == "Kobra S1 Cloud ACE 2 Pro"
    assert ace.model == "ACE 2 Pro"


async def test_d30_feeding_steps_mark_their_box(
    hass: HomeAssistant, cloud: FakeCloud
) -> None:
    _kobra_x(cloud)
    await _cloud(hass)
    feeder = f"sensor.{C}_feeder_ace_loaded_slot"
    ace = f"sensor.{C}_ace_2_pro_secondary_ace_loaded_slot"
    cloud.feed(_step("extfilbox_filament_feeding", channel_no=3))
    await _settle(hass)
    assert (_state(hass, feeder), _state(hass, ace)) == ("3", STATE_UNAVAILABLE)
    cloud.feed(_step("ace_filament_feeding", channel_no=4, unit_no=1))
    await _settle(hass)
    assert (_state(hass, feeder), _state(hass, ace)) == (STATE_UNAVAILABLE, "4")
    # A progress update with a channel but no unit guesses nothing.
    cloud.feed(cp.mqtt("print", "update", "updated", {"channel_no": 1}))
    await _settle(hass)
    assert (_state(hass, feeder), _state(hass, ace)) == (STATE_UNAVAILABLE, "4")


async def test_d30_ace_2_pro_everywhere(hass: HomeAssistant, cloud: FakeCloud) -> None:
    cloud.printers[cp.PRINTER_ID]["multi_color_box"] = [cp.ace_box(0, model_id=40002)]
    await _cloud(hass)
    ace = find_device(hass, f"{cp.USER_ID}-{cp.PRINTER_ID}-ace0")
    assert ace is not None
    assert ace.model == "ACE 2 Pro"
    assert ace.name == "Kobra S1 Cloud ACE 2 Pro"


async def test_d30_only_devices_no_longer_reported_can_be_deleted(
    hass: HomeAssistant, cloud: FakeCloud
) -> None:
    entry = await _cloud(hass)
    registry = dr.async_get(hass)
    printer = find_device(hass, f"{cp.USER_ID}-{cp.PRINTER_ID}")
    ace = find_device(hass, f"{cp.USER_ID}-{cp.PRINTER_ID}-ace0")
    assert printer is not None
    assert ace is not None
    assert not await async_remove_config_entry_device(hass, entry, printer)
    assert not await async_remove_config_entry_device(hass, entry, ace)
    # A replaced mainboard's old printer, and an ACE no longer reported.
    old = registry.async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, f"{cp.USER_ID}-1")}
    )
    gone_ace = registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, f"{cp.USER_ID}-{cp.PRINTER_ID}-ace1")},
    )
    assert await async_remove_config_entry_device(hass, entry, old)
    assert await async_remove_config_entry_device(hass, entry, gone_ace)
    # A printer the cloud reports gone from the account.
    entry.runtime_data.primary.printer.cloud.removed = True
    assert await async_remove_config_entry_device(hass, entry, printer)


async def test_d30_nothing_deleted_while_not_running(hass: HomeAssistant) -> None:
    entry = account_entry()
    device = SimpleNamespace(identifiers={(DOMAIN, "x-1")})
    assert not await async_remove_config_entry_device(hass, entry, device)  # type: ignore[arg-type]


# -- D31: electricity per print ------------------------------------------------

METER = "sensor.plug_energy"
PRICE = "input_number.kwh_price"


def _meter(hass: HomeAssistant, value: Any, unit: str = "kWh") -> None:
    hass.states.async_set(
        METER, str(value), {"unit_of_measurement": unit, "device_class": "energy"}
    )


async def _energy_entry(
    hass: HomeAssistant, start: float = 100.0, **options: Any
) -> MockConfigEntry:
    _meter(hass, start)
    return await _cloud(hass, energy_sensor=METER, **options)


async def test_d31_options_step(hass: HomeAssistant, cloud: FakeCloud) -> None:
    entry = await _cloud(hass)
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    assert "energy" in flow["menu_options"]
    result = await hass.config_entries.options.async_configure(
        flow["flow_id"], {"next_step_id": "energy"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "energy"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "energy_sensor": METER,
            "energy_price_per_kwh": 0.3,
            "energy_price_entity": PRICE,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await _settle(hass)
    assert entry.options["energy_sensor"] == METER
    assert entry.options["energy_price_per_kwh"] == 0.3
    assert entry.options["energy_price_entity"] == PRICE
    # The form shows what is set; clearing the sensor switches it off.
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        flow["flow_id"], {"next_step_id": "energy"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"energy_price_per_kwh": 0}
    )
    await _settle(hass)
    assert "energy_sensor" not in entry.options
    assert "energy_price_entity" not in entry.options
    assert entry.options["energy_price_per_kwh"] == 0.0


async def test_d31_no_meter_no_sensors(hass: HomeAssistant, cloud: FakeCloud) -> None:
    entry = await _cloud(hass)
    for key in (
        "job_energy",
        "job_electricity_cost",
        "last_job_energy",
        "last_job_electricity_cost",
        "last_job_total_cost",
    ):
        assert _entity(hass, entry, key) is None
    assert entry.runtime_data.energy.job_energy(cp.PRINTER_ID) is None


async def test_d31_a_job_and_its_electricity(
    hass: HomeAssistant, cloud: FakeCloud
) -> None:
    hass.config.currency = "EUR"
    entry = await _energy_entry(hass, energy_price_per_kwh=0.25)
    energy = _entity(hass, entry, "job_energy")
    cost = _entity(hass, entry, "job_electricity_cost")
    assert energy is not None
    assert cost is not None
    # 0 from the job's start.
    assert float(_state(hass, energy)) == 0.0
    assert float(_state(hass, cost)) == 0.0
    state = hass.states.get(cost)
    assert state.attributes["unit_of_measurement"] == "EUR"
    assert "state_class" not in state.attributes
    assert hass.states.get(energy).attributes["unit_of_measurement"] == "kWh"
    _meter(hass, 100.5)
    await _settle(hass)
    assert float(_state(hass, energy)) == pytest.approx(0.5)
    assert float(_state(hass, cost)) == pytest.approx(0.125)
    # Wh are converted; a drop, a non-number and a big jump are not booked.
    _meter(hass, 100750, "Wh")
    await _settle(hass)
    assert float(_state(hass, energy)) == pytest.approx(0.75)
    for value, unit in (
        (100.0, "kWh"),
        ("unknown", "kWh"),
        ("abc", "kWh"),
        (100.2, "kWh"),
        (5, "GJ"),
        (106.0, "kWh"),
        (0.1061, "MWh"),
    ):
        _meter(hass, value, unit)
        await _settle(hass)
    # 100.0 (drop) ... 100.2 (+0.2) ... 106.0 (+5.8, too big) ... 106.1 (+0.1)
    assert float(_state(hass, energy)) == pytest.approx(1.05)
    assert float(_state(hass, cost)) == pytest.approx(1.05 * 0.25)
    # The job ends: its totals become the last job's.
    await _finish(hass, entry, cloud)
    assert _state(hass, energy) == STATE_UNAVAILABLE
    last_energy = _entity(hass, entry, "last_job_energy")
    last_cost = _entity(hass, entry, "last_job_electricity_cost")
    total = _entity(hass, entry, "last_job_total_cost")
    assert last_energy is not None
    assert last_cost is not None
    assert total is not None
    assert float(_state(hass, last_energy)) == pytest.approx(1.05)
    assert float(_state(hass, last_cost)) == pytest.approx(0.2625)
    # No filament price: the total is the electricity alone.
    assert float(_state(hass, total)) == pytest.approx(0.26)
    # Nothing is booked while no printer prints.
    _meter(hass, 107.0)
    await _settle(hass)
    assert float(_state(hass, last_energy)) == pytest.approx(1.05)


async def test_d31_price_entity_wins_while_it_reads_a_number(
    hass: HomeAssistant, cloud: FakeCloud
) -> None:
    hass.states.async_set(PRICE, "0.5")
    entry = await _energy_entry(
        hass, energy_price_per_kwh=0.1, energy_price_entity=PRICE
    )
    cost = _entity(hass, entry, "job_electricity_cost")
    _meter(hass, 101.0)
    await _settle(hass)
    assert float(_state(hass, cost)) == pytest.approx(0.5)
    hass.states.async_set(PRICE, "unavailable")
    _meter(hass, 102.0)
    await _settle(hass)
    assert float(_state(hass, cost)) == pytest.approx(0.6)


async def test_d31_no_price_cost_unknown(hass: HomeAssistant, cloud: FakeCloud) -> None:
    entry = await _energy_entry(hass)
    assert _entity(hass, entry, "job_energy") is not None
    assert _entity(hass, entry, "job_electricity_cost") is None
    _meter(hass, 101.0)
    await _settle(hass)
    assert entry.runtime_data.energy.job_cost(cp.PRINTER_ID) is None
    await _finish(hass, entry, cloud)
    assert entry.runtime_data.energy.last_job_cost(cp.PRINTER_ID) is None
    assert _entity(hass, entry, "last_job_electricity_cost") is None
    # The total stays with what is known: no filament price, no electricity
    # price, so no total either.
    assert _entity(hass, entry, "last_job_total_cost") is None


async def test_d31_kept_across_a_restart_mid_print(
    hass: HomeAssistant, cloud: FakeCloud
) -> None:
    entry = await _energy_entry(hass, energy_price_per_kwh=1.0)
    _meter(hass, 101.25)
    await _settle(hass)
    await hass.config_entries.async_reload(entry.entry_id)
    await _settle(hass)
    assert entry.runtime_data.energy.job_energy(cp.PRINTER_ID) == pytest.approx(1.25)
    _meter(hass, 101.5)
    await _settle(hass)
    assert entry.runtime_data.energy.job_energy(cp.PRINTER_ID) == pytest.approx(1.5)
    assert entry.runtime_data.energy.job_cost(cp.PRINTER_ID) == pytest.approx(1.5)


async def test_d31_a_new_job_after_a_restart(
    hass: HomeAssistant, cloud: FakeCloud
) -> None:
    entry = await _energy_entry(hass, energy_price_per_kwh=1.0)
    _meter(hass, 101.0)
    await _settle(hass)
    await hass.config_entries.async_unload(entry.entry_id)
    # Another job runs when Home Assistant is back.
    cloud.jobs = [cp.job(id=cp.JOB_ID + 1, taskid=777)]
    await hass.config_entries.async_setup(entry.entry_id)
    await _settle(hass)
    energy = entry.runtime_data.energy
    assert energy.job_energy(cp.PRINTER_ID) == 0.0
    assert energy.last_job_energy(cp.PRINTER_ID) == pytest.approx(1.0)


def _stub(printer_id: int, printing: bool, task: int | None = 5) -> Any:
    return SimpleNamespace(
        printer_id=printer_id,
        job_in_progress=printing,
        job_task_id=task,
        job_name="part.gcode",
    )


async def test_d31_only_with_exactly_one_printer_printing(hass: HomeAssistant) -> None:
    printers = [_stub(1, True), _stub(2, True, 6)]
    changes: list[int] = []
    meter = EnergyMeter(
        hass,
        "entry",
        {"energy_sensor": METER, "energy_price_per_kwh": 2},
        lambda: printers,
        lambda: changes.append(1),
    )
    _meter(hass, 10.0)
    await meter.async_load()
    for printer in printers:
        meter.update(printer)
    _meter(hass, 11.0)
    await _settle(hass)
    assert meter.job_energy(1) == 0.0
    assert meter.job_energy(2) == 0.0
    assert changes == []
    printers[1] = _stub(2, False)
    meter.update(printers[1])
    _meter(hass, 11.5)
    await _settle(hass)
    assert meter.job_energy(1) == pytest.approx(0.5)
    assert meter.job_cost(1) == pytest.approx(1.0)
    assert meter.job_energy(2) is None
    assert changes == [1]
    # A printer whose state is not known yet does not count as printing.
    printers.append(_stub(3, True))
    _meter(hass, 12.0)
    await _settle(hass)
    assert meter.job_energy(1) == pytest.approx(1.0)
    # Another job replaces the stored one: that one ended unseen.
    printers[0] = _stub(1, True, 9)
    meter.update(printers[0])
    assert meter.last_job_energy(1) == pytest.approx(1.0)
    assert meter.job_energy(1) == 0.0
    # A job seen first without a number or name takes its number later.
    printers[0] = SimpleNamespace(
        printer_id=1, job_in_progress=False, job_task_id=None, job_name=None
    )
    meter.update(printers[0])
    printers[0] = SimpleNamespace(
        printer_id=1, job_in_progress=True, job_task_id=None, job_name=None
    )
    meter.update(printers[0])
    _meter(hass, 12.5)
    await _settle(hass)
    printers[0] = _stub(1, True, 11)
    meter.update(printers[0])
    assert meter.job_energy(1) == pytest.approx(0.5)
    await meter.async_shutdown()


async def test_d31_helpers(hass: HomeAssistant) -> None:
    hass.states.async_set("sensor.x", "2", {"unit_of_measurement": "MWh"})
    assert reading_kwh(hass.states.get("sensor.x")) == 2000.0
    hass.states.async_set("sensor.x", "nan", {"unit_of_measurement": "kWh"})
    assert reading_kwh(hass.states.get("sensor.x")) is None
    hass.states.async_set("sensor.x", "3")
    assert reading_kwh(hass.states.get("sensor.x")) is None
    assert reading_kwh(None) is None
    assert job_key(_stub(1, True, 5)) == "id:5"
    assert job_key(_stub(1, True, -1)) == "name:part.gcode"
    nameless = SimpleNamespace(job_task_id=None, job_name=None)
    assert job_key(nameless) is None  # type: ignore[arg-type]
    settings = EnergySettings.from_options({"energy_price_per_kwh": "x"})
    assert settings == EnergySettings(None, 0.0, None)
    assert EnergySettings.from_options({"energy_price_per_kwh": -3}).price == 0.0
    off = EnergyMeter(hass, "e", {}, list, lambda: None)
    await off.async_load()
    off.update(_stub(1, True))
    assert off.job_energy(1) is None
    assert off.last_job_cost(1) is None
    await off.async_shutdown()


async def test_d31_meter_without_a_first_reading(hass: HomeAssistant) -> None:
    printers = [_stub(1, True)]
    meter = EnergyMeter(
        hass, "entry2", {"energy_sensor": METER}, lambda: printers, lambda: None
    )
    await meter.async_load()  # no state yet
    meter.update(printers[0])
    _meter(hass, 50.0)
    await _settle(hass)
    assert meter.job_energy(1) == 0.0  # the first reading is the baseline
    _meter(hass, 50.5)
    await _settle(hass)
    assert meter.job_energy(1) == pytest.approx(0.5)
    assert meter.job_cost(1) is None
    await meter.async_shutdown()
