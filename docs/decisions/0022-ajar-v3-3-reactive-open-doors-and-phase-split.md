# ADR-0022: Ajar v3.3 Reactive Open Doors, Multi-Hop Middle-Unicorn Percolation, and Hunt/Remediate Phase Split

- **Status:** Accepted (Active)
- **Date:** 2026-11-20
- **Builds on:** [ADR-0017](0017-ajar-v3-dual-mode-architecture.md), [ADR-0018](0018-ajar-v3-1-bug-brain-and-platform-economics.md), [ADR-0019](0019-ajar-v3-2-hooks-and-composable-repro.md), [ADR-0020](0020-ajar-v3-2-2-swarm-wire-profiles-and-reopen.md), [ADR-0021](0021-ajar-v3-2-3-exogenous-target-checks-and-retro-routing.md)

## Context

Forensic inspection of the 16-hour `git-wave1a` C campaign (`2026-11-20`) exposed six structural bottlenecks that throttled complex multi-stage chain synthesis:

1. **Remediation Drag During Active Hunting:** Running 9-arm `ajar patch verify` (`--suite-cmd` + `git clean -fdx` wiping compiled `.o` objects) on early stepping-stone findings consumed the majority of wall-clock hours before high-impact cross-subsystem chains were explored.
2. **Early Satisficing on Multi-Step `High` Stepping Stones:** Reproducing a multi-command `High` capability satisfied first-high stopping rules instead of treating the finding as an intermediate stage (`H5_POST_CONFIRM_ESCALATION`) toward a single-entrypoint Crown Jewel.
3. **No Suspended Subgoal ("Open Door") Memory or Reactive Wakeup:** When deep sink or partial-chain audits hit an unmet upstream precondition, workers had to either block a single task on a static predicate or close out, losing reactive cross-subsystem wakeup when another worker later discovered the missing piece.
4. **Pairwise-Only Bridge Matching Missed Middle-Link Percolation & Trust Gadgets:** Real-world chains frequently combine Low/Medium quirks (`role='capability'`) with non-buggy code that trusts a broken invariant (`role='trust_gadget'`), snapping together only when an intermediate middle link connects an entry prefix to a guarded sink suffix.
5. **Python `StageContext` Boilerplate & Missing Post-State Snapshots:** Confirmed `findings` (`fnd-*`) and `claims` (`clm-*`) were invisible to `ajar chain propose` unless wrapped in Python helper modules, and multi-stage PoCs had to re-run upstream stages from scratch instead of probing saved filesystem post-states.
6. **Subprocess Toolchain Scrubbing & Strike-Burning Compiler Errors:** Stripping `SDKROOT`/`DEVELOPER_DIR`/`PKG_CONFIG_PATH` and dangling `PATH` entries caused compiler/SDK failures that burned `claims.failed_repro_count` strikes, while C file-local `static` helpers inflated cross-file `repomap_edges`.

## Decision

1. **Campaign Phase Split (`runs.campaign_phase = 'hunt' | 'remediate'`, `ajar phase`, `ajar finding calibrate`):**
   - Initialize runs in `hunt` phase by default. While `campaign_phase == 'hunt'`, `ajar patch verify` rejects execution (`EXIT_GATE_BLOCKED`) and `lease_next_task` skips `patch` tasks until `ajar phase advance --to remediate`.
   - `ajar patch verify` preserves compiled `.o`/`.a` objects via `_clean_slot_preserving_objects` + local SSD build caches, defaults `--suite-timeout` to `1800s`, and records `remediation_state = 'verified_local'` (reserving `'maintainer_patched'` for upstream verification). `ajar finding calibrate` adjusts severity and precondition realism in one atomic command.
2. **Suspended Subgoals ("Open Doors") & Portfolio Anti-Starvation (`crown_jewels`, `parked_doors`, `door_fts`, `ajar door`):**
   - `ajar door jewel-add` registers concrete terminal sinks (`crown_jewels`), and `ajar door park` suspends blocked deep sinks or partial chains (`sink_to_source`, `source_to_sink`, `middle_bridge`) with `wanted_tags`, `wanted_symbols`, `blocker_locus`, and optional `snapshot_id`.
   - Parking an unmatched door spawns `<= 2` bounded `bridge` tasks (`max_bridge_attempts = 2`) while `lease_next_task` and `ajar swarm packet --stage portfolio|bridge` preserve greenfield `investigate` capacity.
   - Tri-modal matching (`wake_matching_doors_for_artifact`: capability tags + code symbols/blocker proximity/1-hop `repomap_edges` + SQLite `door_fts` BM25) transitions matching doors (`parked | bridging | exhausted_locked -> ready`) and boosts `chain` task salience to `>= 96`, while keeping `Certified Run Prefix` byte-identical (`Open Doors` render inside `Task Delta`).
3. **Multi-Hop Middle-Unicorn Percolation & Trust Gadgets (`ajar/chain_planner.py`, `ajar primitive --role`):**
   - `primitives` distinguishes `role IN ('capability', 'trust_gadget')` plus `ajar primitive dry`.
   - `detect_percolated_multi_hop_paths` runs forward capability reachability and backward sink-cone search (`2..10` hops), enqueuing `salience = 98` `chain` tasks the moment a newly discovered middle link connects an entry prefix to a sink suffix and surfacing 1-link `unicorn_gaps` in `ajar chain frontier`.
4. **`crown-jewel` Stopping Criterion & Anti-Delusion Realism Gate (`evaluate_precondition_realism`):**
   - `ajar claim reproduce` and `ajar chain propose` hard-block caller-supplied execution/config self-overrides (`-c core.sshCommand=`, `-c core.fsmonitor=`, `--upload-pack=`, `GIT_SSH_COMMAND=`, `LD_PRELOAD=`) and gadget-only chains (`all role == 'trust_gadget'`).
   - Multi-command (`declared_step_count > max_steps`) or operator-assisted Highs classify as `realism_tier = 'stepping_stone'`: they trigger `H5_POST_CONFIRM_ESCALATION` (including `High -> Critical` escalation) and never short-circuit `--stopping crown-jewel`, while bounded exhaustion allows clean `G1–G5` closeout when all surfaces and bridge hunts complete.
5. **Zero-Boilerplate Chain Composition & Post-State Snapshots (`ajar repro try`, `--save-post-state`, `ajar chain probe/propose`):**
   - `ajar chain propose --steps` accepts `fnd-*`, `clm-*`, `prim-*`, and `anom-*` directly, auto-inheriting stored `micropatch_diff` patches for $N$-step causal ablation with `AJAR_ABLATE_STEPS=""` enforced on Arm 2.
   - `ajar claim reproduce --save-post-state <rel_dir>` archives Arm-1 post-state snapshots (`snp-*` `.tar.gz`), and `ajar chain probe --from-snapshot <snp_id>` + strike-free `ajar repro try` enable rapid downstream hypothesis testing without burning strikes.
6. **Toolchain Scrubbing Hygiene, `error_class` Separation, & C `static` Edge Pruning (`ajar/redact.py`, `ajar/repro_source.py`, `ajar/repomap.py`):**
   - `scrubbed_subprocess_env` preserves `SDKROOT` (including cached macOS `xcrun`), `DEVELOPER_DIR`, `PKG_CONFIG_PATH`, `.cargo/bin` + rustup toolchain `bin` (`CARGO_NET_OFFLINE=true`), `$AJAR_RUN_DIR`, and `$AJAR_ARTIFACTS_DIR`, while stripping dangling `PATH` symlinks.
   - `run_source_reproduction` separates `preflight_error` and `build_or_env_error` from `target_negative` (`0` strikes recorded on compiler/SDK/linker errors), and `repomap.py` marks C/C++ `static` definitions `file_local=True` so file-private helpers never pollute cross-file `repomap_edges`.

## Consequences

- Agents pursue deep multi-stage chains and greenfield exploration concurrently during `hunt` without 9-arm remediation drag or premature `High` satisficing.
- Existing `v3.2.x` `run.db` ledgers migrate automatically in-place on `open_run_db` via `_ensure_v33_schema` (`ajar reopen` compatible).

## Risks and Revisit Triggers

- **Risks:** Overly broad `wanted_symbols` on parked doors could wake unrelated capabilities; `_score_door_match` mitigates this by requiring `>= 0.65` tri-modal score (`>= 2` domain tokens on FTS5 hits) and transitioning `ready -> exhausted_locked` if the woken `chain` task closes `dry`.
- **Revisit Trigger:** Revisit percolation hop weighting and snapshot size caps (`64 MiB`) after `git-wave1a` resumed (`v3.3`) and `kona-wave1b` complete.
