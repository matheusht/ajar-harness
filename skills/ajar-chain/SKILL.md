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
ajar door list
ajar primitive list
ajar anomaly list
ajar claim list
ajar precedent search "<stage1_kind> <stage2_kind>"
```

Consult `skills/references/project-zero-zdi-chain-corpus.md` and `skills/references/defi-exploit-chain-corpus.md` for verified multi-stage handoff patterns.

## 2. Multi-Hop Middle-Unicorn Percolation & Open-Door Synthesis

1. **Middle-Unicorn Percolation (`percolated_paths` & `unicorn_gaps`):** A Low/Medium quirk (`role=capability`) plus normal trust-laundering code (`role=trust_gadget`) may sit disconnected from a Crown-Jewel sink until an intermediate link bridges the gap. Check `ajar chain frontier`:
   - If `percolated_paths` is non-empty, prioritize proving the full $N$-hop sequence immediately (`salience = 98`).
   - If `unicorn_gaps` shows a 1-link gap (`forward_prefix -> [unmet_requires] -> backward_suffix`), either park an explicit `bidirectional` Open Door (`ajar door park --direction bidirectional ...`) or dispatch bounded hunters (`ajar swarm packet --stage bridge`).
2. **Post-State Snapshot Probing (`ajar chain probe --from-snapshot`):** When Stage 1 captured a filesystem snapshot (`snp-*` via `ajar claim reproduce --save-post-state`), test downstream Stage-2 consumers directly against that hydrated state inside `slot-inst` before writing the combined end-to-end command:
   ```bash
   ajar chain probe \
     --from-snapshot <snp_id> \
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
2. **Marginal-Contribution & Anti-Gadget-Only Critique:** Every step listed in `--steps` must be causally required, and at least one step must be a real invariant-breaking defect (`fnd-*`, `clm-*`, `anom-*`, or `role=capability` `prim-*`; gadget-only chains are rejected). Remove any step whose ablation still allows `--poc-cmd` to cross the final boundary.
3. **Sibling Cross-Kill Deduplication:** Group sibling paths sharing one broken chokepoint under one root cause rather than inflating counts.

## 5. Zero-Boilerplate Multi-Artifact `ajar chain propose` & $N$-Step Causal Ablation

1. **Direct Step Composition (Zero Mandatory Python Boilerplate):** `--steps` accepts `fnd-*`, `clm-*`, `prim-*`, and `anom-*` IDs directly in causal order and **auto-inherits** `findings.micropatch_diff` and `primitives.micropatch_diff` for per-step ablation (use `--step-micropatch <id>:<diff>` only when overriding or ablating a step without a stored patch, or `ajar primitive promote-helper` when stateful Python `StageContext` builders are helpful):
   ```bash
   ajar chain propose \
     --title "<Stage 1 -> Stage 2 -> Terminal Impact>" \
     --steps "<fnd_or_prim_1>,<prim_or_gadget_2>[,<step_3>...]" \
     [--door <door_id>] \
     [--jewel <jewel_id>] \
     [--declared-steps <N>] \
     --poc-cmd "<end-to-end command invoking real target binary>" \
     --control-cmd "<benign workflow command (runs with AJAR_ABLATE_STEPS='')>" \
     [--step-micropatch "<step_id>:<ablation.diff>"] \
     [--oracle-json '{"expect_regex":"UNAUTHORIZED_STATE"}'] \
     --severity critical
   ```
2. **Portfolio Swarm Dispatch & Runtime Execution Integrity:**
   - Dispatch parallel hunters and chain verifiers via `ajar swarm packet --stage portfolio` (or `--stage chain` / `--stage bridge`), preserving greenfield exploration alongside active bridge hunts.
   - `--poc-cmd` and `--control-cmd` must execute the real target binary without caller-supplied execution self-overrides (`-c core.sshCommand=`, `--upload-pack=`, `GIT_SSH_COMMAND=`, `LD_PRELOAD=`) or static source-inspection cheats.

Elevate chain severity above its individual links only when the end-to-end PoC passes per-step causal ablation and achieves an unauthorized `C`/`I`/`A` impact that no single step reaches alone.

