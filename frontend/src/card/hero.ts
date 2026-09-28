import { LitElement, css, html, nothing, type PropertyValues } from "lit";
import { mdiCamera, mdiImage, mdiPrinter3d, mdiPrinter3dNozzle } from "@mdi/js";
import { defineOnce } from "../ha/dom";
import type { HomeAssistant } from "../ha/types";
import { aceCount, aceUnit, feedingSlot, tipColour, type AceUnit } from "../lib/ace";
import { chooseBody } from "../lib/body";
import { heatLevel } from "../lib/colour";
import type { MediaView, ResolvedConfig } from "../lib/config";
import type { Printer } from "../lib/entities";
import { isErrorState, isPrinting, printState } from "../lib/state";
import { localize } from "../localize";
import { icon } from "../ui/icon";
import { sharedStyles } from "../ui/styles";
import { artLayout, artStyles, renderArt, type ArtAceUnit, type ArtModel } from "./art";
import "./camera";

type Tab = Exclude<MediaView, "auto" | "none">;

let heroCount = 0;

/** The preview URL without its rotating access token, so a failure is remembered. */
function previewKey(url: string): string {
  return url.replace(/([?&])token=[^&]*&?/, "$1").replace(/[?&]$/, "");
}

/** The media area (FRONTEND.md §4.4). */
export class AnycubicHero extends LitElement {
  static override properties = {
    hass: { attribute: false },
    printer: { attribute: false },
    config: { attribute: false },
    preview: { type: Boolean },
    tapped: { state: true },
    failed: { state: true },
  };

  hass?: HomeAssistant;
  printer?: Printer;
  config?: ResolvedConfig;
  /** Card-picker and gallery previews: never start a camera. */
  preview = false;
  private tapped?: Tab;
  private failed = new Set<string>();
  private probing?: string;
  private readonly uid = `ac${++heroCount}`;

  static override styles = [
    sharedStyles,
    artStyles,
    css`
      :host {
        display: block;
      }
      .frame {
        position: relative;
        aspect-ratio: 16 / 9;
        border-radius: var(--ac-radius);
        overflow: hidden;
        background: #000;
      }
      .frame.art {
        aspect-ratio: 4 / 3;
        background: transparent;
      }
      .preview-img {
        width: 100%;
        height: 100%;
        object-fit: contain;
        display: block;
        background: var(--ac-surface-2);
      }
      .art-wrap {
        position: absolute;
        inset: 0 0 44px 0;
        container-type: size;
        display: flex;
        align-items: center;
        justify-content: center;
      }
      .frame.single .art-wrap {
        inset: 0;
      }
      .art-box {
        position: relative;
        width: min(100cqw, calc(100cqh * var(--ratio)));
        height: min(100cqh, calc(100cqw / var(--ratio)));
      }
      .chamber {
        position: absolute;
        overflow: hidden;
        background: #000;
      }
      .art-box .art {
        position: absolute;
        inset: 0;
      }
      .tabs {
        position: absolute;
        left: 8px;
        bottom: 8px;
        display: flex;
        gap: 4px;
        padding: 3px;
        border-radius: 22px;
        background: rgba(0, 0, 0, 0.45);
      }
      .frame.art .tabs {
        background: rgba(0, 0, 0, 0.72);
      }
      .tabs button {
        width: 34px;
        height: 34px;
        border-radius: 50%;
        border: none;
        background: transparent;
        color: rgba(255, 255, 255, 0.85);
        cursor: pointer;
        display: flex;
        align-items: center;
        justify-content: center;
      }
      .tabs button[aria-pressed="true"] {
        background: rgba(255, 255, 255, 0.92);
        color: #111;
      }
      .tabs button:focus-visible {
        outline: 2px solid #fff;
      }
    `,
  ];

  private get noCamera(): boolean {
    return this.preview || !!this.config?.noCamera;
  }

  private previewUrl(): string | undefined {
    const e = this.printer?.entity("job_image_url", "image");
    if (!e || e.state === "unavailable") return undefined;
    const pic = e.attributes.entity_picture;
    if (typeof pic === "string" && pic) return pic;
    const token = e.attributes.access_token;
    return typeof token === "string" ? `/api/image_proxy/${e.entity_id}?token=${token}` : undefined;
  }

  private usablePreview(): string | undefined {
    const url = this.previewUrl();
    return url && !this.failed.has(previewKey(url)) ? url : undefined;
  }

  protected override willUpdate(changed: PropertyValues): void {
    if (!changed.has("hass") && !changed.has("printer")) return;
    // Probe the render so a LAN-only printer (render in the cloud) drops the tab.
    const url = this.previewUrl();
    if (!url || typeof Image === "undefined") return;
    const key = previewKey(url);
    if (this.failed.has(key) || this.probing === key) return;
    this.probing = key;
    const img = new Image();
    img.onerror = () => this.markFailed(url);
    img.src = url;
  }

  private markFailed(url: string) {
    const key = previewKey(url);
    if (this.failed.has(key)) return;
    this.failed = new Set(this.failed).add(key);
  }

  private tabs(): Tab[] {
    const p = this.printer;
    const cam = p?.camera(this.config?.cameraEntityId);
    const hasCamera = !!cam && !this.noCamera;
    const hasPreview = !!this.usablePreview();
    const tabs: Tab[] = [];
    if (hasCamera) tabs.push("camera");
    if (hasPreview) tabs.push("preview");
    tabs.push("printer");
    if (hasPreview && hasCamera) tabs.push("printer_model");
    return tabs;
  }

  private current(tabs: Tab[]): { tab: Tab; explicit: boolean } {
    const mv = this.config?.mediaView ?? "auto";
    let wanted: Tab;
    let explicit = false;
    if (this.tapped) {
      wanted = this.tapped;
      explicit = true;
    } else if (mv !== "auto" && mv !== "none") {
      wanted = mv;
      explicit = true;
    } else {
      wanted = tabs.includes("preview") ? "preview" : "printer";
    }
    if (!tabs.includes(wanted)) return { tab: "printer", explicit: false };
    return { tab: wanted, explicit };
  }

  private artModel(tab: Tab, explicit: boolean): { model: ArtModel; units: number } {
    const p = this.printer!;
    const cfg = this.config!;
    const { body, minAce } = chooseBody(cfg.printerArt, p.device?.model || p.name);
    const count = body === "resin" ? 0 : Math.max(aceCount(p), minAce);
    const live: AceUnit[] = [aceUnit(p, 0), aceUnit(p, 1)];
    const feeding = live.some((u) => u.loadedSlot) ? feedingSlot(live) : undefined;
    const ace: ArtAceUnit[] = [];
    for (let k = 0; k < count; k++) {
      const u = live[k];
      ace.push({
        feeding: feeding?.unit === k,
        reels: (u?.active ? u.slots : []).map((s) => ({
          colour: s.colour,
          percent: s.percent,
          loaded: s.loaded,
          feeding: feeding?.unit === k && feeding.slot === s.slot,
        })),
      });
    }
    const cam = p.camera(cfg.cameraEntityId);
    const cameraInChamber = tab === "printer" && explicit && !!cam?.available && !this.noCamera;
    const state = printState(p);
    return {
      units: count,
      model: {
        uid: this.uid,
        body,
        ace,
        tipColour: tipColour(live.filter((u) => u.active)),
        progress: p.num("job_progress"),
        printing: isPrinting(p),
        paused: p.isOn("job_is_paused") === true,
        error: isErrorState(state),
        fanOn: (p.num("fan_speed_pct") ?? 0) > 0,
        lightOn: p.value("printer_light", "light") === "on",
        nozzleHeat: heatLevel(p.num("curr_nozzle_temp"), p.num("target_nozzle_temp")),
        bedHeat: heatLevel(p.num("curr_hotbed_temp"), p.num("target_hotbed_temp")),
        previewUrl: this.usablePreview(),
        cameraInChamber,
      },
    };
  }

  private renderArtSurface(tab: Tab, explicit: boolean) {
    const { model, units } = this.artModel(tab, explicit);
    const layout = artLayout(model.body, units);
    const c = layout.chamber;
    const pct = (v: number, of: number) => `${(v / of) * 100}%`;
    const cam = this.printer?.camera(this.config?.cameraEntityId);
    return html`<div class="art-wrap">
      <div class="art-box" style="--ratio: ${layout.width / layout.height}">
        ${model.cameraInChamber && cam
          ? html`<div
              class="chamber"
              style="left:${pct(c.x, layout.width)};top:${pct(c.y, layout.height)};width:${pct(c.w, layout.width)};height:${pct(c.h, layout.height)}"
            >
              <anycubic-camera .hass=${this.hass} .entityId=${cam.entityId} .available=${cam.available} .live=${cam.isCloud}></anycubic-camera>
            </div>`
          : nothing}
        ${renderArt(model, layout)}
      </div>
    </div>`;
  }

  protected override render() {
    if (!this.config || this.config.mediaView === "none" || !this.printer) return nothing;
    const t = (k: string) => localize(this.hass?.language, `card.media_view.${k}`);
    const tabs = this.tabs();
    const { tab, explicit } = this.current(tabs);
    const isArt = tab === "printer" || tab === "printer_model";
    let surface;
    if (tab === "camera") {
      const cam = this.printer.camera(this.config.cameraEntityId)!;
      surface = html`<anycubic-camera .hass=${this.hass} .entityId=${cam.entityId} .available=${cam.available} .live=${cam.isCloud}></anycubic-camera>`;
    } else if (tab === "preview") {
      const url = this.usablePreview()!;
      surface = html`<img class="preview-img" src=${url} alt=${t("preview_alt")} @error=${() => this.markFailed(url)} />`;
    } else {
      surface = this.renderArtSurface(tab, explicit);
    }
    const icons: Record<Tab, string> = {
      camera: mdiCamera,
      preview: mdiImage,
      printer: mdiPrinter3d,
      printer_model: mdiPrinter3dNozzle,
    };
    return html`<div class="frame ${isArt ? "art" : ""} ${tabs.length > 1 ? "" : "single"}">
      ${surface}
      ${tabs.length > 1
        ? html`<div class="tabs">
            ${tabs.map(
              (k) => html`<button
                title=${t(`tabs.${k}`)}
                aria-label=${t(`tabs.${k}`)}
                aria-pressed=${k === tab ? "true" : "false"}
                @click=${() => (this.tapped = k)}
              >
                ${icon(icons[k], 20)}
              </button>`,
            )}
          </div>`
        : nothing}
    </div>`;
  }
}

defineOnce("anycubic-hero", AnycubicHero);
