"""Sensors (BEHAVIOUR §2.1-§2.10). Only keys with a LAN source exist here."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfLength,
    UnitOfMass,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.util import dt as dt_util

from .const import ACE_SLOTS
from .entity import (
    AnycubicEntity,
    AnycubicEntityDescription,
    Device,
    Kind,
    async_add_when_ready,
)
from .filament import rgb_to_hex
from .model import slot_attributes
from .spool_image import spool_picture

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from .coordinator import AnycubicConfigEntry, AnycubicCoordinator

# The unit text 2.x reported, capital L included (COMPAT §3 "State formats").
UNIT_LAYERS = "Layers"

type ValueFn = Callable[[AnycubicCoordinator], Any]
type AttrsFn = Callable[[AnycubicCoordinator], dict[str, Any] | None]


@dataclass(frozen=True, kw_only=True)
class AnycubicSensorDescription(AnycubicEntityDescription, SensorEntityDescription):
    """A sensor reading one value of the printer."""

    value_fn: ValueFn
    attrs_fn: AttrsFn | None = None
    monetary: bool = False


def _minutes_dhm(minutes: int | None) -> str | None:
    if minutes is None:
        return None
    days, rest = divmod(minutes, 1440)
    hours, mins = divmod(rest, 60)
    return f"{days}:{hours}:{mins}"


def _job_eta(c: AnycubicCoordinator) -> datetime | None:
    """now + remaining minutes, to the minute (BEHAVIOUR §1.6, G22)."""
    remaining = c.printer.job_remaining_minutes
    if not remaining:
        return None
    eta = dt_util.utcnow() + timedelta(minutes=remaining)
    return eta.replace(second=0, microsecond=0)


def _current_status_attrs(c: AnycubicCoordinator) -> dict[str, Any]:
    p = c.printer
    return {
        "model": p.identity.model_name,
        "machine_type": p.identity.model_id,
        "supported_functions": [],
        "material_type": p.identity.material_type,
        "device_status_code": p.device_status,
        "is_printing_code": p.work_status,
        "print_status_code": p.job_status_code,
        "peripherals": p.peripherals,
        # Lifetime figures come from the cloud only (BEHAVIOUR §2.4).
        "total_material_used": None,
        "total_print_time_hrs": None,
        "total_print_time_dhm": None,
        "job_download_progress": None,
    }


def _job_name_attrs(c: AnycubicCoordinator) -> dict[str, Any]:
    p = c.printer
    job = p.job
    elapsed = p.job_elapsed_minutes
    remaining = p.job_remaining_minutes
    total = (
        elapsed + remaining if elapsed is not None and remaining is not None else None
    )
    attrs: dict[str, Any] = {}
    if job is not None and job.filename:
        attrs["file_name"] = job.filename
    # Always present (BEHAVIOUR §2.3); the slicer details are cloud only.
    attrs |= {
        "created_timestamp": None,
        "finished_timestamp": None,
        "print_total_time": None,
        "print_total_time_minutes": total,
        "print_total_time_dhm": _minutes_dhm(total),
        "print_supplies_usage": p.job_filament_used,
        "print_status_message": None,
    }
    return attrs


def _speed_mode_attrs(c: AnycubicCoordinator) -> dict[str, Any]:
    p = c.printer
    return {
        "available_modes": p.speed_modes,
        "print_speed_mode_code": p.speed_mode_code,
    }


def _target_attrs(c: AnycubicCoordinator) -> dict[str, Any]:
    # The allowed range comes from the cloud job detail: null on LAN.
    return {"limit_min": None, "limit_max": None}


def _external_attrs(c: AnycubicCoordinator) -> dict[str, Any]:
    spool = c.printer.external_spool
    if spool is None:
        return {}
    return {
        "material": spool.material,
        "color": spool.color,
        "color_hex": rgb_to_hex(spool.color),
        "loaded": spool.loaded,
    }


def _external_material(c: AnycubicCoordinator) -> str | None:
    spool = c.printer.external_spool
    if spool is None or not spool.loaded:
        return None
    return spool.material


def _axis_position(axis: str) -> ValueFn:
    return lambda c: c.printer.axis_position(axis)


def _slot_remaining(number: int) -> ValueFn:
    return lambda c: c.ledger.slot_remaining(c.printer, number)


def _slot_remaining_percent(number: int) -> ValueFn:
    return lambda c: c.ledger.slot_remaining_percent(c.printer, number)


def _forecast(name: str) -> ValueFn:
    return lambda c: getattr(c.forecast, name) if c.forecast is not None else None


def _forecast_source(c: AnycubicCoordinator) -> dict[str, Any]:
    return {"source": c.forecast.source if c.forecast is not None else "unknown"}


def _ledger(name: str) -> ValueFn:
    return lambda c: getattr(c.ledger, name)(c.printer.printer_id)


PRINTER_SENSORS: tuple[AnycubicSensorDescription, ...] = (
    AnycubicSensorDescription(
        key="current_status",
        value_fn=lambda c: c.printer.current_status,
        attrs_fn=_current_status_attrs,
    ),
    AnycubicSensorDescription(
        key="last_error_code",
        value_fn=lambda c: c.printer.last_error_code,
    ),
    AnycubicSensorDescription(
        key="last_error",
        value_fn=lambda c: c.printer.last_error,
    ),
    AnycubicSensorDescription(
        key="job_name",
        value_fn=lambda c: c.printer.job_name,
        attrs_fn=_job_name_attrs,
    ),
    AnycubicSensorDescription(
        key="job_progress",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c: c.printer.job_progress,
    ),
    AnycubicSensorDescription(
        key="job_time_elapsed",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c: c.printer.job_elapsed_minutes,
    ),
    AnycubicSensorDescription(
        key="job_time_remaining",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c: c.printer.job_remaining_minutes,
    ),
    AnycubicSensorDescription(
        key="job_state",
        value_fn=lambda c: c.printer.job_state,
    ),
    AnycubicSensorDescription(
        key="job_eta",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_job_eta,
    ),
    AnycubicSensorDescription(
        key="job_current_layer",
        native_unit_of_measurement=UNIT_LAYERS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c: c.printer.job.current_layer if c.printer.job else None,
    ),
    AnycubicSensorDescription(
        key="job_total_layers",
        native_unit_of_measurement=UNIT_LAYERS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c: c.printer.job.total_layers if c.printer.job else None,
    ),
    AnycubicSensorDescription(
        key="job_filament_used",
        native_unit_of_measurement=UnitOfLength.MILLIMETERS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c: c.printer.job_filament_used,
    ),
    *(
        AnycubicSensorDescription(
            key=f"axis_position_{axis}",
            native_unit_of_measurement=UnitOfLength.MILLIMETERS,
            device_class=SensorDeviceClass.DISTANCE,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=1,
            entity_registry_enabled_default=False,
            value_fn=_axis_position(axis),
        )
        for axis in ("x", "y", "z")
    ),
    AnycubicSensorDescription(
        key="external_spool_material",
        entity_registry_enabled_default=False,
        value_fn=_external_material,
        attrs_fn=_external_attrs,
    ),
)

FDM_SENSORS: tuple[AnycubicSensorDescription, ...] = (
    *(
        AnycubicSensorDescription(
            key=key,
            kind=Kind.FDM,
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
            device_class=SensorDeviceClass.TEMPERATURE,
            state_class=SensorStateClass.MEASUREMENT,
            value_fn=fn,
            attrs_fn=attrs,
        )
        for key, fn, attrs in (
            ("curr_nozzle_temp", lambda c: c.printer.nozzle_temperature, None),
            ("curr_hotbed_temp", lambda c: c.printer.hotbed_temperature, None),
            (
                "target_nozzle_temp",
                lambda c: c.printer.target_nozzle_temperature,
                _target_attrs,
            ),
            (
                "target_hotbed_temp",
                lambda c: c.printer.target_hotbed_temperature,
                _target_attrs,
            ),
        )
    ),
    AnycubicSensorDescription(
        key="fan_speed_pct",
        kind=Kind.FDM,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c: c.printer.fan_speed,
    ),
    AnycubicSensorDescription(
        key="aux_fan_speed_pct",
        kind=Kind.FDM,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c: c.printer.aux_fan_speed,
    ),
    AnycubicSensorDescription(
        key="print_speed_pct",
        kind=Kind.FDM,
        state_class=SensorStateClass.MEASUREMENT,
        # Read from the raw print report (DECISIONS round 2, Q2.2).
        value_fn=lambda c: c.printer.print_speed_pct,
    ),
    AnycubicSensorDescription(
        key="job_speed_mode",
        kind=Kind.FDM,
        value_fn=lambda c: c.printer.job_speed_mode,
        attrs_fn=_speed_mode_attrs,
    ),
    # Computed from the ledger (BEHAVIOUR §2.10).
    AnycubicSensorDescription(
        key="job_filament_required",
        kind=Kind.FDM,
        native_unit_of_measurement=UnitOfMass.GRAMS,
        device_class=SensorDeviceClass.WEIGHT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=_forecast("required"),
        attrs_fn=_forecast_source,
    ),
    AnycubicSensorDescription(
        key="job_filament_shortfall",
        kind=Kind.FDM,
        native_unit_of_measurement=UnitOfMass.GRAMS,
        device_class=SensorDeviceClass.WEIGHT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=_forecast("shortfall"),
    ),
    AnycubicSensorDescription(
        key="job_filament_runs_out_at",
        kind=Kind.FDM,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        entity_registry_enabled_default=False,
        value_fn=_forecast("runs_out_at"),
    ),
    AnycubicSensorDescription(
        key="job_cost",
        kind=Kind.FDM,
        device_class=SensorDeviceClass.MONETARY,
        suggested_display_precision=2,
        monetary=True,
        value_fn=_forecast("cost"),
    ),
    AnycubicSensorDescription(
        key="last_job_cost",
        kind=Kind.FDM,
        device_class=SensorDeviceClass.MONETARY,
        suggested_display_precision=2,
        monetary=True,
        value_fn=_ledger("last_job_cost"),
    ),
    AnycubicSensorDescription(
        key="last_job_filament",
        kind=Kind.FDM,
        native_unit_of_measurement=UnitOfMass.GRAMS,
        device_class=SensorDeviceClass.WEIGHT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        entity_registry_enabled_default=False,
        value_fn=_ledger("last_job_filament"),
    ),
    AnycubicSensorDescription(
        key="filament_cost_total",
        kind=Kind.FDM,
        device_class=SensorDeviceClass.MONETARY,
        # G20: total for the lifetime spend.
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=2,
        monetary=True,
        value_fn=_ledger("cost_total"),
        attrs_fn=lambda c: {
            "by_material_g": c.ledger.material_totals(c.printer.printer_id)
        },
    ),
    AnycubicSensorDescription(
        key="nozzle_filament_total",
        kind=Kind.FDM,
        native_unit_of_measurement=UnitOfMass.GRAMS,
        device_class=SensorDeviceClass.WEIGHT,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=1,
        entity_registry_enabled_default=False,
        value_fn=_ledger("nozzle_total"),
    ),
    AnycubicSensorDescription(
        key="nozzle_abrasive_filament",
        kind=Kind.FDM,
        native_unit_of_measurement=UnitOfMass.GRAMS,
        device_class=SensorDeviceClass.WEIGHT,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=1,
        value_fn=_ledger("nozzle_abrasive"),
    ),
    AnycubicSensorDescription(
        key="nozzle_wear_percent",
        kind=Kind.FDM,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=1,
        value_fn=_ledger("nozzle_wear"),
    ),
    AnycubicSensorDescription(
        key="spool_inventory_remaining",
        kind=Kind.FDM,
        native_unit_of_measurement=UnitOfMass.GRAMS,
        device_class=SensorDeviceClass.WEIGHT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda c: c.ledger.spool_inventory_remaining(),
        attrs_fn=lambda c: {
            "spools": [entry.as_dict() for entry in c.ledger.spool_inventory()]
        },
    ),
    AnycubicSensorDescription(
        key="spool_inventory_count",
        kind=Kind.FDM,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda c: c.ledger.spool_inventory_count(),
    ),
)


def _ace_sensors(box: int) -> tuple[AnycubicSensorDescription, ...]:
    """Sensors shared by both ACE units (BEHAVIOUR §2.8, §2.9)."""
    prefix = "" if box == 0 else "secondary_"
    kind = Kind.ACE1 if box == 0 else Kind.ACE2
    device = Device.ACE1 if box == 0 else Device.ACE2

    def loaded(c: AnycubicCoordinator) -> int | None:
        index = c.printer.ace_loaded_slot_index(box)
        return index + 1 if index is not None else None

    return (
        AnycubicSensorDescription(
            key=f"{prefix}ace_spools",
            kind=kind,
            device=device,
            value_fn=lambda c: "active" if c.printer.spool_info(box) else "inactive",
            attrs_fn=lambda c: {
                "spool_info": c.printer.spool_info(box),
                "box_info": c.printer.box_info(box),
            },
        ),
        AnycubicSensorDescription(
            key=f"{prefix}ace_loaded_slot",
            kind=kind,
            device=device,
            value_fn=loaded,
        ),
        AnycubicSensorDescription(
            key=f"{prefix}ace_current_temperature",
            kind=kind,
            device=device,
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
            device_class=SensorDeviceClass.TEMPERATURE,
            state_class=SensorStateClass.MEASUREMENT,
            value_fn=lambda c: float(c.printer.ace_temperature(box)),
        ),
        AnycubicSensorDescription(
            key=f"{prefix}dry_status_target_temperature",
            kind=kind,
            device=device,
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
            device_class=SensorDeviceClass.TEMPERATURE,
            state_class=SensorStateClass.MEASUREMENT,
            value_fn=lambda c: float(c.printer.drying_value(box, "target_temp")),
        ),
        # Minutes, deliberately without a declared unit (BEHAVIOUR §8).
        AnycubicSensorDescription(
            key=f"{prefix}dry_status_total_duration",
            kind=kind,
            device=device,
            state_class=SensorStateClass.MEASUREMENT,
            value_fn=lambda c: round(c.printer.drying_value(box, "duration")),
        ),
        AnycubicSensorDescription(
            key=f"{prefix}dry_status_remaining_time",
            kind=kind,
            device=device,
            state_class=SensorStateClass.MEASUREMENT,
            value_fn=lambda c: round(c.printer.drying_value(box, "remain_time")),
        ),
    )


def _slot_value(box: int, number: int) -> ValueFn:
    def value(c: AnycubicCoordinator) -> str | None:
        slot = c.printer.ace_slot(box, number)
        if c.printer.slot_is_empty(slot):
            return None  # B16
        return slot.material if slot is not None else None

    return value


def _slot_attrs(box: int, number: int) -> AttrsFn:
    def attrs(c: AnycubicCoordinator) -> dict[str, Any] | None:
        slot = c.printer.ace_slot(box, number)
        if slot is None:
            return None
        full = slot_attributes(slot, number - 1)
        full.pop("color_group")
        full.pop("icon_type")
        return full

    return attrs


FIRST_ACE_SENSORS: tuple[AnycubicSensorDescription, ...] = (
    *_ace_sensors(0),
    AnycubicSensorDescription(
        key="box_fan_level",
        kind=Kind.ACE1,
        device=Device.ACE1,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c: c.printer.box_fan_level,
    ),
    *(
        description
        for number in ACE_SLOTS
        for description in (
            AnycubicSensorDescription(
                key=f"ace_slot_{number}",
                kind=Kind.ACE1,
                device=Device.ACE1,
                value_fn=_slot_value(0, number),
                attrs_fn=_slot_attrs(0, number),
            ),
            AnycubicSensorDescription(
                key=f"ace_slot_{number}_filament_remaining",
                kind=Kind.ACE1,
                device=Device.ACE1,
                native_unit_of_measurement=UnitOfMass.GRAMS,
                device_class=SensorDeviceClass.WEIGHT,
                state_class=SensorStateClass.MEASUREMENT,
                suggested_display_precision=0,
                entity_registry_enabled_default=False,
                value_fn=_slot_remaining(number),
            ),
            AnycubicSensorDescription(
                key=f"ace_slot_{number}_filament_remaining_percent",
                kind=Kind.ACE1,
                device=Device.ACE1,
                native_unit_of_measurement=PERCENTAGE,
                state_class=SensorStateClass.MEASUREMENT,
                suggested_display_precision=0,
                entity_registry_enabled_default=False,
                value_fn=_slot_remaining_percent(number),
            ),
        )
    ),
)

SECOND_ACE_SENSORS = _ace_sensors(1)

SENSORS: tuple[AnycubicSensorDescription, ...] = (
    *PRINTER_SENSORS,
    *FDM_SENSORS,
    *FIRST_ACE_SENSORS,
    *SECOND_ACE_SENSORS,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AnycubicConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensors of a config entry."""
    async_add_when_ready(
        entry.runtime_data, SENSORS, AnycubicSensor, async_add_entities
    )


class AnycubicSensor(AnycubicEntity, SensorEntity):
    """A printer or ACE sensor."""

    entity_description: AnycubicSensorDescription

    @property
    def _value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator)

    @property
    def available(self) -> bool:
        """A sensor with no value is unavailable, not unknown (§0.3)."""
        return super().available and self._value is not None

    @property
    def native_value(self) -> Any:
        return self._value

    @property
    def native_unit_of_measurement(self) -> str | None:
        if self.entity_description.monetary:
            return self.hass.config.currency
        return super().native_unit_of_measurement

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if (attrs_fn := self.entity_description.attrs_fn) is None:
            return None
        return attrs_fn(self.coordinator)

    @property
    def entity_picture(self) -> str | None:
        key = self.entity_description.key
        if not key.startswith("ace_slot_") or not key[-1].isdigit():
            return None
        attrs = self.extra_state_attributes or {}
        if attrs.get("edit_status") == 2:
            return None
        return spool_picture(list(attrs.get("colors_hex") or []))
