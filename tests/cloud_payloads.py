"""Cloud payloads for the fake Anycubic cloud.

Shapes follow anycubic-cloud-client's docs/PROTOCOL.md (Parts B-D); values
are made up. Each helper returns a fresh dict so tests can change it.
"""

from __future__ import annotations

import base64
import copy
import json
import time
from typing import Any

from . import payloads

USER_ID = 123456
EMAIL = "someone@example.com"
PRINTER_ID = 42424242
PRINTER_KEY = "fakeprinterkey0001"
MACHINE_TYPE = 20025
JOB_ID = 90001
TOPIC = "anycubic/anycubicCloud/v1/printer/public/{mt}/{key}/{kind}/report"


def jwt(**claims: Any) -> str:
    """An unsigned JWT with the given claims (enough for the local checks)."""

    def part(value: dict[str, Any]) -> str:
        raw = json.dumps(value).encode()
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    return f"{part({'alg': 'RS256'})}.{part(claims)}.c2lnbmF0dXJl"


def slicer_token(days: float = 60) -> str:
    return jwt(
        exp=int(time.time() + days * 86400),
        tokenType="access-token",
        iss="https://uc.makeronline.com",
    )


def ace_box(box_id: int = 0, **changes: Any) -> dict[str, Any]:
    return {
        "id": box_id,
        "status": 1,
        "temp": 33,
        "humidity": 12,
        "model_id": 40001,
        "auto_feed": 1,
        "loaded_slot": 1,
        "feed_status": {"code": 200, "type": 1, "current_status": 0, "slot_index": 1},
        "drying_status": {
            "status": 0,
            "target_temp": 0,
            "duration": 0,
            "remain_time": 0,
        },
        "slots": [
            {
                "index": index,
                "sku": f"SKU{index}",
                "type": "PLA",
                "color": [255, 255 - 60 * index, 255, 255],
                "color_group": [[255, 255 - 60 * index, 255, 255]],
                "status": 5 if index == 1 else 4,
                "edit_status": 0,
                "icon_type": 0,
                "consumables_percent": 0,
            }
            for index in range(4)
        ],
    } | changes


def detail(printer_id: int = PRINTER_ID, **changes: Any) -> dict[str, Any]:
    """The printer detail (E6), a Kobra S1 with one ACE Pro, idle."""
    return {
        "id": printer_id,
        "name": "Kobra S1 Cloud",
        "key": PRINTER_KEY if printer_id == PRINTER_ID else f"key{printer_id}",
        "machine_type": MACHINE_TYPE,
        "model": "Anycubic Kobra S1",
        "img": "https://cdn.example.invalid/device.png",
        "device_status": 1,
        "is_printing": 1,
        "base": {
            "print_count": 174,
            "print_totaltime": "798hour29min",
            "material_type": "Filament",
            "material_used": "18.17kg",
            "description": "SERIAL",
            "create_time": 1751145530,
            "firmware_version": "2.7.2.7",
            "machine_mac": payloads.MAC_UID if printer_id == PRINTER_ID else None,
        },
        "parameter": {"curr_hotbed_temp": 28, "curr_nozzle_temp": 31},
        "type_function_ids": [2, 13, 22, 39, 41, 2006, 99],
        "version": {
            "need_update": 0,
            "firmware_version": "2.7.2.7",
            "target_version": "2.7.2.7",
            "update_progress": 0,
            "update_status": "",
        },
        "multi_color_box_version": [
            {
                "box_name": "ACE Pro",
                "need_update": 0,
                "firmware_version": "1.3.863",
                "target_version": "1.3.863",
                "box_id": 0,
            }
        ],
        "external_shelves": {"id": None, "type": None, "color": None, "loaded": None},
        "multi_color_box": ace_box(0),
    } | changes


def job(**changes: Any) -> dict[str, Any]:
    """A job-list record (E12), printing."""
    record = {
        "id": JOB_ID,
        "taskid": 555,
        "user_id": USER_ID,
        "printer_id": PRINTER_ID,
        "gcode_id": 700002,
        "img": "https://cdn.example.invalid/preview.png",
        "estimate": 12345,
        "remain_time": 42,
        "print_time": 95,
        "progress": 69,
        "pause": 0,
        "print_status": 1,
        "reason": 0,
        "status": 1,
        "create_time": 1790000000,
        "start_time": 1790000100,
        "end_time": 0,
        "total_time": "2hour17min",
        "gcode_name": "benchy_PLA_0.2.gcode",
        "settings": json.dumps(
            {
                "curr_layer": 120,
                "total_layers": 240,
                "supplies_usage": 31783,
                "state": "printing",
                "slicer": "Slicer Next",
            }
        ),
        "slice_param": json.dumps(
            {
                "image_id": "relative/image/path.png",
                "layer_height": 0.2,
                "printer_settings_id": "Kobra S1 0.4",
                "filament_type": "PLA;PETG",
                "temperature": 220,
                "bed_temperature": -1,
                "fill_density": "15%",
                "travel_speed": 300,
                "brim_type": "",
                "paint_infos": [
                    {"paint_index": 0, "material_type": "PLA", "filament_used": 94.5}
                ],
            }
        ),
        "slice_result": json.dumps(
            {"size_x": 60.0, "size_y": 31.0, "size_z": 48.0, "used_filament": 94.5}
        ),
        "source": "slicer",
        "key": PRINTER_KEY,
        "machine_type": MACHINE_TYPE,
        "printer_name": "Kobra S1 Cloud",
    }
    record.update(changes)
    return record


def job_detail(**changes: Any) -> dict[str, Any]:
    """Job detail (E13)."""
    return {
        "z_thick": 0.2,
        "print_speed_mode": 2,
        "print_speed_pct": 100,
        "fan_speed_pct": 60,
        "temp": {
            "target_nozzle_temp": 220,
            "target_hotbed_temp": 60,
            "limit": {"hotbed_temp_limit": [35, 120], "nozzle_temp_limit": [185, 320]},
        },
        "print_speed_model_des": [
            {"title": "Silent", "print_speed_mode": 1},
            {"title": "Standard", "print_speed_mode": 2},
            {"title": "Sport", "print_speed_mode": 3},
        ],
    } | changes


def cloud_file(**changes: Any) -> dict[str, Any]:
    return {
        "id": 700001,
        "gcode_id": 700002,
        "old_filename": "benchy.gcode",
        "filename": "storage-name",
        "size": 1234567,
        "thumbnail": "https://cdn.example.invalid/thumb.png?X-Amz-Signature=abc",
        "estimate": 3600,
        "material_name": "PLA",
        "layer_height": 0.2,
        "supplies_usage": 4567,
        "size_x": 60.0,
        "size_y": 31.0,
        "size_z": 48.0,
    } | changes


def camera_reply() -> dict[str, Any]:
    return {
        "msgid": "fake-msgid-0001",
        "shengwang": {
            "appid": "FAKEAGORAAPPID",
            "channel": PRINTER_KEY,
            "rtc_token": "007fakertctoken",
            "uid": 5001,
            "client_uid": 6001,
        },
    }


def user_info() -> dict[str, Any]:
    return {"id": USER_ID, "user_email": EMAIL, "mobile": "", "birthday": "1990-01-01"}


def mqtt(  # noqa: PLR0917 - the envelope, in wire order
    kind: str,
    action: str,
    state: str,
    data: Any = None,
    code: int = 200,
    msg: str = "done",
) -> dict[str, Any]:
    return {
        "type": kind,
        "action": action,
        "state": state,
        "code": code,
        "msg": msg,
        "msgid": "fake-msgid",
        "timestamp": 0,
        "data": copy.deepcopy(data),
    }


def topic(kind: str, key: str = PRINTER_KEY, machine_type: int = MACHINE_TYPE) -> str:
    return TOPIC.format(mt=machine_type, key=key, kind=kind)
