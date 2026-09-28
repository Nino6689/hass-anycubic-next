# anycubic_cloud 3.0 frontend

The sidebar panel and the dashboard card (`custom:anycubic-card`) for the
`anycubic_cloud` integration, written from `docs/FRONTEND.md` and
`docs/DECISIONS.md` under the clean-room rules in `docs/CLEAN-ROOM.md`.
TypeScript + Lit, bundled with Rollup. MIT licence.

## Commands

```sh
npm ci
npm run lint        # eslint
npm run typecheck   # tsc --noEmit
npm test            # vitest (config parsing, entity resolution, formatting, helpers)
npm run build       # rollup + scripts/stamp.mjs
```

`npm run build:debug` builds unminified bundles with the panel's debug page.

## Output

| File | Served as |
|---|---|
| `dist/entrypoint.<sha256[:8]>.js` | the panel module (custom element `anycubic-cloud-panel`) |
| `dist/anycubic-card.js` | the card module, stable name; load as `anycubic-card.js?v=<card hash>` |
| `dist/build.json` | the names and both hashes |

The panel and card hashes are computed separately. `scripts/stamp.mjs` renames
the panel file, copies both bundles into `python/anycubic_cloud_frontend/dist/`
and writes `python/anycubic_cloud_frontend/_build.py`, so the Python package
always names the files it ships.

## The Python package (`python/`)

`anycubic-cloud-frontend` `1.0.0.dev0` (not published). The integration uses:

```python
import anycubic_cloud_frontend as fe

fe.locate_dir()  # serve this directory at /anycubic-cloud-panel-static
fe.entrypoint_js()  # panel module filename, register with module_url
fe.webcomponent_name()  # "anycubic-cloud-panel"
fe.card_js()  # "anycubic-card.js"
fe.card_hash()  # add the card as an extra JS module: anycubic-card.js?v=<hash>
```

Constants `ENTRYPOINT_JS`, `CARD_JS`, `CARD_HASH`, `PANEL_HASH`,
`WEBCOMPONENT_NAME` and `FRONTEND_VERSION` are exported too. Build the wheel
after `npm run build`: `python -m build --wheel python`.

The panel reads its card settings from the panel config: the integration
passes the entry's stored `card_config` object as the config itself. The same
object nested under a `card_config` key is also accepted.

State words (Status, Availability, the header) use Home Assistant's translated
entity state (`hass.formatEntityState`) and fall back to the card's own strings
for states it cannot translate. A file list's refresh control is disabled, with
a notice, while its `request_file_list_<source>` button is unavailable or
missing. The ETA adds a short weekday when the job ends on another day.

## Source layout

| Path | Contents |
|---|---|
| `src/lib/` | pure logic: config keys and defaults, entity resolution, state, formatting, colours, ACE data, artwork body choice, actions, YAML |
| `src/localize/` | strings (`en.json`; other languages fall back to English per key) |
| `src/card/` | the card, hero, artwork, camera view, dialogs and editor |
| `src/panel/` | the panel shell, main, file and print pages |
| `src/ui/` | shared dialog, icon and styles |
| `tests/` | unit tests |
