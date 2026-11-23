# ADR-0025: Ajar v3.4 Value Hill-Climbing, Unified Issue & Gadget Catalog, Fail-Closed Arm-3 Proof, and Bundle Sealing

- **Status:** Accepted (Active)
- **Date:** 2026-11-23
- **Builds On:** [ADR-0022](0022-ajar-v3-3-reactive-open-doors-and-phase-split.md), [ADR-0023](0023-agent-friendly-layered-architecture-and-dst.md), [ADR-0024](0024-modular-dag-zero-cycles-and-swarm-resilience.md)
- **Related Guide:** [Campaign Ladder & Horizon Roadmap](../campaigns-and-roadmap.md)

## Context

Forensic analysis of Ajar's 78.8h C systems campaign (`348.7` strict agent-hours, `355` sessions) exposed seven structural harness bottlenecks:

1. **Compute Misallocation & Discovery Stall:** Over `40%` of swarm compute went into ledger/package churn and premature multi-version production patch iterations (`PatchV1..V6`) while greenfield discovery received `< 5%` of compute and stalled after the first hour. `compute_task_salience` accidentally dropped `KIND_SALIENCE_FLOORS` when recomputing salience, `portfolio` claim dispatch sorted FIFO instead of by severity, and `ajar phase advance` permitted entering `remediate` before `G5` chain convergence finished.
2. **Disconnected Composable Pieces:** Capabilities, normal-code `trust_gadget` transitions, config-gated claims, unexplained anomalies, and Open Doors lived in separate tables without a unified search or backward sink-to-source call-cone slicer (`callee <- caller`) to surface indirect sinks (`Upload2Shell`-style write-to-loader bridges) and unvisited upstream callers.
3. **False-Pass Arm-3 & Step-Ablation Loophole:** In `ajar/repro_source.py` and `ajar/repro_compose.py`, Arm 3 (`micropatch + PoC`) and per-step chain ablation evaluated `not arm3_fired and not timed_out` without checking `_detect_build_or_env_failure` or `SIGKILL`/`OOM` (`exit 137`/`-9`). A broken micropatch that crashed or deleted a binary could pass Arm 3 if Arm 4 happened not to invoke that binary. Conversely, genuine micropatch syntax/guard mismatches burned `failed_repro_count` strikes even when Arm 1 + Arm 2 had already proven the PoC.
4. **Mid-Run Harness Drift & Split-Brain Closeout:** Agents edited `ajar/*.py` mid-campaign without cryptographic detection in `runs`, created ad-hoc `finding_corrections` rows that conflicted with `findings` and later `finding_calibrated` events, and lacked an explicit CLI command to close an operator-stopped run without claiming `all_gates_passed`.
5. **Symlink & Concurrent-Writer Package Churn:** Manual `SHA256SUMS` scripts repeatedly invalidated deliverable directories due to symlink roots, concurrent writers, and leaked local developer paths.
6. **Layer-0 Coordinator Prompt Bloat, Worker Collisions, & Passive Unicorn Gaps:** Hand-composed coordinator prompts bloated worker context, drifted into premature patching (`25.5%` in unsteered runs), collided on shared files/claims, and left 1-link Middle-Unicorn chain gaps passive in `ajar chain frontier` while greenfield discovery stalled after `stall_window` zero-yield tasks.
7. **Single-Island Monopoly, Disjunctive Percolation Noise, Blind Chain Retries, & Unannotated Guard Failures:** Under `--uncapped` (`cogs_cap_usd = 0.0`), the `25%` dry-surface token breaker was inactive so early stepping-stones could monopolize exploration on `1..2` subsystems; disjunctive `1`-of-$k$ tag intersections spawned false-positive multi-hop chain tasks while truncation hid late high-value `(forward_tip, backward_entry)` pairs; repeated `ajar chain propose` and `ajar claim reproduce` retries guessed inputs without line-level `@VISITED` / `@UNREACHED` feedback; and raw `event_id` progress checks reset stall counters on administrative events (`finding_calibrated`, `lead_vote_cast`, unverified `chain_proposed`).

## Decision

1. **Multi-Agent Expected-Value Lead Voting, Per-Root Plateau Breaker, Hard `hunt`-Phase Patch Firewall, & Frictionless `ajar init` Quote UX (`ajar lead`, `ajar phase`, `ajar init`, `ajar map --unvisited`):**
   - Add `lead_votes` (`LeadTargetKind`, `ajar lead {vote,rank,throttles}`, MCP `ajar_lead_vote` / `ajar_lead_rank`) computing `compute_lead_ev_formula` (`1..10` impact, plausibility, chainability, effort + multi-worker quorum bonus) and feeding consensus EV (`-15..+15`) directly into `compute_task_salience`.
   - Restore `KIND_SALIENCE_FLOORS` (`chain=75`, `reproduce=72`, `falsify=70`, `bridge=68`) in `compute_task_salience`, penalize post-reproduction non-chain churn on already-reproduced files via `compute_root_plateau_throttles` (`-35` after `>= 2` closed post-repro tasks unless a `ready` Open Door or `crown_jewel` is active), sort `portfolio` claims by severity, and add `ajar map --unvisited` (`scout_coverage_pct`, `unvisited_slices`).
   - Hard-fail `ajar patch verify` (and MCP `ajar_patch_verify`) plus `ajar swarm brief` on `kind='patch'` with `EXIT_GATE_BLOCKED` while `campaign_phase == 'hunt'`, and gate `ajar phase advance --to remediate|full` on `G5_anomalies_and_chains` (`0` unexplained anomalies, `0` unwaived `ready` doors, `0` nonterminal high-salience chains) and `0` open/leased `critical` hunt/chain/verify tasks unless `--force --notes <reason>` records an explicit operator `scope_authority` touch.
   - Add `--max-spend <usd>`, `--warn-above-usd <usd>` (`25.0` default), and `--yes` to `ajar init` so runs start in a single command with inline quote estimation, automatic COGS cap clamping, and non-blocking budget notices.
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
5. **Layer-0 Disjoint Swarm Wave Planner, Discovery-Stall Circuit Breaker, Middle-Unicorn Auto-Bridge, & Minimal Worker Dispatch Briefs (`ajar swarm {plan,brief}`):**
   - Add `plan_swarm_wave` (`ajar swarm plan [--workers N] [--no-enqueue] [--stall-window K]`, MCP `ajar_swarm_plan`) selecting `<= max_workers` open tasks disjoint on primary target file, `claim_id`, and `door_id` (unless `kind == 'chain'`), excluding `patch` tasks while `campaign_phase == 'hunt'`, annotating `falsify` tasks with `proposer_worker_id` (`must_differ_from_worker`), auto-enqueuing `<= 2` greenfield `investigate` tasks on unvisited `backslice` or PageRank slices when the last `stall_window` terminal tasks yielded `0` claims/primitives, and auto-enqueuing `<= 2` `salience=90` `bridge` tasks targeting the highest-scoring Crown-Jewel `unicorn_gaps`.
   - Add `build_worker_dispatch_brief` (`ajar swarm brief <task_id> [--worker <id>] [--raw]`, MCP `ajar_swarm_brief`) compiling a deterministic `<= 40`-line Layer-0 Markdown + JSON brief mapping `task.kind` to `skills/ajar-{map,investigate,falsify,reproduce,chain,patch,report}/SKILL.md`, emitting explicit phase guardrails, capping catalog context at `<= 3` neighbors, and raising `EXIT_GATE_BLOCKED` whenever `worker_id == proposer_worker_id` on `falsify` tasks.
6. **Conjunctive Hyperedge Percolation, `AH-PUCT` Abductive Cut-Lemma Scoring, & `H9_INVARIANT_SYMMETRY` (`ajar/chain_planner.py`, `ajar/epistemic_hooks.py`):**
   - Require full conjunctive subset satisfaction (`requires_tags <= state_tags` plus upstream guard satisfaction) in `detect_percolated_multi_hop_paths` so partial `1`-of-$k$ tag overlaps never emit false-positive `chain` tasks.
   - Rank all `(forward_tip, backward_entry)` `unicorn_gaps` in `compute_chain_frontier` via `ah_puct_score` ($Q + U$), combining Crown-Jewel impact weight $\cdot \gamma^{\hat{d}}$, `repomap_edges` $0/1/2$-hop call-graph proximity, materialized `repro_snapshots` bonus, and inverse `bridge` visit exploration prior to top-$K$ truncation.
   - Add `HookCode.H9_INVARIANT_SYMMETRY` (`max_leases=1`, mandatory `Kill Rule`), firing on guarded capabilities (`ajar primitive add --guarded-by`) and when `ajar primitive dry` closes an inner guard while `repomap_edges` exposes unaudited peer callers or sibling state writers.
7. **`QD-Islands` Subsystem Deme Firewall, Grounded Lyapunov Epistemic Potential $\Phi(t)$, & 2-Strike Chain-Probe Pivot (`ajar/store/util.py`, `ajar/db.py`, `ajar/hooks.py`, `ajar/repro_compose.py`):**
   - Add `compute_island_illumination` (`QD-Islands`) boosting unvisited subsystem islands (`+12` salience + anti-monopoly lease interleave in `lease_next_task` and `plan_swarm_wave` while global illumination `< 0.75`) and throttling over-mined islands (`-25` salience, `<= 55` cap when `explore_share > fair_share_cap` without a `ready` Open Door or recent Crown-Jewel progress).
   - Replace raw `event_id` progress checks in `ajar hook claude-stop` and `ajar loop` with Grounded Lyapunov epistemic potential $\Phi(t)$ (`compute_epistemic_potential`, `compute_epistemic_delta` surfaced in `ajar status` and `ajar pulse`), advancing $\Delta \Phi > 0$ strictly on verified `coverage_spans`, `certified_bindings`, `dry` guard closures, `primitives`, settled `claims`, woken `parked_doors`, `findings`/`chains`, or reached `crown_jewels`.
   - Enforce a 2-strike stagnation gate (`evaluate_chain_failure_streak`) on `ajar chain propose`: after `2` consecutive unverified attempts on the same step set or `door_id` since the last runtime probe, reject a 3rd blind retry (`EXIT_GATE_BLOCKED`) with a `fix_hint` directing the worker to run `ajar chain probe`, `ajar repro slice-probe`, or `ajar claim instrument`.
8. **Zero-Dependency `@VISITED` / `@UNREACHED` Source Slice Probe (`ajar/slice_probe.py`, `ajar/cli/repro.py`):**
   - Add `ajar repro slice-probe` (MCP `ajar_repro_slice_probe`) executing exploratory commands inside `repro/slot-<k>` with zero-dependency Python `sys.settrace` (chaining `repro/helpers/sitecustomize.py` loopback socket isolation first) or GCC `gcov --json-format`, annotating `@VISITED (hits=N)` vs `@UNREACHED` (`<-- FIRST_UNREACHED_AFTER_GUARD`), extracting ASan/UBSan/TSan/MSan crash frames, optionally recording `coverage_spans` (`--record-coverage`), and transitioning `needs_instrumentation` claims (`--claim`) cleanly back to `survived_falsify`.

## Quantitative Benchmark Summary (20-Seed 3-Way Wave-C Simulation)

`tests/dst/test_wave_c_benchmark.py` evaluates `N = 20` deterministic PRNG seeds (`1000..1019`) across a 12-island, 60-file systems repository (`uncapped_research`, `cogs_cap_usd = 0.0`, `stopping_criterion = 'crown-jewel'`):

| Metric (`N = 20` Seeds, 12-Island / 60-File Topology) | `v3.3-sim` | `v3.4-base` | `v3.4-wave-c` |
| --- | ---: | ---: | ---: |
| **Subsystem Illumination @ 16 Explore Leases** | `0.0833` (`8.3%`) | `0.5000` (`50.0%`) | **`1.0000` (`100.0%`)** |
| **Max Single-Island Explore Lease Share** | `1.0000` (`100.0%`) | `0.6875` (`68.8%`) | **`0.3125` (`31.25%`)** |
| **False-Positive Conjunctive Chain Tasks Spawned** | `1.0` | `1.0` | **`0.0`** |
| **True Middle-Unicorn `Recall@8` / `MRR`** | `0.00` / `0.00` | `0.00` / `0.00` | **`1.00` / `1.00`** |
| **Mean Explore Leases to Crown-Jewel Percolation** | `22.85` | `17.20` | **`8.10` (`-52.9%` vs `v3.4-base`)** |
| **False Progress Resets Across 25 Churn Events** | `25 / 25` | `25 / 25` | **`0 / 25` ($\Delta \Phi = 0.0$)** |

## Consequences

- **Positive:** Swarm compute illuminates all subsystem islands without `--uncapped` monopoly, ranks multi-hop Crown-Jewel bridges by conjunctive cut-lemma value (`AH-PUCT`), pivots blind chain/repro retries into `@VISITED`/`@UNREACHED` runtime probes, ignores administrative log churn via $\Phi(t)$, and prevents broken micropatches or tampered bundles from corrupting findings.
- **Negative / Costs:** Schema version advances to `340` (`_ensure_v34_schema` migrates `v3.1..v3.3` databases idempotently with `PRAGMA legacy_alter_table=ON/OFF`).

## Risks & Revisit Triggers

- **EV Vote Gaming by Noisy Workers:** Consensus EV caps single-worker salience shift to `±15` and weights multi-worker quorum (`voter_count`); revisit weights after the next two multi-hour engagements.
- **Over-Aggressive Root or Island Throttling:** `compute_root_plateau_throttles` and `compute_island_illumination` exempt files and islands with active `ready` Open Doors or recent `crown_jewel` progress while preserving `reproduce`/`falsify`/`bridge`/`chain` salience floors.
