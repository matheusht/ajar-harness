# rounds.md — round ledger, family registry, primitive registry

Pinned: `a7eb776afc68ed4bed05ba554f7f1e95f5d49b44`. Newest first. Append-only.

## Round 0 — blind portfolio (2026-08-11, 16 hunters, one family each)

**Launch:** 16 independent hunters (deepseek-v4-flash, thinking high), one family each, no crown-jewel
prior beyond the shared recon-signals.md seed. Reports in `evidence/round0/<key>.md`.

**Family registry (after round 0):**

| family | mechanism | status | signal | blocked-reason |
|---|---|---|---|---|
| f1 | DAG validation & unit acceptance | exhausted | strong (T1 crash, T2 S1-sibling, T3 old-DAG AA-trigger) | — |
| f2 | main-chain selection & stability | exhausted | strong (T-f2-01 MySQL divergence, T-f2-02 race crash) | — |
| f3 | signature & authentifier verification | exhausted | negative (malleability refuted, pubkey fail-closed, unsigned refused on all paths) | — |
| f4 | definition language / smart addresses | exhausted | negative (S1 migration complete here; T1 refuted by spend-time revalidation) | — |
| f5 | formula / oscript evaluation | live (report pending) | — | — |
| f6 | divisible assets | exhausted | negative (precision held via MAX_CAP; SQL held; spend-proof architectural) | — |
| f7 | indivisible assets | exhausted | strong (C1 crash, triple-sourced) | — |
| f8 | private payments & spend proofs | live (report pending) | — | — |
| f9 | network protocol | exhausted | weak (T1 unbounded streaming — DoS class; no crash-on-crafted-message) | — |
| f10 | storage, catchup, proof chains | exhausted | weak (T1 merkle-proof vacuously satisfiable — engine semantics; catchup anchored) | — |
| f11 | AA engine (in ocore) | exhausted | negative (forged-AA refuted 3 layers; disjuncts present; R1-A/R1-B weak) | — |
| f12 | encoding & hashing | exhausted | negative (canonicalization total; -0 handled) + latent (T2 type-string divergence) | — |
| f13 | races & TOCTOU | exhausted | strong (T-A crash — same as f1-T1; T-B stability race) | — |
| f14 | fail-open error handling | exhausted | strong-shape (T1 missing return — definite control-flow bug) | — |
| f15 | composer & signing | exhausted | weak (T1 signed_message no-validation; T2 light hub-position trust) | — |
| f16 | economics & misc | exhausted | strong (T1 tps-fee Infinity/balance poisoning — reachability open; T2 future-timestamp fee inflation) | — |

**Orchestrator adjudication — round-0 harvest (14 reports read, 2 pending):**

### Tier A — candidates for round-1 confirmation (PoC) + refutation

1. **A1 — private divisible-asset double-spend → uncaught throw → full-node crash (TRIPLE-SOURCED: f1-T1, f7-C1, f13-T-A).** `validation.js:2276-2280` `onDone` throws when a private-asset double-spend conflict is found and `!conf.bLight`. The throw is in a completion callback → escapes async → `network.js:4367` uncaughtException handler re-throws → process death. Crash-loop persists via `unhandled_private_payments` re-validation on restart (f7). The 05f291d8 fix gated the throw on `!conf.bLight` — the full-node sibling was NOT fixed (the light path got the clean rejection; full node kept the crash). Entry: private elements via chat path (`network.js:2269/2333`; direct `private_payment` ws command is dead code per f9-H8 — verify the reachable entry in PoC). **DoS-coordination classification: judgment call** — crashing unit is invalid (all nodes agree); node-side catch fixes it (out per strict rule) BUT the crash-loop is network-wide and persists until every operator patches (in-scope class). Escalate to operator decision after PoC.
2. **A2 — `+competitor_units.sequence='good'` unary-plus on TEXT column → Oracle MySQL coercion → divergent final-bad resolution → ball-hash divergence (f2-T-f2-01).** Verified correct on sqlite + MariaDB; Oracle MySQL coercion is documented but untested here. Consensus-critical IF MySQL nodes participate. Round-1: confirm MySQL semantics (documented behavior + SQL standard) and the production DB mix question.
3. **A3 — stability-advance race: `throw Error("earlier unit is no longer on main chain")` after lock wait (f2-T-f2-02 / f13-T-B).** Reorg during the lock queue → uncaught throw → crash OR handleJoint lock leak → permanent liveness stall. Needs a lab race demo; window is narrow (single-writer serialization).
4. **A4 — tps-fee settlement → exp() blow-up → author balance poisoning (f16-T1).** `getFinalTpsFee = round(base * (exp(tps) - 1))`, elapsed=1 on equal timestamps, count≥30 → fee ≥ 10% of total supply; count≥709 → Infinity → `tps_fees_balance` plunges negative → author permanently frozen. **Open reachability:** the spamming author's own last unit must declare a fee they can afford (self-limiting); needs lab measurement + economics (200%-expense rule).
5. **A5 — `validateAATrigger` `count_primary_aa_triggers > 1` rule LACKS the S1 disjunct (f1-T2).** The one non-disjunct sibling found (f4/f7/f11 confirmed migration complete elsewhere). Permanent-reject branch only fires on `last_ball_mci >= pemCurvesFixMci`; old-DAG-with-ball attachment bypasses on nodes behind. Cross-node acceptance divergence.
6. **A6 — old-DAG AA-trigger validation skip (f1-T3 + orchestrator spot-check).** `validateAATrigger` outer gate `last_ball_mci < v4UpgradeMci || bAA || !last_ball_mci` — genesis-attached units (`!last_ball_mci`) skip ALL trigger validation, making the hardened disjuncts unreachable for exactly the units they cover. Impact gated on AA engine processing (f11 says multi-trigger handling is bounded).

### Tier B — engine-semantics / medium leads

7. **B1 — `is_valid_merkle_proof` vacuously satisfiable (f10-T1).** Proof root attacker-supplied, never bound to a committed tree; `proof = "0-" + base64(hash(X))` always passes. Contrast `in merkle` (root bound to on-chain feed). In-scope AA engine (SF-9/SF-10); impact conditional on AA usage.
8. **B2 — `handleSavedPrivatePayments` missing return after catch (f14-T1).** Error path continues processing; double-cb; undefined-hash event key; possible error-then-accept. Wallet sibling (wallet.js:1029-1031) has the return — missed-return confirmed by comparison.
9. **B3 — future-timestamp fee-multiplier inflation (f16-T2).** `getRecentTps` counts future-dated units, `getCurrentTps` excludes them → attacker inflates `min_acceptable_tps_fee` multiplier to 5× network-wide. Real-but-capped (griefing; likely below $1k floor).

### Tier C — latent hazards / cross-family (registry)

10. **C1 — Decimal-vs-Number string-form divergence in formula hashing (f12-T2).** `sha256(12345678901234567)` differs Decimal vs Number (measured). Deterministic per node today; latent split if typing diverges; live AA-correctness trap. → f5.
11. **C2 — nonserial units skip authentifier re-verification (f3-T5).** Trusts ball integrity + prior serial validation; needs f2/f10 ball-anchor adjudication.
12. **C3 — definition-change race (f3-T6/f4-T4).** validation.js:1484 comment: "todo: investigate if this can split the nodes". Pending-definition spend race; active code rejects duplicates; low-probability.
13. **C4 — temp_data fee trusts claimed data_length (f12-T5).** Underpaid fee if unreconciled; needs f1/f16 confirmation.
14. **C5 — AA-path unstable-feed reads with "sort randomly" tie-break (f12-T6).** Node-dependent AA state if state transitions read unstable feeds; needs f5/f11.
15. **C6 — validation.js:741 non-AA-parent gate lacks disjunct (f11 cross-flag).** "allows what the rule forbids" — old-DAG units may have all-AA parents.
16. **C7 — light-mode hub-position trust (f15-T2).** Hub-chosen parent position → S1 rule bypass for light-composed units.
17. **C8 — signed_message signing path skips validation (f15-T1).** Needs user confirmation + a signed_message consumer; weak.

### Tier D — held / refuted negatives (recorded, high value)

- **D1 — JS Number on money: held on validation path.** MAX_CAP=9e15 < 2^53 bounds every amount and total (f1-T5, f6-T2, f7). The goal-prompt seam is contained on the asset path; residual = formula (C1) + fee math (A4/B3).
- **D2 — Signature: malleability refuted (high-S rejected, tested), pubkey fail-closed, unsigned-refusal verified on all 3 delivery paths (f3).**
- **D3 — Forged AA unit injection: refuted at 3 layers (f11).**
- **D4 — Catchup trust chain: anchored at every layer (f10-T3); merkle proof sound where root is feed-bound (f12-N6).**
- **D5 — Canonicalization: total + deterministic; -0 handled everywhere (f12-N3/N4).**
- **D6 — Definition language: S1 migration complete; spend-time revalidation closes old-DAG definitions (f4).**
- **D7 — No crash-on-crafted-message in the network layer (f9-H4) — the only crash classes are on invalid units (A1) and a narrow race (A3).**
- **D8 — Money arithmetic in divisible/indivisible asset paths held (f6/f7); cap/denomination integrity enforced; issue authz held.**

**Primitive registry:**

| primitive | pre-auth source? | sink | reach / cap | composes-with | status |
|---|---|---|---|---|---|
| A1 private-double-spend crash | network (chat-delivered private elements) | uncaught throw → crash | full node, all nodes processing | crash-loop persistence | candidate (triple-sourced) |
| A2 MySQL sequence coercion | unit content (author-controlled) | ball-hash divergence | DB-backend-dependent | consensus divergence | candidate |
| A4 tps-fee exp blowup | unit rate + timestamps | tps_fees_balance poisoning | economics-bound | fee freeze | candidate |
| A5 multi-trigger gate gap | old-DAG attachment | AA trigger validation skip | node-state-dependent | A6 | candidate |

**Round ledger (hypotheses opened/closed):**
- R0.0: 16 families live → 14 reports adjudicated, f5/f8 pending.
- R0.1: A1/A2/A3/A4/A5/A6 to round-1 PoC/refute. B1/B2/B3 to adjudication (engine semantics). C1-C8 registry. D1-D8 held.

## Round 1 — PoC + adversarial refutation (2026-08-11)

**Launch:** 6 builders (p1,p2,p4,p6,p8,p9) + 2 fresh-context refuters (r1 crash family, r2 MySQL+fee).

**Resolved so far:**

- **p9 CONFIRMED_SIGNAL** — `is_valid_merkle_proof` vacuously satisfiable (real formula engine):
  4/4 arbitrary elements pass with attacker-chosen root; `in merkle` contrast fails without a posted
  feed; bonus: the e01ba3e sibling-cap is bare-mci gated (60-sibling proof rejected above fix MCI,
  accepted below) — S1 family at the eval side. → FINDING candidate (engine footgun, usage-capped).
- **p4 REFUTED** — f2-T-f2-01 demoted: `+sequence='good'` executed on sqlite/MariaDB/MySQL8/MySQL5.7
  matches only 'good' everywhere (unary plus coerces only pure-integer strings). Residual = hygiene
  note (5 sites), not reportable. Lesson recorded: SQL semantic claims must be executed.
- **Orchestrator sqlite test (r2's script):** -Infinity persists in the INT column; min-fee gate
  rejects poisoned authors forever (finite -1.07e13 also permanent). P6 mechanics: fee math ✓,
  sqlite persistence ✓, gate permanence ✓ — reachability + economics pending p6.
- **Orchestrator timestamp analysis:** no past bound on unit timestamps (only +5s future) → attacker
  can set their unit's timestamp equal to the previous MC unit's → elapsed=1 controllable; linear
  chain of 30 units → count=30. The self-limiting economics (declared fee for late flood units) is
  the open question.
- **p1/p2/p6/p8/r1/r2: in flight** (crash PoCs are the hardest — real private-payment composition
  against a custom-genesis lab ledger).

**Primitive registry update:**

| primitive | status | composes-with |
|---|---|---|
| p9 merkle vacuous satisfiability | confirmed (real path) | AA logic (out-of-scope AAs = cap) |
| p9b S1-gated sibling cap | confirmed (real path) | old-DAG family |
| p4 sequence coercion | REFUTED | — |
| crash family (1662/1678/2289/2449) | pending p1/p2 | crash-loop persistence |
| tps-fee poisoning | mechanics confirmed; reachability pending p6 | T2 multiplier inflation |
| S1 old-DAG gating (741/986-992/1025-1028 + formula eval) | pending p8 | all old-DAG payloads |

## Round 1 complete — orchestrator adjudication (2026-08-11)

**Harvest after adversarial round (all PoCs executed on the real path; all refuters fresh-context):**

| candidate | verdict | decisive control / evidence |
|---|---|---|
| crash 1667 "spent from another address" | **REFUTED** | address-binding validation.js:1557-1568 precedes (single-authored: address rejected; multi-authored: must be an author → guard can never fire) — r1 |
| crash 2292 "spend proof didn't help" | **REFUTED** | message-level validateSpendProofs preempts every included conflict; handleJoint serialization kills the race; missing spend_proofs rejected (1613-1616) — r1 + p2 exp-a |
| crash 1686 "unreachable code" | **REFUTED as attacker-reachable** | state machine: temp-bad only on is_stable=0; markMcIndexStable resolves all temp-bad at mci before addBalls; advanceMcStability is 1-mci-at-a-time → balled-mci temp-bad impossible. p2's EXIT=1 crash ran on a synthesized unreachable state (p2 honestly flagged this residual). Reorg corner unproven → hardening note |
| crash 2451 "stable temp-bad output" | **REFUTED** | same state argument |
| **F3 invisible fork** (f8-TRIPLE-2) | **CONFIRMED empirically** (r1 exp: A_own saved while victim's spend_proofs row exists) | spend-proof address attacker-chosen, never unit-level validated → doublespend invisible to the standard check, resolution deferred to fork race → payment-race finding |
| P4 MySQL `+sequence='good'` | **REFUTED** | empirical on sqlite/MariaDB/MySQL8/MySQL5.7: unary-plus coerces only pure-integer strings; DECISIVE: conf.js:66-68 "mysql is not currently supported" (2026-07-11) — unsupported deployment. Residual: latent hygiene hazard |
| **F4 tps-fee poisoning** | **real-but-capped** | finite poisoning CONFIRMED real-path (count=30/elapsed=1 → fee 106,865 GBYTE = 10.7% supply; honest author −106,865; gate hard-rejects after). Infinity unreachable (funding bound caps count≈33). Permanence partial (repayable debt). Economics: ~1:1 scatter damage below 200%-expense bar; whale >213k marginal |
| **F2 signed-package S1 bypass** | **CONFIRMED mechanism** | 7a max_complexity 0-vs-10; 7b acceptance divergence (same package accepted below fix MCI, rejected above); 7c 60 calls below vs 3-cap above. Old-DAG attachment statically passes validation (no recency requirement; team's own commits confirm the class). **Open link: trigger stabilization** (needs network PoC) |
| **F1 merkle vacuous** | **CONFIRMED** | 4/4 vacuous proofs true on the real formula engine; `in merkle` contrast fails without posted feed; 60-sibling cap S1-gated (skipped below fix MCI) |

**Survivors → round 2 (independent runs + kill-pair + chainability):**
- F1: independent reviewer runs p9. Severity: engine footgun, usage-capped → Medium.
- F2: independent reviewer runs p8; kill-pair on the stabilization link (can an old-DAG-attached trigger stabilize?). Medium availability.
- F3: independent reviewer runs r1's exp; kill-pair bug-vs-design framing. Low/Medium payment race.
- F4: independent reviewer runs r2's fee drive; severity = below-bar real-but-capped → Low (report as robustness/economics finding).

**Demoted/closed:** crash family (4 sites) — hardening note; P4 — closed; f1/f7/f13 crash claims — refuted (lesson: synthesized-state PoCs must prove state reachability); f8 TRIPLE-1 — refuted (address-binding).

## Round 2 — independent runs + kill-pair + link + chainability (2026-08-11)

**Standing gate honored:** every confirmed PoC got an independent fresh-context run reading RAW output.

| id | verdict | note |
|---|---|---|
| IR-F1 (p9 merkle) | **CONFIRMED** | 4/4 vacuous true, controls correct, independent cross-construction; row-10 precision + S1-reachability nuances flagged |
| IR-F2 (p8 signed-package) | **CONFIRMED** | 7a/7b/7c reproduce; real crypto; no reward-hacking |
| IR-F3 (invisible fork) | **CONFIRMED** | independent DB read: two rows same P, attacker unit saved 'good'; contrast rejected |
| IR-F4 (tps-fee) | **CONFIRMED** | fee/balance/gate/-Infinity all verified; -Inf persists as REAL -Inf across pool reopen |
| KP-F2-link (S1 stabilization) | **S1 FAMILY DEAD** | witnessed level ancestry-derived; best-parent sorts by it; MC walk from tip; every eval path current-mci. F2/A5/A6/f1-T7/P9-bonus all unreachable → hardening note |
| CHAIN-1 (composition) | **F3 bounded / temp_data refuted / S1 family = durable form** | input-layer equivalence argument (later partially overturned by KP-F3-establish: private payload flow can't run the input check network-wide) |
| KP-F3-establish | **F3 real defect (Low-Medium)** | the only network-wide private double-spend protection is the spend-proof check; address-keyed → defeated; two 'good' same-proof units can coexist unresolved; private-vs-public asymmetry undocumentable |
| KP-F3-kill | pending | — |

**Findings promoted:** obyte-2026-08-001 (merkle, Medium) — 6/6 gates; obyte-2026-08-004 (tps-fee, Low) — 6/6 gates.
**Closed:** crash family (unreachable states), MySQL divergence (empirical + conf.js), temp_data (reconciled), S1 old-DAG execution family (stabilization dead).

## Tier-C registry — final dispositions (2026-08-11, 100%-exhaustion audit)

| lead | origin | final disposition | decisive control |
|---|---|---|---|
| C1 Decimal-vs-Number string divergence in formula hashing | f12-T2 | **latent hazard, closed** | deterministic per node today; typing is on-chain-determined; no live divergence path (f5 R3/R4) |
| C2 nonserial units skip authentifier re-verification | f3-T5 | **held** | ball integrity + serial-validation anchor (f3 T5; f10 T3 catchup anchored) |
| C3 definition-change race ("can this split the nodes") | f3-T6/f4-T4 | **held** | active code rejects duplicates; pending-change semantics resolve at last_ball_mci (f4 T4) |
| C4 temp_data fee claim | f12-T5 | **REFUTED** | validation.js:1983 reconciles data_length vs actual (CHAIN-1 angle 4) |
| C5 unstable-feed reads in AA state | f12-T6 | **closed** | AA state transitions read stable data (f11 held 9); getter/state paths verified |
| C6 validation.js:741 non-AA-parent gate | f11 cross-flag | **closed** | era-consistency for never-stabilizing units (KP-F2-link) |
| C7 light-mode hub-position trust | f15-T2 | **bounded** | S1 family dead (KP-F2-link); light model trusts hub by design |
| C8 signed_message signing path skips validation | f15-T1 | **bounded** | requires user confirmation + a signed_message consumer; wallet-side UX gate (f15 assessment) |
| f16-T2 future-timestamp fee multiplier | f16-T2 | **real-but-capped** | source-confirmed asymmetry (getRecentTps vs getCurrentTps); below the $1k floor (griefing) — hardening note |
| f9-T1 unbounded joint streaming | f9-T1 | **out-of-scope class** | node-side cap resolves; no rate limiting anywhere — hardening note |
| f7-C4 blinding logged to console | f7-C4 | **privacy observation** | not on the program's impact list (no fund loss/freeze) — note for operator |
| f6-T5 duplicate private payment re-process | f6-T5 | **weak, closed** | dedup fires when address visible; no theft path (f6) |
| f11-R1-B light-vendor AA definition insert | f11-R1-B | **bounded** | wallet-side, hub-trusted by design; consensus path unaffected |
| f14-T1 missing return in handleSavedPrivatePayments | f14-T1 | **control-flow bug, impact unclear** | definite missed-return (wallet sibling has it); error-then-continue + double-cb; no fund path demonstrated — hardening/robustness note |

All leads adjudicated; nothing remaining is a live consensus/fund finding. The final harvest:
F1 (Medium, promoted), F4 (Low, promoted), F3 (pending kill-pair), plus hardening notes.
