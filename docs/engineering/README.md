# Engineering notes

This folder holds the engineering decisions for the harness. It does not hold business content.

The folder started on 2026-08-08 after a research session. The session measured where the harness
loses operator time. It also compared the harness against external systems.

## Contents

| File | Content |
|---|---|
| `001-evidence.md` | The measurements from the session. Each item has a source. |
| `002-decisions.md` | The decisions. It shows decided items and open items separately. |
| `003-roadmap.md` | The work phases in priority order. |

## Relation to other folders

- `docs/decisions/` holds the older architecture decision records (0001 to 0008). Do not duplicate
  them here. This folder records engineering decisions that came from the 2026-08-08 session.
- `engine/` holds the doctrine that the model reads during work.
- `tools/` holds the code that makes decisions without a model.

## Terminology

Use these terms with one meaning only. Do not use other words for the same thing.

| Term | Meaning |
|---|---|
| harness | The research system in this repository. |
| operator | The person who supervises the harness. |
| claim | A statement of fact in a document. |
| finding | A record of a confirmed vulnerability. |
| gate | A check that stops the work until a condition is true. |
| oracle | A check that decides if a result is real. |
| card | A reusable knowledge file in `skills/`. |
| intervention | A correction that the operator makes to the harness output. |
| evaluation primitive | A cheap mechanical check that shows if a result is real. |
| deterministic grader | Code that decides pass or fail. A model cannot change it. |

## Rules for this folder

1. Write each claim with a source. Give a file path, a command, or a URL.
2. Show measured values and estimated values separately.
3. Keep decided items and open items separately. Do not mix them.
