import { describe, expect, it } from "vitest";
import {
  ALL_STATS,
  CARD_DEFAULTS,
  CARD_KEYS,
  PANEL_DEFAULTS,
  cardSize,
  resolveConfig,
  stripDefaults,
} from "../src/lib/config";

describe("resolveConfig defaults", () => {
  it("applies every card default to an empty config", () => {
    const c = resolveConfig({ type: "custom:anycubic-card" });
    expect(c).toEqual({
      printer_id: undefined,
      vertical: false,
      round: true,
      use_24hr: true,
      temperatureUnit: "C",
      lightEntityId: undefined,
      powerEntityId: undefined,
      cameraEntityId: undefined,
      monitoredStats: ["Status", "ETA", "Elapsed", "Remaining"],
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
    });
  });

  it("accepts null and undefined", () => {
    expect(resolveConfig(undefined).round).toBe(true);
    expect(resolveConfig(null).sections).toEqual(["filament"]);
  });

  it("covers all 19 documented keys", () => {
    expect(CARD_KEYS).toHaveLength(19);
    const resolved = resolveConfig({});
    for (const key of CARD_KEYS) expect(key in resolved).toBe(true);
  });

  it("does not mutate its input or share default lists", () => {
    const input = Object.freeze({ monitoredStats: Object.freeze(["ETA"]), sections: Object.freeze(["move"]) });
    const c = resolveConfig(input as never);
    c.monitoredStats!.push("Status");
    expect(input.monitoredStats).toEqual(["ETA"]);
    const d = resolveConfig({});
    d.slotColors.push("red");
    d.sections.push("insights");
    expect(CARD_DEFAULTS.slotColors).toEqual([]);
    expect(CARD_DEFAULTS.sections).toEqual(["filament"]);
  });
});

describe("resolveConfig per key", () => {
  it("printer_id", () => {
    expect(resolveConfig({ printer_id: "abc" }).printer_id).toBe("abc");
    expect(resolveConfig({ printer_id: "" }).printer_id).toBeUndefined();
    expect(resolveConfig({ printer_id: 42 }).printer_id).toBe("42");
  });

  it.each(["vertical", "round", "use_24hr", "showSettingsButton", "alwaysShow", "showControls", "noCamera"] as const)(
    "boolean %s honours both values and falls back on junk",
    (key) => {
      expect(resolveConfig({ [key]: true })[key]).toBe(true);
      expect(resolveConfig({ [key]: false })[key]).toBe(false);
      expect(resolveConfig({ [key]: "false" })[key]).toBe(false);
      expect(resolveConfig({ [key]: 7 })[key]).toBe(CARD_DEFAULTS[key]);
    },
  );

  it("temperatureUnit", () => {
    expect(resolveConfig({ temperatureUnit: "F" }).temperatureUnit).toBe("F");
    expect(resolveConfig({ temperatureUnit: "°f" }).temperatureUnit).toBe("F");
    expect(resolveConfig({ temperatureUnit: "K" }).temperatureUnit).toBe("C");
  });

  it("entity ids", () => {
    const c = resolveConfig({ lightEntityId: "light.a", powerEntityId: "switch.p", cameraEntityId: "camera.c" });
    expect([c.lightEntityId, c.powerEntityId, c.cameraEntityId]).toEqual(["light.a", "switch.p", "camera.c"]);
    expect(resolveConfig({ lightEntityId: "" }).lightEntityId).toBeUndefined();
  });

  it("monitoredStats keeps order, allows empty, skips unknown values", () => {
    expect(resolveConfig({ monitoredStats: ["Layer", "T Bed", "ETA"] }).monitoredStats).toEqual(["Layer", "T Bed", "ETA"]);
    expect(resolveConfig({ monitoredStats: [] }).monitoredStats).toEqual([]);
    expect(resolveConfig({ monitoredStats: ["Nope", "Status"] }).monitoredStats).toEqual(["Status"]);
    expect(resolveConfig({ monitoredStats: "ETA" }).monitoredStats).toEqual(["ETA"]);
    expect(ALL_STATS).toHaveLength(24);
  });

  it("scaleFactor", () => {
    expect(resolveConfig({ scaleFactor: 0.75 }).scaleFactor).toBe(0.75);
    expect(resolveConfig({ scaleFactor: 2 }).scaleFactor).toBe(2);
    expect(resolveConfig({ scaleFactor: "0.5" }).scaleFactor).toBe(0.5);
    expect(resolveConfig({ scaleFactor: 0 }).scaleFactor).toBe(1);
    expect(resolveConfig({ scaleFactor: -1 }).scaleFactor).toBe(1);
    expect(resolveConfig({ scaleFactor: "x" }).scaleFactor).toBe(1);
  });

  it("slotColors", () => {
    expect(resolveConfig({ slotColors: ["#ff0000", "blue"] }).slotColors).toEqual(["#ff0000", "blue"]);
    expect(resolveConfig({ slotColors: "#00ff00" }).slotColors).toEqual(["#00ff00"]);
    expect(resolveConfig({ slotColors: [1, "red"] }).slotColors).toEqual(["red"]);
  });

  it("mediaView and printerArt fall back to auto", () => {
    for (const v of ["auto", "camera", "preview", "printer", "printer_model", "none"]) {
      expect(resolveConfig({ mediaView: v }).mediaView).toBe(v);
    }
    expect(resolveConfig({ mediaView: "bogus" }).mediaView).toBe("auto");
    for (const v of ["auto", "kobra_s1", "kobra_s1_combo", "kobra_3", "resin", "fdm"]) {
      expect(resolveConfig({ printerArt: v }).printerArt).toBe(v);
    }
    expect(resolveConfig({ printerArt: "kobra_x" }).printerArt).toBe("auto");
  });

  it("sections render in fixed order and drop unknown values", () => {
    expect(resolveConfig({ sections: ["insights", "filament"] }).sections).toEqual(["filament", "insights"]);
    expect(resolveConfig({ sections: [] }).sections).toEqual([]);
    expect(resolveConfig({ sections: ["move"] }).sections).toEqual([]);
  });
});

describe("legacy move section", () => {
  it("turns the move pad on when showMoveButtons is absent", () => {
    expect(resolveConfig({ sections: ["filament", "move"] }).showMoveButtons).toBe(true);
  });
  it("an explicit boolean always wins", () => {
    expect(resolveConfig({ sections: ["move"], showMoveButtons: false }).showMoveButtons).toBe(false);
    expect(resolveConfig({ sections: [], showMoveButtons: true }).showMoveButtons).toBe(true);
  });
  it("stripDefaults keeps an explicit false next to a legacy move", () => {
    expect(stripDefaults({ sections: ["move"], showMoveButtons: false })).toEqual({
      sections: ["move"],
      showMoveButtons: false,
    });
  });
});

describe("panel defaults", () => {
  it("differ from the card where specified", () => {
    const c = resolveConfig({}, PANEL_DEFAULTS);
    expect(c.showSettingsButton).toBe(true);
    expect(c.alwaysShow).toBe(true);
    expect(c.showMoveButtons).toBe(true);
    expect(c.monitoredStats).toBeUndefined();
  });
  it("honour stored false, 0, empty lists and whole-number scaleFactor", () => {
    const c = resolveConfig(
      { alwaysShow: false, showMoveButtons: false, monitoredStats: [], scaleFactor: 1, mediaView: "none", noCamera: true },
      PANEL_DEFAULTS,
    );
    expect(c.alwaysShow).toBe(false);
    expect(c.showMoveButtons).toBe(false);
    expect(c.monitoredStats).toEqual([]);
    expect(c.scaleFactor).toBe(1);
    expect(c.mediaView).toBe("none");
    expect(c.noCamera).toBe(true);
  });
});

describe("stripDefaults", () => {
  it("removes scalar defaults and keeps lists and other keys", () => {
    expect(
      stripDefaults({
        type: "custom:anycubic-card",
        printer_id: "x",
        round: true,
        vertical: true,
        mediaView: "auto",
        monitoredStats: ["Status", "ETA", "Elapsed", "Remaining"],
        grid_options: { columns: 6 },
        lightEntityId: "",
      }),
    ).toEqual({
      type: "custom:anycubic-card",
      printer_id: "x",
      vertical: true,
      monitoredStats: ["Status", "ETA", "Elapsed", "Remaining"],
      grid_options: { columns: 6 },
    });
  });
});

describe("cardSize", () => {
  it("is 4 without a hero, else 8", () => {
    expect(cardSize(resolveConfig({ mediaView: "none" }))).toBe(4);
    expect(cardSize(resolveConfig({}))).toBe(8);
  });
});
