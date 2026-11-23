# ADR-0025: Ajar v3.4 Value Hill-Climbing, Unified Issue & Gadget Catalog, Fail-Closed Arm-3 Proof, and Bundle Sealing

- **Status:** Accepted (Active)
- **Date:** 2026-11-23
- **Builds On:** [ADR-0022](0022-ajar-v3-3-reactive-open-doors-and-phase-split.md), [ADR-0023](0023-agent-friendly-layered-architecture-and-dst.md), [ADR-0024](0024-modular-dag-zero-cycles-and-swarm-resilience.md)

## Context

Forensic analysis of Ajar's 78.8-hour (`348.7` strict agent-hour, `355`-session) source campaign on upstream Git exposed five structural harness bottlenecks:

1. **Compute Misallocation & Discovery Stall:** Over `40%` of swarm compute went into ledger/package churn and premature multi-version production patch iterations (`PatchV1..V6`) while greenfield discovery received `< 5%` of compute and stalled after the first hour. `compute_task_salience` accidentally dropped `KIND_SALIENCE_FLOORS` when recomputing salience, `portfolio` claim dispatch sorted FIFO instead of by severity, and `ajar phase advance` permitted entering `remediate` before `G5` chain convergence finished.
2. **Disconnected Composable Pieces:** Capabilities, normal-code `trust_gadget` transitions, config-gated claims, unexplained anomalies, and Open Doors lived in separate tables without a unified search or backward sink-to-source call-cone slicer (`callee <- caller`) to surface indirect sinks (`Upload2Shell`-style write-to-loader bridges) and unvisited upstream callers.
3. **False-Pass Arm-3 & Step-Ablation Loophole:** In `ajar/repro_source.py` and `ajar/repro_compose.py`, Arm 3 (`micropatch + PoC`) and per-step chain ablation evaluated `not arm3_fired and not timed_out` without checking `_detect_build_or_env_failure` or `SIGKILL`/`OOM` (`exit 137`/`-9`). A broken micropatch that crashed or deleted a binary could pass Arm 3 if Arm 4 happened not to invoke that binary. Conversely, genuine micropatch syntax/guard mismatches burned `failed_repro_count` strikes even when Arm 1 + Arm 2 had already proven the PoC.
4. **Mid-Run Harness Drift & Split-Brain Closeout:** Agents edited `ajar/*.py` mid-campaign without cryptographic detection in `runs`, created ad-hoc `finding_corrections` rows that conflicted with `findings` and later `finding_calibrated` events, and lacked an explicit CLI command to close an operator-stopped run without claiming `all_gates_passed`.
5. **Symlink & Concurrent-Writer Package Churn:** Manual `SHA256SUMS` scripts repeatedly invalidated deliverable directories due to symlink roots, concurrent writers, and leaked local developer paths.

## Decision

1. **Multi-Agent Expected-Value Lead Voting, Per-Root Plateau Breaker, & Phase Gate (`ajar lead`, `ajar phase`, `ajar map --unvisited`):**
   - Add `lead_votes` (`LeadTargetKind`, `ajar lead {vote,rank,throttles}`, MCP `ajar_lead_vote` / `ajar_lead_rank`) computing `compute_lead_ev_formula` (`1..10` impact, plausibility, chainability, effort + multi-worker quorum bonus) and feeding consensus EV (`-15..+15`) directly into `compute_task_salience`.
   - Restore `KIND_SALIENCE_FLOORS` (`chain=75`, `reproduce=72`, `falsify=70`, `bridge=68`) in `compute_task_salience`, penalize post-reproduction non-chain churn on already-reproduced files via `compute_root_plateau_throttles` (`-35` after `>= 2` closed post-repro tasks unless a `ready` Open Door or `crown_jewel` is active), sort `portfolio` claims by severity, and add `ajar map --unvisited` (`scout_coverage_pct`, `unvisited_slices`).
   - Gate `ajar phase advance --to remediate|full` on `G5_anomalies_and_chains` (`0` unexplained anomalies, `0` unwaived `ready` doors, `0` nonterminal high-salience chains) and `0` open/leased `critical` hunt/chain/verify tasks unless `--force --notes <reason>` records an explicit operator `scope_authority` touch.
2. **Unified Issue & Gadget Catalog, Backward Sink Slicing, & Modular Backup-Slot Chains (`ajar/catalog.py`, `ajar chain propose --backup-step`):**
   - Add `ajar/catalog.py` (`ajar catalog {search,backslice}`, MCP `ajar_catalog_search` / `ajar_catalog_backslice`) indexing findings, capabilities, `trust_gadget` transitions, candidate claims, anomalies, and Open Doors, synthesizing 1-hop composable pairs and walking `repomap_edges` backward (`callee <- caller`) up to `6` hops from any Crown Jewel, Open Door, locus, or symbol while highlighting `unvisited_caller_files`.
   - Keep `surfaces` active alongside `crown_jewels` in `compute_chain_frontier` and rank 1-link `crown_jewel` `unicorn_gaps` first.
   - Add `--backup-step <primary_id>:<backup_id>` (`chains.backup_steps_json`, `$AJAR_ACTIVE_STEPS`, `$AJAR_STEP_SWAPS`) to `ajar chain propose` so modular stage backups swap automatically when a primary step fails, followed by full benign control and per-step causal ablation on the winning step set.
   - Add `--same-root-of` on `ajar claim propose`, `ajar claim duplicate`, `--declared-steps` / `--realism-tier` on `ajar finding calibrate`, `ajar chain calibrate`, and `distinct_root_causes_count` in `ajar status` and `ajar report`.
3. **Fail-Closed Arm-3 / Step-Ablation Proof & Zero-Strike `micropatch_error` Separation:**
   - Require Arm 3 (`ajar claim reproduce`) and per-step chain ablation (`ajar chain propose`) to pass `not _detect_build_or_env_failure(...)` and `exit_code not in (-9, 137)` in addition to non-firing oracle evaluation.
   - Classify Arm-3/Arm-4 failures after passing Arm 1 + Arm 2 as `error_class = "micropatch_error"` (`0` strikes, `poc_proven = True`), fail closed when `--save-post-state` is missing on disk, support `--max-changed-lines`, support `ajar chain probe --build-cmd`, and fix `swarm.py` non-repro `regression_tdd` fallback prompts so `investigate`/`falsify` workers audit boundary invariants rather than authoring patches.
4. **Harness Code-Hash Binding, Timestamp-Ordered Correction Projection, `ajar close`, & `ajar bundle {seal,verify}`:**
   - Bind `runs.harness_sha256 = compute_harness_code_sha256()` on `ajar init` and surface `harness_modified_mid_run` in `ajar doctor --run` and `ajar report`.
   - Project `finding_corrections` deterministically via `apply_latest_finding_corrections` (superseded by newer `finding_calibrated` events) across `ajar report`, `ajar finding list`, and `ajar export-graph`.
   - Add `ajar close --reason <stopped_by_operator|window_reached|superseded> --notes <text>` for honest non-gate run closeout, and `ajar bundle {seal,verify}` enforcing `os.lstat` symlink rejection, two-snapshot writer stability, secret + local-path archive hygiene scanning, and atomic `BUNDLE-MANIFEST.json` + `SEAL.sha256` verification.

## Consequences

- **Positive:** Swarm compute concentrates on unvisited slices, consensus high-EV leads, and 1-link Crown-Jewel chains instead of premature patching or ledger churn; broken micropatches can neither false-pass Arm 3 nor burn PoC strikes; mid-run harness edits and tampered/dirty deliverable bundles are caught deterministically.
- **Negative / Costs:** Schema version advances to `340` (`_ensure_v34_schema` migrates `v3.1..v3.3` databases idempotently with `PRAGMA legacy_alter_table=ON/OFF`).

## Risks & Revisit Triggers

- **EV Vote Gaming by Noisy Workers:** Consensus EV caps single-worker salience shift to `±15` and weights multi-worker quorum (`voter_count`); revisit weights after the next two multi-hour engagements.
- **Over-Aggressive Root Plateau Throttling:** `compute_root_plateau_throttles` exempts files with active `ready` Open Doors or `crown_jewel` findings and preserves `reproduce`/`falsify`/`bridge`/`chain` salience floors.
