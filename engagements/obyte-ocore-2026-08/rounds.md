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

## Round E1 — cascading/escalation/chainability (2026-08-11, 16 hunters, 5 timed out mid-experiment)

Big-picture step-back (orchestrator): money-creation lane (fee accounting), the missing two-node
lab, the incidental parent_composer crash, AA issueAsset precision, multisig paths, the F3→F4
chain edge.

| lane | verdict | decisive evidence |
|---|---|---|
| E1-1 fee accounting | **capped (orchestrator OV-1; E1-1 timed out mid-verification)** | declared fee burned from inputs (validation.js:2654-2656); delta-only settlement (storage.js:1246-1261); recipient override (storage.js:1458-1465); double-application candidate traced single-application under locks — ER-4 verifying |
| E1-2 fork race | **capped** | conflict machinery never fires on two 'good' units (main_chain.js:1292-1293); grind-space empirically confirmed (8 hashes); value ledger resolves to victim (divisible_asset.js:159) |
| E1-3 vulnerable-AA demo | TIMED OUT (partial) | retry E2 with the E1-7 lab |
| E1-4 F1 sibling sweep | **F1 is a one-off** | only primitive with a prover-supplied truth anchor; is_valid_sig/vrf/signed-package sound-as-stated (HN-12) |
| E1-5 parent_composer crash | **capped → HN-14** | throw empirically reproduced (16 exclusions → unhandled rejection); attacker-influenceable pool; node-side-fixable → out-of-scope class |
| E1-6 issueAsset cap precision | TIMED OUT | retry E2 |
| E1-7 two-node lab | **DONE — infrastructure built** | real relay protocol, real validation, stability + 7 balls on both nodes (evidence/lab/e17b-*) |
| E1-8 merchant exposure | **escalated exposure evidence** | direct-descendant ghost, unbounded window, no signal; Low ceiling intact |
| E1-9 flood e2e | TIMED OUT | retry E2 with the E1-7 lab |
| E1-10 fee recipients | **capped** | conserved; witness-rounding dust zero-mean, OP-only |
| E1-11 storage-size accounting | **held/capped + HN-13** | 16/16 shapes conserved; checkStorageSizes crash-on-mismatch (scheduled, not attacker-reachable) |
| E1-12 multisig wallet paths | **Q-2 quarantine candidate confirmed** | extended_pubkeys injection → permanent silent multisig-wallet DoS (device.js:214, wallet_defined_by_keys.js:361-378, no removal path) |
| E1-13 chain graph | **no escalation** | F3→F4 edge corrected (capability-neutrality, not MC status); no amplifier, no new finding |
| E1-14 big-picture re-scan | **explicit none** | 3 observations (wallet fee-estimation timing, light cache growth, Q-1 remains the only new crash class) |
| E1-15 reorg corner | **capped (definitively closed)** | retreat NULLs indices; re-advance above the join; resolution atomic with balling |
| E1-16 issue spend proof | TIMED OUT | retry E2 |

**E1 review round launched (ER-1..ER-4, fresh context):** fork-race + merchant exposure; parent
composer + storage accounting; multisig + F1 one-off; the orchestrator's fee-accounting
adjudication (incl. the double-application question — Critical if real).

**E2 plan (next):** retry the 5 timed-out lanes with the working two-node lab; AA trigger
execution on the network; empirical F3 displacement; HN-5→parent-composer chain; natural-burst F4;
estimation-asymmetry refund path; light-vendor handshake; archiving edge; governance vote
economics; exchange-integration surface.

## Round ER — E1 verification (2026-08-11, 4 fresh reviewers) — ALL VERIFIED

| review | verdict | key findings |
|---|---|---|
| ER-1 (E1-2 + E1-8) | verified | grind confirmed with nuances (isOP tier on mainnet before unit ASC — no-op for non-witnesses; ranking at main_chain.js:46-48; '8 hashes' lacks a raw artifact); value ledger resolves to victim; merchant exposure verified (raw log: A accepted, both on MC) |
| ER-2 (E1-5 + E1-11) | verified | crash intercepted by the lab handler (unhandled rejection observed, Node-default crash); LIMIT 16 + ordering + exclusion math verified (rate-change exposure: units paid at low-rate undercut the later min); flood reachability source-traced |
| ER-3 (E1-12 + E1-4) | verified | multisig DoS chain fully verified against source; F1 one-off confirmed |
| ER-4 (fee accounting) | verified | conservation verified; double-application: single-application in all direct paths (function boundaries, one-MCI-per-pass, monotonic watermark); ONE conditional residual — MySQL watermark `creation_date` tie-break can go stale across restarts → double-application (double-credit/debit); sqlite immune; MySQL unsupported → **hardening note (HN-15)**, no live money creation |

**E2 launched (16 lanes):** fee-accounting empirical, vulnerable-AA demo, issueAsset precision,
flood e2e on the two-node lab, issue spend proof, AA trigger on the network, F3 displacement
empirical, HN-5→parent-composer chain, natural-burst F4, estimation-asymmetry refund,
witness-rounding dust, light-vendor handshake, archiving edge, governance vote economics,
exchange-integration surface, Q-1 crash-loop persistence.

## Round E2 — directed escalation on the two-node lab (2026-08-11, 16 hunters, 3 timed out)

| lane | verdict | decisive evidence |
|---|---|---|
| E2-1 fee accounting | **RESOLVED — no money creation** | funding gates block un-funded declarations (A1/A2); conservation (A3: net = final); delta re-applies on double-call (C: caller discipline is the invariant); **double-application confirmed through the real reprocess path** (D: 1e6→2e6→3e6) → HN-15 real-but-conditional (MySQL watermark, sqlite immune) |
| E2-2 vulnerable-AA demo | TIMED OUT | retry E3 (E2-6's AA path now available) |
| E2-3 issueAsset cap | **REFUTED cap-exceedance** | validation total caps close the 2^53 window; residue = composer-side drift, self-inflicted |
| E2-4 flood e2e | TIMED OUT | retry E3 on the E1-7 lab |
| E2-5 issue spend proof | **capped** | mechanism confirmed; reachable case economically inert; value-bearing contained |
| E2-6 AA trigger on network | **CONFIRMED** | full AA path executes: definition→stabilize→aa_triggers→handleAATriggers→formula→deterministic response committed (identical hash both nodes) |
| E2-7 F3 displacement | TIMED OUT | retry E3 on the E1-7 lab |
| E2-8 HN-5→parent-composer | **chain refuted; crash confirmed** | future-dating doesn't hit the parent filter's rate source; the flood DOES → crash end-to-end (E1-5/HN-14) |
| E2-9 natural-burst F4 | **REFUTED (LR-3 corrected)** | composition throughput caps ~6/s; settlement elapsed dilutes tps ~3; the 10x estimation multiplier credits (not debits) the balance; F4 = attack-only, economics-capped |
| E2-10 estimation refund | **capped** | refund mechanism, no withdrawal, net = final (declared 1.068e15, final 17, net 17) |
| E2-11 rounding dust | **capped** | floor dust always destroys; half-up can create but OP-only or economically dead; E1-10 zero-mean imprecise |
| E2-12 light handshake | (read separately) | — |
| E2-13 archiving | **capped** | sound for double-claim/theft; NOT EXISTS guards; residuals hardening |
| E2-14 governance votes | **capped** | no escalation lane; 2 HN; F4 parameter-dependence bounded |
| E2-15 exchange surface | **capped** | no new mechanism; 3 integration-level consequences of existing findings |
| E2-16 Q-1 crash-loop | **escalated (evidence)** | remote zero-cost wallet crash, crash-loop persistence 3/3 cycles on the real path (bServeAsHub victims / stale-key edges); quarantine-level, operator's scope decision |

**E2-review round launched (4 fresh reviewers).** E3 plan: retry E2-2/E2-4/E2-7 with the working
AA path + two-node lab; then the terminal coverage review.

## Round ER2 — E2 verification (2026-08-11, 4 fresh reviewers) — ALL VERIFIED

- ER2-1: money-creation resolution confirmed (no money creation; HN-15 conditional MySQL
  watermark); 2 evidence-quality findings recorded (E2-10 writer-grep regex false negative; E2-1
  dead-code in final JSON) — conclusions stand, artifacts flagged.
- ER2-2: natural-burst refutation verified (composition cap 6.7/s measured; settlement window
  4-7s dilutes tps; credit direction verified with a tps_interval=60 magnitude caveat).
- ER2-3: Q-1 crash-loop verified 3/3 (exact raw log lines); delivery path real and remote.
- ER2-4: issueAsset/issue-proof/archiving caps verified.

**E3 launched (16 lanes):** vulnerable-AA demo on the working AA path, flood e2e, F3 displacement
empirical, the device-crash→restart→double-application chain, F1 fund-impact demo, Q-1 PoC
finalization, rounding quantification, AA→AA chains, AA-response fee interplay, exchange
hot-wallet F4, light-vendor fund path, recipient spend race, parent-composer blast radius, AA
self-redefinition, terminal coverage review, multi-asset private uniqueness.

## Round E3 — terminal escalation (2026-08-11, 16 hunters, 6 timed out mid-lab)

| lane | verdict | decisive evidence |
|---|---|---|
| E3-1 vulnerable-AA demo | **DELIVERED — F1 fund-impact** | attack → BYPASS-CONFIRMED (withdrawal 1000) vs control → bounce, on the real two-node network |
| E3-2 flood e2e | TIMED OUT | partial: the equal-timestamp flood hits the parent filter (future-stamped) — fix identified (WP-1 at T0-1, flood at T0, WP-2 at T0+1); retry E4 |
| E3-3 F3 displacement | TIMED OUT | partial: relay working, temp-bad control meaningful; retry E4 |
| E3-4 double-application chain | **attacker-triggerable in every link** but MySQL-unsupported + sqlite-immune | flood → same-second tie → device-crash on bServeAsHub → restart → stale watermark → reprocess; HN-15 confirmed with the full chain |
| E3-5 airdrop-claim demo | TIMED OUT | retry E4 |
| E3-6 Q-1 PoC finalization | TIMED OUT | retry E4 |
| E3-7 rounding | **capped** | paid-witnessing OP-only; hc minting real (+50) but economically dead (≥29 units/hop) |
| E3-8 AA→AA chains | TIMED OUT | retry E4 |
| E3-9 AA-response fee | TIMED OUT | retry E4 |
| E3-10 exchange F4 | **REFUTED F4 impact — DEMOTION** | M1: 1-MCI-at-a-time → count=1 (fee=17 every step, real path); M2: wall-clock elapsed dilutes honest units (4,917 base); E2-9 real-network: fees 0-190, balances +181, no negatives; r2 drive = synthesized-state error |
| E3-11 light-vendor | **trust-model-bound** | no fund-impact candidate crosses the hub-trust boundary |
| E3-12 recipient spend race | **capped** | no same-block race; balance-gate divergence window capped at behind-node junk |
| E3-13 parent-composer blast | **capped at Low client-availability** | HN-14 stands; not reportable under Primacy of Rules |
| E3-14 AA self-redefinition | **capped** | no redefinition/overwrite/re-wiring; churn bounded |
| E3-15 terminal coverage | **no new in-scope lane — COVERED** | full terminal coverage statement appended |
| E3-16 multi-asset uniqueness | **sound** | cross-asset reuse impossible (asset in the hash); same-asset double-claim rejected; cross-asset reference blocked |

**THE ESCALATION PHASE REFUTED ITS OWN FINDING:** obyte-2026-08-004 (tps-fee poisoning) DEMOTED —
the honest-author-freeze impact claim is unreachable (E3-10 M1/M2 + E2-9 real-network + orchestrator
source verification of the settlement ordering). The count>=30 state was a synthesized-state error
(the p2 lesson applied to our own finding). Residual: self-frosting economics, HN-15, fee-curve
design note.

**E4 (final round) launched:** F4 refutation review, attacker-cost measurement, F3 displacement,
airdrop-claim demo, F1/F3 package revisions, terminal severity audit, Q-1 PoC, AA→AA chains,
AA-response fee, lessons + memory + casebook + handoff packages, lifecycle re-run, covered-dry audit.

## Round E4 — final escalation round (2026-08-11, 16 agents, 5 timed out mid-lab)

| lane | verdict |
|---|---|
| E4-1 F4 refutation review | **demotion CORRECT**; M1 rationale needs correction (E2-9 produced count=22 — a real lag state exists; the true protections are M2 elapsed-dilution + funding bound + self-frosting) |
| E4-2 attacker cost | **REFUTED (inert) end-to-end** — real two-node network at mainnet parameters: no impact of any kind (attacker or victim); the trigger state is unreachable |
| E4-5 F1 package revision | revised — E3-1 fund-impact demo folded in; gates re-run |
| E4-6 terminal severity audit | **001 Medium (5.3) confirmed** (impact class demonstrated); **003 Low (3.7) confirmed** (ceiling); 004 demoted; NET severity change of the escalation phase = zero + one correction |
| E4-10 lessons package | drafted (5 cross-engagement lessons incl. the synthesized-state lesson applied to our own finding) |
| E4-11 memory disposition | finalized (PC-2/3/5 promote, PC-1/4 defer, casebook recommendation) |
| E4-12 casebook draft | scrubbed structure prepared |
| E4-13 operator handoff | assembled (findings + hardening + quarantine + coverage + submission framing) |
| E4-14 lifecycle re-run | gates pass for 001/003; 004 refutation recorded inside the package (re-promotion guarded) |
| E4-15 covered-dry audit | **COVERED-DRY** — 16 families + 48 escalation lanes exhausted; primitive registry disposed; blind round no new in-scope family; ladder lanes dry |
| E4-16 pattern promotions | PC-2/3/5 finalized; conformance re-run |
| E4-3/4/7/8/9 | timed out (lab) — coverage unaffected (per E4-15; the E3-1 demo + E1-2/E1-8 audits cover their questions) |

**E4-REVIEW round launched (4 fresh reviewers)** — final verification of: the demotion + M1
correction, the end-to-end flood refutation + severity audit, the lifecycle/conformance/handoff,
and the covered-dry audit.

## Round ER4 — E4 final verification (2026-08-11, 4 fresh reviewers) — ALL VERIFIED WITH CORRECTIONS

- ER4-1: F4 demotion CORRECT; M1 rationale corrected (E2-9 count=22 — a real lag state; the true
  protections are M2 elapsed-dilution + funding bound + self-frosting).
- ER4-2: E4-2's "fully inert" OVERSTATED and corrected: tps_interval=60 cache artifact (34/34 DB
  fees match interval=60); count=31 measured on the real path; elapsed=1 constructible (stamp at
  last_ball_ts+1, validation bounds only the future); the attacker CAN self-frost (~10.7% of
  supply on their own chain) — self-grief, out of program scope. NO VICTIM IMPACT → the 004
  demotion stands.
- ER4-3: lifecycle gates 6/6 CLEAR for 001/003; 004 refutation recorded in-package; conformance
  801/0 PASS; handoff accurate (cosmetic warts only).
- ER4-4: covered-dry VERIFIED for the declared in-scope surfaces; the F4-magnitude evidence
  quality corrected (tps_interval=60); demotion direction survives independent re-derivation
  (micro-GBYTE magnitudes at interval=1).

**CAMPAIGN TERMINAL STATE (escalation phase, 4 rounds + 4 review rounds):**
- 2 proven findings: 001 (Medium 5.3, fund-impact demonstrated), 003 (Low 3.7, ceiling confirmed).
- 004 unproven (impact refuted; mechanism = design note + HN-15 + self-frosting economics).
- Hardening: 20 items. Quarantine: Q-1 (crash-loop PoC ready), Q-2 (multisig DoS).
- Covered-dry verified. The escalation phase's net severity effect: zero changes to the standing
  findings, one self-correction (004 demoted), multiple evidence-quality corrections applied.
