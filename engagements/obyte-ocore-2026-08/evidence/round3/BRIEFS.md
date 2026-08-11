# Round 3 briefs — obyte-ocore-2026-08 (blind sweep + light surface + adjudication reviews)

Terminal round per multi-round-orchestration §5: coverage-dry requires a blind no-new-family round.
3 findings promoted (001 merkle Medium, 003 spend-proof Low, 004 tps-fee Low); S1 family dead;
crash family refuted; all Tier-C leads adjudicated.

## LR-1 — light-client surface (never fully audited)
light.js (~37KB), light_wallet.js, wallet.js light paths, light.js proof-chain verification, the
light-vs-full asymmetry family (05f291d8). Questions: (1) light proof-chain validation gaps (can a
malicious vendor serve forged units/proofs); (2) light spend-proof handling (uniqueness NOT
verified in light — what breaks); (3) light AA definition handling (f11-R1-B); (4) any light-path
fund movement without full validation. Report evidence/round3/LR-1.md.

## LR-2 — independent review of the F3 kill-pair adjudication
Fresh context: read findings/obyte-2026-08-003/* + evidence/round2/KP-F3-*.md. Adjudication was
"real defect, Low (Medium ceiling conditional on merchant acceptance)". Attack that: is the
merchant-exposure ceiling honestly framed? Is the ledger-integrity claim overstated (two 'good'
same-proof units — do they actually coexist on the MC path, or does stabilization resolve them)?
Is Low the right severity? Report evidence/round3/LR-2.md.

## LR-3 — F4 natural-burst escalation + multi-private-asset uniqueness
(1) The natural-burst form of the tps-fee poisoning (no attacker): a NATURAL 30-unit burst in a
second (AA launch, exchange sweep) freezes every author settling in the window — verify the
mechanism framing and decide if F4's severity should rise (it's currently Low). (2) Multi-private-
asset per-tuple uniqueness (f8 gap): two private assets in one unit — is the uniqueness check
per-tuple? Report evidence/round3/LR-3.md.

## LR-4 — BLIND no-new-family sweep (fresh context, no priors)
Read ONLY the pinned source tree (no engagement files). Two hours over the whole codebase: find ANY
family/mechanism the engagement's 16 families did not cover. Report: new families found (or
explicitly none), with file:line. This is the coverage-dry requirement — an honest negative is the
expected outcome. Report evidence/round3/LR-4.md.

## LR-5 — hub surface (bServeAsHub)
network.js hub paths: device login (device.js loginToHub), hub/deliver + hub/message mailbox,
device_messages storage, peer auth. Questions: (1) mailbox abuse with fund-adjacent impact; (2)
hub spoofing / login confusion; (3) anything below the program's minimum impact or in the fund
classes. Report evidence/round3/LR-5.md.

## LR-6 — dependency surface
package.json dependency set at the pin: secp256k1 4.0.3, sqlite3 5.1.7, nearley 2.16.0, moo 0.5.1,
decimal.js 10.6.0, ws 8.21.0, level-rocksdb 5, async 2.6.4, lodash 4.18.1. Check the installed
versions in node_modules for known high-severity issues affecting the consensus/validation paths
(note: this is a local pin audit — known-CVE matching only as routing; never report an n-day as a
find). Focus: does any dependency's behavior affect validation correctness (nearley grammar
parsing, decimal.js precision, ws framing). Report evidence/round3/LR-6.md.

## LR-7 — witness/OP protocol depth
witness list mutation (MAX_WITNESS_LIST_MUTATIONS=1), witness_proof.js, my_witnesses.js,
paid_witnessing.js spend paths, initial_votes.js. Questions: (1) witness-list mutation distance
rule bypass (f1-T4 lead — below-MCI mutations); (2) paid-witnessing earnings spend validation
(f16 gap); (3) OP-list vote counting edges. Report evidence/round3/LR-7.md.

## LR-8 — formula language completeness
Ops skimmed in round 0 (f5 gaps): func_call/func_declaration recursion, foreach/map/filter/reduce
on attacker-shaped collections, json_parse/json_stringify edge cases (prototype pollution, __proto__
keys, huge nesting), search_param_list, selectSubobject/filterBySearchCriteria/assignByPath.
Questions: any op whose attacker-shaped input produces divergence, crash, or state corruption.
Report evidence/round3/LR-8.md.

Output contract: report to evidence/round3/<id>.md; return JSON {id, verdict, evidence}. No live
network. No secrets. Local only.
