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

## Q3 — Shape of the `extfilbox` report

*Asked by the implementation team (Phase B, LAN), 2026-09-28.*

BEHAVIOUR §2.7 describes the external holder's material, colour and loaded
flag, but no LAN payload is documented (anycubic-lan keeps it as raw data).
**Interim choice** (`model.py`, `Printer.external_spool`): read the block
itself, or `data.external_shelves` when present; material from `type`, else
`material`; colour from `color` (`[r, g, b]`); loaded from `loaded`; the
holder is absent when `id`, material and `loaded` are all missing. What are
the real keys?

## Q4 — Unique ids of a printer that reports no MAC

*Asked by the implementation team (Phase B, LAN), 2026-09-28.*

COMPAT §3 builds every unique id from the MAC. When the discovery document
has no `usn`, the entry's unique id is `lan-<host>` (COMPAT §1) but nothing
says what entity unique ids use. **Interim choice** (`coordinator.py`): the
broker's `deviceId`, upper-cased, in place of the MAC. Did 2.x do something
else here?

## Q5 — Hybrid entry covering several printers

*Asked by the implementation team (Phase B, LAN), 2026-09-28.*

A cloud entry may list several `printer_ids`, but LAN Mode reaches one
printer (`options.lan_host`). Without the cloud there is no way to tell which
id it is. **Interim choice**: the first id in `printer_ids`, with a warning in
the log. Is there a better rule (in 2.x, the cloud matched it by model id)?

## Q6 — How the frontend bundles reach the integration

*Asked by the implementation team (Phase B, LAN), 2026-09-28.*

FRONTEND §1.1 leaves the delivery open, and DECISIONS frontend 1 names the
PyPI package `anycubic-cloud-frontend` 1.0.0 without its interface (how the
integration asks for the directory, file names and component name).
**Interim choice** (`panel.py`): serve `custom_components/anycubic_cloud/www/`
when it contains `anycubic-card.js` and one `entrypoint*.js`; the panel's
component name is `anycubic-cloud-panel`. Nothing is registered when the
bundles are absent. Which interface should the integration use?

## Q7 — 2.x cloud entries during the LAN-only beta

*Asked by the implementation team (Phase B, LAN), 2026-09-28.*

As instructed, a cloud entry without LAN Mode stays *not ready* (retried with
back-off) and gets a warning repair issue `cloud_not_supported_yet_<entry id>`
explaining that cloud support arrives in a later beta; its data and options
are never touched. Confirm this is the wanted user experience (the
alternative is a terminal setup error, which stops the retries).

## Q8 — Cloud-only entities left in the registry of LAN entries

*Asked by the implementation team (Phase B, LAN), 2026-09-28.*

2.x created some cloud-sourced entities on LAN entries too (for example
`print_time_total_hrs`, the file lists, `mqtt_connection_active`,
`cloud_camera`). 3.0 does not create them on LAN entries, so Home Assistant
shows them as "no longer provided". **Interim choice**: leave them in the
registry (the user can delete them; nothing is removed automatically). Should
3.0 remove them, or keep providing them as always unavailable?

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
