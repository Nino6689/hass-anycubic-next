// Card bundle: served at /anycubic-cloud-panel-static/anycubic-card.js.
import "./card/card";
import "./card/editor";
import { VERSION } from "./version";

const CARD = {
  type: "anycubic-card",
  name: "Anycubic Card",
  description: "Anycubic Cloud Integration Card",
  preview: true,
};

window.customCards = window.customCards ?? [];
if (!window.customCards.some((c) => c.type === CARD.type)) window.customCards.push(CARD);

console.info(`%c anycubic-card %c ${VERSION} `, "background:#1976d2;color:#fff;border-radius:3px 0 0 3px", "background:#555;color:#fff;border-radius:0 3px 3px 0");
