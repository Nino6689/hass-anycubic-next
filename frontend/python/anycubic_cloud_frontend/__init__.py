"""Built frontend for the anycubic_cloud Home Assistant integration.

The integration serves :func:`locate_dir` at ``/anycubic-cloud-panel-static``,
registers the panel module :func:`entrypoint_js` as the custom element
:func:`webcomponent_name`, and loads the card as
``anycubic-card.js?v=<card_hash()>``. All names and hashes are written by the
frontend build, so they always match the files in :func:`locate_dir`.
"""

from __future__ import annotations

from pathlib import Path

__version__ = "1.0.0.dev0"

WEBCOMPONENT_NAME = "anycubic-cloud-panel"

try:
    from ._build import CARD_HASH, CARD_JS, ENTRYPOINT_JS, FRONTEND_VERSION, PANEL_HASH
except ImportError as err:  # pragma: no cover - only in an unbuilt checkout
    raise ImportError(
        "anycubic_cloud_frontend has not been built; run `npm run build` in frontend/"
    ) from err

__all__ = [
    "CARD_HASH",
    "CARD_JS",
    "ENTRYPOINT_JS",
    "FRONTEND_VERSION",
    "PANEL_HASH",
    "WEBCOMPONENT_NAME",
    "card_hash",
    "card_js",
    "entrypoint_js",
    "locate_dir",
    "webcomponent_name",
]


def locate_dir() -> str:
    """Return the directory holding the built panel and card files."""
    return str(Path(__file__).parent / "dist")


def entrypoint_js() -> str:
    """Return the panel module's filename (content-hashed)."""
    return ENTRYPOINT_JS


def webcomponent_name() -> str:
    """Return the panel's custom element name."""
    return WEBCOMPONENT_NAME


def card_js() -> str:
    """Return the card module's stable filename."""
    return CARD_JS


def card_hash() -> str:
    """Return the card module's content hash, for the ``?v=`` query string."""
    return CARD_HASH
