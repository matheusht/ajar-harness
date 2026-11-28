---
name: ajar-run-autopsy
description: Post-mortem completed or aborted Ajar v3.6.2 runs across artifacts and transcripts using Deming Anti-Tampering, Bitter-Lesson discipline, and C3 verification audits.
---

# Ajar Run Autopsy (`v3.6.2`)

Use this skill after any completed, partial, dry, or aborted audit run to diagnose harness defects, wasted spend, silent blind spots, and verification leaks—without knee-jerk tampering.

## 1. Ground-Truth Artifact Surface

Reconstruct what actually happened from primary artifacts before reading summaries or prose claims:

- **Run & Worker State:** `.ajar/STATUS.md`, `.ajar/workers/W<id>/notes.md`, `.ajar/REALITY.md` (PageRank production map).
- **Stigmergic Memory:** `.ajar/whiteboard.sqlite` (primary SQLite WAL + FTS5 store: `events`, `claims`, `events_fts`), `.ajar/WHITEBOARD.md` (`<=8KB` snapshot), and `.ajar/events.jsonl` (legacy/audit mirror).
- **Build & Proof Chain:** `.ajar/build.sh`, `.ajar/build_recipe.json`, `.ajar/candidates.jsonl`, `.ajar/verdicts.jsonl`.
- **Host Transcripts:** External agent logs (`transcript.jsonl`, Claude, Codex, Pi, or SWE-1 session logs) for tool loops, retries, and context drops.

```bash
sqlite3 -readonly .ajar/whiteboard.sqlite "SELECT kind, count(*) FROM events GROUP BY kind ORDER BY 2 DESC;"
sqlite3 -readonly .ajar/whiteboard.sqlite "SELECT target, count(*) FROM events WHERE kind='claim' GROUP BY target HAVING count(*)>1;"
```

Every autopsy claim must cite an artifact path, event `seq`, candidate ID, or transcript turn—never memory or intuition.

## 2. Attribution Firewall: Model/Env vs. Harness

Before blaming `ajar-harness`, separate external noise from harness architecture:

- **Provider / Model Limits:** Rate limits, provider outages, cross-family critic timeouts, or silent context truncation (e.g., high-concurrency free-plan model context drops) are **env/model faults**, not harness bugs.
- **Sandbox / Target Host Friction:** Missing toolchains, flaky upstream networks, or container OOMs belong in environment notes unless `autobuild.py` or `verify.py` hid or misclassified the failure.
- **Genuine Harness Flaws:** Only attribute to `ajar-harness` when Ring-0/Ring-1 code, prompts, whiteboard coordination, or `verify.py` gating caused avoidable blindness, wasted turns, or bad verdicts under healthy model/env conditions.

## 3. Four Ajar Security Autopsy Axes

Audit every run—including "green" runs that produced `C3` advisories—across four axes:

1. **Unit Economics & Yield:** Compute `$/C3` verified finding, inspect the `CostMeter` burn curve and `92%` drain timing (did exploration freeze too late or starve `ajar verify`?), and compare spend on killed vs. promoted candidates.
2. **Kill-Gate & Stagnation Timing:** Pinpoint the turn when upstream `HEAD` status, build-profile validity, or the write-primitive vs. read-only impact ceiling became knowable. Quantify sunk-cost turns burned after that ceiling, plus Build Doctor (`autobuild.py`) compile friction.
3. **Silent Blind Spots (Even on "Green" Runs):** Check for high-PageRank production slices in `.ajar/REALITY.md` never visited, duplicate worker claims or colliding probes, prose-only `DEAD_END`s lacking execution evidence that poisoned recall, crash-frame-only bandaid patches instead of root-cause fixes, and orphaned `WISH` vs. `EFFECT` records that never joined.
4. **Verification Integrity (`verify.py` 5-Stage `C3` Drop-Off):** Tabulate candidate attrition across Stage 1 (`3x` attributed fail), Stage 2 (fuzzy patch apply), Stage 3 (mandatory post-patch rebuild), Stage 4 (`3x` pass + upstream `test_cmd`), and Stage 5 (Blind Cross-Family Critic). Flag static-vs-dynamic inversions, missing non-vacuity/control checks, and citation or span provenance drift (`SpanTracker`).

## 4. Deming Anti-Tampering & Bitter-Lesson Gate

Classify every autopsy finding into exactly one bucket—defaulting to restraint over churn:

| Classification | Criteria & Required Action |
| --- | --- |
| **`HARNESS FIX`** | Systemic, recurring `ajar-harness` defect (seen across runs or provably structural) that a smarter model alone will not fix. Specify the exact Ring-0/Ring-1 module and minimal diff. |
| **`METHOD GAP`** | Repeatable audit methodology miss (e.g., skipping sibling routes, premature `DEAD_END`, weak control check). Propose a tight skill or prompt clarification, not new Python machinery. |
| **`TEST FIRST`** | Plausible hypothesis lacking reproduction or rent proof. Specify a local Phase-0 probe (`ajar bench --phase0`), regression test, or Leave-One-Out ablation (`ajar run ... --disable-<module>`) before touching code. |
| **`IGNORE (ONE-OFF NOISE)`** | Single-run variance, target quirk, provider/model hiccup, or problem that the next frontier model generation will absorb naturally. Do **not** tamper. |

**Bitter-Lesson & Earned-Mass Rules:**
- Reject any fix that recreates `v3.4` complexity bloat, rigid per-language heuristics, or brittle checklists.
- Whenever a Ring-1 organ (`repomap`, `whiteboard`, `epistemic`, `chain-weaver`, `autobuild`, `swarm`, `microfuzz`) burned tokens or latency without moving `C3` yield, propose a `--disable-<module>` Leave-One-Out rent ablation—deletion beats tuning.

## 5. Strict Read-Only & Confidentiality Default

- **Read-Only Autopsy:** Never silently edit harness code, skills, or target repositories during an autopsy; output a compact diagnostic report with evidence citations and ranked next actions for founder review.
- **Zero Leakage & Disclosure Gate:** Never exfiltrate raw target findings, PoCs, credentials, or developer home paths, and never submit advisories or contact vendors (`AGENTS.md` Boundaries #3–#4).

## 6. Autopsy Report Output Shape

Emit a compact 5-part report aligned with Deming Anti-Tampering:

1. **Run Snapshot:** Target, commit, profile, spend, `C3` yield, `$/C3`, and Model/Env vs. Harness attribution verdict.
2. **Spend & 5-Stage `C3` Funnel:** `CostMeter` curve, `92%` drain timing, and Stage 1–5 attrition counts from `.ajar/verdicts.jsonl`.
3. **Kill-Gate & Blind-Spot Audit:** Sunk-cost turns after ceiling, Build Doctor friction, unvisited slices, prose-only `DEAD_END`s, bandaid patches, and orphaned `WISH`/`EFFECT` pairs with exact citations.
4. **Deming Action Table:** Each finding classified strictly as `HARNESS FIX`, `METHOD GAP`, `TEST FIRST`, or `IGNORE (ONE-OFF NOISE)`.
5. **Rent & Ablation Proposals:** Any Ring-1 organ recommended for `--disable-<module>` Leave-One-Out testing or deletion.
