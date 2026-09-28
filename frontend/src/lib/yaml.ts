// YAML for the panel's preset gallery (FRONTEND.md §4.15).

function scalar(value: unknown): string {
  if (typeof value === "string") {
    // Quote anything YAML could read as another type or that has special characters.
    if (value === "" || /^[\s\-?:,[\]{}#&*!|>'"%@`]|: |\s#|\s$/.test(value) || /^(true|false|null|yes|no|on|off|~|[-+.\d].*)$/i.test(value)) {
      return JSON.stringify(value);
    }
    return value;
  }
  return String(value);
}

export function cardYaml(config: Record<string, unknown>): string {
  const lines = ["type: custom:anycubic-card"];
  for (const [key, value] of Object.entries(config)) {
    if (key === "type" || value === undefined || value === null) continue;
    if (Array.isArray(value)) {
      if (value.length === 0) {
        lines.push(`${key}: []`);
      } else {
        lines.push(`${key}:`);
        for (const item of value) lines.push(`  - ${scalar(item)}`);
      }
    } else {
      lines.push(`${key}: ${scalar(value)}`);
    }
  }
  return lines.join("\n");
}
