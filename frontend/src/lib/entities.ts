// Entity resolution (FRONTEND.md §3): printers, their entity sets, and lookups by
// the registry `translation_key`. Pure functions of the `hass` object.

import type { DeviceRegistryEntry, HassEntity, HomeAssistant } from "../ha/types";

export const DOMAIN = "anycubic_cloud";
export const MANUFACTURER = "Anycubic";

type HassLike = Pick<HomeAssistant, "states" | "entities" | "devices">;

/** Devices offered as printers (§3.1), in registry order. */
export function findPrinters(hass: HassLike | undefined): DeviceRegistryEntry[] {
  if (!hass?.devices || !hass.entities) return [];
  const withOurEntities = new Set<string>();
  for (const entry of Object.values(hass.entities)) {
    if (entry.platform === DOMAIN && entry.device_id) withOurEntities.add(entry.device_id);
  }
  return Object.values(hass.devices).filter(
    (d) => d.manufacturer === MANUFACTURER && !d.via_device_id && withOurEntities.has(d.id),
  );
}

export function deviceName(device: DeviceRegistryEntry | undefined): string | undefined {
  return device?.name_by_user || device?.name || undefined;
}

function objectId(entityId: string): string {
  const dot = entityId.indexOf(".");
  return dot < 0 ? entityId : entityId.slice(dot + 1);
}

function domainOf(entityId: string): string {
  const dot = entityId.indexOf(".");
  return dot < 0 ? "" : entityId.slice(0, dot);
}

/** Longest common prefix of the object ids, cut back to its last underscore (§3.3). */
export function commonPrefix(entityIds: string[]): string {
  if (entityIds.length === 0) return "";
  const ids = entityIds.map(objectId);
  let prefix = ids[0];
  for (const id of ids.slice(1)) {
    let i = 0;
    while (i < prefix.length && i < id.length && prefix[i] === id[i]) i++;
    prefix = prefix.slice(0, i);
    if (prefix === "") return "";
  }
  const cut = prefix.lastIndexOf("_");
  return cut < 0 ? "" : prefix.slice(0, cut + 1);
}

export interface EntitySet {
  /** The printer device. */
  device?: DeviceRegistryEntry;
  /** The printer plus its child devices (ACE units). */
  deviceIds: string[];
  /** Entity ids of the set, in registry order. */
  entityIds: string[];
  prefix: string;
}

/** The printer's entity set (§3.2). Unknown device → an empty set. */
export function entitySet(hass: HassLike | undefined, deviceId: string | undefined): EntitySet {
  const device = deviceId ? hass?.devices?.[deviceId] : undefined;
  if (!hass || !device) return { device, deviceIds: [], entityIds: [], prefix: "" };
  const deviceIds = [
    device.id,
    ...Object.values(hass.devices)
      .filter((d) => d.via_device_id === device.id)
      .map((d) => d.id),
  ];
  const members = new Set(deviceIds);
  const entityIds = Object.values(hass.entities ?? {})
    .filter((e) => e.device_id && members.has(e.device_id))
    .map((e) => e.entity_id);
  return { device, deviceIds, entityIds, prefix: commonPrefix(entityIds) };
}

/**
 * Find the entity with registry translation key `key` in `domain` (§3.3).
 * Entities that are disabled (absent from the display list) or have no state
 * object count as missing. The English-suffix match is a last resort for
 * entities that carry no translation key at all.
 */
export function resolveEntityId(
  hass: HassLike | undefined,
  set: EntitySet,
  key: string,
  domain: string,
): string | undefined {
  if (!hass) return undefined;
  const live = set.entityIds.filter((id) => domainOf(id) === domain && hass.states?.[id] !== undefined);
  const pick = (matches: string[]): string | undefined => {
    if (matches.length <= 1) return matches[0];
    const preferred = set.prefix ? matches.find((id) => objectId(id).startsWith(set.prefix)) : undefined;
    return preferred ?? matches[0];
  };
  const registry = hass.entities ?? {};
  const byKey = live.filter((id) => registry[id]?.translation_key === key);
  if (byKey.length) return pick(byKey);
  const bySuffix = live.filter((id) => {
    const tk = registry[id]?.translation_key;
    const oid = objectId(id);
    return (tk === undefined || tk === null) && (oid === key || oid.endsWith(`_${key}`));
  });
  if (bySuffix.length > 1 && set.prefix) {
    const exact = bySuffix.find((id) => objectId(id) === `${set.prefix}${key}`);
    if (exact) return exact;
  }
  return pick(bySuffix);
}

/** A state that carries no reading. */
export function isNoValue(state: string | undefined | null): boolean {
  return state === undefined || state === null || state === "" || state === "unknown" || state === "unavailable";
}

export interface CameraChoice {
  entityId: string;
  isCloud: boolean;
  available: boolean;
}

/** Choose the hero's camera (§3.7). */
export function chooseCamera(
  hass: HassLike | undefined,
  set: EntitySet,
  override?: string,
): CameraChoice | undefined {
  if (!hass) return undefined;
  const candidates: CameraChoice[] = set.entityIds
    .filter((id) => domainOf(id) === "camera")
    .map((id) => {
      const tk = hass.entities?.[id]?.translation_key;
      const isCloud = tk ? tk === "cloud_camera" : objectId(id).endsWith("cloud_camera");
      const state = hass.states?.[id]?.state;
      return { entityId: id, isCloud, available: state !== undefined && state !== "unavailable" };
    });
  candidates.sort((a, b) => Number(a.isCloud) - Number(b.isCloud));
  if (override) {
    const known = candidates.find((c) => c.entityId === override);
    return known ?? { entityId: override, isCloud: objectId(override).endsWith("cloud_camera"), available: true };
  }
  return candidates.find((c) => c.available) ?? candidates[0];
}

/**
 * A printer as the UI sees it: its device, entity set and typed lookups.
 * Build a new one per `hass` update; construction is cheap.
 */
export class Printer {
  readonly set: EntitySet;
  private readonly cache = new Map<string, string | undefined>();

  constructor(
    readonly hass: HassLike | undefined,
    readonly deviceId: string | undefined,
  ) {
    this.set = entitySet(hass, deviceId);
  }

  get device(): DeviceRegistryEntry | undefined {
    return this.set.device;
  }

  get exists(): boolean {
    return this.set.device !== undefined;
  }

  get name(): string | undefined {
    return deviceName(this.set.device);
  }

  /** The printer device's primary config entry id. */
  get configEntry(): string | undefined {
    const d = this.set.device;
    return d?.primary_config_entry ?? d?.config_entries?.[0] ?? undefined;
  }

  id(key: string, domain = "sensor"): string | undefined {
    const k = `${domain}|${key}`;
    if (!this.cache.has(k)) this.cache.set(k, resolveEntityId(this.hass, this.set, key, domain));
    return this.cache.get(k);
  }

  entity(key: string, domain = "sensor"): HassEntity | undefined {
    const id = this.id(key, domain);
    return id ? this.hass?.states?.[id] : undefined;
  }

  /** The state, or undefined when missing, unknown or unavailable. */
  value(key: string, domain = "sensor"): string | undefined {
    const s = this.entity(key, domain)?.state;
    return isNoValue(s) ? undefined : s;
  }

  num(key: string, domain = "sensor"): number | undefined {
    const v = this.value(key, domain);
    if (v === undefined) return undefined;
    const n = Number(v);
    return Number.isFinite(n) ? n : undefined;
  }

  /** true / false for on / off, undefined without a reading. */
  isOn(key: string, domain = "binary_sensor"): boolean | undefined {
    const v = this.value(key, domain);
    return v === "on" ? true : v === "off" ? false : undefined;
  }

  attr<T = unknown>(key: string, attribute: string, domain = "sensor"): T | undefined {
    return this.entity(key, domain)?.attributes?.[attribute] as T | undefined;
  }

  /** An entity that exists and is not unavailable (usable for a press/toggle). */
  usable(key: string, domain: string): boolean {
    const s = this.entity(key, domain)?.state;
    return s !== undefined && s !== "unavailable";
  }

  get materialType(): string | undefined {
    return this.attr<string>("current_status", "material_type");
  }

  get isResin(): boolean {
    return this.materialType === "Resin";
  }

  get isFilament(): boolean {
    return this.materialType === "Filament";
  }

  aceActive(unit: 0 | 1): boolean {
    return this.value(unit === 0 ? "ace_spools" : "secondary_ace_spools") === "active";
  }

  camera(override?: string): CameraChoice | undefined {
    return chooseCamera(this.hass, this.set, override);
  }
}
