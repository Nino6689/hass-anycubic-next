// Panel file pages (FRONTEND.md §4.16).

import { LitElement, css, html, nothing } from "lit";
import { mdiDelete, mdiRefresh } from "@mdi/js";
import { defineOnce } from "../ha/dom";
import type { HomeAssistant } from "../ha/types";
import { callAction, pressButton } from "../lib/actions";
import { Printer } from "../lib/entities";
import { localize } from "../localize";
import { icon } from "../ui/icon";
import { sharedStyles } from "../ui/styles";
import "../card/dialogs";

export type FileSource = "local" | "udisk" | "cloud";

interface FileInfo {
  name?: string;
  id?: number;
  size_mb?: number;
}

/**
 * Whether the refresh control is offered. The cloud list always can be; the
 * printer's own lists need the request button and a printer that can answer
 * (DECISIONS, frontend 12: hide the control otherwise).
 */
export function canRefresh(p: Printer, source: FileSource): boolean {
  if (!p.usable(`request_file_list_${source}`, "button")) return false;
  if (source === "cloud") return true;
  return p.attr<boolean>("mqtt_connection_active", "supports_mqtt_login", "binary_sensor") !== false;
}

export class AnycubicFilesPage extends LitElement {
  static override properties = {
    hass: { attribute: false },
    deviceId: { type: String },
    source: { type: String },
    refreshing: { state: true },
    deleting: { state: true },
    confirm: { state: true },
  };

  hass?: HomeAssistant;
  deviceId?: string;
  source: FileSource = "local";
  private refreshing = false;
  private deleting = false;
  private confirm?: FileInfo;

  private t(key: string, vars?: Record<string, string | number>): string {
    return localize(this.hass?.language, key, vars);
  }

  private async refresh(p: Printer) {
    if (this.refreshing || !this.hass) return;
    this.refreshing = true;
    try {
      await pressButton(this.hass, p, `request_file_list_${this.source}`);
    } catch (err) {
      console.error("anycubic panel:", err);
    } finally {
      this.refreshing = false;
    }
  }

  private async deleteFile(p: Printer, file: FileInfo) {
    this.confirm = undefined;
    if (this.deleting || !this.hass) return;
    this.deleting = true;
    try {
      if (this.source === "cloud") {
        if (typeof file.id !== "number") return;
        await callAction(this.hass, p, "delete_file_cloud", { file_id: file.id });
      } else {
        await callAction(this.hass, p, `delete_file_${this.source}`, { filename: file.name });
      }
    } catch (err) {
      console.error("anycubic panel:", err);
    } finally {
      this.deleting = false;
    }
  }

  protected override render() {
    const p = new Printer(this.hass, this.deviceId);
    const raw = p.attr<FileInfo[]>(`file_list_${this.source}`, "file_info");
    const files = Array.isArray(raw) ? raw.filter((f) => f && typeof f.name === "string") : [];
    const refresh = canRefresh(p, this.source);
    return html`<ha-card>
      <div class="bar">
        ${refresh
          ? html`<button class="btn" ?disabled=${this.refreshing} @click=${() => this.refresh(p)}>
              ${icon(mdiRefresh, 18)} ${this.t("common.actions.refresh")}
            </button>`
          : this.source !== "cloud"
            ? html`<p class="note">${this.t("common.messages.mqtt_unsupported")}</p>`
            : nothing}
      </div>
      ${files.length
        ? html`<ul>
            ${files.map(
              (f) => html`<li>
                <span class="name">${f.name}</span>
                <button
                  class="icon-btn"
                  title=${this.t("common.actions.delete")}
                  aria-label=${`${this.t("common.actions.delete")} ${f.name}`}
                  ?disabled=${this.deleting}
                  @click=${() => (this.confirm = f)}
                >
                  ${icon(mdiDelete)}
                </button>
              </li>`,
            )}
          </ul>`
        : html`<p class="note">${this.t("panels.files.empty")}</p>`}
      <anycubic-confirm
        .hass=${this.hass}
        .open=${this.confirm !== undefined}
        .heading=${this.t("common.actions.delete")}
        .message=${this.t("panels.files.confirm_delete", { name: this.confirm?.name ?? "" })}
        @dialog-closed=${() => (this.confirm = undefined)}
        @confirmed=${() => this.confirm && this.deleteFile(p, this.confirm)}
      ></anycubic-confirm>
    </ha-card>`;
  }

  static override styles = [
    sharedStyles,
    css`
      ha-card {
        display: block;
        padding: 16px;
      }
      .bar {
        display: flex;
        justify-content: flex-end;
        margin-bottom: 8px;
      }
      .bar .note {
        margin: 0;
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
        border-bottom: 1px solid var(--ac-divider);
      }
      li:last-child {
        border-bottom: none;
      }
      .name {
        flex: 1;
        overflow-wrap: anywhere;
      }
    `,
  ];
}

defineOnce("anycubic-files-page", AnycubicFilesPage);
