// Panel print pages (FRONTEND.md §4.17). Instead of loading Home Assistant's
// developer-tools action form, this page uploads the file through Home
// Assistant's file-upload endpoint (the one the file selector uses) and calls
// the action with the returned file id.

import { LitElement, css, html, nothing } from "lit";
import { mdiPlay } from "@mdi/js";
import { defineOnce, haptic } from "../ha/dom";
import type { HomeAssistant } from "../ha/types";
import { callAction } from "../lib/actions";
import { Printer } from "../lib/entities";
import { localize } from "../localize";
import { icon } from "../ui/icon";
import { sharedStyles } from "../ui/styles";

export type PrintMode = "no_cloud_save" | "save_in_cloud";

export const ACCEPT = ".gcode,.pwsp,.pwsq,.zip";

/** `"1, 2 5"` → `[1, 2, 5]`; undefined for bad input, `[]` for empty. */
export function parseSlots(text: string): number[] | undefined {
  const parts = text.split(/[\s,;]+/).filter((s) => s !== "");
  const nums = parts.map(Number);
  if (nums.some((n) => !Number.isInteger(n) || n < 1)) return undefined;
  return nums;
}

export class AnycubicPrintPage extends LitElement {
  static override properties = {
    hass: { attribute: false },
    deviceId: { type: String },
    mode: { type: String },
    file: { state: true },
    slots: { state: true },
    status: { state: true },
    error: { state: true },
  };

  hass?: HomeAssistant;
  deviceId?: string;
  mode: PrintMode = "no_cloud_save";
  private file?: File;
  private slots = "";
  private status: "idle" | "working" | "done" | "failed" = "idle";
  private error?: string;

  private t(key: string): string {
    return localize(this.hass?.language, key);
  }

  private edited() {
    this.error = undefined;
    if (this.status !== "working") this.status = "idle";
  }

  private async upload(file: File): Promise<string> {
    const hass = this.hass!;
    if (!hass.fetchWithAuth) throw new Error("File upload is not available");
    const body = new FormData();
    body.append("file", file);
    const resp = await hass.fetchWithAuth("/api/file_upload", { method: "POST", body });
    if (!resp.ok) throw new Error(`${resp.status} ${resp.statusText}`);
    const json = (await resp.json()) as { file_id?: string };
    if (!json.file_id) throw new Error("Upload returned no file id");
    return json.file_id;
  }

  private async print(p: Printer, needsSlots: boolean) {
    haptic("light");
    if (!this.file) {
      this.error = this.t("panels.print.no_file");
      return;
    }
    const slots = parseSlots(this.slots);
    if (needsSlots && slots === undefined) {
      this.error = this.t("panels.print.slots_invalid");
      return;
    }
    this.status = "working";
    this.error = undefined;
    try {
      const fileId = await this.upload(this.file);
      const data: Record<string, unknown> = { uploaded_gcode_file: fileId };
      if (needsSlots && slots && slots.length) data.slot_number = slots;
      await callAction(this.hass!, p, `print_and_upload_${this.mode}`, data);
      this.status = "done";
      haptic("success");
    } catch (err) {
      this.status = "failed";
      this.error = err instanceof Error ? err.message : String((err as { message?: string })?.message ?? err);
      haptic("failure");
    }
  }

  protected override render() {
    const p = new Printer(this.hass, this.deviceId);
    const needsSlots = p.aceActive(0);
    const working = this.status === "working";
    return html`<ha-card>
      <label class="field">
        <span>${this.t("panels.print.file")}</span>
        <input
          type="file"
          accept=${ACCEPT}
          ?disabled=${working}
          @change=${(e: Event) => {
            this.file = (e.target as HTMLInputElement).files?.[0];
            this.edited();
          }}
        />
      </label>
      ${needsSlots
        ? html`<label class="field">
            <span>${this.t("panels.print.slots")}</span>
            <input
              .value=${this.slots}
              inputmode="numeric"
              placeholder="1, 2"
              ?disabled=${working}
              @input=${(e: Event) => {
                this.slots = (e.target as HTMLInputElement).value;
                this.edited();
              }}
            />
          </label>`
        : nothing}
      ${this.error ? html`<div class="alert" role="alert">${this.error}</div>` : nothing}
      ${this.status === "done" ? html`<p class="ok" role="status">${this.t("panels.print.started")}</p>` : nothing}
      <div class="actions">
        <button class="btn primary" ?disabled=${working || !p.exists} @click=${() => this.print(p, needsSlots)}>
          ${working ? html`<span class="spinner" aria-hidden="true"></span>` : icon(mdiPlay, 18)}
          ${working ? this.t("panels.print.uploading") : this.t("common.actions.print")}
        </button>
      </div>
    </ha-card>`;
  }

  static override styles = [
    sharedStyles,
    css`
      ha-card {
        display: block;
        padding: 16px;
      }
      .field {
        display: flex;
        flex-direction: column;
        gap: 6px;
        margin-bottom: 16px;
      }
      .field span {
        font-weight: 500;
      }
      .actions {
        display: flex;
        justify-content: flex-end;
      }
      .alert {
        border-left: 4px solid var(--ac-problem);
        background: color-mix(in srgb, var(--ac-problem) 10%, transparent);
        padding: 8px 12px;
        border-radius: 4px;
        margin-bottom: 12px;
      }
      .ok {
        color: var(--ac-printing);
      }
      .spinner {
        width: 16px;
        height: 16px;
        border-radius: 50%;
        border: 2px solid currentColor;
        border-right-color: transparent;
        animation: spin 800ms linear infinite;
      }
      @keyframes spin {
        to {
          transform: rotate(360deg);
        }
      }
    `,
  ];
}

defineOnce("anycubic-print-page", AnycubicPrintPage);
