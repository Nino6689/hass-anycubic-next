import { svg, type SVGTemplateResult } from "lit";

/** An inline Material Design icon (path data from @mdi/js). */
export function icon(path: string, size = 24): SVGTemplateResult {
  return svg`<svg class="mdi" viewBox="0 0 24 24" width=${size} height=${size} aria-hidden="true" focusable="false"><path d=${path} fill="currentColor"></path></svg>`;
}
