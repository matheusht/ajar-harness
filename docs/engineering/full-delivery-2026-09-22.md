# Governed hunter delivery and research evaluation

Status: local implementation and qualification complete at implementation head `b30cee92`; hosted
CI and real-provider qualification remain separate. Authorized by the user's 2026-09-22 request for
the full outcomes of #85, #97, external destination enforcement, and message-board follow-through.
Starting point: `c139c660f9563e5daef568f9cb53207fb4395372`.

## Intent and boundaries

Complete the ordinary evidence-producing agent workflow, remove unnecessary manual transfers,
and evaluate whether stronger persistence or task-local notices earn their cost. Preserve the
existing scope, evidence, independent-review, redaction, and escalation boundaries.

Implementation uses Sol Medium; planning and acceptance review use Astra High. No Ultra/Max,
heavy skill workflow, new execution kernel, global knowledge service, or unrelated WIP import.
Real target engagements and Zone-2 artifacts are outside this engineering/evaluation work.
Frozen communication/recovery v1 packets remain unchanged; their illustrative results are not
measurements. Irreversible external actions require confirmation.

## Delivery acceptance

- **#85:** one signed activation path; retained applicable evidence gates; explicit privilege,
  severity and impact-state provenance; no legacy-version bypass; negative-state filing; preserved
  historical replay; retired legacy production writer; interruption and retry qualification.
- **#97:** ordinary hypothesis → exactly one admitted hunter attempt → adjudication; deterministic
  current-only view; exact safe methodology and target-file allowlist; inaccessible prior verdicts,
  gold and unrelated records; principal/view/state binding; safe inspection; lifecycle cleanup.
- **Egress:** enforcement outside the model; approved destination/operation works; denied requests,
  redirect/DNS/host/direct-socket bypasses cannot reach sinks; provider access cannot become an
  unrestricted target channel; scope and parent audit records remain outside worker control.
- **Board:** bounded task-local append-only notices; authenticated roles; independent first
  observations precede sharing; source revisions and corrections remain attributable; notices
  confer no evidence verdict or execution permission; actual post/read workflow exercised.
- **Integration:** the complete synthetic workflow reaches authenticated activation through the
  production seams; meaningful rejection/recovery cases run with saved inputs and results.

For each code slice, enumerate failure modes and write the workflow checks before implementation.
Run relevant existing regressions and exact integrated-head checks. Record structural/mocked,
real-Docker, actual-model and provider qualification separately; no substitution of one for another.

## Evaluation questions

1. **Framing:** neutral instructions versus evidence-grounded persistence versus unsupported
   certainty on positive, patched and deceptive-near-miss versions of a small benign repository.
   Keep model/tools/budget constant; measure valid positives, false confirmations, supported
   negative conclusions, uncertainty, effort and operator intervention separately.
2. **Communication:** serial versus capable direct handoff versus direct handoff plus the board,
   using complete, complementary and late-correction workshop sources. Match source release,
   total resources and workers; capture actual independent observations, messages and finals.
   Equal quality at equal or lower effort favors the simpler arrangement.
3. **Recovery:** exercise baseline and pinned SDK interfaces for late correction, cooperative
   pause and lost receipt. Capture actual adapter arguments and interface behavior; a scripted
   expectation replay cannot count as implementation qualification.

Freeze each new run's configuration, source/reference hashes, schedules, resource ceilings,
grading rules and stop conditions before candidate outputs. Keep unsuccessful assignments and
unknown measurements. Separate blinded grading from workers. Measure model inference rather
than claiming synthetic replay establishes agent effectiveness.

## Evidence ledger

| Work | State | Evidence |
| --- | --- | --- |
| Prior #99 delivery | Merged; main CI passed | PR #115, main `c139c660` |
| #85 | Implemented and locally qualified | One signed v3 activation path; retired legacy mutation; exact interrupted-write retry; unrelated orphan rejection with unchanged ledger |
| #97 | Implemented and locally qualified | One running hypothesis reached one brokered attempt and adjudication through a compiled current-only hunter view |
| Egress | Implemented and locally qualified | Parent-enforced provider and signed target-fetch paths; Docker negative sinks observed zero denied requests |
| Board and new evaluations | Implemented as optional; bounded studies complete | Board did not meet its default-adoption gate; framing showed no arm difference at the fixed ceiling; SDK replay duplicated an unreceipted effect |

The original dirty checkout is preserved. The integration worktree is `/tmp/redteam-harness-full`.
The full kernel self-test passed. Focused results were broker protocol 22/22, external network 10/10,
filing activation 16/16, record-review atomicity 11/11, engineering guidance 12/12, engagement-lock
race pass, and the real-Docker joint hunter workflow pass. Canonical review staging retained
5,466.604 ms of its unchanged 10,000 ms prewrite budget. The full repository conformance run and
hosted CI are repeated at the final documentation head before delivery.

## Environment observations

- Claude Code 2.1.278 reported an authenticated subscription, but a no-tools configuration probe
  returned HTTP 403 `oauth_not_allowed_for_organization`, zero reported model tokens and no model
  result. An authorized local API key is needed for real-provider qualification of that backend.
- Codex CLI 0.155.1 accepted `gpt-5.6-sol` with medium effort and returned `READY` in fresh probes.
  These were configuration checks, not study assignments. The tool-disabled settings follow the
  [official configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference).
  The exact backend weights and full internal system context are not independently observed.
- The pinned recovery SDK `f1f35031d364f9f0d8e94dda0853c92abefdccff` was checked out separately at
  `/tmp/redteam-recovery-sdk`; `uv sync --frozen --no-dev` succeeded and its public offline
  Agent/Runner/RunState/ScriptedModel imports work. No production dependency was added.
- Existing Docker image
  `golang@sha256:699337d620559a59b4a2bb298ad59611e535d2ee755a34cf2d2a98f37578dc80`
  runs `/usr/bin/python3` (3.13.5) without networking, capabilities or a writable root. This is a
  usable deterministic qualification fixture, not a qualified real-model image.
