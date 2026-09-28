import { describe, expect, it } from "vitest";
import { Printer, chooseCamera, commonPrefix, entitySet, findPrinters, resolveEntityId } from "../src/lib/entities";
import { device, hassWith } from "./fixtures";

const printer = device("p1", { name: "Kobra" });
const ace = device("a1", { via_device_id: "p1", name: "Kobra ACE Pro" });
const other = device("p2", { name: "Second" });

function sample() {
  return hassWith(
    [printer, ace, other, device("scan", { name: "Scanner copy" })],
    [
      { id: "sensor.kobra_drucker_status", device: "p1", key: "current_status", state: "available", attrs: { material_type: "Filament" } },
      { id: "sensor.kobra_job_state", device: "p1", key: "job_state", state: "printing" },
      { id: "binary_sensor.kobra_online", device: "p1", key: "printer_online", state: "on" },
      { id: "switch.kobra_ace_pro_auffullen", device: "a1", key: "multi_color_box_runout_refill", state: "off" },
      { id: "button.kobra_ace_pro_trocknen_1", device: "a1", key: "drying_start_preset_1", state: "unknown" },
      { id: "sensor.second_job_state", device: "p2", key: "job_state", state: "idle" },
      { id: "sensor.scanner_thing", device: "scan", key: null, state: "1", platform: "nmap" },
      { id: "camera.kobra_camera", device: "p1", key: "camera", state: "idle" },
      { id: "camera.kobra_cloud_camera", device: "p1", key: "cloud_camera", state: "idle" },
    ],
  );
}

describe("findPrinters", () => {
  it("offers only Anycubic top-level devices that carry integration entities", () => {
    expect(findPrinters(sample()).map((d) => d.id)).toEqual(["p1", "p2"]);
  });
  it("rejects other manufacturers", () => {
    const h = hassWith([device("x", { manufacturer: "Anycubic Inc" })], [{ id: "sensor.a", device: "x", key: "job_state", state: "1" }]);
    expect(findPrinters(h)).toEqual([]);
  });
  it("copes with a missing hass", () => {
    expect(findPrinters(undefined)).toEqual([]);
  });
});

describe("entity set and lookup", () => {
  it("includes child devices", () => {
    const set = entitySet(sample(), "p1");
    expect(set.deviceIds).toEqual(["p1", "a1"]);
    expect(set.entityIds).toContain("switch.kobra_ace_pro_auffullen");
    expect(set.entityIds).not.toContain("sensor.second_job_state");
  });

  it("matches by translation key regardless of the entity id language", () => {
    const h = sample();
    const set = entitySet(h, "p1");
    expect(resolveEntityId(h, set, "current_status", "sensor")).toBe("sensor.kobra_drucker_status");
    expect(resolveEntityId(h, set, "multi_color_box_runout_refill", "switch")).toBe("switch.kobra_ace_pro_auffullen");
    expect(resolveEntityId(h, set, "drying_start_preset_1", "button")).toBe("button.kobra_ace_pro_trocknen_1");
  });

  it("never crosses printers", () => {
    const h = sample();
    expect(resolveEntityId(h, entitySet(h, "p1"), "job_state", "sensor")).toBe("sensor.kobra_job_state");
    expect(resolveEntityId(h, entitySet(h, "p2"), "job_state", "sensor")).toBe("sensor.second_job_state");
  });

  it("respects the domain", () => {
    const h = sample();
    expect(resolveEntityId(h, entitySet(h, "p1"), "job_state", "binary_sensor")).toBeUndefined();
  });

  it("uses the corrected keys, not the 2.x names", () => {
    const h = sample();
    const set = entitySet(h, "p1");
    expect(resolveEntityId(h, set, "ace_run_out_refill", "switch")).toBeUndefined();
    expect(resolveEntityId(h, set, "drying_preset_1", "button")).toBeUndefined();
  });

  it("treats disabled (absent from the list) and state-less entities as missing", () => {
    const h = sample();
    delete h.states["sensor.kobra_job_state"];
    expect(resolveEntityId(h, entitySet(h, "p1"), "job_state", "sensor")).toBeUndefined();
  });

  it("breaks ties with the common prefix", () => {
    const h = hassWith(
      [printer],
      [
        { id: "sensor.kobra_a", device: "p1", key: "a", state: "1" },
        { id: "sensor.renamed_job_state", device: "p1", key: "job_state", state: "x" },
        { id: "sensor.kobra_job_state", device: "p1", key: "job_state", state: "y" },
        { id: "sensor.kobra_b", device: "p1", key: "b", state: "1" },
      ],
    );
    const set = entitySet(h, "p1");
    expect(set.prefix).toBe("");
    // no usable prefix: the first match wins
    expect(resolveEntityId(h, set, "job_state", "sensor")).toBe("sensor.renamed_job_state");
    const h2 = hassWith(
      [printer],
      [
        { id: "sensor.kobra_s1_x_job_state", device: "p1", key: "job_state", state: "x" },
        { id: "sensor.kobra_s1_job_state", device: "p1", key: "job_state", state: "y" },
        { id: "sensor.kobra_s1_b", device: "p1", key: "b", state: "1" },
      ],
    );
    expect(entitySet(h2, "p1").prefix).toBe("kobra_s1_");
  });

  it("falls back to the id suffix only for entities without a translation key", () => {
    const h = hassWith(
      [printer],
      [
        { id: "sensor.kobra_job_name", device: "p1", key: undefined, state: "cube" },
        { id: "sensor.kobra_other_job_name", device: "p1", key: "something_else", state: "x" },
      ],
    );
    expect(resolveEntityId(h, entitySet(h, "p1"), "job_name", "sensor")).toBe("sensor.kobra_job_name");
  });

  it("commonPrefix", () => {
    expect(commonPrefix(["sensor.kobra_s1_a", "switch.kobra_s1_b"])).toBe("kobra_s1_");
    expect(commonPrefix(["sensor.abc"])).toBe("");
    expect(commonPrefix([])).toBe("");
  });
});

describe("Printer helpers", () => {
  it("reads values and hides unknown/unavailable", () => {
    const p = new Printer(sample(), "p1");
    expect(p.name).toBe("Kobra");
    expect(p.configEntry).toBe("entry-p1");
    expect(p.value("job_state")).toBe("printing");
    expect(p.value("drying_start_preset_1", "button")).toBeUndefined();
    expect(p.usable("drying_start_preset_1", "button")).toBe(true);
    expect(p.isOn("printer_online")).toBe(true);
    expect(p.isFilament).toBe(true);
    expect(p.num("job_state")).toBeUndefined();
  });
  it("an unknown device gives an empty printer that never throws", () => {
    const p = new Printer(sample(), "gone");
    expect(p.exists).toBe(false);
    expect(p.value("job_state")).toBeUndefined();
    expect(p.camera()).toBeUndefined();
    expect(new Printer(undefined, undefined).value("x")).toBeUndefined();
  });
  it("falls back to the first config entry", () => {
    const h = hassWith([device("p9", { primary_config_entry: null, config_entries: ["e1", "e2"] })], []);
    expect(new Printer(h, "p9").configEntry).toBe("e1");
  });
});

describe("chooseCamera", () => {
  it("prefers the local camera and flags the cloud one", () => {
    const h = sample();
    const set = entitySet(h, "p1");
    expect(chooseCamera(h, set)).toEqual({ entityId: "camera.kobra_camera", isCloud: false, available: true });
    h.states["camera.kobra_camera"].state = "unavailable";
    expect(chooseCamera(h, set)).toEqual({ entityId: "camera.kobra_cloud_camera", isCloud: true, available: true });
    h.states["camera.kobra_cloud_camera"].state = "unavailable";
    expect(chooseCamera(h, set)?.entityId).toBe("camera.kobra_camera");
  });
  it("uses an override even outside the set", () => {
    const h = sample();
    expect(chooseCamera(h, entitySet(h, "p1"), "camera.garage_cloud_camera")).toEqual({
      entityId: "camera.garage_cloud_camera",
      isCloud: true,
      available: true,
    });
  });
  it("none without cameras", () => {
    const h = sample();
    expect(chooseCamera(h, entitySet(h, "p2"))).toBeUndefined();
  });
});
