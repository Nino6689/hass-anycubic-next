// The card's dialogs (FRONTEND.md §4.11): print settings, spool editor, drying,
// and a plain confirmation.

import { LitElement, css, html, nothing, type PropertyValues } from "lit";
import { defineOnce, fire } from "../ha/dom";
import type { HomeAssistant } from "../ha/types";
import { SPOOL_MATERIALS, callAction, pressButton, setSlotService } from "../lib/actions";
import type { AceSlot } from "../lib/ace";
import { hexToRgb, normaliseColour, rgbToHex, spoolRgb } from "../lib/colour";
import type { Printer } from "../lib/entities";
import { isPaused, isPrinting } from "../lib/state";
import { localize } from "../localize";
import "../ui/dialog";
import { sharedStyles } from "../ui/styles";

const dialogStyles = css`
  .row {
    display: flex;
    flex-wrap: wrap;
    align-items: end;
    gap: 8px;
    margin: 12px 0;
  }
  .row label {
    display: flex;
    flex-direction: column;
    gap: 4px;
    flex: 1 1 160px;
    font-size: 13px;
    color: var(--ac-muted);
  }
  .buttons {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin: 8px 0 4px;
  }
  .stack {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .swatches {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }
  .swatch {
    width: 32px;
    height: 32px;
    border-radius: 50%;
    border: 2px solid var(--ac-divider);
    cursor: pointer;
    padding: 0;
  }
  input[type="color"] {
    width: 64px;
    height: 40px;
    padding: 2px;
  }
  p {
    margin: 8px 0;
  }
`;

abstract class CardDialog extends LitElement {
  static override properties = {
    hass: { attribute: false },
    printer: { attribute: false },
    open: { type: Boolean },
    busy: { state: true },
  };

  hass?: HomeAssistant;
  printer?: Printer;
  open = false;
  protected busy = false;

  static override styles = [sharedStyles, dialogStyles];

  protected t(key: string, vars?: Record<string, string | number>): string {
    return localize(this.hass?.language, key, vars);
  }

  protected close(): void {
    fire(this, "dialog-closed");
  }

  /** Run a call with controls disabled; close afterwards unless told not to. */
  protected async run(work: () => Promise<void>, closeAfter = true): Promise<void> {
    if (this.busy) return;
    this.busy = true;
    try {
      await work();
      if (closeAfter) this.close();
    } catch (err) {
      console.error("anycubic-card:", err);
    } finally {
      this.busy = false;
    }
  }
}

/** Yes/No confirmation. Fires `confirmed` on Yes; `dialog-closed` on No. */
export class AnycubicConfirm extends LitElement {
  static override properties = {
    hass: { attribute: false },
    open: { type: Boolean },
    heading: { type: String },
    message: { type: String },
  };

  hass?: HomeAssistant;
  open = false;
  heading = "";
  message = "";

  static override styles = [sharedStyles, dialogStyles];

  protected override render() {
    const t = (k: string) => localize(this.hass?.language, k);
    return html`<anycubic-dialog .open=${this.open} .heading=${this.heading} .closeLabel=${t("common.actions.close")}>
      <p>${this.message}</p>
      <div class="buttons">
        <button class="btn danger" @click=${() => fire(this, "confirmed")}>${t("common.actions.yes")}</button>
        <button class="btn" @click=${() => fire(this, "dialog-closed")}>${t("common.actions.no")}</button>
      </div>
    </anycubic-dialog>`;
  }
}

type Field = "speed" | "nozzle" | "bed" | "fan";
type Verb = "pause" | "resume" | "cancel";

export class AnycubicPrintSettings extends CardDialog {
  static override properties = {
    ...CardDialog.properties,
    confirm: { state: true },
    edits: { state: true },
  };

  private confirm?: Verb;
  private edits: Partial<Record<Field, string>> = {};

  protected override willUpdate(changed: PropertyValues): void {
    if (changed.has("open") && this.open) {
      this.confirm = undefined;
      this.edits = {};
    }
  }

  private live(field: Field): string {
    const p = this.printer;
    if (!p) return "";
    switch (field) {
      case "speed": {
        const code = p.attr<number>("job_speed_mode", "print_speed_mode_code");
        return code === undefined || code === null ? "" : String(code);
      }
      case "nozzle":
        return p.value("target_nozzle_temp") ?? "";
      case "bed":
        return p.value("target_hotbed_temp") ?? "";
      case "fan":
        return p.value("fan_speed_pct") ?? "";
    }
  }

  private val(field: Field): string {
    return this.edits[field] ?? this.live(field);
  }

  private edit(field: Field, value: string) {
    this.edits = { ...this.edits, [field]: value };
  }

  private save(field: Field) {
    const hass = this.hass;
    const p = this.printer;
    const n = Number(this.val(field));
    if (!hass || !p || this.val(field) === "" || !Number.isFinite(n)) return;
    const calls: Record<Field, [string, Record<string, unknown>]> = {
      speed: ["change_print_speed_mode", { speed_mode: Math.round(n) }],
      nozzle: ["change_print_target_nozzle_temperature", { temperature: Math.round(n) }],
      bed: ["change_print_target_hotbed_temperature", { temperature: Math.round(n) }],
      fan: ["change_print_fan_speed", { speed: Math.round(n) }],
    };
    const [service, data] = calls[field];
    this.run(() => callAction(hass, p, service, data));
  }

  private numberRow(field: Exclude<Field, "speed">, labelKey: string, saveKey: string, min?: number, max?: number) {
    return html`<div class="row">
      <label
        >${this.t(`card.print_settings.${labelKey}`)}
        <input
          type="number"
          inputmode="numeric"
          .value=${this.val(field)}
          min=${min ?? nothing}
          max=${max ?? nothing}
          ?disabled=${this.busy}
          @input=${(e: Event) => this.edit(field, (e.target as HTMLInputElement).value)}
          @keydown=${(e: KeyboardEvent) => e.key === "Enter" && this.save(field)}
      /></label>
      <button class="btn" ?disabled=${this.busy} @click=${() => this.save(field)}>${this.t(`card.print_settings.${saveKey}`)}</button>
    </div>`;
  }

  private renderConfirm(verb: Verb) {
    const action = this.t(`common.actions.${verb}`);
    return html`<p>${this.t("card.print_settings.confirm_message", { action })}</p>
      <div class="buttons">
        <button
          class="btn danger"
          ?disabled=${this.busy}
          @click=${() => this.run(() => pressButton(this.hass!, this.printer!, `${verb}_print`))}
        >
          ${this.t("common.actions.yes")}
        </button>
        <button class="btn" ?disabled=${this.busy} @click=${() => (this.confirm = undefined)}>${this.t("common.actions.no")}</button>
      </div>`;
  }

  private renderSettings() {
    const p = this.printer;
    if (!p) return nothing;
    const modes = p.attr<{ mode: number; description: string }[]>("job_speed_mode", "available_modes");
    const printing = isPrinting(p);
    const paused = isPaused(p);
    const nozzleMin = p.attr<number>("target_nozzle_temp", "limit_min");
    const nozzleMax = p.attr<number>("target_nozzle_temp", "limit_max");
    const bedMin = p.attr<number>("target_hotbed_temp", "limit_min");
    const bedMax = p.attr<number>("target_hotbed_temp", "limit_max");
    return html`<div class="buttons">
        <button class="btn" ?disabled=${!p.usable("pause_print", "button") || !printing || paused} @click=${() => (this.confirm = "pause")}>
          ${this.t("card.print_settings.print_pause")}
        </button>
        <button class="btn" ?disabled=${!p.usable("resume_print", "button") || !paused} @click=${() => (this.confirm = "resume")}>
          ${this.t("card.print_settings.print_resume")}
        </button>
        <button class="btn danger" ?disabled=${!p.usable("cancel_print", "button") || !printing} @click=${() => (this.confirm = "cancel")}>
          ${this.t("card.print_settings.print_cancel")}
        </button>
      </div>
      ${p.isFilament
        ? html`${Array.isArray(modes) && modes.length
            ? html`<div class="row">
                <label
                  >${this.t("card.print_settings.label_speed_mode")}
                  <select
                    .value=${this.val("speed")}
                    ?disabled=${this.busy}
                    @change=${(e: Event) => this.edit("speed", (e.target as HTMLSelectElement).value)}
                  >
                    ${modes.map(
                      (m) => html`<option value=${String(m.mode)} ?selected=${String(m.mode) === this.val("speed")}>${m.description}</option>`,
                    )}
                  </select></label
                >
                <button class="btn" ?disabled=${this.busy} @click=${() => this.save("speed")}>
                  ${this.t("card.print_settings.save_speed_mode")}
                </button>
              </div>`
            : nothing}
          ${this.numberRow("nozzle", "label_nozzle_temp", "save_target_nozzle", nozzleMin, nozzleMax)}
          ${this.numberRow("bed", "label_hotbed_temp", "save_target_hotbed", bedMin, bedMax)}
          ${this.numberRow("fan", "label_fan_speed", "save_fan_speed", 0, 100)}`
        : nothing}`;
  }

  protected override render() {
    const heading = this.confirm ? this.t("card.print_settings.confirm_heading") : this.t("card.print_settings.heading");
    return html`<anycubic-dialog .open=${this.open} .heading=${heading} .closeLabel=${this.t("common.actions.close")}>
      ${this.confirm ? this.renderConfirm(this.confirm) : this.renderSettings()}
    </anycubic-dialog>`;
  }
}

export class AnycubicSpoolEditor extends CardDialog {
  static override properties = {
    ...CardDialog.properties,
    unit: { type: Number },
    spool: { attribute: false },
    presets: { attribute: false },
    material: { state: true },
    colour: { state: true },
  };

  unit: 0 | 1 = 0;
  spool?: AceSlot;
  presets: string[] = [];
  private material = "";
  private colour = "#ffffff";

  protected override willUpdate(changed: PropertyValues): void {
    if ((changed.has("open") || changed.has("spool")) && this.open && this.spool) {
      const m = this.spool.material?.toUpperCase().replace(/\s+/g, "_");
      this.material = m && (SPOOL_MATERIALS as readonly string[]).includes(m) ? m : "";
      const rgb = spoolRgb(this.spool.raw);
      this.colour = rgb ? rgbToHex(rgb) : "#ffffff";
    }
  }

  private save() {
    const rgb = hexToRgb(this.colour);
    if (!this.material || !rgb || !this.spool || !this.hass || !this.printer) return;
    const [r, g, b] = rgb;
    this.run(() =>
      callAction(this.hass!, this.printer!, setSlotService(this.material), {
        box_id: this.unit,
        slot_number: this.spool!.slot,
        slot_color_red: r,
        slot_color_green: g,
        slot_color_blue: b,
      }),
    );
  }

  protected override render() {
    const presets = this.presets
      .map((c) => ({ raw: c, css: normaliseColour(c) }))
      .filter((c): c is { raw: string; css: string } => !!c.css);
    return html`<anycubic-dialog
      .open=${this.open}
      .heading=${this.t("card.spool_settings.heading", { slot: this.spool?.slot ?? "" })}
      .closeLabel=${this.t("common.actions.close")}
    >
      <div class="row">
        <label
          >${this.t("card.spool_settings.label_select_material")}
          <select .value=${this.material} @change=${(e: Event) => (this.material = (e.target as HTMLSelectElement).value)}>
            <option value="" ?selected=${!this.material} disabled>${this.t("card.spool_settings.placeholder_material")} (PLA)</option>
            ${SPOOL_MATERIALS.map((m) => html`<option value=${m} ?selected=${m === this.material}>${m.replace("_", " ")}</option>`)}
          </select></label
        >
      </div>
      ${presets.length
        ? html`<p class="muted">${this.t("card.spool_settings.label_preset_colours")}</p>
            <div class="swatches">
              ${presets.map(
                (c) => html`<button
                  class="swatch"
                  style="background:${c.css}"
                  title=${c.raw}
                  aria-label=${c.raw}
                  @click=${() => {
                    const hex = c.css.startsWith("#") ? c.css : undefined;
                    if (hex) this.colour = hex;
                    else this.colour = cssToHex(c.css) ?? this.colour;
                  }}
                ></button>`,
              )}
            </div>`
        : nothing}
      <div class="row">
        <label
          >${this.t("card.spool_settings.label_select_colour")}
          <input type="color" .value=${this.colour} @input=${(e: Event) => (this.colour = (e.target as HTMLInputElement).value)}
        /></label>
      </div>
      <div class="buttons">
        <button class="btn primary" ?disabled=${this.busy || !this.material} @click=${this.save}>${this.t("common.actions.save")}</button>
      </div>
    </anycubic-dialog>`;
  }
}

/** Resolve any CSS colour to #rrggbb using the browser. */
function cssToHex(colour: string): string | undefined {
  if (typeof document === "undefined") return undefined;
  const el = document.createElement("canvas").getContext("2d");
  if (!el) return undefined;
  el.fillStyle = "#000000";
  el.fillStyle = colour;
  const out = el.fillStyle;
  return typeof out === "string" && out.startsWith("#") ? out : undefined;
}

export class AnycubicDrying extends CardDialog {
  static override properties = {
    ...CardDialog.properties,
    unit: { type: Number },
  };

  unit: 0 | 1 = 0;

  protected override render() {
    const p = this.printer;
    const prefix = this.unit === 1 ? "secondary_" : "";
    const positive = (v: unknown) => typeof v === "number" && Number.isFinite(v) && v > 0;
    // A preset exists only with both a duration and a temperature (§4.11).
    const presets = [1, 2, 3, 4]
      .map((n) => {
        const key = `${prefix}drying_start_preset_${n}`;
        return { n, key, duration: p?.attr<number>(key, "duration", "button"), temp: p?.attr<number>(key, "temperature", "button") };
      })
      .filter(({ key, duration, temp }) => p?.usable(key, "button") && positive(duration) && positive(temp));
    const stopKey = `${prefix}drying_stop`;
    return html`<anycubic-dialog
      .open=${this.open}
      .heading=${this.t("card.drying_settings.heading")}
      .closeLabel=${this.t("common.actions.close")}
    >
      <div class="stack">
        ${presets.map(({ n, key, duration, temp }) => {
          return html`<button class="btn" ?disabled=${this.busy} @click=${() => this.run(() => pressButton(this.hass!, p!, key))}>
            ${this.t("card.drying_settings.button_preset", { number: n })} — ${duration}
            ${this.t("card.drying_settings.button_minutes")} @ ${temp}°C
          </button>`;
        })}
        ${p?.id(stopKey, "button")
          ? html`<button class="btn danger" ?disabled=${this.busy} @click=${() => this.run(() => pressButton(this.hass!, p!, stopKey))}>
              ${this.t("card.drying_settings.button_stop_drying")}
            </button>`
          : nothing}
      </div>
    </anycubic-dialog>`;
  }
}

defineOnce("anycubic-confirm", AnycubicConfirm);
defineOnce("anycubic-print-settings", AnycubicPrintSettings);
defineOnce("anycubic-spool-editor", AnycubicSpoolEditor);
defineOnce("anycubic-drying", AnycubicDrying);
