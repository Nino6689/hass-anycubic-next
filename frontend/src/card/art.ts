// The printer artwork (FRONTEND.md §4.5): a schematic, generic printer drawn
// for this project. No maker's logo or other marks appear anywhere in it.

import { css, nothing, svg, unsafeCSS, type SVGTemplateResult } from "lit";
import { contrastOn, mixHex } from "../lib/colour";
import type { Body } from "../lib/body";

export const ART_W = 480;
const TOP = 30;
const BODY_H = 330;
const ACE_H = 84;
const PART_MAX = 110;

export interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface ArtReel {
  colour?: string;
  percent?: number;
  loaded: boolean;
  feeding: boolean;
}

export interface ArtAceUnit {
  reels: ArtReel[];
  feeding: boolean;
}

export interface ArtModel {
  uid: string;
  body: Body;
  ace: ArtAceUnit[];
  tipColour?: string;
  progress?: number;
  printing: boolean;
  paused: boolean;
  error: boolean;
  fanOn: boolean;
  lightOn: boolean;
  nozzleHeat: number;
  bedHeat: number;
  previewUrl?: string;
  cameraInChamber: boolean;
}

export interface ArtLayout {
  width: number;
  height: number;
  y0: number;
  chamber: Rect;
}

const CHAMBER: Record<Body, Rect> = {
  enclosed: { x: 100, y: 36, w: 280, h: 196 },
  bedslinger: { x: 110, y: 30, w: 260, h: 200 },
  resin: { x: 130, y: 30, w: 220, h: 170 },
  generic: { x: 112, y: 22, w: 256, h: 230 },
};

const PLATE_Y: Record<Body, number> = { enclosed: 214, bedslinger: 246, resin: 204, generic: 236 };

/** Size of the drawing and where its chamber sits, in drawing units. */
export function artLayout(body: Body, aceCount: number): ArtLayout {
  const units = body === "resin" ? 0 : aceCount;
  const y0 = TOP + units * ACE_H;
  const c = CHAMBER[body];
  return { width: ART_W, height: y0 + BODY_H + 6, y0, chamber: { ...c, y: c.y + y0 } };
}

const AMBER = "#ffb300";
const HOT = "#ff3d00";
const LIGHT = "#ffd27a";

function heatColour(level: number): string {
  return mixHex(AMBER, HOT, level);
}

function fan(cx: number, cy: number, on: boolean): SVGTemplateResult {
  const blade = "M0 -2 C 6 -14, 14 -10, 12 -2 Z";
  return svg`<g transform="translate(${cx} ${cy})" class="a-fan ${on ? "on" : ""}">
    <circle r="18" class="a-hole a-line"></circle>
    <g class=${on ? "spin" : ""}>
      <circle r="16" fill="none"></circle>
      <path d=${blade}></path>
      <path d=${blade} transform="rotate(120)"></path>
      <path d=${blade} transform="rotate(240)"></path>
      <circle r="3"></circle>
    </g>
  </g>`;
}

function screen(x: number, y: number, w: number, h: number, m: ArtModel): SVGTemplateResult {
  const cx = x + w / 2;
  const cy = y + h / 2;
  let glyph: SVGTemplateResult;
  if (m.error) {
    glyph = svg`<path d="M${cx} ${cy - 13} L${cx + 14} ${cy + 11} L${cx - 14} ${cy + 11} Z" fill="#e53935"></path>
      <rect x=${cx - 1.5} y=${cy - 5} width="3" height="9" fill="#fff"></rect>
      <rect x=${cx - 1.5} y=${cy + 6} width="3" height="3" fill="#fff"></rect>`;
  } else if (m.paused) {
    glyph = svg`<rect x=${cx - 9} y=${cy - 11} width="6" height="22" rx="1.5" fill=${AMBER}></rect>
      <rect x=${cx + 3} y=${cy - 11} width="6" height="22" rx="1.5" fill=${AMBER}></rect>`;
  } else {
    // A plain isometric cube: a neutral "3D" glyph.
    const s = Math.min(w, h) * 0.28;
    glyph = svg`<g class="a-glyph" transform="translate(${cx} ${cy})">
      <path d="M0 ${-s} L${s * 0.87} ${-s / 2} L${s * 0.87} ${s / 2} L0 ${s} L${-s * 0.87} ${s / 2} L${-s * 0.87} ${-s / 2} Z"></path>
      <path d="M${-s * 0.87} ${-s / 2} L0 0 L${s * 0.87} ${-s / 2} M0 0 L0 ${s}"></path>
    </g>`;
  }
  return svg`<rect x=${x} y=${y} width=${w} height=${h} rx="5" class="a-screen"></rect>${glyph}`;
}

function reel(cx: number, cy: number, r: ArtReel, maxR: number, hubR: number): SVGTemplateResult {
  const pct = r.percent === undefined ? 100 : Math.min(100, Math.max(0, r.percent));
  const radius = hubR + (maxR - hubR) * (pct / 100);
  const colour = r.loaded ? r.colour : undefined;
  return svg`<g>
    <circle cx=${cx} cy=${cy} r=${maxR} class="a-reel-rim"></circle>
    <circle cx=${cx} cy=${cy} r=${radius} class=${colour ? "a-reel" : "a-reel empty"} style=${colour ? `fill:${colour}` : ""}></circle>
    <circle cx=${cx} cy=${cy} r=${hubR} class="a-hole a-line"></circle>
    ${r.feeding ? svg`<circle cx=${cx} cy=${cy} r=${maxR + 4} class="a-feeding"></circle>` : nothing}
  </g>`;
}

function aceUnits(m: ArtModel, y0: number): SVGTemplateResult[] {
  const out: SVGTemplateResult[] = [];
  m.ace.forEach((unit, k) => {
    const y = y0 - (k + 1) * ACE_H + 6;
    const midY = y + 36;
    const lane = 418 + k * 12;
    const tube = `M370 ${midY} H${lane} V${y0 + 22} H392`;
    out.push(svg`<path d=${tube} class=${unit.feeding ? "a-tube feeding" : "a-tube"}
      style=${unit.feeding && m.tipColour ? `stroke:${m.tipColour}` : ""}></path>`);
  });
  m.ace.forEach((unit, k) => {
    const y = y0 - (k + 1) * ACE_H + 6;
    out.push(svg`<rect x="110" y=${y} width="260" height="72" rx="10" class="a-chassis"></rect>`);
    unit.reels.slice(0, 4).forEach((r, i) => out.push(reel(110 + (260 * (i + 0.5)) / 4, y + 36, r, 26, 9)));
    for (let i = unit.reels.length; i < 4; i++) {
      out.push(reel(110 + (260 * (i + 0.5)) / 4, y + 36, { loaded: false, feeding: false }, 26, 9));
    }
  });
  return out;
}

function sideReel(m: ArtModel, y0: number): SVGTemplateResult {
  const cy = y0 + 80;
  return svg`<g>
    <path d="M40 ${cy - 30} C 40 ${y0 - 22}, 120 ${y0 - 22}, 132 ${y0 + 8}" class="a-tube feeding"
      style=${m.tipColour ? `stroke:${m.tipColour}` : ""}></path>
    <path d="M80 ${cy} H40" class="a-rail"></path>
    ${reel(40, cy, { loaded: true, feeding: false, colour: m.tipColour ?? "var(--ac-accent)" }, 30, 10)}
  </g>`;
}

interface PartGeom {
  cx: number;
  base: number;
  height: number;
  hanging: boolean;
}

function part(m: ArtModel, g: PartGeom): SVGTemplateResult | typeof nothing {
  if (g.height <= 0.5) return nothing;
  const tip = m.tipColour ?? "var(--ac-accent)";
  const halo = contrastOn(m.tipColour?.startsWith("#") ? m.tipColour : undefined);
  const dir = g.hanging ? 1 : -1;
  const top = g.hanging ? g.base : g.base - g.height;
  if (m.previewUrl) {
    const boxW = 150;
    const boxY = g.hanging ? g.base : g.base - PART_MAX;
    const flip = g.hanging ? `translate(0 ${2 * g.base + PART_MAX}) scale(1 -1)` : "";
    return svg`<defs>
        <mask id="mask-${m.uid}" style="mask-type:alpha" maskUnits="userSpaceOnUse"
          x=${g.cx - boxW / 2} y=${boxY} width=${boxW} height=${PART_MAX}>
          <image href=${m.previewUrl} x=${g.cx - boxW / 2} y=${boxY}
            width=${boxW} height=${PART_MAX} preserveAspectRatio="xMidYMax meet" transform=${flip}></image>
        </mask>
        <clipPath id="reveal-${m.uid}"><rect x=${g.cx - boxW / 2 - 4} y=${top} width=${boxW + 8} height=${g.height}></rect></clipPath>
        <filter id="halo-${m.uid}" x="-10%" y="-10%" width="120%" height="120%">
          <feMorphology in="SourceAlpha" operator="dilate" radius="1.2" result="grown"></feMorphology>
          <feFlood flood-color=${halo} flood-opacity="0.8"></feFlood>
          <feComposite in2="grown" operator="in" result="ring"></feComposite>
          <feMerge><feMergeNode in="ring"></feMergeNode><feMergeNode in="SourceGraphic"></feMergeNode></feMerge>
        </filter>
      </defs>
      <g clip-path="url(#reveal-${m.uid})"><g filter="url(#halo-${m.uid})">
        <rect x=${g.cx - boxW / 2} y=${boxY} width=${boxW} height=${PART_MAX} style="fill:${tip}" mask="url(#mask-${m.uid})"></rect>
      </g></g>`;
  }
  // A generic tapered block with faint layer lines.
  const wBase = 90;
  const wTop = 64;
  const widthAt = (d: number) => wBase - ((wBase - wTop) * d) / PART_MAX;
  const far = widthAt(g.height);
  const near = wBase;
  const edge = g.base + dir * g.height;
  const pts = [
    [g.cx - near / 2, g.base],
    [g.cx + near / 2, g.base],
    [g.cx + far / 2, edge],
    [g.cx - far / 2, edge],
  ]
    .map((p) => p.join(","))
    .join(" ");
  const lines: SVGTemplateResult[] = [];
  for (let d = 7; d < g.height; d += 7) {
    const w = widthAt(d);
    const y = g.base + dir * d;
    lines.push(svg`<line x1=${g.cx - w / 2} x2=${g.cx + w / 2} y1=${y} y2=${y} class="a-layer" style="stroke:${halo}"></line>`);
  }
  return svg`<polygon points=${pts} style="fill:${tip}" class="a-part"></polygon>${lines}`;
}

function head(m: ArtModel, cx: number, top: number, sweep: boolean): SVGTemplateResult {
  const glow = m.nozzleHeat > 0 ? heatColour(m.nozzleHeat) : undefined;
  return svg`<g transform="translate(${cx} ${top})"><g class=${sweep ? "sweep" : ""}>
    <rect x="-22" y="0" width="44" height="30" rx="5" class="a-chassis solid"></rect>
    <path d="M-7 30 L7 30 L2 39 L-2 39 Z" class="a-nozzle"></path>
    ${glow ? svg`<circle cx="0" cy="39" r="6" style="fill:${glow};opacity:${0.35 + 0.65 * m.nozzleHeat}" class="a-glow"></circle>` : nothing}
  </g></g>`;
}

function lightStrip(m: ArtModel, x: number, y: number, w: number, chamber: Rect): SVGTemplateResult {
  return svg`
    <rect x=${x} y=${y} width=${w} height="4" rx="2" class=${m.lightOn ? "a-led on" : "a-led"}></rect>
    ${m.lightOn && !m.cameraInChamber
      ? svg`<defs><linearGradient id="wash-${m.uid}" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stop-color=${LIGHT} stop-opacity="0.28"></stop>
            <stop offset="1" stop-color=${LIGHT} stop-opacity="0"></stop>
          </linearGradient></defs>
          <rect x=${chamber.x} y=${y + 4} width=${chamber.w} height=${chamber.h - (y + 4 - chamber.y)} fill="url(#wash-${m.uid})"></rect>`
      : nothing}`;
}

function bedGlow(m: ArtModel, x: number, y: number, w: number): SVGTemplateResult | typeof nothing {
  if (m.bedHeat <= 0 || m.cameraInChamber) return nothing;
  return svg`<rect x=${x} y=${y} width=${w} height="5" rx="2" style="fill:${heatColour(m.bedHeat)};opacity:${0.3 + 0.7 * m.bedHeat}"></rect>`;
}

function progressHeight(m: ArtModel, max: number): number {
  if (m.progress === undefined || !Number.isFinite(m.progress) || m.progress < 0.5) return 0;
  return (Math.min(100, m.progress) / 100) * max;
}

function fdmInterior(m: ArtModel, l: ArtLayout, plateY: number, plateX: number, plateW: number, gantry: boolean) {
  const h = m.cameraInChamber ? 0 : progressHeight(m, PART_MAX);
  const parked = l.chamber.y + 12;
  const headTop = m.cameraInChamber ? parked : Math.max(parked, plateY - h - 42);
  const sweep = m.printing && !m.paused && !m.cameraInChamber;
  return svg`
    ${gantry
      ? svg`<rect x=${l.chamber.x - 10} y=${headTop + 10} width=${l.chamber.w + 20} height="8" rx="3" class="a-rail-bar"></rect>`
      : svg`<line x1=${l.chamber.x} x2=${l.chamber.x + l.chamber.w} y1=${headTop + 14} y2=${headTop + 14} class="a-rail"></line>`}
    <rect x=${plateX} y=${plateY} width=${plateW} height="6" rx="2" class="a-plate"></rect>
    ${bedGlow(m, plateX, plateY + 6, plateW)}
    ${m.cameraInChamber ? nothing : part(m, { cx: 240, base: plateY, height: h, hanging: false })}
    ${head(m, 240, headTop, sweep)}`;
}

function enclosed(m: ArtModel, l: ArtLayout): SVGTemplateResult {
  const y0 = l.y0;
  const c = l.chamber;
  const frame = `M80 ${y0 + 14} a14 14 0 0 1 14 -14 H386 a14 14 0 0 1 14 14 V${y0 + 306} a14 14 0 0 1 -14 14 H94 a14 14 0 0 1 -14 -14 Z
    M${c.x} ${c.y} V${c.y + c.h} H${c.x + c.w} V${c.y} Z`;
  return svg`
    ${m.cameraInChamber ? nothing : svg`<rect x=${c.x} y=${c.y} width=${c.w} height=${c.h} class="a-hole"></rect>`}
    ${fdmInterior(m, l, y0 + PLATE_Y.enclosed, 120, 240, false)}
    ${lightStrip(m, 110, c.y + 2, 260, c)}
    <path d=${frame} fill-rule="evenodd" class="a-chassis"></path>
    <line x1="100" x2="380" y1=${y0 + 244} y2=${y0 + 244} class="a-rail"></line>
    ${screen(110, y0 + 254, 80, 50, m)}
    <g class="a-vents">${[0, 1, 2, 3].map((i) => svg`<line x1=${220 + i * 22} x2=${220 + i * 22} y1=${y0 + 262} y2=${y0 + 296}></line>`)}</g>
    ${fan(350, y0 + 279, m.fanOn)}`;
}

function bedslinger(m: ArtModel, l: ArtLayout): SVGTemplateResult {
  const y0 = l.y0;
  const c = l.chamber;
  const plateY = y0 + PLATE_Y.bedslinger;
  return svg`
    ${fdmInterior(m, l, plateY, 140, 200, true)}
    <rect x="150" y=${plateY + 6} width="180" height=${y0 + 262 - plateY - 6} class="a-rail-bar"></rect>
    <rect x="96" y=${y0 + 10} width="14" height="252" rx="4" class="a-chassis solid"></rect>
    <rect x="370" y=${y0 + 10} width="14" height="252" rx="4" class="a-chassis solid"></rect>
    <rect x="90" y=${y0 + 6} width="300" height="16" rx="5" class="a-chassis solid"></rect>
    ${lightStrip(m, 116, y0 + 24, 248, c)}
    <rect x="80" y=${y0 + 262} width="320" height="58" rx="10" class="a-chassis"></rect>
    ${screen(98, y0 + 272, 70, 38, m)}
    ${fan(355, y0 + 291, m.fanOn)}`;
}

function resin(m: ArtModel, l: ArtLayout): SVGTemplateResult {
  const y0 = l.y0;
  const c = l.chamber;
  const vatY = y0 + PLATE_Y.resin;
  const travel = PART_MAX - 4;
  const h = m.cameraInChamber ? 0 : progressHeight(m, travel);
  const platformY = m.cameraInChamber ? c.y + 20 : vatY - 14 - h;
  return svg`
    ${m.cameraInChamber ? nothing : svg`<rect x=${c.x} y=${c.y} width=${c.w} height=${c.h} class="a-hole"></rect>`}
    <rect x="322" y=${c.y + 6} width="10" height=${vatY - c.y - 6} class="a-rail-bar"></rect>
    <path d="M300 ${platformY + 4} H327" class="a-rail"></path>
    <rect x="170" y=${platformY} width="140" height="10" rx="2" class="a-chassis solid"></rect>
    ${m.cameraInChamber ? nothing : part(m, { cx: 240, base: platformY + 10, height: h > 0 ? vatY - platformY - 10 : 0, hanging: true })}
    <rect x="140" y=${vatY} width="200" height="16" rx="3" class="a-plate"></rect>
    ${lightStrip(m, 140, c.y - 4, 200, c)}
    <rect x="120" y=${y0 + 20} width="240" height=${vatY - y0 - 20} rx="10" class="a-lid"></rect>
    <rect x="110" y=${y0 + 220} width="260" height="100" rx="10" class="a-chassis"></rect>
    ${screen(130, y0 + 246, 76, 48, m)}
    ${fan(330, y0 + 270, m.fanOn)}`;
}

function generic(m: ArtModel, l: ArtLayout): SVGTemplateResult {
  const y0 = l.y0;
  const c = l.chamber;
  return svg`
    ${m.cameraInChamber ? nothing : svg`<rect x=${c.x} y=${c.y} width=${c.w} height=${c.h} class="a-hole"></rect>`}
    ${fdmInterior(m, l, y0 + PLATE_Y.generic, 150, 180, false)}
    ${lightStrip(m, 120, y0 + 18, 240, c)}
    <path d="M100 ${y0 + 16} a6 6 0 0 1 6 -6 H374 a6 6 0 0 1 6 6 V${y0 + 304} a6 6 0 0 1 -6 6 H106 a6 6 0 0 1 -6 -6 Z
      M${c.x} ${c.y} V${c.y + c.h} H${c.x + c.w} V${c.y} Z" fill-rule="evenodd" class="a-chassis"></path>
    ${screen(118, y0 + 266, 60, 34, m)}
    ${fan(348, y0 + 283, m.fanOn)}`;
}

/** The whole drawing. The chamber is left open while the camera plays behind it. */
export function renderArt(m: ArtModel, layout: ArtLayout): SVGTemplateResult {
  const bodyArt =
    m.body === "enclosed"
      ? enclosed(m, layout)
      : m.body === "bedslinger"
        ? bedslinger(m, layout)
        : m.body === "resin"
          ? resin(m, layout)
          : generic(m, layout);
  const filament = m.body === "resin" ? nothing : m.ace.length ? aceUnits(m, layout.y0) : sideReel(m, layout.y0);
  return svg`<svg class="art" viewBox="0 0 ${layout.width} ${layout.height}" aria-hidden="true" focusable="false"
      preserveAspectRatio="xMidYMid meet">
    ${filament}
    ${bodyArt}
  </svg>`;
}

export const artStyles = css`
  .art {
    display: block;
    width: 100%;
    height: 100%;
    pointer-events: none;
    overflow: visible;
  }
  .a-chassis {
    fill: color-mix(in srgb, var(--primary-text-color) 9%, var(--ac-surface));
    stroke: var(--primary-text-color);
    stroke-width: 2;
  }
  .a-chassis.solid {
    fill: color-mix(in srgb, var(--primary-text-color) 22%, var(--ac-surface));
  }
  .a-lid {
    fill: color-mix(in srgb, var(--ac-accent) 10%, transparent);
    stroke: var(--primary-text-color);
    stroke-width: 2;
  }
  .a-hole {
    fill: var(--ac-surface);
  }
  .a-line {
    stroke: var(--primary-text-color);
    stroke-width: 1.5;
  }
  .a-rail {
    stroke: var(--ac-muted);
    stroke-width: 3;
    stroke-linecap: round;
    fill: none;
  }
  .a-rail-bar {
    fill: var(--ac-muted);
    opacity: 0.7;
  }
  .a-plate {
    fill: var(--ac-divider);
    stroke: var(--ac-muted);
    stroke-width: 1;
  }
  .a-nozzle {
    fill: var(--primary-text-color);
  }
  .a-vents line {
    stroke: var(--ac-muted);
    stroke-width: 3;
    stroke-linecap: round;
    opacity: 0.6;
  }
  .a-screen {
    fill: var(--ac-surface);
    stroke: var(--primary-text-color);
    stroke-width: 1.5;
  }
  .a-glyph path {
    fill: none;
    stroke: var(--ac-accent);
    stroke-width: 2;
    stroke-linejoin: round;
  }
  .a-fan path,
  .a-fan g > circle:not([fill]) {
    fill: var(--primary-text-color);
  }
  .a-fan {
    opacity: 0.35;
  }
  .a-fan.on {
    opacity: 1;
  }
  .a-fan .spin {
    transform-box: fill-box;
    transform-origin: center;
    animation: ac-spin 1s linear infinite;
  }
  .a-led {
    fill: ${unsafeCSS(LIGHT)};
    opacity: 0.25;
  }
  .a-led.on {
    opacity: 1;
    filter: drop-shadow(0 0 4px ${unsafeCSS(LIGHT)});
  }
  .a-reel-rim {
    fill: var(--ac-surface);
    stroke: var(--ac-muted);
    stroke-width: 1.5;
  }
  .a-reel {
    stroke: color-mix(in srgb, var(--primary-text-color) 35%, transparent);
    stroke-width: 1;
  }
  .a-reel.empty {
    fill: var(--ac-surface-2);
  }
  .a-feeding {
    fill: none;
    stroke: var(--ac-accent);
    stroke-width: 3;
  }
  .a-tube {
    fill: none;
    stroke: var(--ac-muted);
    stroke-width: 3;
    stroke-linecap: round;
    stroke-linejoin: round;
    opacity: 0.5;
  }
  .a-tube.feeding {
    stroke: var(--ac-accent);
    stroke-width: 4;
    opacity: 1;
  }
  .a-part {
    stroke: none;
  }
  .a-layer {
    stroke-width: 1;
    opacity: 0.25;
  }
  .sweep {
    animation: ac-sweep 4.5s ease-in-out infinite alternate;
  }
  @keyframes ac-sweep {
    from {
      transform: translateX(-85px);
    }
    to {
      transform: translateX(85px);
    }
  }
  @keyframes ac-spin {
    to {
      transform: rotate(360deg);
    }
  }
  @media (prefers-reduced-motion: reduce) {
    .sweep,
    .a-fan .spin {
      animation: none;
    }
  }
`;
