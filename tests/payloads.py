"""Printer payloads for the fake LAN client.

Shapes follow anycubic-lan's docs/PROTOCOL.md §6 (captured from a Kobra S1);
values are made up. Each helper returns a fresh dict so tests can change it.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Any

from anycubic_lan import BrokerCredentials, DiscoveryInfo, PrinterConnectionInfo

HOST = "10.0.66.28"
MAC = "a4:e8:8d:80:54:c8"
MAC_UID = "A4-E8-8D-80-54-C8"
DEVICE_ID = "372d94454cf5d746d07a8100df8674aa"
# lan_printer_id(DEVICE_ID): BLAKE2b, digest_size=6, big-endian (COMPAT §2).
PRINTER_ID = 173939650300971
UPLOAD_URL = f"http://{HOST}:18910/gcode_upload?s=SIGNEDSECRET"
DISCOVERY_TOKEN = "0123456789abcdeffedcba9876543210"


def discovery_document(**changes: Any) -> dict[str, Any]:
    return {
        "ctrlType": "lan",
        "token": DISCOVERY_TOKEN,
        "ctrlInfoUrl": f"http://{HOST}:18910/ctrl",
        "modelId": "20025",
        "cn": "SERIAL123",
        "usn": "uuid:fdm:A4-E8-8D-80-54-C8",
        "modelName": "Anycubic Kobra S1",
        "deviceType": "fdm",
        "ip": HOST,
        "fileUploadurl": UPLOAD_URL,
        "rtspUrl": f"http://{HOST}:18088/flv",
    } | changes


def connection_info(
    *,
    model_id: int = 20025,
    usn: str | None = "uuid:fdm:A4-E8-8D-80-54-C8",
    model_name: str | None = "Anycubic Kobra S1",
    device_type: str | None = "fdm",
    device_id: str = DEVICE_ID,
) -> PrinterConnectionInfo:
    raw = discovery_document()
    return PrinterConnectionInfo(
        host=HOST,
        discovery=DiscoveryInfo(
            token=DISCOVERY_TOKEN,
            ctrl_info_url=f"http://{HOST}:18910/ctrl",
            model_id=model_id,
            ctrl_type="lan",
            serial="SERIAL123",
            usn=usn,
            model_name=model_name,
            device_type=device_type,
            raw=MappingProxyType(raw),
        ),
        credentials=BrokerCredentials(
            host=HOST,
            port=9883,
            username="printer-user",
            password="printer-pass",
            device_id=device_id,
        ),
    )


def envelope(kind: str, data: Any, **fields: Any) -> dict[str, Any]:
    return {
        "type": kind,
        "action": "report",
        "state": "done",
        "code": 200,
        "msg": "done",
        "data": data,
    } | fields


def job(**changes: Any) -> dict[str, Any]:
    return {
        "remain_time": 42,
        "curr_layer": 3,
        "total_layers": 5,
        "supplies_usage": 120,
        "print_time": 7,
        "progress": 60,
        "state": "printing",
        "print_status": 1,
        "filename": ".3mf_temp/0622-1002-Wolf_plate(01)_PLA_0.2_45s.gcode",
        "pause": 0,
        "project_type": 1,
        "task_id": 614707220,
        "print_speed_mode": None,
    } | changes


def info(project: dict[str, Any] | None = None, **changes: Any) -> dict[str, Any]:
    data = {
        "printerName": "Anycubic Kobra S1",
        "model": "Anycubic Kobra S1",
        "ip": HOST,
        "version": "2.7.2.7",
        "state": "busy" if project else "free",
        "urls": {"fileUploadurl": UPLOAD_URL, "rtspUrl": f"http://{HOST}:18088/flv"},
        "temp": {
            "curr_hotbed_temp": 31,
            "curr_nozzle_temp": 34,
            "target_hotbed_temp": 0,
            "target_nozzle_temp": 0,
        },
        "print_speed_mode": 2,
        "fan_speed_pct": 55,
        "aux_fan_speed_pct": 20,
        "box_fan_level": 3,
        "project": project,
        "last_project": None,
    } | changes
    return envelope("info", data)


def slot(index: int, **changes: Any) -> dict[str, Any]:
    colors = [[255, 255, 255], [0, 0, 0], [255, 0, 0], [0, 128, 255]]
    return {
        "index": index,
        "sku": f"SKU{index}",
        "type": "PLA",
        "color": colors[index],
        "status": 4,
        "edit_status": 0,
    } | changes


def box(box_id: int = 0, **changes: Any) -> dict[str, Any]:
    return {
        "id": box_id,
        "status": 1,
        "model_id": 40001,
        "auto_feed": 0,
        "loaded_slot": -1,
        "temp": 25,
        "drying_status": {
            "status": 0,
            "target_temp": 0,
            "duration": 0,
            "remain_time": 0,
        },
        "slots": [slot(i) for i in range(4)],
    } | changes


def ace(*boxes: dict[str, Any], action: str = "getInfo") -> dict[str, Any]:
    return envelope(
        "multiColorBox",
        {"multi_color_box": list(boxes)},
        action=action,
        state="success",
    )


def lights(*items: dict[str, Any]) -> dict[str, Any]:
    return envelope("light", {"lights": list(items)}, action="query")


def light(light_type: int = 2, on: int = 1) -> dict[str, Any]:
    return {"type": light_type, "status": on, "brightness": 100 if on else 0}


def peripherals(camera: int = 1, ace_fitted: int = 1, udisk: int = 1) -> dict[str, Any]:
    return envelope(
        "peripherie",
        {"camera": camera, "multiColorBox": ace_fitted, "udisk": udisk},
        action="query",
    )


def ai_settings(status: int = 0) -> dict[str, Any]:
    return envelope(
        "aiSettings",
        {
            "ai_settings": {
                "status": status,
                "type": 2,
                "count": 60,
                "notice_type": [0, 1],
                "sensitivity_level": [1, 1],
            }
        },
        action="query",
    )


def axis_position(x: float = 47, y: float = 276, z: float = 3.8) -> dict[str, Any]:
    return envelope("axis", {"coordinates": {"x": x, "y": y, "z": z}}, action="query")


def axis_move(state: str) -> dict[str, Any]:
    return envelope("axis", None, action="move", state=state)


def extfilbox(**data: Any) -> dict[str, Any]:
    return envelope("extfilbox", data, action="query")
