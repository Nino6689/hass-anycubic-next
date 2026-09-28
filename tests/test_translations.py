"""Every translation key the code uses exists in strings.json."""

from __future__ import annotations

import json
from pathlib import Path
import re

import yaml

from custom_components.anycubic_cloud import (
    binary_sensor,
    button,
    number,
    select,
    sensor,
    switch,
)
from custom_components.anycubic_cloud.model import _JOB_STATE_TEXT
from custom_components.anycubic_cloud.services import SERVICES

ROOT = Path(__file__).parent.parent / "custom_components" / "anycubic_cloud"
STRINGS = json.loads((ROOT / "strings.json").read_text())


def test_english_translation_matches_strings() -> None:
    assert json.loads((ROOT / "translations" / "en.json").read_text()) == STRINGS


def test_exception_keys_exist() -> None:
    used: set[str] = set()
    for path in ROOT.glob("*.py"):
        text = path.read_text()
        used |= set(re.findall(r'translation_key="([a-z_]+)"', text))
        used |= set(re.findall(r'_error\(\s*"([a-z_]+)"', text))
    missing = used - set(STRINGS["exceptions"])
    assert not missing


def test_flow_errors_and_aborts_exist() -> None:
    lan = {
        "lan_host_required",
        "lan_printer_in_cloud_mode",
        "lan_unsupported_printer",
        "lan_unreachable",
    }
    assert lan | {"lan_different_printer"} <= set(STRINGS["config"]["error"])
    assert lan | {"invalid_card_config"} <= set(STRINGS["options"]["error"])
    text = (ROOT / "config_flow.py").read_text()
    for reason in set(re.findall(r'reason="([a-z_]+)"', text)):
        assert reason in STRINGS["config"]["abort"], reason
    assert "cloud_not_supported_yet" not in STRINGS["config"]["abort"]
    cloud = {
        "invalid_token_format",
        "token_expired",
        "token_corrupted",
        "invalid_auth",
        "wrong_token_type",
        "cannot_read_response",
        "cannot_connect",
        "no_printers",
        "invalid_printer",
    }
    assert cloud <= set(STRINGS["config"]["error"])


def test_entity_names_exist() -> None:
    entities = STRINGS["entity"]
    for platform, descriptions in (
        ("sensor", sensor.SENSORS),
        ("binary_sensor", binary_sensor.BINARY_SENSORS),
        ("button", button.BUTTONS),
        ("number", number.NUMBERS),
        ("select", (select.AXIS_STEP, select.SPEED_MODE)),
        ("switch", (switch.AI_DETECTION, *switch.RUNOUT_REFILL)),
    ):
        for description in descriptions:
            assert entities[platform][description.key]["name"], description.key


def test_services_documented() -> None:
    documented = yaml.safe_load((ROOT / "services.yaml").read_text())
    assert set(documented) == set(SERVICES)
    for name, spec in documented.items():
        strings = STRINGS["services"][name]
        assert set(spec["fields"]) == set(strings["fields"]), name


def test_icons_reference_existing_entities() -> None:
    icons = json.loads((ROOT / "icons.json").read_text())
    for platform, keys in icons["entity"].items():
        for key in keys:
            assert key in STRINGS["entity"][platform]
    assert set(icons["services"]) == set(SERVICES)


def test_state_translations() -> None:
    """Round 2, F4: every state BEHAVIOUR §2.1 and §2.3 list has an English word."""
    sensors = STRINGS["entity"]["sensor"]
    job_states = {
        "printing",
        "paused",
        "finished",
        "failed",
        "downloading",
        "checking",
        "preheating",
        "slicing",
        "levelling",
        "idle",
        "unknown",
    }
    assert set(sensors["job_state"]["state"]) == job_states
    assert set(_JOB_STATE_TEXT.values()) <= job_states
    assert set(sensors["current_status"]["state"]) == {
        "moving",
        "busy",
        "available",
        "unknown",
    }
    for key in ("job_state", "current_status"):
        assert all(sensors[key]["state"].values())
