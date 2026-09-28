# anycubic-cloud-frontend

The built sidebar panel and dashboard card for the `anycubic_cloud` Home
Assistant integration. Home Assistant core does not accept frontend files
inside an integration, so they ship in this package; the integration serves
the directory it points at.

```python
import anycubic_cloud_frontend as fe

fe.locate_dir()        # directory to serve at /anycubic-cloud-panel-static
fe.entrypoint_js()     # "entrypoint.<hash>.js" — the panel module
fe.webcomponent_name() # "anycubic-cloud-panel"
fe.card_js()           # "anycubic-card.js" (stable name)
fe.card_hash()         # content hash for "anycubic-card.js?v=<hash>"
```

Build it from `frontend/` with `npm ci && npm run build`, then build the wheel
here. MIT licence.
