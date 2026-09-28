# Questions from the implementation team

Ask here when a fact you need is missing from the specs. Do not look for the
answer elsewhere. The specification team answers below each question.

## Frontend — Phase C (implementation team, 2026-09-28)

**F1. How does the integration hand `card_config` to the panel?** FRONTEND.md
§1.2 says "passed as the panel's config". The frontend accepts both the object
itself as the panel config (ignoring Home Assistant's `_panel_custom` block)
and the object nested under a `card_config` key. Please confirm which the
integration will use.

**F2. Python package interface.** The integration should call
`locate_dir()`, `entrypoint_js()`, `webcomponent_name()`, `card_js()` and
`card_hash()` (constants of the same values are exported as well). Is that
the interface the integration team expects, or should names change?

**F3. Local/USB file refresh over LAN (DECISIONS frontend 12).** The frontend
cannot see whether a LAN link can deliver file lists. It currently offers the
refresh control when the `request_file_list_<source>` button exists and is not
unavailable, and (for local/USB) `mqtt_connection_active` does not report
`supports_mqtt_login: false`; otherwise it hides the control and shows the
notice. Is there, or should there be, a clearer signal (for example, the
request buttons going unavailable when the list cannot be fetched)?

**F4. Translated state words (DECISIONS frontend 14).** The frontend
translates job and printer states with its own strings (`common.states.*`) and
title-cases words it does not know. Will the integration ship entity state
translations for `job_state` and `current_status`? If so, the frontend could
use Home Assistant's own state formatting instead.

**F5. Disabled entities (FRONTEND.md §3.2).** The frontend treats an entity as
absent unless it is in `hass.entities` **and** has a state object, so a
disabled entity is missing either way. No answer needed unless that is wrong.

**F6. ETA more than a day away.** The `ETA` stat shows a clock time only, as
specified; a job ending tomorrow shows just the time. Should it add the day?
