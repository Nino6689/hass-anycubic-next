import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  computeEta,
  convertTemperature,
  dryingRemainingPercent,
  formatClock,
  formatEta,
  formatDuration,
  formatGrams,
  formatMoney,
  formatPercent,
  formatTemperature,
  parseDurationSeconds,
  titleCase,
} from "../src/lib/format";

describe("temperatures", () => {
  it("converts and rounds", () => {
    expect(formatTemperature(215.4, "°C", "C", true)).toBe("215°C");
    expect(formatTemperature(215.456, "°C", "C", false)).toBe("215.46°C");
    expect(formatTemperature(100, "°C", "F", true)).toBe("212°F");
    expect(formatTemperature(212, "°F", "C", true)).toBe("100°C");
    expect(formatTemperature(20, undefined, "C", true)).toBe("20°C");
    expect(formatTemperature(undefined, "°C", "C", true)).toBe("—");
    expect(convertTemperature(0, "°C", "F")).toBe(32);
  });
});

describe("durations", () => {
  it("parses the three accepted forms", () => {
    expect(parseDurationSeconds("90")).toBe(5400);
    expect(parseDurationSeconds("1.5")).toBe(90);
    expect(parseDurationSeconds("01:02:03")).toBe(3723);
    expect(parseDurationSeconds("2 days, 3:04:05")).toBe(2 * 86400 + 3 * 3600 + 4 * 60 + 5);
    expect(parseDurationSeconds("1 day, 0:00:00")).toBe(86400);
    expect(parseDurationSeconds("soon")).toBeUndefined();
    expect(parseDurationSeconds("")).toBeUndefined();
    expect(parseDurationSeconds(undefined)).toBeUndefined();
  });

  it("formats with rounding", () => {
    expect(formatDuration(0, true)).toBe("0m");
    expect(formatDuration(1, true)).toBe("1m");
    expect(formatDuration(192, true)).toBe("4m");
    expect(formatDuration(5 * 3600 + 3 * 60, true)).toBe("5h 3m");
    expect(formatDuration(5 * 3600 + 2 * 60 + 1, true)).toBe("5h 3m");
    expect(formatDuration(86400 + 5 * 3600 + 30 * 60, true)).toBe("1d 5h");
    expect(formatDuration(2 * 3600, true)).toBe("2h");
  });

  it("formats without rounding", () => {
    expect(formatDuration(0, false)).toBe("0s");
    expect(formatDuration(192, false)).toBe("3m 12s");
    expect(formatDuration(5 * 3600 + 3 * 60 + 9, false)).toBe("5h 3m");
    expect(formatDuration(86400 + 5 * 3600 + 7, false)).toBe("1d 5h");
    expect(formatDuration(45.7, false)).toBe("45s");
    expect(formatDuration(-5, false)).toBe("0s");
    expect(formatDuration(undefined, false)).toBe("—");
    expect(formatDuration(NaN, true)).toBe("—");
  });
});

describe("clock and ETA", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 8, 28, 13, 5, 9));
  });
  afterEach(() => vi.useRealTimers());

  it("formats 24 and 12 hour clocks", () => {
    const d = new Date(2026, 8, 28, 13, 5, 9);
    expect(formatClock(d, true, true)).toBe("13:05");
    expect(formatClock(d, true, false)).toBe("13:05:09");
    expect(formatClock(d, false, true)).toBe("1:05 pm");
    expect(formatClock(new Date(2026, 8, 28, 0, 7), false, true)).toBe("12:07 am");
    expect(formatClock(new Date(2026, 8, 28, 12, 0), false, true)).toBe("12:00 pm");
    expect(formatClock(undefined, true, true)).toBe("—");
  });

  it("adds a short, locale-aware weekday when the end is not today", () => {
    const now = new Date(2026, 8, 28, 13, 5, 9);
    expect(formatEta(new Date(2026, 8, 28, 23, 59), true, true, "en", now)).toBe("23:59");
    expect(formatEta(new Date(2026, 8, 29, 0, 10), true, true, "en", now)).toBe("Tue 00:10");
    expect(formatEta(new Date(2026, 8, 29, 0, 10), false, true, "en", now)).toBe("Tue 12:10 am");
    expect(formatEta(new Date(2026, 8, 29, 0, 10), true, true, "de", now)).toBe("Di 00:10");
    expect(formatEta(new Date(2026, 9, 5, 9, 0), true, true, "fr", now)).toBe("lun. 09:00");
    expect(formatEta(new Date(2026, 8, 29, 0, 10), true, true, "not a locale!", now)).toBe("Tue 00:10");
    expect(formatEta(new Date(2026, 8, 28, 15, 0), true, true, "en")).toBe("15:00");
    expect(formatEta(undefined, true, true, "en", now)).toBe("—");
  });

  it("prefers the job_eta timestamp", () => {
    expect(computeEta("2026-09-28T15:00:00+00:00", 60)?.toISOString()).toBe("2026-09-28T15:00:00.000Z");
  });
  it("falls back to now + remaining", () => {
    expect(computeEta(undefined, 600)?.getTime()).toBe(Date.now() + 600_000);
    expect(computeEta("garbage", 60)?.getTime()).toBe(Date.now() + 60_000);
    expect(computeEta(undefined, undefined)).toBeUndefined();
  });
});

describe("money, grams, percent", () => {
  it("money uses Intl, plain decimals without currency, and survives a bad code", () => {
    expect(formatMoney(3.5, "en", "EUR")).toBe("€3.50");
    expect(formatMoney(3.5, "en", undefined)).toBe("3.50");
    expect(formatMoney(3.5, "en", "NOT A CODE")).toBe("3.50 NOT A CODE");
    expect(formatMoney(undefined, "en", "EUR")).toBe("—");
  });
  it("grams and percent", () => {
    expect(formatGrams(12.6)).toBe("13 g");
    expect(formatPercent(12.34, 1)).toBe("12.3%");
    expect(formatGrams(undefined)).toBe("—");
  });
  it("drying remaining share", () => {
    expect(dryingRemainingPercent(30, 120)).toBe(25);
    expect(dryingRemainingPercent(30, 0)).toBeUndefined();
    expect(dryingRemainingPercent(200, 120)).toBe(100);
  });
  it("titleCase", () => {
    expect(titleCase("printing")).toBe("Printing");
    expect(titleCase("not_ready yet")).toBe("Not Ready Yet");
    expect(titleCase(undefined)).toBe("—");
  });
});
