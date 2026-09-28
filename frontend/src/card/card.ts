// The dashboard card, `custom:anycubic-card` (FRONTEND.md §2, §4).

import { LitElement, css, html, nothing, type PropertyValues, type TemplateResult } from "lit";
import {
  mdiAlert,
  mdiArrowDown,
  mdiArrowLeft,
  mdiArrowRight,
  mdiArrowUp,
  mdiChevronDown,
  mdiCog,
  mdiEngineOff,
  mdiHome,
  mdiHomeOutline,
  mdiLightbulbOn,
  mdiLightbulbOutline,
  mdiPause,
  mdiPlay,
  mdiPower,
  mdiRadiator,
  mdiStop,
} from "@mdi/js";
import { defineOnce } from "../ha/dom";
import type { HomeAssistant } from "../ha/types";
import { pressButton, selectOption, toggleEntity, toggleSwitch } from "../lib/actions";
import { aceUnit, type AceSlot } from "../lib/ace";
import { CARD_DEFAULTS, cardSize, resolveConfig, type Defaults, type ResolvedConfig } from "../lib/config";
import { Printer, findPrinters } from "../lib/entities";
import {
  NO_VALUE,
  clampPercent,
  computeEta,
  dryingRemainingPercent,
  formatClock,
  formatDuration,
  formatGrams,
  formatMoney,
  formatPercent,
  formatTemperature,
  parseDurationSeconds,
} from "../lib/format";
import { isPaused, isPrinting, isRunning, printState, statusCategory, statusStat } from "../lib/state";
import { localize, stateWord } from "../localize";
import { icon } from "../ui/icon";
import { sharedStyles } from "../ui/styles";
import "./dialogs";
import "./hero";

type Dialog =
  | { kind: "settings" }
  | { kind: "spool"; unit: 0 | 1; slot: AceSlot }
  | { kind: "drying"; unit: 0 | 1 }
  | { kind: "cancel" };

interface Tick {
  sig: string;
  base: number;
  at: number;
}

export class AnycubicCard extends LitElement {
  static override properties = {
    hass: { attribute: false },
    preview: { type: Boolean },
    defaults: { attribute: false },
    raw: { state: true },
    revealed: { state: true },
    openSection: { state: true },
    dialog: { state: true },
    pending: { state: true },
  };

  hass?: HomeAssistant;
  /** Set by Home Assistant in card-picker/editor previews; never start a camera. */
  preview = false;
  /** Defaults to apply (the panel passes its own). */
  defaults: Readonly<Defaults> = CARD_DEFAULTS;
  private raw: Record<string, unknown> = {};
  private revealed = false;
  private openSection?: "filament" | "insights";
  private dialog?: Dialog;
  private pending = new Set<string>();
  private config: ResolvedConfig = resolveConfig({});
  private printer: Printer = new Printer(undefined, undefined);
  private ticks = new Map<string, Tick>();
  private timer?: number;

  // ---- Lovelace card API -------------------------------------------------

  setConfig(config: Record<string, unknown>): void {
    // Keep our own shallow copy; the dashboard's object is never touched.
    this.raw = config && typeof config === "object" ? { ...config } : {};
  }

  /** Property form of setConfig, for hosts that render the card from a template. */
  set cardConfig(config: Record<string, unknown>) {
    this.setConfig(config);
  }

  getCardSize(): number {
    return cardSize(this.config);
  }

  getGridOptions() {
    return { columns: 12, min_columns: 6, rows: "auto" };
  }

  static getConfigElement(): HTMLElement {
    return document.createElement("anycubic-card-editor");
  }

  static getStubConfig(hass?: HomeAssistant): Record<string, unknown> {
    const first = findPrinters(hass)[0];
    return first ? { printer_id: first.id } : {};
  }

  // ---- lifecycle ---------------------------------------------------------

  override connectedCallback(): void {
    super.connectedCallback();
    this.timer = window.setInterval(() => {
      if (isRunning(this.printer)) this.requestUpdate();
    }, 1000);
  }

  override disconnectedCallback(): void {
    window.clearInterval(this.timer);
    super.disconnectedCallback();
  }

  protected override willUpdate(changed: PropertyValues): void {
    if (changed.has("raw") || changed.has("defaults")) {
      this.config = resolveConfig(this.raw, this.defaults);
    }
    if (changed.has("hass") || changed.has("raw")) {
      this.printer = new Printer(this.hass, this.config.printer_id);
    }
  }

  // ---- helpers -----------------------------------------------------------

  private t(key: string, vars?: Record<string, string | number>): string {
    return localize(this.hass?.language, key, vars);
  }

  private async act(id: string, work: () => Promise<void>): Promise<void> {
    if (this.pending.has(id)) return;
    this.pending = new Set(this.pending).add(id);
    try {
      await work();
    } catch (err) {
      console.error("anycubic-card:", err);
    } finally {
      const next = new Set(this.pending);
      next.delete(id);
      this.pending = next;
    }
  }

  /** A duration entity in seconds, ticking while the job runs (§4.7). */
  private ticking(key: string, direction: 1 | -1): number | undefined {
    const e = this.printer.entity(key);
    const base = parseDurationSeconds(e && e.state !== "unavailable" && e.state !== "unknown" ? e.state : undefined);
    if (!e || base === undefined) return undefined;
    const sig = `${e.state}|${e.last_updated}`;
    let tick = this.ticks.get(key);
    if (!tick || tick.sig !== sig) {
      tick = { sig, base, at: Date.now() };
      this.ticks.set(key, tick);
    }
    if (!isRunning(this.printer)) {
      tick.base = base;
      tick.at = Date.now();
      return base;
    }
    const passed = (Date.now() - tick.at) / 1000;
    return Math.max(0, tick.base + direction * passed);
  }

  private temp(key: string): string {
    const e = this.printer.entity(key);
    const unit = e?.attributes.unit_of_measurement;
    return formatTemperature(this.printer.num(key), unit, this.config.temperatureUnit, this.config.round);
  }

  private plain(key: string, suffix = ""): string {
    const v = this.printer.value(key);
    return v === undefined ? NO_VALUE : `${v}${suffix}`;
  }

  // ---- stats -------------------------------------------------------------

  private statValue(stat: string): TemplateResult | string {
    const p = this.printer;
    const c = this.config;
    const lang = this.hass?.language;
    switch (stat) {
      case "Status":
        return stateWord(lang, statusStat(p));
      case "Online": {
        const on = p.isOn("printer_online");
        return on === undefined ? NO_VALUE : this.t(on ? "common.values.online" : "common.values.offline");
      }
      case "Availability": {
        const s = p.value("current_status");
        return s === undefined ? NO_VALUE : stateWord(lang, s);
      }
      case "Project":
        return this.plain("job_name");
      case "Layer":
        return this.plain("job_current_layer");
      case "ETA": {
        const eta = computeEta(p.value("job_eta"), this.ticking("job_time_remaining", -1));
        return formatClock(eta, c.use_24hr, c.round);
      }
      case "Elapsed":
        return formatDuration(this.ticking("job_time_elapsed", 1), c.round);
      case "Remaining":
        return formatDuration(this.ticking("job_time_remaining", -1), c.round);
      case "Hotend":
        return this.temp("curr_nozzle_temp");
      case "Bed":
        return this.temp("curr_hotbed_temp");
      case "T Hotend":
        return this.temp("target_nozzle_temp");
      case "T Bed":
        return this.temp("target_hotbed_temp");
      case "Speed Mode": {
        const modes = p.attr<{ mode: number; description: string }[]>("job_speed_mode", "available_modes");
        const code = p.attr<number>("job_speed_mode", "print_speed_mode_code");
        const hit = Array.isArray(modes) ? modes.find((m) => m.mode === code) : undefined;
        return hit?.description ?? p.value("job_speed_mode") ?? this.t("common.messages.unknown");
      }
      case "Fan Speed":
        return this.plain("fan_speed_pct", "%");
      case "Dry Status": {
        const on = p.isOn("dry_status_is_drying");
        return on === undefined ? NO_VALUE : this.t(on ? "common.values.drying" : "common.values.not_drying");
      }
      case "Dry Time": {
        const rem = p.num("dry_status_remaining_time");
        const pct = dryingRemainingPercent(rem, p.num("dry_status_total_duration"));
        if (rem === undefined) return NO_VALUE;
        return html`<span class="dry">
          <span>${Math.round(rem)} ${this.t("common.values.minutes")}</span>
          ${pct === undefined ? nothing : html`<span class="bar small"><span style="width:${pct}%"></span></span>`}
        </span>`;
      }
      case "On Time":
        return this.plain("job_on_time", " s");
      case "Off Time":
        return this.plain("job_off_time", " s");
      case "Bottom Time":
        return this.plain("job_bottom_time", " s");
      case "Model Height":
        return this.plain("job_model_height", " mm");
      case "Bottom Layers":
        return this.plain("job_bottom_layers", ` ${this.t("common.values.layers")}`);
      case "Z Up Height":
        return this.plain("job_z_up_height", " mm");
      case "Z Up Speed":
        return this.plain("job_z_up_speed");
      case "Z Down Speed":
        return this.plain("job_z_down_speed");
      default:
        return NO_VALUE;
    }
  }

  private renderStats() {
    const stats = this.config.monitoredStats ?? [];
    if (!stats.length) return nothing;
    return html`<dl class="stats">
      ${stats.map(
        (s) => html`<div class="stat">
          <dt>${this.t(`card.monitored_stats.${s}`)}</dt>
          <dd>${this.statValue(s)}</dd>
        </div>`,
      )}
    </dl>`;
  }

  private renderProgress() {
    const p = this.printer;
    const raw = p.num("job_progress");
    if (raw === undefined || raw < 0) return nothing;
    const pct = clampPercent(raw);
    const shown = this.config.round ? `${Math.round(pct)}%` : `${Number(pct.toFixed(2))}%`;
    const cur = p.value("job_current_layer");
    const total = p.value("job_total_layers");
    return html`<div class="progress">
      <div class="progress-line">
        <span class="pct">${shown}</span>
        ${cur !== undefined && total !== undefined
          ? html`<span class="muted">${this.t("card.progress.layer", { current: cur, total })}</span>`
          : nothing}
      </div>
      <div
        class="bar"
        role="progressbar"
        aria-valuemin="0"
        aria-valuemax="100"
        aria-valuenow=${Math.round(pct)}
      >
        <span style="width:${pct}%"></span>
      </div>
    </div>`;
  }

  // ---- header ------------------------------------------------------------

  private renderHeader(state: string, open: boolean) {
    const c = this.config;
    const light = c.lightEntityId ? this.hass?.states[c.lightEntityId] : undefined;
    const lightOn = light?.state === "on";
    return html`<div class="header">
      <button
        class="title"
        aria-expanded=${open ? "true" : "false"}
        title=${this.t("card.buttons.toggle_body")}
        @click=${() => (this.revealed = !this.revealed)}
      >
        <span class="dot"></span>
        <span class="names">
          <span class="name">${this.printer.name ?? this.t("card.fallback_name")}</span>
          <span class="state">${stateWord(this.hass?.language, state)}</span>
        </span>
      </button>
      ${c.lightEntityId
        ? html`<button
            class="icon-btn ${lightOn ? "on" : ""}"
            title=${this.t("card.buttons.light")}
            aria-label=${this.t("card.buttons.light")}
            aria-pressed=${lightOn ? "true" : "false"}
            ?disabled=${this.pending.has("light")}
            @click=${() => this.act("light", () => toggleEntity(this.hass!, c.lightEntityId))}
          >
            ${icon(lightOn ? mdiLightbulbOn : mdiLightbulbOutline)}
          </button>`
        : nothing}
      ${c.powerEntityId
        ? html`<button
            class="icon-btn"
            title=${this.t("card.buttons.power")}
            aria-label=${this.t("card.buttons.power")}
            ?disabled=${this.pending.has("power")}
            @click=${() => this.act("power", () => toggleEntity(this.hass!, c.powerEntityId))}
          >
            ${icon(mdiPower)}
          </button>`
        : nothing}
    </div>`;
  }

  // ---- controls and move pad --------------------------------------------

  private press(key: string) {
    return () => this.act(key, () => pressButton(this.hass!, this.printer, key));
  }

  private renderControls() {
    const p = this.printer;
    const printing = isPrinting(p);
    const paused = isPaused(p);
    const settings = printing || this.config.showSettingsButton;
    if (!printing && !settings) return nothing;
    return html`<div class="controls">
      ${printing
        ? html`${paused
              ? html`<button class="btn" ?disabled=${!p.usable("resume_print", "button") || this.pending.has("resume_print")} @click=${this.press("resume_print")}>
                  ${icon(mdiPlay, 18)} ${this.t("card.controls.resume")}
                </button>`
              : html`<button class="btn" ?disabled=${!p.usable("pause_print", "button") || this.pending.has("pause_print")} @click=${this.press("pause_print")}>
                  ${icon(mdiPause, 18)} ${this.t("card.controls.pause")}
                </button>`}
            <button
              class="btn danger"
              ?disabled=${!p.usable("cancel_print", "button") || this.pending.has("cancel_print")}
              @click=${() => (this.dialog = { kind: "cancel" })}
            >
              ${icon(mdiStop, 18)} ${this.t("card.controls.cancel")}
            </button>`
        : nothing}
      ${settings
        ? html`<button class="btn" @click=${() => (this.dialog = { kind: "settings" })}>
            ${icon(mdiCog, 18)} ${this.t("card.buttons.print_settings")}
          </button>`
        : nothing}
    </div>`;
  }

  private moveBtn(key: string, label: string, content: TemplateResult | string, cls = "") {
    const p = this.printer;
    return html`<button
      class="pad-btn ${cls}"
      title=${label}
      aria-label=${label}
      ?disabled=${!p.usable(key, "button") || this.pending.has(key)}
      @click=${this.press(key)}
    >
      ${content}
    </button>`;
  }

  private renderMovePad() {
    const p = this.printer;
    const m = (k: string) => this.t(`card.move.${k}`);
    const step = p.entity("axis_step", "select");
    const options = step && step.state !== "unavailable" ? (step.attributes.options ?? []) : [];
    const moving = p.isOn("axis_moving") === true;
    const failed = p.isOn("axis_move_failed") === true;
    return html`<div class="move">
      ${options.length
        ? html`<div class="steps" role="group" aria-label=${m("step")}>
            ${options.map(
              (o) => html`<button
                class="chip ${o === step?.state ? "selected" : ""}"
                aria-pressed=${o === step?.state ? "true" : "false"}
                ?disabled=${this.pending.has("axis_step")}
                @click=${() => this.act("axis_step", () => selectOption(this.hass!, p, "axis_step", o))}
              >
                ${o}
              </button>`,
            )}
          </div>`
        : nothing}
      <div class="pad">
        <div class="pad-col">
          ${this.moveBtn("axis_home_all", m("home_all"), icon(mdiHome))}
          ${this.moveBtn("axis_motors_off", m("motors_off"), icon(mdiEngineOff))}
        </div>
        <div class="dial">
          ${this.moveBtn("axis_move_y_plus", "Y+", html`${icon(mdiArrowUp, 18)}<small>Y+</small>`, "q top")}
          ${this.moveBtn("axis_move_x_minus", m("x_minus"), html`${icon(mdiArrowLeft, 18)}<small>X−</small>`, "q left")}
          ${this.moveBtn("axis_move_x_plus", m("x_plus"), html`<small>X+</small>${icon(mdiArrowRight, 18)}`, "q right")}
          ${this.moveBtn("axis_move_y_minus", m("y_minus"), html`<small>Y−</small>${icon(mdiArrowDown, 18)}`, "q bottom")}
          ${this.moveBtn("axis_home_xy", m("home_xy"), html`${icon(mdiHomeOutline, 18)}<small>XY</small>`, "centre")}
        </div>
        <div class="pad-col">
          ${this.moveBtn("axis_move_z_plus", m("z_plus"), html`${icon(mdiArrowUp, 18)}<small>Z</small>`)}
          ${this.moveBtn("axis_home_z", m("home_z"), html`${icon(mdiHomeOutline, 18)}<small>Z</small>`, "accent")}
          ${this.moveBtn("axis_move_z_minus", m("z_minus"), html`${icon(mdiArrowDown, 18)}<small>Z</small>`)}
        </div>
      </div>
      ${moving
        ? html`<p class="note" role="status">${m("moving")}</p>`
        : failed
          ? html`<p class="warn" role="status">${icon(mdiAlert, 18)} ${m("failed")}</p>`
          : nothing}
    </div>`;
  }

  // ---- sections ----------------------------------------------------------

  private renderAceStrip(unit: 0 | 1) {
    const p = this.printer;
    const data = aceUnit(p, unit);
    const refillKey = unit === 0 ? "multi_color_box_runout_refill" : "secondary_multi_color_box_runout_refill";
    const refill = p.entity(refillKey, "switch");
    const refillOn = refill?.state === "on";
    return html`<div class="ace">
      ${refill
        ? html`<button
            class="refill ${refillOn ? "on" : ""}"
            role="switch"
            aria-checked=${refillOn ? "true" : "false"}
            ?disabled=${refill.state === "unavailable" || this.pending.has(refillKey)}
            @click=${() => this.act(refillKey, () => toggleSwitch(this.hass!, p, refillKey))}
          >
            <span>${this.t("card.buttons.runout_refill")}</span>
            <span class="toggle"><span></span></span>
          </button>`
        : nothing}
      <div class="spools">
        ${data.slots.map(
          (s) => html`<button
            class="spool ${data.loadedSlot === s.slot ? "feeding" : ""}"
            title=${`${s.slot}: ${s.material ?? "---"}`}
            @click=${() => (this.dialog = { kind: "spool", unit, slot: s })}
          >
            <span class="ring" style="background:${s.loaded && s.colour ? s.colour : "#9e9e9e"}"><span>${s.slot}</span></span>
            <span class="material">${s.loaded ? (s.material ?? "---") : "---"}</span>
          </button>`,
        )}
      </div>
      <button class="btn dry" @click=${() => (this.dialog = { kind: "drying", unit })}>
        ${icon(mdiRadiator, 18)} ${this.t("card.buttons.dry")}
      </button>
    </div>`;
  }

  private renderInsights() {
    const p = this.printer;
    const lang = this.hass?.language ?? "en";
    const cur = this.hass?.config?.currency;
    const rows: [string, string][] = [];
    const money = (k: string) => {
      const v = p.num(k);
      if (v !== undefined) rows.push([k, formatMoney(v, lang, cur)]);
    };
    const grams = (k: string) => {
      const v = p.num(k);
      if (v !== undefined) rows.push([k, formatGrams(v)]);
    };
    money("job_cost");
    money("last_job_cost");
    money("filament_cost_total");
    grams("job_filament_required");
    grams("job_filament_shortfall");
    const wear = p.num("nozzle_wear_percent");
    if (wear !== undefined) rows.push(["nozzle_wear_percent", formatPercent(wear, 1)]);
    grams("spool_inventory_remaining");
    const short = p.isOn("job_filament_insufficient") === true;
    return html`${short ? html`<p class="warn">${icon(mdiAlert, 18)} ${this.t("card.insights.insufficient")}</p>` : nothing}
    ${rows.length
      ? html`<div class="insights">
          ${rows.map(
            ([k, v]) => html`<div class="tile">
              <span class="muted">${this.t(`card.insights.${k}`)}</span><strong>${v}</strong>
            </div>`,
          )}
        </div>`
      : html`<p class="note">${this.t("card.insights.empty")}</p>`}`;
  }

  private renderSections() {
    const p = this.printer;
    const list: { id: "filament" | "insights"; body: () => unknown }[] = [];
    if (this.config.sections.includes("filament") && p.aceActive(0)) {
      list.push({
        id: "filament",
        body: () => html`${this.renderAceStrip(0)}${p.aceActive(1) ? this.renderAceStrip(1) : nothing}`,
      });
    }
    if (this.config.sections.includes("insights")) list.push({ id: "insights", body: () => this.renderInsights() });
    if (!list.length) return nothing;
    return html`<div class="sections">
      ${list.map((s) => {
        const open = this.openSection === s.id;
        return html`<section class=${open ? "open" : ""}>
          <button
            class="section-head"
            aria-expanded=${open ? "true" : "false"}
            @click=${() => (this.openSection = open ? undefined : s.id)}
          >
            <span>${this.t(`card.sections.${s.id}`)}</span>${icon(mdiChevronDown, 20)}
          </button>
          ${open ? html`<div class="section-body">${s.body()}</div>` : nothing}
        </section>`;
      })}
    </div>`;
  }

  // ---- dialogs -----------------------------------------------------------

  private closeDialog = () => {
    this.dialog = undefined;
  };

  private renderDialogs() {
    const d = this.dialog;
    return html`
      <anycubic-print-settings
        .hass=${this.hass}
        .printer=${this.printer}
        .open=${d?.kind === "settings"}
        @dialog-closed=${this.closeDialog}
      ></anycubic-print-settings>
      <anycubic-spool-editor
        .hass=${this.hass}
        .printer=${this.printer}
        .open=${d?.kind === "spool"}
        .unit=${d?.kind === "spool" ? d.unit : 0}
        .spool=${d?.kind === "spool" ? d.slot : undefined}
        .presets=${this.config.slotColors}
        @dialog-closed=${this.closeDialog}
      ></anycubic-spool-editor>
      <anycubic-drying
        .hass=${this.hass}
        .printer=${this.printer}
        .open=${d?.kind === "drying"}
        .unit=${d?.kind === "drying" ? d.unit : 0}
        @dialog-closed=${this.closeDialog}
      ></anycubic-drying>
      <anycubic-confirm
        .hass=${this.hass}
        .open=${d?.kind === "cancel"}
        .heading=${this.t("card.print_settings.confirm_heading")}
        .message=${this.t("card.controls.confirm_cancel")}
        @dialog-closed=${this.closeDialog}
        @confirmed=${() => {
          this.dialog = undefined;
          this.press("cancel_print")();
        }}
      ></anycubic-confirm>
    `;
  }

  // ---- render ------------------------------------------------------------

  protected override render() {
    const c = this.config;
    const p = this.printer;
    const state = printState(p);
    const printing = isPrinting(p);
    const open = c.alwaysShow || printing || this.revealed;
    const showHero = c.mediaView !== "none";
    return html`<ha-card class="cat-${statusCategory(state)}">
      <div class="wrap" style="--hero-fr:${c.scaleFactor}fr">
        ${this.renderHeader(state, open)}
        <div class="body ${open ? "open" : ""}" ?inert=${!open} aria-hidden=${open ? "false" : "true"}>
          <div class="body-inner">
            <div class="main ${c.vertical ? "vertical" : ""} ${showHero ? "" : "no-hero"}">
              ${showHero
                ? html`<anycubic-hero .hass=${this.hass} .printer=${p} .config=${c} .preview=${this.preview}></anycubic-hero>`
                : nothing}
              <div class="summary">${this.renderProgress()} ${this.renderStats()}</div>
            </div>
            ${c.showControls ? this.renderControls() : nothing} ${c.showMoveButtons ? this.renderMovePad() : nothing}
            ${this.renderSections()}
          </div>
        </div>
      </div>
      ${this.renderDialogs()}
    </ha-card>`;
  }

  static override styles = [
    sharedStyles,
    css`
      :host {
        display: block;
      }
      ha-card {
        display: block;
        height: 100%;
        overflow: hidden;
        --ac-status: var(--ac-problem);
      }
      ha-card.cat-activity {
        --ac-status: var(--ac-activity);
      }
      ha-card.cat-printing {
        --ac-status: var(--ac-printing);
      }
      ha-card.cat-healthy {
        --ac-status: var(--ac-healthy);
      }
      .wrap {
        container-type: inline-size;
        padding: 8px 16px 16px;
      }
      .header {
        display: flex;
        align-items: center;
        gap: 4px;
      }
      .title {
        flex: 1;
        min-width: 0;
        display: flex;
        align-items: center;
        gap: 12px;
        padding: 6px 0;
        background: none;
        border: none;
        text-align: left;
        cursor: pointer;
      }
      .dot {
        width: 12px;
        height: 12px;
        flex: none;
        border-radius: 50%;
        background: var(--ac-status);
        box-shadow: 0 0 0 3px color-mix(in srgb, var(--ac-status) 25%, transparent);
      }
      .names {
        display: flex;
        flex-direction: column;
        min-width: 0;
      }
      .name {
        font-size: 18px;
        font-weight: 500;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }
      .state {
        font-size: 13px;
        color: var(--ac-muted);
      }
      .body {
        display: grid;
        grid-template-rows: 0fr;
        opacity: 0;
        transition: grid-template-rows 250ms ease, opacity 250ms ease;
        pointer-events: none;
      }
      .body.open {
        grid-template-rows: 1fr;
        opacity: 1;
        pointer-events: auto;
      }
      .body-inner {
        min-height: 0;
        overflow: hidden;
      }
      @media (prefers-reduced-motion: reduce) {
        .body,
        .bar span {
          transition: none;
        }
      }
      .main {
        display: grid;
        gap: 16px;
        padding-top: 8px;
      }
      @container (min-width: 480px) {
        .main:not(.vertical):not(.no-hero) {
          grid-template-columns: var(--hero-fr) 1fr;
          align-items: center;
        }
      }
      .summary {
        min-width: 0;
      }
      .progress {
        margin-bottom: 8px;
      }
      .progress-line {
        display: flex;
        justify-content: space-between;
        align-items: baseline;
        gap: 8px;
        margin-bottom: 4px;
      }
      .pct {
        font-size: 22px;
        font-weight: 600;
      }
      .bar {
        height: 8px;
        border-radius: 4px;
        background: var(--ac-surface-2);
        overflow: hidden;
      }
      .bar span {
        display: block;
        height: 100%;
        background: var(--ac-status);
        border-radius: inherit;
        transition: width 600ms ease;
      }
      .bar.small {
        height: 5px;
        width: 100%;
        margin-top: 3px;
      }
      .bar.small span {
        background: var(--ac-accent);
      }
      .dry {
        display: inline-flex;
        flex-direction: column;
        align-items: flex-end;
        min-width: 80px;
      }
      .stats {
        margin: 0;
        display: flex;
        flex-direction: column;
        gap: 4px;
      }
      .stat {
        display: flex;
        justify-content: space-between;
        gap: 12px;
        padding: 3px 0;
        border-bottom: 1px solid color-mix(in srgb, var(--ac-divider) 60%, transparent);
      }
      .stat:last-child {
        border-bottom: none;
      }
      dt {
        font-weight: 600;
      }
      dd {
        margin: 0;
        text-align: right;
        overflow-wrap: anywhere;
      }
      .controls {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        margin-top: 16px;
      }
      .move {
        margin-top: 16px;
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 12px;
      }
      .steps {
        display: flex;
        gap: 6px;
        flex-wrap: wrap;
        justify-content: center;
      }
      .pad {
        display: flex;
        align-items: center;
        gap: 16px;
      }
      .pad-col {
        display: flex;
        flex-direction: column;
        gap: 8px;
      }
      .pad-btn {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 2px;
        width: 48px;
        height: 44px;
        border-radius: 12px;
        border: 1px solid var(--ac-divider);
        background: var(--ac-surface-2);
        cursor: pointer;
        flex-direction: column;
        font-size: 11px;
      }
      .pad-btn small {
        font-size: 11px;
        line-height: 1;
      }
      .pad-btn.accent {
        background: var(--ac-accent);
        color: var(--text-primary-color, #fff);
        border-color: transparent;
      }
      .pad-btn[disabled] {
        opacity: 0.4;
        cursor: default;
      }
      .dial {
        position: relative;
        width: 168px;
        height: 168px;
        border-radius: 50%;
        background: var(--ac-surface-2);
        border: 1px solid var(--ac-divider);
      }
      .dial .pad-btn {
        position: absolute;
        background: transparent;
        border: none;
      }
      .dial .q.top {
        top: 6px;
        left: calc(50% - 24px);
      }
      .dial .q.bottom {
        bottom: 6px;
        left: calc(50% - 24px);
      }
      .dial .q.left {
        left: 6px;
        top: calc(50% - 22px);
        flex-direction: row;
      }
      .dial .q.right {
        right: 6px;
        top: calc(50% - 22px);
        flex-direction: row;
      }
      .dial .centre {
        top: calc(50% - 26px);
        left: calc(50% - 26px);
        width: 52px;
        height: 52px;
        border-radius: 50%;
        background: var(--ac-surface);
        border: 1px solid var(--ac-divider);
      }
      .dial .pad-btn:hover:not([disabled]) {
        color: var(--ac-accent);
      }
      @container (max-width: 360px) {
        .pad {
          gap: 8px;
        }
        .dial {
          width: 144px;
          height: 144px;
        }
        .pad-btn {
          width: 42px;
        }
      }
      .sections {
        margin-top: 16px;
        display: flex;
        flex-direction: column;
        gap: 8px;
      }
      section {
        border: 1px solid var(--ac-divider);
        border-radius: 10px;
        overflow: hidden;
      }
      .section-head {
        width: 100%;
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 10px 12px;
        background: none;
        border: none;
        cursor: pointer;
        font-weight: 500;
      }
      .section-head .mdi {
        transition: transform 200ms ease;
      }
      section.open .section-head .mdi {
        transform: rotate(180deg);
      }
      .section-body {
        padding: 0 12px 12px;
      }
      .ace {
        display: flex;
        align-items: center;
        gap: 12px;
        flex-wrap: wrap;
        padding: 8px 0;
      }
      .ace + .ace {
        border-top: 1px solid var(--ac-divider);
      }
      .refill {
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 6px;
        font-size: 12px;
        background: none;
        border: 1px solid var(--ac-divider);
        border-radius: 10px;
        padding: 8px;
        cursor: pointer;
      }
      .toggle {
        width: 34px;
        height: 18px;
        border-radius: 9px;
        background: var(--ac-divider);
        position: relative;
      }
      .toggle span {
        position: absolute;
        top: 2px;
        left: 2px;
        width: 14px;
        height: 14px;
        border-radius: 50%;
        background: #fff;
        transition: left 150ms ease;
      }
      .refill.on .toggle {
        background: var(--ac-accent);
      }
      .refill.on .toggle span {
        left: 18px;
      }
      .spools {
        flex: 1;
        display: flex;
        justify-content: space-around;
        gap: 6px;
        min-width: 0;
      }
      .spool {
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 4px;
        background: none;
        border: none;
        cursor: pointer;
        padding: 2px;
      }
      .ring {
        width: 44px;
        height: 44px;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        box-shadow: inset 0 0 0 1px rgba(0, 0, 0, 0.2);
      }
      .spool.feeding .ring {
        outline: 3px solid var(--ac-accent);
        outline-offset: 2px;
      }
      .ring span {
        width: 20px;
        height: 20px;
        border-radius: 50%;
        background: rgba(255, 255, 255, 0.9);
        color: #111;
        font-size: 11px;
        font-weight: 600;
        display: flex;
        align-items: center;
        justify-content: center;
      }
      .material {
        font-size: 12px;
      }
      .insights {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(130px, 1fr));
        gap: 8px;
      }
      .tile {
        display: flex;
        flex-direction: column;
        gap: 2px;
        padding: 8px 10px;
        border-radius: 8px;
        background: var(--ac-surface-2);
        font-size: 13px;
      }
      .tile strong {
        font-size: 16px;
      }
    `,
  ];
}

defineOnce("anycubic-card", AnycubicCard);
