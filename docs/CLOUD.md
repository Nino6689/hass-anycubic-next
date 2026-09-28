# Cloud half of 3.0: integration requirements

Phase E. The cloud protocol and the client library it is built on live in
`Nino6689/anycubic-cloud-client` (MIT): `docs/PROTOCOL.md` for the wire, and
`docs/INTEGRATION-SPEC.md` for the library API. This file covers what is
specific to the integration. Everything else about the cloud is already in
this repository:

| Topic | Where |
|---|---|
| What every entity means, and its cloud source (HTTP, CMQTT) | `BEHAVIOUR.md` §1–§2 |
| Refresh cadence, cloud MQTT, hybrid entries, printer off | `BEHAVIOUR.md` §5.1, §5.2, §5.4, §5.5 |
| Tokens, expiry repair, re-authentication | `BEHAVIOUR.md` §5.6, and PROTOCOL A §5.3 (required rules) |
| Setup outcomes, config flow, options flow | `BEHAVIOUR.md` §5.7–§5.9 |
| Config entry data and options, token store, step ids | `COMPAT.md` §1, §6 |
| Actions and their cloud forms | `BEHAVIOUR.md` §4 |
| Decisions that override 2.x | `DECISIONS.md` |

## 1. Anycubic's credentials: where the integration gets them

Decision (Nino, 2026-09-28): 3.0 loads Anycubic's app credentials and MQTT
TLS material **at run time from the PyPI package `anycubic-cloud-api`**. Every
2.x install already has that package. Nothing is copied into this repository or
into `anycubic-cloud-client`. The implementation team loads the items named
below **by name only** and must not read that package's source (`CLEAN-ROOM.md`).

- Add the requirement `anycubic-cloud-api>=0.4.31,<0.5` to the manifest. Its
  dependencies are compatible with `anycubic-lan`'s: `aiohttp`, `cryptography`
  and `paho-mqtt`, plus `aiofiles` and `bcrypt`.
- Build the library's `CloudSecrets` from:

  | `CloudSecrets` field | Source in the installed package |
  |---|---|
  | `app_id` | attribute `AC_KNOWN_AID` of module `anycubic_cloud_api.const.const` |
  | `app_secret` | attribute `AC_KNOWN_SEC` of the same module |
  | `client_id_web` | attribute `AC_KNOWN_CID_WEB` of the same module |
  | `client_id_app` | attribute `AC_KNOWN_CID_APP` of the same module |
  | `mqtt_ca_pem` | package data file `resources/anycubic_mqqt_tls_ca.crt` in package `anycubic_cloud_api` (note the spelling `mqqt`) |
  | `mqtt_client_cert_pem` | package data file `resources/anycubic_mqqt_tls_client.crt` |
  | `mqtt_client_key_pem` | package data file `resources/anycubic_mqqt_tls_client.key` |

- Load them once per Home Assistant run, in the executor, because importing and
  file reads block. Keep them only in memory. Never log them, and never put
  them in diagnostics, `repr`s or the token store export.
- If the package, a module attribute or a file is missing, or `CloudSecrets`
  rejects them:
  - cloud features are unavailable;
  - raise a translated repair issue (`cloud_credentials_unavailable`) and log one warning;
  - hybrid entries keep running on LAN, and cloud-only entries are *not ready*;
  - the user's data is never touched.
- Tests mock the loader and use fake values. CI must not need the real package.

## 2. What changes from the LAN-only beta

- Cloud entries now load. Remove the repair `cloud_not_supported_yet_<entry id>`
  and the *not ready* path from DECISIONS round 2 Q7. Delete a leftover
  issue of that kind on setup.
- Hybrid entries (`options.lan_mode_enabled` + `options.lan_host`) run both
  transports as `BEHAVIOUR.md` §5.4 says: LAN for what LAN provides, cloud for
  the rest. The entities left unavailable on LAN are created again from the cloud: the
  cloud-only set in `ACCEPTANCE.md` (Upgrade test U, "not provided").
- `mqtt_connect_mode` and the "refresh MQTT connection" and "manual MQTT connection" entities come back (BEHAVIOUR §5.2).
- The config flow gains the cloud steps in COMPAT §1: region, auth mode pick,
  token, and the Android device id. Also re-authentication and reconfigure, with the
  mode-picking order in PROTOCOL A §2.9.
- Accept entries whose `user_auth_mode` is 3 but whose token is a web token
  (PROTOCOL A §2.8). They exist in the field.
- The file-list buttons (answer F3) become available whenever the cloud can
  fetch that list.
- The firmware update entities get `latest_version` from the cloud (G10) and
  offer install where BEHAVIOUR §2.17 says so.

## 3. Acceptance the specification team will run

The same harness as Phase B (`ACCEPTANCE.md`), over the copy of a real 2.x
cloud install:

1. **Upgrade:** no entity id changes. The 2.x cloud entities come back with values that match
   live 2.x, and the token store is kept.
2. **Live cloud reads, then harmless commands.**
3. **A camera stream.**
4. **Re-authentication with a fresh token.**

These tests need the printer with LAN Mode **off** for the time they run.
