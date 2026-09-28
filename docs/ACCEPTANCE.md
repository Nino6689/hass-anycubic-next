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
