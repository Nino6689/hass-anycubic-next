// Service calls (FRONTEND.md §3.6). Integration actions always carry both
// `config_entry` and `device_id`; entity calls only ever target a resolved id.

import type { HomeAssistant } from "../ha/types";
import { DOMAIN, type Printer } from "./entities";

export const SPOOL_MATERIALS = ["PLA", "PETG", "ABS", "PACF", "PC", "ASA", "HIPS", "PA", "PLA_SE"] as const;

export function printerSelector(p: Printer): { config_entry?: string; device_id?: string } {
  return { config_entry: p.configEntry, device_id: p.deviceId };
}

export async function callAction(
  hass: HomeAssistant,
  p: Printer,
  service: string,
  data: Record<string, unknown> = {},
): Promise<void> {
  if (!p.deviceId || !p.configEntry) throw new Error("No printer selected");
  await hass.callService(DOMAIN, service, { ...printerSelector(p), ...data });
}

/** Press a resolved button; does nothing when the button is missing. */
export async function pressButton(hass: HomeAssistant, p: Printer, key: string): Promise<void> {
  const id = p.id(key, "button");
  if (!id) return;
  await hass.callService("button", "press", { entity_id: id });
}

export async function toggleEntity(hass: HomeAssistant, entityId: string | undefined): Promise<void> {
  if (!entityId) return;
  await hass.callService("homeassistant", "toggle", { entity_id: entityId });
}

export async function toggleSwitch(hass: HomeAssistant, p: Printer, key: string): Promise<void> {
  const id = p.id(key, "switch");
  if (!id) return;
  await hass.callService("switch", "toggle", { entity_id: id });
}

export async function selectOption(hass: HomeAssistant, p: Printer, key: string, option: string): Promise<void> {
  const id = p.id(key, "select");
  if (!id) return;
  await hass.callService("select", "select_option", { entity_id: id, option });
}

export function setSlotService(material: string): string {
  return `multi_color_box_set_slot_${material.toLowerCase()}`;
}
