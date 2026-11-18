---
name: ajar-chain
description: Run Stage-5 Converge synthesis to break upstream guards, apply the 6 chain angle-shapes, challenge severity caps, and verify end-to-end exploit chains.
---

# Ajar Chain (Stage-5 Converge)

Use this skill when closeout gate `G5` enqueues a Stage-5 `Converge` (`chain`) task, when guarded primitives (`guarded_by_locus != ''`) await guard breaking, or when two or more `primitives`, `unexplained` anomalies, or `low`/`medium` findings exist in `run.db`.

## 1. Load All Composable Signals

Inspect every recorded capability, guarded sink, anomaly, binding, and capped claim across subsystems:

```bash
ajar primitive list
ajar anomaly list
ajar claim list
ajar binding list
ajar precedent search "<stage1_kind> <stage2_kind>"
```

Consult `skills/references/project-zero-zdi-chain-corpus.md` and `skills/references/defi-exploit-chain-corpus.md` for verified multi-stage handoff patterns.

## 2. Invariant-Pair Guard Breaking

Match `primitives.postconditions` against every guarded sink (`primitives.guarded_by_locus` / `guard_assumption`) and `conditional_blocked` task predicate:

1. List every guarded primitive where standalone exploitation was blocked by an upstream invariant `I`.
2. Search all other `primitives`, `anomalies`, and `low`/`medium` findings across sibling routes, background workers, callbacks, or batch endpoints whose `postconditions` falsify or bypass `I`.
3. Run `ajar pulse` after recording new primitives so `conditional_blocked` tasks whose predicates are satisfied reopen automatically with boosted salience.

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

1. **Attack Your Own Caps First:** Inspect every `low`/`medium` finding and `blocked` claim. Ask: *"Which recorded primitive or sibling route removes the precondition that capped this bug's severity?"*
2. **Marginal-Contribution Critique:** Every step listed in `--steps` must be causally required. Remove any step whose deletion still allows `--poc-cmd` to cross the final trust boundary; never pad a standalone bug into a synthetic multi-step chain.
3. **Sibling Cross-Kill Deduplication:** When multiple candidate chains or claims pivot through the exact same broken chokepoint, group them under one root cause or verify duplicate cross-kill rather than inflating finding counts.

## 5. Promote Composable `StageContext` Helpers and Prove $N$-Step Causal Ablation

1. For reusable stage capabilities, promote a dual-mode Python helper (`ctx.is_ablated("<prim_id>")` returning benign state during control/ablation) into read-only `repro/helpers/ajar_helpers/` outside `slot-<k>`:
   ```bash
   ajar primitive promote-helper <primitive_id> \
     --file <path/to/stage_helper.py> \
     --callable <fn_name> \
     --provides-tags "<ns:tag>"
   ```
2. Propose and verify the end-to-end chain inside `repro/slot-<k>`. `ajar chain propose` automatically runs (a) full exploit chain, (b) benign control, and (c) per-step marginal ablation (`AJAR_ABLATE_STEPS=<step_id>` or `--step-micropatch <step_id>:<diff>`), rejecting any padded step whose removal still triggers the oracle:
   ```bash
   ajar chain propose \
     --title "<Stage 1 -> Stage 2 -> Terminal Impact>" \
     --steps "<primitive_id_1>,<primitive_id_2>" \
     --poc-cmd "<end-to-end multi-stage command using ajar_helpers or target binary>" \
     --control-cmd "<benign workflow command that does not cross boundary>" \
     [--step-micropatch "<primitive_id_1>:<step1.diff>"] \
     [--oracle-json '{"expect_regex":"UNAUTHORIZED_STATE"}'] \
     --severity critical
   ```

Elevate chain severity above its individual links only when the end-to-end PoC passes per-step causal ablation and achieves an unauthorized `C`/`I`/`A` impact that no single step reaches alone.
