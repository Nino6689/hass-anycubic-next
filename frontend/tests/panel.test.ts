import { describe, expect, it } from "vitest";
import { offeredStats } from "../src/card/editor";
import { Printer } from "../src/lib/entities";
import { canRefresh } from "../src/panel/files-page";
import { PRESETS, panelDefaultStats } from "../src/panel/main-page";
import { PAGES, panelCardConfig, parseRoute } from "../src/panel/panel";
import { parseSlots } from "../src/panel/print-page";
import { device, hassWith } from "./fixtures";

describe("routing", () => {
  it("parses device and page, defaulting to main", () => {
    expect(parseRoute("")).toEqual({});
    expect(parseRoute("/")).toEqual({});
    expect(parseRoute("/abc")).toEqual({ deviceId: "abc", page: "main" });
    expect(parseRoute("/abc/cloud-files")).toEqual({ deviceId: "abc", page: "cloud-files" });
    expect(PAGES).toContain("print-no_cloud_save");
  });
});

describe("panel card_config", () => {
  it("uses the stored card_config object as the panel config itself", () => {
    const stored = { printer_id: "0a1b", monitoredStats: ["Status", "ETA"], use_24hr: false };
    expect(panelCardConfig({ config: { ...stored, _panel_custom: { name: "anycubic-cloud-panel" } } })).toEqual(stored);
  });
  it("accepts the config directly or nested, dropping the custom-panel block", () => {
    expect(panelCardConfig({ config: { round: false, _panel_custom: { name: "x" } } })).toEqual({ round: false });
    expect(panelCardConfig({ config: { card_config: { alwaysShow: false } } })).toEqual({ alwaysShow: false });
    expect(panelCardConfig({ config: null })).toEqual({});
    expect(panelCardConfig(undefined)).toEqual({});
  });
});

describe("print slots", () => {
  it("parses slot lists", () => {
    expect(parseSlots("1, 2 5")).toEqual([1, 2, 5]);
    expect(parseSlots("")).toEqual([]);
    expect(parseSlots("0")).toBeUndefined();
    expect(parseSlots("a")).toBeUndefined();
    expect(parseSlots("1.5")).toBeUndefined();
  });
});

const printer = device("p1");
const ace = device("a1", { via_device_id: "p1" });

describe("stats offered and panel defaults", () => {
  it("filament printer with ACE", () => {
    const h = hassWith(
      [printer, ace],
      [
        { id: "sensor.k_status", device: "p1", key: "current_status", state: "idle", attrs: { material_type: "Filament" } },
        { id: "sensor.k_ace", device: "a1", key: "ace_spools", state: "active" },
        { id: "update.k_ace_fw", device: "a1", key: "multi_color_box_fw_version", state: "off" },
      ],
    );
    const p = new Printer(h, "p1");
    const offered = offeredStats(p);
    expect(offered).toContain("Hotend");
    expect(offered).toContain("Dry Time");
    expect(offered).not.toContain("On Time");
    expect(new Set(offered).size).toBe(offered.length);
    expect(panelDefaultStats(p)).toEqual([
      "Status", "ETA", "Elapsed", "Remaining", "Hotend", "Bed", "T Hotend", "T Bed",
      "Online", "Availability", "Project", "Layer", "Dry Status", "Dry Time",
    ]);
  });
  it("resin printer", () => {
    const h = hassWith([printer], [{ id: "sensor.k_status", device: "p1", key: "current_status", state: "idle", attrs: { material_type: "Resin" } }]);
    const p = new Printer(h, "p1");
    expect(offeredStats(p)).toContain("Z Up Speed");
    expect(offeredStats(p)).not.toContain("Hotend");
    expect(panelDefaultStats(p)).toEqual(["Status", "ETA", "Elapsed", "Remaining", "Online", "Availability", "Project", "Layer"]);
  });
  it("presets carry no camera", () => {
    for (const preset of PRESETS) expect(preset.config.mediaView).not.toBe("camera");
  });
});

describe("file refresh", () => {
  const withButtons = (local?: string, cloud?: string) =>
    new Printer(
      hassWith(
        [printer],
        [
          ...(local === undefined ? [] : [{ id: "button.k_req_local", device: "p1", key: "request_file_list_local", state: local }]),
          ...(cloud === undefined ? [] : [{ id: "button.k_req_cloud", device: "p1", key: "request_file_list_cloud", state: cloud }]),
          { id: "binary_sensor.k_mqtt", device: "p1", key: "mqtt_connection_active", state: "off", attrs: { supports_mqtt_login: false } },
        ],
      ),
      "p1",
    );
  it("follows the source's request button", () => {
    expect(canRefresh(withButtons("unknown"), "local")).toBe(true);
    expect(canRefresh(withButtons("2026-09-28T10:00:00+00:00"), "local")).toBe(true);
    expect(canRefresh(withButtons("unavailable"), "local")).toBe(false);
    expect(canRefresh(withButtons("unknown"), "udisk")).toBe(false);
    expect(canRefresh(withButtons(undefined, "unknown"), "cloud")).toBe(true);
    expect(canRefresh(withButtons("unknown", "unavailable"), "cloud")).toBe(false);
    expect(canRefresh(withButtons(), "cloud")).toBe(false);
  });
});
