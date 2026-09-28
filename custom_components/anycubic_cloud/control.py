"""Orders to the printer, shared by buttons, numbers, switches and actions.

Every order goes over LAN (BEHAVIOUR §5.3). Failures surface as Home
Assistant errors carrying the printer's message (§2.12). Controls end with an
immediate refresh unless the specification says otherwise.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from anycubic_lan import AnycubicLanError, NotConnectedError, ReportKind
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from .const import (
    AXIS_XY,
    AXIS_Z,
    DOMAIN,
    FEED_TYPE_FEED,
    FEED_TYPE_FINISH,
    FEED_TYPE_RETRACT,
    HOME_ALL_POLL,
    HOME_ALL_TIMEOUT,
    MOVE_HOME,
)
from .filament import drying_profile
from .model import WORK_BUSY

if TYPE_CHECKING:
    from .coordinator import AnycubicCoordinator
    from .model import Printer


def _printer(coordinator: AnycubicCoordinator) -> Printer:
    return coordinator.printer


async def _send(order: Awaitable[object]) -> None:
    try:
        await order
    except NotConnectedError as err:
        raise HomeAssistantError(
            translation_domain=DOMAIN, translation_key="printer_not_connected"
        ) from err
    except AnycubicLanError as err:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="printer_error",
            translation_placeholders={"message": str(err)},
        ) from err


async def _send_and_refresh(
    coordinator: AnycubicCoordinator, order: Awaitable[object]
) -> None:
    await _send(order)
    await coordinator.async_request_refresh()


# -- job ----------------------------------------------------------------------


async def async_job_command(coordinator: AnycubicCoordinator, action: str) -> None:
    """Pause, resume or stop the job; nothing is sent without one (§2.12)."""
    printer = _printer(coordinator)
    if printer.job is None or printer.job_task_id is None:
        return
    link = coordinator.link
    orders: dict[str, Callable[[], Awaitable[None]]] = {
        "pause": link.async_pause,
        "resume": link.async_resume,
        "stop": link.async_stop,
    }
    await _send_and_refresh(coordinator, orders[action]())


# -- axes (BEHAVIOUR §2.12) ----------------------------------------------------


def _refuse_while_printing(printer: Printer) -> None:
    if printer.job_in_progress:
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="printer_printing"
        )


async def async_move_axis(
    coordinator: AnycubicCoordinator, axis: int, move_type: int
) -> None:
    printer = _printer(coordinator)
    _refuse_while_printing(printer)
    distance = (
        0
        if move_type == MOVE_HOME
        else coordinator.ledger.axis_step(printer.printer_id)
    )
    await _send_and_refresh(
        coordinator, coordinator.link.async_move_axis(axis, move_type, distance)
    )


async def async_home_all(coordinator: AnycubicCoordinator) -> None:
    """Home X/Y, wait until neither moving nor busy (at most 45 s), home Z.

    The wait reads the pushed axis/move state (G8).
    """
    printer = _printer(coordinator)
    _refuse_while_printing(printer)
    await _send(coordinator.link.async_move_axis(AXIS_XY, MOVE_HOME, 0))
    # Forget the previous move's state: only a report for this homing ("done"
    # or "failed") ends the wait, not a "done" left over from an earlier jog.
    printer.axis_move_state = "sent"
    loop = asyncio.get_running_loop()
    deadline = loop.time() + HOME_ALL_TIMEOUT
    while loop.time() < deadline:
        await asyncio.sleep(HOME_ALL_POLL)
        if not printer.is_moving and printer.work_status != WORK_BUSY:
            break
    if printer.axis_move_state == "sent":
        printer.axis_move_state = None  # the printer never reported the move
    await _send_and_refresh(
        coordinator, coordinator.link.async_move_axis(AXIS_Z, MOVE_HOME, 0)
    )


async def async_motors_off(coordinator: AnycubicCoordinator) -> None:
    _refuse_while_printing(_printer(coordinator))
    await _send_and_refresh(coordinator, coordinator.link.async_motors_off())


async def async_request_position(coordinator: AnycubicCoordinator) -> None:
    await _send_and_refresh(coordinator, coordinator.link.async_query(ReportKind.AXIS))


# -- temperatures and fans (BEHAVIOUR §2.13; B22: idle or printing) ----------


_TEMPERATURE_TARGETS = {"target_nozzle_temp": "nozzle", "target_hotbed_temp": "bed"}


async def async_set_temperature(
    coordinator: AnycubicCoordinator, key: str, value: int
) -> None:
    """Set one target; the other heater is left alone (PROTOCOL §7.2)."""
    target = {_TEMPERATURE_TARGETS[key]: value}
    await _send_and_refresh(
        coordinator, coordinator.link.async_set_temperatures(**target)
    )


async def async_set_fan(coordinator: AnycubicCoordinator, key: str, value: int) -> None:
    await _send_and_refresh(coordinator, coordinator.link.async_set_fan(key, value))


# -- light (BEHAVIOUR §2.16) ---------------------------------------------------


async def async_set_light(coordinator: AnycubicCoordinator, on: bool) -> None:
    light_type = _printer(coordinator).light_type
    if light_type is None:  # pragma: no cover - the entity is unavailable then
        return
    await _send_and_refresh(
        coordinator, coordinator.link.async_set_light(on, light_type)
    )


# -- ACE (BEHAVIOUR §2.12, §3.11, §4.2, §4.3) ----------------------------------


async def async_ace_refresh(coordinator: AnycubicCoordinator) -> None:
    await _send_and_refresh(
        coordinator, coordinator.link.async_query(ReportKind.MULTI_COLOR_BOX)
    )


async def async_ace_feed(
    coordinator: AnycubicCoordinator,
    box: int,
    slot_index: int,
    *,
    finished: bool = False,
    refresh: bool = True,
) -> None:
    """Feed a slot (or end a feed); nothing is sent without an ACE."""
    printer = _printer(coordinator)
    if not printer.supports_ace or slot_index < 0:
        return
    order = coordinator.link.async_ace_feed(
        box, slot_index, FEED_TYPE_FINISH if finished else FEED_TYPE_FEED
    )
    if refresh:
        await _send_and_refresh(coordinator, order)
    else:
        await _send(order)


async def async_ace_retract(
    coordinator: AnycubicCoordinator, box: int, *, refresh: bool = True
) -> None:
    """Retract what the ACE is feeding (feed type 2, slot -1)."""
    if not _printer(coordinator).supports_ace:
        return
    order = coordinator.link.async_ace_feed(box, -1, FEED_TYPE_RETRACT)
    if refresh:
        await _send_and_refresh(coordinator, order)
    else:
        await _send(order)


def drying_defaults(coordinator: AnycubicCoordinator, box: int) -> tuple[int, int]:
    """(°C, minutes): stored settings, else the profile of the material in
    the ACE being dried (§3.11, B11)."""
    printer = _printer(coordinator)
    ledger = coordinator.ledger
    feeding = ledger.feeding_slot(printer.printer_id) if box == 0 else None
    profile_temp, profile_minutes = drying_profile(printer.ace_material(box, feeding))
    temperature = ledger.drying_setting(printer.printer_id, "temperature")
    duration = ledger.drying_setting(printer.printer_id, "duration")
    return (
        int(temperature) if temperature is not None else profile_temp,
        int(duration) if duration is not None else profile_minutes,
    )


async def async_drying_start(
    coordinator: AnycubicCoordinator, box: int, preset: int | None = None
) -> None:
    printer = _printer(coordinator)
    if printer.ace_box(box) is None:
        return
    if preset is not None:
        values = coordinator.drying_preset(preset)
        if values is None:
            return  # pressing with the preset missing does nothing
        duration, temperature = values
    else:
        temperature, duration = drying_defaults(coordinator, box)
    await _send_and_refresh(
        coordinator, coordinator.link.async_ace_dry(box, 1, temperature, duration)
    )


async def async_drying_stop(coordinator: AnycubicCoordinator, box: int) -> None:
    """Stop drying on this ACE only (DECISIONS V11)."""
    if _printer(coordinator).ace_box(box) is None:
        return
    await _send_and_refresh(coordinator, coordinator.link.async_ace_dry(box, 0, 0, 0))


async def async_set_auto_feed(
    coordinator: AnycubicCoordinator, box: int, enabled: bool
) -> None:
    """Run-out refill; nothing is sent when the state already matches."""
    printer = _printer(coordinator)
    if printer.ace_auto_feed(box) == enabled:
        return
    await _send_and_refresh(
        coordinator, coordinator.link.async_ace_auto_feed(box, enabled)
    )


async def async_set_slot(
    coordinator: AnycubicCoordinator,
    box: int,
    slot_index: int,
    material: str,
    color: list[int],
) -> None:
    """Tell the ACE what is in a slot (§4.2); no ACE or job precondition.

    Slot 0 would become index -1: nothing is sent, as for a feed (§4.3).
    """
    if slot_index < 0:
        return
    await _send_and_refresh(
        coordinator,
        coordinator.link.async_ace_set_slot(box, slot_index, material, color),
    )
