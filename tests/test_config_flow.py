"""Config and options flows (BEHAVIOUR §5.8, §5.9)."""

from __future__ import annotations

from typing import Any

from anycubic_lan import (
    InvalidResponseError,
    LanModeDisabledError,
    PrinterUnreachableError,
    UnsupportedPrinterError,
)
from homeassistant.config_entries import SOURCE_DHCP, SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.anycubic_cloud.config_flow import sanitize_card_config
from custom_components.anycubic_cloud.const import DOMAIN

from . import payloads
from .conftest import MockPrinter, cloud_entry, lan_entry, setup_entry

NEW_HOST = "10.0.66.99"
DHCP = DhcpServiceInfo(ip=NEW_HOST, hostname="kobra-s1", macaddress="a4e88d8054c8")


async def _start_local(hass: HomeAssistant) -> Any:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.MENU
    assert result["menu_options"] == ["cloud", "local"]
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "local"}
    )


async def test_local_setup(hass: HomeAssistant, printer: MockPrinter) -> None:
    result = await _start_local(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "local"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"lan_host": f" {payloads.HOST} "}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Anycubic Kobra S1"
    assert result["data"] == {
        "lan_host": payloads.HOST,
        "printer_ids": [payloads.PRINTER_ID],
    }
    assert result["options"] == {"lan_mode_enabled": True, "lan_host": payloads.HOST}
    assert result["result"].unique_id == payloads.MAC
    await hass.async_block_till_done(wait_background_tasks=True)


async def test_local_setup_without_mac_or_model(
    hass: HomeAssistant, printer: MockPrinter
) -> None:
    printer.info = payloads.connection_info(usn=None, model_name=None)
    result = await _start_local(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"lan_host": payloads.HOST}
    )
    assert result["title"] == f"Anycubic ({payloads.HOST})"
    assert result["result"].unique_id == f"lan-{payloads.HOST}"
    await hass.async_block_till_done(wait_background_tasks=True)


@pytest.mark.parametrize(
    ("error", "errors"),
    [
        (LanModeDisabledError("x"), {"base": "lan_printer_in_cloud_mode"}),
        (UnsupportedPrinterError("x"), {"base": "lan_unsupported_printer"}),
        (PrinterUnreachableError("x"), {"base": "lan_unreachable"}),
        (InvalidResponseError("x"), {"base": "lan_unreachable"}),
        (RuntimeError("x"), {"base": "lan_unreachable"}),
    ],
)
async def test_local_errors(
    hass: HomeAssistant,
    printer: MockPrinter,
    error: Exception,
    errors: dict[str, str],
) -> None:
    result = await _start_local(hass)
    printer.handshake_error = error
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"lan_host": payloads.HOST}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == errors
    printer.handshake_error = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"lan_host": payloads.HOST}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done(wait_background_tasks=True)


async def test_local_host_required(hass: HomeAssistant, printer: MockPrinter) -> None:
    result = await _start_local(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"lan_host": "  "}
    )
    assert result["errors"] == {"lan_host": "lan_host_required"}


async def test_local_existing_printer_moves_address(
    hass: HomeAssistant, printer: MockPrinter
) -> None:
    """G24: the address the connection reads (options) is updated."""
    entry = lan_entry()
    entry.add_to_hass(hass)
    result = await _start_local(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"lan_host": NEW_HOST}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.options["lan_host"] == NEW_HOST
    assert entry.data["lan_host"] == NEW_HOST
    await hass.async_block_till_done(wait_background_tasks=True)


async def test_cloud_step_explains(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "cloud"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "cloud_not_supported_yet"


async def test_dhcp_discovery(hass: HomeAssistant, printer: MockPrinter) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_DHCP}, data=DHCP
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "confirm_discovery"
    assert result["description_placeholders"] == {"host": NEW_HOST}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.MENU
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "local"}
    )
    assert result["step_id"] == "local"
    schema_default = result["data_schema"].schema
    assert any(
        getattr(key, "default", lambda: None)() == NEW_HOST for key in schema_default
    )


async def test_dhcp_updates_known_lan_entry(
    hass: HomeAssistant, printer: MockPrinter
) -> None:
    entry = lan_entry()
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_DHCP}, data=DHCP
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.options["lan_host"] == NEW_HOST
    await hass.async_block_till_done(wait_background_tasks=True)

    # The same address again changes nothing.
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_DHCP}, data=DHCP
    )
    assert result["reason"] == "already_configured"


async def test_dhcp_ignores_printer_of_a_cloud_entry(
    hass: HomeAssistant, printer: MockPrinter
) -> None:
    """B27: a printer already on an account entry is not offered again."""
    entry = cloud_entry(lan=False)
    entry.add_to_hass(hass)
    dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "123456-42424242")},
        connections={(dr.CONNECTION_NETWORK_MAC, payloads.MAC)},
    )
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_DHCP}, data=DHCP
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_dhcp_ignores_mac_of_another_integration(
    hass: HomeAssistant, printer: MockPrinter
) -> None:
    other = MockConfigEntry(domain="other")
    other.add_to_hass(hass)
    dr.async_get(hass).async_get_or_create(
        config_entry_id=other.entry_id,
        connections={(dr.CONNECTION_NETWORK_MAC, payloads.MAC)},
    )
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_DHCP}, data=DHCP
    )
    assert result["step_id"] == "confirm_discovery"


async def _reconfigure(hass: HomeAssistant, entry: MockConfigEntry) -> Any:
    return await entry.start_reconfigure_flow(hass)


async def test_reconfigure_lan_only(hass: HomeAssistant, printer: MockPrinter) -> None:
    """V14/G5: Connection acts on the entry being reconfigured."""
    entry = await setup_entry(hass, lan_entry())
    result = await _reconfigure(hass, entry)
    assert result["type"] is FlowResultType.MENU
    assert result["menu_options"] == ["connection"]
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "connection"}
    )
    assert result["step_id"] == "connection"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"lan_mode_enabled": True, "lan_host": NEW_HOST}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.options["lan_host"] == NEW_HOST
    assert entry.data["lan_host"] == NEW_HOST
    await hass.async_block_till_done(wait_background_tasks=True)


async def test_reconfigure_errors_and_other_printer(
    hass: HomeAssistant, printer: MockPrinter
) -> None:
    entry = await setup_entry(hass, lan_entry())
    result = await _reconfigure(hass, entry)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "connection"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"lan_mode_enabled": True, "lan_host": ""}
    )
    assert result["errors"] == {"lan_host": "lan_host_required"}
    printer.info = payloads.connection_info(usn="uuid:fdm:A4-E8-8D-00-00-01")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"lan_mode_enabled": True, "lan_host": NEW_HOST}
    )
    assert result["errors"] == {"base": "lan_different_printer"}
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"lan_mode_enabled": False, "lan_host": NEW_HOST}
    )
    assert result["reason"] == "reconfigure_successful"
    assert entry.options["lan_mode_enabled"] is False
    assert entry.options["lan_host"] == payloads.HOST
    await hass.async_block_till_done(wait_background_tasks=True)


async def test_reconfigure_entry_without_mac_checks_the_printer(
    hass: HomeAssistant, printer: MockPrinter
) -> None:
    """A ``lan-<host>`` entry is matched by its printer id instead."""
    printer.info = payloads.connection_info(usn=None)
    entry = await setup_entry(hass, lan_entry(unique_id=f"lan-{payloads.HOST}"))
    result = await _reconfigure(hass, entry)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "connection"}
    )
    printer.info = payloads.connection_info(usn=None, device_id="otherprinter")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"lan_mode_enabled": True, "lan_host": NEW_HOST}
    )
    assert result["errors"] == {"base": "lan_different_printer"}
    printer.info = payloads.connection_info(usn=None)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"lan_mode_enabled": True, "lan_host": NEW_HOST}
    )
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done(wait_background_tasks=True)


async def test_reconfigure_cloud_entry(
    hass: HomeAssistant, printer: MockPrinter
) -> None:
    entry = cloud_entry(lan=False)
    entry.add_to_hass(hass)
    result = await _reconfigure(hass, entry)
    assert result["menu_options"] == ["reauth", "printer", "connection"]
    for step in ("reauth", "printer"):
        other = await _reconfigure(hass, entry)
        other = await hass.config_entries.flow.async_configure(
            other["flow_id"], {"next_step_id": step}
        )
        assert other["type"] is FlowResultType.ABORT
        assert other["reason"] == "cloud_not_supported_yet"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "connection"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"lan_mode_enabled": True, "lan_host": payloads.HOST}
    )
    assert result["reason"] == "reconfigure_successful"
    # Switching a cloud entry to LAN keeps its account data untouched.
    assert entry.options["lan_host"] == payloads.HOST
    assert "lan_host" not in entry.data
    assert entry.data["user_token"]
    await hass.async_block_till_done(wait_background_tasks=True)


async def test_reauth_explains(hass: HomeAssistant) -> None:
    entry = cloud_entry(lan=False)
    entry.add_to_hass(hass)
    result = await entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "cloud_not_supported_yet"


async def _options(hass: HomeAssistant, entry: MockConfigEntry, step: str) -> Any:
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.MENU
    assert step in result["menu_options"]
    return await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": step}
    )


async def test_options_menu(hass: HomeAssistant, printer: MockPrinter) -> None:
    entry = await setup_entry(hass, lan_entry())
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["menu_options"] == ["drying", "local", "card_config", "debug"]

    printer.connect_payloads = [payloads.info(), payloads.peripherals(ace_fitted=0)]
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    # G21: no drying presets for a printer known to have no ACE.
    assert result["menu_options"] == ["local", "card_config", "debug"]

    cloud = cloud_entry(lan=False)
    cloud.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(cloud.entry_id)
    assert result["menu_options"] == ["mqtt", "drying", "local", "card_config", "debug"]


async def test_options_drying(hass: HomeAssistant, printer: MockPrinter) -> None:
    entry = await setup_entry(
        hass,
        lan_entry(
            options={
                "lan_mode_enabled": True,
                "lan_host": payloads.HOST,
                "drying_preset_duration_4": 10,
                "card_config": {"round": False},
            }
        ),
    )
    result = await _options(hass, entry, "drying")
    assert result["step_id"] == "drying"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"drying_preset_duration_1": 240, "drying_preset_temperature_1": 55},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {
        "lan_mode_enabled": True,
        "lan_host": payloads.HOST,
        "card_config": {"round": False},
        "drying_preset_duration_1": 240,
        "drying_preset_temperature_1": 55,
    }
    await hass.async_block_till_done(wait_background_tasks=True)


async def test_options_mqtt(hass: HomeAssistant, printer: MockPrinter) -> None:
    entry = cloud_entry(lan=False)
    entry.add_to_hass(hass)
    result = await _options(hass, entry, "mqtt")
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"mqtt_connect_mode": "4"}
    )
    assert entry.options["mqtt_connect_mode"] == 4
    assert entry.options["drying_preset_duration_1"] == 240
    await hass.async_block_till_done(wait_background_tasks=True)


async def test_options_local(hass: HomeAssistant, printer: MockPrinter) -> None:
    entry = await setup_entry(hass, lan_entry())
    result = await _options(hass, entry, "local")
    printer.handshake_error = PrinterUnreachableError("x")
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"lan_mode_enabled": True, "lan_host": NEW_HOST}
    )
    assert result["errors"] == {"base": "lan_unreachable"}
    printer.handshake_error = None
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"lan_mode_enabled": True, "lan_host": NEW_HOST}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options["lan_host"] == NEW_HOST
    await hass.async_block_till_done(wait_background_tasks=True)

    result = await _options(hass, entry, "local")
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"lan_mode_enabled": False, "lan_host": NEW_HOST}
    )
    assert entry.options["lan_mode_enabled"] is False
    await hass.async_block_till_done(wait_background_tasks=True)


async def test_options_card_config(hass: HomeAssistant, printer: MockPrinter) -> None:
    entry = await setup_entry(hass, lan_entry())
    result = await _options(hass, entry, "card_config")
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"card_config": ["not", "a", "mapping"]}
    )
    assert result["errors"] == {"card_config": "invalid_card_config"}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"card_config": {"vertical": False, "scaleFactor": 1, "bogus": 1}},
    )
    assert entry.options["card_config"] == {"vertical": False, "scaleFactor": 1}
    await hass.async_block_till_done(wait_background_tasks=True)


async def test_options_debug(hass: HomeAssistant, printer: MockPrinter) -> None:
    options = {"lan_mode_enabled": True, "lan_host": payloads.HOST, "debug": True}
    entry = await setup_entry(hass, lan_entry(options=options))
    result = await _options(hass, entry, "debug")
    defaults = {key.schema: key.default() for key in result["data_schema"].schema}
    assert defaults == {"debug_mqtt_msg": True, "debug_api_calls": True}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"debug_mqtt_msg": True, "debug_api_calls": False}
    )
    assert entry.options["debug_mqtt_msg"] is True
    assert entry.options["debug_api_calls"] is False
    await hass.async_block_till_done(wait_background_tasks=True)


def test_sanitize_card_config() -> None:
    """DECISIONS frontend 3: false, 0, empty and whole numbers are kept."""
    raw = {
        "vertical": False,
        "round": "yes",
        "scaleFactor": 1,
        "monitoredStats": [],
        "slotColors": "red",
        "sections": ["filament", 3],
        "mediaView": "none",
        "noCamera": True,
        "showMoveButtons": False,
        "temperatureUnit": "F",
        "unknown": True,
        "alwaysShow": 0,
    }
    assert sanitize_card_config(raw) == {
        "vertical": False,
        "scaleFactor": 1,
        "monitoredStats": [],
        "slotColors": "red",
        "mediaView": "none",
        "noCamera": True,
        "showMoveButtons": False,
        "temperatureUnit": "F",
    }
    assert sanitize_card_config({"scaleFactor": True}) == {}
