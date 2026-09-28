// ACE (multi-colour box) data as the UI needs it.

import { spoolColour, type SpoolInfo } from "./colour";
import type { Printer } from "./entities";

export interface AceSlot {
  slot: number;
  colour?: string;
  material?: string;
  loaded: boolean;
  /**
   * The ledger's estimate of what is left on the reel, from the slot's
   * `ace_slot_N_filament_remaining_percent` sensor; undefined when unknown.
   * Never `consumables_percent`, which Anycubic always reports as 0
   * (DECISIONS, 'Reel fill').
   */
  percent?: number;
  raw: SpoolInfo;
}

export interface AceUnit {
  index: 0 | 1;
  active: boolean;
  slots: AceSlot[];
  /** 1-based slot feeding the printer, or undefined. */
  loadedSlot?: number;
}

export function aceUnit(p: Printer, index: 0 | 1): AceUnit {
  const key = index === 0 ? "ace_spools" : "secondary_ace_spools";
  const active = p.aceActive(index);
  const info = p.attr<SpoolInfo[]>(key, "spool_info");
  const box = p.attr<{ loaded_slot?: number | null }>(key, "box_info");
  const prefix = index === 0 ? "" : "secondary_";
  const slots: AceSlot[] = (Array.isArray(info) ? info : []).map((s, i) => {
    const slot = typeof s?.slot === "number" ? s.slot : i + 1;
    return {
      slot,
      colour: spoolColour(s),
      material: typeof s?.material_type === "string" && s.material_type ? s.material_type : undefined,
      loaded: s?.spool_loaded !== false,
      percent: p.num(`${prefix}ace_slot_${slot}_filament_remaining_percent`),
      raw: s ?? {},
    };
  });
  const loaded = typeof box?.loaded_slot === "number" ? box.loaded_slot : undefined;
  return { index, active, slots, loadedSlot: active ? loaded : undefined };
}

/** Number of ACE units reporting spools: 2, 1 or 0 (§4.5). */
export function aceCount(p: Printer): 0 | 1 | 2 {
  if (p.aceActive(1)) return 2;
  if (p.aceActive(0)) return 1;
  return 0;
}

/**
 * The feeding unit and slot. First unit's loaded slot; else the second unit's
 * (DECISIONS, frontend 7); else slot 1 of the first unit.
 */
export function feedingSlot(units: AceUnit[]): { unit: number; slot: number } {
  const first = units[0];
  if (first?.loadedSlot) return { unit: 0, slot: first.loadedSlot };
  const second = units[1];
  if (second?.loadedSlot) return { unit: 1, slot: second.loadedSlot };
  return { unit: 0, slot: 1 };
}

/** The colour of the filament at the nozzle, if known. */
export function tipColour(units: AceUnit[]): string | undefined {
  const { unit, slot } = feedingSlot(units);
  return units[unit]?.slots.find((s) => s.slot === slot)?.colour;
}
