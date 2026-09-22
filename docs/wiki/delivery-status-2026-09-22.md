# Local candidate delivery status — 2026-09-22

This page records the September 22 candidate progression. The three original heads below are
historical inputs; they were integrated and repaired on
`codex/full-harness-delivery-2026-09-22`. This is a dated handoff, not a live status service.

## Integrated update

Implementation head `b30cee92` completes the local #85 filing path, #97 ordinary hunter path,
parent-enforced egress, optional task board, and bounded research record. The full kernel self-test
passed. Focused qualification passed for broker protocol (22/22), external network scope (10/10),
filing activation (16/16), record-review atomicity (11/11), engineering guidance (12/12), the
engagement-lock race, and the real-Docker joint hunter workflow.

The board remains optional because it did not meet its adoption gate. Unsupported-certainty framing
also remains rejected as a default: the bounded framing pilot observed no arm difference, and a
prior still supplies search direction rather than claim truth. External-effect recovery remains
receipt-bounded; the SDK replay result showed that restoring a pre-effect snapshot can duplicate an
effect whose receipt was lost.

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

## Remaining qualification boundaries

- **Hosted exact-head checks.** Local kernel and focused workflow checks pass at the implementation
  head. The repository conformance run and hosted CI are repeated after this status update; neither
  is claimed by this paragraph before its result is observed.
- **Real provider deferred.** Real-provider qualification was deferred by the user after the
  available Claude authentication path returned `403 oauth_not_allowed_for_organization`. The
  recorded request/response exercise used an owned fake provider. It establishes actual-client
  request shape and local protocol handling only.
- **Provider compatibility.** The integrated broker accepts the actual Claude Code request shape
  `POST /v1/messages?beta=true` against an owned fake provider. This establishes local client/proxy
  compatibility only; real Anthropic authentication and inference remain unqualified.
- **Managed-sandbox limitation.** Two POSIX session checks in the egress worktree encountered
  `PermissionError` when the managed CLI sandbox denied `os.killpg`. The Docker qualification was
  performed separately; the POSIX failures are retained as a test-environment limitation, not
  converted into a pass.

This delivery adds the bounded ordinary hunter path but no live-target authority or Zone-2 work.
The [task-board contract](../engineering/task-board-v1.md),
[filing scope](../engineering/filing-scope-2026-09-20.md) and [Docker work-queue contract](../agents/docker-work-queue.md)
remain the relevant source documents; this page does not supersede them.
