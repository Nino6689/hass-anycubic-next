# Frontend specification — `anycubic_cloud` 3.0

Functional specification of the sidebar panel and the dashboard card that ship with the
integration. Written by the specification team on 2026-09-28 from the 2.9.x frontend
(`anycubic-cloud-frontend` 0.2.1, panel source 0.2.2) and the integration code that serves it.

This document states **behaviour, data and requirements only**. It contains no code, styles or
markup from 2.x, and the implementation team must not go looking for them (see
[`CLEAN-ROOM.md`](CLEAN-ROOM.md)). Where 2.x behaves badly, the defect is called out and the
required 3.0 behaviour is stated. Anything the specification team could not confirm is marked
**(to verify)**; ask in [`QUESTIONS.md`](QUESTIONS.md).

Words: **must** = compatibility or correctness requirement; **should** = the 2.x behaviour worth
keeping, which may be improved; **may** = free choice.

Related: entity keys, attributes and actions are defined in [`COMPAT.md`](COMPAT.md). This
document refers to entities by their **key** (the unique-id suffix in COMPAT §3).

---

## 1. Delivery and registration

### 1.1 What the integration must serve

| Item | Requirement |
|---|---|
| Static URL prefix | `/anycubic-cloud-panel-static` — **must** stay. Users who added the card as a dashboard resource by hand reference `/anycubic-cloud-panel-static/anycubic-card.js`. |
| Card bundle | Served at `/anycubic-cloud-panel-static/anycubic-card.js` — stable filename, **must** stay. |
| Panel bundle | Served under the same prefix with a content hash in its **filename** (2.x: `entrypoint.<8 hex>.js`). The exact name is free; only the integration refers to it. |
| Cache headers | 2.x serves the directory with caching disabled at the HTTP layer and relies on changing URLs (see 1.4). 3.0 may do the same. |
| Where the files live | 2.x ships the built bundles in a separate PyPI package because Home Assistant core does not accept frontend assets inside an integration; the integration asks that package for its directory, its entrypoint filename and its web-component name. 3.0 may keep that pattern with **its own, newly named** package (the 2.x package is GPL and on the excluded list), or bundle the files for the HACS release. **(to verify: package name and delivery choice for 3.0)** |
| Multi-printer safety | Several config entries set up concurrently. Registering the static path twice must not fail an entry: if registration raises because the path is already routed, check that the path really is being served and carry on; re-raise only if it is not. Do not decide this by parsing the exception text. |

### 1.2 Sidebar panel

| Property | Value |
|---|---|
| Registration | Home Assistant's custom-panel mechanism, loading the panel bundle as an ES module |
| Frontend URL path | `anycubic_cloud` (the panel lives at `/anycubic_cloud`). **Should** stay — users bookmark `/anycubic_cloud/<device id>/<page>`. |
| Web component name | `anycubic-cloud-panel` in 2.x (may change; nothing persistent stores it) |
| Sidebar title | `Anycubic Cloud & LAN` (not localised) |
| Sidebar icon | `mdi:printer-3d` |
| Admin only | No — every user sees it |
| Panel config | The `card_config` object from the entry's options (see 2.6), passed as the panel's config |
| Count | One panel for the whole integration, however many printers/entries |

Lifecycle requirements:

1. Register the panel **and the card** at the start of entry setup, **before** the first data
   refresh. A printer that is offline, an expired token or a cloud outage must not stop the card's
   JavaScript reaching the browser — otherwise every dashboard shows "Custom element not found"
   instead of an unavailable card.
2. When a second entry finds the panel already registered (including the race where two entries
   pass the "already registered?" check at once and the loser's registration raises), treat it as
   success. Decide by asking the frontend's panel registry, not by reading the error message.
3. On unload, remove the panel **only if no other entry of the domain is still loaded**. Unloading
   or reloading one printer must not take the sidebar away from the others.
4. Because only the first entry to register passes its config, the panel uses the `card_config`
   of whichever entry set up first. **(to verify: keep this, or merge / pick deterministically)**

### 1.3 Card registration

| Property | Value |
|---|---|
| Custom element | `anycubic-card` — **must** stay (`type: custom:anycubic-card` is stored in users' dashboards) |
| How the browser gets it | The integration adds the card bundle as an "extra JS module URL" on the frontend, so it loads on every page without the user adding a resource |
| Card picker entry | The bundle registers itself in the frontend's custom-card list: type `anycubic-card`, name `Anycubic Card`, description `Anycubic Cloud Integration Card`, live preview enabled. Searching "Anycubic" in *Add card → By card* finds it. |
| Visual editor | Provided (element `anycubic-card-editor` in 2.x; name is free). See 2.5. |
| Stub config | When added from the picker: `{ printer_id: <device id of the first printer found> }` (printer discovery rule in 3.1) |
| Card size (masonry) | 4 when `mediaView: none`, otherwise 8 |
| Grid options (sections view) | 12 columns by default, minimum 6 columns, rows automatic |

**Double-load tolerance (must).** The same card bundle can be loaded twice in one document — once
from the integration's hashed URL and once from a hand-added resource — and the panel bundle also
contains the card's inner components. Every custom element must therefore be defined only if the
tag is not already defined; a second definition attempt must be a silent no-op, never an error.

Both bundles print a one-line version banner to the browser console on load (cosmetic; may keep).

### 1.4 Cache-busting

| Bundle | Mechanism |
|---|---|
| Panel | Content hash **in the filename**; the integration registers the panel with the hashed name, so a new build is a new URL. |
| Card | Stable filename (for hand-added resources); the integration's extra-JS URL carries the hash as a query string, `anycubic-card.js?v=<hash>`. |
| Hash | 2.x: the first 8 hex characters of the SHA-256 of the built file. Panel and card hashes are computed **separately**, because a card-only change leaves the panel file unchanged and reusing its hash would leave browsers on the old card. |

Build tooling must keep the hashes, the filenames and whatever the integration reads them from in
agreement automatically; a mismatch either 404s the panel or serves a stale card.

---

## 2. Card configuration schema

### 2.1 General rules

- The card accepts the configuration object unchanged and **must not mutate** the object it is
  given (the dashboard editor treats a mutated object as a user edit). Work on a copy.
- Every key is optional. Unknown keys **must** be ignored, never rejected — this includes
  Home Assistant's own layout keys (`grid_options`, `view_layout`, `visibility`, …).
- There is no validation error path in 2.x; a bad value falls back to the default where noted.
- Defaults are applied at render time; they are not written back into the config.

### 2.2 Keys (hard compatibility requirement — all must be accepted unchanged)

19 keys plus the standard `type`.

| # | Key | Type | Default (card) | Effect |
|---|---|---|---|---|
| — | `type` | string | — | Always `custom:anycubic-card` |
| 1 | `printer_id` | string | none | **Home Assistant device-registry id** of the printer device (not the Anycubic printer id). Selects the printer and, through it, all its entities. Missing or unknown id: the card renders with no data (see 4.13). |
| 2 | `vertical` | bool | `false` | Forces the stacked layout (hero above summary) even when the card is wide. |
| 3 | `round` | bool | `true` | Rounds temperatures to whole degrees (otherwise two decimals), progress to a whole percent, and durations to minutes. |
| 4 | `use_24hr` | bool | `true` | ETA clock format: 24-hour vs 12-hour with am/pm. |
| 5 | `temperatureUnit` | `"C"` \| `"F"` | `"C"` | Unit temperatures are **displayed** in; values are converted from the entity's own unit. |
| 6 | `lightEntityId` | entity id (string) | none | Adds a light toggle to the header. Any light entity — typically the printer's own `printer_light`, but not assumed. |
| 7 | `powerEntityId` | entity id (string) | none | Adds a power toggle to the header — meant for the user's own smart plug; the printer offers no power entity. |
| 8 | `cameraEntityId` | entity id (string) | auto | Overrides which camera the hero uses (see 3.7). |
| 9 | `monitoredStats` | list of stat names | `[Status, ETA, Elapsed, Remaining]` | The stat rows, **in list order**. Values in 2.3. An empty list shows no rows. |
| 10 | `scaleFactor` | number | `1` | In the side-by-side layout, the relative width of the hero column against the summary column (hero : summary = factor : 1). Zero, negative or missing → 1. The editor offers 1, 0.75 and 0.5, but any positive number must work. |
| 11 | `slotColors` | list of CSS colour strings | `[]` | Preset swatches offered in the spool editor (4.11). |
| 12 | `showSettingsButton` | bool | `false` | Shows the *Print settings* button even when no job is running. |
| 13 | `alwaysShow` | bool | `false` | When false, the card body collapses unless a job is running (4.1). |
| 14 | `mediaView` | enum (2.3) | `auto` | Which hero surface opens first; `none` hides the hero. |
| 15 | `printerArt` | enum (2.3) | `auto` | Which chassis the printer artwork draws. Unrecognised values behave as `auto`. |
| 16 | `showMoveButtons` | bool | `false` (see 2.4) | Shows the jog/move pad inline under the controls. |
| 17 | `showControls` | bool | `true` | Shows the controls row (pause/resume/cancel/print settings). |
| 18 | `sections` | list of section names | `[filament]` | Which collapsible sections to offer: `filament`, `insights`. Legacy value `move` (2.4). Rendering order is fixed (Filament, then Insights) regardless of list order. |
| 19 | `noCamera` | bool | `false` | Never start any camera stream, whatever `mediaView` says. For galleries, wall panels and second dashboards that must not take the stream from the phone app. **2.x defect:** documented in the README but the `anycubic-card` element never passes it on, so it has no effect from YAML. 3.0 **must** honour it. |

### 2.3 Enumerated values

**`monitoredStats` values** (exact strings, including spaces and capitals — stored in dashboards):

| Value | Group | Row shows |
|---|---|---|
| `Status` | general | Job state, or the printer status when no job state is known (4.7) |
| `ETA` | time | Clock time the job should finish |
| `Elapsed` | time | Time spent on the job, ticking |
| `Remaining` | time | Time left, counting down |
| `Online` | general | Online / Offline |
| `Availability` | general | Printer status text |
| `Project` | general | Job name |
| `Layer` | general | Current layer number |
| `Hotend` | FDM | Current nozzle temperature |
| `Bed` | FDM | Current bed temperature |
| `T Hotend` | FDM | Target nozzle temperature |
| `T Bed` | FDM | Target bed temperature |
| `Dry Status` | FDM / ACE | Drying / Not drying (first ACE) |
| `Dry Time` | FDM / ACE | Drying time left, with a bar (first ACE) |
| `Speed Mode` | FDM | Current print speed mode name |
| `Fan Speed` | FDM | Part-fan percentage |
| `On Time` | resin | Exposure on-time, seconds |
| `Off Time` | resin | Off-time, seconds |
| `Bottom Time` | resin | Bottom exposure, seconds |
| `Model Height` | resin | Model height, mm |
| `Bottom Layers` | resin | Bottom layer count |
| `Z Up Height` | resin | Lift height, mm |
| `Z Up Speed` | resin | Lift speed (no unit) |
| `Z Down Speed` | resin | Retract speed (no unit) |

A value not in this list renders a placeholder "unknown" row in 2.x. **(to verify: 3.0 should
probably skip unknown values silently)**

**`mediaView`:** `auto`, `camera`, `preview`, `printer`, `printer_model`, `none` (meanings in 4.4).

**`printerArt`:** `auto`, `kobra_s1`, `kobra_s1_combo`, `kobra_3`, `resin`, `fdm` (meanings in 4.5).

**`sections`:** `filament`, `insights`; legacy `move`.

**`temperatureUnit`:** `C`, `F`.

### 2.4 Defaults and migration

- `showMoveButtons` absent **and** `sections` contains `move` → treat `showMoveButtons` as `true`.
  (Move used to be a collapsible section; configs saved then must keep their move pad.) If
  `showMoveButtons` is present as a boolean it always wins. `move` in `sections` is otherwise
  ignored — it never renders a section.
- Everything else: absent → the default in 2.2. There is no other migration.

### 2.5 Visual editor

Three tabs. The **Colours** tab appears only when the selected printer has an ACE (primary
`ace_spools` state is `active`). Labels and helper texts are localised (keys in 5.3).

**Main tab** — a Home Assistant form, fields in this order:

| Field | Control | Options |
|---|---|---|
| `printer_id` | single-select dropdown | Each discovered printer (3.1), label = device name, value = device id |
| `vertical` | toggle | |
| `round` | toggle | |
| `use_24hr` | toggle | |
| `temperatureUnit` | single-select list | `C` shown as °C, `F` shown as °F |
| `alwaysShow` | toggle | |
| `showSettingsButton` | toggle | |
| `scaleFactor` | single-select list | 1, 0.75, 0.5 |
| `lightEntityId` | entity picker, domain `light` | helper text explains it is for any light |
| `powerEntityId` | entity picker, domain `switch` | helper text explains it is for the user's own smart plug, so an empty list is normal |
| `cameraEntityId` | entity picker, domain `camera` | helper text explains it overrides the automatic choice |
| `mediaView` | dropdown | the six values, localised labels |
| `printerArt` | dropdown | the six values, localised labels |
| `showControls` | toggle | |
| `showMoveButtons` | toggle | |
| `sections` | multi-select list | `filament`, `insights` (localised labels) |

**Stats tab** — a checklist of stat names that can be ticked on/off and reordered (up/down per
ticked row); ticked rows first, in chosen order, then unticked ones. The list offered depends on
the printer: general + time stats always; plus the FDM group for filament printers or the resin
group for resin printers (by `current_status` attribute `material_type`: `Filament` / `Resin`);
plus the ACE group when an ACE is present. (The FDM group already contains the two drying stats.)
Initial ticks come from the current `monitoredStats`; values not offered are dropped. Row labels
are the raw stat names in 2.x (not localised).

**Colours tab** — `slotColors` as a list of free-text entries.

**Saving.** Each change emits the new config. 2.x strips any **scalar** key whose value equals the
card default before emitting (lists are always kept). The editor applies defaults, including the
`move` migration, to its own copy only.

### 2.6 The `card_config` option (panel settings)

The options flow step `card_config` holds one free-form object. It configures the **panel's** hero
card, not dashboard cards. 2.x keeps only these keys, silently discarding everything else:

| Key | Accepted type |
|---|---|
| `vertical`, `round`, `use_24hr`, `showSettingsButton`, `alwaysShow` | boolean |
| `temperatureUnit`, `lightEntityId`, `powerEntityId`, `cameraEntityId` | string |
| `monitoredStats`, `slotColors` | list of strings (a bare string is also passed through) |
| `scaleFactor` | float |

2.x quirks: a value is kept only if it is truthy, so a stored `false`, `0` or empty list is
dropped and the panel's own default (below) applies instead; an integer `scaleFactor` (e.g. `1`)
fails the float check and is dropped. `mediaView`, `printerArt`, `showControls`,
`showMoveButtons`, `sections` and `noCamera` are read by the panel but can never arrive through this
option. 3.0 **must** read existing stored `card_config` objects without error. **(to verify: whether
3.0 honours stored `false` values and integer `scaleFactor`, and whether it passes the newer keys
through)**

Panel defaults for its hero card (differ from the card's):

| Key | Panel default |
|---|---|
| `vertical` | false |
| `round`, `use_24hr` | true |
| `showSettingsButton` | **true** |
| `alwaysShow` | **true** |
| `mediaView` / `printerArt` | auto |
| `showControls` | true |
| `showMoveButtons` | **true** |
| `sections` | `[filament]` |
| `monitoredStats` | depends on the printer — see 4.15 |

---

## 3. Entity resolution

### 3.1 Finding printers

A device is offered as a printer (panel printer list, editor dropdown, stub config) when **all**
hold:

1. its manufacturer is exactly `Anycubic`;
2. it has no parent device (`via_device` unset) — ACE units are children and must never be offered;
3. at least one entity whose integration/platform is `anycubic_cloud` belongs to it (a network
   scanner can register its own "Anycubic" device for the same printer; offering that yields a
   blank card).

### 3.2 A printer's entity set

The printer's device **plus every device whose parent is that printer** (its ACE units). All
entities attached to any of those devices form the set every lookup searches. 2.x reads this from
the frontend's entity-registry display list and device registry, both available on the `hass`
object without extra requests. (Disabled entities are, as far as known, absent from that list —
**to verify** — so the frontend must treat a disabled entity as missing.)

### 3.3 The lookup rule

History: until frontend 0.2.0 lookups matched the **English entity-id suffix** (e.g. an id ending
`_printer_online`). An entity id is derived once, when the entity is first created, from its name
as translated into whatever language Home Assistant was running then — so on German, French,
Dutch… installs nothing matched and cards went blank; moving the ACE
to its own device also added an infix that broke suffix matching on fresh English installs. 0.2.0
switched to the integration's own identity.

Required rule for 3.0:

1. **Match by translation key.** An entity matches a lookup for key *K* in domain *D* when its
   entity id is in domain *D* and its registry `translation_key` equals *K*. The integration
   **must** set `translation_key` equal to the entity's key (the unique-id suffix in COMPAT §3)
   for every entity — true for every entity in 2.x — because the frontend has no other stable,
   language-independent identity available.
2. **Search only the printer's entity set** (3.2), so two printers never cross.
3. If two entities match (should not happen), prefer one whose object id starts with the set's
   common prefix (longest common prefix of the set's object ids, cut back to the last underscore);
   otherwise take the first match. The prefix is a tie-breaker only, never a filter, and an empty
   prefix is fine.
4. Entity-id suffix matching may remain as a last-resort fallback but must never be required.
5. Never build an entity id by concatenating strings. If a lookup finds nothing, the element that
   needs it is hidden or disabled; it must not call a service on a guessed id.

**Legacy lookup names.** 2.x internally used some names that differ from the integration's keys
and aliased them. The rebuild should simply use the integration keys; the pairs are listed so
nothing is missed:

| 2.x frontend name | Integration key |
|---|---|
| `nozzle_temperature` | `curr_nozzle_temp` |
| `hotbed_temperature` | `curr_hotbed_temp` |
| `target_nozzle_temperature` | `target_nozzle_temp` |
| `target_hotbed_temperature` | `target_hotbed_temp` |
| `fan_speed` | `fan_speed_pct` |
| `drying_active` | `dry_status_is_drying` |
| `drying_remaining_time` | `dry_status_remaining_time` |
| `drying_total_duration` | `dry_status_total_duration` |
| `job_preview` | `job_image_url` |
| `printer_firmware` | `fw_version` |
| `ace_firmware` | `multi_color_box_fw_version` |

**2.x lookups that never matched the integration key** (so they only ever worked, if at all, via
English id text). 3.0 must use the correct key:

| Element | 2.x looked for | Correct key |
|---|---|---|
| Run-out refill toggle (Filament section) | `ace_run_out_refill` / `secondary_ace_run_out_refill` | `multi_color_box_runout_refill` / `secondary_multi_color_box_runout_refill` (switch) |
| Drying preset buttons (drying dialog) | `drying_preset_N` / `secondary_drying_preset_N` | `drying_start_preset_N` / `secondary_drying_start_preset_N` (button), N = 1–4 |

### 3.4 What the frontend needs from the integration (beyond COMPAT)

| Need | Detail |
|---|---|
| Device manufacturer | exactly `Anycubic` on printer and ACE devices |
| Printer device `model` | the printer's model name (drives artwork detection); falls back to the device name |
| Printer device `sw_version` | firmware version (panel Machine group) |
| Printer device `serial_number` | the Anycubic printer id as text (panel Diagnostics) |
| Printer device connections | the MAC as the first connection (panel Diagnostics) |
| ACE device | `via_device` = the printer |
| `current_status` attribute `material_type` | `Filament` or `Resin` — decides FDM vs resin UI |
| `ace_spools` / `secondary_ace_spools` state | `active` when that unit reports spools, `inactive` otherwise |
| `ace_spools` attribute `spool_info` | list, one item per slot: `material_type` (string), `color` ([r,g,b] 0–255), `color_hex` (string), `spool_loaded` (bool), `consumables_percent` (0–100 or null), `slot` (1-based), plus others the UI ignores |
| `ace_spools` attribute `box_info` | object with `loaded_slot` (1-based slot feeding the printer, or null when none / external spool) |
| `job_speed_mode` attributes | `available_modes` (list of `{mode: int, description: string}`), `print_speed_mode_code` (int) |
| `target_nozzle_temp` / `target_hotbed_temp` attributes | `limit_min`, `limit_max` (numbers) |
| `mqtt_connection_active` attribute | `supports_mqtt_login` (bool) |
| `file_list_local` / `file_list_udisk` / `file_list_cloud` attribute | `file_info`: list of `{name, size_mb}`; cloud items also carry `id` (int) |
| Drying preset buttons `drying_start_preset_N` | attributes `duration` (minutes) and `temperature` (°C) |
| `job_image_url` image entity | standard image entity; the UI fetches it through Home Assistant's image proxy with the entity's `access_token` attribute |
| `axis_step` select | standard select with `options` attribute |

### 3.5 Entity keys each UI element reads

| UI element | Keys (domain) |
|---|---|
| Header state, status colour, "printing" flag | `job_state` (sensor), `printer_online` (binary_sensor), `current_status` (sensor) |
| Progress block | `job_progress`, `job_current_layer`, `job_total_layers` (sensors) |
| Hero preview tab | `job_image_url` (image) |
| Hero camera | every `camera.*` entity in the set; `cloud_camera` / `camera` keys |
| Artwork | `job_progress`, `job_state` (sensors); `job_is_paused` (binary_sensor); `printer_light` (light); `ace_spools`, `secondary_ace_spools` (sensors, attributes); `curr_nozzle_temp`, `target_nozzle_temp`, `curr_hotbed_temp`, `target_hotbed_temp`, `fan_speed_pct` (sensors); device model |
| Stats rows | `job_state`, `current_status`, `job_time_elapsed`, `job_time_remaining`, `curr_*`/`target_*` temps, `printer_online`, `job_name`, `job_current_layer`, `job_speed_mode`, `fan_speed_pct`, `dry_status_is_drying`, `dry_status_remaining_time`, `dry_status_total_duration`, `job_on_time`, `job_off_time`, `job_bottom_time`, `job_model_height`, `job_bottom_layers`, `job_z_up_height`, `job_z_up_speed`, `job_z_down_speed` |
| Controls row | `pause_print`, `resume_print`, `cancel_print` (buttons) |
| Move pad | `axis_step` (select); `axis_moving`, `axis_move_failed` (binary_sensors); `axis_home_all`, `axis_home_xy`, `axis_home_z`, `axis_motors_off`, `axis_move_x_plus`, `axis_move_x_minus`, `axis_move_y_plus`, `axis_move_y_minus`, `axis_move_z_plus`, `axis_move_z_minus` (buttons) |
| Filament section | `ace_spools` / `secondary_ace_spools`; `multi_color_box_runout_refill` / `secondary_multi_color_box_runout_refill` (switch) |
| Drying dialog | `drying_start_preset_1..4`, `drying_stop` and their `secondary_` forms (buttons) |
| Insights section | `job_cost`, `last_job_cost`, `filament_cost_total`, `job_filament_required`, `job_filament_shortfall`, `nozzle_wear_percent`, `spool_inventory_remaining` (sensors); `job_filament_insufficient` (binary_sensor) |
| Print settings dialog | `current_status`, `fan_speed_pct`, `target_nozzle_temp`, `target_hotbed_temp`, `job_speed_mode` (sensors); `pause_print`, `resume_print`, `cancel_print` (buttons) |
| Panel Machine / ACE groups | `fw_version`, `multi_color_box_fw_version` (update); `is_available`, `printer_online`, `dry_status_is_drying` (binary_sensors); `dry_status_remaining_time`, `dry_status_total_duration` (sensors) |
| Panel file tabs | `file_list_local`, `file_list_udisk`, `file_list_cloud` (sensors); `request_file_list_local`, `request_file_list_udisk`, `request_file_list_cloud` (buttons); `mqtt_connection_active` (binary_sensor) |

A missing, `unknown` or `unavailable` entity always reads as "no value" (em dash, hidden row or
disabled control as described per element) — never as zero, `NaN` or an error string.

### 3.6 Actions the frontend calls

All integration actions are called with **both** `config_entry` (the printer device's primary
config entry id) **and** `device_id` (the printer's device id). 3.0 actions **must** accept both
together (COMPAT §4 says "one of"; the frontend sends two).

| Trigger | Call |
|---|---|
| Controls row, move pad, drying presets/stop, file-list refresh | `button.press` on the resolved button entity |
| Step-size chip | `select.select_option` on `axis_step` with the chosen option |
| Header light / power toggle | `homeassistant.toggle` on the configured entity |
| Run-out refill tile | `switch.toggle` on the refill switch |
| Spool editor save | `anycubic_cloud.multi_color_box_set_slot_<material, lower-case>` with `box_id` (0 or 1), `slot_number` (1–4), `slot_color_red/green/blue` (0–255) |
| Print settings | `anycubic_cloud.change_print_speed_mode` (`speed_mode` = mode code), `change_print_target_nozzle_temperature` / `change_print_target_hotbed_temperature` (`temperature`), `change_print_fan_speed` (`speed`); `change_print_aux_fan_speed` and `change_print_box_fan_speed` exist in the dialog but are hidden |
| File delete | `anycubic_cloud.delete_file_local` / `delete_file_udisk` (`filename`), `delete_file_cloud` (`file_id`) |
| Panel print tabs | `anycubic_cloud.print_and_upload_no_cloud_save` / `print_and_upload_save_in_cloud` with the form's fields |

### 3.7 Camera choice

1. Candidates: every `camera.*` entity in the printer's set. A candidate is the **cloud** camera
   when its translation key is `cloud_camera` (fallback: id ends with `cloud_camera`); otherwise it
   is the local camera. A candidate is available unless its state is `unavailable` or missing.
2. Order: local before cloud (the local stream comes straight from the printer).
3. With `cameraEntityId` set: use that entity. If it is not among the candidates it is still used,
   assumed available, and judged cloud by its id suffix.
4. Without it: the first available candidate, else the first candidate (which may be unavailable),
   else none.

---

## 4. Screens and behaviour

### 4.1 Shared derivations

**Print state string** (drives header text, status colour and several decisions):
- `job_state` lower-cased, when it is neither `unknown` nor `unavailable`;
- otherwise `offline` when `printer_online` is `off`;
- otherwise `current_status` lower-cased (`unknown` if missing).
A local-only printer (no cloud job data) therefore shows its own status rather than
"Unavailable".

**Printing** = the job state is known and is one of `printing`, `preheating`, `paused`,
`downloading`, `checking`. **Paused** = job state `paused`. **Job running** (clocks tick) =
printing and not paused.

**Status colour** (theme-appropriate hues; 2.x uses fixed amber/green/cyan/red):

| Category | States |
|---|---|
| Activity (amber) | `preheating`, `busy` |
| Printing (green) | the other printing states |
| Healthy / idle (cyan) | `operational`, `finished`, `available`, `idle`, `free` |
| Problem (red) | `unknown` and every other string (e.g. `offline`, failures, `moving`) |

(`moving` — reported while an axis jogs — falls into red in 2.x. **To verify** whether it should
be activity.)

**Collapsed body.** When `alwaysShow` is false and the printer is not printing, the body (everything
under the header) is collapsed, unless the user has tapped the header to reveal it. The tap
toggles a per-view override; printing always reveals the body. Collapse/expand animates height and
opacity over roughly a quarter second; the collapsed body is hidden from assistive tech and
ignores pointer input.

**Value formatting.**
- Unknown value: an em dash.
- Temperature: converted from the entity's unit (°C/°F; unknown unit = °C) to `temperatureUnit`;
  whole degrees when `round`, else two decimals; suffix `°C`/`°F`.
- Duration: the two most significant units from days/hours/minutes/seconds, e.g. `1d 5h`,
  `5h 3m`, `3m 12s`; minutes are dropped when days are shown and seconds when hours or days are
  shown. With `round`, seconds round **up** to the next minute and seconds are never shown. Zero is
  `0m` (round) or `0s`. Never an empty string.
- Time entities: accept `N days, HH:MM:SS`, `HH:MM:SS`, or a plain number meaning **minutes**.
- ETA: the local clock time "now + remaining" — `HH:mm` or `h:mm am/pm`, with seconds when not
  rounding — formatted in the browser's local time zone.
- Money: Intl currency format in Home Assistant's language and configured currency; with no
  currency, two decimals; with a currency Intl rejects, two decimals plus the code.

### 4.2 Card layout

Top to bottom inside one standard card surface:

1. **Header** (always visible).
2. **Body** (collapsible, 4.1):
   1. **Main area**: the **hero** (4.4) and the **summary** (progress 4.6 + stats 4.7).
   2. **Controls row** (4.8), if `showControls`.
   3. **Move pad** (4.9), if `showMoveButtons`.
   4. **Sections** (4.10), each a collapsible panel.
3. Three dialogs attached to the card (4.11), hidden until opened.

### 4.3 Header

- Left, one tappable block: a small round **status dot** in the status colour; the printer's
  **device name** (fallback text when no printer); under it the **print state string** in title
  case. Tapping toggles the collapsed body (4.1).
- Right: a **light** button (only with `lightEntityId`; bulb-on / bulb-off icon from that entity's
  `on` state, highlighted when on) and a **power** button (only with `powerEntityId`; power icon,
  no state shown). Each calls a toggle and is disabled until the call returns.

### 4.4 Hero (media area)

A rounded frame at 16:9 showing one **surface** at a time, with an overlay **tab strip** of icon
buttons at the bottom-left (only when more than one tab is available). When the printer artwork is
showing, the frame switches to 4:3 with a transparent background, and the tab strip gets a solid
backing.

**Tabs and availability**

| Tab | Offered when |
|---|---|
| Camera | a camera was chosen (3.7) and `noCamera` is false |
| Preview (the sliced job's render) | `job_image_url` exists and its image has not failed to load |
| Printer (artwork) | always |
| Printer + model | a usable preview **and** a camera both exist (without a camera, the Printer tab already shows the model) |

**Which tab is shown:** the user's tap for this view, else `mediaView` if not `auto`, else
(**auto**) Preview when usable, otherwise Printer. If the wanted tab is not available, Printer.
`mediaView: none` removes the hero entirely.

**Camera rules (must).** Each cloud-camera session consumes a one-time token, and the cloud serves
only the newest requester — so merely loading a dashboard must never pull the video away from the
phone app or slicer. Therefore: `auto` never selects the camera; a camera
starts only from a tap on its tab, from `mediaView: camera`, or from the Printer case below;
`noCamera` suppresses all of them; card-picker previews and the panel gallery never start one.

**Surfaces**

- *Camera*: Home Assistant's own camera stream element (it picks HLS or WebRTC from the entity's
  capabilities, so both local and cloud cameras work), muted, filling the frame. Messages instead
  of video: camera unavailable; video player unavailable (the element could not be loaded);
  starting video. A red **LIVE** badge sits top-right while the **cloud** camera is showing.
  Home Assistant loads its stream element lazily; 2.x forces it to load by asking the dashboard
  helpers to create a picture-entity card and discarding it **(the rebuild may find a cleaner
  way)**.
- *Preview*: the job render, fitted inside the frame. If the image fails to load (typical on a
  LAN-only connection, where the render lives in the cloud), remember that for this URL, drop the
  tab and fall back. A new URL resets the failure.
- *Printer* / *Printer + model*: the artwork (4.5). The live camera plays **inside the artwork's
  build chamber** only when the Printer surface was explicitly chosen (tab tap or
  `mediaView: printer`), the chosen camera is available, `noCamera` is false, and the surface is
  not *Printer + model*. Merely falling back to Printer (no preview) must not start the camera.
  *Printer + model* never puts the camera in the chamber; it always shows the modelled print.

### 4.5 Printer artwork

A vector drawing of the printer whose every moving or coloured part reflects a live reading. The
rebuild **must draw its own artwork** (see §6); what follows is the behaviour it
must express.

**Body selection.** `printerArt` other than `auto` forces a body. For `auto`, match the device
model (else name), case-insensitive, against this ordered list — first containing match wins:

| Model text contains | Body |
|---|---|
| `kobra s1` | Kobra S1 (enclosed) |
| `kobra 3` | Kobra 3 (open-frame bed-slinger) |
| `kobra 2` | Kobra 3 body |
| `photon` / `mono` / `m5s` / `m7` | Resin |
| `kobra` (must be last) | Kobra 3 body |
| none | Generic FDM (deliberately schematic) |

`kobra_s1_combo` means the S1 body **with at least one ACE** stacked on it even if no ACE has
reported yet — it asserts the hardware.

**Filament source (FDM bodies).**
- ACE count: 2 if the second unit reports spools, else 1 if the first does, else 0.
- 0 ACE: a single reel on a side holder outside the chassis, in the active filament colour, with a
  feed tube into the frame.
- 1 or 2 ACE: the units drawn **stacked on top of the printer** (the drawing grows taller; the
  artwork's proportions change and the frame must keep the whole drawing visible). Each unit shows
  four reels in a row in their reported colours; each reel's visible diameter shrinks toward its
  hub as the slot's **`ace_slot_N_filament_remaining_percent`** falls (for the second ACE,
  `secondary_ace_slot_N_filament_remaining_percent`; unknown = drawn full; never smaller than the hub).
  **Not** `consumables_percent`: Anycubic sends 0 for every slot, so every reel would look empty
  (DECISIONS, 'Reel fill'). The slot
  currently feeding the printer is outlined, and only the feeding unit draws its feed tube in
  filament colour. A second unit with no colours is drawn uncoloured, never as a copy of the
  first.
- Resin body: no filament path at all.

**Active (tip) colour** = the colour of the loaded slot: `box_info.loaded_slot` of the first unit
(1-based; null → slot 1). Colour from `color_hex`, else from the `[r,g,b]` `color` array; strings
may be `#RRGGBB`, `#RRGGBBAA`, `#RGB`, bare hex, `rgb()/hsl()` or a common colour name (black,
white, grey/gray, silver, red, orange, yellow, green, blue, purple, pink, brown, clear, natural,
transparent → a representative swatch). Anything else → the theme accent colour. 2.x never
computes a loaded slot on the second unit **(to verify: highlight across all eight slots)**.

**State the drawing reflects**

| Machine state | Drawing |
|---|---|
| Progress 0–100 % | Print head/gantry height follows progress (rises as the part grows); a printed part grows on the plate |
| Part shape | With a job render available, the part is the render's **silhouette** (its alpha channel), tinted in the tip colour with a contrasting thin halo so dark filament stays visible, revealed from the plate upward by progress. Without a render, a generic tapered block with faint layer lines. Nothing below ~0.5 % progress. |
| Resin | The part hangs **under** the rising build platform |
| Printing | The print head sweeps left and right continuously (about a 4–5 s cycle) |
| Part fan > 0 % | A fan glyph on the chassis spins (about one turn per second); dimmed and still when off |
| Chamber light `printer_light` on | The LED strip under the top rail is lit and casts a faint warm wash into the chamber; off, the strip stays visible but dim. Unknown/unavailable = off. |
| Heaters | Nozzle melt zone and bed heater glow, colour ramping from amber to orange-red by progress toward their **own** target: (current − 20) / (target − 20), clamped 0–1; no target = cold |
| Paused (`job_is_paused` on) | The printer's screen shows a pause symbol (amber) |
| Error (job state contains `fail` or `error`) | The screen shows a warning symbol (red) |
| Idle / printing | The screen shows the maker's logo **(to verify: trademark — whether 3.0 draws the Anycubic mark at all)** |

**Camera in the chamber.** The chamber is drawn as a hole so a video placed behind it shows
through. While the camera plays there: the head parks at the top, and nothing modelled is drawn
inside the chamber (no part, no bed glow, no light wash) so the real print is not hidden. The video
sits in the chamber at 16:9, centred, not cropped, clipped to the hole; the hole must stay aligned
with the video at every size and ACE count.

**Technical requirements.** Colours follow the Home Assistant theme (chassis = primary text colour,
accent = active-state/primary colour, rails = secondary text, plate = divider, holes = card
background); fixed colours only for the pause/error symbols, the light and heat glows. Every
internal SVG id must be unique per card instance (several cards on one page must not share clip
paths or masks). The drawing ignores pointer input and is hidden from assistive tech. Under
`prefers-reduced-motion` the sweep and fan spin stop (state stays readable from position and
opacity).

### 4.6 Progress block

Shown only when `job_progress` is a finite number ≥ 0 (a missing or unavailable entity hides it).
Contents: the percentage (clamped 0–100, rounded when `round`), `Layer X / Y` when both layer
sensors have values, and a horizontal bar filled to the percentage in the status colour (width
animates smoothly).

### 4.7 Stats rows

A vertical list, one row per `monitoredStats` entry in order: bold localised label on the left,
value on the right (wrapping if long).

| Stat | Value |
|---|---|
| `Status` | print state as in 4.1 but falling back to `current_status` (not `offline`), title case |
| `Online` | `Online` / `Offline` from `printer_online` |
| `Availability` | `current_status`, title case |
| `Project` | `job_name` |
| `Layer` | `job_current_layer` |
| `ETA` | clock time now + `job_time_remaining` (4.1) |
| `Elapsed` | `job_time_elapsed`, **ticks up once a second** while the job is running |
| `Remaining` | `job_time_remaining`, **ticks down once a second** while running, never below zero |
| `Hotend` / `Bed` / `T Hotend` / `T Bed` | temperatures (4.1) |
| `Speed Mode` | the `description` of the `available_modes` item whose `mode` equals `print_speed_mode_code`, else "Unknown" |
| `Fan Speed` | `fan_speed_pct` + `%` |
| `Dry Status` | `Drying` / `Not Drying` from the first ACE's `dry_status_is_drying` |
| `Dry Time` | `<remaining> Mins` over a bar filled to remaining ÷ total (the bar **shrinks** as drying proceeds; the panel's drying figure instead shows the elapsed share — **to verify** which is intended) |
| resin rows | raw state + unit: seconds for the three times, `mm` for heights, `layers` for bottom layers, none for speeds |

Ticking clocks restart from the entity's value every time Home Assistant pushes a state update, and
stop ticking when the job is paused or finished. The ETA row uses the remaining time, so between
updates it drifts by the elapsed seconds. **(to verify: whether 3.0 should read the `job_eta`
timestamp sensor instead)**

### 4.8 Controls row

A row of buttons, shown only if `showControls` and at least one button applies:
- While printing: **Resume** (if paused) or **Pause**, and **Cancel** (styled as destructive).
  They press the button entities directly, with **no confirmation** in 2.x. **(to verify: whether
  Cancel should confirm)** Each is disabled when its entity is missing or unavailable.
- **Print settings** (cog icon) — while printing, or always with `showSettingsButton`. Opens the
  print settings dialog.

### 4.9 Move pad

Shown when `showMoveButtons` is true.
- **Step size**: a segmented row of chips, one per `axis_step` option, the current option
  highlighted; tapping selects it. Hidden if the select is missing.
- **XY dial**: a round control split into four quadrant buttons — Y+ (top), X− (left), X+
  (right), Y− (bottom) — each with an arrow and its axis label, and a centre button **Home X/Y**.
- **Left column**: Home all axes; Release motors.
- **Right column**: Z+ (up); **Home Z** (accented); Z− (down).
- Every button presses its entity and is disabled when that entity is missing or unavailable.
- Under the pad: a "moving" note while `axis_moving` is on; otherwise a warning while
  `axis_move_failed` is on, explaining that the printer refuses Z moves until Z has been homed separately.
- Narrow viewports tighten spacing; the pad must stay usable on a phone.

### 4.10 Sections

Collapsible panels with a title and a chevron (rotates when open); at most one open at a time; all
start closed. Offered per `sections`, rendered Filament then Insights.

**Filament** — offered only when the first ACE is present (`ace_spools` = `active`). Shows one
**ACE strip** per unit (second strip when `secondary_ace_spools` = `active`). Each strip, left to
right:
- **Run-out refill** tile: label plus the switch's on/off toggle; tapping toggles the unit's refill
  switch **exactly once** per tap, ignoring taps while a call is in flight.
- **Spool rings**, one per slot in `spool_info`: a filled circle in the slot colour (neutral grey
  when `spool_loaded` is false) with the slot number on a light disc in the middle, and the material
  name below (`---` when not loaded). Tapping a ring opens the **spool editor** for that unit and
  slot.
- **Dry** button (radiator icon): opens the **drying dialog** for that unit.

**Insights** — label/value rows, each omitted when its entity has no value:

| Row | Source | Format |
|---|---|---|
| This job | `job_cost` | money |
| Last job | `last_job_cost` | money |
| Filament spend | `filament_cost_total` | money |
| Job needs | `job_filament_required` | whole grams + `g` |
| Shortfall | `job_filament_shortfall` | whole grams + `g` |
| Nozzle wear | `nozzle_wear_percent` | one decimal + `%` |
| Spools left | `spool_inventory_remaining` | whole grams + `g` |

Above the rows, a warning line when `job_filament_insufficient` is on. With no rows at all, a
short note telling the user these numbers need at least one finished job and spool weights
entered. Rows lay
out as a responsive grid of small tiles (as many columns as fit, minimum ~130 px each).

### 4.11 Dialogs

Common behaviour: a full-viewport overlay above the dashboard with a centred panel (about 80 % of
the width, capped near 600 px; ~95 % on narrow screens), a close (×) control, closing on a backdrop
tap but not on taps inside the panel, and a brief scale/fade-in on opening. Each dialog belongs to
its card; opening one on one card must not open it on another.

**Print settings**
- Title and three buttons: **Pause**, **Resume**, **Cancel**. Each switches the dialog to a
  **confirmation** view: a message with the chosen action's localised verb inserted, and Yes / No.
  Yes presses the matching button entity and closes; No returns to the settings.
- Filament printers only (by `material_type`), each row with its own Save button:
  - **Speed mode** — dropdown of `available_modes` descriptions, initially the current one. Saves
    the numeric mode.
  - **Nozzle target** — number field, initial = `target_nozzle_temp`, min/max from its
    `limit_min`/`limit_max`.
  - **Bed target** — same with `target_hotbed_temp`.
  - **Fan speed** — number field 0–100, initial = `fan_speed_pct`.
  - Auxiliary-fan and box-fan rows exist but are **hidden** in 2.x.
- Pressing Enter in a field saves that field. A field the user has touched stops following live
  updates until it is saved or the dialog is closed/reopened. Saving calls the action and closes the
  dialog; controls are disabled while a call is in flight.

**Spool editor** (one ACE slot)
- Title with the slot number (1-based).
- **Material** dropdown: `PLA`, `PETG`, `ABS`, `PACF`, `PC`, `ASA`, `HIPS`, `PA`, `PLA_SE`;
  preselected to the slot's material if it is one of these, otherwise empty with `PLA` as the
  placeholder (the user must then choose).
- **Preset colours**: the `slotColors` swatches; tapping one loads it into the colour picker.
- **Colour picker** initialised to the slot's colour. 2.x embeds a third-party picker (hue strip,
  saturation/lightness area, RGB(A) channel inputs, editable hex, copy-to-clipboard menu, OK
  button); the rebuild **may use any picker** (Home Assistant's own RGB colour selector is a good
  fit) as long as it yields an RGB triple.
- **Save** (and the picker's own confirm, if it has one) calls
  `multi_color_box_set_slot_<material>` with the unit, the 1-based slot and the RGB, then closes.
  Nothing is sent without a material and a three-component colour.

**Drying** (one ACE unit)
- Title, then up to four preset buttons, each shown only if that unit's preset button entity
  exists and is not unavailable (a preset exists when both its duration and temperature are set in
  the options). Label: the localised word for preset + number, then `<duration> <minutes-word> @
  <temperature>°C` from the button's attributes (always °C).
- **Stop drying**, on its own line, when the unit's stop button exists.
- Pressing any of them presses the entity and closes the dialog.

### 4.12 Responsive behaviour, theming, accessibility

- The card lays itself out by **its own width** (container query), not the window: at 480 px and
  wider the hero and summary sit side by side (ratio from `scaleFactor`) unless `vertical`; below
  that, stacked.
- Must look right from a narrow phone column to a full-width panel.
- Colours come from the Home Assistant theme (light and dark); overlay controls on the hero use
  light-on-translucent-dark.
- Buttons carry titles/labels; the hero tabs expose pressed state; section headers expose expanded
  state; the collapsed body is hidden from assistive tech; decorative artwork is hidden from it.

### 4.13 Card states at a glance

| Situation | What the card shows |
|---|---|
| Printing | Body open regardless of `alwaysShow`; green dot; progress, ticking clocks, Pause/Cancel (+ settings); head sweeping |
| Paused | Green dot (paused counts as printing); Resume/Cancel; clocks hold; pause symbol on the artwork screen |
| Idle / finished | Cyan dot; body collapsed unless `alwaysShow` or header tapped; no pause/cancel |
| Offline | Header state "Offline", red dot; temperatures em-dashed; progress hidden if unavailable; art idle |
| LAN-only (no cloud job data) | Header shows the printer's own status; preview tab disappears after its load fails |
| No `printer_id` / device gone | Fallback title, state "Unknown", red dot; everything empty; must not throw |

### 4.14 Panel shell and routing

- A header bar in the Home Assistant app-header style: the sidebar/menu button (for narrow
  layouts), the localised panel **title**, and the frontend version string on the right.
- Routes under `/anycubic_cloud`: `/<printer device id>/<page>`. No device id → the **printer
  selection** page. Missing page segment → `main`.
- **Printer selection**: a localised prompt and a centred row of large tappable tiles, one per
  discovered printer (3.1), labelled with the device name. Tapping navigates to
  `/<device id>/main` (history push). 2.x shows this page even when there is only one printer
  **(may auto-select)**.
- **Tabs** (scrollable strip under the toolbar, upper-case labels), history-pushed on change;
  tapping the current tab scrolls to top:

| Page segment | Tab | Content |
|---|---|---|
| `main` | Main | 4.15 |
| `local-files` | Local files | 4.16 |
| `udisk-files` | USB disk files | 4.16 |
| `cloud-files` | Cloud files | 4.16 |
| `print-no_cloud_save` | Print (no cloud save) | 4.17 |
| `print-save_in_cloud` | Print (save in cloud) | 4.17 |
| `debug` | Debug | 4.18 — only in debug builds |

  An unknown page shows a "page not found" message.
- Content area: centred; file and print pages are held to a readable lane (~600–1024 px), the main
  page may use up to ~1600 px; under 600 px everything is full width.
- The panel must follow Home Assistant's route updates (2.x also listens for location changes but
  its path check never matches the underscore URL — rely on the route data Home Assistant passes).

### 4.15 Panel — Main page

Three blocks; from ~1100 px viewport width the hero and rail sit side by side (hero wider, rail at
least ~320 px) with the gallery spanning beneath; narrower, everything stacks.

1. **Hero** — the card (same component as the dashboard card) for the selected printer, with the
   panel config (2.6) and panel defaults. Default `monitoredStats` when the config gives none:

| Printer | Stats |
|---|---|
| Has an ACE (ACE firmware entity exists) | Status, ETA, Elapsed, Remaining, Hotend, Bed, T Hotend, T Bed, Online, Availability, Project, Layer, Dry Status, Dry Time |
| Filament, no ACE | the same without the two drying stats |
| Otherwise | Status, ETA, Elapsed, Remaining, Online, Availability, Project, Layer |

2. **Rail** — titled tiles of label/value rows. Rows with no value are dropped; a tile with no rows
   is not shown.

| Tile | Rows |
|---|---|
| Machine | Model (device model); Firmware (device sw_version); Firmware update (`fw_version` update entity: "Update available" / "Up to date"); Online (`printer_online`); Availability (`is_available`: "Available" / "Busy") |
| ACE | ACE firmware update (as above for `multi_color_box_fw_version`); Drying (`dry_status_is_drying`); Drying progress = (1 − remaining ÷ total) × 100, two decimals + `%` |
| Diagnostics | A collapsed disclosure: printer name, printer id (device serial number), MAC |

3. **Preset gallery** — a title, a one-line lede, and a grid of tiles (auto-fit, ~300–380 px each).
   Each tile: a header with the preset's localised name and a **Copy** button; a **live preview**
   of the card; and the YAML that produces it. Previews render at dashboard-column width (so they
   show the stacked layout), are **non-interactive** (no accidental printer commands) and **never
   start a camera**. The YAML is generated from the same config object that renders the preview:
   first line `type: custom:anycubic-card`, then one `key: value` line per key, lists as indented
   `- item` lines. It scrolls horizontally inside its box rather than widening the page. `printer_id`
   is the selected device id (placeholder text if none). Keys a preset omits use the **card**
   defaults, exactly as a pasted card would.

| Preset | Config |
|---|---|
| Full | `mediaView: printer`, `showControls: true`, `showMoveButtons: true`, `sections: [filament]`, `alwaysShow: true` |
| Printer + model | `mediaView: printer_model`, `showControls: true`, `showMoveButtons: false`, `alwaysShow: true` |
| Compact | `mediaView: printer`, `showControls: false`, `showMoveButtons: false`, `alwaysShow: true`, `monitoredStats: [Status, ETA]` |
| Vertical | `vertical: true`, `mediaView: printer`, `showControls: true`, `showMoveButtons: false`, `alwaysShow: true` |

   There is deliberately **no camera preset** (4.4). **Copy** puts the YAML on the clipboard — with
   a fallback that works on plain-http installs where the async clipboard API is unavailable — and
   shows a localised "copied" confirmation on the button for ~1.5 s.

### 4.16 Panel — file pages (local, USB disk, cloud)

One card per page:
- A **refresh** button (refresh icon) that presses `request_file_list_<source>`; disabled while a
  refresh is in flight. For **local** and **USB**, it is also disabled — with a localised notice
  that the printer lacks MQTT support — when `mqtt_connection_active` has
  `supports_mqtt_login` false; **cloud** is always enabled. **(to verify: whether LAN-mode
  entries should enable local/USB refresh without MQTT login)**
- The file list from the source sensor's `file_info`, in the order given: one row per file with the
  name and a **delete** button (bin icon). Delete calls the matching delete action (by `filename`,
  or by `id` for cloud) with **no confirmation** in 2.x **(to verify: add one)**; delete buttons
  are disabled while a delete is in flight. Size is not shown.

### 4.17 Panel — print pages

Two identical pages differing only in the action: *no cloud save* →
`print_and_upload_no_cloud_save`; *save in cloud* → `print_and_upload_save_in_cloud`.
- Home Assistant's own action-form component, with the action picker hidden, advanced fields
  shown, and the data prefilled with `config_entry` and `device_id` of the selected printer. The
  user supplies `uploaded_gcode_file` (a file upload accepting `.gcode`, `.pwsp`, `.pwsq`, `.zip`)
  and optionally `slot_number` (list of ACE slots).
- A **Print** button (play icon) showing progress while the call runs, success/failure feedback on
  completion, a haptic tick on press, and the error message in an error alert if the call fails.
  Editing the form clears the error.
- 2.x makes the action-form component available by forcing Home Assistant's developer-tools panel
  code to load; the rebuild **may** use any supported way to obtain an action/file form.

### 4.18 Panel — debug page

Developer aid, not reachable in release builds: entity count, narrow flag, and JSON dumps of the
panel config, route, printers, the printer's entity set and the selected device. Optional in 3.0.

### 4.19 Strings 2.x shows in hard-coded English

Not in the translation files; 3.0 should give them keys (new keys are fine — see 5.3): card
fallback name; header button titles (show/hide body, printer light, printer power); control labels
(Pause, Resume, Cancel); section titles (Filament, Insights); "Layer X / Y"; move-pad titles and
notes; Insights row labels, warning and empty note; hero LIVE badge, preview alt text and camera
messages; print-settings dialog title and confirmation title; "choose preset colour" label; editor
"choose monitored stats" label and stat names in the Stats tab; stat values Online/Offline,
Drying/Not Drying, Available/Busy, Update available/Up to date, Unknown, "Mins"; job/printer state
words shown title-cased from raw entity states **(to verify: localise via the integration's entity
state translations)**; the panel's "page not found" message.

---

## 5. Localisation

### 5.1 Languages

Six, all complete (every language has all 137 keys):

| Code (as Home Assistant reports it) | Language |
|---|---|
| `en` | English (fallback) |
| `de` | German |
| `es` | Spanish |
| `fr` | French |
| `nl` | Dutch |
| `zh-Hans` | Chinese (Simplified) |

The text itself is not reproduced here. **(to verify: whether 3.0 re-translates from scratch or
Nino arranges reuse of the 2.x translations)**

### 5.2 Lookup behaviour

- Language = Home Assistant's current UI language (`hass.language`), re-evaluated when it changes.
- Exact code match only; a missing language **or** a missing key falls back to English per key.
  2.x does not map regional variants (`de-CH`, `pt-BR`, `zh-Hant`…) to a base language — they get
  English. The rebuild **should** also try the base language before English.
- Messages use ICU message format; the only placeholder in 2.x is `{action}` in
  `card.print_settings.confirm_message`, filled with the localised `common.actions.<pause|resume|cancel>`.
- Nested JSON, dotted key paths.

### 5.3 Keys (137 leaf keys)

The rebuild may rename or add keys freely — no dashboard stores them — but must cover the same
strings in the same six languages. The one hard dependency is that stat labels are looked up by the
stat **value** (`card.monitored_stats.<value>`, value strings from 2.3, spaces included).

**Panel-wide**
- `title`
- `panels.initial.printer_select`

**Common**
- `common.actions.`: `cancel`, `pause`, `print`, `resume`, `yes`, `no`, `save`
- `common.messages.mqtt_unsupported`

**Card — buttons and hero**
- `card.buttons.`: `print_settings`, `dry`, `runout_refill`
- `card.media_view.tabs.`: `camera`, `preview`, `printer`, `printer_model`

**Card — stat labels** (`card.monitored_stats.` + value)
- `ETA`, `Elapsed`, `Remaining`, `Status`, `Online`, `Availability`, `Project`, `Layer`, `Hotend`,
  `Bed`, `T Hotend`, `T Bed`, `Dry Status`, `Dry Time`, `Speed Mode`, `Fan Speed`, `On Time`,
  `Off Time`, `Bottom Time`, `Model Height`, `Bottom Layers`, `Z Up Height`, `Z Up Speed`,
  `Z Down Speed`

**Card — print settings dialog** (`card.print_settings.`)
- `confirm_message` (placeholder `{action}`), `label_nozzle_temp`, `label_hotbed_temp`,
  `label_fan_speed`, `label_aux_fan_speed`, `label_box_fan_speed`, `print_pause`, `print_resume`,
  `print_cancel`, `save_speed_mode`, `save_target_nozzle`, `save_target_hotbed`, `save_fan_speed`,
  `save_aux_fan_speed`, `save_box_fan_speed`

**Card — drying dialog** (`card.drying_settings.`)
- `heading`, `button_preset`, `button_stop_drying`, `button_minutes`

**Card — spool editor** (`card.spool_settings.`)
- `heading`, `label_select_material`, `label_select_colour`

**Card — visual editor** (`card.configure.`)
- `tabs.`: `main`, `stats`, `colours`
- `labels.`: `printer_id`, `vertical`, `round`, `use_24hr`, `show_settings_button`,
  `always_show`, `temperature_unit`, `light_entity_id`, `power_entity_id`, `camera_entity_id`,
  `scale_factor`, `slot_colors`, `media_view`, `printer_art`, `show_controls`,
  `show_move_buttons`, `sections`
- `helpers.`: `light_entity_id`, `power_entity_id`, `camera_entity_id`
- `options.printer_art.`: `auto`, `kobra_s1`, `kobra_s1_combo`, `kobra_3`, `resin`, `fdm`
- `options.media_view.`: `auto`, `camera`, `preview`, `printer`, `printer_model`, `none`
- `options.sections.`: `filament`, `insights`

**Panel — tab titles**
- `panels.main.title`, `panels.files_local.title`, `panels.files_udisk.title`,
  `panels.files_cloud.title`, `panels.print_no_cloud_save.title`,
  `panels.print_save_in_cloud.title`, `panels.debug.title`
  (each of these `panels.<page>` objects also carries an empty `cards` object — structure only)

**Panel — main page**
- `panels.main.groups.`: `machine`, `ace`, `diagnostics`
- `panels.main.presets.`: `title`, `lede`, `full`, `model`, `compact`, `vertical`, `copy`, `copied`
- `panels.main.cards.main.fields.`: `printer_name`, `printer_id`, `printer_mac`, `printer_model`,
  `printer_fw_version`, `printer_fw_update_available`, `printer_online`, `printer_available`,
  `curr_nozzle_temp`, `curr_hotbed_temp`, `target_nozzle_temp`, `target_hotbed_temp`,
  `job_state`, `job_progress`, `ace_fw_version`, `ace_fw_update_available`, `drying_active`,
  `drying_progress`
- `panels.main.cards.main.description`

Unused in 2.x's current layout (present in the files, never shown): `panels.main.cards.main.description`
and the fields `curr_nozzle_temp`, `curr_hotbed_temp`, `target_nozzle_temp`, `target_hotbed_temp`,
`job_state`, `job_progress`, `ace_fw_version`.

---

## 6. Third-party and derived areas the rebuild must not reproduce

The implementation team must design these areas afresh from this specification. Named so they can
be avoided; nothing about their code is described here.

**Derived from `dangreco/threedy`** (the 2.x README credits it with the card concept, via the
WaresWichall card):
- the overall card concept: header with status dot, collapse-when-idle, light/power header toggles;
- the monitored-stats model — the stat list, per-second ticking time rows, and duration/ETA/
  temperature formatting helpers;
- the config key vocabulary (`vertical`, `round`, `use_24hr`, `temperatureUnit`, `*EntityId`,
  `monitoredStats`, `scaleFactor`, `alwaysShow`) — **the keys themselves must be kept for
  compatibility**; only their implementation is to be avoided;
- the original box-model animated printer (frame/axis/build-plate dimension configuration and its
  scaling maths — still present in 2.x as an unused leftover) and the click-to-toggle camera
  overlay component (unused in 2.x).

**From WaresWichall/hass-anycubic_cloud** (excluded source; most of the 2.x frontend descends from
it): the panel shell, file and print pages, the ACE strip, spool/drying/print-settings dialogs, the
dropdown and reorderable-checklist widgets, modal styling and the entity helpers. The text of the
2.x translation files (5.1) is likewise not to be copied without the clearance asked about there.

**Other third-party code copied into the 2.x source tree:**
- a vendored Lit colour-picker component set (hue bar, HSL canvas, channel inputs, copy dialog) and
  the drag/"movable" helper it depends on;
- a DOM event-firing helper adapted from Polymer / the Home Assistant frontend;
- a haptic-feedback helper from the Home Assistant frontend;
- a define-only-if-undefined element decorator adapted from lit-element's source;
- the trick that loads Home Assistant's action-form component by forcing the developer-tools panel
  to load, and the trick that loads the camera-stream element by creating a throw-away
  picture-entity card (both are common community techniques; re-derive from Home Assistant's
  documented APIs where possible).

Ordinary npm dependencies of 2.x — Lit, Material Design Icons, date-fns, intl-messageformat,
Lit Labs motion, modern-color, home-assistant-js-websocket — are libraries under their own
permissive licences, not derived code; 3.0 may depend on these or others.

---

## 7. Open items (to verify)

1. 3.0 frontend package name and delivery (separate package vs bundled) — 1.1.
2. Which entry's `card_config` configures the panel when there are several — 1.2.
3. Whether 3.0 honours stored `false` / `0` values and integer `scaleFactor` in `card_config`, and
   passes the newer keys through — 2.6.
4. Unknown `monitoredStats` values: skip instead of a placeholder row — 2.3.
5. Disabled entities are absent from the frontend's entity list — 3.2.
6. Status colour for `current_status` = `moving` — 4.1.
7. Highlighting a loaded slot on the second ACE — 4.5.
8. Drawing the Anycubic logo in the artwork (trademark) — 4.5.
9. Dry Time bar direction (remaining vs elapsed) — 4.7.
10. ETA from `job_time_remaining` vs the `job_eta` timestamp sensor — 4.7.
11. Confirmation for the inline Cancel button — 4.8.
12. Local/USB file refresh for LAN-mode entries without MQTT login — 4.16.
13. Confirmation before deleting a file — 4.16.
14. Localising job/printer state words via entity state translations — 4.19.
15. Reuse or fresh translation of the 2.x strings — 5.1.
16. Home Assistant's legacy tab components (used by 2.x for panel and editor tabs) may no longer
    exist in current frontends — use whatever tab component current Home Assistant provides.
