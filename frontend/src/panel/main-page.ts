// Panel main page (FRONTEND.md §4.15): hero card, info rail, preset gallery.

import { LitElement, css, html, nothing } from "lit";
import { mdiCheck, mdiContentCopy } from "@mdi/js";
import { copyText, defineOnce } from "../ha/dom";
import type { HomeAssistant } from "../ha/types";
import { PANEL_DEFAULTS, STATS_ACE, resolveConfig } from "../lib/config";
import { Printer } from "../lib/entities";
import { formatDuration, dryingRemainingPercent } from "../lib/format";
import { cardYaml } from "../lib/yaml";
import { localize } from "../localize";
import { icon } from "../ui/icon";
import { sharedStyles } from "../ui/styles";
import "../card/card";

const BASE_STATS = ["Status", "ETA", "Elapsed", "Remaining"];
const EXTRA_STATS = ["Online", "Availability", "Project", "Layer"];
const TEMP_STATS = ["Hotend", "Bed", "T Hotend", "T Bed"];

/** The panel hero's rows when the stored config names none (§4.15). */
export function panelDefaultStats(p: Printer): string[] {
  const ace = p.id("multi_color_box_fw_version", "update") !== undefined;
  if (ace) return [...BASE_STATS, ...TEMP_STATS, ...EXTRA_STATS, ...STATS_ACE];
  if (p.isFilament) return [...BASE_STATS, ...TEMP_STATS, ...EXTRA_STATS];
  return [...BASE_STATS, ...EXTRA_STATS];
}

export const PRESETS: { key: string; config: Record<string, unknown> }[] = [
  {
    key: "full",
    config: { mediaView: "printer", showControls: true, showMoveButtons: true, sections: ["filament"], alwaysShow: true },
  },
  { key: "model", config: { mediaView: "printer_model", showControls: true, showMoveButtons: false, alwaysShow: true } },
  {
    key: "compact",
    config: { mediaView: "printer", showControls: false, showMoveButtons: false, alwaysShow: true, monitoredStats: ["Status", "ETA"] },
  },
  {
    key: "vertical",
    config: { vertical: true, mediaView: "printer", showControls: true, showMoveButtons: false, alwaysShow: true },
  },
];

export class AnycubicMainPage extends LitElement {
  static override properties = {
    hass: { attribute: false },
    deviceId: { type: String },
    panelConfig: { attribute: false },
    copied: { state: true },
  };

  hass?: HomeAssistant;
  deviceId?: string;
  panelConfig: Record<string, unknown> = {};
  private copied?: string;

  private t(key: string): string {
    return localize(this.hass?.language, key);
  }

  private f(key: string): string {
    return this.t(`panels.main.cards.main.fields.${key}`);
  }

  private heroConfig(p: Printer): Record<string, unknown> {
    const resolved = resolveConfig(this.panelConfig, PANEL_DEFAULTS);
    return {
      ...this.panelConfig,
      printer_id: this.deviceId,
      monitoredStats: resolved.monitoredStats ?? panelDefaultStats(p),
    };
  }

  private firmwareState(p: Printer, key: string): string | undefined {
    const s = p.value(key, "update");
    return s === "on" ? this.t("common.values.update_available") : s === "off" ? this.t("common.values.up_to_date") : undefined;
  }

  private onOff(p: Printer, key: string, on: string, off: string): string | undefined {
    const v = p.isOn(key);
    return v === undefined ? undefined : this.t(v ? on : off);
  }

  private tile(title: string, rows: [string, string | undefined | null][]) {
    const shown = rows.filter((r): r is [string, string] => r[1] !== undefined && r[1] !== null && r[1] !== "");
    if (!shown.length) return nothing;
    return html`<ha-card class="tile">
      <h3>${title}</h3>
      <dl>
        ${shown.map(([k, v]) => html`<div><dt>${k}</dt><dd>${v}</dd></div>`)}
      </dl>
    </ha-card>`;
  }

  private renderRail(p: Printer) {
    const d = p.device;
    const rem = p.num("dry_status_remaining_time");
    const pct = dryingRemainingPercent(rem, p.num("dry_status_total_duration"));
    const drying =
      rem !== undefined && pct !== undefined && rem > 0 ? `${formatDuration(rem * 60, true)} (${pct.toFixed(2)}%)` : undefined;
    const mac = d?.connections?.[0]?.[1];
    const diag: [string, string | undefined | null][] = [
      [this.f("printer_name"), p.name],
      [this.f("printer_id"), d?.serial_number],
      [this.f("printer_mac"), mac],
    ];
    const diagShown = diag.filter((r) => r[1]);
    return html`<div class="rail">
      ${this.tile(this.t("panels.main.groups.machine"), [
        [this.f("printer_model"), d?.model],
        [this.f("printer_fw_version"), d?.sw_version],
        [this.f("printer_fw_update_available"), this.firmwareState(p, "fw_version")],
        [this.f("printer_online"), this.onOff(p, "printer_online", "common.values.online", "common.values.offline")],
        [this.f("printer_available"), this.onOff(p, "is_available", "common.values.available", "common.values.busy")],
      ])}
      ${this.tile(this.t("panels.main.groups.ace"), [
        [this.f("ace_fw_update_available"), this.firmwareState(p, "multi_color_box_fw_version")],
        [this.f("drying_active"), this.onOff(p, "dry_status_is_drying", "common.values.drying", "common.values.not_drying")],
        [this.f("drying_progress"), drying],
      ])}
      ${diagShown.length
        ? html`<ha-card class="tile">
            <details>
              <summary>${this.t("panels.main.groups.diagnostics")}</summary>
              <dl>
                ${diagShown.map(([k, v]) => html`<div><dt>${k}</dt><dd>${v}</dd></div>`)}
              </dl>
            </details>
          </ha-card>`
        : nothing}
    </div>`;
  }

  private async copy(key: string, yaml: string) {
    if (await copyText(yaml)) {
      this.copied = key;
      window.setTimeout(() => {
        if (this.copied === key) this.copied = undefined;
      }, 1500);
    }
  }

  private renderGallery() {
    return html`<section class="gallery">
      <h2>${this.t("panels.main.presets.title")}</h2>
      <p class="muted">${this.t("panels.main.presets.lede")}</p>
      <div class="grid">
        ${PRESETS.map(({ key, config }) => {
          const full = { printer_id: this.deviceId ?? "<device id>", ...config };
          const yaml = cardYaml(full);
          const done = this.copied === key;
          return html`<ha-card class="preset">
            <header>
              <strong>${this.t(`panels.main.presets.${key}`)}</strong>
              <button class="btn" @click=${() => this.copy(key, yaml)}>
                ${icon(done ? mdiCheck : mdiContentCopy, 18)}
                ${this.t(done ? "panels.main.presets.copied" : "panels.main.presets.copy")}
              </button>
            </header>
            <div class="preview" inert>
              <anycubic-card .hass=${this.hass} .preview=${true} .cardConfig=${full}></anycubic-card>
            </div>
            <pre>${yaml}</pre>
          </ha-card>`;
        })}
      </div>
    </section>`;
  }

  protected override render() {
    const p = new Printer(this.hass, this.deviceId);
    return html`<div class="top">
        <div class="hero">
          <anycubic-card .hass=${this.hass} .defaults=${PANEL_DEFAULTS} .cardConfig=${this.heroConfig(p)}></anycubic-card>
        </div>
        ${this.renderRail(p)}
      </div>
      ${this.renderGallery()}`;
  }

  static override styles = [
    sharedStyles,
    css`
      :host {
        display: block;
      }
      .top {
        display: grid;
        gap: 16px;
      }
      @media (min-width: 1100px) {
        .top {
          grid-template-columns: minmax(0, 2fr) minmax(320px, 1fr);
          align-items: start;
        }
      }
      .rail {
        display: flex;
        flex-direction: column;
        gap: 16px;
      }
      .tile {
        padding: 12px 16px;
      }
      h3 {
        margin: 0 0 8px;
        font-size: 16px;
        font-weight: 500;
      }
      dl {
        margin: 0;
      }
      dl div {
        display: flex;
        justify-content: space-between;
        gap: 12px;
        padding: 4px 0;
        border-bottom: 1px solid color-mix(in srgb, var(--ac-divider) 60%, transparent);
      }
      dl div:last-child {
        border-bottom: none;
      }
      dt {
        color: var(--ac-muted);
      }
      dd {
        margin: 0;
        text-align: right;
        overflow-wrap: anywhere;
      }
      summary {
        cursor: pointer;
        font-weight: 500;
      }
      details[open] summary {
        margin-bottom: 8px;
      }
      .gallery {
        margin-top: 32px;
      }
      .gallery h2 {
        margin: 0 0 4px;
        font-size: 20px;
        font-weight: 500;
      }
      .grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(300px, 380px));
        gap: 16px;
        margin-top: 12px;
      }
      .preset {
        padding: 12px;
        display: flex;
        flex-direction: column;
        gap: 12px;
        min-width: 0;
      }
      .preset header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 8px;
      }
      .preview {
        pointer-events: none;
        user-select: none;
      }
      pre {
        margin: 0;
        padding: 10px;
        border-radius: 8px;
        background: var(--ac-surface-2);
        font-size: 12px;
        overflow-x: auto;
        max-width: 100%;
      }
    `,
  ];
}

defineOnce("anycubic-main-page", AnycubicMainPage);
