import { describe, expect, it } from "vitest";
import { feedingSlot, tipColour, type AceUnit } from "../src/lib/ace";
import { bodyFromModel, chooseBody } from "../src/lib/body";
import { contrastOn, heatLevel, normaliseColour, spoolColour, spoolRgb } from "../src/lib/colour";
import { printStateOf, statusCategory } from "../src/lib/state";
import { cardYaml } from "../src/lib/yaml";
import { LANGUAGES, localize, stateWord, tryLocalize } from "../src/localize";

describe("print state", () => {
  it("follows job state, then offline, then printer status", () => {
    expect(printStateOf("Printing", "on", "busy")).toBe("printing");
    expect(printStateOf("unavailable", "off", "busy")).toBe("offline");
    expect(printStateOf(undefined, "on", "Available")).toBe("available");
    expect(printStateOf(undefined, undefined, undefined)).toBe("unknown");
  });
  it("colours moving as activity, not a problem", () => {
    expect(statusCategory("moving")).toBe("activity");
    expect(statusCategory("preheating")).toBe("activity");
    expect(statusCategory("paused")).toBe("printing");
    expect(statusCategory("idle")).toBe("healthy");
    expect(statusCategory("offline")).toBe("problem");
    expect(statusCategory("failed")).toBe("problem");
  });
});

describe("colours", () => {
  it("normalises the accepted forms", () => {
    expect(normaliseColour("#FF0000")).toBe("#ff0000");
    expect(normaliseColour("#ff000080")).toBe("#ff0000");
    expect(normaliseColour("#f00")).toBe("#ff0000");
    expect(normaliseColour("00ff00")).toBe("#00ff00");
    expect(normaliseColour("rgb(1, 2, 3)")).toBe("rgb(1, 2, 3)");
    expect(normaliseColour("hsl(120deg 50% 50%)")).toBe("hsl(120deg 50% 50%)");
    expect(normaliseColour("Grey")).toBe(normaliseColour("gray"));
    expect(normaliseColour("sparkly")).toBeUndefined();
    expect(normaliseColour(12)).toBeUndefined();
  });
  it("reads a spool's colour from hex, then rgb", () => {
    expect(spoolColour({ color_hex: "#123456", color: [0, 0, 0] })).toBe("#123456");
    expect(spoolColour({ color: [255, 128, 0] })).toBe("#ff8000");
    expect(spoolColour({})).toBeUndefined();
    expect(spoolRgb({ color_hex: "#ff8000" })).toEqual([255, 128, 0]);
  });
  it("heat and contrast", () => {
    expect(heatLevel(20, 220)).toBe(0);
    expect(heatLevel(120, 220)).toBe(0.5);
    expect(heatLevel(300, 220)).toBe(1);
    expect(heatLevel(100, undefined)).toBe(0);
    expect(heatLevel(100, 0)).toBe(0);
    expect(contrastOn("#ffffff")).toBe("#1b1b1b");
    expect(contrastOn("#000000")).toBe("#ffffff");
  });
});

describe("ACE feeding slot", () => {
  const unit = (index: 0 | 1, loaded?: number): AceUnit => ({
    index,
    active: true,
    loadedSlot: loaded,
    slots: [1, 2, 3, 4].map((slot) => ({ slot, loaded: true, colour: `#${index}${slot}0000`, raw: {} })),
  });
  it("uses the first unit, then the second, then slot 1", () => {
    expect(feedingSlot([unit(0, 3), unit(1, 2)])).toEqual({ unit: 0, slot: 3 });
    expect(feedingSlot([unit(0), unit(1, 2)])).toEqual({ unit: 1, slot: 2 });
    expect(feedingSlot([unit(0)])).toEqual({ unit: 0, slot: 1 });
    expect(tipColour([unit(0, 3)])).toBe("#030000");
    expect(tipColour([])).toBeUndefined();
  });
});

describe("artwork body", () => {
  it("matches models in order", () => {
    expect(bodyFromModel("Anycubic Kobra S1 Combo")).toBe("enclosed");
    expect(bodyFromModel("Kobra 3 Max")).toBe("bedslinger");
    expect(bodyFromModel("KOBRA 2 Neo")).toBe("bedslinger");
    expect(bodyFromModel("Photon Mono M7 Pro")).toBe("resin");
    expect(bodyFromModel("Kobra X")).toBe("bedslinger");
    expect(bodyFromModel("Vyper")).toBe("generic");
    expect(bodyFromModel(undefined)).toBe("generic");
  });
  it("forced bodies and the combo", () => {
    expect(chooseBody("kobra_s1_combo", "whatever")).toEqual({ body: "enclosed", minAce: 1 });
    expect(chooseBody("resin", "Kobra S1")).toEqual({ body: "resin", minAce: 0 });
    expect(chooseBody("auto", "Kobra S1")).toEqual({ body: "enclosed", minAce: 0 });
  });
});

describe("yaml", () => {
  it("writes keys, lists and quotes risky strings", () => {
    expect(
      cardYaml({ printer_id: "0a1b", mediaView: "printer", alwaysShow: true, monitoredStats: ["Status", "ETA"], sections: [] }),
    ).toBe(
      [
        "type: custom:anycubic-card",
        'printer_id: "0a1b"',
        "mediaView: printer",
        "alwaysShow: true",
        "monitoredStats:",
        "  - Status",
        "  - ETA",
        "sections: []",
      ].join("\n"),
    );
  });
});

describe("localisation", () => {
  it("falls back from region to base to English, per key", () => {
    expect(localize("de-CH", "common.actions.yes")).toBe("Yes");
    expect(localize("fr", "card.monitored_stats.T Bed")).toBe("Bed target");
    expect(localize("en", "card.print_settings.confirm_message", { action: "pause" })).toBe("Do you want to pause the print?");
    expect(tryLocalize("en", "no.such.key")).toBeUndefined();
    expect(localize("en", "no.such.key")).toBe("no.such.key");
  });
  it("translates state words and title-cases unknown ones", () => {
    expect(stateWord("en", "PRINTING")).toBe("Printing");
    expect(stateWord("en", "self_test")).toBe("Self Test");
    expect(stateWord("en", undefined)).toBe("Unknown");
  });
  it("has a label for every stat and every editor option", async () => {
    const { ALL_STATS, MEDIA_VIEWS, PRINTER_ARTS, SECTIONS } = await import("../src/lib/config");
    for (const s of ALL_STATS) expect(tryLocalize("en", `card.monitored_stats.${s}`)).toBeDefined();
    for (const v of MEDIA_VIEWS) expect(tryLocalize("en", `card.configure.options.media_view.${v}`)).toBeDefined();
    for (const v of PRINTER_ARTS) expect(tryLocalize("en", `card.configure.options.printer_art.${v}`)).toBeDefined();
    for (const v of SECTIONS) expect(tryLocalize("en", `card.configure.options.sections.${v}`)).toBeDefined();
    expect(Object.keys(LANGUAGES)).toEqual(["en", "de", "es", "fr", "nl", "zh-Hans"]);
  });
});
