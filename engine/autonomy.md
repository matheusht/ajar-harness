# autonomy.md — staged autonomy and how a gate earns removal

## 1. Autonomy is not one control

The harness treats supervision as one setting: the operator checks the work before it moves on. That
is the wrong model. Parasuraman, Sheridan and Wickens (2000) decompose automation into four separate
stages, each with its own level:

| Stage | In this harness | Cost of an error | Default level |
|---|---|---|---|
| Information acquisition | recon, surface snapshots, routing signals | wasted compute | high autonomy |
| Information analysis | narrowing, triples, reachability, chain construction | wasted effort, a wrong lead | high autonomy |
| Decision selection | `confirmed`, severity, `covered-dry` | a false report or a missed bug | **operator** |
| Action implementation | Zone-2 artifacts, filing, disclosure | not reversible | **operator** |

Running acquisition and analysis near-autonomous while decision and action stay human is not a
compromise. It is the correct shape. Read the level per stage, never as one number.

## 2. Which gates are irreducible

Two gates stay human. No framework surveyed supports removing either.

**Zone-2 confirmation before an impact artifact.** The action is not reversible. Every production
system that handles this class narrows the *capability* rather than trusting supervision more.

**Adjudicating `confirmed`.** This is decision selection, the exact stage where automation bias
produces silent misses. Skitka et al. measured the reason: training reduces commission errors and
does **not** reduce omission errors. Telling a model to be careful does not fix a missed check. Only
an independent check does.

Everything else is a candidate for graduation.

## 3. The standby method

A gate is removed by evidence, never by decision.

1. **Declare the rule before the data.** Write a preregistration: the gate, the sample size, the
   quality proxy, and the decision rule. A rule written after seeing results is not a rule.
2. **Run on standby.** The operator watches and does not gate.
3. **Record every intervention live.** Use `tools/intervention_ledger.py` with
   `provenance: "live"`. Never mix live entries with backfilled ones in one statistic.
4. **Decide at N.** Not before.

Source: Feng, McDonald and Zhang 2025, "assisted evaluation". One paper, not independently
validated. The method is reasonable, not proven.

## 4. What must be true before a gate is removed

- The gate is **reversible**. Restoring it costs a re-review and nothing else.
- The stage is acquisition or analysis, not decision or action.
- A **quality proxy with ground truth** exists. Without one you measure only that nobody complained.
- The intervention count is at or near zero across the declared N.
- **The verifier is not the thing being verified.** DO-178C, the JPL two-analyzer rule and Binary
  Authorization all converge on this, and it is the failure this harness has hit most often.

## 5. Read the sample honestly

A small N bounds a rate loosely. With N=40 and zero misses, the rule of three puts the 95% upper
bound on the true miss rate near 7.5%. That is not "the gate is safe". It is "the miss rate is
probably under 7.5%". State the bound whenever the number is reported.

## 6. The two failure modes, and they are opposite

**Asking too often** produces rubber-stamping. Alarm-fatigue and SOC research both find that volume
and lack of differentiation drive it, not accuracy: a well-calibrated gate still produces
rubber-stamping if the operator sees too many without severity differentiation. The fix is batching
and exception-surfacing, not a smarter alarm.

**Asking too rarely** produces automation bias, and its omission half cannot be trained away.

Set the ask-threshold by cost asymmetry, not by habit. A rare, catastrophic-miss stage should stay
trigger-happy while other stages get stingier.

## 7. Anti-patterns

- **Self-reported confidence as the escalation trigger.** The verifier becomes the thing verified.
- **Calibrate once, trust for ever.** Oracle validity does not transfer across namespaces. Declare a
  re-check cadence when the gate is removed.
- **Graduating two gates at once.** If quality drops you cannot say which caused it.
- **A holdout that leaks.** A leaking holdout does not fail loudly. It produces a clean-looking
  result that means nothing. Run `tools/preflight_holdout.py` before the run, not after.

## 8. Record

Every graduation writes: the preregistration, the live ledger entries, the preflight result, and the
decision against the declared rule. A gate removed without those four cannot be defended later, and
cannot be reversed with evidence when it turns out to be wrong.
