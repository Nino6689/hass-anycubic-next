import { LitElement, css, html, nothing } from "lit";
import { defineOnce } from "../ha/dom";
import type { HomeAssistant } from "../ha/types";
import { localize } from "../localize";

let streamReady: Promise<boolean> | undefined;

/**
 * Home Assistant defines its camera stream element lazily. Ask the dashboard
 * helpers to load the camera "more info" control, which brings it in, and wait
 * a bounded time for the tag.
 */
export function ensureCameraStream(): Promise<boolean> {
  if (customElements.get("ha-camera-stream")) return Promise.resolve(true);
  streamReady ??= (async () => {
    try {
      const helpers = await window.loadCardHelpers?.();
      helpers?.importMoreInfoControl?.("camera");
    } catch {
      // fall through to the wait; it decides
    }
    await Promise.race([
      customElements.whenDefined("ha-camera-stream"),
      new Promise((resolve) => setTimeout(resolve, 10000)),
    ]);
    const ok = customElements.get("ha-camera-stream") !== undefined;
    if (!ok) streamReady = undefined;
    return ok;
  })();
  return streamReady;
}

/** A muted live stream of one camera entity, with the fallback messages. */
export class AnycubicCamera extends LitElement {
  static override properties = {
    hass: { attribute: false },
    entityId: { type: String },
    available: { type: Boolean },
    live: { type: Boolean },
    player: { state: true },
  };

  hass?: HomeAssistant;
  entityId?: string;
  available = true;
  /** Show the LIVE badge (cloud camera). */
  live = false;
  private player: "loading" | "ready" | "failed" = "loading";

  static override styles = css`
    :host {
      position: relative;
      display: block;
      width: 100%;
      height: 100%;
      background: #000;
      overflow: hidden;
    }
    ha-camera-stream {
      display: block;
      width: 100%;
      height: 100%;
      --video-max-height: 100%;
    }
    .msg {
      position: absolute;
      inset: 0;
      display: flex;
      align-items: center;
      justify-content: center;
      text-align: center;
      padding: 12px;
      color: #eee;
      font-size: 14px;
    }
    .live {
      position: absolute;
      top: 8px;
      right: 8px;
      background: #d32f2f;
      color: #fff;
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.06em;
      padding: 2px 6px;
      border-radius: 4px;
    }
  `;

  override connectedCallback(): void {
    super.connectedCallback();
    ensureCameraStream().then((ok) => (this.player = ok ? "ready" : "failed"));
  }

  protected override render() {
    const t = (k: string) => localize(this.hass?.language, `card.media_view.${k}`);
    const stateObj = this.entityId ? this.hass?.states[this.entityId] : undefined;
    if (!this.available || !stateObj || stateObj.state === "unavailable") {
      return html`<div class="msg">${t("camera_unavailable")}</div>`;
    }
    if (this.player === "failed") return html`<div class="msg">${t("player_unavailable")}</div>`;
    if (this.player === "loading") return html`<div class="msg">${t("starting")}</div>`;
    return html`<ha-camera-stream
        .hass=${this.hass}
        .stateObj=${stateObj}
        .muted=${true}
        .controls=${false}
        .allowExoPlayer=${true}
        .fitMode=${"contain"}
      ></ha-camera-stream>
      ${this.live ? html`<span class="live">${t("live")}</span>` : nothing}`;
  }
}

defineOnce("anycubic-camera", AnycubicCamera);
