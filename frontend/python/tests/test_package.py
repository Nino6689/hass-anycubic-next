"""Checks that the built package agrees with the files it ships."""

import hashlib
import json
from pathlib import Path
import unittest

import anycubic_cloud_frontend as fe


def _hash8(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:8]


class PackageTest(unittest.TestCase):
    def test_files_exist_and_hashes_match(self) -> None:
        root = Path(fe.locate_dir())
        panel = root / fe.entrypoint_js()
        card = root / fe.card_js()
        assert panel.is_file()
        assert card.is_file()
        assert fe.entrypoint_js() == f"entrypoint.{_hash8(panel)}.js"
        assert fe.card_hash() == _hash8(card)
        assert fe.card_js() == "anycubic-card.js"

    def test_names(self) -> None:
        assert fe.webcomponent_name() == "anycubic-cloud-panel"
        assert fe.__version__ == "1.0.0.dev0"
        info = json.loads((Path(fe.locate_dir()) / "build.json").read_text())
        assert info["entrypoint"] == fe.entrypoint_js()
        assert info["webcomponent"] == fe.WEBCOMPONENT_NAME

    def test_panel_defines_its_component(self) -> None:
        text = (Path(fe.locate_dir()) / fe.entrypoint_js()).read_text()
        assert fe.WEBCOMPONENT_NAME in text
        card = (Path(fe.locate_dir()) / fe.card_js()).read_text()
        assert "anycubic-card" in card


if __name__ == "__main__":
    unittest.main()
