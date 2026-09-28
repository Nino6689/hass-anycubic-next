// The small part of Home Assistant's frontend `hass` object this project uses.
// Written against the Home Assistant frontend developer documentation; only the
// fields read here are declared.

export interface HassEntityAttributes {
  friendly_name?: string;
  unit_of_measurement?: string;
  entity_picture?: string;
  access_token?: string;
  options?: string[];
  [key: string]: unknown;
}

export interface HassEntity {
  entity_id: string;
  state: string;
  attributes: HassEntityAttributes;
  last_changed: string;
  last_updated: string;
}

/** One row of the entity registry display list (`hass.entities`). */
export interface EntityRegistryDisplayEntry {
  entity_id: string;
  device_id?: string | null;
  platform?: string;
  translation_key?: string | null;
  name?: string | null;
  hidden?: boolean;
}

/** One row of the device registry (`hass.devices`). */
export interface DeviceRegistryEntry {
  id: string;
  name: string | null;
  name_by_user?: string | null;
  manufacturer: string | null;
  model: string | null;
  sw_version?: string | null;
  serial_number?: string | null;
  via_device_id: string | null;
  connections?: [string, string][];
  config_entries?: string[];
  primary_config_entry?: string | null;
}

export interface HomeAssistant {
  states: Record<string, HassEntity>;
  entities: Record<string, EntityRegistryDisplayEntry>;
  devices: Record<string, DeviceRegistryEntry>;
  language: string;
  locale?: { language: string };
  config: { currency?: string; unit_system?: { temperature?: string } };
  themes?: { darkMode?: boolean };
  callService(
    domain: string,
    service: string,
    data?: Record<string, unknown>,
    target?: Record<string, unknown>,
  ): Promise<unknown>;
  fetchWithAuth?(path: string, init?: RequestInit): Promise<Response>;
}

export interface PanelInfo<C = Record<string, unknown>> {
  component_name?: string;
  url_path?: string;
  title?: string | null;
  config?: C | null;
}

export interface Route {
  prefix: string;
  path: string;
}

export interface LovelaceCardEditor extends HTMLElement {
  hass?: HomeAssistant;
  setConfig(config: Record<string, unknown>): void;
}

declare global {
  interface Window {
    customCards?: { type: string; name: string; description: string; preview?: boolean }[];
    loadCardHelpers?: () => Promise<{ importMoreInfoControl?: (type: string) => void }>;
  }
}
