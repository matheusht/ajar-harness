# IR-F3 — Independent run of the invisible-fork experiment (f8-TRIPLE-2 / r1 §6)

**Reviewer:** IR-F3 (fresh context, independent) · **Target:** ocore pinned `a7eb776afc68ed4bed05ba554f7f1e95f5d49b44`
**Experiment:** `evidence/lab/r1/p1-refute.js` (self-booting real-path script: `composer.composeJoint` → `validation.validate` → `writer.saveJoint`; synthetic genesis, local only)
**My raw log:** `evidence/round2/IR-F3.raw.log` (this reviewer's own run, captured fresh)
**Builder log for comparison:** `evidence/lab/r1/p1-refute.raw.log`; refuter report `evidence/round1/r1.md` §6

**Verdict: CONFIRMED** — the invisible-fork property holds exactly as r1 described: the victim's
spend is saved with its (P, victim) row, the attacker's re-spend with the SAME P under the
attacker's own address is accepted and saved with no conflict detected, and the process does not
crash. The double-spend is invisible to the standard spend-proof check because that check keys on
the (spend_proof, address) pair where address is derived from the unit's own authors
(validation.js:1557–1568, 1643–1654) — a different address with the same P never matches.

---

## How I ran it (independence)

`p1-refute.js` is a **self-booting** script (patches `desktop_app`, builds its own synthetic
genesis, seeds `system_vars`, boots db/network itself, data dir `r1/.r1data`) — it is not a
`lab.js` module (it exports nothing). The lab harness (`lab.js:47`) requires the target script as a
module function, so `node lab-obyte.js <script>` cannot drive it — confirming that the refuter's
own raw log (data dir `.r1data`, "I'm already at the root") was produced by a **direct** run.
I ran it the same way, from inside the ocore tree:

```
cd /Users/matheusvsky/Documents/trab/obyte-ocore-2026-08-ocore && \
  node /Users/matheusvsky/Documents/trab/llm-redteam-harness/engagements/obyte-ocore-2026-08/evidence/lab/r1/p1-refute.js \
  > .../evidence/round2/IR-F3.raw.log 2>&1
```

Exit code **2** — this is the script's own terminal path (`main().catch → process.exit(2)`)
reached after the final E2 variant's clean unit rejection, identical to the refuter's original run
(their log also ends `RESULT-ERROR: A_multi unit error ...`). Zero `Uncaught exception` lines in my
log. **No crash.**

Key log lines (my run, `IR-F3.raw.log`):

| line | event |
|---|---|
| 137 | `GENESIS SAVED p53VER...` (synthetic genesis through real validation+save) |
| 249 | `U2 VALIDATION OK sequence=good` |
| 283 | `U2 SAVED 9oUzebci...` (victim's spend unit) |
| 287 | `SPEND-PROOFS-ROWS: [{"unit":"9oUzebci...","address":"53LEKO6Y33YSN26JZYHEC4GF3E2UV7UH","spend_proof":"FLfhdvp5K2oLornLJsCLts0l4DzU2e/nJDca4mA7Xqg="}]` |
| 390 | `A_own VALIDATION OK sequence=good` (attacker re-spend, same P, own address) |
| 427 | `A_own SAVED UfKyiN5j...` |
| 431 | `NEGATIVE-CONTROL-1: unit with (P, implied attacker_addr) accepted, NO crash` |
| 540 | `A_victim UNIT-ERROR when single-authored, must not put address in spend proof` (E1 contrast, clean rejection, no crash) |
| 684 | `A_multi UNIT-ERROR ... conflicting spend proof in inner unit ...` (E2 contrast — the check DOES fire when the address matches, no crash) |

## 1. The victim's spend is saved with its (P, victim) row — CONFIRMED

- My log line 249/283: U2 validated `good` and saved.
- My log line 287: after save, `spend_proofs` contains
  `(unit=9oUzebci…, address=53LEKO6Y33YSN26JZYHEC4GF3E2UV7UH, spend_proof=P)` where
  `P = FLfhdvp5K2oLornLJsCLts0l4DzU2e/nJDca4mA7Xqg=`. 53LEKO6… is the victim's address (U2 is
  authored by the victim signer — confirmed in the composed-unit JSON in my log around line 218).
- **Independent DB check** (read-only sqlite3 on the post-run DB `lab/r1/.r1data/byteball.sqlite`):

```
SELECT unit, address, spend_proof FROM spend_proofs ORDER BY spend_proof_index;
9oUzebciLvpklDKpaDZJBYRu6IzZg47NTYz7muQKjSA=|53LEKO6Y33YSN26JZYHEC4GF3E2UV7UH|FLfhdvp5K2oLornLJsCLts0l4DzU2e/nJDca4mA7Xqg=
UfKyiN5jFywszdOmZcaRcikgHkK2AhBasfiMEz2fLxA=|XY222HAMIBK3OJ5ADVFIEAS5VZZLI7BB|FLfhdvp5K2oLornLJsCLts0l4DzU2e/nJDca4mA7Xqg=
```

The victim's row is present. (`spend_proofs` rows are written in `writer.js:279–286` from
`objSpendProof.address || arrAuthorAddresses[0]`, same transaction as the unit save.)

## 2. The attacker's re-spend with the SAME P and the attacker's own address is ACCEPTED and SAVED — CONFIRMED

- My log line 390: `A_own VALIDATION OK sequence=good`.
- My log line 427: `A_own SAVED UfKyiN5j...`.
- **Independent DB check** — units table:

```
SELECT unit, main_chain_index, is_stable, sequence, is_on_main_chain FROM units ORDER BY main_chain_index;
p53VERXrU9Unzwhq6KR5exhSoA0mJqpgjFTbVzmNYHw=|0|1|good|1     <- genesis
9oUzebciLvpklDKpaDZJBYRu6IzZg47NTYz7muQKjSA=|1|0|good|1     <- U2 (victim)
UfKyiN5jFywszdOmZcaRcikgHkK2AhBasfiMEz2fLxA=|2|0|good|1     <- A_own (attacker), SAVED, good
```

- The DB `spend_proofs` table now holds **two** rows with the identical spend_proof `P` — one under
  the victim's address (from U2), one under the attacker's address (from A_own). No conflict was
  detected at A_own's validation, and A_own was committed as a good unit on the main chain.

## 3. No crash — CONFIRMED

- The process ran to the script's designed terminal (exit 2 via `RESULT-ERROR: A_multi unit
  error …`, i.e. the final E2 contrast is a *clean unit rejection*, not a crash). Zero
  `Uncaught exception` lines in my log.
- The only crash-like path in this family (`network.js:4367–4379` uncaughtException re-throw) was
  never reached; the E1/E2 variants were both cleanly rejected by the message-level checks.

## Why the double-spend is invisible to the standard check (source-level)

`validation.js:1643–1654` (`validateSpendProofs`, runs before payload validation in every
`validateMessage`): the conflict query is

```sql
SELECT address, unit, main_chain_index, sequence FROM spend_proofs JOIN units USING(unit)
WHERE unit != ? AND (spend_proof=<P> AND address=<address>)
```

where `address` is `objSpendProof.address || objUnit.authors[0].address` — i.e. the **unit's own
author** (validation.js:1556–1568: single-authored → author address implied; multi-authored →
must be an author). The victim's row is `(P, victim_addr)`; A_own's query is
`spend_proof=P AND address=attacker_addr` → no row matches → `rows.length === 0` →
`checkForDoublespends` returns `cb()` (validation.js:1658–1659) → accepted. The check keys the
double-spend on the *address that signed the unit*, never on the private output being spent, so a
re-spend by any other address with the same bearer proof P is invisible.

**Contrast control (from my run, log line 684):** the E2 variant reuses P with `address:
attacker_addr` (an author) — this time the query *does* match A_own's own row
`(P, attacker_addr)` and the unit is cleanly rejected `"conflicting spend proof in inner unit ..."`.
This proves the check works only within an address: same P + same address → rejected; same P +
different address → silently accepted. That is precisely the invisible-fork property.

## Why this is not a crash finding (alignment with round-1 adjudication)

The r1 refutation's crash claims (validation.js:1667/1686/2292/2451 unreachable) stand. What
survives is the economic/payment-race observation: a private-payment double-spend is deferred to
the fork race instead of being rejected at the unit level, because the spend-proof uniqueness check
is address-scoped. Per rounds.md round-1 adjudication this is **F3, Low/Medium payment race**,
kill-pair framed (bug vs by-design bearer model) in KP-F3-kill / KP-F3-establish. The bearer-model
defense (sender always retains blinding; both units allowed; merchant must wait for stability
regardless) is the counter-argument; the divergence from the public-asset model (public double-spend
gets a clean second-spend rejection) is the defect-side argument. My role here is limited to
confirming the empirical property, which is done.

## Reward-hacking check

- No mocks/fake clients: composer → validation → writer are the real ocore modules; DB is the real
  sqlite file; spend proof P is a real 32-byte base64 hash of the documented shape.
- No hardcoded expectations: the script asserts nothing; my verdict rests on raw log + DB rows I
  read directly.
- The script does zero the upgrade MCIs and sets `COUNT_WITNESSES=1` (synthetic-genesis lab
  config, per scope.md §7 zone-2 containment) — this does not affect the spend-proof check, which
  is not MCI-gated.

## Residual risks / notes

- The experiment uses a synthetic P (not one derived from a real private asset's blinding), and the
  units carry `payload_location:"none"` with no real payload. This is sufficient to exercise the
  message-level spend-proof check (the check runs on `payload_location:"none"` payment messages
  exactly as on the gossip path), but a full end-to-end proof (real private payment → recipient
  spend → attacker re-spend) would strengthen the economic framing. r1 §5 concedes the bearer-secret
  premise (sender retains blinding and can recompute P), so the mechanism is real.
- Whether this rises to a reportable finding is the KP-F3 kill/establish question (out of this
  reviewer's lane); the empirical property itself is confirmed.
