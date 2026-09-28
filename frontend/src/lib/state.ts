// Shared derivations (FRONTEND.md §4.1).

import { isNoValue, type Printer } from "./entities";

export const PRINTING_STATES = ["printing", "preheating", "paused", "downloading", "checking"];

export type StatusCategory = "activity" | "printing" | "healthy" | "problem";

/** Job state, else `offline`, else the printer status (lower case). */
export function printStateOf(
  jobState: string | undefined,
  online: string | undefined,
  currentStatus: string | undefined,
): string {
  if (!isNoValue(jobState)) return String(jobState).toLowerCase();
  if (online === "off") return "offline";
  return isNoValue(currentStatus) ? "unknown" : String(currentStatus).toLowerCase();
}

export function printState(p: Printer): string {
  return printStateOf(
    p.entity("job_state")?.state,
    p.entity("printer_online", "binary_sensor")?.state,
    p.entity("current_status")?.state,
  );
}

/** The `Status` stat: like the print state, but never `offline`. */
export function statusStat(p: Printer): string {
  return printStateOf(p.entity("job_state")?.state, undefined, p.entity("current_status")?.state);
}

export function jobStateOf(p: Printer): string | undefined {
  return p.value("job_state")?.toLowerCase();
}

export function isPrinting(p: Printer): boolean {
  const s = jobStateOf(p);
  return s !== undefined && PRINTING_STATES.includes(s);
}

export function isPaused(p: Printer): boolean {
  return jobStateOf(p) === "paused";
}

export function isRunning(p: Printer): boolean {
  return isPrinting(p) && !isPaused(p);
}

/** Status colour category. `moving` counts as activity (DECISIONS, frontend 6). */
export function statusCategory(state: string): StatusCategory {
  if (["preheating", "busy", "moving"].includes(state)) return "activity";
  if (PRINTING_STATES.includes(state)) return "printing";
  if (["operational", "finished", "available", "idle", "free"].includes(state)) return "healthy";
  return "problem";
}

export function isErrorState(state: string | undefined): boolean {
  return !!state && (state.includes("fail") || state.includes("error"));
}
