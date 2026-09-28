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
