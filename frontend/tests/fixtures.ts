import type { DeviceRegistryEntry, EntityRegistryDisplayEntry, HassEntity } from "../src/ha/types";

export interface FakeHass {
  states: Record<string, HassEntity>;
  entities: Record<string, EntityRegistryDisplayEntry>;
  devices: Record<string, DeviceRegistryEntry>;
}

export function device(id: string, extra: Partial<DeviceRegistryEntry> = {}): DeviceRegistryEntry {
  return {
    id,
    name: `Device ${id}`,
    manufacturer: "Anycubic",
    model: "Kobra S1",
    via_device_id: null,
    primary_config_entry: `entry-${id}`,
    config_entries: [`entry-${id}`],
    ...extra,
  };
}

export function hassWith(
  devices: DeviceRegistryEntry[],
  entities: { id: string; device: string; key?: string | null; state?: string; attrs?: Record<string, unknown>; platform?: string }[],
): FakeHass {
  const hass: FakeHass = { states: {}, entities: {}, devices: {} };
  for (const d of devices) hass.devices[d.id] = d;
  for (const e of entities) {
    hass.entities[e.id] = {
      entity_id: e.id,
      device_id: e.device,
      platform: e.platform ?? "anycubic_cloud",
      translation_key: e.key === undefined ? null : e.key,
    };
    if (e.state !== undefined) {
      hass.states[e.id] = {
        entity_id: e.id,
        state: e.state,
        attributes: e.attrs ?? {},
        last_changed: "",
        last_updated: "",
      };
    }
  }
  return hass;
}
