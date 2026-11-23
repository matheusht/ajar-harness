---
name: ajar-chain
description: Run Stage-5 Converge synthesis to break upstream guards, apply the 6 chain angle-shapes, challenge severity caps, and verify end-to-end exploit chains.
---

# Ajar Chain (Stage-5 Converge)

Use this skill when closeout gate `G5` enqueues a Stage-5 `Converge` (`chain`) task, when guarded primitives (`guarded_by_locus != ''`) await guard breaking, or when two or more `primitives`, `unexplained` anomalies, or `low`/`medium` findings exist in `run.db`.

## 1. Load All Composable Signals

Inspect the live chain frontier (woken `ready` Open Doors, $2..10$-hop percolated paths, 1-link `unicorn_gaps`, post-state snapshots, and capability bridges) alongside recorded capabilities, trust gadgets, and stepping-stone findings:

```bash
ajar chain frontier
ajar catalog search [--tags "<ns:tag>"] [--role <finding|capability|trust_gadget|candidate_claim|anomaly|open_door>]
ajar catalog backslice <sink_or_jewel_or_door_id> --max-hops 3
ajar door list
ajar lead rank
ajar precedent search "<stage1_kind> <stage2_kind>"
```

Consult `skills/references/project-zero-zdi-chain-corpus.md` and `skills/references/defi-exploit-chain-corpus.md` for verified multi-stage handoff patterns.

## 2. Multi-Hop Middle-Unicorn Percolation, Backward Sink Slicing, & Open-Door Synthesis

1. **Middle-Unicorn Percolation (`percolated_paths`, `unicorn_gaps`, & `ajar catalog backslice`):** A Low/Medium quirk (`role=capability`) plus normal trust-laundering code (`role=trust_gadget` — such as normal hook/template/plugin loaders) may sit disconnected from a Crown-Jewel sink until an intermediate link bridges the gap. Check `ajar chain frontier` and `ajar catalog backslice`:
   - If `percolated_paths` is non-empty, prioritize proving the full $N$-hop sequence immediately (`salience = 98`).
   - Run `ajar catalog backslice <cjw_or_symbol> --max-hops 3` to walk `repomap_edges` backward (`callee <- caller`) from terminal sinks, surfacing indirect-sink bridges and `unvisited_caller_files`.
   - If `unicorn_gaps` shows a 1-link Crown-Jewel gap (`forward_prefix -> [unmet_requires] -> backward_suffix`), either park an explicit `bidirectional` Open Door (`ajar door park --direction bidirectional ...`) or dispatch bounded hunters (`ajar swarm packet --stage bridge`).
2. **Post-State Snapshot Probing (`ajar chain probe --from-snapshot`):** When Stage 1 captured a filesystem snapshot (`snp-*` via `ajar claim reproduce --save-post-state`), test downstream Stage-2 consumers directly against that hydrated state inside the shared `slot-<k>` pool (passing `--build-cmd` when compiled binaries are untracked) before writing the combined end-to-end command:
   ```bash
   ajar chain probe \
     --from-snapshot <snp_id> \
     [--build-cmd "<incremental build command>"] \
     --cmd "<stage-2 consumer command operating on hydrated Stage-1 post-state>" \
     [--oracle-json '{"expect_regex":"UNAUTHORIZED_SINK"}']
   ```

## 3. Check All 6 Chain Angle-Shapes

Evaluate composition across six concrete structural patterns:

1. **Entry -> Guard Bypass -> Inner Sink:** Combine path/host normalization drift, SSRF, or header/parameter smuggling with an internal or guarded mutation sink.
2. **State Nudge -> Invariant Drift -> Accounting/Auth Corruption:** Combine dust/rounding nudges, stale cache/oracle reads, or partial state writes with downstream share, collateral, or quota math.
3. **Disclosure -> Secret/Nonce Recovery -> Forgery:** Combine an information leak, timing/error oracle, or unauthenticated metadata read with token, webhook, or signature verification.
4. **Peer-Hook / Lifecycle Asymmetry:** Enter state through a permissive sibling route or `update`/`transfer`/`callback` hook that omits an invariant enforced only on `create`.
5. **Defeats-Its-Own-Mitigations:** Test whether a sanitizer, canonicalizer, retry handler, lock fallback, or rate limiter mutates input or state in a way that enables a secondary exploit primitive.
6. **Shared-Chokepoint Widening:** When one broken helper, middleware, or deserialization wrapper feeds multiple downstream subsystems, trace the highest-impact reachable sink rather than stopping at the first low-impact caller.

## 4. Three Mandatory Converge Critiques

Before proposing or closing out chains, apply three critiques:

1. **Attack Your Own Stepping Stones First:** Inspect every `low`/`medium` finding, `stepping_stone` `high` finding, and `ready` Open Door. Ask: *"Which recorded capability, trust gadget, or sibling route turns this multi-step capability into a single-entrypoint Crown Jewel?"*
2. **Marginal-Contribution & Anti-Gadget-Only Critique:** Every step listed in `--steps` must be causally required, and at least one step must be a real invariant-breaking defect (`fnd-*`, `clm-*`, `anom-*`, or `role=capability` `prim-*`; gadget-only chains are rejected, and step ablation fails closed on compiler/env errors or `SIGKILL`/`OOM`). Remove any step whose ablation still allows `--poc-cmd` to cross the final boundary.
3. **Sibling Cross-Kill Deduplication:** Group sibling paths sharing one broken chokepoint under one root cause rather than inflating counts.

## 5. Zero-Boilerplate Multi-Artifact `ajar chain propose`, Backup-Slot Swaps, & Calibration

1. **Direct Step Composition & Modular `--backup-step` Swaps:** `--steps` accepts `fnd-*`, `clm-*`, `prim-*`, and `anom-*` IDs directly in causal order, **auto-inherits** `findings.micropatch_diff` and `primitives.micropatch_diff` for per-step ablation, and supports `--backup-step <primary_id>:<backup_id>` (`$AJAR_ACTIVE_STEPS` / `$AJAR_STEP_SWAPS`) to swap alternate capabilities automatically if a primary step fails:
   ```bash
   ajar chain propose \
     --title "<Stage 1 -> Stage 2 -> Terminal Impact>" \
     --steps "<fnd_or_prim_1>,<prim_or_gadget_2>[,<step_3>...]" \
     [--backup-step "<primary_step_id>:<backup_step_id>"] \
     [--build-cmd "<optional build command>"] \
     [--door <door_id>] \
     [--jewel <jewel_id>] \
     [--declared-steps <N>] \
     --poc-cmd "<end-to-end command invoking real target binary>" \
     --control-cmd "<benign workflow command (runs with AJAR_ABLATE_STEPS='')>" \
     [--step-micropatch "<step_id>:<ablation.diff>"] \
     [--oracle-json '{"expect_regex":"UNAUTHORIZED_STATE"}'] \
     --severity critical
   ```
   Use `ajar chain calibrate <chain_id> --realism-tier <crown_jewel|high_impact|stepping_stone> [--declared-steps <N>] --reason "..."` when post-review refines interaction step counts or visible-error boundaries.
2. **Portfolio Swarm Dispatch & Runtime Execution Integrity:**
   - Dispatch parallel hunters and chain verifiers via `ajar swarm packet --stage portfolio` (or `--stage chain` / `--stage bridge`), preserving greenfield exploration alongside active bridge hunts.
   - `--poc-cmd` and `--control-cmd` must execute the real target binary without caller-supplied execution self-overrides (`-c core.sshCommand=`, `--upload-pack=`, `GIT_SSH_COMMAND=`, `LD_PRELOAD=`) or static source-inspection cheats.

Elevate chain severity above its individual links only when the end-to-end PoC passes per-step causal ablation and achieves an unauthorized `C`/`I`/`A` impact that no single step reaches alone.

