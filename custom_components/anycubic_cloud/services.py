"""Actions (BEHAVIOUR §4, COMPAT §4).

All 27 actions are registered when the integration loads, even with no entry,
so automations that use them validate. Those with a LAN form work on LAN
entries; the cloud-only ones raise a translated error there.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv, device_registry as dr
import voluptuous as vol

from . import control
from .const import DOMAIN, SET_SLOT_MATERIALS
from .coordinator import AnycubicCoordinator
from .identity import printer_identifier
from .model import WORK_BUSY

ATTR_CONFIG_ENTRY = "config_entry"
ATTR_DEVICE_ID = "device_id"
ATTR_PRINTER_ID = "printer_id"
ATTR_BOX_ID = "box_id"
ATTR_SLOT_NUMBER = "slot_number"
ATTR_RED = "slot_color_red"
ATTR_GREEN = "slot_color_green"
ATTR_BLUE = "slot_color_blue"
ATTR_FINISHED = "finished"
ATTR_UPLOADED_FILE = "uploaded_gcode_file"
ATTR_FILENAME = "filename"
ATTR_FILE_ID = "file_id"
ATTR_SPEED_MODE = "speed_mode"
ATTR_TEMPERATURE = "temperature"
ATTR_SPEED = "speed"
ATTR_LAYERS = "layers"
ATTR_TIME = "time"

_NON_NEGATIVE_INT = vol.All(vol.Coerce(int), vol.Range(min=0))
_NON_NEGATIVE_FLOAT = vol.All(vol.Coerce(float), vol.Range(min=0))
_COLOR = vol.All(vol.Coerce(int), vol.Range(min=0, max=255))

_PRINTER_SELECTOR: dict[vol.Marker, Any] = {
    vol.Required(ATTR_CONFIG_ENTRY): cv.string,
    vol.Optional(ATTR_DEVICE_ID): vol.Any(cv.string, [cv.string]),
    vol.Optional(ATTR_PRINTER_ID): _NON_NEGATIVE_INT,
}


def _schema(fields: dict[vol.Marker, Any]) -> vol.All:
    """The printer selector plus ``fields``; one of device/printer id needed."""
    return vol.All(
        vol.Schema({**_PRINTER_SELECTOR, **fields}),
        cv.has_at_least_one_key(ATTR_DEVICE_ID, ATTR_PRINTER_ID),
    )


SET_SLOT_SCHEMA = _schema(
    {
        vol.Optional(ATTR_BOX_ID, default=0): _NON_NEGATIVE_INT,
        vol.Required(ATTR_SLOT_NUMBER): _NON_NEGATIVE_INT,
        vol.Required(ATTR_RED): _COLOR,
        vol.Required(ATTR_GREEN): _COLOR,
        vol.Required(ATTR_BLUE): _COLOR,
    }
)
EXTRUDE_SCHEMA = _schema(
    {
        vol.Optional(ATTR_BOX_ID, default=0): _NON_NEGATIVE_INT,
        vol.Required(ATTR_SLOT_NUMBER): _NON_NEGATIVE_INT,
        vol.Optional(ATTR_FINISHED, default=False): cv.boolean,
    }
)
RETRACT_SCHEMA = _schema({vol.Optional(ATTR_BOX_ID, default=0): _NON_NEGATIVE_INT})
PRINT_UPLOAD_SCHEMA = _schema(
    {
        vol.Optional(ATTR_SLOT_NUMBER): vol.All(cv.ensure_list, [_NON_NEGATIVE_INT]),
        vol.Required(ATTR_UPLOADED_FILE): cv.string,
    }
)
FILENAME_SCHEMA = _schema({vol.Required(ATTR_FILENAME): cv.string})
FILE_ID_SCHEMA = _schema({vol.Required(ATTR_FILE_ID): _NON_NEGATIVE_INT})
SPEED_MODE_SCHEMA = _schema({vol.Required(ATTR_SPEED_MODE): _NON_NEGATIVE_INT})
TEMPERATURE_SCHEMA = _schema({vol.Required(ATTR_TEMPERATURE): _NON_NEGATIVE_INT})
SPEED_SCHEMA = _schema({vol.Required(ATTR_SPEED): _NON_NEGATIVE_INT})
LAYERS_SCHEMA = _schema({vol.Required(ATTR_LAYERS): _NON_NEGATIVE_INT})
TIME_SCHEMA = _schema({vol.Required(ATTR_TIME): _NON_NEGATIVE_FLOAT})

type Handler = Callable[[AnycubicCoordinator, ServiceCall], Awaitable[None]]


def _error(key: str, **placeholders: str) -> ServiceValidationError:
    return ServiceValidationError(
        translation_domain=DOMAIN,
        translation_key=key,
        translation_placeholders=placeholders or None,
    )


def _resolve(hass: HomeAssistant, call: ServiceCall) -> AnycubicCoordinator:
    """The coordinator of the printer an action targets (BEHAVIOUR §4.1)."""
    entry_id = call.data[ATTR_CONFIG_ENTRY]
    entry = hass.config_entries.async_get_entry(entry_id)
    if entry is None or entry.domain != DOMAIN:
        raise _error("config_entry_not_found")
    if entry.state is not ConfigEntryState.LOADED:
        raise _error("config_entry_not_loaded")
    coordinator: AnycubicCoordinator = entry.runtime_data
    printer = coordinator.printer
    if (device_ids := call.data.get(ATTR_DEVICE_ID)) is not None:
        # device_id wins when both are given.
        if isinstance(device_ids, list):
            if len(device_ids) != 1:
                raise _error("one_printer_at_a_time")
            device_ids = device_ids[0]
        device = dr.async_get(hass).async_get(device_ids)
        if (
            device is None
            or printer_identifier(entry, printer.printer_id) not in device.identifiers
        ):
            raise _error("printer_not_found")
        return coordinator
    if call.data[ATTR_PRINTER_ID] != printer.printer_id:
        raise _error("printer_not_found")
    return coordinator


# -- handlers ------------------------------------------------------------------


def _set_slot(material: str) -> Handler:
    async def handler(coordinator: AnycubicCoordinator, call: ServiceCall) -> None:
        color = [call.data[ATTR_RED], call.data[ATTR_GREEN], call.data[ATTR_BLUE]]
        await control.async_set_slot(
            coordinator,
            call.data[ATTR_BOX_ID],
            call.data[ATTR_SLOT_NUMBER] - 1,
            material,
            color,
        )

    return handler


async def _extrude(coordinator: AnycubicCoordinator, call: ServiceCall) -> None:
    await control.async_ace_feed(
        coordinator,
        call.data[ATTR_BOX_ID],
        call.data[ATTR_SLOT_NUMBER] - 1,
        finished=call.data[ATTR_FINISHED],
        refresh=False,
    )


async def _retract(coordinator: AnycubicCoordinator, call: ServiceCall) -> None:
    await control.async_ace_retract(coordinator, call.data[ATTR_BOX_ID], refresh=False)


async def _cloud_only(coordinator: AnycubicCoordinator, call: ServiceCall) -> None:
    # No LAN form (BEHAVIOUR §4.7); the cloud cannot reach a printer in LAN
    # Mode, and cloud support arrives in a later 3.0 release.
    raise _error("cloud_only_action", action=call.service)


def _running_job_required(coordinator: AnycubicCoordinator) -> None:
    """Checked in this order (BEHAVIOUR §4.6)."""
    printer = coordinator.printer
    if printer.work_status != WORK_BUSY:
        raise _error("printer_not_busy")
    if printer.job is None:
        raise _error("no_job")
    if not printer.job_in_progress:
        raise _error("job_not_in_progress")


async def _speed_mode(coordinator: AnycubicCoordinator, call: ServiceCall) -> None:
    _running_job_required(coordinator)
    printer = coordinator.printer
    codes = {mode["mode"] for mode in printer.speed_modes}
    # LAN publishes no list of modes, so this always refuses there. With a
    # list (cloud phase) the code would be sent as a print/update order.
    if call.data[ATTR_SPEED_MODE] not in codes:
        raise _error("speed_mode_unavailable")


def _temperature(key: str) -> Handler:
    async def handler(coordinator: AnycubicCoordinator, call: ServiceCall) -> None:
        await control.async_set_temperature(
            coordinator, key, call.data[ATTR_TEMPERATURE]
        )

    return handler


def _fan(key: str) -> Handler:
    async def handler(coordinator: AnycubicCoordinator, call: ServiceCall) -> None:
        await control.async_set_fan(coordinator, key, call.data[ATTR_SPEED])

    return handler


SERVICES: dict[str, tuple[vol.All, Handler]] = {
    **{
        f"multi_color_box_set_slot_{suffix}": (SET_SLOT_SCHEMA, _set_slot(material))
        for suffix, material in SET_SLOT_MATERIALS.items()
    },
    "multi_color_box_filament_extrude": (EXTRUDE_SCHEMA, _extrude),
    "multi_color_box_filament_retract": (RETRACT_SCHEMA, _retract),
    "print_and_upload_save_in_cloud": (PRINT_UPLOAD_SCHEMA, _cloud_only),
    "print_and_upload_no_cloud_save": (PRINT_UPLOAD_SCHEMA, _cloud_only),
    "print_local_file": (FILENAME_SCHEMA, _cloud_only),
    "delete_file_local": (FILENAME_SCHEMA, _cloud_only),
    "delete_file_udisk": (FILENAME_SCHEMA, _cloud_only),
    "delete_file_cloud": (FILE_ID_SCHEMA, _cloud_only),
    "change_print_speed_mode": (SPEED_MODE_SCHEMA, _speed_mode),
    "change_print_target_nozzle_temperature": (
        TEMPERATURE_SCHEMA,
        _temperature("target_nozzle_temp"),
    ),
    "change_print_target_hotbed_temperature": (
        TEMPERATURE_SCHEMA,
        _temperature("target_hotbed_temp"),
    ),
    "change_print_fan_speed": (SPEED_SCHEMA, _fan("fan_speed_pct")),
    "change_print_aux_fan_speed": (SPEED_SCHEMA, _fan("aux_fan_speed_pct")),
    "change_print_box_fan_speed": (SPEED_SCHEMA, _fan("box_fan_level")),
    "change_print_bottom_layers": (LAYERS_SCHEMA, _cloud_only),
    "change_print_bottom_time": (TIME_SCHEMA, _cloud_only),
    "change_print_off_time": (TIME_SCHEMA, _cloud_only),
    "change_print_on_time": (TIME_SCHEMA, _cloud_only),
}


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register every action of the integration."""
    for name, (schema, handler) in SERVICES.items():

        async def _handle(call: ServiceCall, handler: Handler = handler) -> None:
            await handler(_resolve(hass, call), call)

        hass.services.async_register(DOMAIN, name, _handle, schema=schema)
