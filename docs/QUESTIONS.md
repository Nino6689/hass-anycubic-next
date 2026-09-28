# Questions from the implementation team

Ask here when a fact you need is missing from the specs. Do not look for the
answer elsewhere. The specification team answers below each question.

## Q1 — Field names inside LAN order payloads

*Asked by the implementation team (Phase B, LAN), 2026-09-28.*

anycubic-lan PROTOCOL §7.2 names the kind/action of the temperature, fan,
axis and ACE orders but says their `data` field names "should be confirmed
against a printer". BEHAVIOUR §5.3 says the payload is the cloud order's,
which the implementation team has no description of. **Interim choice**
(`lan.py`), modelled on the printer's own report shapes:

| Order | `data` sent |
|---|---|
| `tempature`/`set` | only the figure being changed: `{"target_nozzle_temp": n}` or `{"target_hotbed_temp": n}`. BEHAVIOUR §2.13 says the cloud sends the other figure as 0 with a heat type; without the heat-type field name, sending 0 might switch the other heater off, so it is left out. |
| `fan`/`setSpeed` | only the fan being changed: `{"fan_speed_pct": n}`, `{"aux_fan_speed_pct": n}` or `{"box_fan_level": n}` |
| `axis`/`move` | `{"axis": 1-4, "move_type": 0/1/2, "distance": mm}` |
| `axis`/`turnOff` | `{}` |
| `multiColorBox`/`setDry` | `{"multi_color_box": [{"id": box, "drying_status": {"status": 0/1, "target_temp": °C, "duration": min}}]}` |
| `multiColorBox`/`feedFilament` | `{"multi_color_box": [{"id": box, "feed_status": {"slot_index": i, "type": 1/2/3}}]}` |
| `multiColorBox`/`setInfo` | `{"multi_color_box": [{"id": box, "slots": [{"index": i, "type": material, "color": [r,g,b]}]}]}` |
| `multiColorBox`/`setAutoFeed` | `{"multi_color_box": [{"id": box, "auto_feed": 0/1}]}` |

What are the exact `data` objects the printer accepts for each?

**Applied in round 2.**

## Q2 — Public hooks missing from anycubic-lan 0.1.0

*Asked by the implementation team (Phase B, LAN), 2026-09-28.*

1. The axis binary sensors need the `axis`/`move` report's `state`
   (`doing`/`done`/`failed`, BEHAVIOUR §1.8), which `PrinterState` does not
   keep. **Interim choice**: `IntegrationLanClient` (in `lan.py`) overrides
   the client's private `_handle_message` and runs the public
   `parse_message` on each payload before anycubic-lan merges it. Could
   anycubic-lan offer a public raw-report listener (or keep the last axis
   move state), so the override can go?
2. `print_speed_pct` (BEHAVIOUR §2.2: "CMQTT/LAN print `updated`") is not
   parsed by anycubic-lan, so on LAN the sensor has no value (unavailable).
   Which field carries it in LAN reports, and can the library expose it?
3. anycubic-lan's `ACE_MODELS` still maps `40002` to "ACE Pro"; PROTOCOL
   §6.7 now says `40001`. The integration uses its own table (COMPAT §2).

**Applied in round 2.**

## Q3 — Shape of the `extfilbox` report

*Asked by the implementation team (Phase B, LAN), 2026-09-28.*

BEHAVIOUR §2.7 describes the external holder's material, colour and loaded
flag, but no LAN payload is documented (anycubic-lan keeps it as raw data).
**Interim choice** (`model.py`, `Printer.external_spool`): read the block
itself, or `data.external_shelves` when present; material from `type`, else
`material`; colour from `color` (`[r, g, b]`); loaded from `loaded`; the
holder is absent when `id`, material and `loaded` are all missing. What are
the real keys?

**Applied in round 2.**

## Q4 — Unique ids of a printer that reports no MAC

*Asked by the implementation team (Phase B, LAN), 2026-09-28.*

COMPAT §3 builds every unique id from the MAC. When the discovery document
has no `usn`, the entry's unique id is `lan-<host>` (COMPAT §1) but nothing
says what entity unique ids use. **Interim choice** (`coordinator.py`): the
broker's `deviceId`, upper-cased, in place of the MAC. Did 2.x do something
else here?

**Applied in round 2.**

## Q5 — Hybrid entry covering several printers

*Asked by the implementation team (Phase B, LAN), 2026-09-28.*

A cloud entry may list several `printer_ids`, but LAN Mode reaches one
printer (`options.lan_host`). Without the cloud there is no way to tell which
id it is. **Interim choice**: the first id in `printer_ids`, with a warning in
the log. Is there a better rule (in 2.x, the cloud matched it by model id)?

**Applied in round 2.**

## Q6 — How the frontend bundles reach the integration

*Asked by the implementation team (Phase B, LAN), 2026-09-28.*

FRONTEND §1.1 leaves the delivery open, and DECISIONS frontend 1 names the
PyPI package `anycubic-cloud-frontend` 1.0.0 without its interface (how the
integration asks for the directory, file names and component name).
**Interim choice** (`panel.py`): serve `custom_components/anycubic_cloud/www/`
when it contains `anycubic-card.js` and one `entrypoint*.js`; the panel's
component name is `anycubic-cloud-panel`. Nothing is registered when the
bundles are absent. Which interface should the integration use?

**Applied in round 2.**

## Q7 — 2.x cloud entries during the LAN-only beta

*Asked by the implementation team (Phase B, LAN), 2026-09-28.*

As instructed, a cloud entry without LAN Mode stays *not ready* (retried with
back-off) and gets a warning repair issue `cloud_not_supported_yet_<entry id>`
explaining that cloud support arrives in a later beta; its data and options
are never touched. Confirm this is the wanted user experience (the
alternative is a terminal setup error, which stops the retries).

**Applied in round 2.**

## Q8 — Cloud-only entities left in the registry of LAN entries

*Asked by the implementation team (Phase B, LAN), 2026-09-28.*

2.x created some cloud-sourced entities on LAN entries too (for example
`print_time_total_hrs`, the file lists, `mqtt_connection_active`,
`cloud_camera`). 3.0 does not create them on LAN entries, so Home Assistant
shows them as "no longer provided". **Interim choice**: leave them in the
registry (the user can delete them; nothing is removed automatically). Should
3.0 remove them, or keep providing them as always unavailable?

**Applied in round 2.**

## Q9 — Entity names and DHCP matchers

*Asked by the implementation team (Phase B, LAN), 2026-09-28.*

1. DECISIONS frontend 15 says to write all strings fresh, but COMPAT §3 says
   new installs keep 2.x entity ids only if the English entity names stay the
   same. **Interim choice**: entity names are taken from COMPAT's "Name (en)"
   column (a compatibility fact); every other string (flows, errors, issues,
   actions, states) is new text. The eight drying-preset buttons have no
   COMPAT name and got new ones ("Start drying preset N", "Secondary start
   drying preset N"). Please confirm.
2. COMPAT does not list the manifest's DHCP matchers. **Interim choice**:
   anycubic-lan PROTOCOL §8 — MAC prefix `A4E88D*`, hostnames `anycubic*`
   and `kobra*`.

**Applied in round 2.**

## Frontend — Phase C (implementation team, 2026-09-28)

**F1. How does the integration hand `card_config` to the panel?** FRONTEND.md
§1.2 says "passed as the panel's config". The frontend accepts both the object
itself as the panel config (ignoring Home Assistant's `_panel_custom` block)
and the object nested under a `card_config` key. Please confirm which the
integration will use.

**Applied in round 2.**

**F2. Python package interface.** The integration should call
`locate_dir()`, `entrypoint_js()`, `webcomponent_name()`, `card_js()` and
`card_hash()` (constants of the same values are exported as well). Is that
the interface the integration team expects, or should names change?

**Applied in round 2.**

**F3. Local/USB file refresh over LAN (DECISIONS frontend 12).** The frontend
cannot see whether a LAN link can deliver file lists. It currently offers the
refresh control when the `request_file_list_<source>` button exists and is not
unavailable, and (for local/USB) `mqtt_connection_active` does not report
`supports_mqtt_login: false`; otherwise it hides the control and shows the
notice. Is there, or should there be, a clearer signal (for example, the
request buttons going unavailable when the list cannot be fetched)?

**Applied in round 2.**

**F4. Translated state words (DECISIONS frontend 14).** The frontend
translates job and printer states with its own strings (`common.states.*`) and
title-cases words it does not know. Will the integration ship entity state
translations for `job_state` and `current_status`? If so, the frontend could
use Home Assistant's own state formatting instead.

**Applied in round 2.**

**F5. Disabled entities (FRONTEND.md §3.2).** The frontend treats an entity as
absent unless it is in `hass.entities` **and** has a state object, so a
disabled entity is missing either way. No answer needed unless that is wrong.

**Applied in round 2.**

**F6. ETA more than a day away.** The `ETA` stat shows a clock time only, as
specified; a job ending tomorrow shows just the time. Should it add the day?

**Applied in round 2.**

## Phase E2 — the cloud half (implementation team, 2026-09-28)

Asked while building the cloud half on `anycubic-cloud-client` 0.1.0. Each
interim choice is marked in the code with its number (`E2-Qn in
docs/QUESTIONS.md`).

**E2-Q1. The Agora SDK key for encrypted camera channels.** The library's
Agora client needs the RSA public key embedded in `agora-rtc-sdk-ng` 4.24.0
to join an encrypted channel (its QUESTIONS Q6); the Kobra S1's camera
answers with `AES_256_GCM2`. The integration has no source for that key.
**Interim choice** (`camera.py`): the session is built without it, so an
unencrypted channel streams and an encrypted one fails with a clear
"Could not open the Anycubic cloud camera" error. Where should the key come
from - loaded by name like the app credentials (CLOUD.md §1), or shipped in
the library?

**E2-Q2. Setup after repeated transient answers.** BEHAVIOUR §5.7 and
PROTOCOL A §3.7 say setup retries a "request error" answer 3 times, 10 s
apart, then fails with a *terminal* error. A terminal error leaves the entry
failed until the user reloads it, which a cloud outage or a rate limit at
Home Assistant start-up would cause. **Interim choice** (`cloud.py`,
`CloudAccount._async_setup_retry`): the 3 retries 10 s apart are kept, then
the entry is *not ready* and Home Assistant keeps retrying with back-off.
Confirm, or should it be terminal after all?

**E2-Q3. The expiry repair's links.** BEHAVIOUR §5.6 names placeholders
`tool_macos`, `tool_windows`, `tool_browser` ("the three helper links") and a
learn-more link "to the token tools", but not their addresses. **Interim
choice** (`cloud.py`, `HELP_URL`): all four point to the token section of
the 2.x README, `https://github.com/Nino6689/hass-anycubic#getting-a-token`.
Which addresses should they be?

**E2-Q4. The legacy `auth_mode_*` steps.** DECISIONS V9 says to drop them;
this phase's task asks for COMPAT §1's step ids including the auth-mode pick.
**Interim choice** (`config_flow.py`): `auth_mode_pick`, `auth_mode_web`,
`auth_mode_slicer` and `auth_mode_android` exist as BEHAVIOUR §5.8 describes
(fixed mode, quotes stripped, no other checks; a re-authentication through
them neither clears the store nor reloads), and no menu leads to them, as in
2.x. Should they be removed instead?

**E2-Q5. Printers not loaded at setup.** BEHAVIOUR §1.7 says a selected
printer not loaded at setup is picked up by a later refresh; G23 says a
printer the cloud cannot supply at setup makes the entry *not ready*.
**Interim choice** (`__init__.py`): not ready (the retried setup then picks
the printer up), since an offline printer still has a cloud record. The one
exception: a hybrid entry whose cloud is unavailable at setup runs its LAN
printer and leaves the others to the next setup. Is a runtime pickup still
wanted on top?

**E2-Q6. Re-authentication with another account's token.** Nothing says what
happens when the new token belongs to a different Anycubic account than the
entry (its unique id). **Interim choice** (`config_flow.py`): abort
`wrong_account` and change nothing, as Home Assistant integrations usually
do. Confirm.

**E2-Q7. The outage log.** BEHAVIOUR §5.5 wants a cloud outage logged once
(warning) and its recovery once (info). The integration does so; Home
Assistant's coordinator also logs its own standard line once per printer at
the start of the outage (error) and at recovery (info). **Interim choice**:
both are kept. Should the coordinator's line be suppressed?

**E2-Q8. The token store's app keys.** The 2.x store also holds
`app_id`, `app_secret`, `app_version` and `app_client_id`. The library never
exports Anycubic's credentials, so 3.0 saves only `auth_token`,
`auth_access_token`, `device_id` and `auth_mode`; 2.x reads back only the
first three, so a downgrade keeps working. Confirm that dropping the four app
keys from the store on the first save is acceptable.

**E2-Q9. The cloud file list on a printer in LAN Mode.** The cloud list is
the account's, over HTTP, so `request_file_list_cloud` stays available on a
hybrid entry whose printer is on LAN (answer F3: available whenever the list
can be fetched), while the local and USB buttons are unavailable there.
Confirm.
