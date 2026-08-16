# Round 2 briefs — obyte-ocore-2026-08 (independent runs + kill-pair + stabilization link + chainability)

Launched 2026-08-11. Standing operator gate: every finding ships a maximum-impact PoC AND an
independent fresh-context run of that PoC reading RAW output. Round-1 adjudication in rounds.md.

## Independent PoC reviewers (fresh context; execute, don't trust)

### IR-F1 — independently run the P9 merkle PoC
- PoC: `evidence/lab/p9/p9-poc.js` (README in same dir); builder report `evidence/round1/p9.md`.
- Execute: `cd /Users/matheusvsky/Documents/trab/obyte-ocore-2026-08-ocore && node lab-obyte.js <abs>/evidence/lab/p9/p9-poc.js`
- Verify from RAW output: (1) all 4 vacuous rows true; (2) positive control true; (3) negative
  control false; (4) 60-sibling above-fix false / below-fix true; (5) `in merkle` contrast false.
- Check for reward-hacking (mock, hardcoded expectation, non-real path). Report
  `evidence/round2/IR-F1.md` + verdict JSON.

### IR-F2 — independently run the P8 signed-package PoC
- PoC: `evidence/lab/p8/run.js`; builder report `evidence/round1/p8.md`.
- Execute: same pattern. Verify from RAW output: 7a max_complexity 0 vs 10; 7b acceptance divergence;
  7c call-count divergence (60 below, 3-cap above).
- Report `evidence/round2/IR-F2.md` + verdict JSON.

### IR-F3 — independently run the invisible-fork experiment (f8-TRIPLE-2, r1's exp)
- Experiment: `evidence/lab/r1/p1-refute.js` (raw log `evidence/lab/r1/p1-refute.raw.log`); see
  `evidence/round1/r1.md` §6 (A_own accepted+saved while the victim's spend_proofs row exists).
- Execute and verify: (1) the victim's spend is saved with its (P, victim) row; (2) the attacker's
  re-spend with the SAME P and the attacker's own address is ACCEPTED and SAVED (no conflict
  detected); (3) no crash. Confirm the "invisible to the standard check" property from the DB state.
- Report `evidence/round2/IR-F3.md` + verdict JSON.

### IR-F4 — independently run the tps-fee drive + sqlite persistence tests
- Scripts: `evidence/round1/r2-tps-fee-drive.js`, `evidence/round1/r2-sqlite-infinity-test.js`;
  refuter report `evidence/round1/R2.md`.
- Execute both through the lab harness. Verify: fee=106,864,745,815,235 base at count=30/elapsed=1;
  honest author balance −106,864,745,815,218; gate rejection afterwards; -Infinity persistence.
- Report `evidence/round2/IR-F4.md` + verdict JSON.

## Kill-pair — F3 framing (bug vs by-design bearer model)

### KP-F3-kill — build the strongest case F3 is NOT reportable
Fresh context. Read `evidence/round0/f8.md` (TRIPLE-2/3), `evidence/round1/r1.md` §6,
`evidence/round2/BRIEFS.md` (this file), and the Obyte design context: spend proofs are published
"to protect against double-spends" (blackbytes docs). Argue: bearer-proof design (sender always
retains the blinding and can re-spend until the recipient's spend stabilizes — same as any
payer-controlled output); double-spends are resolved by the fork race for ALL assets (public
included — both units allowed, MC picks the winner); the spend-proof uniqueness check is a
detection-acceleration mechanism, not the security boundary; no marginal impact over the normal
model (a merchant must wait for stability regardless). Concede only where code/docs force you.

### KP-F3-establish — find the strongest TRUE form of F3
Fresh context, blind to the killer. Read the same sources. Build the best case that F3 IS a
defect: what does the address-validation gap enable that the public-asset model cannot do; is the
designed early-detection protection (unit-level rejection) defeated; can a merchant accepting a
private payment be defrauded in a way the public model prevents; is the divergence between public
(clean rejection) and private (invisible fork) evidence of unintended behavior; does the spend
proof's purpose ("to protect against double-spends") make fork-deferral a design violation?
"If this is empty" is an acceptable outcome. Concede where the code forces you.

## Stabilization link — the load-bearing question for F2 and the whole S1 family

### KP-F2-link — can an old-DAG-attached unit stabilize and execute?
Worker (full context). Question: the S1 eval-side bypass (F2, f5-T1) and the old-DAG gating family
(A5/A6) all require a unit attached below the upgrade MCIs to (a) pass validation, (b) stabilize
(get a ball), (c) execute the AA / reach the gated code with its old position. Determine
EMPIRICALLY (source trace + lab where feasible):
1. Can an old-DAG-attached unit be included on the MC (best-parent selection — does determineBestParent
   prefer tips; can old-attached units win)? (main_chain.js, storage.js determineBestParent, graph.js)
2. Can it reach the witnessed level required for stability (witnesses witness the tip region)?
3. What is the evaluation mci for an AA trigger at stabilization (aa_composer handlePrimaryAATrigger —
   is it the trigger's stored mci, the current mci, or the validation-time last_ball_mci)?
4. Is there ANY path where the gated evaluation runs with mci < pemCurvesFixMci on a real node
   (no-ball window, dry-run/estimation, getters, secondary triggers)?
Deliverable: `evidence/round2/KP-F2-link.md` — the answer per question with file:line, and the
terminal verdict: F2 reachable / real-but-capped (which window) / dead.

## Chainability

### CHAIN-1 — composition pass over F1+F2+F3+F4
Worker. Angles: (1) do F1 and F2 share the S1 root (old-DAG attachment as the primitive — what
else does it open if the link holds); (2) F3 + F4 (payment race + fee poisoning — does the fork
race interact with the fee window); (3) the persistence-of-effect angles (crash-loop, replay,
sibling sweep: are there OTHER spend-proof address-validation gaps; other bare-mci eval gates);
(4) the temp_data fee claim (f12-T5) — does validation reconcile data_length? Deliverable:
`evidence/round2/CHAIN-1.md` with per-angle verdicts (bounded / amplifier / new_finding).

## Output contract (all)
Report to `evidence/round2/<id>.md`; return JSON `{id, verdict, evidence, raw_output_ref}`.
Reviewers: do not modify PoC scripts; record + re-run if a fix is needed. No live network. No secrets.
