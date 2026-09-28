// The sidebar panel (FRONTEND.md §4.14): shell, routing and tabs.

import { LitElement, css, html, nothing, type PropertyValues } from "lit";
import { mdiMenu, mdiPrinter3d } from "@mdi/js";
import { defineOnce, fire, navigate } from "../ha/dom";
import type { HomeAssistant, PanelInfo, Route } from "../ha/types";
import { deviceName, findPrinters } from "../lib/entities";
import { localize } from "../localize";
import { icon } from "../ui/icon";
import { sharedStyles } from "../ui/styles";
import { DEBUG, VERSION } from "../version";
import "./files-page";
import "./main-page";
import "./print-page";

export const PAGES = [
  "main",
  "local-files",
  "udisk-files",
  "cloud-files",
  "print-no_cloud_save",
  "print-save_in_cloud",
  "debug",
] as const;
export type Page = (typeof PAGES)[number];

const TITLES: Record<Page, string> = {
  main: "panels.main.title",
  "local-files": "panels.files_local.title",
  "udisk-files": "panels.files_udisk.title",
  "cloud-files": "panels.files_cloud.title",
  "print-no_cloud_save": "panels.print_no_cloud_save.title",
  "print-save_in_cloud": "panels.print_save_in_cloud.title",
  debug: "panels.debug.title",
};

/** `/<device>/<page>` → parts; a missing page is `main`. */
export function parseRoute(path: string | undefined): { deviceId?: string; page?: string } {
  const parts = (path ?? "").split("/").filter((s) => s !== "");
  if (!parts.length) return {};
  return { deviceId: decodeURIComponent(parts[0]), page: parts[1] ?? "main" };
}

/**
 * The panel's card settings. The integration passes the entry's stored
 * `card_config` object as the panel config itself (DECISIONS round 2, F1);
 * Home Assistant's `_panel_custom` block is dropped. The object nested under a
 * `card_config` key is still accepted.
 */
export function panelCardConfig(panel: PanelInfo | undefined): Record<string, unknown> {
  const config = panel?.config;
  if (!config || typeof config !== "object") return {};
  const nested = (config as Record<string, unknown>).card_config;
  if (nested && typeof nested === "object" && !Array.isArray(nested)) return { ...(nested as Record<string, unknown>) };
  const copy: Record<string, unknown> = { ...config };
  delete copy._panel_custom;
  return copy;
}

export class AnycubicCloudPanel extends LitElement {
  static override properties = {
    hass: { attribute: false },
    narrow: { type: Boolean },
    route: { attribute: false },
    panel: { attribute: false },
  };

  hass?: HomeAssistant;
  narrow = false;
  route?: Route;
  panel?: PanelInfo;

  private t(key: string): string {
    return localize(this.hass?.language, key);
  }

  private get base(): string {
    return this.route?.prefix || "/anycubic_cloud";
  }

  private pages(): Page[] {
    return PAGES.filter((p) => p !== "debug" || DEBUG);
  }

  protected override updated(changed: PropertyValues): void {
    // With exactly one printer there is nothing to choose.
    if (!changed.has("route") && !changed.has("hass")) return;
    const { deviceId } = parseRoute(this.route?.path);
    if (deviceId || !this.hass) return;
    const printers = findPrinters(this.hass);
    if (printers.length === 1) navigate(`${this.base}/${printers[0].id}/main`, true);
  }

  private goto(deviceId: string, page: Page) {
    const url = `${this.base}/${encodeURIComponent(deviceId)}/${page}`;
    if (url === window.location.pathname) {
      this.renderRoot.querySelector(".content")?.scrollTo({ top: 0, behavior: "smooth" });
      return;
    }
    navigate(url);
  }

  private renderSelect() {
    const printers = findPrinters(this.hass);
    return html`<div class="select">
      <p>${this.t(printers.length ? "panels.initial.printer_select" : "panels.initial.no_printers")}</p>
      <div class="printers">
        ${printers.map(
          (d) => html`<button class="printer" @click=${() => this.goto(d.id, "main")}>
            ${icon(mdiPrinter3d, 48)}<span>${deviceName(d) ?? d.id}</span>
          </button>`,
        )}
      </div>
    </div>`;
  }

  private renderPage(deviceId: string, page: string) {
    switch (page) {
      case "main":
        return html`<anycubic-main-page
          .hass=${this.hass}
          .deviceId=${deviceId}
          .panelConfig=${panelCardConfig(this.panel)}
        ></anycubic-main-page>`;
      case "local-files":
      case "udisk-files":
      case "cloud-files":
        return html`<anycubic-files-page .hass=${this.hass} .deviceId=${deviceId} .source=${page.split("-")[0]}></anycubic-files-page>`;
      case "print-no_cloud_save":
      case "print-save_in_cloud":
        return html`<anycubic-print-page .hass=${this.hass} .deviceId=${deviceId} .mode=${page.slice(6)}></anycubic-print-page>`;
      case "debug":
        if (DEBUG) {
          return html`<pre class="debug">
${JSON.stringify(
              {
                entities: Object.keys(this.hass?.entities ?? {}).length,
                narrow: this.narrow,
                config: panelCardConfig(this.panel),
                route: this.route,
                printers: findPrinters(this.hass),
                device: this.hass?.devices[deviceId],
              },
              null,
              2,
            )}</pre
          >`;
        }
        return html`<p class="note">${this.t("common.messages.page_not_found")}</p>`;
      default:
        return html`<p class="note">${this.t("common.messages.page_not_found")}</p>`;
    }
  }

  protected override render() {
    const { deviceId, page } = parseRoute(this.route?.path);
    const known = deviceId && this.hass?.devices[deviceId] !== undefined;
    const wide = page === "main";
    return html`<div class="toolbar">
        ${this.narrow
          ? customElements.get("ha-menu-button")
            ? html`<ha-menu-button .hass=${this.hass} .narrow=${this.narrow}></ha-menu-button>`
            : html`<button class="icon-btn menu" @click=${() => fire(this, "hass-toggle-menu")}>${icon(mdiMenu)}</button>`
          : nothing}
        <div class="title">${this.t("title")}</div>
        <div class="version">${VERSION}</div>
      </div>
      ${known
        ? html`<nav class="tabs" role="tablist">
            ${this.pages().map(
              (p) => html`<button role="tab" aria-selected=${p === page ? "true" : "false"} @click=${() => this.goto(deviceId!, p)}>
                ${this.t(TITLES[p])}
              </button>`,
            )}
          </nav>`
        : nothing}
      <div class="content">
        <div class="lane ${wide ? "wide" : ""}">${known ? this.renderPage(deviceId!, page!) : this.renderSelect()}</div>
      </div>`;
  }

  static override styles = [
    sharedStyles,
    css`
      :host {
        display: flex;
        flex-direction: column;
        height: 100%;
        background: var(--primary-background-color);
        color: var(--primary-text-color);
      }
      .toolbar {
        display: flex;
        align-items: center;
        gap: 12px;
        height: var(--header-height, 56px);
        padding: 0 16px;
        box-sizing: border-box;
        background: var(--app-header-background-color, var(--primary-color));
        color: var(--app-header-text-color, var(--text-primary-color, #fff));
        border-bottom: var(--app-header-border-bottom, none);
        flex: none;
      }
      .toolbar .menu {
        color: inherit;
      }
      .title {
        flex: 1;
        font-size: 20px;
        font-weight: 400;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }
      .version {
        font-size: 12px;
        opacity: 0.8;
      }
      .tabs {
        display: flex;
        overflow-x: auto;
        scrollbar-width: none;
        background: var(--app-header-background-color, var(--primary-color));
        flex: none;
      }
      .tabs button {
        flex: none;
        background: none;
        border: none;
        border-bottom: 2px solid transparent;
        color: var(--app-header-text-color, var(--text-primary-color, #fff));
        opacity: 0.75;
        padding: 12px 16px;
        text-transform: uppercase;
        font-size: 14px;
        font-weight: 500;
        cursor: pointer;
      }
      .tabs button[aria-selected="true"] {
        opacity: 1;
        border-bottom-color: currentColor;
      }
      .content {
        flex: 1;
        overflow-y: auto;
        padding: 16px;
      }
      .lane {
        margin: 0 auto;
        max-width: 1024px;
      }
      .lane.wide {
        max-width: 1600px;
      }
      @media (max-width: 600px) {
        .content {
          padding: 8px;
        }
      }
      .select {
        text-align: center;
        padding-top: 32px;
      }
      .printers {
        display: flex;
        flex-wrap: wrap;
        justify-content: center;
        gap: 16px;
        margin-top: 16px;
      }
      .printer {
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 8px;
        width: 180px;
        padding: 24px 12px;
        border-radius: var(--ac-radius);
        border: 1px solid var(--ac-divider);
        background: var(--ac-surface);
        cursor: pointer;
        font-size: 16px;
      }
      .printer:hover {
        border-color: var(--ac-accent);
      }
      .debug {
        white-space: pre-wrap;
        font-size: 12px;
      }
    `,
  ];
}

defineOnce("anycubic-cloud-panel", AnycubicCloudPanel);
