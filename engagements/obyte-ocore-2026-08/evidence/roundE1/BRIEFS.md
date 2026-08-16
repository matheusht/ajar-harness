# Round E1 briefs — obyte-ocore-2026-08 (cascading/escalation/chainability, full persistence)

Launched 2026-08-11. Big-picture step-back completed by the orchestrator; these are the escalation
lanes. **Every claim needs file:line; a cap must be PROVEN, never asserted; the marginal-contribution
critique applies to every escalation (severity = the delta the bug adds, never the total nearby).**
Round structure: 16 escalation hunters → 4 fresh-context reviewers verify every claim → orchestrator
adjudicates → next round.

## The confirmed findings being escalated

- **F1 (obyte-2026-08-001, Medium):** formula `is_valid_merkle_proof` vacuously satisfiable (root
  from the proof itself; any AA using it for membership is bypassable).
- **F3 (obyte-2026-08-003, Low):** spend-proof uniqueness keyed on a party-chosen address — the only
  network-wide private double-spend detection is defeated; two 'good' same-proof units coexist on
  the MC path (ghost IS on-MC — LR-2 verified MC indices 1 and 2).
- **F4 (obyte-2026-08-004, Low):** settlement tps-fee exponential/unbounded vs balances; a 30-unit
  1-second window charges 10.7% of the supply per settling author.
- **Q-1 (quarantined):** remote wallet crash via device-message decryption (device.js:431-432) —
  adjacent surface; escalation work on it stays quarantine-level (no promotion without operator).

## Escalation lanes (16)

### E1-1 — FEE-ACCOUNTING CONSERVATION AUDIT (highest-value lane — potential money creation)
Trace the FULL tps-fee lifecycle end-to-end: (1) where is the DECLARED fee debited — from inputs
(validation.js:2649-2653 funds it) or from tps_fees_balance? (2) the settlement delta
`tps_fees_balance + (declared - final)` (storage.js:1246-1261) — is the declared fee ever debited
from the balance before the delta is applied? (3) if declared > final, the delta is POSITIVE — who
gets credited, and does the credit double-count what the inputs already paid? (4) tps_fee_recipients
(validation.js:1070-1092, storage.js:1458-1470) — where does the declared fee go? (5) negative
balances, initial seeding, and recovery. **Question: can ANY declared/final sequence create value,
enrich the attacker, or double-credit?** A money-creation proof = Critical. Report
evidence/roundE1/E1-1.md with the full accounting table.

### E1-2 — F3 fork-race win analysis
Source-trace the MC race between the victim's spend C and the attacker's ghost A (both 'good', both
spending X): what decides the winner (best-parent witnessed level, timing, OP waypoints,
parent anchoring)? Can the attacker RELIABLY win the race (e.g., by anchoring A on the tip and
delaying C)? Feeds the merchant-exposure ceiling: if the attacker can reliably win, F3's ceiling
rises toward Medium/High (merchant defrauded). If the race is fair, the ceiling stays Low.
Report evidence/roundE1/E1-2.md.

### E1-3 — F1 vulnerable-AA demonstration (fund-impact class)
Build a realistic whitelist-gated AA in the lab: an AA whose init/response formula uses
`is_valid_merkle_proof` to gate a payment (e.g., "only members of the merkle tree may withdraw").
Demonstrate the bypass end-to-end: the attacker's vacuous proof passes the gate and the AA's funds
move. This shows the fund-impact class without auditing real AAs (out of scope). Also document that
the e01ba3e sibling-cap never mitigated the vacuous case (0 siblings suffice). Report
evidence/roundE1/E1-3.md.

### E1-4 — F1 sibling sweep: all prover-supplied verification primitives
Sweep the formula language AND definition language for every verification primitive whose inputs are
prover-supplied: is_valid_sig, vrf_verify, is_valid_signed_package, is_valid_merkle_proof,
is_valid_address, hash predicates (definition.js 'hash', formula sha256/chash160), in merkle.
For each: is the root/commitment bound to an anchored value or prover-chosen? Verify each is sound
or find another unsound one (escalation move 7 — one-off → class). Report
evidence/roundE1/E1-4.md with a per-primitive table.

### E1-5 — parent_composer crash lane (incidental finding from round 1)
r1's lab crashed during bring-up on parent_composer.js:461 "all potential parents underpay the tps
fee". Investigate: (1) what triggers the throw; (2) is it reachable from attacker influence (a
wallet composing against attacker-influenced state? a node composing AA responses?); (3) impact
(client crash? node crash?); (4) is it the same uncaught-throw pattern (HN-2)? Report
evidence/roundE1/E1-5.md.

### E1-6 — AA issueAsset cap-boundary precision (f11-R1-A open lead)
aa_composer.js:1180-1190 — the issue_amount math `objAsset.cap || (target_amount - total_amount)`
on JS Number at the 2^53 boundary: can an AA issue MORE of its own asset than the cap (or than the
intended amount) via precision loss? What does validation check (does the ledger re-verify the
issued amount against the cap)? If an AA can exceed its cap → new asset supply → fund impact.
Report evidence/roundE1/E1-6.md.

### E1-7 — TWO-NODE LAB BUILD (the missing infrastructure)
Build the multi-node local Obyte network: two full-node processes, synthetic genesis with OP/witness
keys, witness simulation, connected as peers. Deliverable: a working two-node lab with a witness
that stabilizes units (or a documented blocker with the exact failing step). This unlocks
empirical proof for E1-2 (race), E1-9 (flood), the KP-F2-link stabilization claim, and the reorg
corner. Reuse evidence/lab/lab.js patterns. Report evidence/roundE1/E1-7.md with run instructions.

### E1-8 — F3 merchant-exposure end-to-end
Using the lab (E1-7) or the single-node simulation: victim spends X (merchant accepts on
inclusion), sender publishes the ghost, both units 'good' on the MC path — demonstrate the
merchant's node state (no rejection signal, both units shown) and the race outcome. Quantify the
exposure window. Report evidence/roundE1/E1-8.md.

### E1-9 — F4 end-to-end flood (real validation + stabilization path)
30 units with equal-second timestamps through REAL validation + save + stabilization (not the
synthetic storage drive from round 1): measure the settlement fee and the poisoned balances
end-to-end. Uses the E1-7 lab if ready; otherwise the real-path single-node drive. Report
evidence/roundE1/E1-9.md.

### E1-10 — tps_fee_recipients + paid-witnessing earnings chain
Where does the DECLARED fee go (recipients' balances — validation.js:1070-1092,
storage.js:1458-1470)? Can the F4 poisoning, the estimation asymmetry (multiplier 10 estimation vs
settlement), or the recipient-split math enrich a chosen recipient (e.g., the attacker names
themselves a recipient)? Is the recipients' share math exact (shares sum 100)? Report
evidence/roundE1/E1-10.md.

### E1-11 — AA storage-size economics
updateStorageSize (aa_composer.js:1517-1555), state-var length caps, checkStorageSizes: can an AA
grow its state beyond its byte balance (state growth unbounded) or shrink it to steal the
difference? Is the storage-size accounting conserved when state is deleted? Report
evidence/roundE1/E1-11.md.

### E1-12 — Multisig wallet paths (never audited)
wallet_defined_by_addresses.js + wallet_defined_by_keys.js deep audit: cosigning flows,
definition-change handling, threshold semantics in the WALLET layer, address→definition resolution
races, signing order determinism. Wallet-side (out of DLT scope per the operator) — report
findings as hardening or quarantine candidates, flag scope. Report evidence/roundE1/E1-12.md.

### E1-13 — CHAIN GRAPH PASS (verified edges only)
Build the cross-finding composition graph with VERIFIED output→precondition edges (escalation move
6 — every edge needs file:line): (1) F3 ghosts on-MC → do they count in getFinalTps windows
(CHAIN-1 said off-MC — LR-2 says on-MC; SETTLE IT — storage.js:1178-1218 count logic) → F4
composition; (2) F1 → AA funds (E1-3); (3) F4 poisoning → F3 merchant exposure (poisoned author
can't contest?); (4) Q-1 device crash → anything (hub-side); (5) any 2-hop path. Each edge: does
A's concrete output satisfy B's concrete precondition? Report evidence/roundE1/E1-13.md.

### E1-14 — BIG-PICTURE RE-SCAN (fresh eyes on the whole tree)
A fresh hunter with the full engagement context (read rounds.md + findings): what SURFACE or LANE
did the 16 families + blind round collectively miss? Candidates to examine: wallet.js internals
beyond signing, data_feeds writers, initial_votes governance paths, archiving/reorg edge cases,
the light-vendor protocol handshake, exchange-integration surfaces, the hub's prepareHistory for
light clients, genesis/initial-db handling. Report: new lane or explicit none, with file:line.
Report evidence/roundE1/E1-14.md.

### E1-15 — THE REORG CORNER (closes the last crash-family question)
r1's residual: can a reorg (goDownAndUpdateMainChainIndex) ever assign main_chain_index <=
last_ball_mci to a previously-unballed temp-bad unit (making the 1686/2451 throws reachable)?
Trace the reorg path: what happens to temp-bad units' main_chain_index when the MC retreats; can a
re-advance place them at a balled MCI? Report evidence/roundE1/E1-15.md with the definitive answer.

### E1-16 — F3 issue-type spend proof (f6-T4 sibling, fresh eyes)
The issue-type spend proof is `hash({asset, amount, address, serial_number})` — NO unit/output
binding (f6-T4). Re-examine as an F3 sibling: can an issue-type proof be reused across units
(per-unit spend_proofs rows exist — does the per-unit keying contain it)? What breaks if the same
issue proof appears in two units? Report evidence/roundE1/E1-16.md.

## Output contract
Report to evidence/roundE1/<id>.md; return JSON {id, claim, verdict: escalated | capped | refuted |
needs_review, decisive_control_or_evidence, cap_proven}. A cap is only proven with the mechanism
that produces it (file:line). No live network. No secrets. Local only.
