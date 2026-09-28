"""Card and panel registration (FRONTEND §1)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
import pytest

from custom_components.anycubic_cloud import panel

from . import payloads
from .conftest import MockPrinter, lan_entry, setup_entry


@pytest.fixture
def bundles(tmp_path: Path) -> Path:
    (tmp_path / "anycubic-card.js").write_text("card")
    (tmp_path / "entrypoint.1234abcd.js").write_text("panel")
    return tmp_path


def test_find_bundles(tmp_path: Path, bundles: Path) -> None:
    card_hash, panel_file = panel._find_bundles(bundles)  # type: ignore[misc]
    assert len(card_hash) == 8
    assert panel_file == "entrypoint.1234abcd.js"
    assert panel._find_bundles(tmp_path / "missing") is None


async def test_nothing_registered_without_frontend(
    hass: HomeAssistant, printer: MockPrinter
) -> None:
    with patch.object(panel, "_find_bundles") as find:
        await setup_entry(hass, lan_entry())
    find.assert_not_called()


async def test_registration_lifecycle(
    hass: HomeAssistant, printer: MockPrinter, bundles: Path
) -> None:
    """One panel for all entries; removed with the last one (B26)."""
    hass.config.components.add("frontend")
    registered: dict[str, dict[str, object]] = {}

    async def register_panel(hass: HomeAssistant, **kwargs: object) -> None:
        registered[str(kwargs["frontend_url_path"])] = kwargs
        hass.data.setdefault("frontend_panels", {})[kwargs["frontend_url_path"]] = (
            kwargs
        )

    assert await async_setup_component(hass, "http", {})
    with (
        patch.object(panel, "WWW", bundles),
        patch.object(
            panel.panel_custom, "async_register_panel", side_effect=register_panel
        ),
        patch.object(panel.frontend, "add_extra_js_url") as add_js,
        patch.object(panel.frontend, "async_remove_panel") as remove,
    ):
        first = await setup_entry(hass, lan_entry())
        second = await setup_entry(
            hass, lan_entry(unique_id="a4:e8:8d:00:00:02", title="Second")
        )
        assert add_js.call_count == 1
        assert add_js.call_args.args[1].startswith(
            "/anycubic-cloud-panel-static/anycubic-card.js?v="
        )
        assert registered["anycubic_cloud"]["module_url"] == (
            "/anycubic-cloud-panel-static/entrypoint.1234abcd.js"
        )
        assert registered["anycubic_cloud"]["sidebar_title"] == "Anycubic Cloud & LAN"
        assert registered["anycubic_cloud"]["require_admin"] is False

        await hass.config_entries.async_unload(first.entry_id)
        remove.assert_not_called()
        await hass.config_entries.async_unload(second.entry_id)
        remove.assert_called_once()
    assert payloads.HOST


async def test_registration_races(hass: HomeAssistant, bundles: Path) -> None:
    """A concurrent registration that raises is fine if the result exists."""
    hass.config.components.add("frontend")
    assert await async_setup_component(hass, "http", {})
    entry = lan_entry()
    with (
        patch.object(panel, "WWW", bundles),
        patch.object(panel, "_static_path_served", return_value=True),
        patch.object(
            hass.http,
            "async_register_static_paths",
            AsyncMock(side_effect=RuntimeError),
        ),
        patch.object(panel.frontend, "add_extra_js_url"),
        patch.object(
            panel.panel_custom,
            "async_register_panel",
            AsyncMock(side_effect=ValueError("already registered")),
        ),
    ):
        hass.data["frontend_panels"] = {}
        with pytest.raises(ValueError, match="already registered"):
            await panel.async_register_frontend(hass, entry)
        hass.data["frontend_panels"] = {"anycubic_cloud": object()}
        await panel.async_register_frontend(hass, entry)

    hass.data.pop(panel._DATA)
    with (
        patch.object(panel, "WWW", bundles),
        patch.object(
            hass.http,
            "async_register_static_paths",
            AsyncMock(side_effect=RuntimeError),
        ),
        pytest.raises(RuntimeError),
    ):
        await panel.async_register_frontend(hass, entry)
    # A failed registration is retried by the next entry.
    assert not hass.data[panel._DATA]["static"]
    with (
        patch.object(panel, "WWW", bundles),
        patch.object(
            hass.http,
            "async_register_static_paths",
            AsyncMock(side_effect=OSError("disk")),
        ),
        pytest.raises(OSError, match="disk"),
    ):
        await panel.async_register_frontend(hass, entry)
    assert not hass.data[panel._DATA]["static"]


async def test_no_bundles_shipped(hass: HomeAssistant, tmp_path: Path) -> None:
    hass.config.components.add("frontend")
    with patch.object(panel, "WWW", tmp_path):
        await panel.async_register_frontend(hass, lan_entry())
    assert panel._DATA not in hass.data
