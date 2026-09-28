"""Serve the dashboard card and register the side panel (FRONTEND §1).

The card and panel bundles are built separately (the clean frontend). This
module serves them when they are shipped inside the integration, in
``www/``: ``anycubic-card.js`` and one ``entrypoint*.js``. How the bundles
reach this directory is QUESTIONS.md Q6; without them nothing is registered
and the integration works without its card.

Registration happens at the start of entry setup, before the first refresh,
so a failing entry still serves its card (B26).
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntryState

from .const import CONF_CARD_CONFIG, DOMAIN

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

WWW = Path(__file__).parent / "www"
STATIC_PREFIX = "/anycubic-cloud-panel-static"
CARD_FILE = "anycubic-card.js"
PANEL_URL_PATH = "anycubic_cloud"
PANEL_COMPONENT = "anycubic-cloud-panel"
PANEL_TITLE = "Anycubic Cloud & LAN"
PANEL_ICON = "mdi:printer-3d"
_DATA = f"{DOMAIN}_frontend"


def _short_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:8]


def _find_bundles(www: Path) -> tuple[str, str] | None:
    """(card hash, panel file name), or ``None`` when not shipped."""
    card = www / CARD_FILE
    panels = sorted(www.glob("entrypoint*.js"))
    if not card.is_file() or not panels:
        return None
    return _short_hash(card), panels[0].name


def _static_path_served(hass: HomeAssistant) -> bool:
    return any(
        resource.canonical == STATIC_PREFIX
        for resource in hass.http.app.router.resources()
        if hasattr(resource, "canonical")
    )


async def async_register_frontend(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Serve the card and register the panel once for the whole integration."""
    if "frontend" not in hass.config.components:
        return
    bundles = await hass.async_add_executor_job(_find_bundles, WWW)
    if bundles is None:
        _LOGGER.debug("No card or panel bundle shipped in %s", WWW)
        return
    card_hash, panel_file = bundles
    state: dict[str, Any] = hass.data.setdefault(_DATA, {})
    if not state.get("static"):
        state["static"] = True
        try:
            await hass.http.async_register_static_paths(
                [StaticPathConfig(STATIC_PREFIX, str(WWW), cache_headers=False)]
            )
        except RuntimeError:
            # Registered by a concurrent setup: fine if it is being served.
            if not _static_path_served(hass):
                raise
        frontend.add_extra_js_url(hass, f"{STATIC_PREFIX}/{CARD_FILE}?v={card_hash}")
    if PANEL_URL_PATH in hass.data.get(frontend.DATA_PANELS, {}):
        return
    try:
        await panel_custom.async_register_panel(
            hass,
            frontend_url_path=PANEL_URL_PATH,
            webcomponent_name=PANEL_COMPONENT,
            sidebar_title=PANEL_TITLE,
            sidebar_icon=PANEL_ICON,
            module_url=f"{STATIC_PREFIX}/{panel_file}",
            embed_iframe=False,
            require_admin=False,
            config=dict(entry.options.get(CONF_CARD_CONFIG) or {}),
        )
    except ValueError:
        # Lost a race with another entry: success if the panel exists.
        if PANEL_URL_PATH not in hass.data.get(frontend.DATA_PANELS, {}):
            raise


def async_unregister_frontend(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove the panel only when no other entry of the domain is loaded."""
    others = [
        other
        for other in hass.config_entries.async_entries(DOMAIN)
        if other.entry_id != entry.entry_id and other.state is ConfigEntryState.LOADED
    ]
    if others:
        return
    if PANEL_URL_PATH in hass.data.get(frontend.DATA_PANELS, {}):
        frontend.async_remove_panel(hass, PANEL_URL_PATH, warn_if_unknown=False)
