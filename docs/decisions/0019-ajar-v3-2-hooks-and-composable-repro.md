# ADR-0019: Ajar v3.2 Event-Driven Epistemic Hooks, Composable Stage Builders, and 9-Arm Fixes Gate

- **Status:** Accepted (Active)
- **Date:** 2026-11-18
- **Extends:** [ADR-0017](0017-ajar-v3-dual-mode-architecture.md), [ADR-0018](0018-ajar-v3-1-bug-brain-and-platform-economics.md)

## Context

`Ajar v3.1` established bi-directional task routing, locus-bound 4-arm reproduction, Stage-5 `Converge`, and an 8-arm remediation gate. Empirical audits of 18 real-world multi-stage vulnerability chains from 2024–2026 (`NGINX2Root`, `React2Shell`, `Calif php2shell`/`java4shell`, `XRPL` `$250K`, `Git 2.56.1` CVEs, `IngressNightmare`, `regreSSHion`, and `Langflow`) plus competitive teardowns of peer AI security engines identified four remaining gaps:

1. **Static Prompt Checklists Create Confirmation Bias:** Injecting long multi-stage exploit checklists on every task wastes prompt budget on clean CRUD code and pushes workers to invent speculative chains when upstream guards are sound.
2. **Monolithic Shell PoCs Cannot Compose or Ablate Cleanly:** Running `ajar chain propose` as a flat shell command in `workspace/` lacked `slot-<k>` git-reset isolation, could not share verified stage builders across workers without polluting `git clean -fdx`, and could not mechanically prove that each step in `--steps` was causally required.
3. **Debug-vs-Release UB Divergence and Remediation Loopholes:** Compiled C/C++/Rust/Zig findings reproduced under `-fsanitize=undefined` or debug assertions could turn out to be `debug_assert_only` no-ops or silent wraparound escalations under `-O2` / `--release`. Meanwhile, `ajar patch verify` needed baseline broken-test diffing, clean-`HEAD` variant firing checks, executable caller/sibling verification commands, and a patch-revert re-failure proof.
4. **Scale and Incremental PR Ergonomics:** Large repositories required cohesive subsystem call-cone partitioning (`--slice-cap 15000` soft target so multi-thousand-line C/Rust state machines are never split mid-file), Lead Orchestrator campaign briefs (`brief.md`) that survive compactions without bloating worker prefixes, `--uncapped` research runs, and PR differential state sync.

## Decision

We upgrade Ajar to `v3.2.1` while preserving the zero-LLM deterministic SQLite WAL core:

1. **Event-Driven Epistemic Micro-Hooks (`ajar/epistemic_hooks.py`, `H1`–`H8`):**
   - Inject `0` hook tokens on plain code when no SQLite state transition or lightweight source signal fires.
   - Cap active guidance at `<= 2` hooks (`<= 90` tokens total) inside the `Task Delta` tail of `render_task_context`, keeping the `Certified Run Prefix` 100% byte-identical across workers for KV prompt-cache hits.
   - Pair every triggered hook (`H1_GUARD_SYMMETRY` through `H8_PROJECTION_UNDER_CONSTRAINT`) with a mandatory 1-line `Kill Rule` and automatic `max_leases` expiry (`<= 2` leases; `1` lease for `H5_POST_CONFIRM_ESCALATION` and `config_gated` probes).
2. **Cross-Subsystem Capability Bridge (`provides_tags <-> requires_tags`):**
   - Extend `primitives` and `surfaces` with normalized `ns:name` capability tags.
   - Automatically match upstream `provides_tags` against downstream `requires_tags` across subsystems to surface candidate bridges in `Task Delta` and enqueue Stage-5 `chain` tasks (`H4_TYPED_STATE_BRIDGE`).
3. **Composable Stage Builder and $N$-Step Causal Ablation (`ajar/repro_compose.py`):**
   - Provide `StageContext` and `ajar primitive promote-helper` to dual-mode-verify (`exploit_path` vs `benign_control`) and lock read-only (`0444`) Python stage helpers under `~/.ajar/runs/<run_id>/repro/helpers/ajar_helpers/` outside `slot-<k>`.
   - Execute `ajar chain propose` inside isolated `repro/slot-<k>` worktrees with `--oracle-json` support and automated per-step marginal-contribution ablation (`AJAR_ABLATE_STEPS` or `--step-micropatch <step_id>:<diff>`), rejecting padded steps.
   - Enforce a container loopback socket guard (`sitecustomize.py` blocking non-loopback `AF_INET`/`AF_INET6` sockets when `AJAR_BLOCK_EXTERNAL_NET=1`) whenever `unshare -rn` is unavailable in unprivileged containers.
4. **Release-Profile UB Differential & Hardened 9-Arm `Fixes` Gate (`ajar/repro_source.py`, `ajar/patch_verify.py`):**
   - Add Arms `5A`/`5B` (`--release-cmd` / `--release-control-cmd`) to `ajar claim reproduce`, classifying `consistent | silent_wrap_escalated | debug_assert_only | trap_dos_only` and blocking `debug_assert_only` claims from `critical`/`high` severity (`G3`).
   - Harden `ajar patch verify` to 9 arms: cached clean-`HEAD` baseline suite diffing (`repro/baseline_suite.json`), verification that `>= 1` `--variant-cmd` triggers on clean `HEAD`, executable `--caller-cmd` and `--sibling-cmd` support, and **Arm 9 (`git apply -R`)** proving that reverting the fix on the same worktree re-triggers the defect oracle.
5. **Cohesive Subsystem Cones, Campaign Briefs, PR Diff Sync, and Modular Instrumentation (`ajar/repomap.py`, `ajar/workspace.py`, `ajar/diff_sync.py`):**
   - Partition repository call graphs into cohesive subsystem call cones (`ajar map --slice-cap 15000`) with a `< 1 KB` architectural skeleton and SHA-bound `ajar coverage record`, avoiding mid-file splits on multi-thousand-line state machines (`apply.c`, `merge-ort.c`).
   - Persist flexible Lead Orchestrator strategy in `~/.ajar/runs/<run_id>/brief.md` (`ajar init --brief-file`, `ajar brief`) outside worker task prefixes, and support `--uncapped` (`pricing_mode=uncapped_research`) for open-ended deep research runs.
   - Support `ajar init --diff <base..head> [--parent-run <id>]` to carry forward `kept` findings/guards, verify `closed` fixes on `HEAD`, and re-open `invalidated_guard` `dry` tasks when edited hunks touch a cited guard locus.
   - Add `ajar task checkpoint`, `ajar claim instrument` (`slot-inst`), `ajar claim falsify --config-gate`, `[UNTRUSTED_TARGET_DOC]` FTS5 provenance tags, and `detect_soliloquy_transcript`.
6. **Initial + Adaptive Threat Modeling (`ajar threat-model`, `threat_models` / `threat_assumptions`):**
   - Synthesize structured campaign threat models (`principals`, `assets`, `consumer_tiers`) and falsifiable boundary assumptions (`invalidated_by_tags`, `check_locus`, `dependent_surface_id`, `escalate_priority`) during `ajar map`.
   - Automatically flip matching `assumed` boundaries to `violated` when a primitive provides `invalidated_by_tags` or a confirmed finding hits `check_locus`, incrementing `threat_models.revision`, upgrading exposed downstream surface priority, unblocking parked tasks (`+30` salience), and injecting a `<= 2`-line `Adaptive Threat-Model Shift` notice into `Task Delta` without altering the KV-cached `Certified Run Prefix`.

## Consequences

- Clean targets incur zero extra prompt tokens while complex multi-stage boundaries receive targeted `<= 90`-token structural prompts with explicit `dry` exit criteria.
- Multi-step chains and production fixes carry mechanical receipts proving marginal step necessity and patch-revert causality.
- `GAP-01` in `check_guarded_primitive_dry_block` is closed so an unexecuted `open` `chain` task cannot permit premature `dry` closure of an unchained guarded primitive.

## Risks and Mitigations

- **Hook Over-Firing on Large Codebases:** Mitigated by `dedup_key` uniqueness, `<= 2` hook cap per task context, mandatory `Kill Rule` lines, and automatic `max_leases` expiration during `ajar pulse`.
- **Container Egress Bypass by Non-Python Binaries:** When `unshare -rn` is unavailable, compiled C/Go/Rust binaries receive scrubbed proxy/network env vars while Python harnesses enforce socket-level loopback blocking; full 3-tier egress proxy isolation for `live` runs remains scheduled for `v3.3`.

## Revisit Triggers

1. When building `v3.3` `live` mode egress sandboxing (`mitmproxy` / network namespace helper).
2. If empirical run telemetry shows any hook (`H1`–`H8`) expiring unused across `> 85%` of exposures without producing a verified primitive, finding, or faster `dry` proof.
