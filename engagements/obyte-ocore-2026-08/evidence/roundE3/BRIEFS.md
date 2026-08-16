# Round E3 briefs — obyte-ocore-2026-08 (terminal escalation: retries + compositions)

After E2 + ER2. The AA path now runs on the two-node network (E2-6). The two-node lab:
evidence/lab/e17b-run.js (hub:6611 / node:6612). Full persistence; caps must be proven.

## E3-1 — VULNERABLE-AA DEMO (retry E2-2, now with the working AA path)
Use E2-6's confirmed AA trigger flow: define a whitelist-gated AA (withdrawal only for merkle-tree
members, gated by is_valid_merkle_proof), trigger it, and demonstrate the vacuous-proof bypass
moving the AA's synthetic funds end-to-end on the network. This is F1's fund-impact class.
Report evidence/roundE3/E3-1.md.

## E3-2 — F4 FLOOD END-TO-END (retry E2-4)
On the two-node lab: post ~30 units with equal-second timestamps through the real relay +
validation + stabilization; measure the settlement fee and poisoned balances end-to-end. Use
E2-9's measured composition-throughput (~6/s) to bound the real attack rate: can an attacker reach
count>=30 in a 1-second elapsed window given the throughput cap? Report evidence/roundE3/E3-2.md.

## E3-3 — F3 DISPLACEMENT EMPIRICAL (retry E2-7)
On the two-node lab: victim spend C, attacker ghost A as a direct descendant with a ground
timestamp; measure which unit holds the MC position and whether the attacker grind (unit-hash
content control) reliably displaces C. Confirms/refutes E1-2's reliably-winnable claim on the real
network. Report evidence/roundE3/E3-3.md.

## E3-4 — DOUBLE-APPLICATION ATTACK ANGLE (the HN-15 question)
ER2-1 verifies the reprocess path re-applies deltas (stale MySQL watermark). Attack question: can
an ATTACKER trigger the double-application? The condition needs a node restart + same-second
multi-mci settlement + stale tie-break. Check: (1) any attacker-triggerable restart (crash the
node? — the crash family is dead, but check the E2-16 device crash on a bServeAsHub node... it
crashes the WALLET, and a hub restart would re-enter updateMissingTpsFees!); (2) can the attacker
force same-second multi-mci settlement; (3) on sqlite the rowid is immune — confirm no sqlite
path. If the device-crash can force a hub restart, the chain device-crash → restart → stale
watermark → double-application is a REAL composition. Report evidence/roundE3/E3-4.md.

## E3-5 — F1 FUND-IMPACT VIA THE AA PATH (the strongest composition)
The confirmed AA path + the merkle footgun: build the withdrawal-gated AA (E3-1) and additionally
show a REALISTIC AA pattern (e.g., airdrop claim gated by a merkle proof) being drained. The
deliverable is the fund-impact demonstration for the F1 report. Report evidence/roundE3/E3-5.md.

## E3-6 — Q-1 MAX-IMPACT POC FINALIZATION
The crash-loop is confirmed (E2-16, 3/3). Finalize the maximum-impact PoC package: the delivery
loop script (hub mailbox → wallet processing → crash → re-delivery), the blast-radius note
(bServeAsHub victims; stale-key edges), and the cleanup. Quarantine-level — ready for the operator
to widen scope. Report evidence/roundE3/E3-6.md.

## E3-7 — WITNESS-ROUNDING HALF-UP QUANTIFICATION
E2-11: the half-up roundings (paid-witnessing, headers commission) can CREATE value. Quantify:
(1) the paid-witnessing rounding (Math.round(payload_commission / count)) — can an OP choose
counts to over-receive?; (2) the headers-commission winner grind (sha1) — the creator pays ~50x
the max gain (E2-11 said economically dead — verify the number); (3) any accumulation over time.
Report evidence/roundE3/E3-7.md.

## E3-8 — AA→AA RESPONSE CHAINS ON THE NETWORK
With the AA path working: trigger an AA whose response triggers a second AA (secondary triggers,
handleSecondaryTriggers) — measure the chain depth limits, the response ordering determinism
across nodes, and whether a crafted chain can amplify work or state. Report
evidence/roundE3/E3-8.md.

## E3-9 — AA RESPONSE FEE INTERPLAY
AA responses carry no tps_fee (validation.js:1054-1056) but count in getFinalTps
(count_aa_responses): can an attacker craft a unit with many AA responses (max_aa_responses up to
10) to inflate the fee window cheaply (responses pay no fee)? The count_units formula
(getCountUnitsPayingTpsFee) includes count_primary_aa_triggers * max_aa_responses — is the
fee-window inflation via AA responses cheaper than via normal units? Report
evidence/roundE3/E3-9.md.

## E3-10 — EXCHANGE HOT-WALLET F4 EXPOSURE
E2-15 documented integration-level consequences. Quantify the F4 poisoning against an exchange
hot-wallet address (a single address authoring many units): the settlement debits hit the exchange
address's balance — what is the freeze cost at the real attack rate (E3-2's bound)? Report
evidence/roundE3/E3-10.md.

## E3-11 — LIGHT-VENDOR FUND PATH
Read E2-12.md first, then chase its open items: the light-client receive path (does a light
wallet accept funds without the full-node checks the vendor skipped?), and the vendor
prepareHistory serving to light clients. Report evidence/roundE3/E3-11.md.

## E3-12 — RECIPIENT SPEND RACE
The tps_fees_balance credit (delta) — can a recipient SPEND the credited balance in the same
block/transaction the credit lands (a race between the credit write and a spend of the balance)?
Or is the balance only usable after the settlement commit? Check the lock ordering around
updateTpsFees vs the min-fee gate reads. Report evidence/roundE3/E3-12.md.

## E3-13 — PARENT-COMPOSER CRASH BLAST RADIUS
E2-8 confirmed the crash end-to-end. Quantify the blast radius: who composes (wallets, AA
responses, exchanges, bots), the flood trigger cost (recent units — the attacker's own units must
be valid + fee-paying), and whether the crash can be looped (victim retries → crash-loop). This is
HN-14's severity sizing. Report evidence/roundE3/E3-13.md.

## E3-14 — AA SELF-REDEFINITION
The definition-change path in AA context: can an AA redefine itself (definition messages from an
AA) and what validates the new definition (validateAADefinition at execution)? Any churn vector
(state reset, getter re-wiring)? Report evidence/roundE3/E3-14.md.

## E3-15 — TERMINAL COVERAGE REVIEW (fresh context, no priors on E3)
The engagement's terminal coverage question: read the findings + rounds.md + HARDENING-NOTES.md,
then sweep the AA engine + fee system + private payments for anything the escalation rounds did NOT
touch (the airdrop/claim pattern, the AA storage-fee interplay with the F4 curve, the
max_aa_responses fee interplay). Report: new lane (file:line) or explicit none, and the terminal
coverage statement. Report evidence/roundE3/E3-15.md.

## E3-16 — MULTI-ASSET PRIVATE PAYMENT UNIQUENESS (f8's last gap)
Two private assets in one unit (dd29823): the spend-proof uniqueness per-tuple across assets —
can a proof for asset A be reused for asset B (the proof hashes asset — check), and is the
uniqueness key (asset, proof, address) or (proof, address)? Report evidence/roundE3/E3-16.md.

## Output contract
Report to evidence/roundE3/<id>.md; return JSON {id, claim, verdict, decisive_control_or_evidence,
cap_proven}. Real-path discipline. No live network. No secrets.
