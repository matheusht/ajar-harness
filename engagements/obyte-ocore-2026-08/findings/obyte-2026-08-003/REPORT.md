# obyte-2026-08-003 — Private-payment spend-proof uniqueness check keyed on a party-chosen address

**Status:** unproven. **Pinned target:** ocore @ `a7eb776afc68ed4bed05ba554f7f1e95f5d49b44`

## Summary (one sentence)

The only network-wide double-spend detection for private payments — the spend-proof uniqueness
check — keys its conflict match on the unit's claimed author address instead of the output owner
the proof commits to, so a sender who retains the bearer spend proof can place a second `'good'`
unit carrying the same proof under a different address, with no conflict detection and no
resolution.

## Affected surface

- `validation.js:1637-1654` `validateSpendProofs` — conflict query keyed on `(spend_proof,
  claimed-address)`
- `validation.js:1557-1568` — claimed address is the unit's own author (single: implied;
  multi: must be an author), never compared to the output owner
- `inputs.js:73-80` — the spend proof commits to the output owner's address
- `divisible_asset.js:120-136, 159` — payload-side recomputation binds the owner (per-node only)
- `validation.js:2695` — `bPrivate` set only in the payload flow → the input-level check cannot
  run network-wide for private payments
- Sender retains the bearer secret: `composer.js:839` (blinding), `divisible_asset.js:56-65`

## Claim tuple

- **target/version:** ocore `a7eb776`, private-payment spend-proof path
- **entrypoint:** any private-payment unit carrying `spend_proofs` (payload_location none — the
  gossip path)
- **preconditions:** sender retains P (bearer design); recipient's spend created the row
  `(P, recipient)`
- **mechanism:** check queries `(P, sender)` → no match → accepted `'good'` network-wide
- **observable effect (measured):** both units saved `'good'`; `spend_proofs` holds two rows with
  the identical P; the contrast (same P + same address) is cleanly rejected
- **negative control:** same P + same address → `"conflicting spend proof in inner unit"` — the
  check works only within an address
- **claimed impact/severity:** Low — payment-race/ledger-integrity; Medium ceiling conditional on
  merchant acceptance flows

## Reproduction (maximum-impact PoC + independent run — standing gate)

```
cd /Users/matheusvsky/Documents/trab/obyte-ocore-2026-08-ocore
node <abs>/unproven/obyte-2026-08-003/p1-refute.js        # victim spend + attacker re-spend (IR-F3 ran this)
node <abs>/unproven/obyte-2026-08-003/kp-f3-ghost-exp.js  # ghost-payload delivery experiment (killer's decisive test)
```

Independent run (IR-F3, fresh context): victim's spend saved with its (P, victim) row; attacker's
re-spend with the same P under the attacker's address ACCEPTED and SAVED as `'good'` (verified by a
direct DB read of `spend_proofs` and `units`); contrast variants cleanly rejected; no crash.
The kill-pair's ghost experiment confirmed the impact ceiling: the attacker's competing payload is
rejected by the payload-side owner binding (`"incorrect spend proof"`) — no direct theft of the
double-spent value, and the victim's unit is not voided in the same-branch case.

## Impact analysis (marginal contribution)

- World without the bug: the uniqueness check would key on the output owner (as the payload-side
  recomputation already does), so a second spend of X would be rejected at unit level on every
  node — the designed early-detection protection.
- Delta: the sender's re-spend enters the DAG as `'good'` with no signal. Ledger-integrity
  degradation (permanent unresolved duplicate-spend records) and a payment-race vector (a merchant
  whose acceptance logic keys on "unit accepted + included" — sound for public bytes — is exposed
  for private bytes).
- **Bounds (kill side, incorporated):** no direct theft (payload binding); no voiding of the
  victim's unit in the same-branch case; the bearer retention itself is possibly by-design — the
  defect is the check's keying, not the retention.
- **Cap:** merchant exposure requires the fork-variant race win + an inclusion-based acceptance
  flow; not demonstrated → Low.

## Negative control

Same P + same address → clean unit rejection (the check works within an address — proving intent
to reject duplicates; only the key is wrong). The payload-side owner binding rejects the ghost's
payload (`"incorrect spend proof"`).

## Remediation note

Bind the unit-level uniqueness key to the output owner — resolve the spend proof's committed
address (the payload-side recomputation, divisible_asset.js:120-136) at unit level, or store the
output owner's address with the spend_proofs row and key the check on it.

## Evidence refs

- `evidence-r1.md` — round-1 refuter report (A_own experiment, §6)
- `evidence-IR-F3.md` — round-2 independent run + DB verification
- `evidence-KP-F3-establish.md` — kill-pair establish side (strongest true form)
- `p1-refute.js`, `kp-f3-ghost-exp.js` — runnable experiments
- `attempts.jsonl` — round-1/round-2 attempt records

**CVSS:3.1/AV:N/AC:H/PR:N/UI:N/S:U/C:N/I:L/A:N** = 3.7
