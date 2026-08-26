# `long-runs/` — long-running goal prompts

Prompts for a multi-hour, multi-round portfolio run against one asset. The mechanics live in
`engine/multi-round-orchestration.md`; these files are the per-engagement front end to it.

| file | use it when |
|---|---|
| `long-run-v2-cdc.md` | **default.** Any long run. Fill the placeholders, delete the surface and idiom rows that do not apply. |
| `../goal-prompt-LONG-RUN.md` | the v1 generic prompt (420 lines). Superseded by v2; kept until v2 has run twice. |
| `reference/sources.md` | the source prompts, verbatim, so the adaptation stays auditable |

## Which source version is better

**The templated long form (Source C) beats the WordPress original (Source A)**, and the short form
(Source B) is a summary of C with nothing of its own. C wins on four things A lacks:

1. **Placeholders.** A makes you rewrite the prompt per target; C makes you fill five fields.
2. **A threat-model block** — "a finding is only valid if" — which maps directly onto gate **G3**,
   the only gate that has ever produced a substance block here
   (`docs/engineering/004-gate-block-audit.md`).
3. **Classify the target first, then justify each surface inclusion *and exclusion* in one line.**
   The exclusions are the half that gets skipped silently.
4. **A language-idiom layer on its own axis**, because those bugs come from how the language behaves
   rather than from the application's architecture. We had no equivalent.

A's only advantage is concreteness, and it is the concreteness of a CTF: a named target, a planted
bug, a flag at a known path. That does not survive contact with a real program.

## The two things we do not copy

**1. Never assert that a vulnerability exists.** Every source version opens by declaring one does.
That is sound for a planted-bug test and is a reward-hack here: a run told to expect a finding does
not terminate until it produces one, and on a clean codebase what it produces is fabricated.
`engine/multi-round-orchestration.md` §5 records this as the one change we made to the method, and it
is the reason our independently reviewed exhaustion verdicts are worth anything. **State the surface;
let the evidence decide.**

**2. The blanket ban on changelogs, CVE databases and patched-version diffs is wrong here.** It is
correct for a planted bug — the answer is in the diff — and backwards for VRP work, where a duplicate
report burns credibility with the same triage team. Novelty is a **gate**, not a shortcut, and
`skills/oracles/` holds an anchored fix-commit corpus built to be read.

The line we keep: read patches to learn the shape of a bug class; do not diff this target against a
patched version to locate its bug.

## What v2 adds beyond both

- The kernel preflight, first, before any recon. A kernel started mid-run is retroactively fatal.
- `unproven/` partials with `what_would_close_it`, and `ceiling-requests.md` for lanes blocked by
  authorization rather than by evidence.
- A stopping contract governed by the **computed work queue**. A blind round records that no new work
  was enqueued and supplies evidence to the final cold review; it never ends a run by itself.
- `budget-bounded` as a terminal state distinct from kernel-backed reviewed exhaustion.

## Before building on this

v2 is **unrun**. It is longer than the source prompts, and length is a cost: `docs/engineering/
003-roadmap.md` records that this harness holds ~3 MB of prose and that more prose has not changed
behaviour. The operator-local Q-02 record says the prompt ablation was **INCONCLUSIVE twice**, so we
still have no evidence that a longer prompt beats a short one. The portable repository deliberately
carries only its target-agnostic [decision-rule checkpoint](../../../../fixtures/preregistration/phase5-q02-prompt-ablation-portable.json),
not a copy of the engagement outcome. That checkpoint pins the complete local records opaquely and
does not independently establish their outcome.

Treat the surface and idiom tables as the part most likely to earn its length, and the prose around
them as the part to cut first if a run shows it is not read.
