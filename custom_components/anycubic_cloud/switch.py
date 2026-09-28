"""Switches (BEHAVIOUR §2.15). ``manual_mqtt_connection_enabled`` is cloud only."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import callback
from homeassistant.exceptions import ServiceValidationError

from . import control
from .const import DOMAIN
from .entity import (
    AnycubicEntity,
    AnycubicEntityDescription,
    Device,
    Kind,
    async_add_when_ready,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from .coordinator import AnycubicConfigEntry, AnycubicCoordinator


@dataclass(frozen=True, kw_only=True)
class AnycubicSwitchDescription(AnycubicEntityDescription, SwitchEntityDescription):
    """A switch of a printer or ACE."""


AI_DETECTION = AnycubicSwitchDescription(
    key="ai_detection_enabled", entity_category=EntityCategory.CONFIG
)
RUNOUT_REFILL = (
    AnycubicSwitchDescription(
        key="multi_color_box_runout_refill", kind=Kind.ACE1, device=Device.ACE1
    ),
    AnycubicSwitchDescription(
        key="secondary_multi_color_box_runout_refill",
        kind=Kind.ACE2,
        device=Device.ACE2,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AnycubicConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the switches of a config entry."""

    def factory(
        coordinator: AnycubicCoordinator, description: AnycubicSwitchDescription
    ) -> AnycubicEntity:
        if description is AI_DETECTION:
            return AiDetectionSwitch(coordinator, description)
        return RunoutRefillSwitch(coordinator, description)

    async_add_when_ready(
        entry.runtime_data, (AI_DETECTION, *RUNOUT_REFILL), factory, async_add_entities
    )


class AiDetectionSwitch(AnycubicEntity, SwitchEntity):
    """AI failure detection. Readable over LAN; changing it is cloud only."""

    entity_description: AnycubicSwitchDescription

    @property
    def is_on(self) -> bool | None:
        # Unknown until the printer has said (§0.3).
        return self.printer.ai_detection_enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._refuse()

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._refuse()

    @staticmethod
    def _refuse() -> None:
        # Order 1243 has no LAN form (BEHAVIOUR §5.3).
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="cloud_only_control"
        )


class RunoutRefillSwitch(AnycubicEntity, SwitchEntity):
    """ACE run-out refill (auto-feed)."""

    entity_description: AnycubicSwitchDescription

    def __init__(
        self,
        coordinator: AnycubicCoordinator,
        description: AnycubicSwitchDescription,
    ) -> None:
        super().__init__(coordinator, description)
        self._box = 0 if description.device is Device.ACE1 else 1
        self._pending: bool | None = None

    @property
    def is_on(self) -> bool:
        if self._pending is not None:
            return self._pending
        return self.printer.ace_auto_feed(self._box)

    @callback
    def _handle_coordinator_update(self) -> None:
        # The printer's own report replaces the state set on sending.
        self._pending = None
        super()._handle_coordinator_update()

    async def _set(self, enabled: bool) -> None:
        if self.is_on == enabled:
            return
        await control.async_set_auto_feed(self.coordinator, self._box, enabled)
        self._pending = enabled
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(False)
