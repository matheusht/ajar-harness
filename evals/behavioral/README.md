# evals/behavioral/ — blind, broker-mediated, paired behavioral evaluation (Phase 10 / 10F / 10G)

Where technique candidates earn a verdict from **behavior**, not provenance. A card-guided researcher
chooses probes and adjudicates on hermetic episodes, so the technique wording can change outcomes — the
thing Phases 2–9 could not measure (the frozen scorers don't read technique cards). Phase 10F/10G made
this boundary trustworthy.

## The integrity boundary (load-bearing)

```
EVALUATOR process (holds gold, owns the BROKER)        RESEARCHER (blind, mediated)
  episode { signal, contaminated, gold }                view { card, task, schema, budget }
  broker executes probes, logs every event   <-------- requests one action per turn (probe | final)
  broker returns ONLY a mediated response     -------->  adjudicates from RESPONSES; its claims are advisory
  broker adjudicates coverage/FDR from its OWN event log
```

- **The broker is authoritative.** It decides which probes executed, the target responses, the
  controls, the fresh-session replay, the evidence refs, and the model/target call + token + elapsed
  ledger. A `confirmed` counts only when the broker's event log proves every oracle requirement.
  Missing, invented, duplicated, or out-of-budget events block or downgrade — the model cannot
  self-report that a control or replay happened.
- **Capability blindness — a transport boundary, not a security sandbox.** The researcher receives only
  the serialized view + mediated responses; the `model` adapter runs as a subprocess in an empty scratch
  cwd with a scrubbed env, and the action vocabulary has no file-read. This bounds the contract and
  reduces accidental leakage, but a scrubbed env + empty cwd do **not** prevent a hostile process from
  reading absolute filesystem paths or using the network. Before any real-model qualification, run the
  researcher under OS-level isolation or a remote, capability-limited model service with no local
  filesystem access (see Decision 0003). `assert_blind()` remains a defense-in-depth payload check.

## Metric boundary

- **Routing qualification is a MEASURED protected capability** (`run-qualification`), a hard gate — not
  counted as coverage, never hardcoded true.
- **Coverage** = hermetic episodes the broker confirms under the full oracle (positive class, final
  `confirmed`, the required controls actually executed, controls clean, replay stable).
- **False-discovery** = any non-positive episode confirmed — a hard veto.
- **Cost** is broker-accounted. A `fake`/simulator cost win can never authorize promotion.

## Canonical gating + immutable runs (10F) — authoritative measured boundary (10H0)

Every candidate passes the canonical campaign/candidate contract gate (`check-campaign.py`) as a fast
**preflight**, but authorization is **measured, not parsed** (Phase 10H0 / Decision 0004): the diff is
applied with `git apply --index` in an isolated detached worktree at committed HEAD, and the resulting
STAGED tree is the authority — `declared == actual` paths, mutable-allowlist membership, regular-file
type, the baseline/non-baseline tree rule, and trusted conformance. This evaluator does not reimplement
apply/gating; it shares the one measured result (`apply-candidate-eval.materialize_candidate`), and each
candidate's run row pins the `materialization` summary (verdict + base/candidate tree ids + actual
paths). Eligibility flags (`conformance_passed`, `budget_unchanged`, `single_mutation`,
`evidence_contract_complete`) and the protected routing capability are measured, never hardcoded. No
final `allow` is ever derived from preflight alone. Each invocation writes an immutable
`runs/<run-id>/{run-manifest.json,report.json,report.md,events.jsonl}` pinning campaign/candidate/card/
episode/scorer/adapter hashes, backend/model/config, seeds, budgets, timestamps, and status. A skipped
or failed run never overwrites a completed one.

Incumbent and candidate run **paired** in a primary + two fresh sessions with recorded anonymized A/B
order; a hermetic `allow` requires strict 3/3 reproduction.

## Episodes

`episodes/{task-reframing,decomposition}.json` — positive / held / refuted / contamination / control.
The `task` is a neutral surface observation (the only scenario text the researcher sees);
`signal_available` / `contaminated` / `class` / `gold_verdict` are evaluator-only. Contamination is the
discriminator: only a researcher that runs the negative control + fresh replay catches it; a card that
drops them (or overclaims) confirms it → FDR → block.

## Tools

- `tools/run-behavioral-eval.py` — the broker + driver. `--backend fake` (default, CI control, cannot
  promote) or `--backend model` (provider-neutral subprocess adapter; unavailable → recorded `skipped`,
  NON-SUCCESS).
- `tools/researcher_adapter.py` — provider-neutral researcher contract: strict action/final schemas,
  bounded malformed-output retries, jailed subprocess, usage accounting, `ModelUnavailable` on no command.
- `tools/fake-researcher-cli.py` — deterministic CLI implementing the wire contract (CI tests the
  subprocess protocol without credentials).
- `tools/build-behavioral-campaign.py` — regenerates the canonical campaign deterministically from HEAD.

```
python3 tools/build-behavioral-campaign.py
python3 tools/run-behavioral-eval.py --campaign evals/behavioral/campaigns/behavioral-canonical-v24-2026-10-02/campaign-manifest.json
python3 tools/run-behavioral-eval.py --self-test
```

## Canonical campaign: `behavioral-canonical-v24-2026-10-02`

Revision 24 preserves earlier evidence while pinning no-follow reads for intervention ledgers, framing-probe packets, false-discovery and
adversarial evaluator corpora, tool-family manifests and fixtures, finding fixtures, capability sources, cards,
oracles, and casebooks.
It keeps candidate definitions and technique patches
unchanged. Earlier revisions remain immutable history rather than being re-pinned. Revision 24 has no executed
candidate run or efficacy claim.
Future changes to a frozen input require another explicit revision; do not refresh this pin in place.

### Historical revision 23

Revision 23 pinned no-follow framing-probe and evaluator corpus reads alongside tool-family, finding, capability,
card, oracle, and casebook scans. Revision 24 supersedes it after intervention ledger reads also began rejecting
symlink and special-file inputs. Its manifest and candidate artifacts remain unchanged, with no executed candidate run or efficacy claim.

### Historical revision 22

Revision 22 pinned no-follow evaluator, tool-family, finding, capability, card, oracle, and casebook reads.
Revision 23 supersedes it after framing-probe packet reads also began rejecting symlink and special-file inputs.
Its manifest and candidate artifacts remain unchanged, with no executed candidate run or efficacy claim.

### Historical revision 21

Revision 21 pinned no-follow tool-family manifest and fixture reads alongside finding, capability, card, oracle, and
casebook scans. Revision 22 supersedes it after false-discovery and adversarial evaluator corpora also began rejecting
symlink and special-file inputs. Its manifest and candidate artifacts remain unchanged, with no executed candidate run or efficacy claim.

### Historical revision 20

Revision 20 pinned no-follow finding-fixture and capability sources alongside card, oracle, and casebook scans.
Revision 21 supersedes it after tool-family authority manifests and negative fixtures also began rejecting symlink
and special-file inputs. Its manifest and candidate artifacts remain unchanged, with no executed candidate run or efficacy claim.

### Historical revision 19

Revision 19 pinned no-follow capability registry, class, and negative-fixture reads alongside card, oracle, and
casebook scans. Revision 20 supersedes it after the finding-fixture corpus also began rejecting unsafe symlink and
special-file inputs. Its manifest and candidate artifacts remain unchanged, with no executed candidate run or efficacy claim.

### Historical revision 18

Revision 18 pinned no-follow capability registry and class reads alongside card, oracle, and casebook scans.
Revision 19 supersedes it after the capability negative-fixture corpus also began rejecting symlink and special-file
inputs. Its manifest and candidate artifacts remain unchanged, with no executed candidate run or efficacy claim.

### Historical revision 17

Revision 17 pinned no-follow card, oracle, and casebook reads. Revision 18 supersedes it after capability registry
and class scans also began rejecting symlink and special-file inputs. Its manifest and candidate artifacts remain
unchanged, with no executed candidate run or efficacy claim.

### Historical revision 16

Revision 16 pinned fail-closed oracle-card reads in the conformance checker. Revision 17 supersedes it after card
and casebook scans also began rejecting symlink and special-file inputs. Its manifest and candidate artifacts
remain unchanged, with no executed candidate run or efficacy claim.

### Historical revision 15

Revision 15 pinned shared regular-file reads and the holdout/conformance scanners' safe handling of symlinks and
non-regular files. Revision 16 supersedes it after oracle-card reads began rejecting symlinks and special files.
Its manifest and candidate artifacts remain unchanged, with no executed candidate run or efficacy claim.

### Historical revision 14

Revision 14 pinned the conformance secret scanner's non-regular-file and symlink handling. Revision 15
supersedes it after the scanner reused the shared regular-file reader with no-follow support. Its manifest and
candidate artifacts remain unchanged, with no executed candidate run or efficacy claim.

### Historical revision 13

Revision 13 pinned candidate-manifest identity checks in the shared loader and behavioral runner. Revision 14
supersedes it after the conformance scanner began refusing symlinks and non-regular inputs. Its manifest and
candidate artifacts remain unchanged, with no executed candidate run or efficacy claim.

### Historical revision 12

Revision 12 froze canonical campaign-path resolution for candidate manifest paths. Revision 13 supersedes
it after the shared loader began requiring the JSON candidate_id to match the directory/entry ID. Its
manifest and candidate artifacts remain unchanged, with no executed candidate run or efficacy claim.

### Historical revision 11

Revision 11 froze campaign-confined candidate manifest paths in the behavioral evaluator. Revision 12
supersedes it after the shared path guard began canonicalizing the campaign path before resolving the
candidate directory. Its manifest and candidate artifacts remain unchanged, with no executed candidate run
or efficacy claim.

### Historical revision 10

Revision 10 froze repository-confined candidate artifact paths in preflight, materialization, and behavioral
evaluation. Revision 11 supersedes it after candidate manifest paths were confined to their campaign and
candidate ID. Its manifest and candidate artifacts remain unchanged, with no executed candidate run or
efficacy claim.

### Historical revision 9

Revision 9 froze candidate-ID path validation in the campaign gate. Revision 10 supersedes it after diff,
evidence, and frozen-input paths were constrained to repository-local files at both preflight and measured
materialization. Its manifest and candidate artifacts remain unchanged, with no executed candidate run or
efficacy claim.

### Historical revision 8

Revision 8 froze the campaign gate and regular-file reader after invalid UTF-8 patches were made to fail
closed. Revision 9 supersedes it after candidate IDs were constrained to safe path components for
candidate artifact paths. Its manifest and candidate artifacts remain unchanged, with no executed candidate
run or efficacy claim.

### Historical revision 7

Revision 7 froze the gate after patch-path parsing switched to Git's NUL-delimited numstat output.
Revision 8 supersedes it after the gate began rejecting invalid UTF-8 patches without a traceback.
Its manifest and candidate artifacts remain unchanged, with no executed candidate run or efficacy claim.

### Historical revision 6

Revision 6 froze the gate after it began treating frozen input paths as immutable. Revision 7
supersedes it after the gate learned to preserve legal filenames containing arrow delimiters. Its
manifest and candidate artifacts remain unchanged, with no executed candidate run or efficacy claim.

### Historical revision 5

Revision 5 froze the campaign gate and its regular-file reader. Revision 6 supersedes it after the
gate began treating frozen input paths as immutable. Its manifest and candidate artifacts remain
unchanged, with no executed candidate run or efficacy claim.

### Historical revision 4

Revision 4 preserved revision 3 and froze the conformance checker after queue and engineering-guidance
changes. It has no executed candidate run or efficacy claim. Its manifest and candidate artifacts are
preserved; the current gate is revision 10.

### Historical revision 3

Revision 3 preserves the revision-2 candidate set and rotates only the frozen conformance-checker pin
after Decision 0005 introduced approved full Draft 2020-12 record validation. Revision 2 and its runs
remain immutable historical evidence; no old result is re-pinned. Revision 3 has no new efficacy claim.

The revision-2 canonical campaign + candidate manifests + real diffs produced this historical
`fake`-backend result (`runs/fake-completed-*`):
no-op `cand-baseline` → **probe** (a no-op can never `allow`); `cand-efficient-task-reframing` →
**allow** by broker-measured cost cut (non-promotable for the fake backend); `cand-decomposition` →
**probe**; `cand-degraded` (test fixture, promotion-excluded) → **block** (confirms contamination →
FDR); `cand-invalid-immutable` → **block** at the canonical gate (touches frozen gold).

## Phase 10G/10I — real-model qualification status: COMPLETED

The adapter contract + deterministic fake adapter + protocol tests were complete in 10G; the earlier
`runs/model-skipped-*` honestly recorded a SKIP when no backend was configured. **Phase 10I qualified a
real model.** A local, capability-limited backend (ollama `qwen3:8b`) was driven through the provider-
neutral subprocess adapter via `tools/ollama-researcher-cli.py` — a thin bridge that talks only to
`http://localhost:11434` over loopback (no credentials, no external egress) and sees only the blind
mediated view. As the adapter notes, the scrubbed env + empty cwd is a **transport boundary, not a kernel
sandbox**; a local model is used precisely because it needs no API key and makes no outbound provider
call. The `runs/model-completed-*` run records the blind, paired, 3/3 result:

- incumbent disciplined: **coverage 1, FDR 0** on both techniques (the model runs core + negative_control
  + replay and adjudicates from broker responses);
- no-op `cand-baseline` → **probe** (a no-op never becomes a win);
- degraded card → **FDR 4 → block** (the model follows the card's “skip the control / always confirm”
  and the FDR veto fires);
- `cand-invalid-immutable` → **block** at the measured materialization gate;
- every candidate **3/3 replay-stable** (temperature 0 + seeded);
- the model's `confirmed` claims granted **no** coverage without matching broker events.

The run is a real signal, not a simulator result; the manifest pins a **redacted** backend command
(program + sha256, never raw args). Nothing promotes automatically. Before a higher-trust qualification
(e.g. one that gates promotion), run the researcher under OS-level isolation, not just the transport
boundary (see Decision 0004 / 0003).
