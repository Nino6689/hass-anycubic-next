"""Firmware update entity (BEHAVIOUR §2.17, G10, DECISIONS V17).

Firmware updates are a cloud service. Over LAN the printer's installed version
comes from ``info.version`` and, with no target known, is also shown as the
latest: no update is offered and nothing can be installed. The ACE firmware
entities are cloud only and are not created on LAN; ones a 2.x install
registered stay in the registry, never removed (DECISIONS round 2, Q8).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from homeassistant.components.update import (
    UpdateDeviceClass,
    UpdateEntity,
    UpdateEntityDescription,
)
from homeassistant.const import EntityCategory

from .entity import AnycubicEntity, AnycubicEntityDescription, async_add_when_ready

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from .coordinator import AnycubicConfigEntry


@dataclass(frozen=True, kw_only=True)
class AnycubicUpdateDescription(AnycubicEntityDescription, UpdateEntityDescription):
    """A firmware update entity."""


FIRMWARE = AnycubicUpdateDescription(
    key="fw_version",
    device_class=UpdateDeviceClass.FIRMWARE,
    entity_category=EntityCategory.CONFIG,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AnycubicConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the update entity of a config entry."""
    async_add_when_ready(
        entry.runtime_data, (FIRMWARE,), PrinterFirmware, async_add_entities
    )


class PrinterFirmware(AnycubicEntity, UpdateEntity):
    """The printer's firmware."""

    entity_description: AnycubicUpdateDescription

    @property
    def installed_version(self) -> str | None:
        return self.printer.state.firmware_version

    @property
    def latest_version(self) -> str | None:
        return self.installed_version
