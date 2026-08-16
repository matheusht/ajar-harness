# LR-2 — Independent review of the F3 kill-pair adjudication (obyte-2026-08-003)

**Target:** ocore pinned `a7eb776afc68ed4bed05ba554f7f1e95f5d49b44` (verified `git rev-parse HEAD`).
**Role:** round-3 independent reviewer of the round-2 adjudication ("real defect, Low; Medium
ceiling conditional on merchant acceptance flows").
**Fresh context read:** `findings/obyte-2026-08-003/*` (REPORT, finding.json, attest.json,
evidence-r1, evidence-IR-F3, evidence-KP-F3-establish, reviews/claim_adjudication.json) +
`evidence/round2/KP-F3-establish.md` + `evidence/round2/CHAIN-1.md`.
**Empirical (my own runs, this review):** re-ran `p1-refute.js` and `kp-f3-ghost-exp.js`
unmodified from the finding dir, plus direct read-only sqlite queries on the post-run DBs
(`.r1data/byteball.sqlite`, `.kp-f3-data/`). Raw output: `/tmp/lr2-p1-run.log`,
`/tmp/lr2-ghost.log` (not persisted — the raw DB end-states are quoted below from my runs).
**Adversarial posture:** the brief asks me to attack the adjudication on three fronts. I verified
every load-bearing line number against the pinned tree before writing anything.

## Verdict (one line)

**Adjudication stands.** The defect is real and Low is the right filing level; the ledger-integrity
claim is confirmed (stabilization does NOT resolve the pair — source-verified, not just
lab-verified), with one precision correction (the duplicate is in the spend-proof *detection* layer,
not in the value ledger); the merchant-exposure ceiling is honestly bounded but its "inclusion-keyed
acceptance" phrasing is imprecise and the exposure is triple-contingent, so the Medium ceiling is a
ceiling, not a probability.

---

## Q1 — Is the merchant-exposure ceiling honestly framed?

**Mostly yes, with one imprecise phrase and one understated contingency.**

What the adjudication claims (finding.json c-004, REPORT.md "Cap"): a merchant whose acceptance
logic keys on "unit accepted + included" is exposed for private bytes; exposure is conditional on
acceptance flows keyed on unit inclusion; not demonstrated → Low.

**Verification of the underlying mechanics (source):**

1. Same-branch case (attacker's ghost unit A is a descendant of the merchant's spend C): C stays
   `'good'` and on-MC, X is spent exactly once by C, nothing voids C. Confirmed by my run of
   `kp-f3-ghost-exp.js`: `X is_spent: [{...is_spent:1}]`, `A_own INPUTS rows: []` — the ghost
   spends nothing in the DAG; `A_own PAYLOAD RESULT: REJECTED: incorrect spend proof`
   (divisible_asset.js:159). No merchant exposure in this case, in any arrival order.
2. Fork case (A and C anchored on the same parents, simultaneous publish): the loser is off-MC but
   keeps its validation-time `sequence` — `'good'`. Sequence (good/temp-bad/final-bad) is the
   author-seriality state set at validation (validation.js:1321-1333), orthogonal to MC status
   (`is_on_main_chain`/`main_chain_index` are assigned by the MC walk, main_chain.js:32-120).
   Nothing ever marks C final-bad: `propagateFinalBad` (main_chain.js:1337+) propagates through the
   **inputs** table (`src_unit IN(?)`), and the ghost has no inputs rows.

**The imprecision:** "acceptance flows keyed on unit inclusion" is self-undermining. A flow
genuinely keyed on **MC inclusion** is NOT exposed: in the fork variant the loser is by definition
not on the MC, so an inclusion-keyed flow refuses to accept C → no exposure; if C wins, C is
included and the merchant is paid (the ghost is the off-MC loser, harmless). The exposed flow is
one that keys on **unit validity (`sequence='good'`) without checking MC inclusion/stability** —
i.e. a validity-keyed flow. The finding's own concession 2 (§"merchant's unit is not voided")
already implies this; the REPORT.md phrase should read "acceptance flows keyed on unit *validity*
without an MC-inclusion/stability check".

**The understated contingency:** for the fork variant to even materialize, three things must align:
(a) C is composed before A reaches the merchant's node, yet both anchor on the same parents — a
narrow simultaneous-publish window (if A arrives first, the merchant's node's tip includes A and C
anchors ON A → same-branch → no race); (b) the attacker's branch wins the witness ball race —
undemonstrated; the round-2 evidence contains no MC-race-win experiment (KP-F2-link proves the
opposite class: old-attached units cannot win MC placement); and (c) the merchant accepts on
validity only. The "Medium ceiling conditional on merchant acceptance flows" is therefore honest
as a *ceiling*, but the conditional includes an un-demonstrated race-win that the finding only
half-acknowledges ("fork-variant economics depend on the F2 link").

**Ceiling verdict:** honestly bounded (conditional, not demonstrated), imprecisely phrased
("inclusion" → "validity"), and the race-win leg is genuinely open. The ceiling does not leak into
the filed severity because the filed severity is Low.

---

## Q2 — Is the ledger-integrity claim overstated? Do two 'good' same-proof units coexist on the MC path, or does stabilization resolve them?

**The descriptive claim is CONFIRMED — and the specific question the brief asks (does
stabilization resolve them) has a verified NO.** I checked this in the source, not just the lab:

1. **No spend-proof involvement anywhere in consensus/stabilization.** `grep -n spend_proof
   main_chain.js` → **zero matches**. The spend-proof uniqueness check runs exactly once, at unit
   arrival (validation.js:1637-1654); it is never re-checked at ball creation, MC update, or MCI
   stabilization.
2. **`handleNonserialUnits` (main_chain.js:1294-1336) only processes units with
   `sequence != 'good'` on the stabilizing MCI.** Both F3 units validate `'good'` — the seriality
   check `findConflictingUnits` (validation.js:1256-1272) is keyed on the unit's **own author
   address** (`WHERE address=?` on the author), so the recipient's unit and the attacker's unit
   (different authors) never conflict with each other, and neither is ever marked temp-bad. The
   stabilization ladder never sees either unit.
3. **`findStableConflictingUnits` (main_chain.js:1391-1424) is author-keyed too** — `JOIN
   unit_authors AS competitor_unit_authors USING(address)`. Even if a temp-bad state existed, a
   same-author competitor is required; a sender-vs-recipient pair has no shared author → no
   competitor found → the unit would be promoted to `'good'`, not voided.
4. **`propagateFinalBad` (main_chain.js:1337+) is inputs-table-keyed** (`SELECT DISTINCT inputs.unit
   ... WHERE src_unit IN(?)`); the ghost has no inputs rows, so final-bad can neither reach it nor
   propagate from it.

**Empirical (my own runs + direct DB reads):**

`p1-refute.js` (re-run, exit 2 = designed terminal, zero `Uncaught exception`):
```
U2 VALIDATION OK sequence=good
U2 SAVED y+nvEEH1EmZnm0CIZkCHErtwGJBG3q+PFGVJm+wWJkM=
SPEND-PROOFS-ROWS: [{"unit":"y+nv...","address":"O644...(victim)","spend_proof":"vBGDhK7..."}]
A_own VALIDATION OK sequence=good
A_own SAVED k5+Y36OgZpnQbBHaNm8rqnETQ8wav620BK1IRkYGj/o=
A_victim UNIT-ERROR "when single-authored, must not put address in spend proof"   (clean rejection)
A_multi  UNIT-ERROR "conflicting spend proof in inner unit k5+Y..."                (control: check fires within an address)
```
sqlite (post-run, read-only):
```
SELECT unit, address, spend_proof FROM spend_proofs;
k5+Y36...=|57D2...(attacker)|vBGDhK7knQevYC0YE27wY6EfzP5ZR2hvv7CJjnhFng4=
y+nvEE...=|O644...(victim)  |vBGDhK7knQevYC0YE27wY6EfzP5ZR2hvv7CJjnhFng4=   <- IDENTICAL P, two units

SELECT unit, main_chain_index, is_stable, sequence, is_on_main_chain FROM units ORDER BY main_chain_index;
I3WR...=|0|1|good|1    <- genesis
y+nvEE...=|1|0|good|1  <- U2 (victim's spend)
k5+Y36...=|2|0|good|1  <- A_own (attacker ghost), SAVED 'good' ON the main chain

SELECT child_unit, parent_unit FROM parenthoods ...;
k5+Y36...=|y+nvEE...   <- ghost is a DIRECT DESCENDANT of the victim's spend (same branch)
y+nvEE...=|I3WR...     <- victim's spend is genesis's child
```
`kp-f3-ghost-exp.js` (re-run, full end-to-end with a real private asset + blinding):
```
A_own UNIT-LEVEL RESULT: ACCEPTED        (ghost unit 'good')
A_own PAYLOAD RESULT: REJECTED: incorrect spend proof   (divisible_asset.js:159)
X is_spent: [{...is_spent:1}]            (X spent exactly once, by the victim's unit)
A_own INPUTS rows: []                    (ghost spends nothing in the DAG)
```

So: **yes, two 'good' units carrying the identical spend proof coexist on the same MC path, as
parent→child, permanently; stabilization does not resolve them.** The ledger-integrity claim is not
overstated at the descriptive level.

**The precision correction (what IS overstated if read loosely):** the word "double-spend".
`spend_proofs` holds two rows with the same P, but the value layer does not double-spend: X's
`outputs` row has `is_spent=1` exactly once, the ghost's `inputs` rows are empty, and the ghost's
payload is rejected on every node that validates it — including the attacker's own (the payload-side
recomputation reads `src_output.address` from the DB, divisible_asset.js:118-136, so the owner-bound
proof never matches the attacker-claimed row). What is violated is the **spend-proof uniqueness
invariant of the detection layer** — the designed early-warning signal (05f291d8 "uniqueness of
spend proof is not verified in light" shows the invariant is first-class, not accidental). The
correct statement: *the network's only unit-level double-spend **signal** for private payments is
defeated for the sender; the value-level double-spend **protection** (payload binding) still holds
everywhere.* The finding's own concessions already say this; the REPORT.md one-liner ("the only
network-wide double-spend protection ... keys its conflict match ...") should say "double-spend
detection" to avoid implying the value ledger can be double-spent.

**One honest caveat on "MC path":** the empirical proof is single-node with synthetic genesis. On a
real network the ghost's MC placement requires witnesses to include it in balls — but it is a normal
serial unit anchored on the tip, so inclusion is the ordinary case; the source-level reasons
(KP-F2-link Q1: MC walk starts from the tip and follows best-parent) do not exclude it. The claim is
source-argued, not multi-node-empirically demonstrated.

---

## Q3 — Is Low the right severity? Would I file it, and at what level?

**Yes — Low is right, and I would file it at Low (CVSS 3.7, I:L). Not Medium.**

- **It is a real, code-level, fixable defect.** The conflict key `(spend_proof, claimed-address)`
  (validation.js:1640-1648) uses a party-chosen string where the cryptographically committed value
  is the output owner (inputs.js:73-80; divisible_asset.js:118-136). The control (`A_multi`, my run)
  proves intent: same P + matching address → clean rejection "conflicting spend proof in inner
  unit". The intent to reject duplicates is unambiguous; only the key is wrong. And the fix is
  simple and obviously correct: key the uniqueness check on the spend proof **alone** (drop the
  `AND address=` clause). P is already unique per source output — `{asset, amount, address, unit,
  message_index, output_index, blinding}` (inputs.js:73-80) — so two units carrying the same P are
  by definition two claims on the same output; the address dimension of the key exists only to
  disambiguate multi-authored joints (which author claims the proof) and is exactly the hole. A
  cheap, correct fix exists → the finding earns its keep as a reportable low.
- **Why not Medium:** the program's Medium rung is "unable to operate due to lack of token funds;
  temporary freezing of funds" — neither applies. No theft (payload binding), no freezing, no
  insolvency, no voiding of the merchant's unit in any branch case, no value-level double-spend.
  The merchant exposure is triple-contingent (simultaneous-publish window + race win +
  validity-keyed acceptance) and undemonstrated. The CVSS 3.7 (AV:N/AC:H/PR:N/UI:N/S:U/C:N/I:L/A:N)
  is defensible: I:L is the correct maximum — a designed detection invariant is violated, with no
  value-integrity, confidentiality, or availability impact; AC:H is generous (the base act is
  trivial for the sender) but the *impactful* act is not, which nets out honestly.
- **Honest negatives a filer must keep:** the "silent contest" harm is, in the same-branch case, a
  false-alarm/no-signal problem for downstream consumers of spend-proof uniqueness (light wallets,
  merchant services, auditors) rather than a fund movement; the durable effect is a permanent ghost
  unit + duplicate P rows on the MC. That is exactly the Low band.
- **The Medium ceiling note should stay** (it is honest), but should be re-worded per Q1:
  "conditional on validity-keyed merchant acceptance AND an undemonstrated MC-race win".

**Fix-feasibility note for the report:** the recommended remediation (REPORT.md) — "bind the
unit-level uniqueness key to the output owner" — cannot be done by *resolving the owner at unit
level* (the whole point of `payload_location:none` is that the node does not have the payload at
validation time; the owner is unknowable there). The workable form is **key on the spend proof
alone** (drop the address from the conflict key), which restores the invariant without needing the
payload. This should be stated in the fix direction so the operator doesn't chase an
unimplementable version.

---

## Evidence index (all verified against the pinned tree this review)

| Claim | Source (pinned) | My verification |
|---|---|---|
| Uniqueness check keys on (P, claimed-address) | validation.js:1637-1654 (query 1644-1648, key 1640-1642) | read |
| Claimed address = author, never owner | validation.js:1557-1568 (1560 single, 1567 multi) | read + A_victim control (my run) |
| True spend proof commits to the output owner | inputs.js:73-80; divisible_asset.js:118-136; indivisible_asset.js:105-133 | read |
| Sender retains the bearer secret | composer.js:839 (`generateBlinding`), divisible_asset.js:56-65 (outputs row stores blinding) | read |
| Stored row keeps the claimed address as-is | writer.js:279-283 (`objSpendProof.address \|\| arrAuthorAddresses[0]`) | read |
| Payload-side binding rejects the ghost everywhere | divisible_asset.js:152-160 ("incorrect spend proof") | ghost exp (my run): REJECTED |
| Value layer records one spend of X | ghost exp (my run): `X is_spent=1`, `A_own INPUTS rows: []` | my sqlite read |
| bPrivate set only in the payload flow | validation.js:2665/2695 (`initPrivatePaymentValidationState`), called from divisible_asset.js:89, indivisible_asset.js:87 | read |
| Public-model equivalent gets a clean rejection | network.js:1146 ("The transaction would be non-serial (a double spend)") | read |
| Seriality check is author-keyed (no temp-bad for the pair) | validation.js:1256-1272, 1321-1333 | read |
| Stabilization does NOT resolve the pair | main_chain.js:1294-1336 (only non-'good' units), 1391-1424 (author-keyed), 1337+ (inputs-keyed); **zero `spend_proof` refs in main_chain.js** | grep + read |
| Both 'good' on the same MC path, parent→child | my run of p1-refute.js + sqlite reads (units, spend_proofs, parenthoods) | reproduced |
| Negative control (check works within an address) | A_multi → "conflicting spend proof in inner unit" | reproduced (my run) |
| Uniqueness invariant is first-class (not accidental) | commit 05f291d8 "uniqueness of spend proof is not verified in light" | git show |

## What I ran (this review)

- `cd <ocore> && node .../findings/obyte-2026-08-003/p1-refute.js` → exit 2 (designed terminal), no
  uncaught exceptions; DB verified via sqlite3.
- `cd <ocore> && node .../findings/obyte-2026-08-003/kp-f3-ghost-exp.js` → exit 0; unit accepted,
  payload rejected, X spent once.
- `git rev-parse HEAD` = `a7eb776afc68ed4bed05ba554f7f1e95f5d49b44`; `grep -n spend_proof
  main_chain.js` = 0 matches; `git show 05f291d8`.

## Residual risks / open items

1. **MC-race-win leg undemonstrated** — the merchant-exposure Medium ceiling depends on it; no
   round-2 experiment tested it (KP-F2-link covers the opposite class). If the operator wants the
   ceiling tested, a two-node synthetic-witness race is the experiment — out of this review lane.
2. **Multi-node MC-inclusion of the ghost** — source-argued, not empirically shown (single-node lab
   only).
3. **Downstream-consumer harm unquantified** — which real-world consumers of spend-proof
   uniqueness (light wallets, merchant services, auditors) would misbehave on the duplicate P is
   outside the core library; it is the realistic Low-band harm and stays conditional.
4. **Per-tuple uniqueness across two private assets in one unit** (f8 gap) — separate lane (LR-3);
   noted here only as a related residual.
5. **Lab scratch dirs** (`.r1data/`, `.kp-f3-data/` in the finding dir) were refreshed by my
   re-runs — untracked experiment data, consistent with how the original evidence was produced.

## Files

- This report: `evidence/round3/LR-2.md`
- Read (fresh context): `findings/obyte-2026-08-003/{REPORT,finding,attest,evidence-r1,
  evidence-IR-F3,evidence-KP-F3-establish,reviews/claim_adjudication}.md/.json`,
  `evidence/round2/{KP-F3-establish,CHAIN-1}.md`
- Re-ran: `findings/obyte-2026-08-003/p1-refute.js`, `findings/obyte-2026-08-003/kp-f3-ghost-exp.js`

```json
{"id": "LR-2", "verdict": "adjudication-stands", "evidence": "F3 (obyte-2026-08-003): real defect confirmed; Low correct; ledger-integrity claim verified — two 'good' same-P units coexist on the same MC path (my re-run + sqlite: units mci 1&2 good, parenthoods parent→child, two identical spend_proof rows) and stabilization does NOT resolve them (main_chain.js has zero spend_proof refs; handleNonserialUnits/findStableConflictingUnits are author-keyed); merchant-exposure ceiling honest but re-phrase 'inclusion'->'validity' and note the race-win leg is undemonstrated; 'double-spend' -> 'double-spend detection' (value layer: X is_spent=1 once, ghost inputs empty, payload rejected everywhere); fix direction: key the check on the spend proof alone (owner is unresolvable at unit level by design)"}
```
