"""Pure filament arithmetic and helpers (BEHAVIOUR §3)."""

from __future__ import annotations

import base64

import pytest

from custom_components.anycubic_cloud.error_codes import describe_error
from custom_components.anycubic_cloud.filament import (
    cost,
    density,
    drying_profile,
    grams_from_length,
    history_key,
    is_abrasive,
    nozzle_wear_percent,
    remaining_grams,
    remaining_percent,
    rgb_to_hex,
    split_signature,
    spool_signature,
)
from custom_components.anycubic_cloud.identity import (
    entry_unique_id_for_lan,
    unique_id_mac,
)
from custom_components.anycubic_cloud.lan import redact_payload, redact_topic
from custom_components.anycubic_cloud.model import (
    ace_model_name,
    material_type_from_device_type,
)
from custom_components.anycubic_cloud.spool_image import spool_picture


def test_grams_from_millimetres() -> None:
    """supplies_usage is millimetres (DECISIONS V1): ~2.98 g per metre of PLA."""
    assert grams_from_length(1000, "PLA") == pytest.approx(2.982, abs=0.001)
    # The cloud figure 2.x matched against a 94.5 g slice estimate.
    assert grams_from_length(31783, "pla") == pytest.approx(94.8, abs=0.1)
    assert grams_from_length(1000, "PETG") > grams_from_length(1000, "PLA")
    assert grams_from_length(None, "PLA") == 0
    assert grams_from_length(-5, "PLA") == 0


@pytest.mark.parametrize(
    ("material", "expected"),
    [
        (" pla ", 1.24),
        ("PLA SE", 1.24),  # no match: the default, as BEHAVIOUR §3.2 notes
        ("PAHT-CF", 1.30),
        ("ABS", 1.04),
        ("TPU", 1.21),
        (None, 1.24),
        ("Unobtainium", 1.24),
    ],
)
def test_density(material: str | None, expected: float) -> None:
    assert density(material) == expected


def test_signatures() -> None:
    assert spool_signature("PLA", "#FFFFFF", "SKU") == "PLA|#FFFFFF|SKU"
    assert spool_signature("PLA", "#FFFFFF", None) == "PLA|#FFFFFF|"
    assert spool_signature("", None, " ") is None
    assert split_signature("PLA|#FFFFFF|") == ("PLA", "#FFFFFF", None)
    assert split_signature("PETG") == ("PETG", None, None)


def test_rgb_to_hex() -> None:
    assert rgb_to_hex((0, 128, 255)) == "#0080FF"
    assert rgb_to_hex([1, 2]) is None
    assert rgb_to_hex([1, 2, 300]) is None
    assert rgb_to_hex(None) is None


def test_remaining() -> None:
    assert remaining_grams(334, 51) == 283.0
    assert remaining_percent(334, 51) == 28.3
    assert remaining_percent(5000, 0) == 100.0
    assert remaining_grams(100, 150) == 0
    assert remaining_percent(100, 150) == 0
    assert remaining_grams(None, None) == 1000.0


def test_cost() -> None:
    assert cost(500, 20) == 10.0
    assert cost(0, 20) is None
    assert cost(500, 0) is None
    assert cost(None, 20) is None


def test_nozzle_wear() -> None:
    assert is_abrasive("PAHT-CF")
    assert is_abrasive("pla glow")
    assert not is_abrasive("PLA")
    assert not is_abrasive(None)
    assert nozzle_wear_percent(250) == 25.0
    assert nozzle_wear_percent(5000) == 100.0


def test_drying_profile() -> None:
    assert drying_profile("PETG") == (65, 360)
    assert drying_profile("pa") == (70, 720)
    assert drying_profile("mystery") == (45, 360)


def test_history_key() -> None:
    assert history_key("0622-1002-Wolf") == "Wolf"
    assert history_key(" Wolf ") == "Wolf"
    assert history_key("0622-1002-") is None
    assert history_key(None) is None


def test_identity_helpers() -> None:
    assert unique_id_mac("a4:e8:8d:80:54:c8") == "A4-E8-8D-80-54-C8"
    assert unique_id_mac("A4-E8-8D-80-54-C8") == "A4-E8-8D-80-54-C8"
    assert entry_unique_id_for_lan("A4-E8-8D-80-54-C8", "h") == "a4:e8:8d:80:54:c8"
    assert entry_unique_id_for_lan(None, " 10.0.0.2 ") == "lan-10.0.0.2"


def test_model_helpers() -> None:
    assert material_type_from_device_type("FDM") == "Filament"
    assert material_type_from_device_type("dlp") == "Resin"
    assert material_type_from_device_type("laser") == "laser"
    assert material_type_from_device_type(None) is None
    assert ace_model_name(40001) == "ACE Pro"
    assert ace_model_name(40002) == "ACE"
    assert ace_model_name(None) == "ACE"
    assert ace_model_name(49999) == "ACE"


def test_error_descriptions() -> None:
    assert describe_error(10107) == "Filament broken"
    assert describe_error(11858) == "Unknown error code 11858"


def test_redact_topic() -> None:
    topic = (
        "anycubic/anycubicCloud/v1/printer/public/20025/"
        "372d94454cf5d746d07a8100df8674aa/info/report"
    )
    assert "372d9445" not in redact_topic(topic)
    assert redact_topic(topic).endswith("/**REDACTED**/info/report")


def test_redact_short_numeric_device_id() -> None:
    """A 15-digit device id is hidden too, in report and order topics."""
    for topic in (
        "anycubic/anycubicCloud/v1/printer/public/20025/123456789012345/info/report",
        "anycubic/anycubicCloud/v1/web/printer/20025/123456789012345/light",
    ):
        assert "123456789012345" not in redact_topic(topic)
        assert "20025/**REDACTED**/" in redact_topic(topic)


def test_redact_payload() -> None:
    raw = b'{"urls": {"fileUploadurl": "http://h:18910/gcode_upload?s=SECRET"}}'
    assert b"SECRET" not in redact_payload(raw)
    assert redact_payload(b'{"a": 1}') == b'{"a": 1}'


def test_spool_picture() -> None:
    picture = spool_picture(["#FF0000", "#00ff00", "bad"])
    assert picture is not None
    svg = base64.b64decode(picture.split(",", 1)[1]).decode()
    assert "#FF0000" in svg
    assert "#00FF00" in svg
    assert "bad" not in svg
    assert spool_picture(["nope"]) is None
    assert spool_picture([]) is None
