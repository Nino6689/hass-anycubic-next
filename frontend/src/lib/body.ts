// Which printer body the artwork draws (FRONTEND.md §4.5).

import type { PrinterArt } from "./config";

export type Body = "enclosed" | "bedslinger" | "resin" | "generic";

const RULES: [string[], Body][] = [
  [["kobra s1"], "enclosed"],
  [["kobra 3"], "bedslinger"],
  [["kobra 2"], "bedslinger"],
  [["photon", "mono", "m5s", "m7"], "resin"],
  [["kobra"], "bedslinger"],
];

export function bodyFromModel(model: string | undefined | null): Body {
  const text = (model ?? "").toLowerCase();
  for (const [needles, body] of RULES) {
    if (needles.some((n) => text.includes(n))) return body;
  }
  return "generic";
}

export interface BodyChoice {
  body: Body;
  /** At least this many ACE units are drawn even before any reports. */
  minAce: number;
}

export function chooseBody(art: PrinterArt, model: string | undefined | null): BodyChoice {
  switch (art) {
    case "kobra_s1":
      return { body: "enclosed", minAce: 0 };
    case "kobra_s1_combo":
      return { body: "enclosed", minAce: 1 };
    case "kobra_3":
      return { body: "bedslinger", minAce: 0 };
    case "resin":
      return { body: "resin", minAce: 0 };
    case "fdm":
      return { body: "generic", minAce: 0 };
    default:
      return { body: bodyFromModel(model), minAce: 0 };
  }
}
