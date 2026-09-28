"""Checks that the built package agrees with the files it ships."""

import hashlib
import json
import unittest
from pathlib import Path

import anycubic_cloud_frontend as fe


def _hash8(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:8]


class PackageTest(unittest.TestCase):
    def test_files_exist_and_hashes_match(self) -> None:
        root = Path(fe.locate_dir())
        panel = root / fe.entrypoint_js()
        card = root / fe.card_js()
        self.assertTrue(panel.is_file())
        self.assertTrue(card.is_file())
        self.assertEqual(fe.entrypoint_js(), f"entrypoint.{_hash8(panel)}.js")
        self.assertEqual(fe.card_hash(), _hash8(card))
        self.assertEqual(fe.card_js(), "anycubic-card.js")

    def test_names(self) -> None:
        self.assertEqual(fe.webcomponent_name(), "anycubic-cloud-panel")
        self.assertEqual(fe.__version__, "1.0.0.dev0")
        info = json.loads((Path(fe.locate_dir()) / "build.json").read_text())
        self.assertEqual(info["entrypoint"], fe.entrypoint_js())
        self.assertEqual(info["webcomponent"], fe.WEBCOMPONENT_NAME)

    def test_panel_defines_its_component(self) -> None:
        text = (Path(fe.locate_dir()) / fe.entrypoint_js()).read_text()
        self.assertIn(fe.WEBCOMPONENT_NAME, text)
        card = (Path(fe.locate_dir()) / fe.card_js()).read_text()
        self.assertIn("anycubic-card", card)


if __name__ == "__main__":
    unittest.main()
