/** Define a custom element only when the tag is still free; a repeat is a no-op. */
export function defineOnce(tag: string, ctor: CustomElementConstructor): void {
  if (typeof customElements === "undefined" || customElements.get(tag)) return;
  try {
    customElements.define(tag, ctor);
  } catch {
    // Another copy of the bundle won the race; the tag is served by it.
  }
}

/** Dispatch a composed, bubbling custom event (how Home Assistant elements talk). */
export function fire<T>(node: EventTarget, type: string, detail?: T): void {
  node.dispatchEvent(new CustomEvent(type, { detail, bubbles: true, composed: true }));
}

/** Navigate inside the Home Assistant app without reloading. */
export function navigate(path: string, replace = false): void {
  if (replace) window.history.replaceState(null, "", path);
  else window.history.pushState(null, "", path);
  fire(window, "location-changed", { replace });
}

/** Ask the companion app for a short vibration, where supported. */
export function haptic(kind: "light" | "success" | "failure" = "light"): void {
  fire(window, "haptic", kind);
}

/** Copy text; works on plain-http installs where the async clipboard API is missing. */
export async function copyText(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    // fall through to the legacy path
  }
  const area = document.createElement("textarea");
  area.value = text;
  area.setAttribute("readonly", "");
  area.style.position = "fixed";
  area.style.opacity = "0";
  document.body.appendChild(area);
  area.select();
  let ok = false;
  try {
    ok = document.execCommand("copy");
  } catch {
    ok = false;
  }
  area.remove();
  return ok;
}
