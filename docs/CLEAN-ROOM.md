# Clean-room record — `anycubic_cloud` 3.0

`anycubic_cloud` 2.x (Nino6689/hass-anycubic) is GPL-3.0 and largely derived
from WaresWichall/hass-anycubic_cloud. 3.0 is a from-scratch reimplementation,
MIT-licensed, containing no code or expression from those projects.

## Roles

| Role | Who | May read | Must not read |
|---|---|---|---|
| **Specification team** | Nino Bondonno, and Claude sessions on his machine | Everything | — |
| **Implementation team** | Claude cloud sessions whose only sources are this repository and the MIT libraries below | This repository's `docs/`; `Nino6689/anycubic-lan` (MIT) and any clean libraries listed here; Python, Home Assistant and dependency documentation; `home-assistant/core` for house style | `Nino6689/hass-anycubic`, `Nino6689/anycubic-cloud-api`, the PyPI packages `anycubic-cloud-api` and `anycubic-cloud-frontend`, `WaresWichall/hass-anycubic_cloud`, `dangreco/threedy`, and any other Anycubic Home Assistant integration or card |

Rules: the specification team writes facts and required behaviour only; the
implementation team writes all code and asks in `docs/QUESTIONS.md` rather
than looking elsewhere; feedback from testing is functional only; finished
code is compared mechanically with the GPL projects before release.

## Log

| Date | Team | Session | Inputs given | Outputs | Did not read the excluded repos |
|---|---|---|---|---|---|
| 2026-09-28 | Specification | Claude (local, Nino's machine) | The live 2.9.x install on Nino's Home Assistant (entity and device registry, entity attributes, `.storage` shapes with values removed, config entry keys); the 2.x translations; the 2.x code, read for facts | `COMPAT.md`, this file, `README.md`, `LICENSE` | n/a — specification team |
| 2026-09-28 | Specification | Claude (local, Nino's machine) | The 2.x integration (`anycubic_cloud` 2.9.3) and library (`anycubic-cloud-api` 0.4.31) code and tests, read for facts; `Nino6689/anycubic-lan` docs | `BEHAVIOUR.md`; corrections to `COMPAT.md` §1, §4, §5, §7 | n/a — specification team |

## Similarity checks

| Date | Artefact | Compared against | Longest identical run | Result |
|---|---|---|---|---|
| 2026-09-28 | `docs/BEHAVIOUR.md` | 2.x integration, library and tests (`.py`, `.json`, `.yaml`), runs of 8+ words | 38 words — the filament density table (data) | Only key names, enum lists and constant tables reach 8 words; prose rewritten until none did |
