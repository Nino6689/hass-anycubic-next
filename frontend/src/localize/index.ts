// String lookup (FRONTEND.md §5.2): exact language, then its base language,
// then English, per key. `{name}` placeholders are filled from `vars`.

import { titleCase } from "../lib/format";
import de from "./languages/de.json";
import en from "./languages/en.json";
import es from "./languages/es.json";
import fr from "./languages/fr.json";
import nl from "./languages/nl.json";
import zhHans from "./languages/zh-Hans.json";

type Tree = { [key: string]: string | Tree };

// Only English is written so far; the others fall back to it key by key.
export const LANGUAGES: Record<string, Tree> = {
  en: en as Tree,
  de: de as Tree,
  es: es as Tree,
  fr: fr as Tree,
  nl: nl as Tree,
  "zh-Hans": zhHans as Tree,
};

function lookup(tree: Tree | undefined, key: string): string | undefined {
  let node: string | Tree | undefined = tree;
  for (const part of key.split(".")) {
    if (node === undefined || typeof node === "string") return undefined;
    node = node[part];
  }
  return typeof node === "string" ? node : undefined;
}

export function languageChain(language: string | undefined): string[] {
  const chain: string[] = [];
  if (language) {
    chain.push(language);
    const base = language.split("-")[0];
    if (base !== language) chain.push(base);
  }
  chain.push("en");
  return chain;
}

/** Look a key up; returns undefined when no language has it. */
export function tryLocalize(
  language: string | undefined,
  key: string,
  vars?: Record<string, string | number>,
): string | undefined {
  let text: string | undefined;
  for (const code of languageChain(language)) {
    text = lookup(LANGUAGES[code], key);
    if (text !== undefined) break;
  }
  if (text === undefined) return undefined;
  if (!vars) return text;
  return text.replace(/\{(\w+)\}/g, (m, name: string) => (name in vars ? String(vars[name]) : m));
}

/** Look a key up; a missing key shows the key itself so it is noticed. */
export function localize(language: string | undefined, key: string, vars?: Record<string, string | number>): string {
  return tryLocalize(language, key, vars) ?? key;
}

export type Localizer = (key: string, vars?: Record<string, string | number>) => string;

export function localizer(language: string | undefined): Localizer {
  return (key, vars) => localize(language, key, vars);
}

/** A job or printer state word, translated when known, else title-cased. */
export function stateWord(language: string | undefined, state: string | undefined): string {
  if (!state) return localize(language, "common.states.unknown");
  const known = tryLocalize(language, `common.states.${state.toLowerCase()}`);
  if (known) return known;
  return titleCase(state);
}
