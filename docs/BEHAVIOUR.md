# Behaviour specification — `anycubic_cloud` 3.0

What every entity, action and connection path of `anycubic_cloud` **does**, so
that 3.0 can be built without reading 2.x. It is the companion to
[`COMPAT.md`](COMPAT.md): COMPAT fixes the identifiers (keys, unique ids,
stored formats); this document gives them meaning. Tables in COMPAT are not
repeated here.

Collected 2026-09-28 by the specification team from the behaviour of
`anycubic_cloud` 2.9.3 and its library `anycubic-cloud-api` 0.4.31, and from
the live install described in COMPAT. Wire facts for LAN Mode are **not**
restated: they live in `Nino6689/anycubic-lan`, `docs/PROTOCOL.md`, cited here
as **LAN §n**.

Anything the specification team is not sure of is marked **(to verify)**; §9
collects them.

---

## Contents

0. Conventions
1. The printer model and shared mappings
2. Entities, key by key
3. Computed features
4. Actions
5. Connection behaviour and setup flows
6. Known 2.x bugs NOT to reproduce
7. 2.x gaps and quirks found while writing this (decisions for 3.0)
8. Corrections made to COMPAT.md
9. Items to verify

---

## 0. Conventions

### 0.1 Words used

| Word | Meaning |
|---|---|
| **Cloud entry** | A config entry set up with an Anycubic token (has `user_token`). |
| **LAN-only entry** | A config entry set up against the printer alone (no `user_token`; `lan_mode_enabled` true). |
| **Hybrid entry** | A cloud entry whose options also switch LAN Mode on. |
| **HTTP** | The cloud REST API, polled. Supplies the printer record, the latest job from the account's job list, and the cloud file list. |
| **CMQTT** | The cloud MQTT push connection. Only possible with a *slicer* or *Android* token (never a web token, never LAN-only), and only while the connect mode (§5.2) holds it open. |
| **LAN** | The MQTT broker that runs on the printer itself once LAN Mode is switched on (LAN §1–§7). |
| **Ledger** | Values computed by the integration from the filament ledger stored in `.storage` (COMPAT §6). |
| **Config** | A value the user typed in (options, number entities). |
| **No value** | The integration's internal reading for a key is absent. How that shows depends on the platform (§0.3). |
| **Job** | The printer's *latest* print job — see §1.3. |

Transport column values used throughout §2: **HTTP**, **CMQTT**, **LAN**,
**Ledger**, **Config**, or combinations. "Cloud" means HTTP and/or CMQTT.

Switching LAN Mode on makes the printer leave the Anycubic account (the
printer does this, not the integration); switching LAN Mode off does not
bring it back (it must be re-added in the Anycubic app). So a printer is reachable over the cloud **or**
over LAN, never both at once.

### 0.2 One refresh, in outline

Every refresh the integration builds, per printer, a flat map of *states*
(one value per entity key) and a map of *attribute blocks* (per key). Every
entity reads its value from that map. Pushed reports (CMQTT or LAN) rebuild the
map immediately; polls rebuild it on a timer (§5.1).

### 0.3 Availability and "no value", per platform

Required unless §6/§7 says otherwise. These reproduce 2.x so automations keep
working, with one addition: **every** entity is unavailable while the
printer's data source is lost (§5.5).

| Platform | Unavailable when | Unknown when | "No value" otherwise shows as |
|---|---|---|---|
| sensor | the value is absent (**not** unknown — 2.x deliberately uses unavailable for "not reported yet") | never | — |
| binary_sensor | source lost; `job_filament_insufficient` also when it has no value | never | **off** |
| button | source lost | — | — |
| number | source lost | value absent | — |
| select | source lost; `set_speed_mode` also when the printer publishes no mode names | — | — |
| switch | source lost | `ai_detection_enabled` when the printer has not said | **off** (other switches) |
| light | the printer has never been known to have a light (live or remembered, §3.13) | on/off not reported since the entry was built | — |
| update | source lost | — | see §2.17 |
| image | no preview URL | — | — |
| camera | see §2.18 | — | — |

### 0.4 How sensor values are presented

- A sensor whose device class is *timestamp* receives seconds since the epoch
  and shows them as a UTC date-time.
- Any fractional reading, and any sensor whose unit is °C, is a float.
- Readings in *layers* or *%*, and whole numbers, are integers.
- Everything else is text.
- Device class, when not stated in COMPAT: a sensor in °C is *temperature*; a
  sensor in seconds or minutes is *duration*.
- State class: text-like sensors have none (`ace_spools`, `secondary_ace_spools`,
  `external_spool_material`, `ace_loaded_slot`, `secondary_ace_loaded_slot`,
  `ace_slot_1`–`4`, `job_speed_mode`, `last_error_code`, `last_error`,
  `current_status`, the three `file_list_*`, `job_name`, `job_state`,
  `job_eta`). Sensors with a state class in COMPAT keep it. **All other
  sensors are *measurement*** (see §7 for the monetary pair).
- A *monetary* sensor's unit is the currency configured in Home Assistant
  (never asked of the user). The same currency is the unit of the
  `ace_slot_N_spool_price` numbers.

---

## 1. The printer model and shared mappings

### 1.1 Online, free and busy

Two independent codes describe a printer:

| Code | Values | Cloud source | LAN source |
|---|---|---|---|
| Device status | `1` online, `2` offline | HTTP printer record `device_status`; CMQTT `lastWill` report, action `onlineReport`, state `online` → 1 / `offline` → 2 | Any `info` report sets 1. LAN never reports "offline": losing the printer makes everything unavailable instead (§5.5). |
| Work status | `1` free, `2` busy | HTTP printer record `is_printing`; CMQTT `status` report, action `workReport`, state `free`/`busy`; print reports (below) | `info.state` `free` → 1, `busy` → 2 (LAN §6.1) |

When nothing has been reported, work status is **free**.

Print reports (CMQTT `print`, and the same kinds locally) move the work status:

| Print report action / state | Work status | Job status set to |
|---|---|---|
| `start` / `printing` | busy | printing |
| `start` / `downloading` | busy | downloading (download % recorded) |
| `start` / `checking` | busy | checking |
| `start` / `preheating` | busy | preheating |
| `start` / `finished` | free | complete |
| `pause` / `pausing` or `paused` | busy | printing, paused |
| `resume` / `resuming` | busy | printing, still paused |
| `resume` / `resumed` | busy | printing, not paused |
| `start` or `stop` / `stoped` (sic) or `stopping` | free | cancelled |
| `start` or `stop` / `failed` | free | cancelled; the message is kept as the job's status message |
| `start` or `update` / `updated` | unchanged | unchanged; applies any of: current temperatures, part-fan %, print-speed %, speed mode, target temperatures |

A CMQTT print report is applied to the known job only when its task id equals
that job's id, or it carries no task id. Reports for a different task id are
discarded until the next HTTP poll brings the new job in (§7, G9).

### 1.2 `current_status` mapping

| State text | When |
|---|---|
| `moving` | an axis move or home is under way (§1.8) — takes precedence |
| `busy` | work status 2 |
| `available` | work status 1 |
| `unknown` | anything else |

### 1.3 The job

- **Over the cloud** the job is the most recent entry for this printer in the
  account's job list (HTTP, every poll), enriched by a second call for that
  job's detail (layer height, speed-mode list, temperature targets and limits).
  It **stays** after the print ends: a finished job keeps reporting
  `finished` until the next job starts. CMQTT print reports update it live.
  While scanning the list for the latest job, if that job has no preview image
  the integration borrows the image of an earlier job with the same name,
  looking back at most 200 entries.
- **Over LAN** the job is the `project` block of the `info` report (LAN §6.2).
  When the printer goes idle the block becomes null and the job is **cleared**:
  every job sensor loses its value, `job_state` reads `idle`.
- A new task id replaces the job; the same task id updates it.

Job status codes (the printer's numbers; LAN §6.2 has the same table):

| Code | Meaning | `job_state` text |
|---|---|---|
| 1 | printing | `printing` (or `paused`, see below) |
| 2 | complete | `finished` |
| 3 | cancelled (includes a user stop and a failure) | `failed` |
| 4 | downloading | `downloading` |
| 5 | checking | `checking` |
| 6 | preheating | `preheating` |
| 7 | slicing | `slicing` |
| 8 | never observed | — |
| 9 | levelling | `levelling` |
| 0 or non-numeric | **not a status** (Kobra X sends 0 mid-print) | keep the previous status; apply the rest of the report |

Rules:

- **Paused** = the job's pause flag is non-zero **and** the job is in progress.
  Paused wins over every other text.
- **In progress** = status 1, 4, 5 or 6. Status 2 or 3 = not in progress. Any
  other code: in progress unless the job's own text phase (a `state` word the
  cloud job settings may carry) is one of `cancelled`, `canceled`, `complete`,
  `completed`, `failed`, `finished`, `free`, `idle`, `stopped`; no text phase
  = not in progress.
- `job_state` for a code not in the table: the job's text phase if it has one,
  else `unknown`.
- **No job at all**: `job_state` is `idle` while the printer is online,
  otherwise no value (unavailable).
- Once a job object has reached complete or cancelled, a later HTTP refresh of
  the **same** job does not move it back; a pushed print report can.

### 1.4 Error codes

- Every CMQTT or LAN message envelope carries a `code` (LAN §5). **`0` and
  `200` mean nothing is wrong.** Any other integer (booleans and non-integers
  are ignored) is a printer fault.
- The code is read **before** the rest of the message is interpreted, so a
  fault is recorded even when the message itself is not understood.
- `last_error_code` = the most recent fault code; `last_error` = its
  description. In 2.x both **stay** until another fault arrives — a later OK
  message does not clear them — and both are held only in memory (lost on
  restart/reload). See §7, G7 for the difference from the `anycubic-lan`
  library's rule.
- Descriptions come from Anycubic's published list,
  <https://wiki.anycubic.com/en/error-codes>; transcribe it from there (2.x
  carries about 95 codes in the 10000–11871 range). A code not on the list is
  described as the text `Unknown error code <n>`.
- Anycubic ships codes that are not on the wiki: `11858` was reported from a
  Kobra X when ACE slot 4 ran dry (hass-anycubic #21).
- HTTP responses' codes are not recorded; with a web token (no CMQTT) these
  sensors therefore never get a value over the cloud.

### 1.5 Speed modes

- The printer reports the mode it is in as an integer (CMQTT print `updated`
  settings; LAN `info.print_speed_mode` and the job block). Observed on a
  Kobra S1: `1` silent/quiet, `2` standard, `3` sport.
- **Names** exist only on the cloud: the job detail carries a list of
  `{name, code}` pairs for the modes that machine offers. LAN has no list.
- `job_speed_mode` text: if the printer has reported a code, the name paired
  with it in the list, else the code as text; if the printer has not reported
  a code, the job's own mode name (looked up the same way); else no value.
- Changing the mode is only accepted while a job is running and only to a code
  in the list (§2.14, §4.6).

### 1.6 Job end time (`job_eta`)

1. If the job carries a finish time greater than zero (cloud job list field),
   that is the answer (for a finished job this is when it finished).
2. Otherwise, if the remaining minutes are non-zero: now + remaining minutes.
3. Otherwise no value. The printer reports 0 minutes remaining while
   levelling, preheating or slicing; neither "now" nor the epoch is a truthful
   end time then.

The value is recomputed at every refresh.

### 1.7 Material type and which entities exist

- Material type is `Filament` or `Resin` (or a raw other string). Cloud: the
  printer record says so. LAN: the discovery document's `deviceType` — `fdm`
  → Filament; `lcd`, `dlp` or `resin` → Resin.
- Entity creation filters, evaluated per printer on every refresh until each
  descriptor has been placed:

| Descriptor type (COMPAT §3 "Type") | Created when | If not yet |
|---|---|---|
| `printer` | the printer has loaded | wait |
| `fdm` | material type is Filament | **dropped for good** if another type (see §7, G14) |
| `lcd` | material type is Resin | **dropped for good** if another type |
| `ace1` | the printer supports an ACE **and** at least 1 ACE has reported | **kept pending** (never dropped — #41) |
| `ace2` | supports an ACE and at least 2 have reported | kept pending |
| `dry1` / `dry2` | as `ace1`/`ace2`, **and** preset N has both a duration and a temperature greater than 0 | kept pending |
| `global` | the printer has loaded | — |

- "Supports an ACE" = the cloud's function list for the printer contains
  function id **2006**, **or** at least one ACE box has been reported (a
  LAN-only printer has no function list).
- The number of ACE units is the number of boxes in the last full ACE report.
  A report that mentions only one box updates that box and **keeps** the
  others.
- `global` descriptors are created **once per printer**, on the printer
  device (not once per entry as COMPAT's wording suggests).
- Entities are never removed when an ACE is unplugged; they simply read 0 or
  no value.
- A printer selected on the entry but not loaded at setup (e.g. offline) is
  picked up on a later refresh, and its devices and entities created then.
  Devices of printers no longer selected are removed from the entry (ACE
  devices go with their printer).

### 1.8 Axis movement state

Reports of kind `axis`, action `move` carry a state: `doing` while moving,
`done` when finished, `failed` when the printer refused the move (usually
because that axis has not been homed since power-on; homing X/Y leaves Z
unhomed). *Moving* = a state has been seen and it is neither `done` nor
`failed`. *Refused* = the last state is `failed`. No position comes with a move
report; the position comes only in reply to a position query.

### 1.9 ACE facts used below

| Fact | Value |
|---|---|
| Box info block (attribute `box_info`) | `box_id`, `model_id`, `status`, `temperature` (°C), `humidity` (reads 0 without a sensor), `auto_feed` (bool), `loaded_slot` (1-based, or null), `feed_status` (`code`, `type`, `current_status`, `slot` 1-based or null) |
| Model ids | `40001` = ACE Pro (device model "ACE Pro"); anything else → "ACE". `40002` is reported by another Kobra S1 owner, name unconfirmed (LAN §6.7) |
| Slot `edit_status` | `0` details read from the spool's tag, `1` typed in by hand, **`2` slot empty** |
| Slot `status` | `5` = this slot is loaded into the printer; `4` = not loaded; other values are presence states |
| Loaded slot | box field `loaded_slot`, 0-based, `-1` = none. **First ACE only:** when it reads −1, the slot whose own status is 5 is taken instead (a Kobra S1 does this mid-print). The second ACE has no such fallback. |
| Empty slots | After a reel is taken out, the ACE goes on reporting that slot's previous material, colour and SKU. Only `edit_status` 2 says it is empty. |
| Drying status | `status` 1 = drying (anything else = not drying); `target_temp` °C; `duration` and `remain_time` minutes. While not drying, target, duration and remaining are reported as **0**. |
| `consumables_percent` | Anycubic's own "remaining" field; reads 0 on every slot observed. Shown, never used. |

---

## 2. Entities, key by key

Column **Transport** says which connections can supply the value. "No value"
behaviour follows §0.3 unless stated.

### 2.1 Printer status and diagnostics

| Key | What it says | Transport | Value | Extra attributes |
|---|---|---|---|---|
| `current_status` | What the printer is doing, in one word (§1.2) | HTTP, CMQTT, LAN | `moving`, `busy`, `available`, `unknown` — always has a value | `model` model name; `machine_type` numeric model id; `supported_functions` list of function names from the cloud's function list (§2.14; empty on LAN); `material_type` `Filament`/`Resin`; `device_status_code` 1/2/null; `is_printing_code` 1/2; `print_status_code` raw job status number; `peripherals` `{camera, ace, usb_disk}` each true/false/null (null = not yet answered); `total_material_used` raw lifetime text as the cloud sends it (e.g. `18.01kg`); `total_print_time_hrs` whole hours; `total_print_time_dhm` `days:hours:minutes`; `job_download_progress` 0–100 |
| `printer_online` (binary) | The printer is connected to its service | HTTP, CMQTT, LAN (§1.1) | on = device status 1 | — |
| `is_available` (binary) | The printer is free | HTTP, CMQTT, LAN | on = work status 1 | — |
| `is_busy` (binary) | The printer is busy | HTTP, CMQTT, LAN | on = work status 2 | — |
| `last_error_code` | Last fault code (§1.4) | CMQTT, LAN | integer | — |
| `last_error` | Anycubic's description of that code | CMQTT, LAN | text | — |
| `mqtt_connection_active` (binary, diagnostic) | A CMQTT client exists — connected **or still connecting** | CMQTT | on/off | `supports_mqtt_login` true for slicer/Android tokens, false for web tokens and LAN-only; `last_error` text of the last CMQTT failure, formed as `<error type>: <message> (host=<host>:<port>)`, or null after a clean run |

### 2.2 Temperatures, fans, speed (filament printers, `fdm`)

| Key | What it says | Transport | Value | Extra attributes |
|---|---|---|---|---|
| `curr_nozzle_temp` | Hotend temperature now | HTTP printer record; CMQTT `tempature` and print `updated`; LAN `info.temp`, `tempature` | °C | — |
| `curr_hotbed_temp` | Bed temperature now | as above | °C | — |
| `target_nozzle_temp` | Hotend set-point | the job's target if the job carries one (cloud job detail, updated by pushed reports), else the printer's own reported set-point (CMQTT `tempature`, LAN `info.temp`/`tempature`) | °C | `limit_min`, `limit_max`: the allowed range from the cloud job detail (null on LAN) |
| `target_hotbed_temp` | Bed set-point | as above | °C | `limit_min`, `limit_max` as above |
| `fan_speed_pct` | Part-cooling fan speed from the **printer's** reports (never the sliced job's figure) | CMQTT `fan`, print `updated`; LAN `info`, `fan` | 0–100, no unit declared | — |
| `aux_fan_speed_pct` | Auxiliary part fan | CMQTT `fan`; LAN `info`, `fan` | 0–100 % | — |
| `print_speed_pct` | Print speed %; the printer's own reading, falling back to the job's setting | CMQTT/LAN print `updated`; fallback cloud job detail | integer, no unit declared | — |
| `job_speed_mode` | Speed mode name (§1.5) | code: CMQTT, LAN; names: HTTP | text | `available_modes` list of `{description, mode}` from the cloud (empty on LAN); `print_speed_mode_code` the printer's code, else the job's |

No HTTP source exists for the fans: with a web token they never get a value.

### 2.3 The job

All job values come from the job (§1.3). Cloud: HTTP poll, updated live by
CMQTT print reports. LAN: the `info.project` block, cleared when idle.

| Key | What it says | Value | Cloud / LAN |
|---|---|---|---|
| `job_name` | File name of the job, without a trailing `.gcode` | text | both (LAN: see §7, G13) |
| `job_progress` | Progress | 0–100 % | both |
| `job_time_elapsed` | Printing time so far | minutes | both |
| `job_time_remaining` | Printer's estimate of time left | minutes | both |
| `job_state` | Job phase (§1.3) | `printing`, `paused`, `finished`, `failed`, `downloading`, `checking`, `preheating`, `slicing`, `levelling`, `idle`, `unknown`, or a raw phase word | both |
| `job_eta` | When the job ends (§1.6) | timestamp | both |
| `job_current_layer` / `job_total_layers` | Layer counters | layers | both |
| `job_z_thick` | Layer height of the job | mm, no unit declared | cloud only |
| `job_filament_used` | Filament extruded so far by this job (the printer's own count, includes purge) | mm (see §9, V1) | both |
| `job_in_progress` (binary) | §1.3 in-progress rule | on/off | both |
| `job_complete` (binary) | Job status 2 | on/off | both (LAN: off once idle) |
| `job_failed` (binary) | Job status 3 (includes a user cancel) | on/off | both |
| `job_is_paused` (binary) | §1.3 paused rule | on/off | both |
| `job_image_url` (image) | Preview picture of the job | PNG fetched from the URL; the cached picture is dropped whenever the URL changes | cloud only; unavailable with no URL |

`job_name` attributes (only keys that have a value are included): `file_name`,
`source`, `slicer`, `printer_profile`, `layer_height`, `filament_types` (list
split from the slicer's `;`-separated text), `nozzle_temperature`,
`bed_temperature`, `fill_density`, `travel_speed`, `brim_type`,
`model_size_mm` (`[x, y, z]`), `estimated_filament` (from the slice result);
slicer values of −1 or empty are left out. Always present:
`created_timestamp`, `finished_timestamp`, `print_total_time` (raw text),
`print_total_time_minutes`, `print_total_time_dhm`, `print_supplies_usage`
(= `job_filament_used`), `print_status_message` (the reason text of a failure,
if any). All slicer detail is cloud only.

The preview URL is the job's image address when it is a full `http…` URL,
otherwise the slice's image path joined to the region's image base (both
regions use the same base in 2.x).

### 2.4 Lifetime counters (cloud only)

| Key | What it says | Value |
|---|---|---|
| `material_used_total` | Lifetime filament, from the printer record's text such as `18.01kg` | kilograms; no value unless the text is a number followed by `kg` |
| `print_time_total_hrs` | Lifetime printing time | whole hours, rounded down. The cloud sends either minutes as a number or `<h>hour<m>min`. On LAN 2.x reports **0** (§7, G11). |
| `print_count_total` | Lifetime print count | integer; no value on LAN |

### 2.5 Files

| Key | What it says | Transport | Value | Attributes |
|---|---|---|---|---|
| `file_list_local` | Files in the printer's internal storage | reply to a cloud order, arrives over **CMQTT only** (no LAN form) | count of files; no value until the list is first requested (button or action) — and also when the printer reports an **empty** list (§7, G12) | `file_info`: list of `{name, size_mb}` |
| `file_list_udisk` | Files on the USB stick | as above | as above | as above |
| `file_list_cloud` | The account's cloud files — the 10 most recent (one page) | HTTP | count; no value until requested, or when empty | `file_info`: list of `{id, name, size_mb, thumbnail, estimate_seconds, material, layer_height, filament_mm, dimensions}` |

The cloud list is account-wide: every printer of the entry shows the same
list. Lists are held in memory only.

### 2.6 Head position and axis state (`fdm` for the binary sensors; the position sensors are on every printer)

| Key | What it says | Transport | Value |
|---|---|---|---|
| `axis_position_x` / `_y` / `_z` | Print-head position | reply to the position query (button `request_axis_position`); CMQTT or LAN `axis` query reply | mm, float, display precision 1; no value until first queried; a reply without coordinates keeps the last position |
| `axis_moving` (binary, device class *moving*) | A jog or home is in progress (§1.8) | CMQTT, LAN | on/off |
| `axis_move_failed` (binary, *problem*; named "Axis move refused") | The last move was refused (§1.8) | CMQTT, LAN | on/off |

### 2.7 External filament holder

The single-spool holder some printers have instead of (or beside) an ACE.

| Key | What it says | Transport | Value | Attributes |
|---|---|---|---|---|
| `external_spool_material` | Material in the holder | HTTP printer record; CMQTT `extfilbox` `reportInfo`; LAN `extfilbox` query | text; no value when the holder is empty **or absent** | `material`, `color` `[r,g,b]` or null, `color_hex` `#RRGGBB` or null, `loaded` bool — or an empty map when there is no holder |
| `external_spool_loaded` (binary) | A spool is loaded in the holder | as above | on/off (off also when there is no holder — §7, G15) | — |

A holder counts as **absent** when the report has no id, no material and no
loaded flag (firmware 2.0.1.9 sends an all-null block on printers without one).

### 2.8 First ACE (`ace1`, on the ACE device)

Transport for everything here: HTTP printer record (each cloud poll), CMQTT
`multiColorBox` reports, LAN `multiColorBox` `getInfo` reply (LAN §6.7).

| Key | What it says | Value | Attributes |
|---|---|---|---|
| `ace_spools` | Whether the ACE reported its slots | `active` when the slot list is known, else `inactive` | `spool_info`: list per slot of `{slot (1-based), material_type, color [r,g,b], color_hex, colors_hex (list; several for a multi-colour reel), color_group (RGBA lists), is_multi_color, sku, status, spool_loaded, edit_status, icon_type, consumables_percent}`; `box_info` (§1.9) |
| `ace_loaded_slot` | Which slot is feeding the printer | 1–4, the number printed on the box; no value when nothing is loaded (§1.9) | — |
| `ace_current_temperature` | Temperature inside the ACE | °C integer; **0** when no box is known | — |
| `ace_slot_1` … `ace_slot_4` | Material in slot N | text as reported (e.g. `PLA`, `PETG`); **no value when the slot is empty** (`edit_status` 2) | `slot`, `color` `[r,g,b]`, `color_hex`, `colors_hex`, `is_multi_color`, `sku` (null when blank), `spool_loaded`, `status`, `edit_status`, `consumables_percent` |
| `ace_slot_N_filament_remaining` | Estimated filament left on the reel (§3.4) | grams, 0 decimals shown; no value when the slot is empty | — |
| `ace_slot_N_filament_remaining_percent` | The same as a share of a full reel (§3.4) | %, 0 decimals shown; no value when empty | — |
| `dry_status_target_temperature` | Drying target | °C; 0 when not drying | — |
| `dry_status_total_duration` | Length of the current drying cycle | minutes (no unit declared); 0 when not drying | — |
| `dry_status_remaining_time` | Drying time left | minutes (no unit declared); 0 when not drying | — |
| `box_fan_level` | "Box fan" level reported with the printer's fans | integer, no unit (§9, V4) | — |
| `dry_status_is_drying` (binary) | ACE is drying | on = drying status 1 | `dry_status_code` the raw drying status |

The `ace_slot_N` entity picture is a small image of a spool face in the reel's
colour(s): a ring coloured with vertical bands (one per colour, in the order
reported), a hollow hub, neutral grey rims so white filament shows on a white
page. Only `#RRGGBB` colours are drawn; none valid → no picture.

### 2.9 Second ACE (`ace2`, on the second ACE device)

Same meanings, box index 1: `secondary_ace_current_temperature`,
`secondary_ace_loaded_slot` (no status-5 fallback), `secondary_ace_spools`
(attributes `spool_info`, `box_info`), `secondary_dry_status_target_temperature`,
`secondary_dry_status_total_duration`, `secondary_dry_status_remaining_time`,
`secondary_dry_status_is_drying` (attribute **`secondary_dry_status_code`**).
There are no per-slot sensors, spool numbers or feed buttons for the second
ACE in 2.x.

### 2.10 Computed filament, cost and wear (Ledger; printer device)

Formulas are in §3. "Job" below is the running job.

| Key | What it says | Value | No value when | Attributes |
|---|---|---|---|---|
| `job_filament_required` | Projected grams the whole job will use | g, 1 decimal | no job in progress; no feeding slot known; not enough data yet (§3.6) | `source`: `history`, `extrapolated`, or `unknown` (before any forecast) |
| `job_filament_shortfall` | Grams the feeding reel is short by | g; 0 when it will last | as above | — |
| `job_filament_runs_out_at` | Job progress at which the reel empties | %; 100 when it will last | as above | — |
| `job_filament_insufficient` (binary, *problem*) | The feeding reel will not finish the job | on = shortfall > 0 | **unavailable** when no forecast (never "off" when unknown) | — |
| `job_cost` | Projected cost of the whole job | money, 2 decimals | as above, or the feeding reel has no price | — |
| `last_job_cost` | Cost of the last finished job | money | no job charged yet, or none of its reels had a price | — |
| `last_job_filament` | Grams charged for the last finished job | g, 1 decimal | no job charged yet | — |
| `filament_cost_total` | Lifetime spend on priced filament | money, 2 decimals; starts at **0** | never | `by_material_g`: map material → lifetime grams |
| `nozzle_filament_total` | Grams through the nozzle since the last reset | g, 1 decimal; starts 0 | never | — |
| `nozzle_abrasive_filament` | Grams of abrasive filament since the last reset | g, 1 decimal; starts 0 | never | — |
| `nozzle_wear_percent` | Abrasive grams against a 1000 g guide life | %, 1 decimal, capped at 100 | never | — |
| `spool_inventory_remaining` | Filament left across **every reel ever seen**, in the machine or not | g, 1 decimal | never | `spools`: list of `{material, color_hex, sku, remaining_g, remaining_percent, spool_price_per_kg}` (nulls for blanks), lowest remaining first |
| `spool_inventory_count` | Number of reels remembered | integer | never | — |

### 2.11 Resin printers (`lcd`, cloud only)

All from the cloud job's settings; resin printers are not supported over LAN.

| Key | What it says | Unit |
|---|---|---|
| `job_on_time` | Normal-layer exposure | s |
| `job_off_time` | Light-off time between layers | s |
| `job_bottom_time` | Bottom-layer exposure | s |
| `job_bottom_layers` | Number of bottom layers | layers |
| `job_model_height` | Model height (the cloud key is spelt `model_hight`) | mm |
| `job_anti_alias_count` | Anti-aliasing level (cloud key `anti_count`) | — |
| `job_z_up_height` | Lift height | mm |
| `job_z_up_speed` / `job_z_down_speed` | Lift and retract speed | none declared (§9, V5) |

### 2.12 Buttons

Every button that talks to the printer ends with an **immediate refresh**
(§5.1), unless marked "no refresh". "Wakes CMQTT" means: before sending, mark
the cloud MQTT link as needed for 5 minutes, start it if the connect mode
allows (§5.2) and wait up to 10 s for it; if it does not come up, fail with the
translated error `mqtt_connect_timeout`. With no CMQTT possible (web token,
LAN-only, *Never connect*) the wait succeeds at once and the order is sent
anyway. Failures from the printer or cloud surface as a Home Assistant error
carrying the message.

| Key | Device | What pressing does | Preconditions | Transport |
|---|---|---|---|---|
| `pause_print` | printer | Pause the job (wakes CMQTT) | a job must exist, else nothing is sent (silently) | cloud order 2; LAN `print`/`pause` with the task id |
| `resume_print` | printer | Resume the job (wakes CMQTT) | as above | order 3; LAN `print`/`resume` |
| `cancel_print` | printer | Stop the job (wakes CMQTT) | as above | order 4; LAN `print`/`stop` |
| `request_file_list_local` | printer | Ask for the internal-storage list (wakes CMQTT). If 5 s later no list has ever arrived, restart CMQTT once and ask again. | printer online for the retry | order 103, cloud only |
| `request_file_list_udisk` | printer | Ask for the USB list (wakes CMQTT) | — | order 101, cloud only |
| `request_file_list_cloud` | printer | Fetch the account's cloud file list (wakes CMQTT, then HTTP) | — | HTTP |
| `refresh_mqtt_connection` | printer, diagnostic | Restart the cloud MQTT link: at most once per 5 minutes; if connected, disconnect, wait 2 s, then reconnect **if** the mode, the manual switch or a recent action calls for it; if not connected, clear any failed attempt and try again under the same rule | — | CMQTT |
| `request_axis_position` | printer, diagnostic, disabled | Ask where the head is (wakes CMQTT); the reply fills `axis_position_*` | — | order 1214; LAN `axis`/`query` |
| `axis_home_xy` | printer (`fdm`) | Home X and Y | refused while a job is in progress | order 201, axis 4, move type 2; LAN `axis`/`move` |
| `axis_home_z` | printer (`fdm`) | Home Z (X/Y homing does not cover Z) | refused while printing | axis 3, move type 2 |
| `axis_home_all` | printer (`fdm`) | Home X/Y, wait until the printer is neither moving nor busy (re-reading its state every 2 s, at most 45 s), then home Z | refused while printing | as above |
| `axis_move_x_plus` … `axis_move_z_minus` (6) | printer (`fdm`) | Jog one axis by the chosen step (`axis_step`) | refused while printing; the printer itself refuses an axis that has not been homed (`axis_move_failed` turns on) | axis x=1, y=2, z=3; move type plus=1, minus=0; distance = step in mm |
| `axis_motors_off` | printer (`fdm`) | Release the steppers (the printer then needs homing again) | refused while printing | order 1213; LAN `axis`/`turnOff` |
| `reset_nozzle_wear` | printer, config, disabled | Zero both nozzle counters after fitting a new nozzle | — | Ledger; no printer traffic |
| `ace_refresh_spools` | ACE 1 | Request a fresh slot report from the ACE (wakes CMQTT) | — | order 1206; LAN `multiColorBox`/`getInfo` |
| `ace_slot_N_feed` (4, disabled) | ACE 1 | Feed the reel in slot N of the **first** ACE to the hotend (feed type 1) | ACE present, else nothing sent | order 1208; LAN `multiColorBox`/`feedFilament` |
| `ace_retract` | ACE 1 | Retract whatever the first ACE is feeding (feed type 2, slot −1) | ACE present | order 1208 |
| `ace_slot_N_reset_spool` (4, config, disabled) | ACE 1 | Treat slot N as a brand-new reel: its used grams go to 0 **and** the reel's remembered history is forgotten (§3.3) | — | Ledger |
| `drying_start` | ACE 1 | Start drying the first ACE at the stored or material-default temperature and duration (§3.11) | ACE present | order 1207 (status 1); LAN `multiColorBox`/`setDry` |
| `drying_stop` | ACE 1 | Stop drying on **every** ACE (sends "not drying" for each connected box) (wakes CMQTT) | ACE present | order 1207 (status 0) |
| `drying_start_preset_1` … `_4` | ACE 1 | Start drying the first ACE with preset N from options (wakes CMQTT) | exists only when preset N has duration and temperature > 0; pressing with the preset missing does nothing | order 1207 |
| `secondary_ace_retract` | ACE 2 | Retract on the second ACE | — | order 1208, box 1 |
| `secondary_drying_start` | ACE 2 | As `drying_start`, box 1, defaults from the second ACE's material | — | order 1207, box 1 |
| `secondary_drying_stop` | ACE 2 | Stop drying on the second ACE only (wakes CMQTT) | — | order 1207, box 1 |
| `secondary_drying_start_preset_1` … `_4` | ACE 2 | Preset N on the second ACE (wakes CMQTT) | as the first ACE's | order 1207, box 1 |

Preset buttons (both ACEs) carry attributes `duration` (minutes) and
`temperature` (°C) from the options.

### 2.13 Numbers

| Key | Device | Range / step / mode | Current value | Setting it | Stored where |
|---|---|---|---|---|---|
| `set_target_nozzle_temp` | printer (`fdm`) | 0–320 °C, step 1, box | `target_nozzle_temp`; unknown when absent | sends a set-temperature order that works **idle or printing** (order 1216, heat type 0 = nozzle only; the other figure is sent as 0); LAN `tempature`/`set` | printer |
| `set_target_hotbed_temp` | printer (`fdm`) | 0–120 °C, step 1, box | `target_hotbed_temp` | order 1216, heat type 1 = bed only | printer |
| `set_fan_speed_pct` | printer (`fdm`) | 0–100 %, step 1, slider | `fan_speed_pct` | order 1221 with the part-fan key only; LAN `fan`/`setSpeed` | printer |
| `set_aux_fan_speed_pct` | printer (`fdm`) | 0–100 %, step 1, slider | `aux_fan_speed_pct` | order 1221, aux-fan key only | printer |
| `set_box_fan_level` | printer (`fdm`) | 0–100, step 1, slider | `box_fan_level` | order 1221, box-fan key only | printer |
| `ace_slot_N_spool_weight` (4, config, disabled) | ACE 1 | 0–10000 g, step **1**, box | the slot's starting weight; **1000** when never set | records the reel's starting weight (also on the remembered reel, together with its current used grams) | Ledger |
| `ace_slot_N_spool_price` (4, config, disabled) | ACE 1 | 0–1000, step 0.01, box, unit = HA currency | the reel's price per kilogram; **0** = not priced | records the price on the slot and the remembered reel | Ledger |
| `drying_set_temperature` | ACE 1, config | 35–70 °C, step 1, box | stored value, else the material default for the first ACE (§3.11) | stores it for the start buttons | Ledger (per printer, shared by both ACEs) |
| `drying_set_duration` | ACE 1, config | 1–720 min, step 1, box | stored value, else the material default | stores it | Ledger |

Setting any number ends with an immediate refresh. The five printer numbers do
not need a running job; they are available whenever the printer is.

### 2.14 Selects

| Key | Options | Current option | Choosing | Availability |
|---|---|---|---|---|
| `axis_step` (`fdm`) | `1 mm`, `15 mm`, `50 mm` | the stored step; `1 mm` when never set | stores the step (Ledger, per printer); used by the jog buttons | whenever the printer is |
| `set_speed_mode` (every printer) | the mode names from the cloud list (§1.5), in the printer's order | the `job_speed_mode` text | sends the code paired with the name as a print-settings change (order 6; LAN `print`/`update` with the task id). **Refused unless a job is in progress**; the code must be in the list; a name not in the list is an error | unavailable when the list is empty — i.e. always on LAN. Over the cloud the list survives the job, so it is available while idle but refuses a change |

Function names used in `current_status.supported_functions` (cloud function id
→ name): 1 `AXLE_MOVEMENT`, 2 `FILE_MANAGER`, 3 `EXPOSURE_TEST`,
7 `LCD_PEER_VIDEO`, 13 `FDM_AXIS_MOVE`, 22 `FDM_PEER_VIDEO`,
26 `DEVICE_STARTUP_SELF_TEST`, 27 `PRINT_STARTUP_SELF_TEST`,
28 `AUTOMATIC_OPERATION`, 29 `RESIDUE_CLEAN`, 30 `NOVICE_GUIDE`,
31 `RELEASE_FILM`, 32 `TASK_MODE`, 33 `LCD_INTELLIGENT_MATERIALS_BOX`,
34 `LCD_AUTO_OUT_IN_MATERIALS`, 35 `M7PRO_AUTOMATIC_OPERATION`,
36 `AI_DETECTION`, 37 `AUTO_LEVELER`, 38 `VIBRATION_COMPENSATION`,
39 `TIME_LAPSE`, 40 `VIDEO_LIGHT`, 41 `BOX_LIGHT`, 2006 `MULTI_COLOR_BOX`.
Unknown ids are left out.

### 2.15 Switches

| Key | Meaning | State source | Turning on / off | Notes |
|---|---|---|---|---|
| `ai_detection_enabled` (printer, config) | AI print-failure detection | the printer's `aiSettings` report (`ai_settings.status` non-zero = on). LAN asks for it every poll; over the cloud it only arrives when the printer volunteers it, e.g. after a change | order 1243 **cloud only** (the slicer marks it wide-area only): status 3 = on, 0 = off, every other setting kept as the printer last reported it (defaults when never reported: type 2, count 60, sensitivity `[1, 1]`, notice type `[0, 1]`) | **unknown** until reported; does not wake CMQTT |
| `multi_color_box_runout_refill` (ACE 1) | ACE run-out refill (auto-feed) | box `auto_feed` 0/1 | wakes CMQTT; if the cached state already matches, nothing is sent; otherwise the cached state is set at once and order 1212 sent (LAN `multiColorBox`/`setAutoFeed`) | off when no box |
| `secondary_multi_color_box_runout_refill` (ACE 2) | Same for the second ACE | box 1 | as above, box 1 | — |
| `manual_mqtt_connection_enabled` (printer, diagnostic) | Hold the cloud MQTT link open regardless of the connect mode | the integration's own flag | sets/clears the flag; takes effect at the next connection check | held **in memory only** — false after every restart or reload; one flag per entry shared by all its printers; no effect in *Never connect* mode or without MQTT support |

Every switch ends with an immediate refresh.

### 2.16 Light — `printer_light`

- **Exists** on every printer; **available** only once the printer has been
  known to have a controllable light — from a live report or remembered from
  an earlier session (§3.13). Resin and older models may never report one.
- **State**: on/off from the printer's light report (LAN §6.5; CMQTT the same
  kinds). Unknown while a remembered light has not reported since the entry
  was built.
- **On/off only.** On a Kobra S1 only 0 and 100 have any effect, and the
  vendor slicer sends nothing else, so no dimming is offered. On sends status
  1 with brightness 100; off sends status 0 with brightness 0 (LAN answer Q9).
- Commands name the printer's light **type** — the lowest type it has
  reported (a Kobra S1 uses 2). Both on and off wake CMQTT first. Cloud order
  1233 (sent with the job's id when a job exists, the form proven on the
  cloud, else printer-level); LAN `light`/`control`. Ends with a refresh.

### 2.17 Update entities

| Key | Installed version | Latest version | Install |
|---|---|---|---|
| `fw_version` (printer) | printer firmware from the cloud printer record, updated by CMQTT `ota` `reportVersion` | the cloud's target version | wakes CMQTT; asks the cloud to update **only** if the cloud flags an update as available; otherwise nothing happens |
| `multi_color_box_fw_version` (ACE 1) | ACE 1 firmware (cloud) | cloud target version | same, box 0 |
| `secondary_multi_color_box_fw_version` (ACE 2) | ACE 2 firmware (cloud) | cloud target version | same, box 1 |

Supports install and progress. *In progress* is true from the moment an update
starts (CMQTT `ota` `update`/`start`) until the printer reports a new
version. Progress, in 2.x only turned into a true/false flag, is: download
phase 0–50 % (half the download percentage), install phase 50–100 % (50 + half
the update percentage), 1 when started with no figures yet. All firmware data
is cloud-only; see §7, G10 for what 2.x shows when it has no value.

### 2.18 Cameras

| Key | What it is | Available when | Behaviour |
|---|---|---|---|
| `camera` | The printer's own HTTP-FLV stream (`info.urls.rtspUrl`, port 18088, LAN §6.1) | the LAN connection is up **and** a stream URL is known: the one the printer named, else `http://<configured host>:18088/flv` | Supports streaming; stills are taken from the running stream (the printer serves one stream only and has no snapshot endpoint — opening a second connection for a still broke the live view, #20). Every time a stream is requested, first publish to the printer on LAN kind `video` the message `{"type": "video", "action": "startCapture", "data": {}}` — the stream stays silent until told (LAN only; the same message over the cloud is ignored by the printer). **Kobra X (model id 20030)** answers the stream with HTTP 206: stream it through an internal Home Assistant endpoint that relays the bytes unchanged but answers 200 (content type from the printer, default `video/x-flv`; no caching), protected by a random per-entity token. |
| `cloud_camera` | The cloud camera, as Agora WebRTC | the printer is loaded and it has **not** reported "no camera" (not having answered yet counts as available) | Browser is the WebRTC peer; Home Assistant only relays signalling. Each viewing session asks the cloud for fresh single-use Agora credentials (cloud order 1001, the credentials come back in the HTTP reply). If none come back, retry once after forcing a fresh cloud login (another Anycubic session — slicer or app — takes the camera away from older sessions); if still none, fail explaining that either there is no camera or another Anycubic session has it. No video passes through Home Assistant, so the still image is a fixed placeholder picture. Sessions are closed when the browser ends them or the entity is removed. See §9, V8. |

---

## 3. Computed features

### 3.1 The filament ledger and when it moves

The ledger (COMPAT §6, store `anycubic_cloud.filament.<entry id>`) holds, per
printer: per-slot figures, the last charged job id, totals, nozzle counters,
the jog step, drying settings and the feeding slot; and, per entry: every reel
ever seen (by signature) and per-model job history.

On each ledger update, for each printer, in this order:

1. **Reel changes** (§3.3).
2. **Feeding-slot capture**: while a job is in progress and the first ACE
   reports a loaded slot ≥ 0, remember it (key `feeding_slot`). The live value
   returns to −1 the moment a job ends, so this is the only evidence of which
   reel fed a print started at the printer's own screen.
3. **Charge a finished job** (§3.5).

A failure in any of this must never fail the refresh. The ledger is saved
whenever something changed. Only the **first** ACE's slots are tracked; the
second ACE has no ledger in 2.x.

In 2.x this update runs only inside a successful cloud poll — never on a LAN
connection (§7, G1). 3.0 must run it on every refresh, whatever the transport.

### 3.2 Grams from length

Filament is 1.75 mm. For a length `L` mm of material with density `ρ` g/cm³:

`grams = π × (0.0875 cm)² × (L / 10) cm × ρ`

(≈ 2.98 g per metre of PLA). A missing, zero or negative length is 0 g.
Density lookup: trim and upper-case the material name, then exact match; no
match → default.

| Material | Density g/cm³ |
|---|---|
| PLA | 1.24 |
| PLA+ | 1.24 |
| PLA-SE | 1.24 |
| PETG | 1.27 |
| ABS | 1.04 |
| ASA | 1.07 |
| PC | 1.20 |
| PA | 1.14 |
| PAHT-CF | 1.30 |
| PACF | 1.30 |
| HIPS | 1.04 |
| TPU | 1.21 |
| anything else | 1.24 |

(Note the ACE set-slot action writes the material `PLA SE` with a space, which
does not match `PLA-SE`; the default gives the same density.)

### 3.3 Spool signature and reel memory

- A reel's **signature** is `material|#RRGGBB|sku` (material type, the slot's
  hex colour, SKU; each may be empty). All three empty → no signature. These
  three are all the ACE says about a reel, so two genuinely identical reels
  share one signature (the reset button handles that case).
- Every ledger update, for the first ACE's slots:
  1. **Bank first**: for every slot with a signature in the report, copy the
     slot's current figures (used grams, weight, price) into the remembered
     reel under the signature the slot **previously** held. Doing all slots
     before resolving any lets two reels that swapped places each find their
     own history.
  2. **Resolve**: for every slot whose reported signature differs from its
     stored one:
     - the signature is remembered → restore its used grams, weight and price
       into the slot;
     - else, if the slot had a previous signature → a new reel: used 0,
       weight 1000 g, price 0 (unpriced);
     - else (first sighting of this slot) → keep the slot's figures;
     - then store the new signature on the slot.
- Empty slots still report their last reel (§1.9), so removing a reel changes
  nothing; inserting a different one does.
- Setting a slot's weight also updates the remembered reel's weight and used
  grams; setting its price updates the remembered reel's price. Resetting a
  slot zeroes its used grams and **deletes** the remembered reel (so putting
  it back does not restore the old figure); the next update re-banks it at 0.
- The remembered reels are what `spool_inventory_*` report.

### 3.4 Remaining grams and percentage

Per slot, from its stored weight `W` (default 1000 g) and used grams `U`:

- **Grams** = max(0, `W − U`), rounded to 0.1 g.
- **Percent** = (`W − U`) ÷ max(`W`, 1000) × 100, clamped to 0–100, rounded to
  0.1. The denominator is a **full reel**, not the weight entered. Example: a
  reel whose starting weight was entered as 334 g and which now holds 283 g
  shows 28 % (283 of 1000), not 85 %. For reels heavier than 1000 g the
  denominator is the reel's own weight (a full 5 kg reel shows 100 %).
- Both have no value when the slot is empty (`edit_status` 2) or unreported.
  The stored figures are untouched, so putting the reel back restores them.

### 3.5 Charging a finished job

When the job exists, is **not** in progress, has an id, and its extruded
length (`job_filament_used`) is non-zero:

1. **Double-charge protection**: if its id equals the stored `last_job_id`,
   stop. Otherwise store its id as `last_job_id` **whatever happens next**, so
   a job that cannot be attributed is not retried forever.
2. **Which slot fed it**: the live loaded slot of the first ACE if ≥ 0, else
   the remembered feeding slot.
3. **Split between slots**: from the cloud job's slice data, the per-colour
   breakdown (`paint_infos`: `paint_index` and `filament_used`). Sum
   `filament_used` per `paint_index`, ignoring non-positive or malformed
   entries, and turn into shares summing to 1.
   - With **one or no** share and a known feeding slot: 100 % to the feeding
     slot. (The slicer's colour index is not a slot number: a one-colour job
     has index 0 whichever slot fed it.)
   - With no shares and no feeding slot: the job cannot be attributed —
     nothing is charged.
   - With several shares: each `paint_index` is treated as the slot index
     (§9, V2).
4. **Grams per slot** = §3.2 on (extruded length × share), with that slot's
   material (as reported for that slot, even if the slot now reads empty).
   Because the length is what the printer actually pushed out, purge waste is
   included and a stopped job costs only the part that printed.
5. Add each slot's grams to its used grams (rounded to 0.01 g).
6. Book totals (§3.8), nozzle wear (§3.9), job history (§3.7); forget the
   remembered feeding slot.

On the very first ledger update after installation the account's latest job is
already finished and has no stored `last_job_id`, so it is charged once
(§9, V3).

### 3.6 Run-out forecast

Only while the job is **in progress**. Otherwise every forecast value has no
value.

1. **Slot**: the first ACE's live loaded slot, else the remembered feeding
   slot; none → no forecast. Material = that slot's reported material.
2. **Required grams**, in order of preference:
   - **History**: if this model has been printed before (§3.7), the average of
     its recorded jobs. Available from the first second of the job. On a real
     print the history figure came within 0.2 % of the final use, while
     extrapolation at 39 % progress was 17 % off.
   - **Extrapolation** by the two-observation rate method:
     - The *anchor* is the first observation of this job (per printer, by job
       id) at which progress is **≥ 3 %**. Its extruded length and progress
       are kept in memory only (after a restart during a print a fresh anchor
       is taken, which is correct). The observation that sets the anchor
       produces no answer. Before 3 % there is no anchor and no answer (the
       purge may still be running). A new job id replaces the anchor.
     - An answer appears once progress is at least **5 percentage points**
       past the anchor. With `Lnow`, `Pnow` now and `La`, `Pa` at the anchor:
       `rate = grams(Lnow − La) ÷ (Pnow − Pa)` g per %;
       `required = grams(Lnow) + rate × (100 − Pnow)`, rounded to 0.1 g.
     - No answer when: length missing or ≤ 0; progress ≤ 0 or > 100; the
       grams since the anchor ≤ 0.
     - Do **not** divide the total so far by the progress: purge and priming
       happen up front and inflate that ratio (a real job of about 52 g came
       out at 125 g at 5 %). Measuring between two observations removes the
       up-front amount.
   - `source` attribute = `history` or `extrapolated` accordingly.
3. **Remaining** = §3.4 grams for that slot (the stored figure, even if the
   slot reads empty).
4. `required ≤ 0` → no forecast. Otherwise:
   - `shortfall = max(0, required − remaining)`;
   - `runs out at = 100` if no shortfall, else `remaining ÷ required × 100`,
     capped at 100;
   - all rounded to 0.1; `insufficient = shortfall > 0`;
   - `job_cost` = §3.8 cost of `required` grams at the feeding reel's price.

### 3.7 Job history

- Key = the job's name, trimmed, with a leading slicer timestamp of the form
  four digits, hyphen, four digits, hyphen removed (e.g. `0622-1002-`); an
  empty result → no history.
- When a job is charged, its total grams (rounded to 0.1) are appended; only
  the **5** most recent samples are kept.
- The estimate is the mean of the positive samples, rounded to 0.1 g.
- Observed: repeated prints of one model used 50.34, 49.49 and 49.49 g.

### 3.8 Cost

- Price is per kilogram, per reel (travels with the signature like the
  weight). **0 means unpriced.**
- Cost of `g` grams at price `p` = `g ÷ 1000 × p`, rounded to 0.01 — or **no
  value** when either `g` or `p` is ≤ 0 or missing. Never report an unpriced
  job as free.
- On charging a job: sum the cost of each slot's grams whose reel is priced.
  `last_job_cost` = that sum if at least one slot was priced, else **no value**
  (partially priced jobs count only the priced part). `last_job_filament` =
  total grams of the job (0.1). If priced, add the sum to `cost_total`.
- `material_totals` adds each slot's grams under its material name (if it has
  one).
- The currency is Home Assistant's configured currency; nothing is converted.

### 3.9 Nozzle wear

- For each slot's grams in a charged job: add to `nozzle_total_g`; if the
  slot's material is abrasive, also add to `nozzle_abrasive_g`. Both counters
  exist (at 0) from the first charged job.
- **Abrasive** = the upper-cased material name contains any of: `CF`, `GF`,
  `CARBON`, `GLASS`, `GLOW`, `GLITTER`, `WOOD`, `METAL` (so `PACF` and
  `PAHT-CF` count). Matching is intentionally broad.
- `nozzle_wear_percent` = min(100, abrasive grams ÷ 1000 × 100), 0.1. 1000 g is
  a rough replacement guide for a brass nozzle on abrasive filament, shown as
  a percentage rather than raised as an alert.
- `reset_nozzle_wear` sets both counters to 0.

### 3.10 Spool inventory

- `spool_inventory_count` = number of remembered reels (entry-wide — the same
  on every printer of the entry).
- `spool_inventory_remaining` = sum over remembered reels of §3.4 grams,
  rounded to 0.1. Its `spools` attribute lists each reel with material, colour
  and SKU split back out of the signature (blanks → null), remaining grams and
  percent, and price per kg (null when unpriced), sorted by remaining grams,
  lowest first.

### 3.11 Drying defaults

- A drying start uses, per value: the stored setting (numbers
  `drying_set_temperature` / `drying_set_duration`; stored per printer and
  shared by both ACEs), else the recommended profile for the material **in the
  ACE being dried**.
- "Material in the ACE": the loaded slot's material (first ACE: live loaded
  slot, else the remembered feeding slot; second ACE: its live loaded slot
  only); if none, the first slot that is not empty and has a material; else
  unknown.
- Profile lookup: trim and upper-case, exact match; unknown → default.

| Material | Temperature °C | Duration h (min) |
|---|---|---|
| PLA | 45 | 6 (360) |
| PLA+ | 45 | 6 (360) |
| PLA-SE | 45 | 6 (360) |
| PETG | 65 | 6 (360) |
| ABS | 70 | 4 (240) |
| ASA | 70 | 4 (240) |
| PC | 70 | 6 (360) |
| PA | 70 | 12 (720) |
| PAHT-CF | 70 | 12 (720) |
| PACF | 70 | 12 (720) |
| HIPS | 65 | 4 (240) |
| TPU | 50 | 8 (480) |
| anything else | 45 | 6 (360) |

Every figure is below the temperature at which that material starts to
soften; when in doubt the table errs cool, since an over-heated reel is lost
while an under-heated one merely dries slowly.

- Options presets (`drying_preset_duration_N` minutes, `drying_preset_temperature_N`
  °C) are separate and fixed; a preset button uses exactly its preset.
- The drying order sends, per box: status (1 start, 0 stop), target
  temperature, duration, and the box id.

### 3.12 Jog step

Stored per printer in the ledger (`axis_step`), 1, 15 or 50 mm, default 1. A
free-text step is deliberately not offered.

### 3.13 Capability memory (light)

Store `anycubic_cloud.capabilities.<entry id>` (COMPAT §6). Whenever a pushed
report is processed, any light type a printer has reported that is not yet
remembered is added to that printer's `light_types` list and saved. A printer
"has a light" if it reports one now **or** one is remembered — so the light
entity stays available across restarts even though the printer mentions its
light only when asked.

### 3.14 Capability polling (cloud)

Whether a printer has a camera, and whether it has a light, are only learnt
from the printer's replies. Over the cloud these are asked for:

- 10 s after the CMQTT link subscribes, for every **online** printer
  (peripherals + light status);
- at the end of each successful cloud poll while CMQTT is up, for online
  printers still missing either answer — at most **3** times per printer; the
  count resets when a printer comes back online after being seen offline.

This polling never opens CMQTT on its own: an Anycubic account can hold only
one such session, and taking it would cut off the user's slicer. Over LAN
both are part of the regular query set (LAN §7.1).

---

## 4. Actions

Answers COMPAT open question C2. All actions are registered when the
integration loads, even with no entry set up, so automations referring to them
validate. The handlers fail if their entry is missing.

### 4.1 Choosing the printer (every action)

| Field | Type | Selector | Required | Meaning |
|---|---|---|---|---|
| `config_entry` | config-entry id | config entry, filtered to this integration | **yes** | which entry |
| `device_id` | device id (a list of exactly one is also accepted) | device, filtered to this integration | one of `device_id` / `printer_id` | the **printer** device (an ACE device is not accepted) |
| `printer_id` | integer ≥ 0 | number, box, 0–9999999999999999999, step 1 | one of `device_id` / `printer_id` | the printer id (cloud id, or the LAN-derived id of COMPAT §2) |

`device_id` wins when both are given. Missing both is a schema error.

Errors (translation keys, raised as service-validation errors):

| Key | When |
|---|---|
| `config_entry_not_found` | no entry with that id |
| `config_entry_not_loaded` | the entry exists but is not set up |
| `one_printer_at_a_time` | `device_id` lists more than one device |
| `printer_not_found` | the device/printer id is not a loaded printer of that entry |
| `gcode_read_failed` | an uploaded file could not be read (§4.4) |
| `printer_busy` | `print_local_file` while the printer is busy or a job is in progress |
| `mqtt_connect_timeout` | (home-assistant error) an action that needs CMQTT could not bring it up within 10 s |

Any failure reported by the printer or the cloud surfaces as a Home Assistant
error carrying that message. Orders with a LAN form (§5.3) go over LAN while
the LAN link is up; the rest go to the cloud, which cannot reach a printer in
LAN Mode.

### 4.2 ACE slot definition — `multi_color_box_set_slot_<material>` (9 actions)

Tell the ACE what is in a slot (material and colour), as when editing a slot
by hand in the slicer.

| Action suffix | Material string sent |
|---|---|
| `pla` | `PLA` |
| `petg` | `PETG` |
| `abs` | `ABS` |
| `pacf` | `PACF` |
| `pc` | `PC` |
| `asa` | `ASA` |
| `hips` | `HIPS` |
| `pa` | `PA` |
| `pla_se` | `PLA SE` |

| Field | Type | Selector | Required | Notes |
|---|---|---|---|---|
| `box_id` | integer ≥ 0 | number box 0–7 | no (default 0) | 0 = first ACE, 1 = second |
| `slot_number` | integer ≥ 0 (validated as non-negative; meaningful 1–4) | number box 1–4 | yes | slot on that ACE, 1-based; sent 0-based |
| `slot_color_red` / `_green` / `_blue` | integer 0–255 | number box 0–255 | yes | colour |

Sends cloud order 1211 / LAN `multiColorBox`/`setInfo` with the box id and one
slot `{index, type, color [r,g,b]}`. No check that an ACE exists and no
printing precondition. Ends with a refresh. Filament printers with an ACE;
both transports.

### 4.3 ACE feed and retract

**`multi_color_box_filament_extrude`** — feed a slot's filament to the
hotend, or end a feed.

| Field | Type | Selector | Required | Notes |
|---|---|---|---|---|
| `box_id` | integer ≥ 0 | number box 0–7 | no (default 0) | |
| `slot_number` | integer ≥ 0 (meaningful 1–4) | number box 1–4 | yes | 1-based |
| `finished` | boolean | boolean | no (false) | true sends the *finish* feed type (3) that ends a feed; false sends *feed* (1). A feed should be followed by a finish. |

Nothing is sent when the printer has no ACE or the slot index is negative.
**No refresh** afterwards. Order 1208 / LAN `multiColorBox`/`feedFilament`.

**`multi_color_box_filament_retract`** — pull the loaded filament back into
the ACE. Field `box_id` (as above). Feed type 2 with slot −1. Nothing sent
without an ACE. No refresh.

### 4.4 Print a file

**`print_and_upload_save_in_cloud`** and **`print_and_upload_no_cloud_save`**
— upload a sliced file and start printing it. **Cloud only** (the print order
has no LAN form and the file goes through Anycubic's storage).

| Field | Type | Selector | Required | Notes |
|---|---|---|---|---|
| `slot_number` | list of integers ≥ 0 (a single number is accepted as a list of one) | object, example `[1, 2]` | see below | ACE slot per colour of the file, in the file's colour order; 1-based across boxes: 1–4 first ACE, 5–8 second |
| `uploaded_gcode_file` | uploaded-file id | file (the validation schema accepts `.gcode`; the action description also lists `.pwsp`, `.pwsq`, `.zip` — §9, V6) | yes | the file |

Rules:

- The uploaded file is read up to 3 times, 1 s apart, if not yet available;
  failure → `gcode_read_failed`.
- Printer **with** an ACE: `slot_number` is required; its length must equal
  the number of colours in the file; the highest slot must lie on a connected
  ACE. Printer **without** an ACE: `slot_number` must be absent. Violations
  are errors.
- *Save in cloud*: upload to the account's permanent cloud storage; check that
  the newest cloud file is the one just uploaded; read its colour list from
  the cloud; map slots; start the print, retrying up to 3 times 3 s apart if
  the cloud does not yet know the file.
- *No cloud save*: read the colour list from the file itself (the file name
  must end `.gcode`); upload as a temporary file that the cloud deletes after
  printing; start the print.
- Slot mapping sends, per colour: the ACE slot index (0-based across boxes),
  the grams the slicer planned, the material type, and the slot's current
  colour.
- On success an event is fired (§4.8).

**`print_local_file`** — start printing a file already on the printer.

| Field | Type | Selector | Required | Notes |
|---|---|---|---|---|
| `filename` | text | text | yes | exact name as listed in `file_list_local`'s `file_info` |

Refused with `printer_busy` while the printer is busy or a job is in progress.
Cloud order 1 (start print) with the local file name and an empty path —
**cloud only**. Ends with a refresh.

### 4.5 Delete files

| Action | Field | Type / selector | Effect | Transport |
|---|---|---|---|---|
| `delete_file_local` | `filename` (required) | text | delete from internal storage (order 104: name, file type −1, path `/`); then request the local list twice, 2 s and 7 s later | cloud order; reply over CMQTT |
| `delete_file_udisk` | `filename` (required) | text | delete from the USB stick (order 102); then request the USB list twice as above | cloud |
| `delete_file_cloud` | `file_id` (required) | integer ≥ 0; number box 0–9999999999999999999 | delete from the account's cloud storage; a refusal → error; on success re-fetch the cloud list 5 s later | HTTP. The printer selector is still required, though unused. |

None of these wakes CMQTT first (§7, G16).

### 4.6 Change settings

| Action | Field | Type | Selector | Needs a running job? | Effect |
|---|---|---|---|---|---|
| `change_print_target_nozzle_temperature` | `temperature` | integer ≥ 0 | number box 0–400 | **no** | as the number `set_target_nozzle_temp` (order 1216); refresh after |
| `change_print_target_hotbed_temperature` | `temperature` | integer ≥ 0 | number box 0–400 | no | as `set_target_hotbed_temp`; refresh |
| `change_print_fan_speed` | `speed` | integer ≥ 0 | number box 0–100 | no | as `set_fan_speed_pct` (order 1221); refresh |
| `change_print_aux_fan_speed` | `speed` | integer ≥ 0 | number box 0–100 | no | as `set_aux_fan_speed_pct`; refresh |
| `change_print_box_fan_speed` | `speed` | integer ≥ 0 | number box 0–100 | no | as `set_box_fan_level`; refresh |
| `change_print_speed_mode` | `speed_mode` | integer ≥ 0 (a mode **code**, §1.5) | number box 0–100 | **yes** | print-settings change (order 6; LAN `print`/`update` with the task id). The code must be one the cloud lists for the job; with no list (LAN) it always fails. No refresh. |
| `change_print_bottom_layers` | `layers` | integer ≥ 0 | number box 0–9999999999999999999 | yes | resin: bottom-layer count (order 6). No refresh. |
| `change_print_bottom_time` | `time` | number ≥ 0 | number box 0–9999999999999999999, step 0.001 | yes | resin: bottom exposure (s) |
| `change_print_off_time` | `time` | number ≥ 0 | as above | yes | resin: light-off time (s) |
| `change_print_on_time` | `time` | number ≥ 0 | as above | yes | resin: normal exposure (s) |

"Needs a running job" is checked in this order, each a service-validation error
with an untranslated English message in 2.x: printer not busy; no job; job not
in progress. The temperature and fan actions have no range check beyond ≥ 0 —
the printer enforces its own limits. Temperature and fan actions work on both
transports; the resin actions are cloud only.

### 4.7 Summary: which printers and transports

| Action group | Printers | Cloud | LAN |
|---|---|---|---|
| set slot, extrude, retract | filament printer with an ACE | yes | yes |
| print and upload (both), print local file | any | yes | **no** |
| delete local / USB file | any | yes (reply needs CMQTT) | no |
| delete cloud file | any cloud entry | yes | no |
| nozzle/bed temperature, fans | filament | yes | yes |
| speed mode | filament, with the cloud's mode list | yes, while printing | fails (no list) |
| bottom layers / times | resin | yes, while printing | no |

### 4.8 Event after a cloud print

Event type **`anycubic_cloud`**, fired after either print-and-upload action
succeeds. Data:

| Key | Value |
|---|---|
| `printer_id` | printer id |
| `printer_name` | printer name |
| `device_id` | the device id given to the action, or null (§7, G17) |
| `type` | `print_cloud_start` |
| `event_data` | `order_msg_id` (text), `printer_id`, `saved_in_cloud` (bool), `file_name`, `cloud_file_id`, `gcode_id` (null for no-cloud-save), `material_list` (the file's colour list), `ams_box_mapping` (list of `{ams_color [r,g,b], ams_index, filament_used, material_type, paint_color [r,g,b], paint_index}` or null) |

---

## 5. Connection behaviour and setup flows

### 5.1 Refresh cadence

| What | When |
|---|---|
| Coordinator refresh | every **15 s** |
| LAN query set (LAN §7.1: info, tempature, fan, light, multiColorBox, print, aiSettings, peripherie, axis, extfilbox) | every refresh while LAN is connected, and once right after connecting |
| Cloud HTTP poll (token check, printer record and latest job per printer, then CMQTT management, new-printer pickup, capability poll, ledger update) | at most every **60 s**, skipped entirely while LAN is connected and never done for LAN-only entries |
| After a control (button, number, switch, select, most actions) | an immediate refresh including a cloud poll; the next cloud poll then follows about 10 s later |
| A pushed report (CMQTT or LAN) | the state map is rebuilt immediately, marked successful, and capability memory updated |
| CMQTT reports a printer going from free to busy (a print started) | an extra full refresh 5 s later |
| Cloud poll failures | after **3** consecutive failures the next due poll is skipped and polling pauses for about 5 minutes (4 minutes on top of the normal 60 s) |

### 5.2 Cloud MQTT (CMQTT)

Only for cloud entries whose token supports MQTT login (slicer or Android;
never web). The option `mqtt_connect_mode` (absent = 1):

| Value | Name | Hold the link open while | Release when |
|---|---|---|---|
| 1 | Printing only (default) | any printer is busy | no printer busy and no job in progress, continuously for 15 min |
| 2 | Printing and drying | any printer busy, or any ACE drying | none busy, no job in progress and nothing drying, for 15 min |
| 3 | Device online | any printer online (or busy) | no printer online, for 15 min |
| 4 | Always | always | never (only on unload/shutdown) |
| 5 | Never connect | never — not even for actions or the manual switch | — |

Additional rules:

- **Actions**: any control that "wakes CMQTT" (§2.12) counts as a reason to be
  connected for **5 minutes**, whatever the mode (except *Never*). Only after
  those 5 minutes does the 15-minute idle clock start.
- **Manual switch** (`manual_mqtt_connection_enabled`): while on, connect and
  never release for idling.
- **When checked**: at the end of each successful cloud poll, on every
  "wake", and by the refresh button. Nothing is started while Home Assistant
  is starting or stopping; on stop the link is closed.
- **Starting**: subscribe to every printer's topics and the user's slice
  report topics; 10 s after subscribing, ask each online printer for
  peripherals and light (§3.14). "Connected" for waiting purposes means the
  subscription was acknowledged; the wait is 10 s.
- **Failure**: the reason (error type, message, broker host:port) is logged
  once as an error and kept as the `last_error` attribute of
  `mqtt_connection_active`; the next check may try again. A failed attempt
  must never block later attempts (§6, B12).
- **Unexpected disconnect**: reconnect automatically after 5 s, recomputing
  the login first (tokens may have been refreshed).
- **Refresh button**: §2.12.
- Every pushed report is applied even if part of it is not understood; the
  state map is rebuilt after every report.

Cloud protocol facts (broker per region, client identity, login derivation,
TLS material, topics, order payloads) are **not** in this document — see §9,
V7.

### 5.3 LAN

Wire protocol: LAN §2–§7. Behaviour:

- **Handshake and connect**: discovery (LAN §2), signed control request
  (LAN §3), broker connect (LAN §4: TLS without verification, client id
  `ha-` + 12 hex, keepalive 60 s, 15 s to be subscribed). Credentials are held
  in memory only.
- **When**: at setup (hybrid and LAN-only), and on every refresh while no LAN
  client exists. A failure is never fatal and only logged at debug.
- **Reports**: bare acknowledgements (no `type`) are dropped. A report that
  fails to parse is dropped without affecting the connection. With one printer
  on the entry every report is for it; with several, the report's model id
  must match the printer's model id, otherwise it is dropped (a warning
  logged once).
- **Building the printer (LAN-only, or hybrid when the cloud cannot supply
  it)**: connect, ask for `info` and wait up to **20 s** for it (none →
  setup is retried later). Identity: model id from the discovery document;
  model name from the discovery document, else the `info` model; name from
  `info.printerName`, else the model name; key = the broker's device id; MAC
  from the discovery URN, upper-case and hyphen-separated like the cloud's
  (this is what keeps unique ids identical across modes); printer id = the
  configured id (COMPAT §2). Material type from `deviceType` (§1.7). Every
  report received so far is applied, then the full query set is sent.
- **Orders**: while LAN is connected, any order with a LAN form goes over LAN
  (the printer can then only be reached that way); orders without one still go
  to the cloud:

| Function | Cloud order | LAN kind / action (LAN §7.2) |
|---|---|---|
| pause / resume / stop job | 2 / 3 / 4 | `print` / `pause` `resume` `stop` + task id |
| print-settings change (speed mode, resin settings) | 6 | `print` / `update` + task id |
| jog / home axis | 201 | `axis` / `move` |
| motors off | 1213 | `axis` / `turnOff` |
| head position query | 1214 | `axis` / `query` |
| set temperatures | 1216 | `tempature` / `set` |
| set fans | 1221 | `fan` / `setSpeed` |
| ACE get info | 1206 | `multiColorBox` / `getInfo` |
| ACE drying | 1207 | `multiColorBox` / `setDry` |
| ACE feed / retract | 1208 | `multiColorBox` / `feedFilament` |
| ACE set slot | 1211 | `multiColorBox` / `setInfo` |
| ACE run-out refill | 1212 | `multiColorBox` / `setAutoFeed` |
| peripherals query | 1231 | `peripherie` / `query` |
| light query | 1232 | `light` / `query` |
| light control | 1233 | `light` / `control` |
| start print (upload, local file) | 1 | **none** |
| list / delete local or USB files | 101–104 | **none** |
| AI detection settings | 1243 | **none** (cloud only) |
| camera open (Agora) | 1001 | none — the LAN camera is `video`/`startCapture` (§2.18) |
| firmware updates | HTTP | none |

- The order payload is the same on both transports; LAN commands carry the
  job's task id inside `data` where needed (as text).

### 5.4 Hybrid entries

- Setup skips the cloud's "is this printer still in the account" check when
  LAN Mode is on.
- Printers: ask the cloud first; if it cannot supply the printer, build it
  from LAN (§5.3).
- While LAN is connected: no cloud poll at all (no token check, no job list,
  no CMQTT management, no firmware data).
- While LAN is enabled but not connected: the cloud is polled as for a cloud
  entry. If that poll fails, stay unavailable (§5.5) until either LAN connects
  or a cloud poll succeeds.

### 5.5 Printer off, outages, never flap

Requirement for 3.0, all entry kinds:

- **When the data source is lost, every entity becomes unavailable once and
  stays unavailable until the source answers again.** No alternating between
  stale values and unavailable (#38 was every entity toggling every 15 s /
  60 s for as long as a LAN printer was off).
- LAN printer switched off or asleep: the broker stops answering (LAN §10).
  LAN-only: unavailable from the first refresh without a connection. Hybrid:
  from the first failed cloud poll, as above.
- Re-run the full handshake when reconnecting — the printer rotates its
  credentials (LAN §10; §7, G2).
- Cloud entry, printer off: the cloud still answers, so entities stay
  available with the cloud's last values and `printer_online` turns off.
- Cloud unreachable: log the outage once (warning) and the recovery once
  (info); do not log every poll. (2.x flaps here too — §7, G3.)

### 5.6 Tokens, expiry and re-authentication

- **Token store** (`anycubic_cloud.<entry id>`, COMPAT §6): after a successful
  setup the working session (including tokens the cloud refreshed) is saved;
  it is saved again whenever a poll finds the tokens changed. At setup the
  stored tokens are laid over the pasted one. If the cloud refuses them and
  stored tokens were used, retry once with **only the pasted token**; success
  overwrites the store. (Logging in from the slicer or the phone app regularly
  invalidates the session Home Assistant holds.) A legacy un-suffixed store
  is read and copied to the per-entry key when the per-entry one is empty.
- **Slicer tokens** are exchanged for a user token (2 attempts, 2 s apart); if
  the exchange is refused the same token is retried as a web token before the
  credentials are called bad. **China**: the pasted slicer token is used
  directly as the user token (no exchange), otherwise MQTT login is impossible.
- **Rejected at runtime** → the entry asks for re-authentication.
- **Expiry repair**: at every refresh of a cloud entry, read the `exp` claim of
  the **pasted** token (without verifying it). If it expires within **14
  days** (including already expired), create/refresh the repair issue
  `token_expiring_<entry id>` (warning, not fixable, learn-more link to the
  token tools) with placeholders `days` (whole days left, floored, never below
  0), `name` (entry title), `reauth_url` (the My-Home-Assistant link to the
  integration), `tool_macos`, `tool_windows`, `tool_browser` (the three helper
  links). Otherwise delete it. A token with no readable `exp` creates nothing.
  Pasted tokens live roughly 90 days and there is no automatic renewal.
- **Re-authentication flow**: straight to the `cloud` form (§5.8), with the
  region pre-filled from the entry. On success: store the new token, auth mode,
  region and device id; **delete the token store** (so the old session cannot
  overwrite the new token); reload the entry; finish with
  `reauth_successful`.

### 5.7 Setting up an entry

- The dashboard card and side panel are registered **before** the first
  refresh, so a failing entry still serves its card (it shows unavailable
  rather than "custom element not found"). One panel for the whole
  integration; it is removed only when no entry of the integration is left
  loaded.
- Cloud entry:
  - no token → re-authentication;
  - token refused (after the pasted-token retry) → re-authentication;
  - first printer: the cloud answered but its reply could not be read →
    *not ready*, message says it is a fault in the integration (not
    credentials, not LAN Mode) and asks for a report with model and firmware;
  - first printer: any other error (e.g. the cloud reporting it deleted —
    what LAN Mode does) or nothing returned → *not ready*, message explains
    LAN Mode and how to enable the local connection;
  - any other unexpected error → *not ready* (never re-authentication).
- Cloud "request error" answers (rate limiting, maintenance) during setup are
  retried 3 times, 10 s apart, then setup fails with a terminal error.
- Printers neither the cloud nor LAN can supply → *not ready* (retried with
  back-off), never a terminal failure (2.x exception: §7, G23).
- Options or data changes reload the entry.
- Unload: close CMQTT, close LAN.

### 5.8 Config flow

Step ids and field keys are in COMPAT §1.

| Step | Asks | Validates | Errors shown | Result |
|---|---|---|---|---|
| `user` (menu) | how to reach the printer | — | — | `cloud` (Anycubic account) or `local` (LAN Mode, no account) |
| `cloud` | `user_token` (required; paste anything), `user_device_id` (optional, Android only), `region` (drop-down `international` default / `china`, labelled with each operator's domain) | 1. **Extract** a token from what was pasted: a JWT anywhere in the text wins; else a JSON object's `access_token`, `XX-Token`, `token` or `auth_token` (also nested under `anycubic_cloud`); else a `key: "value"` fragment with those keys; else the text stripped of wrapping brackets and quotes, rejected if it contains whitespace. 2. **Expired** JWT (`exp` ≤ now). 3. **Signature**: only for tokens whose issuer is `https://uc.makeronline.com`: verify RS256 against the keys at `https://uc.makeronline.com/.well-known/jwks` (fetch with a browser-like user agent; 15 s timeout). An over-long signature is cut to the length the key's modulus implies and accepted if it then verifies. Keys unavailable **or empty** → accept (China publishes an empty key set). Issuer present but no signature segment → corrupted. 4. **Log in**, trying modes in order: with a device id, Android only; otherwise the guess first (starts with `eyJ` → slicer, else web), then the other of slicer/web; each attempt with a fresh client. | `user_token`: `invalid_token_format`, `token_expired`, `token_corrupted`; `base`: `invalid_auth`, `wrong_token_type` (the JWT's `tokenType` claim exists and is not `access-token`; not checked for China), `cannot_read_response` (the reply could not be parsed), `cannot_connect` (anything else) | reauth/reconfigure: update the entry (§5.6), abort `reauth_successful`; new: go to `printer` |
| `printer` | `printer_ids`: multi-select of the account's printers (id → name) | the account has printers; each chosen printer's record can be fetched | `no_printers`, `invalid_printer`, `cannot_read_response`, `cannot_connect` | unique id = account user id. Reconfigure: update token, mode, region, device id, printer list; abort `reconfigure_successful`. New: abort `already_configured` if the account exists; else create the entry, title = account e-mail, else mobile, else user id; options empty |
| `local` | `lan_host` (pre-filled from discovery) | non-empty; LAN handshake succeeds | `lan_host`: `lan_host_required`; `base`: `lan_printer_in_cloud_mode` (discovery says `cloud`), `lan_unsupported_printer` (older printer, missing required fields), `lan_unreachable` (anything else) | unique id = the printer's MAC (`aa:bb:cc:dd:ee:ff`) or `lan-<host>`; if it exists, update its `lan_host` and abort `already_configured`; else create: title = discovery model name, else `Anycubic (<host>)`; data `{lan_host, printer_ids: [id]}`; options `{lan_mode_enabled: true, lan_host}` |
| `dhcp` (discovery) | — | unique id = discovered MAC; abort `already_configured` (updating `lan_host` to the new address — §7, G24) if an entry has it; also abort if **any device carrying that MAC** belongs to an entry of this integration (cloud entries are keyed by account, so without this every DHCP renewal re-offered the printer) | — | `confirm_discovery`; title placeholder `Anycubic (<ip>)` |
| `confirm_discovery` | nothing (placeholder `host`) | — | — | the `user` menu, with `local` pre-filled with the address |
| `reauth` | — | — | — | the `cloud` form |
| `reconfigure` → `reauth_or_choose_printer` (menu) | what to change | — | — | `reauth` (cloud form), `printer` (reuses the entry's token and stored session), `connection` |
| `connection` | `lan_mode_enabled` (bool, current value), `lan_host` (current value) | when enabling: non-empty host and a successful handshake; disabling needs no printer | `lan_host`: `lan_host_required`; `base`: `lan_*` as `local` | update the entry's options; abort `reconfigure_successful` (see §7, G5) |
| `auth_mode_pick` (menu), `auth_mode_web`, `auth_mode_slicer`, `auth_mode_android` | legacy: a token (and device id for Android) with a fixed mode | log in with that mode only (quotes stripped, no extraction or pre-checks) | `invalid_auth`, `wrong_token_type`, `cannot_read_response`, `cannot_connect` | as `cloud`, except that a re-authentication through them neither clears the token store nor reloads the entry; **not reachable from any menu in 2.x** (§9, V9) |

Config entry version 1.1. The flow never stores a password; LAN credentials
are never stored.

### 5.9 Options flow

| Step | Fields | Validation | Notes |
|---|---|---|---|
| `options_menu` | menu, in this order: `mqtt`, `drying` (only if a cloud login during the options flow finds any printer on the account that supports an ACE — never for LAN-only entries), `local`, `card_config`, `debug` | — | |
| `mqtt` | `mqtt_connect_mode`: one of 1–5 (§5.2), default the current value or 1 | — | saved; entry reloads |
| `drying` | `drying_preset_duration_1`–`4` (minutes), `drying_preset_temperature_1`–`4` (°C), all optional non-negative integers | non-negative | a preset needs both values > 0 to get buttons |
| `local` | `lan_mode_enabled`, `lan_host` | disabling: saved at once; enabling: host required and handshake must succeed | errors as `connection` |
| `card_config` | `card_config`: an object | when an object, keep only known keys of the right type: `vertical`, `round`, `use_24hr`, `showSettingsButton`, `alwaysShow` (bool); `temperatureUnit`, `lightEntityId`, `powerEntityId`, `cameraEntityId` (text); `monitoredStats`, `slotColors` (list of text); `scaleFactor` (number) | handed to the side panel |
| `debug` | `debug_api_calls`, `debug_mqtt_msg` (bools; default from the deprecated `debug`) | — | log every HTTP call / every CMQTT message. Logs must redact the printer key in topics. |

Every save merges into the existing options and reloads the entry.

---

## 6. Known 2.x bugs NOT to reproduce

Each was a real defect fixed in 2.x (issue numbers are hass-anycubic's).
Written as requirements.

| # | Requirement | Evidence |
|---|---|---|
| B1 | ACE-dependent entities must be **kept pending** until an ACE reports, never dropped at setup — a LAN-only printer learns about its ACE only after setup. | #41, 2.9.3 |
| B2 | A switched-off LAN printer must make entities unavailable **once** and keep them so; a refresh between cloud polls must not turn the failure into a success with stale data. | #38, 2.8.1 |
| B3 | One null, missing or unexpected field must never discard the rest of a report or the whole printer record. Parse each field on its own; a nested block with unknown keys must not fail the report. (Firmware 2.0.1.9 nulled `external_shelves` fields and every entity went unavailable; a finished job's nested `last_project` froze every LAN reading.) | #28, 2.6.0; library 0.4.2x–0.4.30 |
| B4 | A job status that is not a status (0, non-numeric) keeps the previous status and applies the rest of the report. | #38 (Kobra X), library |
| B5 | A reply that cannot be parsed is a fault in the integration — report it as such, never as bad credentials and never as "try LAN Mode". | #28 |
| B6 | An unclassified error during setup must be *not ready* (retried), never re-authentication — a spurious re-auth prompt stayed visible after the entry recovered. | 2.1.1 |
| B7 | Re-authentication must take effect: a new token must not be overwritten by stale stored tokens, and the entry must reload. | 2.1.1 |
| B8 | A printer that the cloud reports deleted (LAN Mode, code 1007) is *not ready*, not an authentication failure. | 1.x |
| B9 | `job_state` reads `idle` for an online printer with no job, not unavailable. | #35, 2.9.1 |
| B10 | The second ACE must get its own controls (retract, drying start/stop, presets, run-out refill, firmware) and its own model name from its own box info; stopping drying on the second ACE must name box 1 (a stop order without a box id went to box 0). | #33, #39, 2.8.0, library 0.4.31 |
| B11 | Drying defaults come from the material in the ACE **being dried**, not the first one. | #39 |
| B12 | A failed CMQTT connect attempt must be reported (with host and port) and must not block later attempts; the manual switch and refresh button must work when the link never came up. | 2.1.0-beta |
| B13 | `mqtt_connection_active` must not report on for a client that failed to connect. | library 0.4.24 |
| B14 | Print speed % and speed mode are read from the printer's own reports, falling back to the job — a LAN printer has no cloud job. Same for the part fan: never show the sliced job's 0 % while the fan runs. | #19 |
| B15 | The ACE loaded slot is the 1-based number printed on the box, and no value (not −1) when nothing is loaded; fall back to the slot whose status is 5 when the box field reads −1. | 2.3.0 |
| B16 | An empty ACE slot (`edit_status` 2) reads empty, even though the ACE still reports the last material. | #3, 1.4.3 |
| B17 | A single-material job is charged to the slot that fed it, not to `paint_index` 0. | 1.x |
| B18 | The forecast measures the rate between two observations, never total ÷ progress. | 1.x |
| B19 | The run-out problem sensor is unavailable when it does not know — never "off" (= no problem). | 1.x |
| B20 | The light entity survives restarts (remembered capability); the capability poll budget is not spent while the printer is off and is restored when it comes back. | #18; 2.0.0-beta.6 (memory), 2.1.2 (budget) |
| B21 | The light and light query must not require a print job. | library 0.4.17 |
| B22 | Temperature and fan controls work on an idle printer (orders 1216/1221), not only while printing. | 2.x |
| B23 | The image entity is unavailable with no job, rather than serving an error that dashboards draw as a broken image. | 2.3.0 |
| B24 | Camera stills come from the running stream, not a second connection to the printer. | #20 |
| B25 | Kobra X camera: tolerate HTTP 206 on the stream. | PR #27, 2.7.0 |
| B26 | Two printers set up at the same time must not fail on the shared panel registration; unloading one entry must not remove the panel for the others; a failing entry still serves the card. | #24, 2.1.x |
| B27 | One entry per Anycubic account (duplicate setup aborts); a cloud-configured printer is not re-offered by DHCP. | 2.x (DHCP part 2.1.1) |
| B28 | A pasted token is cleaned of quotes, wrappers and surrounding config text; an expired or damaged token is named as such before the server sees it; over-long signatures are repaired; an unreachable **or empty** key set never blocks login. | #8, #13 |
| B29 | A web token mistaken for a slicer token is retried as a web token. | #7, 1.4.2 |
| B30 | Each entry keeps its own token store (two accounts must not overwrite each other). | 2.x |
| B31 | The region must be chosen explicitly and pre-filled on re-auth; an absent or unknown stored region means international. China's MQTT broker certificate does not name its host: verify against the pinned Anycubic CA without a host-name check there only. | #13; library 0.4.23–0.4.24 |
| B32 | Unique ids must be identical whichever transport built the printer: the LAN MAC is normalised to the cloud's upper-case, hyphen form. | 1.3.1 |
| B33 | The LAN camera URL is used only while the LAN link is up; no URL that opens and immediately dies. | 2.x |
| B34 | `external_shelves` sent all-null means **no holder**, not an empty one. | 2.6.1 |
| B35 | A printer fault code is kept and exposed rather than consumed and dropped, and it is recorded even when the message carrying it is not understood. | #21 |
| B36 | Anything the printer sends that this version does not know is logged quietly (debug), not as an error. | 2.x |
| B37 | An entry whose printer is in neither source (e.g. just switched out of LAN Mode) retries rather than failing terminally. | 2.x |
| B38 | Sending an order locally when LAN is up must be decided at send time, every time — not handed over once at setup (the API client and the LAN link are built in either order). | 2.0.0-beta.8 |
| B39 | A cloud outage is logged once going in and once coming out. | 2.x |

---

## 7. 2.x gaps and quirks found while writing this (decisions for 3.0)

Not fixed in 2.x. Each states what 2.x does and what 3.0 should do.

| # | 2.x behaviour | 3.0 requirement |
|---|---|---|
| G1 | The filament ledger (reel changes, feeding slot, job charging, totals, nozzle, history) only updates inside a cloud poll, which never runs on a LAN connection — on LAN filament remaining never goes down. Also, on LAN the job is cleared the moment the printer goes idle, so there is nothing left to charge. | Run the ledger on every refresh on both transports. On LAN, charge a job when it ends (complete, cancelled, or the job block disappears) using the last extruded length and feeding slot seen while it ran. |
| G2 | A LAN link that drops is left to the MQTT library's own reconnect with the **old** credentials; the handshake is only repeated if the client was never created. | On any LAN disconnect, re-run the full handshake before reconnecting (LAN §10). |
| G3 | Cloud-only entries flap during a cloud outage: the failed poll makes non-sensor entities unavailable, the refreshes in between report success with stale data. | Apply §5.5 to every entry kind. |
| G4 | Sensors decide their availability only from "has a value"; they ignore a failed refresh, so they keep showing stale values while every other platform goes unavailable (to verify on a live outage). | All platforms unavailable while the source is lost. |
| G5 | Reconfigure → *Connection* works in tests only because the tests pre-set the entry; in a real reconfigure flow the entry is not loaded at that step and it aborts `reconfigure_successful` without changing anything (to verify). | The connection step must act on the entry being reconfigured. |
| G6 | After a restart the light is available from memory but its command uses light type 1 until the printer reports its real type (Kobra S1 is 2). | Use the remembered type. |
| G7 | `last_error_code`/`last_error` never clear. `anycubic-lan` clears a kind's error on the next OK code of the same kind (its QUESTIONS Q4). | Decide one rule (§9, V10). Keep the 2.x "sticky" rule unless decided otherwise. |
| G8 | *Home all* on LAN always waits the full 45 s: the wait re-reads the printer from the cloud, fails, and skips the idle check. | Wait on the pushed axis/move state. |
| G9 | Over the cloud, CMQTT print reports for a job the job list does not yet know are discarded until the next HTTP poll (≤ 60 s). | Acceptable; or adopt the new task id immediately. |
| G10 | Update entities show the text `None` as installed version when firmware is unknown (always on LAN), and `None` as latest version when the cloud gives no target — which can read as "update available". | Report no version (unknown) instead; on LAN use the firmware version from `info.version` (LAN §6.1) for the printer. |
| G11 | `print_time_total_hrs` (a total-increasing statistic) reads **0** on LAN because the text is missing; switching to LAN looks like a meter reset. | No value when the text is absent. |
| G12 | An empty local, USB or cloud file list reads as "not fetched" (unavailable) instead of 0 files. | 0 when the printer answered with an empty list; no value only until first fetched. |
| G13 | On LAN `job_name` includes the folder (`.3mf_temp/…`), and the job-history key then keeps the timestamp prefix. | Strip directories and the extension (LAN §6.2); history keys then match the cloud's. |
| G14 | A printer whose material type is unknown at first load permanently loses all `fdm` or `lcd` entities (they are dropped, not kept pending). | Keep them pending until the material type is known. |
| G15 | `external_spool_loaded` reads **off** when there is no holder at all. | Unavailable when the holder is absent (as the material sensor). |
| G16 | Deleting local/USB files and setting ACE slots do not wake CMQTT, so the follow-up list request may go unanswered in *Printing only* mode while idle. | Wake CMQTT for every cloud order whose result arrives over CMQTT. |
| G17 | The event's `device_id` is remembered on the action handler between calls, so a later call by `printer_id` reports the previous call's device. | Report the device of the printer this call targeted. |
| G18 | `cloud_camera` is available on LAN-only entries (the printer says it has a camera) although opening it needs the cloud. | Unavailable without a cloud account. |
| G19 | *Drying Stop* on the first ACE stops **every** ACE. | Keep (users may rely on it) or stop box 0 only — decide (§9, V11). |
| G20 | `job_cost` and `last_job_cost` are monetary sensors with the *measurement* state class, which Home Assistant does not accept for monetary sensors (to verify against the registry). | No state class on those two; keep `total` on `filament_cost_total`. |
| G21 | LAN-only entries cannot configure drying presets (the drying menu needs a cloud login) and the reconfigure *printer* step fails with `cannot_read_response`. | Offer drying presets whenever the printer has an ACE; hide *printer*/*reauth* for LAN-only entries. |
| G22 | `job_eta` jitters by seconds each refresh (now + remaining minutes). | Optional: round to the minute. |
| G23 | At setup, a cloud error fetching the **second or later** printer of a cloud entry (LAN off) is a terminal error; only the first printer's is retried. | *Not ready* (retried) for every printer. |
| G24 | A DHCP or `local`-step address update writes `lan_host` into the entry's **data**, but the LAN connection reads the address from the **options**, so a printer that changed address keeps being looked for at the old one. | Update the address the connection actually uses. |

---

## 8. Corrections made to COMPAT.md

Made in the same commit as this document:

1. §1 `region` values are `international` and `china` (not `global`); an
   absent value means international.
2. §1 data table: LAN-only entries carry `lan_host` in `data` too.
3. §4: `config_entry` is **required**, plus one of `device_id` / `printer_id`;
   the field detail is in §4 here.
4. §5: the event data also carries `printer_id`, `printer_name`, `device_id`.
5. §7: C2 and C3 marked answered.

Not changed in COMPAT but to note:

- COMPAT §3.1's "Enabled by default" column reflects the live install, where
  the owner enabled some entities. The 2.x **code defaults** are *disabled*
  for: `axis_position_x/y/z`, `external_spool_material`,
  `external_spool_loaded`, all `ace_slot_N_filament_remaining` and
  `_percent`, `job_filament_runs_out_at`, `last_job_filament`,
  `nozzle_filament_total`, `spool_inventory_count`, `reset_nozzle_wear`,
  `request_axis_position`, all `ace_slot_N_feed`, all
  `ace_slot_N_reset_spool`, all `ace_slot_N_spool_weight` and
  `ace_slot_N_spool_price`. Everything else is enabled. New installs should
  follow the code defaults (§9, V12).
- Units and device classes the 2.x code sets that COMPAT's table leaves blank:
  `ace_slot_N_filament_remaining` grams / weight; `_percent` %;
  `ace_slot_N_spool_weight` grams / weight; `ace_slot_N_spool_price` HA
  currency; temperature sensors *temperature*; `job_on/off/bottom_time`,
  `job_time_elapsed`, `job_time_remaining` *duration*; `job_z_thick`,
  `fan_speed_pct`, `print_speed_pct`, `box_fan_level`,
  `dry_status_total_duration`, `dry_status_remaining_time` deliberately **no
  unit** (keep, so long-term statistics are not broken) (§9, V12).

---

## 9. Items to verify

| # | Item |
|---|---|
| V1 | Unit of the printer's extruded length (`supplies_usage`). 2.x treats it as **millimetres** on both transports, and its conversion matches cloud figures (31 783 → ≈ 95 g of PLA against a 94.5 g slice estimate). `anycubic-lan` PROTOCOL §6.2 says "grams on the S1" for the LAN value. Confirm on a LAN print before 3.0 converts it. |
| V2 | Whether a multi-colour cloud job's `paint_index` equals the ACE slot index. 2.x assumes so when splitting a job between slots. |
| V3 | Whether charging the account's already-finished latest job on the first run after installation is wanted. |
| V4 | What `box_fan_level` physically is — the ACE's fan (2.x puts it on the ACE device) or the enclosure fan (`anycubic-lan` PROTOCOL §6.1). Keep the key and device either way. |
| V5 | Units of the resin `job_z_up_speed` / `job_z_down_speed` and of the resin action times (assumed seconds). |
| V6 | Which file types the print-and-upload actions accept: the schema accepts `.gcode` only, the action description lists `.gcode,.pwsp,.pwsq,.zip`; the no-cloud-save path requires `.gcode`. |
| V7 | **A cloud protocol facts document does not exist yet.** The implementation team cannot build the cloud transport (HTTP endpoints and request signing, login and token exchange, CMQTT broker, client id and login derivation, TLS client certificate and CA, topics, order payloads, cloud upload) from this document or from `anycubic-lan`. Also: the licence of Anycubic's MQTT client certificate and CA that 2.x ships. |
| V8 | The Agora (cloud camera) signalling is not specified here. 2.x's client is adapted from an MIT project (`Jezza34000/homeassistant_petkit`); whether the implementation team may read that project must be added to CLEAN-ROOM.md, or the signalling specified. |
| V9 | Whether the legacy `auth_mode_*` steps are reachable in any real flow (they appear unreachable in 2.x) and must be kept only for their translation keys. |
| V10 | The clearing rule for `last_error_code` / `last_error` (G7). |
| V11 | Whether *Drying Stop* on the first ACE should keep stopping every ACE (G19). |
| V12 | COMPAT §3.1's units/device-class and enabled-by-default columns versus the 2.x code (§8): confirm from the live registry (`original_unit_of_measurement`, `original_device_class`, `disabled_by`) before the implementation relies on either. |
| V13 | Sensor availability during a live outage in 2.x (G4). |
| V14 | Reconfigure → *Connection* in a real flow (G5). |
| V15 | The LAN camera start message (`video` / `startCapture`) is not in `anycubic-lan` PROTOCOL.md; it should be added there. |
| V16 | Entity icons (`icons.json`, 85 entries in 2.x) are not specified anywhere yet. |
| V17 | What the cloud's firmware `target_version` holds when no update is available (null, or the current version) — decides G10. |
