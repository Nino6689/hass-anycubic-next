import { describe, expect, it } from "vitest";
import { aceUnit } from "../src/lib/ace";
import { Printer } from "../src/lib/entities";
import { device, hassWith } from "./fixtures";

const printer = device("p1", { name: "Kobra S1" });
const ace1 = device("a1", { via_device_id: "p1", name: "ACE Pro" });
const ace2 = device("a2", { via_device_id: "p1", name: "Secondary ACE Pro" });

// Anycubic reports consumables_percent as 0 on every slot (BEHAVIOUR §2.7).
const spools = [1, 2, 3, 4].map((slot) => ({
  slot,
  material_type: "PLA",
  color_hex: "#FF0000",
  spool_loaded: true,
  consumables_percent: 0,
}));

function hass(percents: { key: string; state?: string; device: string }[]) {
  return hassWith(
    [printer, ace1, ace2],
    [
      { id: "sensor.kobra_s1_ace_spools", device: "a1", key: "ace_spools", state: "active", attrs: { spool_info: spools } },
      {
        id: "sensor.kobra_s1_secondary_ace_spools",
        device: "a2",
        key: "secondary_ace_spools",
        state: "active",
        attrs: { spool_info: spools },
      },
      ...percents.map((p) => ({ id: `sensor.kobra_s1_${p.key}_x`, device: p.device, key: p.key, state: p.state })),
    ],
  );
}

describe("reel fill (DECISIONS, 'Reel fill')", () => {
  it("comes from each slot's remaining-percent sensor, never consumables_percent", () => {
    const h = hass([
      { key: "ace_slot_1_filament_remaining_percent", state: "75.0", device: "a1" },
      { key: "ace_slot_2_filament_remaining_percent", state: "28.3", device: "a1" },
      { key: "ace_slot_3_filament_remaining_percent", state: "unknown", device: "a1" },
      // Slot 4: the sensor is disabled (no state) — unknown.
      { key: "ace_slot_4_filament_remaining_percent", device: "a1" },
    ]);
    const unit = aceUnit(new Printer(h, "p1"), 0);
    expect(unit.slots.map((s) => s.percent)).toEqual([75, 28.3, undefined, undefined]);
  });

  it("reads the secondary_ sensors for the second ACE", () => {
    const h = hass([
      { key: "ace_slot_1_filament_remaining_percent", state: "10.0", device: "a1" },
      { key: "secondary_ace_slot_1_filament_remaining_percent", state: "60.0", device: "a2" },
      { key: "secondary_ace_slot_3_filament_remaining_percent", state: "0.0", device: "a2" },
    ]);
    const p = new Printer(h, "p1");
    expect(aceUnit(p, 0).slots.map((s) => s.percent)).toEqual([10, undefined, undefined, undefined]);
    expect(aceUnit(p, 1).slots.map((s) => s.percent)).toEqual([60, undefined, 0, undefined]);
  });

  it("is unknown (drawn full) without any remaining-percent sensor", () => {
    const unit = aceUnit(new Printer(hass([]), "p1"), 0);
    expect(unit.slots).toHaveLength(4);
    expect(unit.slots.every((s) => s.percent === undefined)).toBe(true);
  });
});
