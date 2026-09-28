// Value formatting (FRONTEND.md §4.1). Every formatter returns an em dash for
// "no value" and never NaN, an empty string or an exception.

import type { TemperatureUnit } from "./config";

export const NO_VALUE = "—";

/** Convert a temperature from the entity's unit to the display unit. */
export function convertTemperature(value: number, from: string | undefined, to: TemperatureUnit): number {
  const src = from && /f/i.test(from) ? "F" : "C";
  if (src === to) return value;
  return to === "F" ? (value * 9) / 5 + 32 : ((value - 32) * 5) / 9;
}

export function formatTemperature(
  value: number | undefined,
  fromUnit: string | undefined,
  to: TemperatureUnit,
  round: boolean,
): string {
  if (value === undefined || !Number.isFinite(value)) return NO_VALUE;
  const v = convertTemperature(value, fromUnit, to);
  return `${round ? Math.round(v) : v.toFixed(2)}°${to}`;
}

/**
 * Parse a time entity's state into seconds: `N days, HH:MM:SS`, `HH:MM:SS`,
 * or a plain number meaning minutes.
 */
export function parseDurationSeconds(state: string | undefined | null): number | undefined {
  if (state === undefined || state === null) return undefined;
  const text = String(state).trim();
  if (text === "") return undefined;
  const plain = Number(text);
  if (Number.isFinite(plain)) return Math.max(0, plain * 60);
  const m = /^(?:(\d+)\s+days?,\s*)?(\d+):(\d{1,2}):(\d{1,2}(?:\.\d+)?)$/.exec(text);
  if (!m) return undefined;
  const [, d, h, min, s] = m;
  return Number(d ?? 0) * 86400 + Number(h) * 3600 + Number(min) * 60 + Math.floor(Number(s));
}

/**
 * Two most significant units of d/h/m/s. With `round`, seconds round up to the
 * next minute and are never shown. A zero second unit is left out.
 */
export function formatDuration(seconds: number | undefined, round: boolean): string {
  if (seconds === undefined || !Number.isFinite(seconds)) return NO_VALUE;
  let total = Math.max(0, seconds);
  total = round ? Math.ceil(total / 60) * 60 : Math.floor(total);
  const d = Math.floor(total / 86400);
  const h = Math.floor((total % 86400) / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const pair = (a: number, ua: string, b: number, ub: string) => (b > 0 ? `${a}${ua} ${b}${ub}` : `${a}${ua}`);
  if (d > 0) return pair(d, "d", h, "h");
  if (h > 0) return pair(h, "h", m, "m");
  if (round) return `${m}m`;
  if (m > 0) return pair(m, "m", s, "s");
  return `${s}s`;
}

/** A local clock time: `HH:mm` or `h:mm am/pm`, with seconds when not rounding. */
export function formatClock(date: Date | undefined, use24: boolean, round: boolean): string {
  if (!date || Number.isNaN(date.getTime())) return NO_VALUE;
  const pad = (n: number) => String(n).padStart(2, "0");
  const secs = round ? "" : `:${pad(date.getSeconds())}`;
  const mins = pad(date.getMinutes());
  if (use24) return `${pad(date.getHours())}:${mins}${secs}`;
  const h = date.getHours();
  const h12 = h % 12 === 0 ? 12 : h % 12;
  return `${h12}:${mins}${secs} ${h < 12 ? "am" : "pm"}`;
}

/**
 * The job's end: the `job_eta` timestamp when it has a value, otherwise
 * now + remaining seconds (DECISIONS, frontend 10).
 */
export function computeEta(
  etaState: string | undefined,
  remainingSeconds: number | undefined,
  now: number = Date.now(),
): Date | undefined {
  if (etaState) {
    const t = Date.parse(etaState);
    if (Number.isFinite(t)) return new Date(t);
  }
  if (remainingSeconds === undefined || !Number.isFinite(remainingSeconds)) return undefined;
  return new Date(now + Math.max(0, remainingSeconds) * 1000);
}

export function formatMoney(value: number | undefined, language: string, currency: string | undefined): string {
  if (value === undefined || !Number.isFinite(value)) return NO_VALUE;
  if (!currency) return value.toFixed(2);
  try {
    return new Intl.NumberFormat(language || "en", { style: "currency", currency }).format(value);
  } catch {
    return `${value.toFixed(2)} ${currency}`;
  }
}

export function formatGrams(value: number | undefined): string {
  if (value === undefined || !Number.isFinite(value)) return NO_VALUE;
  return `${Math.round(value)} g`;
}

export function formatPercent(value: number | undefined, decimals: number): string {
  if (value === undefined || !Number.isFinite(value)) return NO_VALUE;
  return `${value.toFixed(decimals)}%`;
}

export function clampPercent(value: number): number {
  return Math.min(100, Math.max(0, value));
}

/** `printing` → `Printing`, `not_ready` → `Not Ready`. */
export function titleCase(text: string | undefined): string {
  if (!text) return NO_VALUE;
  return text
    .replace(/_/g, " ")
    .split(" ")
    .filter((w) => w !== "")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
    .join(" ");
}

/** Share of the drying time still to go, 0–100 (DECISIONS, frontend 9). */
export function dryingRemainingPercent(remaining: number | undefined, total: number | undefined): number | undefined {
  if (remaining === undefined || total === undefined || !(total > 0)) return undefined;
  return clampPercent((remaining / total) * 100);
}
