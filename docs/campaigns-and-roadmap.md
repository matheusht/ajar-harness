# Ajar Campaign Ladder & Horizon Roadmap (`v3.4` -> `v3.5`)

This document explains why **Ajar v3.4** exists, defines the **3-Tier Campaign Feedback-Loop Ladder** used to evaluate engine changes with fast `Keep / Simplify / Delete` discipline, and outlines the **Ajar v3.5** technical roadmap across `Platform`, `Code`, `Fixes`, `Security reviews`, and `Supply chain`.

See [architecture.md](architecture.md) for the active module map and [ADR-0025](decisions/0025-ajar-v3-4-value-hillclimbing-catalog-and-fail-closed-truth.md) for the `v3.4` decision record.

---

## 1. Why `Ajar v3.4` Exists

Telemetry from a 78.8h C systems campaign (`355` worker sessions) exposed five recurring failure modes in long-horizon autonomous security runs. `Ajar v3.4` eliminates each failure mode deterministically inside `ajar/` without adding LLM calls to the core engine:

1. **Premature Production Patching (`25.5% -> 0.0%` during `hunt`):**
   - *Failure mode:* Workers pivoted into writing multi-revision production patches and running full test suites while high-value attack surfaces and multi-hop chains remained unaudited.
   - *`v3.4` mechanism:* Runs start in `campaign_phase = 'hunt'`. `ajar patch verify` (and MCP `ajar_patch_verify`), `ajar task lease`, `ajar swarm plan`, and `ajar swarm brief` hard-block `patch` execution during `hunt` (`EXIT_GATE_BLOCKED`), deferring 9-arm `Fixes` until `ajar phase advance --to remediate` verifies `G5` chain convergence.
2. **Single-Root Mode Collapse (`8.3% -> 100.0%` subsystem illumination):**
   - *Failure mode:* Under `--uncapped` research runs, early `stepping_stone` findings spawned corroboration tasks that monopolized `1..2` files while sibling subsystems received zero exploration leases.
   - *`v3.4` mechanism:* `QD-Islands` (`compute_island_illumination`) boosts unvisited subsystem islands (`+12` salience + anti-monopoly wave reservation while illumination `< 0.75`) and caps over-mined islands (`-25` salience, `<= 55` cap), `compute_root_plateau_throttles` penalizes post-reproduction non-chain churn (`-35`), `ajar map --unvisited` surfaces unaudited call cones, and `ajar lead` aggregates multi-worker Expected-Value quorum votes.
3. **Disjunctive `1`-of-`k` False Chains & Hidden Multi-Hop Bridges:**
   - *Failure mode:* Matching a single tag on a multi-precondition sink enqueued unexploitable `chain` tasks while fixed list truncation hid late `(forward_tip, backward_entry)` Crown-Jewel bridges.
   - *`v3.4` mechanism:* `detect_percolated_multi_hop_paths` enforces full conjunctive `requires_tags` subset and upstream guard satisfaction, `ah_puct_score` ranks every 1-link `unicorn_gap` by Crown-Jewel impact, `repomap_edges` call proximity, and materialized `repro_snapshots`, and `ajar catalog {search,backslice}` unifies backward sink-to-source call slicing.
4. **Blind Input Guessing & Permissive Arm-3 Counterfactuals:**
   - *Failure mode:* Workers retried failing PoCs and multi-step chains without line-coverage feedback, while broken micropatches that crashed or failed to compile could falsely satisfy Arm 3 if the exploit oracle did not fire.
   - *`v3.4` mechanism:* `ajar repro slice-probe` renders zero-dependency Python `sys.settrace` and GCC `gcov` `@VISITED` / `@UNREACHED` (`FIRST_UNREACHED_AFTER_GUARD`) line annotations plus ASan/UBSan crash frames; `evaluate_chain_failure_streak` enforces a 2-strike runtime probe pivot on `ajar chain propose`; and Arm 3 / step ablation fail closed on compiler, runtime, or `SIGKILL`/`OOM` errors while separating zero-strike `micropatch_error` (`poc_proven = True`).
5. **Administrative Prose Churn & Onboarding Friction:**
   - *Failure mode:* Non-epistemic log events reset stall counters, manual archive scripts leaked local paths or symlinks, and operators had to run separate quote commands before initializing bounded runs.
   - *`v3.4` mechanism:* Grounded Lyapunov potential $\Phi(t)$ (`compute_epistemic_delta`) advances strictly on verified epistemic state transitions; `ajar bundle {seal,verify}` seals symlink-free, path-scrubbed deliverables; and `ajar init` computes inline quotes and COGS caps in one command with non-blocking warnings and `--max-spend` / `--warn-above-usd` / `--yes` guardrails.

---

## 2. The 3-Tier Campaign Feedback-Loop Ladder

Never validate a new scheduler, hook, or verification rule solely on a multi-day moonshot run. Evaluate every engine change bottom-up across three target tiers, applying **`Keep / Simplify / Delete`** at Tier 1 before advancing:

| Tier | Target Scope (`LoC`) | Wall-Clock Budget | Representative Target Classes | Required Exit Criteria |
| --- | --- | --- | --- | --- |
| **Tier 1: Fast-Feedback Calibration Targets** | `5K–45K LoC` | `< 90m` | Focused C/Rust archive unpackers, binary/wire frame parsers, auth/JWT verifiers, compact RPC daemons | Deterministic DST pass (`scripts/verify-repo.sh --full`) + measurable lift in root-cause precision, token efficiency, or chain completion; delete or simplify mechanisms with zero lift. |
| **Tier 2: Medium State-Machine Targets** | `50K–300K LoC` | `2h–8h` | Protocol state machines, execution/consensus clients, multi-tenant API gateways, embedded storage engines | `>= 0.75` `QD-Islands` subsystem illumination, `0` premature `hunt`-phase patches, clean `H1`–`H9` hook termination, and verified `Open Door` wakeup / 2–3 hop chain ablation. |
| **Tier 3: Moonshot Multi-Hop Targets** | `500K–40M LoC` | `8h–72h+` | Systems toolchains, compilers, language runtimes, OS services, browser/media pipelines, monorepos | Slice-capped PageRank + `ajar catalog backslice` coverage on Crown Jewels, `AH-PUCT` multi-hop percolation, warm `.o` 8-slot throughput, and `remediate`-phase 9-arm `Fixes` (`verified_local`). |

### Canonical Operator Flow Across Tiers

```bash
# Single-command initialization with inline estimate and optional spend ceiling
ajar init <target_dir> --stopping crown-jewel --phase hunt --max-spend 50.0
ajar door jewel-add --name "<terminal_sink>" --locus "<file:line>" --impact-class rce --symbols "<sink_fn>"

# Disjoint wave dispatch + zero-dependency runtime slice probing during hunt
ajar swarm plan --workers 6
ajar repro slice-probe --focus-locus <file:start-end> --cmd "<probe_cmd>" --record-coverage

# Convergence-gated transition to remediate for 9-arm production Fixes
ajar phase advance --to remediate
ajar patch verify <finding_id> --patch <fix.diff> --suite-cmd "<suite>" \
  --variant-cmd "<v1>" --variant-cmd "<v2>" --variant-cmd "<v3>" \
  --caller-audit "<caller safety>" --sibling-audit "<peer symmetry>"
```

---

## 3. `Ajar v3.5` Horizon Roadmap

`Ajar v3.5` builds on `v3.4`'s deterministic SQLite state engine and strict zero-LLM core invariant across four engineering tracks:

1. **Tree-Search MCTS over Conjunctive AND-OR Hypergraphs:**
   - Generalize 1-link `ah_puct_score` cut-lemma ranking into full Selection / Expansion / Backpropagation Monte Carlo Tree Search over conjunctive hypergraph states `(held_tags, cleared_guards, snapshot_id)`, propagating empirical `bridge` and `slice-probe` outcomes up ancestor hyperedges.
2. **Persistent Single-Tenant Attack-Surface Knowledge Graph Across Repositories:**
   - Persist tenant-isolated `ajar-platform-graph/2` invariants, `certified_bindings`, `surface_drivers`, and `trust_gadget` catalogs across coupled microservice repositories and incremental `ajar init --diff <base..head> --parent-run <id>` PR reviews with zero cross-tenant state sharing.
3. **C and Native Micro-Fuzz Runtime Harnesses:**
   - Synthesize bounded in-process `libFuzzer` / sanitizer micro-harnesses inside isolated `repro/slot-<k>` worktrees when `ajar repro slice-probe` identifies narrow arithmetic, framing, or state-flag guards (`FIRST_UNREACHED_AFTER_GUARD`) blocking deep parser sinks.
4. **Copy-on-Write (`reflink` / Overlay) Snapshot Slots:**
   - Replace full directory copies and tarball extraction across `repro/slot-<k>` and `ajar chain probe --from-snapshot` with Copy-on-Write filesystem clones (`cp --reflink=auto`, APFS `clonefile`, or user-space overlay mounts with automatic fallback), cutting large-repository slot reset latency to sub-second overhead.
