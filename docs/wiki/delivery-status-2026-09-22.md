# Local candidate delivery status — 2026-09-22

This page records three separate local candidate heads. They have not been merged, pushed or
released as one system, and their evidence must not be combined into a full qualification claim.
The coordinator is independently reviewing the defensive controls. This is a dated handoff, not a
live status service.

## Candidate boundaries

| Candidate | Exact local head | Observed evidence | Qualification boundary |
| --- | --- | --- | --- |
| Research and optional task board | `1d461b8661da37098c609fe4ef3257c7eaf2667a` (`codex/task-board-research`) | The [portable research artifacts](../experiments/run-artifacts/2026-09-22/README.md) retain the frozen prompts, outputs, manifests, grades and usage receipts. | The board is an optional communication mechanism. The studies do not justify default adoption or a production-effectiveness claim. |
| Integrated filing and worker-flow candidate | `d859a8990b58e71e5b21448070adb6b0fb642264` (`codex/full-harness-delivery-2026-09-22`) | The candidate joins the governed filing path with the container worker workflow and records an actual Claude Code 2.1.278 request to an owned fake Anthropic server. | A clean, exact-head integrated check is pending. The fake-provider observation is not real-provider qualification. |
| Enforced-egress candidate | `3ce769ab28a4bcdf2c361b6b5302c4c50d8cdc5c` (`codex/enforced-egress`) | The candidate contains the separately exercised network-scope controls and a retained managed-sandbox limitation artifact. | It is a separate local candidate. Real Anthropic authentication and inference remain unqualified. |

The branch names and commits identify local review inputs. They do not establish ancestry between
the candidates or approval to integrate them.

## Research recommendation

Keep the typed task board optional. In the matched communication pilot, serial assembly graded
correct twice, direct assembly zero times and board assembly zero times; the board had two wrong
results and one ambiguous result. One correction was represented through the board, but no measured
case supports adopting it by default. The study does not establish a gaslighting or
unsupported-certainty advantage for the board.

The active framing pilot produced nine oracle-matching classifications and no observed difference
between frames. Its fixed two-call schedule measures bounded probe choice and classification; it
does not measure adaptive persistence, search depth or stopping benefit. The scripted recovery
pilot showed late-input and soft-cancel restoration mechanics, while replay from a pre-effect state
duplicated an unreceipted local effect. State recovery therefore does not establish exactly-once
external effects. See [recovery and communication experiments](comparison-experiments.md) for the
experiment lineage and [future evaluation applications](future-evaluations.md) for still-proposed
work.

## Pending and unresolved qualification

- **Integrated checks pending.** A previous full-kernel attempt did not produce a qualifying
  completion before its time limit; a retained later log also ended non-success at
  `record_review_staging_budget_exceeded`. A clean exact-head integrated run remains pending. No
  full-system pass is claimed here.
- **Real provider deferred.** Real-provider qualification was deferred by the user after the
  available Claude authentication path returned `403 oauth_not_allowed_for_organization`. The
  recorded request/response exercise used an owned fake provider. It establishes actual-client
  request shape and local protocol handling only.
- **UNRESOLVED compatibility observation.** The actual Claude Code client against the owned fake
  provider emitted `POST /v1/messages?beta=true`, while the separate egress candidate's typed
  provider-path contract is `/v1/messages`. These candidates have not been exercised together, so
  compatibility is unverified. This observation carries no implementation instruction.
- **Managed-sandbox limitation.** Two POSIX session checks in the egress worktree encountered
  `PermissionError` when the managed CLI sandbox denied `os.killpg`. The Docker qualification was
  performed separately; the POSIX failures are retained as a test-environment limitation, not
  converted into a pass.

This delivery covers defensive controls, provenance and research documentation only. It adds no
live-target authority, Zone-2 work or autonomous hunter capability. The [task-board contract](../engineering/task-board-v1.md),
[filing scope](../engineering/filing-scope-2026-09-20.md) and [Docker work-queue contract](../agents/docker-work-queue.md)
remain the relevant source documents; this page does not supersede them.
