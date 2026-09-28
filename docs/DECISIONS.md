# Specification decisions — resolutions of open items

Decisions by the specification team, 2026-09-28, on the items marked
"to verify" in `BEHAVIOUR.md` §9 and `FRONTEND.md` §7. Where a decision
changes 2.x behaviour it is deliberate, and noted.

## Behaviour (`BEHAVIOUR.md`)

| Item | Decision |
|---|---|
| **V1** unit of the printer's used-filament figure (`supplies_usage`) | **Millimetres of filament extruded**, on both transports. Grams are computed from it with the density table (§3). `anycubic-lan`'s PROTOCOL.md said grams; that was a specification error and is corrected there. |
| **V2** does a multi-colour cloud job's colour index equal the ACE slot? | Cloud phase (D). Until then: no — treat it as an index into the job's own material list, and use the slot the printer reports as feeding for single-material jobs. |
| **V3** charge the account's latest finished job on first install? | **No.** Filament and cost accounting start from the first job that finishes after setup. |
| **V4** `box_fan_level` | Keep the 2.x entity, key and device placement unchanged (compatibility). It reports the printer's box fan level. |
| **V5** resin units | Keep the 2.x units and ranges (seconds for the time fields, as 2.x presents them). Resin support is cloud phase (D). |
| **V6** print-and-upload file types | Cloud phase (D). |
| **V7** cloud protocol and Anycubic's MQTT certificate | Cloud phase (D): a `CLOUD-PROTOCOL.md` spec follows after Anycubic replies to the developer-portal request, or on 2026-10-12 if they have not. The certificate and key are Anycubic's data, shipped as a separate resource, never in core. |
| **V8** cloud camera signalling | The implementation team **may read `Jezza34000/homeassistant_petkit` (MIT)**, which 2.x's cloud camera was adapted from; credit it as 2.x does. `CLEAN-ROOM.md` updated. |
| **V9** legacy `auth_mode_*` setup steps | Drop them; they are unreachable. No config entry depends on them. |
| **V10** last-error sensors | **Clear on the next OK code** from the same report kind (as `anycubic-lan` does). Changed from 2.x, which held the last fault. |
| **V11** first ACE's Drying Stop | **Stops the first ACE only.** Each unit has its own stop. Changed from 2.x. |
| **V12** COMPAT columns taken from the live install | For *existing* entities the registry wins anyway. For defaults on new installs use: enabled-by-default as in COMPAT §3.1/3.2 unless the registry shows `disabled_by: user` (a user choice, not a default). |
| **V13 / G4** stale sensor values during an outage | **All entities go unavailable together** when the printer is unreachable, once, and stay unavailable until it answers (never flap). |
| **V14 / G5** Reconfigure → Connection aborting | Must work: saving LAN settings from Reconfigure updates the entry and reloads it. |
| **V15** LAN camera start | Now in `anycubic-lan` PROTOCOL.md: publish `{"type":"video","action":"startCapture","data":{}}` on the `video` query topic; the printer replies with a `video` report. |
| **V16** icons | Now in COMPAT §3.3. |
| **V17** firmware target when no update exists | The update entity shows the installed version as the latest (no update available). |
| **G1** LAN filament tracking never deducts in 2.x | **3.0 deducts on job completion on both transports.** (Also being fixed in 2.x.) |
| **G20** money sensors with the measurement state class | Use state class **total** for lifetime cost and **none** for per-job cost; keep device class monetary. |

## Frontend (`FRONTEND.md`)

| Item | Decision |
|---|---|
| 1 package name | Publish the clean bundles under the existing PyPI name **`anycubic-cloud-frontend`** as a new major version (`1.0.0`), so the integration's requirement keeps its name. The implementation team must not read the existing package's contents. |
| 2 several printers, one panel | Keep 2.x behaviour: the first printer's `card_config` configures the panel. |
| 3 `card_config` values | **Honour `false`, `0`, empty values and whole-number `scaleFactor`**, and pass every card key through, including `mediaView`, `printerArt`, `showControls`, `showMoveButtons`, `sections`, `noCamera`. |
| 4 unknown `monitoredStats` | Skip silently. |
| 5 disabled entities | Treat as absent; the element that needs one hides. |
| 6 `moving` status colour | An "active" colour, not the error red. |
| 7 loaded slot on a second ACE | Highlight it, as for the first. |
| 8 Anycubic logo in the artwork | **No.** Draw generic printers without Anycubic's logo or other trademarks. |
| 9 Dry Time bar | Show **time remaining** on both card and panel. |
| 10 ETA | Use the `job_eta` timestamp sensor when it has a value; otherwise now + remaining time. |
| 11 Cancel on the card | **Ask for confirmation.** |
| 12 local/USB file lists over LAN | Refresh over LAN when the printer supports it; otherwise hide the refresh control. |
| 13 deleting a file | **Ask for confirmation.** |
| 14 state words | **Translate** job and printer states. |
| 15 translation text | **Write fresh.** The implementation team writes new English strings; other languages are translated from those. 2.x text is not reused. |
| 16 Home Assistant tab components | Use components that exist in current Home Assistant; don't depend on removed internals. |
