// Card configuration: the stored keys (FRONTEND.md §2), their defaults, and the
// panel's `card_config` option. Parsing never mutates its input and never throws.

export const STATS_GENERAL = ["Status", "Online", "Availability", "Project", "Layer"] as const;
export const STATS_TIME = ["ETA", "Elapsed", "Remaining"] as const;
export const STATS_FDM = [
  "Hotend",
  "Bed",
  "T Hotend",
  "T Bed",
  "Dry Status",
  "Dry Time",
  "Speed Mode",
  "Fan Speed",
] as const;
export const STATS_ACE = ["Dry Status", "Dry Time"] as const;
export const STATS_RESIN = [
  "On Time",
  "Off Time",
  "Bottom Time",
  "Model Height",
  "Bottom Layers",
  "Z Up Height",
  "Z Up Speed",
  "Z Down Speed",
] as const;

export const ALL_STATS: readonly string[] = [
  ...new Set<string>([...STATS_GENERAL, ...STATS_TIME, ...STATS_FDM, ...STATS_RESIN]),
];

export const MEDIA_VIEWS = ["auto", "camera", "preview", "printer", "printer_model", "none"] as const;
export type MediaView = (typeof MEDIA_VIEWS)[number];

export const PRINTER_ARTS = ["auto", "kobra_s1", "kobra_s1_combo", "kobra_3", "resin", "fdm"] as const;
export type PrinterArt = (typeof PRINTER_ARTS)[number];

export const SECTIONS = ["filament", "insights"] as const;
export type Section = (typeof SECTIONS)[number];

export type TemperatureUnit = "C" | "F";

/** Every key a stored card config may carry, as users' dashboards hold them. */
export const CARD_KEYS = [
  "printer_id",
  "vertical",
  "round",
  "use_24hr",
  "temperatureUnit",
  "lightEntityId",
  "powerEntityId",
  "cameraEntityId",
  "monitoredStats",
  "scaleFactor",
  "slotColors",
  "showSettingsButton",
  "alwaysShow",
  "mediaView",
  "printerArt",
  "showMoveButtons",
  "showControls",
  "sections",
  "noCamera",
] as const;
export type CardKey = (typeof CARD_KEYS)[number];

export interface ResolvedConfig {
  printer_id?: string;
  vertical: boolean;
  round: boolean;
  use_24hr: boolean;
  temperatureUnit: TemperatureUnit;
  lightEntityId?: string;
  powerEntityId?: string;
  cameraEntityId?: string;
  /** `undefined` only for the panel, which then picks per printer (§4.15). */
  monitoredStats?: string[];
  scaleFactor: number;
  slotColors: string[];
  showSettingsButton: boolean;
  alwaysShow: boolean;
  mediaView: MediaView;
  printerArt: PrinterArt;
  showMoveButtons: boolean;
  showControls: boolean;
  sections: Section[];
  noCamera: boolean;
}

export type Defaults = Omit<ResolvedConfig, "printer_id" | "lightEntityId" | "powerEntityId" | "cameraEntityId">;

export const DEFAULT_STATS = ["Status", "ETA", "Elapsed", "Remaining"];

export const CARD_DEFAULTS: Readonly<Defaults> = Object.freeze({
  vertical: false,
  round: true,
  use_24hr: true,
  temperatureUnit: "C",
  monitoredStats: DEFAULT_STATS,
  scaleFactor: 1,
  slotColors: [],
  showSettingsButton: false,
  alwaysShow: false,
  mediaView: "auto",
  printerArt: "auto",
  showMoveButtons: false,
  showControls: true,
  sections: ["filament"],
  noCamera: false,
} satisfies Defaults);

/** The panel's hero card defaults (§2.6); `monitoredStats` depends on the printer. */
export const PANEL_DEFAULTS: Readonly<Defaults> = Object.freeze({
  ...CARD_DEFAULTS,
  showSettingsButton: true,
  alwaysShow: true,
  showMoveButtons: true,
  monitoredStats: undefined,
});

type Raw = Record<string, unknown> | null | undefined;

function asBool(value: unknown, fallback: boolean): boolean {
  if (typeof value === "boolean") return value;
  if (typeof value === "string") {
    const v = value.trim().toLowerCase();
    if (v === "true") return true;
    if (v === "false") return false;
  }
  return fallback;
}

function asString(value: unknown): string | undefined {
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  if (typeof value !== "string") return undefined;
  const v = value.trim();
  return v === "" ? undefined : v;
}

function asStringList(value: unknown): string[] | undefined {
  if (typeof value === "string") return value.trim() === "" ? [] : [value.trim()];
  if (!Array.isArray(value)) return undefined;
  return value.filter((v): v is string => typeof v === "string").map((v) => v.trim()).filter((v) => v !== "");
}

function asEnum<T extends string>(value: unknown, allowed: readonly T[], fallback: T): T {
  if (typeof value !== "string") return fallback;
  const v = value.trim();
  return (allowed as readonly string[]).includes(v) ? (v as T) : fallback;
}

function asScale(value: unknown, fallback: number): number {
  const n = typeof value === "number" ? value : typeof value === "string" ? Number(value) : NaN;
  if (!Number.isFinite(n) || n <= 0) return value === undefined ? fallback : 1;
  return n;
}

function asUnit(value: unknown, fallback: TemperatureUnit): TemperatureUnit {
  if (typeof value !== "string") return fallback;
  const v = value.trim().toUpperCase().replace("°", "");
  return v === "F" ? "F" : v === "C" ? "C" : fallback;
}

/** Whether the legacy `move` section switches the move pad on (§2.4). */
export function legacyMoveRequested(raw: Raw): boolean {
  const sections = asStringList(raw?.sections);
  return sections !== undefined && sections.includes("move");
}

/**
 * Apply defaults to a stored card config. `false`, `0` and empty lists are kept
 * as given; unknown keys and unknown list values are ignored.
 */
export function resolveConfig(raw: Raw, defaults: Readonly<Defaults> = CARD_DEFAULTS): ResolvedConfig {
  const c = raw ?? {};
  const stats = asStringList(c.monitoredStats);
  const sections = asStringList(c.sections);
  const showMove =
    typeof c.showMoveButtons === "boolean" || typeof c.showMoveButtons === "string"
      ? asBool(c.showMoveButtons, defaults.showMoveButtons)
      : legacyMoveRequested(c) || defaults.showMoveButtons;
  return {
    printer_id: asString(c.printer_id),
    vertical: asBool(c.vertical, defaults.vertical),
    round: asBool(c.round, defaults.round),
    use_24hr: asBool(c.use_24hr, defaults.use_24hr),
    temperatureUnit: asUnit(c.temperatureUnit, defaults.temperatureUnit),
    lightEntityId: asString(c.lightEntityId),
    powerEntityId: asString(c.powerEntityId),
    cameraEntityId: asString(c.cameraEntityId),
    monitoredStats:
      stats !== undefined
        ? stats.filter((s) => ALL_STATS.includes(s))
        : defaults.monitoredStats
          ? [...defaults.monitoredStats]
          : undefined,
    scaleFactor: asScale(c.scaleFactor, defaults.scaleFactor),
    slotColors: asStringList(c.slotColors) ?? [...defaults.slotColors],
    showSettingsButton: asBool(c.showSettingsButton, defaults.showSettingsButton),
    alwaysShow: asBool(c.alwaysShow, defaults.alwaysShow),
    mediaView: asEnum(c.mediaView, MEDIA_VIEWS, defaults.mediaView),
    printerArt: asEnum(c.printerArt, PRINTER_ARTS, defaults.printerArt),
    showMoveButtons: showMove,
    showControls: asBool(c.showControls, defaults.showControls),
    sections:
      sections !== undefined
        ? SECTIONS.filter((s) => sections.includes(s))
        : [...defaults.sections],
    noCamera: asBool(c.noCamera, defaults.noCamera),
  };
}

/**
 * Prepare a config for saving from the visual editor: scalar keys equal to the
 * card default are removed; lists are always kept; other keys pass through.
 */
export function stripDefaults(config: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  const defaults = CARD_DEFAULTS as unknown as Record<string, unknown>;
  for (const [key, value] of Object.entries(config)) {
    if (value === undefined || value === null || value === "") continue;
    // An explicit `showMoveButtons: false` must survive while a legacy `move`
    // section would otherwise switch the pad back on.
    if (key === "showMoveButtons" && legacyMoveRequested(config)) {
      out[key] = value;
      continue;
    }
    if (!Array.isArray(value) && key in defaults && defaults[key] === value) continue;
    out[key] = value;
  }
  return out;
}

/** Card size in masonry rows (§1.3). */
export function cardSize(config: ResolvedConfig): number {
  return config.mediaView === "none" ? 4 : 8;
}
