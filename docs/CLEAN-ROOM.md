# Clean-room record — `anycubic_cloud` 3.0

`anycubic_cloud` 2.x (Nino6689/hass-anycubic) is GPL-3.0 and largely derived
from WaresWichall/hass-anycubic_cloud. 3.0 is a from-scratch reimplementation,
MIT-licensed, containing no code or expression from those projects.

## Roles

| Role | Who | May read | Must not read |
|---|---|---|---|
| **Specification team** | Nino Bondonno, and Claude sessions on his machine | Everything | — |
| **Implementation team** | Claude cloud sessions whose only sources are this repository and the MIT libraries below | This repository's `docs/`; `Nino6689/anycubic-lan` (MIT) and any clean libraries listed here; `Jezza34000/homeassistant_petkit` (MIT) for the cloud camera's Agora client, credited; Python, Home Assistant and dependency documentation; `home-assistant/core` for house style | `Nino6689/hass-anycubic`, `Nino6689/anycubic-cloud-api`, the PyPI package `anycubic-cloud-api`, the **0.x** releases of the PyPI package `anycubic-cloud-frontend` (1.0.0 and later are built from this repository's `frontend/` and are clean), `WaresWichall/hass-anycubic_cloud`, `dangreco/threedy`, and any other Anycubic Home Assistant integration or card |

Rules: the specification team writes facts and required behaviour only; the
implementation team writes all code and asks in `docs/QUESTIONS.md` rather
than looking elsewhere; feedback from testing is functional only; finished
code is compared mechanically with the GPL projects before release.

## Log

| Date | Team | Session | Inputs given | Outputs | Did not read the excluded repos |
|---|---|---|---|---|---|
| 2026-09-28 | Specification | Claude (local, Nino's machine) | The live 2.9.x install on Nino's Home Assistant (entity and device registry, entity attributes, `.storage` shapes with values removed, config entry keys); the 2.x translations; the 2.x code, read for facts | `COMPAT.md`, this file, `README.md`, `LICENSE` | n/a — specification team |
| 2026-09-28 | Specification | Claude (local, Nino's machine) | The 2.x integration (`anycubic_cloud` 2.9.3) and library (`anycubic-cloud-api` 0.4.31) code and tests, read for facts; `Nino6689/anycubic-lan` docs | `BEHAVIOUR.md`; corrections to `COMPAT.md` §1, §4, §5, §7 | n/a — specification team |
| 2026-09-28 | Specification | Claude (local, frontend agent) | The 2.x frontend panel and card, read for facts | `FRONTEND.md` | n/a — specification team |
| 2026-09-28 | Specification | Claude (local) | `BEHAVIOUR.md` §9 and `FRONTEND.md` §7 open items; 2.x `icons.json` | `DECISIONS.md`; COMPAT §3.3 icons; V8 source allowed above | n/a — specification team |
| 2026-09-28 | Implementation | Claude (cloud session, Phase C frontend, branch `clean/frontend`) | This repository's `docs/` (`FRONTEND.md`, `DECISIONS.md`, `COMPAT.md`, `BEHAVIOUR.md`); the npm packages Lit, @mdi/js, TypeScript, Rollup, Vitest and ESLint, installed from the registry; no web searches | `frontend/` (card, panel, strings, artwork, tests, `anycubic-cloud-frontend` Python package), `.github/workflows/frontend.yaml`, questions F1–F6 in `QUESTIONS.md` | Yes — none of the excluded repositories or packages, and no other printer card or panel, were opened, fetched, searched for or quoted |
| 2026-09-28 | Specification | Claude (local) | PR #1 and PR #2 (for acceptance and similarity checks only); 2.x code and library, read for protocol facts | Round-2 answers in `DECISIONS.md`; exact command payloads in `anycubic-lan` PROTOCOL.md | n/a — specification team |
| 2026-09-28 | Implementation | Claude cloud session (Phase C, round 2) | This repository's `docs/` (`CLEAN-ROOM.md`, `DECISIONS.md` round-2 answers, `QUESTIONS.md`; `FRONTEND.md` searched for the ETA rules) and `frontend/` on branch `clean/frontend`; the npm packages locked in `frontend/package-lock.json` and the Python `build` tool, installed from their registries; no web searches | `frontend/` changes for F1–F6 (panel config, file-refresh signal, Home Assistant state translations, ETA weekday) with tests; "Applied in round 2" notes in `QUESTIONS.md`; this row | Yes — none of the excluded repositories or packages, and no other printer card or panel, were opened, fetched, searched for or quoted |

## Similarity checks

| Date | Artefact | Compared against | Longest identical run | Result |
|---|---|---|---|---|
| 2026-09-28 | `docs/BEHAVIOUR.md` | 2.x integration, library and tests (`.py`, `.json`, `.yaml`), runs of 8+ words | 38 words — the filament density table (data) | Only key names, enum lists and constant tables reach 8 words; prose rewritten until none did |
| 2026-09-28 | PR #2 `custom_components/anycubic_cloud/` | 2.x integration, 2.x library, WaresWichall | 40 — Anycubic's error-code table (Anycubic's own messages, passed as data in BEHAVIOUR); 12 — filament density table (physical data); next 7 — Home Assistant import blocks | Clean |
| 2026-09-28 | PR #1 `frontend/src/` | 2.x `frontend_panel/src` | 5 — generic CSS centring rules; 4 — card default values required by COMPAT | Clean |
