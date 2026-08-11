# Round E2 briefs — obyte-ocore-2026-08 (directed escalation with the two-node lab)

After E1 + ER review. The two-node lab (evidence/lab/e17b-run.js, hub:6611 + node:6612, real relay
protocol, stability + balls verified) is the primary tool. Full persistence; every claim needs
file:line + raw evidence; caps must be proven.

## E2-1 — FEE-ACCOUNTING EMPIRICAL (retry E1-1; the money-creation question)
Drive the REAL settlement path end-to-end (fix the caches_ready wait by polling, per E1-1's
partial): (1) confirm conservation on the happy path (declared burned from inputs, delta-only
settlement, net cost = final); (2) TEST the double-application candidate directly — call the
settlement paths in the orders the writer/stabilization produce and check no (address, mci) delta
applies twice; (3) test the estimation-asymmetry refund: declare D at a high local estimate
(flood first), then let the window settle low — measure the balance credit; (4) any sequence
where balance increases without a matching input burn. Report evidence/roundE2/E2-1.md.

## E2-2 — VULNERABLE-AA DEMO (retry E1-3; F1 fund-impact class)
Build a realistic whitelist-gated AA (withdrawal only for merkle-tree members) on the lab; call the
withdrawal with the vacuous proof; show the AA's funds move (synthetic). Use the real formula
engine inside the real AA trigger path (aa_composer) or the direct evaluation path if the AA
trigger wiring is not yet lab-supported. Report evidence/roundE2/E2-2.md.

## E2-3 — ISSUEASSET CAP PRECISION (retry E1-6)
aa_composer.js:1180-1190 issue_amount math at the 2^53 boundary: can an AA issue more of its own
asset than the cap? Trace the validation-side cap check (does the ledger re-verify the issued
amount?). Construct the boundary case (cap near 2^53, amounts straddling). Report
evidence/roundE2/E2-3.md.

## E2-4 — F4 FLOOD END-TO-END ON THE TWO-NODE LAB (retry E1-9)
Using evidence/lab/e17b-*: post ~30 units with equal-second timestamps through the real relay +
validation + stabilization on the node; measure the settlement fee and the poisoned balances
end-to-end (the window count = real MC units). Report evidence/roundE2/E2-4.md.

## E2-5 — ISSUE SPEND PROOF REUSE (retry E1-16)
The issue-type spend proof hash({asset, amount, address, serial_number}) has no unit/output
binding: test reuse across units (per-unit spend_proofs rows — can the same issue proof appear in
two units with the per-unit keying containing it? what does the doublespend query catch?). Report
evidence/roundE2/E2-5.md.

## E2-6 — AA TRIGGER EXECUTION ON THE TWO-NODE NETWORK
The lab now stabilizes units; the remaining gap is AA trigger execution at stabilization. Wire an
AA trigger through: post a paying unit that triggers an AA, confirm handleAATriggers fires at
stabilization, and the AA response is composed + propagated. Deliverable: the complete AA path on
the network (feeds E2-2 and any AA-conditional escalation). Report evidence/roundE2/E2-6.md.

## E2-7 — F3 DISPLACEMENT EMPIRICAL (the E1-2 claim, on the real network)
On the two-node lab: victim spend C, attacker ghost A as a direct descendant with a ground
timestamp; measure which unit holds the MC position and whether the attacker's grind
(unit-hash content control) reliably displaces C. Confirms or refutes E1-2's "reliably
attacker-winnable" claim empirically. Report evidence/roundE2/E2-7.md.

## E2-8 — HN-5→PARENT-COMPOSER CHAIN EMPIRICAL
The chain: future-timestamp units (valid, cheap) → getRecentTps inflation → fee multiplier 5 →
local fee estimate rises → filterParentsByTpsFeeAndReplace excludes all parents → composition
crash. On the lab: post future-dated units, verify getRecentTps > 15, then compose a unit and
observe the parent filter decisions (throw or fallback?). Report evidence/roundE2/E2-8.md.

## E2-9 — NATURAL-BURST F4 (no attacker)
On the two-node lab: 20 units in one second (a mass-claim pattern) — measure the settlement fees
of the early units (validated at the calm estimate, settled at the burst rate) and the resulting
balances. Quantify the small-author freeze (E1-3/LR-3 said single-digit GBYTE — verify). Report
evidence/roundE2/E2-9.md.

## E2-10 — ESTIMATION-ASYMETRY REFUND PATH
The estimation applies tps_fee_multiplier (10) while settlement does not: declare at the high
estimate, settle low — measure the balance credit and check whether the credit can be converted to
real spend (the balance is spendable for fees; can it be withdrawn?). Any asymmetric gain?
Report evidence/roundE2/E2-10.md.

## E2-11 — WITNESS-ROUNDING DUST (E1-10 residual)
The witness-rounding dust (Math.floor(delta*share/100) per recipient): measure whether the
rounding is truly zero-mean or can be biased by choosing shares (e.g., 33/33/34) and deltas to
accumulate dust in a chosen address. Dust per unit is < 1 unit; at scale (attacker floods many
units) does it accumulate meaningfully? Report evidence/roundE2/E2-11.md.

## E2-12 — LIGHT-VENDOR HANDSHAKE (E1-14 O-notes)
prepareHistory/processHistory + the light get_* commands: any fund-adjacent flaw in what the
vendor serves to light clients (balances, addresses, definitions, private payments)? Trust-model
notes allowed; report fund-impact candidates only if they cross the trust boundary. Report
evidence/roundE2/E2-12.md.

## E2-13 — ARCHIVING EDGE
archive-then-respend, the unspend queries (archiving.js:107-160), void-vs-remove: can a unit spend
an output that was archived (archived outputs reusable?), or double-claim after a reorg-void?
Report evidence/roundE2/E2-13.md.

## E2-14 — GOVERNANCE VOTE ECONOMICS
system_vote_count / SYSTEM_VOTE_COUNT_FEE (1e9): can an attacker cheaply swing op_list or fee
parameter votes (threshold_size, base_tps_fee, tps_interval, tps_fee_multiplier)? What are the
vote-counting rules (countVotes, emergency changes) and the cheapest attack? Economic/governance
attacks are out of scope per the program — report the economics anyway (feeds F4's parameter
dependence: a governance vote could change the fee curve). Report evidence/roundE2/E2-14.md.

## E2-15 — EXCHANGE-INTEGRATION SURFACE
The wallet.js/light.js APIs an exchange integration would use (balances, history, receiving,
withdrawals): any integration-level flaw (balance misread, race between balance display and
settlement, the F4 poisoning hitting exchange hot-wallet balances)? Report
evidence/roundE2/E2-15.md.

## E2-16 — CRASH-LOOP PERSISTENCE (the Q-1/device-crash escalation, quarantine-level)
The device-layer scheduled throw (device.js:431-432): build the delivery loop (hub mailbox → wallet
processing) and demonstrate the crash-loop persistence (re-delivery re-crashes). Quarantine-level
(no promotion without the operator's scope decision) — but the maximum-impact PoC must be ready if
the operator widens scope. Report evidence/roundE2/E2-16.md.

## Output contract
Report to evidence/roundE2/<id>.md; return JSON {id, claim, verdict: escalated | capped | refuted
| needs_review, decisive_control_or_evidence, cap_proven}. Real-path discipline. No live network.
No secrets.
