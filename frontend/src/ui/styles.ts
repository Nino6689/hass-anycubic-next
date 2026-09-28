import { css } from "lit";

/** Buttons, chips and small pieces shared by the card, dialogs and panel. */
export const sharedStyles = css`
  :host {
    --ac-accent: var(--state-active-color, var(--primary-color, #03a9f4));
    --ac-activity: var(--warning-color, #ffa600);
    --ac-printing: var(--success-color, #43a047);
    --ac-healthy: var(--info-color, #039be5);
    --ac-problem: var(--error-color, #db4437);
    --ac-radius: var(--ha-card-border-radius, 12px);
    --ac-muted: var(--secondary-text-color, #727272);
    --ac-divider: var(--divider-color, rgba(0, 0, 0, 0.12));
    --ac-surface: var(--card-background-color, var(--ha-card-background, #fff));
    --ac-surface-2: var(--secondary-background-color, #f3f3f3);
  }
  .mdi {
    display: block;
    flex: none;
  }
  button {
    font: inherit;
    color: inherit;
  }
  .btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    min-height: 36px;
    padding: 0 14px;
    border-radius: 18px;
    border: 1px solid var(--ac-divider);
    background: var(--ac-surface-2);
    color: var(--primary-text-color);
    cursor: pointer;
    font-weight: 500;
    font-size: 14px;
    transition: background 120ms ease, opacity 120ms ease;
  }
  .btn:hover:not([disabled]) {
    background: color-mix(in srgb, var(--ac-accent) 14%, var(--ac-surface-2));
  }
  .btn:focus-visible,
  .icon-btn:focus-visible,
  .chip:focus-visible {
    outline: 2px solid var(--ac-accent);
    outline-offset: 2px;
  }
  .btn[disabled],
  .icon-btn[disabled],
  .chip[disabled] {
    opacity: 0.45;
    cursor: default;
  }
  .btn.primary {
    background: var(--ac-accent);
    border-color: transparent;
    color: var(--text-primary-color, #fff);
  }
  .btn.danger {
    background: color-mix(in srgb, var(--ac-problem) 14%, var(--ac-surface));
    border-color: color-mix(in srgb, var(--ac-problem) 40%, transparent);
    color: var(--ac-problem);
  }
  .icon-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 40px;
    height: 40px;
    border-radius: 50%;
    border: none;
    background: transparent;
    cursor: pointer;
    color: var(--ac-muted);
  }
  .icon-btn:hover:not([disabled]) {
    background: color-mix(in srgb, var(--primary-text-color) 8%, transparent);
  }
  .icon-btn.on {
    color: var(--ac-activity);
  }
  .chip {
    border: 1px solid var(--ac-divider);
    background: transparent;
    border-radius: 16px;
    padding: 4px 12px;
    cursor: pointer;
    font-size: 13px;
  }
  .chip.selected {
    background: var(--ac-accent);
    color: var(--text-primary-color, #fff);
    border-color: transparent;
  }
  .muted {
    color: var(--ac-muted);
  }
  .note {
    font-size: 13px;
    color: var(--ac-muted);
    margin: 8px 0 0;
  }
  .warn {
    font-size: 13px;
    color: var(--ac-activity);
    display: flex;
    gap: 6px;
    align-items: flex-start;
  }
  input,
  select {
    font: inherit;
    color: var(--primary-text-color);
    background: var(--ac-surface);
    border: 1px solid var(--ac-divider);
    border-radius: 8px;
    padding: 8px 10px;
    min-height: 38px;
    box-sizing: border-box;
  }
  .visually-hidden {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip: rect(0 0 0 0);
    white-space: nowrap;
  }
`;
