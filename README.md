# hass-anycubic-next

The clean-room rewrite of the **Anycubic Cloud & LAN** Home Assistant
integration (`anycubic_cloud` 3.0). It will replace the current 2.x code in
[Nino6689/hass-anycubic](https://github.com/Nino6689/hass-anycubic) once it
has been beta-tested. Users update through HACS as normal; nothing about their
setup changes.

- **Why:** so the whole integration is code we own outright (MIT), built on
  the same clean libraries as the Home Assistant core integration.
- **How:** written from specifications in [`docs/`](docs/) by a separate
  implementation team, under the rules in [`docs/CLEAN-ROOM.md`](docs/CLEAN-ROOM.md).
- **Status:** 3.0 development builds (`3.0.0-dev1`). Printers are reached
  over LAN Mode, over the Anycubic cloud, or both: the LAN half (Phase B),
  the dashboard card and side panel (Phase C) and the cloud half (Phase E2)
  are in `custom_components/anycubic_cloud/` and `frontend/`. Until 3.0 is
  released, 2.x stays fully maintained.

This project is **not affiliated with or endorsed by Anycubic**.

## The Anycubic cloud in 3.0

Cloud support is built on the MIT library
[`anycubic-cloud-client`](https://github.com/Nino6689/anycubic-cloud-client).
Anycubic has no public API: its cloud expects the credentials of its own apps
(app identifiers, an app secret, and a TLS client certificate for its MQTT
broker). Neither this integration nor that library contains any of them.
At run time the integration reads them, by name only, from the
[`anycubic-cloud-api`](https://pypi.org/project/anycubic-cloud-api/) package
that every 2.x install already has and that the manifest requires. They are
kept in memory, never logged, never written to disk and never put in
diagnostics. If the package is missing or incomplete, a repair notice says so:
entries in LAN Mode keep working, and entries that need the cloud wait,
unchanged.

You sign in by pasting the access token of Anycubic Slicer Next (a website or
Android-app token works too); the integration never asks for a password.
Tokens last about 90 days, and a repair notice warns two weeks before yours
expires.

## Development

```sh
# anycubic-cloud-client comes from its release branch until 0.1.0 is on PyPI;
# the tests never need Anycubic's credentials package.
pip install -r requirements_test.txt
ruff check . && ruff format --check .
mypy
pytest
```

MIT licence.
