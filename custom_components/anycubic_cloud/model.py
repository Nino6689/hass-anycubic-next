"""The integration's view of one printer, derived from anycubic-lan's state.

Everything here is a pure reading of the latest merged ``PrinterState`` plus
the few facts anycubic-lan does not keep (the axis move state, whether an
``info`` report has arrived). The rules are BEHAVIOUR §1 and §2.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from anycubic_lan import AceBox, AceSlot, Job, PrinterState, PrintStatus

from .const import ACE_MODEL_DEFAULT, ACE_MODEL_NAMES, CAMERA_PORT
from .error_codes import describe_error
from .filament import rgb_to_hex

MATERIAL_FILAMENT = "Filament"
MATERIAL_RESIN = "Resin"

# Device status (BEHAVIOUR §1.1).
DEVICE_ONLINE = 1
DEVICE_OFFLINE = 2
# Work status (BEHAVIOUR §1.1).
WORK_FREE = 1
WORK_BUSY = 2

# Job status codes that mean "in progress" (BEHAVIOUR §1.3).
_IN_PROGRESS = frozenset({1, 4, 5, 6})
_OVER = frozenset({2, 3})
# Text phases that mean a job with an unlisted code is over (BEHAVIOUR §1.3).
_OVER_PHASES = frozenset(
    {
        "cancelled",
        "canceled",
        "complete",
        "completed",
        "failed",
        "finished",
        "free",
        "idle",
        "stopped",
    }
)
_JOB_STATE_TEXT: Mapping[int, str] = {
    1: "printing",
    2: "finished",
    3: "failed",
    4: "downloading",
    5: "checking",
    6: "preheating",
    7: "slicing",
    9: "levelling",
}

# ACE slot facts (BEHAVIOUR §1.9).
SLOT_EDIT_EMPTY = 2
SLOT_STATUS_LOADED = 5

# Axis move states (BEHAVIOUR §1.8).
AXIS_DONE = "done"
AXIS_FAILED = "failed"


def material_type_from_device_type(device_type: str | None) -> str | None:
    """``fdm`` → Filament; ``lcd``/``dlp``/``resin`` → Resin (BEHAVIOUR §1.7)."""
    if not device_type:
        return None
    lowered = device_type.lower()
    if lowered == "fdm":
        return MATERIAL_FILAMENT
    if lowered in ("lcd", "dlp", "resin"):
        return MATERIAL_RESIN
    return device_type


def ace_model_name(model_id: int | None) -> str:
    """Device model of an ACE unit (COMPAT §2; DECISIONS round 2, Q2.3).

    ``40001`` is the ACE Pro; any other or unknown id is the generic ACE.
    """
    if model_id is None:
        return ACE_MODEL_DEFAULT
    return ACE_MODEL_NAMES.get(model_id, ACE_MODEL_DEFAULT)


def print_speed_pct(action: str | None, state: str | None, data: object) -> int | None:
    """The speed % a ``print`` report carries, if any (round 2, Q2.2).

    Only ``start``/``update`` reports in state ``updated`` carry it, under
    ``data.settings.print_speed_pct``.
    """
    if action not in ("start", "update") or state != "updated":
        return None
    if not isinstance(data, Mapping):
        return None
    settings = data.get("settings")
    if not isinstance(settings, Mapping):
        return None
    value = settings.get("print_speed_pct")
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return round(value)


def _number(value: float | None) -> float | None:
    return float(value) if value is not None else None


def _whole(value: float | None) -> int | None:
    return round(value) if value is not None else None


@dataclass(slots=True)
class PrinterIdentity:
    """Who the printer is. Fixed for the life of a config entry's setup."""

    printer_id: int
    mac: str
    """Upper-case, hyphen-separated, as used in unique ids (COMPAT §3)."""
    name: str
    model_name: str
    model_id: int
    material_type: str | None
    host: str
    serial: str | None = None
    connection_mac: str | None = None
    """``aa:bb:cc:dd:ee:ff`` for the device registry connection, if known."""


@dataclass(slots=True)
class ExternalSpool:
    """The external filament holder (BEHAVIOUR §2.7)."""

    material: str | None
    color: list[int] | None
    loaded: bool


@dataclass(slots=True)
class Printer:
    """Live readings of one printer."""

    identity: PrinterIdentity
    state: PrinterState = field(default_factory=PrinterState)
    info_seen: bool = False
    axis_move_state: str | None = None
    print_speed_pct: int | None = None
    """From ``print`` reports' ``data.settings`` (PROTOCOL §7.2, round 2 Q2.2)."""
    remembered_light_types: frozenset[int] = frozenset()

    # -- identity ----------------------------------------------------------

    @property
    def printer_id(self) -> int:
        return self.identity.printer_id

    @property
    def is_filament(self) -> bool:
        return self.identity.material_type == MATERIAL_FILAMENT

    # -- online / busy (BEHAVIOUR §1.1, §1.2) -------------------------------

    @property
    def device_status(self) -> int | None:
        """1 once any ``info`` report arrived. LAN never reports offline."""
        return DEVICE_ONLINE if self.info_seen else None

    @property
    def is_online(self) -> bool:
        return self.device_status == DEVICE_ONLINE

    @property
    def work_status(self) -> int:
        """``free`` → 1, ``busy`` → 2; free when nothing has been said."""
        raw = self.state.printer_state
        if raw == "busy":
            return WORK_BUSY
        if raw is None or raw == "free":
            return WORK_FREE
        # An unknown word: busy while a job runs, else free.
        return WORK_BUSY if self.job_in_progress else WORK_FREE

    @property
    def is_moving(self) -> bool:
        state = self.axis_move_state
        return state is not None and state not in (AXIS_DONE, AXIS_FAILED)

    @property
    def axis_move_failed(self) -> bool:
        return self.axis_move_state == AXIS_FAILED

    @property
    def current_status(self) -> str:
        if self.is_moving:
            return "moving"
        if self.work_status == WORK_BUSY:
            return "busy"
        if self.work_status == WORK_FREE:
            return "available"
        return "unknown"  # pragma: no cover - work_status is always 1 or 2

    # -- the job (BEHAVIOUR §1.3) ------------------------------------------

    @property
    def job(self) -> Job | None:
        return self.state.job

    @property
    def job_status_code(self) -> int | None:
        """The job's status number; 0 and unknown values keep the previous one."""
        job = self.job
        if job is None or job.print_status is None:
            return None
        return int(job.print_status)

    @property
    def job_in_progress(self) -> bool:
        job = self.job
        if job is None:
            return False
        code = self.job_status_code
        if code in _IN_PROGRESS:
            return True
        if code in _OVER:
            return False
        phase = (job.state or "").strip().lower()
        if not phase:
            return False
        return phase not in _OVER_PHASES

    @property
    def job_is_paused(self) -> bool:
        job = self.job
        return job is not None and bool(job.pause) and self.job_in_progress

    @property
    def job_complete(self) -> bool:
        return self.job_status_code == PrintStatus.COMPLETE

    @property
    def job_failed(self) -> bool:
        return self.job_status_code == PrintStatus.CANCELLED

    @property
    def job_state(self) -> str | None:
        job = self.job
        if job is None:
            # B9: an online printer with no job is idle, not unavailable.
            return "idle" if self.is_online else None
        if self.job_is_paused:
            return "paused"
        code = self.job_status_code
        if code is not None and code in _JOB_STATE_TEXT:
            return _JOB_STATE_TEXT[code]
        return job.state or "unknown"

    @property
    def job_name(self) -> str | None:
        """File name without folders and extension (G13)."""
        job = self.job
        return job.name if job is not None else None

    @property
    def job_filament_used(self) -> float | None:
        """Millimetres extruded so far by this job (DECISIONS V1)."""
        job = self.job
        return _number(job.supplies_usage) if job is not None else None

    @property
    def job_task_id(self) -> int | None:
        job = self.job
        return job.task_id if job is not None else None

    @property
    def job_progress(self) -> int | None:
        job = self.job
        return _whole(job.progress) if job is not None else None

    @property
    def job_remaining_minutes(self) -> int | None:
        job = self.job
        return _whole(job.remain_time) if job is not None else None

    @property
    def job_elapsed_minutes(self) -> int | None:
        job = self.job
        return _whole(job.print_time) if job is not None else None

    # -- temperatures, fans, speed (BEHAVIOUR §2.2) --------------------------

    @property
    def nozzle_temperature(self) -> float | None:
        return _number(self.state.temperatures.nozzle)

    @property
    def hotbed_temperature(self) -> float | None:
        return _number(self.state.temperatures.bed)

    @property
    def target_nozzle_temperature(self) -> float | None:
        # LAN has no cloud job detail, so the printer's own set-point.
        return _number(self.state.temperatures.nozzle_target)

    @property
    def target_hotbed_temperature(self) -> float | None:
        return _number(self.state.temperatures.bed_target)

    @property
    def fan_speed(self) -> int | None:
        return _whole(self.state.fans.fan_speed_pct)

    @property
    def aux_fan_speed(self) -> int | None:
        return _whole(self.state.fans.aux_fan_speed_pct)

    @property
    def box_fan_level(self) -> int | None:
        return self.state.fans.box_fan_level

    @property
    def speed_mode_code(self) -> int | None:
        """The printer's reported mode, else the job's (BEHAVIOUR §1.5)."""
        if self.state.speed_mode_raw is not None:
            return self.state.speed_mode_raw
        job = self.job
        return job.speed_mode_raw if job is not None else None

    @property
    def speed_modes(self) -> list[dict[str, Any]]:
        """``{description, mode}`` pairs. Cloud only: always empty on LAN."""
        return []

    @property
    def job_speed_mode(self) -> str | None:
        code = self.speed_mode_code
        if code is None:
            return None
        for mode in self.speed_modes:
            if mode["mode"] == code:
                return str(mode["description"])
        return str(code)

    # -- errors (BEHAVIOUR §1.4, DECISIONS V10) -----------------------------

    @property
    def last_error_code(self) -> int | None:
        # anycubic-lan clears a kind's code on its next OK code (V10).
        return self.state.last_error_code

    @property
    def last_error(self) -> str | None:
        code = self.last_error_code
        return describe_error(code) if code is not None else None

    # -- head position (BEHAVIOUR §2.6) -------------------------------------

    def axis_position(self, axis: str) -> float | None:
        position = self.state.position
        if position is None:
            return None
        return _number(getattr(position, axis))

    # -- light (BEHAVIOUR §2.16, §3.13) -------------------------------------

    @property
    def light_types(self) -> set[int]:
        live = {light.type for light in self.state.lights if light.type is not None}
        return live | set(self.remembered_light_types)

    @property
    def has_light(self) -> bool:
        return bool(self.light_types)

    @property
    def light_type(self) -> int | None:
        """The lowest light type reported now or remembered (G6)."""
        types = self.light_types
        return min(types) if types else None

    @property
    def light_on(self) -> bool | None:
        light_type = self.light_type
        for light in self.state.lights:
            if light.type == light_type:
                return light.on
        return None

    # -- AI detection (BEHAVIOUR §2.15) --------------------------------------

    @property
    def ai_detection_enabled(self) -> bool | None:
        settings = self.state.ai_settings
        if settings is None or settings.status is None:
            return None
        return settings.status != 0

    # -- camera (BEHAVIOUR §2.18) -------------------------------------------

    @property
    def camera_url(self) -> str:
        """The URL the printer named, else the default on the configured host."""
        return self.state.camera_url or f"http://{self.identity.host}:{CAMERA_PORT}/flv"

    @property
    def peripherals(self) -> dict[str, bool | None]:
        peripherals = self.state.peripherals
        if peripherals is None:
            return {"camera": None, "ace": None, "usb_disk": None}
        return {
            "camera": peripherals.camera,
            "ace": peripherals.ace,
            "usb_disk": peripherals.usb_disk,
        }

    # -- external holder (BEHAVIOUR §2.7) -----------------------------------

    @property
    def external_spool(self) -> ExternalSpool | None:
        """The holder, or ``None`` when absent.

        Keys as confirmed in DECISIONS round 2, Q3 (``id``, ``type``,
        ``color``, ``loaded``; PROTOCOL §7.2); ``material`` and
        ``external_shelves`` are also accepted.
        """
        raw = self.state.external_filament_box
        if raw is None:
            return None
        block: Mapping[str, Any] = raw
        nested = raw.get("external_shelves")
        if isinstance(nested, Mapping):
            block = nested
        box_id = block.get("id")
        material = block.get("type")
        if not isinstance(material, str) or not material.strip():
            material = block.get("material")
        material = material.strip() if isinstance(material, str) else None
        loaded_raw = block.get("loaded")
        if box_id is None and not material and loaded_raw is None:
            return None  # B34: an all-null block means no holder
        color = block.get("color")
        color_list = (
            list(color)
            if isinstance(color, list) and rgb_to_hex(color) is not None
            else None
        )
        return ExternalSpool(
            material=material or None,
            color=color_list,
            loaded=bool(loaded_raw) and not isinstance(loaded_raw, str),
        )

    # -- ACE (BEHAVIOUR §1.9, §2.8, §2.9) -----------------------------------

    @property
    def ace_count(self) -> int:
        return len(self.state.ace_boxes)

    @property
    def supports_ace(self) -> bool:
        """LAN has no function list: an ACE has reported (BEHAVIOUR §1.7)."""
        return self.ace_count > 0

    def ace_box(self, index: int) -> AceBox | None:
        """The ACE with ``id`` == ``index``, else the one in that position."""
        boxes = self.state.ace_boxes
        for box in boxes:
            if box.id == index:
                return box
        if 0 <= index < len(boxes) and boxes[index].id is None:
            return boxes[index]
        return None

    def ace_loaded_slot_index(self, index: int) -> int | None:
        """0-based slot feeding the printer.

        First ACE only: when ``loaded_slot`` reads -1, the slot whose own
        status is 5 is taken instead (B15). The second ACE has no fallback.
        """
        box = self.ace_box(index)
        if box is None:
            return None
        if index == 0:
            return box.loaded_slot
        raw = box.loaded_slot_raw
        return raw if raw is not None and raw >= 0 else None

    def ace_slot(self, index: int, slot_number: int) -> AceSlot | None:
        """Slot ``slot_number`` (1-based) of ACE ``index``."""
        box = self.ace_box(index)
        if box is None:
            return None
        for position, slot in enumerate(box.slots):
            slot_index = slot.index if slot.index is not None else position
            if slot_index == slot_number - 1:
                return slot
        return None

    @staticmethod
    def slot_is_empty(slot: AceSlot | None) -> bool:
        return slot is None or slot.edit_status == SLOT_EDIT_EMPTY

    def ace_temperature(self, index: int) -> int:
        box = self.ace_box(index)
        if box is None or box.temp is None:
            return 0
        return round(box.temp)

    def ace_model(self, index: int) -> str:
        box = self.ace_box(index)
        return ace_model_name(box.model_id if box is not None else None)

    def drying_value(self, index: int, name: str) -> float:
        """Drying figure; 0 when not drying or unreported (BEHAVIOUR §1.9)."""
        box = self.ace_box(index)
        drying = box.drying if box is not None else None
        if drying is None or not drying.is_drying:
            return 0
        value = getattr(drying, name)
        return value if value is not None else 0

    def drying_status_code(self, index: int) -> int | None:
        box = self.ace_box(index)
        drying = box.drying if box is not None else None
        return drying.status if drying is not None else None

    def is_drying(self, index: int) -> bool:
        return self.drying_status_code(index) == 1

    def ace_auto_feed(self, index: int) -> bool:
        box = self.ace_box(index)
        return bool(box.auto_feed) if box is not None else False

    def spool_info(self, index: int) -> list[dict[str, Any]]:
        box = self.ace_box(index)
        if box is None:
            return []
        return [
            slot_attributes(slot, position) | {"material_type": slot.material}
            for position, slot in enumerate(box.slots)
        ]

    def box_info(self, index: int) -> dict[str, Any] | None:
        box = self.ace_box(index)
        if box is None:
            return None
        loaded = self.ace_loaded_slot_index(index)
        return {
            "box_id": box.id,
            "model_id": box.model_id,
            "status": box.status,
            "temperature": box.temp,
            "humidity": 0,
            "auto_feed": bool(box.auto_feed),
            "loaded_slot": loaded + 1 if loaded is not None else None,
            "feed_status": box.feed_status,
        }

    def ace_material(self, index: int, feeding_slot: int | None) -> str | None:
        """Material "in the ACE" for drying defaults (BEHAVIOUR §3.11, B11)."""
        loaded = self.ace_loaded_slot_index(index)
        if loaded is None and index == 0:
            loaded = feeding_slot
        if loaded is not None:
            slot = self.ace_slot(index, loaded + 1)
            if slot is not None and slot.material:
                return slot.material
        box = self.ace_box(index)
        for slot in box.slots if box is not None else ():
            if not self.slot_is_empty(slot) and slot.material:
                return slot.material
        return None


def slot_attributes(slot: AceSlot, position: int) -> dict[str, Any]:
    """Attributes of an ACE slot (BEHAVIOUR §2.8)."""
    color = list(slot.color) if slot.color is not None else None
    color_hex = rgb_to_hex(slot.color)
    slot_index = slot.index if slot.index is not None else position
    return {
        "slot": slot_index + 1,
        "color": color,
        "color_hex": color_hex,
        "colors_hex": [color_hex] if color_hex else [],
        "color_group": [[*color, 255]] if color is not None else [],
        "is_multi_color": False,
        "sku": slot.sku or None,
        "status": slot.status,
        "spool_loaded": slot.status == SLOT_STATUS_LOADED,
        "edit_status": slot.edit_status,
        "icon_type": None,
        "consumables_percent": None,
    }
