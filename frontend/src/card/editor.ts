// The card's visual editor (FRONTEND.md §2.5).

import { LitElement, css, html, nothing, type PropertyValues } from "lit";
import { mdiArrowDown, mdiArrowUp, mdiClose } from "@mdi/js";
import { defineOnce, fire } from "../ha/dom";
import type { HomeAssistant } from "../ha/types";
import {
  MEDIA_VIEWS,
  PRINTER_ARTS,
  SECTIONS,
  STATS_ACE,
  STATS_FDM,
  STATS_GENERAL,
  STATS_RESIN,
  STATS_TIME,
  legacyMoveRequested,
  resolveConfig,
  stripDefaults,
} from "../lib/config";
import { Printer, deviceName, findPrinters } from "../lib/entities";
import { localize } from "../localize";
import { icon } from "../ui/icon";
import { sharedStyles } from "../ui/styles";

type Tab = "main" | "stats" | "colours";

/** Stats offered for a printer: general + time, then FDM or resin, then ACE. */
export function offeredStats(p: Printer): string[] {
  const list: string[] = [...STATS_GENERAL, ...STATS_TIME];
  if (p.isResin) list.push(...STATS_RESIN);
  else if (p.isFilament) list.push(...STATS_FDM);
  if (p.aceActive(0)) list.push(...STATS_ACE);
  return [...new Set(list)];
}

export class AnycubicCardEditor extends LitElement {
  static override properties = {
    hass: { attribute: false },
    config: { state: true },
    tab: { state: true },
  };

  hass?: HomeAssistant;
  private config: Record<string, unknown> = {};
  private tab: Tab = "main";

  static override styles = [
    sharedStyles,
    css`
      .tabs {
        display: flex;
        gap: 4px;
        border-bottom: 1px solid var(--ac-divider);
        margin-bottom: 16px;
      }
      .tabs button {
        background: none;
        border: none;
        border-bottom: 2px solid transparent;
        padding: 10px 14px;
        cursor: pointer;
        text-transform: uppercase;
        font-size: 13px;
        font-weight: 500;
        color: var(--ac-muted);
      }
      .tabs button[aria-selected="true"] {
        color: var(--ac-accent);
        border-bottom-color: var(--ac-accent);
      }
      ul {
        list-style: none;
        margin: 0;
        padding: 0;
      }
      li {
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 4px 0;
        border-bottom: 1px solid color-mix(in srgb, var(--ac-divider) 60%, transparent);
      }
      li label {
        flex: 1;
        display: flex;
        align-items: center;
        gap: 10px;
        cursor: pointer;
      }
      input[type="checkbox"] {
        min-height: auto;
        width: 18px;
        height: 18px;
      }
      .colour-row {
        display: flex;
        gap: 8px;
        align-items: center;
        margin-bottom: 8px;
      }
      .colour-row input {
        flex: 1;
      }
      .sample {
        width: 28px;
        height: 28px;
        border-radius: 50%;
        border: 1px solid var(--ac-divider);
        flex: none;
      }
      p {
        margin: 0 0 12px;
      }
    `,
  ];

  setConfig(config: Record<string, unknown>): void {
    this.config = config && typeof config === "object" ? { ...config } : {};
  }

  private t(key: string): string {
    return localize(this.hass?.language, key);
  }

  private get printer(): Printer {
    return new Printer(this.hass, resolveConfig(this.config).printer_id);
  }

  protected override willUpdate(changed: PropertyValues): void {
    if (this.tab === "colours" && changed.has("hass") && !this.printer.aceActive(0)) this.tab = "main";
  }

  private emit(next: Record<string, unknown>) {
    this.config = next;
    fire(this, "config-changed", { config: stripDefaults(next) });
  }

  // ---- main tab: a Home Assistant form ------------------------------------

  private schema() {
    const opts = (prefix: string, values: readonly string[]) =>
      values.map((v) => ({ value: v, label: this.t(`card.configure.options.${prefix}.${v}`) }));
    const printers = findPrinters(this.hass).map((d) => ({ value: d.id, label: deviceName(d) ?? d.id }));
    return [
      { name: "printer_id", selector: { select: { mode: "dropdown", options: printers } } },
      { name: "vertical", selector: { boolean: {} } },
      { name: "round", selector: { boolean: {} } },
      { name: "use_24hr", selector: { boolean: {} } },
      {
        name: "temperatureUnit",
        selector: { select: { mode: "list", options: [{ value: "C", label: "°C" }, { value: "F", label: "°F" }] } },
      },
      { name: "alwaysShow", selector: { boolean: {} } },
      { name: "showSettingsButton", selector: { boolean: {} } },
      {
        name: "scaleFactor",
        selector: {
          select: {
            mode: "list",
            options: ["1", "0.75", "0.5"].map((v) => ({ value: v, label: this.t(`card.configure.options.scale_factor.${v}`) })),
          },
        },
      },
      { name: "lightEntityId", selector: { entity: { domain: "light" } } },
      { name: "powerEntityId", selector: { entity: { domain: "switch" } } },
      { name: "cameraEntityId", selector: { entity: { domain: "camera" } } },
      { name: "mediaView", selector: { select: { mode: "dropdown", options: opts("media_view", MEDIA_VIEWS) } } },
      { name: "printerArt", selector: { select: { mode: "dropdown", options: opts("printer_art", PRINTER_ARTS) } } },
      { name: "showControls", selector: { boolean: {} } },
      { name: "showMoveButtons", selector: { boolean: {} } },
      { name: "noCamera", selector: { boolean: {} } },
      { name: "sections", selector: { select: { multiple: true, mode: "list", options: opts("sections", SECTIONS) } } },
    ];
  }

  private static LABELS: Record<string, string> = {
    printer_id: "printer_id",
    vertical: "vertical",
    round: "round",
    use_24hr: "use_24hr",
    temperatureUnit: "temperature_unit",
    alwaysShow: "always_show",
    showSettingsButton: "show_settings_button",
    scaleFactor: "scale_factor",
    lightEntityId: "light_entity_id",
    powerEntityId: "power_entity_id",
    cameraEntityId: "camera_entity_id",
    mediaView: "media_view",
    printerArt: "printer_art",
    showControls: "show_controls",
    showMoveButtons: "show_move_buttons",
    noCamera: "no_camera",
    sections: "sections",
  };

  private formData(): Record<string, unknown> {
    const r = resolveConfig(this.config);
    return {
      ...r,
      scaleFactor: String(r.scaleFactor),
      lightEntityId: r.lightEntityId ?? "",
      powerEntityId: r.powerEntityId ?? "",
      cameraEntityId: r.cameraEntityId ?? "",
    };
  }

  private formChanged(ev: CustomEvent<{ value: Record<string, unknown> }>) {
    ev.stopPropagation();
    const value = ev.detail.value;
    const next: Record<string, unknown> = { ...this.config };
    for (const [key, v] of Object.entries(value)) {
      if (!(key in AnycubicCardEditor.LABELS)) continue;
      if (key === "scaleFactor") next[key] = Number(v);
      else if (key === "sections") {
        // Keep a legacy `move` entry only while the move toggle has not been set.
        const keepMove = legacyMoveRequested(this.config) && typeof this.config.showMoveButtons !== "boolean";
        next[key] = keepMove ? [...(v as string[]), "move"] : v;
      } else if (v === "" || v === undefined) delete next[key];
      else next[key] = v;
    }
    this.emit(next);
  }

  private renderMain() {
    const LABELS = AnycubicCardEditor.LABELS;
    const helpers = new Set(["lightEntityId", "powerEntityId", "cameraEntityId"]);
    return html`<ha-form
      .hass=${this.hass}
      .data=${this.formData()}
      .schema=${this.schema()}
      .computeLabel=${(s: { name: string }) => this.t(`card.configure.labels.${LABELS[s.name]}`)}
      .computeHelper=${(s: { name: string }) =>
        helpers.has(s.name) ? this.t(`card.configure.helpers.${LABELS[s.name]}`) : undefined}
      @value-changed=${this.formChanged}
    ></ha-form>`;
  }

  // ---- stats tab: tick and reorder ---------------------------------------

  private renderStats() {
    const offered = offeredStats(this.printer);
    const current = (resolveConfig(this.config).monitoredStats ?? []).filter((s) => offered.includes(s));
    const rest = offered.filter((s) => !current.includes(s));
    const set = (list: string[]) => this.emit({ ...this.config, monitoredStats: list });
    const move = (i: number, d: -1 | 1) => {
      const list = [...current];
      const j = i + d;
      if (j < 0 || j >= list.length) return;
      [list[i], list[j]] = [list[j], list[i]];
      set(list);
    };
    return html`<p class="muted">${this.t("card.configure.labels.monitored_stats")}</p>
      <ul>
        ${current.map(
          (s, i) => html`<li>
            <label
              ><input type="checkbox" checked @change=${() => set(current.filter((x) => x !== s))} />${this.t(
                `card.monitored_stats.${s}`,
              )}</label
            >
            <button class="icon-btn" ?disabled=${i === 0} title=${this.t("card.configure.labels.move_up")} @click=${() => move(i, -1)}>
              ${icon(mdiArrowUp, 20)}
            </button>
            <button
              class="icon-btn"
              ?disabled=${i === current.length - 1}
              title=${this.t("card.configure.labels.move_down")}
              @click=${() => move(i, 1)}
            >
              ${icon(mdiArrowDown, 20)}
            </button>
          </li>`,
        )}
        ${rest.map(
          (s) => html`<li>
            <label
              ><input type="checkbox" @change=${() => set([...current, s])} />${this.t(`card.monitored_stats.${s}`)}</label
            >
          </li>`,
        )}
      </ul>`;
  }

  // ---- colours tab -------------------------------------------------------

  private renderColours() {
    const colours = resolveConfig(this.config).slotColors;
    const set = (list: string[]) => this.emit({ ...this.config, slotColors: list });
    return html`<p class="muted">${this.t("card.configure.labels.slot_colors")}</p>
      ${colours.map(
        (c, i) => html`<div class="colour-row">
          <span class="sample" style="background:${c}"></span>
          <input
            .value=${c}
            @change=${(e: Event) => {
              const next = [...colours];
              next[i] = (e.target as HTMLInputElement).value.trim();
              set(next.filter((x) => x !== ""));
            }}
          />
          <button class="icon-btn" title=${this.t("card.configure.labels.remove")} @click=${() => set(colours.filter((_, j) => j !== i))}>
            ${icon(mdiClose, 20)}
          </button>
        </div>`,
      )}
      <div class="colour-row">
        <input
          placeholder="#ff7700"
          @change=${(e: Event) => {
            const input = e.target as HTMLInputElement;
            const v = input.value.trim();
            input.value = "";
            if (v) set([...colours, v]);
          }}
        />
        <span class="muted">${this.t("card.configure.labels.add_colour")}</span>
      </div>`;
  }

  protected override render() {
    if (!this.hass) return nothing;
    const tabs: Tab[] = ["main", "stats"];
    if (this.printer.aceActive(0)) tabs.push("colours");
    return html`<div class="tabs" role="tablist">
        ${tabs.map(
          (k) => html`<button role="tab" aria-selected=${k === this.tab ? "true" : "false"} @click=${() => (this.tab = k)}>
            ${this.t(`card.configure.tabs.${k}`)}
          </button>`,
        )}
      </div>
      ${this.tab === "main" ? this.renderMain() : this.tab === "stats" ? this.renderStats() : this.renderColours()}`;
  }
}

defineOnce("anycubic-card-editor", AnycubicCardEditor);
