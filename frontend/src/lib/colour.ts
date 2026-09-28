// Filament colours for the artwork and ACE strip (FRONTEND.md §4.5).

export type RGB = [number, number, number];

/** Representative swatches for colour words printers and users use. */
const NAMED: Record<string, string> = {
  black: "#1b1b1b",
  white: "#f4f4f4",
  grey: "#8a8a8a",
  gray: "#8a8a8a",
  silver: "#c0c4c8",
  red: "#d32f2f",
  orange: "#f57c00",
  yellow: "#fbc02d",
  green: "#388e3c",
  blue: "#1976d2",
  purple: "#7b1fa2",
  pink: "#ec6fa4",
  brown: "#795548",
  clear: "#dfe9ee",
  natural: "#e8dcc0",
  transparent: "#dfe9ee",
};

function hex2(n: number): string {
  return Math.round(Math.min(255, Math.max(0, n))).toString(16).padStart(2, "0");
}

export function rgbToHex([r, g, b]: RGB): string {
  return `#${hex2(r)}${hex2(g)}${hex2(b)}`;
}

export function hexToRgb(hex: string): RGB | undefined {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex.trim());
  if (!m) return undefined;
  const v = parseInt(m[1], 16);
  return [(v >> 16) & 255, (v >> 8) & 255, v & 255];
}

/**
 * Normalise a colour string to something CSS accepts, or undefined.
 * Accepts #RRGGBB, #RRGGBBAA, #RGB, bare hex, rgb()/rgba()/hsl()/hsla(), and
 * the common colour words above.
 */
export function normaliseColour(input: unknown): string | undefined {
  if (typeof input !== "string") return undefined;
  const text = input.trim().toLowerCase();
  if (text === "") return undefined;
  if (NAMED[text]) return NAMED[text];
  const hex = /^#?([0-9a-f]{3}|[0-9a-f]{6}|[0-9a-f]{8})$/.exec(text);
  if (hex) {
    const h = hex[1];
    if (h.length === 3) return `#${h[0]}${h[0]}${h[1]}${h[1]}${h[2]}${h[2]}`;
    return `#${h.slice(0, 6)}`;
  }
  if (/^(rgb|rgba|hsl|hsla)\(\s*[-\d.%\s,/deg]+\)$/.test(text)) return text;
  return undefined;
}

function rgbArray(value: unknown): RGB | undefined {
  if (!Array.isArray(value) || value.length < 3) return undefined;
  const nums = value.slice(0, 3).map(Number);
  if (nums.some((n) => !Number.isFinite(n))) return undefined;
  return nums as RGB;
}

export interface SpoolInfo {
  slot?: number;
  material_type?: string;
  color?: unknown;
  color_hex?: unknown;
  spool_loaded?: boolean;
  consumables_percent?: number | null;
}

/** A slot's colour: `color_hex`, else the `[r,g,b]` array; undefined when neither parses. */
export function spoolColour(spool: SpoolInfo | undefined): string | undefined {
  if (!spool) return undefined;
  const fromHex = normaliseColour(spool.color_hex);
  if (fromHex) return fromHex;
  const rgb = rgbArray(spool.color);
  return rgb ? rgbToHex(rgb) : undefined;
}

/** A slot's colour as an RGB triple, for the spool editor. */
export function spoolRgb(spool: SpoolInfo | undefined): RGB | undefined {
  const rgb = rgbArray(spool?.color);
  if (rgb) return rgb;
  const hex = normaliseColour(spool?.color_hex);
  return hex?.startsWith("#") ? hexToRgb(hex) : undefined;
}

/** Linear blend between two hex colours, t in 0–1. */
export function mixHex(a: string, b: string, t: number): string {
  const ca = hexToRgb(a) ?? [0, 0, 0];
  const cb = hexToRgb(b) ?? [0, 0, 0];
  const k = Math.min(1, Math.max(0, t));
  return rgbToHex([ca[0] + (cb[0] - ca[0]) * k, ca[1] + (cb[1] - ca[1]) * k, ca[2] + (cb[2] - ca[2]) * k]);
}

/** Black or white, whichever reads better against a hex colour. */
export function contrastOn(hex: string | undefined): string {
  const rgb = hex ? hexToRgb(hex) : undefined;
  if (!rgb) return "#ffffff";
  const lum = (0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]) / 255;
  return lum > 0.55 ? "#1b1b1b" : "#ffffff";
}

/** Heater glow: 0 when cold, 1 at target; (current − 20) / (target − 20). */
export function heatLevel(current: number | undefined, target: number | undefined): number {
  if (current === undefined || target === undefined || !(target > 20)) return 0;
  return Math.min(1, Math.max(0, (current - 20) / (target - 20)));
}
