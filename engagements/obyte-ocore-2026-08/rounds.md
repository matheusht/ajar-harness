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
