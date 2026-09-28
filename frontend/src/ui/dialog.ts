import { LitElement, css, html, nothing } from "lit";
import { mdiClose } from "@mdi/js";
import { defineOnce, fire } from "../ha/dom";
import { icon } from "./icon";
import { sharedStyles } from "./styles";

/**
 * A modal owned by the element that renders it: full-viewport backdrop, a
 * centred panel, a close control; a backdrop tap or Escape closes it.
 * Fires `dialog-closed` when the user dismisses it.
 */
export class AnycubicDialog extends LitElement {
  static override properties = {
    open: { type: Boolean, reflect: true },
    heading: { type: String },
    closeLabel: { type: String },
  };

  open = false;
  heading = "";
  closeLabel = "Close";

  static override styles = [
    sharedStyles,
    css`
      :host {
        display: contents;
      }
      .backdrop {
        position: fixed;
        inset: 0;
        z-index: 10;
        display: flex;
        align-items: center;
        justify-content: center;
        background: rgba(0, 0, 0, 0.45);
        animation: fade 160ms ease-out;
      }
      .panel {
        width: 80%;
        max-width: 600px;
        max-height: 88vh;
        overflow: auto;
        box-sizing: border-box;
        background: var(--ac-surface);
        color: var(--primary-text-color);
        border-radius: var(--ac-radius);
        box-shadow: 0 12px 40px rgba(0, 0, 0, 0.35);
        padding: 12px 20px 20px;
        animation: pop 160ms ease-out;
      }
      header {
        display: flex;
        align-items: center;
        gap: 8px;
        margin-bottom: 8px;
      }
      h2 {
        flex: 1;
        margin: 0;
        font-size: 18px;
        font-weight: 500;
      }
      @media (max-width: 600px) {
        .panel {
          width: 95%;
        }
      }
      @keyframes fade {
        from {
          opacity: 0;
        }
      }
      @keyframes pop {
        from {
          opacity: 0;
          transform: scale(0.94);
        }
      }
      @media (prefers-reduced-motion: reduce) {
        .backdrop,
        .panel {
          animation: none;
        }
      }
    `,
  ];

  override connectedCallback(): void {
    super.connectedCallback();
    window.addEventListener("keydown", this.onKey);
  }

  override disconnectedCallback(): void {
    window.removeEventListener("keydown", this.onKey);
    super.disconnectedCallback();
  }

  private onKey = (ev: KeyboardEvent) => {
    if (this.open && ev.key === "Escape") this.dismiss();
  };

  private dismiss() {
    fire(this, "dialog-closed");
  }

  protected override render() {
    if (!this.open) return nothing;
    return html`<div class="backdrop" @click=${(ev: Event) => ev.target === ev.currentTarget && this.dismiss()}>
      <div class="panel" role="dialog" aria-modal="true" aria-label=${this.heading}>
        <header>
          <h2>${this.heading}</h2>
          <button class="icon-btn" title=${this.closeLabel} aria-label=${this.closeLabel} @click=${this.dismiss}>
            ${icon(mdiClose)}
          </button>
        </header>
        <slot></slot>
      </div>
    </div>`;
  }
}

defineOnce("anycubic-dialog", AnycubicDialog);
