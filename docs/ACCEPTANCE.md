# Acceptance reports

Functional results from the specification team's tests of the 3.0 builds —
observed behaviour against expected, never code. The implementation team
fixes what is listed under **To fix**, and marks each item `**Fixed in <sha>.**`.

## Upgrade test U — 2026-09-28, build `clean/lan-integration` @ `5c0b6f8`

**Method.** A scratch Home Assistant 2026.9.3 was seeded with a copy of a
real 2.x install's storage — the config entry (a cloud account with LAN Mode
on, `lan_host` in `options`), its 132 registry entities (3 disabled by the
integration), its two devices (Kobra S1 and one ACE Pro), the filament and
capability stores and the restore-state records. The 3.0 build was dropped
in over it and run for 75 s against the real printer over LAN. Every
entity's state was compared with the live 2.x install reading the same
printer at the same moment.

**Passed.**

- The config entry loads on LAN. Its `data`, `options` and version are left untouched.
- All 132 unique ids re-attach, and no entity id changes. 3.0 creates no new entities.
- Both device identifiers are kept (`<user id>-<printer id>` and `…-ace0`). So are the device names, models and firmware version.
- Of the entities provided on LAN, 97 match 2.x exactly in value and unit. All differences are listed below.
- 16 entities are not provided, all of them cloud-only as BEHAVIOUR.md says: MQTT connection entities, file lists and their buttons, the cloud camera, job preview, Z thickness, lifetime totals and ACE firmware.
- The 3 entities disabled in 2.x stay disabled.
- Filament ledger: no job is charged again, and totals, slots and job records are unchanged. One reel's memory
  (`spools["PLA|#5B618F|HPL17-106"]`) moved from 156.7 g to 156.89 g, the
  value its loaded slot already held. 2.x had let the two drift apart, and
  3.0 re-syncs them. **Accepted.**
- `external_spool_loaded` is unavailable where 2.x says `off`. The printer has no
  external holder, so this is BEHAVIOUR G15's specified fix. **Accepted.**

**To fix.**

| # | Observed | Expected |
|---|---|---|
| U1 | `job_current_layer`, `job_total_layers` (and `job_bottom_layers`) have the unit `layers`. | `Layers`. COMPAT.md named a constant instead of giving the text; it now gives the literal string. |
| U2 | `number` states read `360`, `45`, `0`. | `360.0`, `45.0`, `0.0`: float values, as 2.x reported (COMPAT §3 "State formats"). Covers drying duration and temperature, fan speeds, box fan level and every other number. |
| U3 | At setup Home Assistant 2026.9 logs: *Detected that custom integration 'anycubic_cloud' calls `device_registry.async_get_or_create` with a deprecated `via_device` parameter; use `via_device_id` instead* (`entity.py`, line 151). | No deprecation warnings. |
| U4 | At shutdown Home Assistant logs: *Task … name='anycubic_cloud push <title> anycubic_cloud <entry id>' coro=AnycubicCoordinator._async_push_listeners() … was still running after final writes shutdown stage; Integrations should cancel non-critical tasks when receiving the stop event*. | The push task ends cleanly on unload and on Home Assistant stop. |

U1: **Fixed in 894f7ed.**

U2: **Fixed in 4335f21.**

U3: **Fixed in 70049e6.**

U4: **Fixed in ebe11ea.**

### Re-run on `clean/lan-integration` @ `60d851a` (after round 2)

The method is unchanged. Everything under **Passed** above still holds. 104 provided entities now
match 2.x exactly (97 before). The request-file-list buttons now exist on LAN
and read unavailable, which is answer F3 applied as specified. **Accepted.**

- U1, U2 and U3 are still open. This build predates the report.
- U4 did not reproduce in this run: the push task ended before shutdown. Keep the fix anyway. The warning appears whenever a report is still being coalesced when Home Assistant stops.

### Commands on hardware, `60d851a`

These were run from the 3.0 build through Home Assistant against the real printer, with the live 2.x
install reading the same printer as a witness. Only harmless controls were used. Light off, then on; part fan to
20 %, then back to 0 %. Every call returned 200, and 3.0 and the 2.x witness both saw each change within 8 s. **Passed.**

### Attributes, `60d851a`

Every attribute of every entity was compared with live 2.x. These differences are **accepted**:

- `consumables_percent` and `icon_type` in the ACE slot lists are empty on LAN. LAN reports don't carry them, and 2.x showed a made-up `0`.
- `box_info.feed_status` is empty. The last report carried `null`; 2.x kept a stale feed result.
- `box_info.loaded_slot` reads 1. It now agrees with the `ace_loaded_slot` sensor, where 2.x's attribute said null while the sensor said 1.
- `current_status`: `job_download_progress` and `total_print_time_*` are empty on LAN. They come from the cloud; 2.x showed zeros.
- `job_speed_mode` `available_modes` is `[]` on LAN, as BEHAVIOUR states.
- `job_cost` and `last_job_cost` have no `measurement` state class, as COMPAT lists. Home Assistant rejects `measurement` for monetary sensors. Upgraders will see a one-off "no longer has a state class" note in the statistics tools. That goes in the release notes.
- `spool_inventory_remaining`: one reel reads 0.2 g lower. This is the reel-memory re-sync accepted above.

**To fix.**

| # | Observed | Expected |
|---|---|---|
| U5 | On LAN, the printer firmware update entity sets `latest_version` to the installed version, so it claims "up to date". | BEHAVIOUR G10: `installed_version` comes from LAN `info.version` (done), and `latest_version` stays **unknown** until the cloud supplies a target. Never copy the installed version into it. |

U5: **Fixed in 20aa31f.**

## Frontend with the integration — 2026-09-28, `clean/frontend` @ `6a8c382` + `clean/lan-integration` @ `60d851a`

**Method.** The Phase C bundles were built with `npm ci && npm run build` and
served through the integration's `www/` fallback. They were loaded in the scratch
Home Assistant over the 2.x snapshot and the live printer, and rendered in WebKit at 1440 px
and 390 px wide. The panel was opened at `/anycubic_cloud`, and the card on a
dashboard twice: once with the defaults, once with `alwaysShow`, `vertical`,
`round: false`, `use_24hr` and a custom `monitoredStats` list.

**Passed.**

- The panel registers as "Anycubic Cloud & LAN", and every tab loads. The Overview shows the
  printer illustration with the ACE's four spools in their real colours and slot 1 marked loaded. It also shows live state and
  temperatures, the machine and colour-box boxes, move controls and the
  "card ideas" examples.
- The card with default options is folded to its header while the printer is idle, which is the `alwaysShow: false` behaviour.
  With `alwaysShow` it shows the illustration and every requested stat, with live values.
- There were no console errors or page errors at either width.
- The phone layout keeps its width; the page tabs scroll.

**Notes.**

- The Overview's "Firmware update: Current" comes from U5 and will read unknown once U5 is fixed.
- The speed stat reads `2`: the mode code. On LAN, 2.x shows the same, because the names come from the cloud (BEHAVIOUR). **Accepted.**

## Round 3 re-test — 2026-09-28, `clean/lan-integration` @ `4939244` + `clean/frontend` @ `6a8c382`

The full run was repeated: the upgrade test over the 2.x snapshot, the hardware commands and the frontend screenshots.

- **U1–U5 are confirmed fixed on hardware.** The layer unit reads `Layers` and numbers read `45.0`.
  Home Assistant logs **no** warnings from the integration at setup, while running or at shutdown.
  The LAN firmware entity reads `unknown`, and the panel shows the installed version without claiming "Current".
- 110 entities provided on LAN now match 2.x exactly. Every remaining difference is one accepted above.
  The file-list buttons (F3), `external_spool_loaded` (G15), the firmware entity (G10) and the reel-memory re-sync.
- The config entry, all 132 ids, both devices and the ledger are intact. The commands and the frontend pass as before.

**Result: Phase B (LAN) and Phase C (frontend) are accepted.**

## After merging B and C — 2026-09-28, `main` @ `6a353fe`

| # | Observed | Expected |
|---|---|---|
| M1 | The Tests workflow's `ruff check .` now also covers `frontend/python/tests/test_package.py`, and fails there with 12 errors: I001 (import order) and PT009 (unittest-style `assertEqual`/`assertTrue`). Mypy, both pytest jobs and the Frontend workflow pass. | `main` is green. Bring `frontend/python/tests` in line with the repository's ruff rules. Don't exclude it. |

M1: **Fixed in dee3e61.**

## Cloud half — 2026-09-28, `clean/cloud` @ `a60314f` (PR #4) with `anycubic-cloud-client` v0.1.0

**Method.** The upgrade test over a fresh snapshot of the live 2.x install, with the printer now on the cloud (LAN Mode off). It was run twice:
the entry as it is, with its LAN option on (hybrid, where LAN is unreachable and the entry falls back to the cloud), and with the LAN option off (pure cloud). The
test HA reused the live install's saved tokens, so no second token exchange was needed. The run also included a fresh cloud setup through the real
config flow in an empty Home Assistant, the hardware commands, and the panel and card in WebKit.

**Passed.**

- Both variants: the entry loads, and its data, options and version are untouched. All 132 unique ids re-attach with no id changes and no new entities.
  **All 132 are provided**, cloud-only ones included (the file lists, the MQTT entities, the cloud camera, the job preview, the lifetime totals and ACE firmware).
- **127 of 129 compared entities match live 2.x exactly in value and unit.** The two differences are `job_preview`, where 3.0 has the image
  and 2.x reads `unknown` (accepted, an improvement), and X1 below. Attributes are identical apart from differences already accepted: `loaded_slot`,
  `job_download_progress` empty while idle, and the monetary `state_class`.
- Devices are kept. On the cloud the ACE device also gains its firmware version (`1.3.863`), where 2.x left it blank.
- Hardware commands over the cloud: the light and the part fan are both reported back.
- **A fresh cloud setup through the config flow**: menu → token (signs in within 1.2 s) → printer (lists the Kobra S1) → entry. The entry has
  2.x's data keys, unique id = user id, mode 3, and a token store and ledger are written. All 132 entity keys are registered, and the log is free of warnings.
- The panel with cloud data shows the last job at 100 % with its preview image, "Done at Sat 21:32" (F6), and firmware and colour-box updates as "Current".
- The Home Assistant log has no warnings from the integration.

**To fix.**

| # | Observed | Expected |
|---|---|---|
| X1 | `job_filament_used` reads `65.0`. | `65`, the whole number of millimetres, as 2.x reports it (COMPAT §3 'State formats'). |
| X2 | Over the cloud every ACE reel in the card and panel art is drawn **empty**. `consumables_percent` is 0 for every slot, as BEHAVIOUR says it always is. | Fill each reel from the slot's `ace_slot_N_filament_remaining_percent` (`secondary_…` for ACE 2). Unknown = full. Never use `consumables_percent` (FRONTEND.md corrected; DECISIONS 'Reel fill'). |
| X3 | The cloud camera doesn't stream. HA shows *"Could not open the Anycubic cloud camera: The camera channel is encrypted: pass the Agora SDK public key"*. | This is fixed in the library (its ACCEPTANCE L3: the key becomes its default). Once the library is updated, the integration needs no key handling of its own. Re-test the stream after that. |

X1: **Fixed in 30bd535.**

X2: **Fixed in 4058653.**

### Final re-test — 2026-09-28, `clean/cloud` @ `3ed37dd` with `anycubic-cloud-client` `main` @ `ea1b7e1`

- **X1 confirmed.** `job_filament_used` matches 2.x (`65`). 128 of 129 compared entities now match live 2.x exactly. The only
  difference left is `job_preview`, where 3.0 shows the image (accepted).
- **X2 confirmed.** The ACE reels in the art show the slot colours and are sized by the ledger's remaining percentages (84 %, 72 %,
  91 %, 100 %). The printed part on the bed is drawn in the loaded colour.
- **X3 confirmed.** The cloud camera streams live through Home Assistant's WebRTC, on desktop and phone.
- Hardware commands over the cloud (light, part fan) are reported back. The log has no warnings from the integration. The live 2.x
  install stayed healthy throughout.
- Similarity is unchanged (the data tables and import blocks). The secret scan found no hits in 63 files.

**Result: Phase E2 (cloud half) accepted. `anycubic_cloud` 3.0 works over the cloud and over LAN.**

## Beta 2 — field reports from 2.x users, 2026-10-13 (D1–D8)

**Source.** Reports from users on other printers (Kobra X, Kobra 4, Kobra S1 with two ACE Pro units), confirmed where possible on the
development S1. They are stated as what the printer sends and what a user should see. Each one is an acceptance check for 3.0.0-beta.2:
if 3.0 already behaves as expected, add a test that shows it and say so under the item.

### D1. ACE Pro drying limit
- An ACE with `model_id` **40001** (ACE Pro) refuses a dry cycle above **55 °C**, with code **11505** ("The drying request did not enter the target temperature"). Seen on a user's two units; the development S1's ACE Pro reports 40001 too.
- Expected: a drying start on a 40001 unit never asks for more than 55 °C. This covers a material default (e.g. PETG at 65 °C), a value the user set and a preset. The number entity's state reflects the cap. Other model ids are sent what was asked.

**Fixed in hass-anycubic-next@18f855d.** Tests `test_beta2.py::test_d1_*`.

### D2. A refused drying start is visible
- On refusal the printer answers the `setDry` order with a non-success reply carrying a fault code (11505 in the case above), either on the envelope or inside `data`.
- Expected: a WARNING log line naming the code and its description, and the code reaches the last-error sensors. The button must not look as if it worked.

**Fixed in anycubic-lan@533233f, anycubic-cloud-client@b0dabff and hass-anycubic-next@18f855d.** Tests `test_beta2.py::test_d2_*`.

### D3. Second ACE after restart
- After an HA restart, the second ACE's entities on an S1 with 2× ACE Pro stayed unavailable until "Refresh ACE Spools" was pressed.
- Expected: once a push connection (cloud MQTT or LAN) is up, the integration sends the same box-report request as that button, once per connection. It does not open a connection just to send it.

**Already holds over LAN — test `anycubic-lan` `test_client.py::test_box_report_requested_once_per_connection` (anycubic-lan@898ad70).** **Fixed over the cloud MQTT in hass-anycubic-next@18f855d.** Tests `test_beta2.py::test_d3_*`; `test_d3_never_opens_or_holds_the_cloud_link` shows the request neither opens nor holds the link.

### D4. Active channel on the Kobra X
- A Kobra X (machine type 20030) reports filament changes as `print` / `update` / `updated` messages whose data is just `{"channel_no": N, "settings": {"light": 0}}`. It stops updating the ACE's own `loaded_slot` after the first few changes of a print.
- `channel_no` counts from **1** across every box in order. Observed values were 3 and 4 on a 4-slot Kobra X. The base is inferred and has not yet been confirmed against the printer's screen.
- Expected: the loaded-slot sensor follows `channel_no`.

**Fixed in anycubic-lan@533233f, anycubic-cloud-client@b0dabff and hass-anycubic-next@18f855d.** The numbering is `model.ace_slot_for_channel`, marked as an assumption. Tests `test_beta2.py::test_d4_*`.

### D5. Progress-only print updates
- The Kobra X sends `print` / `update` / `updated` with `curr_layer, file_root_path, filename, filetype, print_time, progress, remain_time, settings.light, supplies_usage, total_layers` and **no task id**.
- The S1 adds `display_filename, origin3mf, source_info, temp_gcode`.
- Expected: progress fields apply to the current job, and none of these fields produce a warning-level log line.

**Fixed in anycubic-lan@533233f and anycubic-cloud-client@b0dabff** (no warning was logged before either). Tests `test_beta2.py::test_d5_*`.

### D6. LAN print speed presets
- Over LAN the printer sends no speed-preset list, so the speed select was unavailable through every LAN print. The printer accepts the change locally.
- Codes observed on S1 and Kobra 4: 1 Silent, 2 Standard, 3 Sport.
- Expected: when no list is reported, the select offers those three, and a list the printer does send wins.

**Fixed in hass-anycubic-next@18f855d.** Tests `test_beta2.py::test_d6_*`.

### D7. Kobra 4 camera
- The Kobra 4 (machine type **20028**) FLV endpoint on port 18088 answers `206 Partial Content` like the Kobra X, so go2rtc refuses it.
- Expected: same handling as the Kobra X.

**Fixed in hass-anycubic-next@3b475f3.** Tests `test_camera.py::test_kobra_x_relay[20028]`, `test_beta2.py::test_d7_kobra_4_stream_is_relayed`.


### D8. A finished LAN job reads finished
- Over LAN, when a print ends the printer stops reporting the job (`project` goes null), and job state went straight to `idle`. Over the cloud it reads `finished` until the next job, because the account keeps the last job.
- The printer's info report still carries the ended job in `last_project`, with `state` (`finished`, or `stoped` for a cancelled one), `task_id` and `filename`.
- Expected: over LAN, job state reads `finished` (or `cancelled`) after a job ends, until the next job starts, matching the cloud. `idle` is for a printer that hasn't run a job since setup.

**Fixed in hass-anycubic-next@18f855d.** Tests `test_beta2.py::test_d8_*`. A cancelled LAN job reads `cancelled` as stated here; the cloud's status 3 still reads `failed` (BEHAVIOUR §1.3), unchanged.

### Beta 2 acceptance — 2026-10-13, `clean/beta2` @ `60e7101` with `anycubic-lan` @ `bd516c7` and `anycubic-cloud-client` @ `4cdc23d`

**Method.** The upgrade test over a fresh snapshot of the live install (now 3.0.0b1), against the real Kobra S1 on the cloud (LAN Mode off),
with `--actuate`. Similarity against the excluded trees for all three PRs, and the secret scan.

- The entry loads. Its data, options and version are untouched. All 132 unique ids re-attach, with no id changes and no new entities. Devices are kept.
- **128 of 129 compared entities match live exactly in value and unit.** The one difference is `job_preview`'s timestamp (the same image, fetched later).
- The filament ledger is identical. The light (off/on) and the part fan (20 %, then 0) are reported back over the cloud. There are no warnings from the integration.
- Similarity is unchanged from the last checks: integration 40/12/7 (the data tables and import blocks), cloud client 25/23 (Agora join fields and function-id
  names, as before), `anycubic-lan` 6. The secret scan found 0 hits in 148 files.
- **Not verifiable on the development machine:** D3 for a second unit (one ACE here), D4's numbering (no Kobra X), D7 (no Kobra 4),
  and D1/D2 against the ACE itself (not started a real dry cycle). These rest on their tests until users confirm them.

**Result: Beta 2 accepted.** The libraries were released as `anycubic-lan` 0.1.1 and `anycubic-cloud-client` 0.1.1, and are pinned here.

## Beta 3 — field reports, 2026-10-15 to 2026-10-19 (D9–D20)

**Source.** Reports from users on a Kobra X with and without an ACE 2 Pro, and a Kobra 4 with an ACE 2 Pro in LAN Mode (some of it observed on
3.0.0-beta.2 itself), confirmed where possible on the development S1. They are stated as what the printer sends and what a user should see,
and are the acceptance checks for 3.0.0-beta.3. If 3.0 already behaves as expected, add a test that shows it and say so under the item.

**D9 (diagnostics carry a sign-in token) and D16 (a Kobra 4 charges no LAN print) block the beta.** D17 is wanted but not blocking: if it
doesn't fit safely, say so under it and leave it for a later beta.

### D9. Diagnostics must carry no credential or personal data 🔴
- Confirmed on the live 3.0.0b2 install: the diagnostics download's `cloud.account` block contains **`casdoor_user_token`**. That's a JWT sign-in token for the Anycubic account. Its claims include `email`, `phone`, `id`, `scope` and `exp`, and the one checked had more than two months left. The same block also contains **`tourist_device_id`**.
- The account record also carries `user_activation_key` and `user_url`. A real 2.x download showed that cloud printer and project records carry: the printer serial, hex-encoded, as `description`; every print's file name (`name`, `task_name`, `filename`, `display_filename`, `gcode_name`, `temp_gcode`); and its image (`img`, `image_id`).
- Expected:
  - None of those values appear in a download.
  - A credential added later under a new key mustn't leak either. Any key containing `token`, `secret` or `password`, and any string shaped like a JWT (three base64url segments starting `eyJ`), is redacted wherever it appears.
  - Empty or null values may stay visible.
  - Print history may remain without names or images, because status is what bugs are debugged from.
  - A printer id appears as the same placeholder in every block.
- Test with fixtures carrying each field above. Assert the raw values are absent from `json.dumps` of the download.

**Fixed in hass-anycubic-next@ca9a82f.** Diagnostics use the rules in `redact.py` (shared with D14). Each printer id reads as
`printer_1`, … in every block; the job history keeps its figures under numbered keys. Tests `test_beta3.py::test_d9_*`.

### D10. Filament-change steps, counted per box (corrects D4)
- During a multi-colour print, a Kobra X (20030) with an ACE 2 Pro sends `print` messages with `action: start`, `code: 200`, and these states:
  - `extfilbox_filament_feeding`, `extfilbox_filament_unfeeding`: data `{"channel_no": N, "taskid": …}`. **No `unit_no`.** This is the printer's own feeder.
  - `ace_filament_feeding`: data `{"channel_no": N, "taskid": …, "unit_no": 1}`. This is the ACE.
  - `nozzle_purging`: data `{"channel_no": N, "taskid": …}`.
- Observed sequence in one print: own feeder 1 → 1 → 2, then ACE unit 1 channel 1, then ACE unit 1 channel 2.
- **`channel_no` counts from 1 within its box, not across boxes.** D4's "across every box in order" was wrong.
- Not yet known: which entry in the box list is the Kobra X's own feeder when an ACE is fitted, and whether `unit_no` 1 means list index 0 or 1. The ACE 2 Pro's drying report names box `id: 0`. Without an ACE, the Kobra X's own feeder is the only box (#34).
- Expected:
  - A feed with one box sets that box's loaded slot to `channel_no − 1`.
  - On a printer whose boxes are all ACEs (e.g. an S1 with two), `unit_no` U selects ACE U.
  - On a Kobra X with an ACE, the loaded slot isn't changed until the mapping is confirmed. A wrong slot is worse than a stale one.
  - Purge and unfeed steps change nothing and log nothing above debug.

**Fixed in anycubic-lan@375bdaa, anycubic-cloud-client@fb63060 and hass-anycubic-next@e391fc2.** The libraries parse the steps
(`FilamentFeed` / `PrintUpdate.filament_step`, `unit_no`); purge and unfeed steps change nothing and are never job states. The box
mapping is in one place, `model.box_and_slot_for_feed`: one box takes any feed (`channel_no − 1`); on a Kobra X with an ACE (more than
one box, or an ACE has reported feeding) the loaded slot is left unchanged; otherwise `unit_no` U selects the U-th ACE. Beta 2's
numbering across boxes is gone. Tests `test_beta3.py::test_d10_*`, `anycubic-lan` `test_beta3.py`, `anycubic-cloud-client` `test_beta3.py`.

### D11. ACE 2 Pro drying report without a temperature
- The ACE 2 Pro's periodic `multiColorBox` / `autoUpdateDryStatus` / `success` report carries per box only `{"id": 0, "drying_status": {"duration": 14400, "humidity": 28, "remain_time": 162, "status": 1, "target_temp": 50}}`. There's **no `temp`**.
- Expected: drying state, humidity, target and remaining time update from it. The box temperature keeps its last reading and is never set to 0 or unknown because of this report. Nothing is logged above debug.

**Fixed in anycubic-lan@375bdaa and hass-anycubic-next@e391fc2.** The temperature already kept its reading (a partial box report is
merged field by field); the humidity inside `drying_status` was not read, and a box given as an object rather than a list was not
taken. Both are now. Tests `test_beta3.py::test_d11_*`, `anycubic-lan` `test_beta3.py::test_drying_report_without_temperature`.

### D12. A cloud refresh must not overwrite the slot the printer reported
- While the printer was printing from slot 4, the loaded-slot sensor changed to slot 2. No message from the printer arrived at that moment. The only event was the periodic cloud printer-info refresh. The cloud record's `multi_color_box[].loaded_slot` goes stale during a print. The Anycubic slicer shows the wrong slot too.
- Expected: once the printer has reported a loaded slot (by MQTT or LAN, through any of D4, D10 or D13), a cloud refresh doesn't change it. The printer's next report does. With no printer report, the cloud value is used. Other fields from the cloud refresh (temperatures, spools) still update.

**Fixed in hass-anycubic-next@e391fc2.** The slot the printer itself reported (a feed, or a box's own `loaded_slot` over LAN or the
cloud MQTT) is kept over a cloud refresh; the printer's next report changes it, and a repeat of a stale box value does not. Tests
`test_beta3.py::test_d12_*`.

### D13. The printer's own `current_filament` report
- The `extfilbox` report with `action: auto`, `state: done` carries `current_filament` as `"<box>-<slot>"`, both counted from 0. `"0-3"` was observed while the screen showed slot 4 and `channel_no` was 4. It reads `""` while the filament is retracted for leveling or wiping.
- Expected: on a printer with one box, the loaded slot follows it. An empty or malformed reading keeps the last slot. With several boxes, apply the same certainty rule as D10.

**Fixed in anycubic-lan@375bdaa, anycubic-cloud-client@fb63060 and hass-anycubic-next@e391fc2.** Over LAN the `auto` report also no
longer replaces the external holder. It goes through the same mapping as D10. Tests `test_beta3.py::test_d13_*`.

### D14. Logs must not carry printer identifiers
- A debug log of an MQTT message printed the raw payload. A `buried` / `PrintStart` report includes `cn_code`, and only the printer key in the topic was redacted.
- Expected: no log line at any level contains `cn_code`, serials, MAC or IP addresses, printer keys, or any value under a key containing `token`, `secret` or `password`. Use the same rules as D9.

**Fixed in hass-anycubic-next@ca9a82f and 5b3f5b8, and anycubic-lan@375bdaa.** `redact.py` holds the rules D9 uses; the LAN
message log, every log line that carries an error's text, and the coordinator's name use them, and the printer's address is no longer in
any log line (the `lan_unreachable` and `lan_connection_lost` messages no longer name it). The cloud MQTT log already held: it logs
kind/action/state and the redacted topic only (`anycubic-cloud-client` `test_beta3.py::test_message_log_has_no_identifiers`).
Tests `test_beta3.py::test_d14_*`.

### D15. Job numbers that arrive as text, and job `-1`
- During a LAN print a Kobra 4 sends the job number as **text**: `task_id: "-1"` in the info report's `project` block, and `taskid: "-1"` in the `print` report sent when the print starts. Every LAN print is `-1`.
- The `last_project` block (the one with a `localtask` field) carries the previous **cloud** job number, also as text (`"131189709"`).
- Expected:
  - A job number that arrives as text is read the same as a number, including a negative one.
  - `-1`, `0` and anything that isn't a whole number identify no job. Two jobs both numbered `-1` are never treated as the same job.

**Fixed in anycubic-lan@375bdaa** (text was read only as digits, so `"-1"` was no number). Text and numbers read the same; `Job.job_id`
names a job only above 0, and the job merge and the ledger use it. The cloud client already read text (`as_int`). Tests
`test_beta3.py::test_d15_*`, `anycubic-lan` `test_beta3.py::test_job_number_as_text_or_number`.

### D16. LAN prints are charged without relying on a job number 🔴
- Observed on beta.2: two identical short LAN prints from slot 4 (about 0.9 g, 309 mm "filament used" each). The spool didn't change, and neither job is in the history. The 309 mm was seen while printing. The charge was skipped only because the job had no number.
- Expected:
  - Every LAN print that Home Assistant watched running is charged to its spool once, when it finishes. That includes the same file printed twice in a row, whose finished record reads identically both times.
  - A print that finished before Home Assistant was watching (an upgrade or a restart) isn't charged.
  - A job is never charged twice, whether it's seen over LAN, over the cloud, or both. A Kobra S1 gives LAN prints a real job number that the cloud may later report.
  - Switching the printer from LAN Mode back to the cloud never charges a job again. Seen on 2.x: the cloud re-reported its newest job (a September print, charged at the time) as soon as the printer came back, and it was charged a second time.

**Fixed in hass-anycubic-next@e033dd3** (with D15). A run is followed per source and charged once when that source shows it over,
whatever its number; only numbered jobs touch `last_job_id`, and a number charged since setup is not charged again. Beta 2 stores load
unchanged (the stored shape is the same). Tests `test_beta3.py::test_d16_*`: two consecutive -1 prints, the same file twice, a print never
watched running, a beta.2 store, LAN to cloud and back, and a numbered job seen on both sources.

### D17. A restart mid-print shouldn't lose the print (wanted, not blocking)
- Today a print is charged once, at the end, and only if it was watched running. A Home Assistant restart mid-print loses the whole job.
- The reporter's own automation counts as the print runs: each time "filament used" rises, the new millimetres are converted to grams for the slot loaded at that moment. That survives restarts and handles multi-colour prints, and the spool goes down live.
- Expected, if adopted: charging is incremental and persisted, the total for a job matches what a charge at the end would give, and nothing is counted twice across a restart.

**Deferred — a LAN print numbered `-1` carries nothing that survives a restart and tells it apart from the next print of the same
file, so a persisted partial charge could be counted twice or lost; and a multi-colour cloud job's split is only known at its end.**
D16's charge at the end stands.

### D18. A "LAN Mode active" sensor
- In cloud mode the Kobra 4 closes all its LAN ports. Whether port 18910 answers tells the current mode reliably. The reporter uses that as a sensor today.
- Expected: a binary sensor that is on while the printer's LAN port answers and off when it's refused. It's never unavailable just because the printer is in cloud mode. Switching modes from Home Assistant isn't possible as far as anyone knows; the printer's messages point to its screen.

**Fixed in hass-anycubic-next@5b3f5b8.** `binary_sensor.<printer>_lan_mode_active` reads the outcome of the coordinator's own
connection attempts (the refresh already runs the handshake while not connected, G2): on once a handshake succeeds, off when the port
refuses (`PrinterUnreachableError`) or the printer answers in cloud mode (`LanModeDisabledError`). No other connection is opened. It exists
only for printers with a LAN Mode address and stays available while the printer is in cloud mode. Tests `test_beta3.py::test_d18_*`.

### D19. Firmware version in LAN Mode
- Observed on beta.2: printer and ACE firmware read `unknown` in LAN Mode. The LAN info report carries the printer's firmware as `version` (`"2.7.2.7"` on a Kobra S1).
- Expected: the printer firmware entity reads the LAN `version` while in LAN Mode. ACE firmware may stay unknown if nothing local reports it.
- Also observed and expected: the cloud camera and the file-list buttons are unavailable in LAN Mode.

**Already holds — test `test_beta3.py::test_d19_lan_firmware_and_cloud_only_entities`.** In LAN Mode the firmware entity's
`installed_version` is the LAN `version`; its state reads unknown because the latest version is unknown over LAN (U5). The cloud camera
and the local and USB file-list buttons are unavailable in LAN Mode.

### D20. The update coordinator is created with its config entry
- Core requires it, so it matters for the core `anycubic` integration too. Expected: every coordinator receives the config entry when it's built.

**Already holds — test `test_beta3.py::test_d20_coordinators_have_their_entry`.** The integration has one coordinator class,
built with `config_entry=` in every case.

### Beta 3 acceptance — 2026-10-19, `clean/beta3` @ `bf4c20f` with `anycubic-lan` @ `1f02367` and `anycubic-cloud-client` @ `dd26db4`

**Method.** The upgrade test over a fresh snapshot of the live install (now 3.0.0b2), against the real Kobra S1 on the cloud (LAN Mode off),
with `--actuate`. Similarity against the excluded trees for all three PRs, and the secret scan.

- The entry loads. Its data, options and version are untouched. All 132 unique ids re-attach, with no id changes. Devices are kept.
- **128 of 129 compared entities match live exactly in value and unit.** The one difference is `job_preview`'s timestamp (the same image, fetched later).
- One new entity, as D18 asks: `binary_sensor.anycubic_kobra_s1_lan_mode_active`, enabled. It reads `off` with the printer in cloud mode, not unavailable.
- 54 entities read unavailable or unknown at idle, the same as beta.2 (buttons without a press, and job values with no job).
- The filament ledger is identical. The light (off/on) and the part fan (20 %, then 0) are reported back over the cloud. The only warning in the log is
  Home Assistant's notice for any custom integration.
- Similarity is unchanged from beta.2: integration 40/12/7 (the error-code table, the density table and import blocks), cloud client 25/23
  (Agora join fields and function-id names), `anycubic-lan` 6. The secret scan found 0 hits in 110 files.
- **Not verifiable on the development machine:** D10, D12 and D13 (no Kobra X), D11 (no ACE 2 Pro), D15 and D16 with a printer that numbers
  LAN prints `-1` (Kobra 4), and D18 in LAN Mode. These rest on their tests until users confirm them.

**Result: Beta 3 accepted.** The libraries were released as `anycubic-lan` 0.1.2 and `anycubic-cloud-client` 0.1.2, and are pinned here.

### Beta 3 on hardware in LAN Mode — 2026-10-19, live install on 3.0.0b3

The development S1 was switched to LAN Mode with the live install running beta.3. One single-material print was started over LAN
(task `-1`) and ran to the end.

- **D18:** `lan_mode_active` went from `off` to `on` within a refresh, with no restart.
- **D19:** the printer firmware entity's installed version is `2.7.2.7` in LAN Mode; its state is unknown, as stated.
- **D8:** job state went `preheating` → `printing` → `finished`, and stayed `finished`.
- **D15/D16:** the job numbered `-1` was charged once to the slot that fed it, 724.2 → 721.2 g (3.0 g of PLA+). The printer reported
  951 mm, which is 2.84 g at PLA's density. "Last job filament" reads 3.0 g. Refreshes after the end charged nothing more.
- **Observed, not specified:** job progress and job filament used read unavailable once the job is `finished` (no running job). Over the
  cloud they keep the last job's values. Not a defect against D8; noted for a later round.
- **D8 (cancelled):** a LAN job stopped during preheating reads `cancelled`; it reported 0 mm and nothing was charged.
- **Observed, not specified:** "Last job filament" changed from 3.0 to 2.8 g when the printer dropped off the network for ~20 s and
  reconnected, with no new job. The spools did not change. The value should not be recomputed on reconnect; noted for a later round.

## Beta 4 — field reports, 2026-10-19 to 2026-10-20 (D21–D23)

**Source.** hass-anycubic #44, from a Kobra S1 Max owner with an ACE, with diagnostics, and the development Kobra S1's own history. 2.x
shipped these in 2.9.9, so they are compatibility facts as well as features: COMPAT.md has the new rows, and an update from 2.9.9 must find
the same unique ids on the same devices. If 3.0 already behaves as expected, add a test that shows it and say so under the item.

### D21. Chamber temperature, where the printer has a sensor
- A Kobra S1 Max reports a real chamber temperature in the printer's temperature data (`curr_chamber_temp`, 32 °C in the reporter's
  diagnostics), both in the cloud record and when asked locally. A Kobra S1 has no chamber sensor and reports `0` in the same field.
- Expected: a `chamber_temperature` sensor on the printer device, °C, device class temperature. It's created the first time the printer reports a
  non-zero value, and never on a printer that only ever reports `0` or nothing. `0` reads as "no reading", not as 0 °C.

**Fixed in anycubic-cloud-client@ac5f868 and hass-anycubic-next@38e703b.** LAN and cloud MQTT already read `curr_chamber_temp`
(anycubic-lan `test_tempature_merges_and_chamber_flag`); the cloud record's `parameter.curr_chamber_temp` was not read
(`PrinterDetail.chamber_temp`, test `test_chamber_temperature_from_the_record`), and there was no entity. Tests in `tests/test_beta4.py`:
`test_d21_lan_chamber_temperature_on_first_non_zero_reading`, `test_d21_lan_printer_reporting_nothing_gets_no_chamber_sensor`,
`test_d21_cloud_chamber_temperature_from_the_record_and_mqtt`, `test_d21_cloud_chamber_temperature_from_mqtt_first`.

### D22. ACE humidity, where the box has a sensor
- An ACE's own report carries `humidity`. Some boxes send real values (58–84 % have been seen); others send `0`. D11's ACE 2 Pro drying report
  carries it too.
- Expected: `ace_humidity` on the first ACE and `secondary_ace_humidity` on the second, %, device class humidity. As with D21, each is created on
  the first non-zero reading, and `0` means no sensor. 3.0 already shows humidity in the card's box data; this is the entity.

**Fixed in anycubic-lan@10fd1a0 and hass-anycubic-next@38e703b.** The cloud record already carried the box's `humidity`
(anycubic-cloud-client `test_ace_humidity_from_the_record`); the LAN parser, which also reads the cloud's pushed box reports, dropped it
(`AceBox.humidity`, tests `test_box_humidity_is_read`, `test_box_humidity_of_two_boxes_and_a_partial_report`), and there was no
entity. A non-zero drying-report humidity (D11) counts too and is preferred, as in the card's box data. Tests in `tests/test_beta4.py`:
`test_d22_lan_ace_humidity_on_first_non_zero_reading`, `test_d22_lan_drying_report_humidity_creates_the_sensor`,
`test_d22_cloud_ace_humidity`, `test_d22_cloud_record_humidity_at_setup`.

### D23. The box fan is the printer's enclosure fan
- On the development Kobra S1 on 2026-10-19, `box_fan_level` went to 60, then 80, during a print (08:10–08:18 UTC) while the ACE never dried. It
  is set through the same print-settings command as the part and auxiliary fans. It belongs to the printer, not the ACE.
- Expected: `box_fan_level` sits on the **printer** device, named "Chamber Fan Level". Its unique id doesn't change, so an existing entity keeps
  its entity id and only changes device. The `set_box_fan_level` number is named "Set chamber fan level". The sensor is created when the
  printer first reports the value, so a printer that never reports it gets no entity. A second ACE doesn't get a copy.

**Fixed in hass-anycubic-next@38e703b.** The sensor sat on the first ACE and was created with it. It is now on the printer, created once
`box_fan_level` is reported; a registry entry 2.x left on the ACE is moved to the printer device at setup, before any reading, with its
entity id unchanged. Tests in `tests/test_beta4.py`: `test_d23_chamber_fan_on_the_printer`, `test_d23_chamber_fan_created_when_first_reported`,
`test_d23_existing_box_fan_moves_to_the_printer`.
- Upgrade check: from a 2.9.9 install, `box_fan_level` re-attaches to the printer device and `chamber_temperature`/`ace_humidity` re-attach
  wherever 2.9.9 had created them.

**Fixed in hass-anycubic-next@38e703b — test `test_2x_cloud_entry_upgrade`** (`tests/test_cloud_upgrade.py`): every COMPAT §3.1 row,
the three new ones included, is seeded as 2.x stores it, with `box_fan_level` on the ACE device; after setup `box_fan_level` is on the
printer device under the same entity id, and `chamber_temperature` and `ace_humidity` are provided with values (the box fan waits for its
first report, which over the cloud only a pushed `fan` message carries).

### D24. A finished print is charged to the slot that fed it 🔴
- **Source.** hass-anycubic #40, 2026-10-21: beta.3 on a Kobra 4 + ACE 2 Pro in LAN Mode, four short single-material LAN prints from
  ACE slot 4 (PETG). Each was charged once, as D16 asks, but **three of the four went to slot 1**.
- Observed: at the end of a print the Kobra 4 retracts the filament and reports its idle loaded slot (slot 1) about 15 s **before** it
  reports `finished`. During those seconds the job still reads printing and "filament used" no longer rises. The one print charged
  correctly was the one where both reports arrived together. The reporter's own automation, which charges as the print runs to the slot
  loaded at that moment, got the right slot every time.
- Expected:
  - A finished print is charged to the slot that was feeding it **while filament was going through**. A slot reported after the last
    rise in "filament used" (the retract) doesn't decide where the print is charged.
  - Where a print without a per-filament breakdown fed from more than one slot, the slot that fed most of it is charged.
  - The slot loaded at the moment the print ends is only used for a print that Home Assistant didn't watch running.
  - What one print fed never decides where the next one is charged.
  - Holds for cloud jobs too, not only LAN jobs numbered `-1`.
- 2.x fixes the same fault in 2.9.10. The behaviour above is the whole requirement.

**Fixed in hass-anycubic-next@eee7378.** The ledger charged a single-material print to the slot loaded *when it ended*, and also stored
any slot seen while the job read printing, the retract included. Now each run books every rise in "filament used" to the slot loaded as
that rise is reported (the ledger runs on every report). The slot that fed the most is charged, so a slot reported after the last rise
decides nothing. The slot loaded at the end is used only when the run was never seen feeding. The remembered `feeding_slot` is dropped when
a run ends, so it can't carry to the next print. LAN and cloud runs are tracked the same way, including cloud jobs with a one-colour
breakdown. Tests in `tests/test_beta4.py`: `test_d24_kobra4_retract_before_finished` (retract before `finished`, and both together),
`test_d24_the_slot_that_fed_most`, `test_d24_slot_at_the_end_only_for_a_print_not_seen_feeding`, `test_d24_one_print_never_decides_the_next`,
`test_d24_lan_print_from_slot_4` (the field report: four LAN prints numbered `-1` from slot 4, each retracting to slot 1 first),
`test_d24_cloud_job`.

### Beta 3 in the field — Kobra 4 + ACE 2 Pro, LAN Mode (hass-anycubic #40, 2026-10-21)

- Updated from beta.2 through HACS: every entity came back with the same id and the spool data carried over. The one new entity is
  `lan_mode_active` (D18). The firmware reads `1.2.1.3` in the update entity's `installed_version` (D19).
- **D15/D16 hold on a printer that numbers LAN prints `-1`:** four LAN prints in a row, the same file twice among them, each charged once.
  The slot was wrong for three of them (D24).
- **LAN → cloud:** nothing was charged again over 9 minutes in cloud mode; the filament store was byte-for-byte unchanged (D16).
- **D18:** `lan_mode_active` went `off` about 5 s after the reporter's own port check and stayed off; the printer stayed online through the cloud.
- LAN printing facts from the same report (paged `listLocal`, plain `.gcode` storage, thumbnails) are in `anycubic-lan` PROTOCOL §7.3.

### D22 in the field — beta.3, Kobra 4 + ACE 2 Pro, LAN Mode (hass-anycubic #40, 2026-10-22)

- Observed on beta.2 and beta.3: the card's box humidity reads `0` in LAN Mode and real values (27–37 %) over the cloud. 2.9.7 showed real
  values in LAN Mode too. Over LAN this box sends its humidity on the box itself (`multi_color_box[].humidity`), not in `drying_status`.
- That is the box-level reading D22 asks for, so beta 4 covers it. The development S1's ACE Pro sends `humidity: 0` over LAN (no
  sensor), so the positive case rests on the D22 tests and on the reporter.
- **Decided 2026-10-22 (Nino): unknown, not 0 → D25 in Beta 5.** Was: the reporter asks for the card's box data to read *unknown* rather than `0` while no
  humidity has been reported. BEHAVIOUR.md documents `humidity` "reads 0 without a sensor", as in 2.x, so this would be a deliberate
  change to the card's data.

### Beta 4 acceptance — 2026-10-22, `clean/beta4` @ `db35c50` with `anycubic-lan` @ `5e0c097` and `anycubic-cloud-client` @ `75e5a62`

**Method.** The upgrade test over a fresh snapshot of the live install (3.0.0b3, 133 entities), on Home Assistant 2026.10.2, against the
real Kobra S1 **in LAN Mode** (beta 3 was accepted in cloud mode), with `--actuate`. Similarity against the excluded trees for all three
branches, including 2.9.10, which fixes D24 in 2.x. Secret scan.

- The entry loads. Its data, options and version are untouched. No entity id changed or went missing. Both devices are kept.
- **All 130 compared entities match live exactly in value and unit.** No new entity: the S1 has no chamber sensor (D21) and its ACE Pro
  reports humidity `0` (D22), so neither sensor is created, as specified.
- **D23:** `sensor.anycubic_kobra_s1_ace_box_fan_level` ("Chamber Fan Level") and `number.office_anycubic_kobra_s1_set_box_fan_level`
  ("Set chamber fan level") sit on the printer device with their entity ids unchanged.
- The light (off/on) and the part fan (20 %, then 0) are reported back over LAN, matching live. The filament ledger is identical. The only
  warning in the log is Home Assistant's notice for any custom integration.
- 61 entities read unavailable or unknown at idle, against 54 in beta 3's cloud-mode run. The difference is the cloud-only entities in LAN
  Mode (D19), and live beta.3 reads the same.
- Similarity is unchanged: integration 40/12/7 (the error-code table, the density table, import blocks), cloud client 25, `anycubic-lan` 6.
  D24's ledger shares nothing with 2.9.10. The secret scan found 0 hits in 66 files.
- **Not verifiable on the development machine:** D21 and D22 with real sensors, and D24 on a printer that retracts before `finished`. These
  rest on their tests until users confirm them.

**Result: Beta 4 accepted.** Merged: next #11, `anycubic-lan` #4, `anycubic-cloud-client` #5. Library releases and the beta are next.

## Beta 5 — decisions and field reports from 2026-10-22 (D25)

### D25. The ACE's humidity in `box_info` reads unknown, not 0, until there is a real reading
- **Source.** hass-anycubic #40 (Kobra 4 + ACE 2 Pro, LAN Mode): the `box_info` attribute's `humidity` read `0` while nothing had been
  reported. Automations that compare it with a threshold took the box for very dry. Nino decided (2026-10-22) that unknown is right, even
  though 2.x shows `0` there.
- Expected:
  - `box_info.humidity` is **`null`** until the box has reported a non-zero humidity (its own or in a drying report, as D11 and D22
    read them). A box without a sensor, which only ever sends `0`, stays `null`.
  - Once a real value has been reported it is shown, and later partial reports keep it, as they keep everything else in the box.
  - Applies to both ACEs, LAN and cloud alike.
  - The `ace_humidity` / `secondary_ace_humidity` sensors are unchanged (D22). Nothing else in `box_info` changes.
  - The card and panel don't show humidity today; whatever reads `box_info` must cope with `null`.
- This is a deliberate change from 2.x. It goes in the release notes, and COMPAT/BEHAVIOUR say so.

**Fixed in hass-anycubic-next@3ce0bc6.** `box_info.humidity` is now the same reading as the `ace_humidity` / `secondary_ace_humidity`
sensors (drying report, else the box's own) and `null` where they have none; the sensors and the other `box_info` keys are unchanged.
An explicit `0` after a real reading reads `null` again, as the sensor reads unavailable (D22). Integration only; the card and panel read
only `box_info.loaded_slot`, and diagnostics do not include it, so `frontend/` is unchanged. COMPAT lists only the attribute names, so
it needs no note. Tests in `tests/test_beta5.py`: `test_d25_lan_box_that_only_reports_0_reads_null`,
`test_d25_lan_real_reading_is_shown_and_kept_through_partial_reports`, `test_d25_lan_drying_report_reading_counts`,
`test_d25_lan_second_ace`, `test_d25_cloud_box_that_only_reports_0_reads_null`, `test_d25_cloud_real_reading_is_shown_and_kept`,
`test_d25_cloud_second_ace`.
