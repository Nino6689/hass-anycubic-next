"""The Anycubic Cloud & LAN integration (``anycubic_cloud`` 3.0).

This is the LAN half of 3.0. An entry runs over LAN when its options enable
LAN Mode with a printer address - every LAN-only entry, and any 2.x cloud
entry the user switched to LAN Mode. A 2.x cloud entry without LAN Mode keeps
all its data untouched and waits, not ready, for the cloud release.
"""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv, issue_registry as ir
from homeassistant.helpers.typing import ConfigType

from .const import CONF_LAN_HOST, CONF_LAN_MODE_ENABLED, DOMAIN
from .coordinator import AnycubicConfigEntry, AnycubicCoordinator
from .entity import async_register_printer_device
from .identity import is_cloud_entry
from .panel import async_register_frontend, async_unregister_frontend
from .services import async_setup_services

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.CAMERA,
    Platform.LIGHT,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.UPDATE,
]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

ISSUE_CLOUD_PENDING = "cloud_not_supported_yet"


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the actions, with or without entries (BEHAVIOUR §4)."""
    async_setup_services(hass)
    return True


def _issue_id(entry: AnycubicConfigEntry) -> str:
    return f"{ISSUE_CLOUD_PENDING}_{entry.entry_id}"


async def async_setup_entry(hass: HomeAssistant, entry: AnycubicConfigEntry) -> bool:
    """Set up one entry."""
    # The card is served before anything can fail (B26).
    await async_register_frontend(hass, entry)
    host = str(entry.options.get(CONF_LAN_HOST) or "").strip()
    if not entry.options.get(CONF_LAN_MODE_ENABLED) or not host:
        if is_cloud_entry(entry):
            # A 2.x cloud entry: not ready with retries plus a repair issue,
            # its data never modified (confirmed, DECISIONS round 2, Q7).
            ir.async_create_issue(
                hass,
                DOMAIN,
                _issue_id(entry),
                is_fixable=False,
                is_persistent=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key=ISSUE_CLOUD_PENDING,
                translation_placeholders={"name": entry.title},
            )
            raise ConfigEntryNotReady(
                translation_domain=DOMAIN,
                translation_key="cloud_not_supported_yet",
                translation_placeholders={"name": entry.title},
            )
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN, translation_key="lan_mode_off"
        )
    ir.async_delete_issue(hass, DOMAIN, _issue_id(entry))

    coordinator = AnycubicCoordinator(hass, entry, host)
    await coordinator.async_setup()
    entry.runtime_data = coordinator
    await coordinator.async_config_entry_first_refresh()
    async_register_printer_device(coordinator)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: AnycubicConfigEntry) -> bool:
    """Unload an entry; the coordinator closes LAN and saves the ledger."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        async_unregister_frontend(hass, entry)
    return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: AnycubicConfigEntry) -> None:
    """Forget the entry's repair issue."""
    ir.async_delete_issue(hass, DOMAIN, _issue_id(entry))
