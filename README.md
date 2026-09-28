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
- **Status:** specification phase. Until 3.0 is released, 2.x stays fully
  maintained.

MIT licence.
