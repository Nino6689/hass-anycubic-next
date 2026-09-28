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
