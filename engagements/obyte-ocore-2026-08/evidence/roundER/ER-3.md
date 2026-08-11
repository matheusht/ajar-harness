# ER-3 — Review of E1-12 (multisig DoS) + E1-4 (F1 one-off)

**Reviewer:** fresh context, adversarial-lite. **Pinned source:** ocore
`a7eb776afc68ed4bed05ba554f7f1e95f5d49b44` (verified: local clone HEAD == pin, tree clean).
**Doctrine:** claims verified against pinned source + raw evidence; hunter summaries not trusted.
**Local only:** no network, no secrets, no repo modifications (scratch sqlite in /tmp, deleted after).

## Claim (a) — E1-12 multisig DoS chain: **VERIFIED** (all steps; independent empirical re-run passed)

| Step | Claim | Verdict | Decisive evidence |
|---|---|---|---|
| a1 | `my_xpubkey` accepted from non-correspondents | verified | device.js:214 `arrSubjectsAllowedFromNoncorrespondents = ["pairing", "my_xpubkey", "wallet_fully_approved"]`; :215-217 whitelist gate. |
| a2 | wallet.js handler validates only string/length | verified | wallet.js:162-170 `case "my_xpubkey"`: `isNonemptyString(body.wallet)`, `isNonemptyString(body.my_xpubkey)`, `length > 112` only; no wallet-id format, existence, or membership check → `walletDefinedByKeys.addDeviceXPubKey(...)`. |
| a3 | `addDeviceXPubKey` inserts a member row with approval_date, no membership check | verified | wallet_defined_by_keys.js:361-367 `INSERT OR IGNORE INTO extended_pubkeys (wallet, device_address) VALUES(?,?)` then `UPDATE ... SET extended_pubkey=?, approval_date=now WHERE wallet=? AND device_address=?`; no wallet lookup, no member check. Schema has **no FK**: initial-db/byteball-sqlite.sql:573 comment "no FK because xpubkey may arrive earlier...". |
| a4 | wallet never finalizes: `checkAndFinalizeWallet` requires `member_ready_date` on every row | verified | wallet_defined_by_keys.js:123-133: `rows.some(row => !row.member_ready_date)` → return without `ready_date`. Attacker row never gets `member_ready_date` (attacker never replies `wallet_fully_approved`). |
| a5 | no removal path: `deleteWallet` blocked by approval_date | verified | wallet_defined_by_keys.js:332-338: `if (rows[0].approval_date) return onDone();` — attacker's row HAS approval_date → kept. **Bonus found by reviewer:** initiator cancel is equally blocked — the initiator's own row gets `approval_date` at creation (addWallet, wallet_defined_by_keys.js:185-188 `if (device_address === device.getMyDeviceAddress()) ... approval_date`), and `cancel_new_wallet` routes to the same deleteWallet (wallet.js:153-155). Re-creating reproduces the same wallet id (createWallet:234-235 `wallet = sha256(xPubKey).base64`). |
| a6 | full-approval machinery counts the attacker | verified | checkAndFullyApproveWallet (wallet_defined_by_keys.js:140-167) requires every row's `approval_date` — attacker's row has one → `full_approval_date` set, notifications to ALL rows including the attacker. |
| a7 | address leak + malformed-xpubkey crash | verified | issueAddress:606-620 sends every derived address to ALL extended_pubkeys rows except self (incl. attacker). deriveAddress:554-563 iterates all rows and calls `derivePubkey` → `new Bitcore.HDPublicKey(xPubKey)` (line 540) throws on a malformed injected xpubkey. NOTE: derived addresses are NOT changed by the extra row (replaceInTemplate substitutes only `$name` vars the template references, definition.js:1468-1493; attacker's `pubkey@<A>` param is unused), consistent with H1. |
| a8 | marginal-contribution: "injection after final approval still blocks ready_date" | **partially overstated** | If `ready_date` is ALREADY set (wallet completed), injection cannot un-set it (finalize UPDATE has `WHERE ready_date IS NULL`, and the blocking branch merely returns early). Verified: `ready_date` is set synchronously in the approve/finalize chain; the DoS window is any point BEFORE ready_date is set (incl. after `full_approval_date`, the normal multi-day approval window). Core claim — a wallet not yet completed can be permanently parked in "fully approved but never ready", silently, with no removal path — verified. The report's own BEFORE/AFTER framing is a control (finalize logic works) + attack (blocked). |

### Independent empirical re-run (reviewer, real schema)
Reproduced the exact schema (wallets, extended_pubkeys, no FK) in a scratch sqlite and the exact
query logic. Timeline: M1 initiator row (xpub+approval) → M2 approves via addDeviceXPubKey SQL →
all approved → attacker A injects → M2 replies member_ready → finalize check → **BLOCKED,
`ready_date` NULL**; deleteWallet(A) → "already approved → kept"; cancel by M1 → "already
approved → kept". All six observed states match the claim chain exactly. (E1-12's own lab script
`/tmp/e1-12-check.js` was deleted; its prose claims are now independently re-confirmed.)

## Claim (b) — E1-4: F1 is the ONLY prover-anchored verification primitive: **VERIFIED**

Spot-checks against pinned source:

1. **is_valid_sig** (formula/evaluation.js:1699-1730) — verified: signature of `arr[3]` verified
   against evaluated message + **explicit `pem_key` argument** via
   `signature.verifyMessageWithPemPubKey(evaluated_message, evaluated_signature, formatted_pem_key, mci)`.
   Key is the anchor; opcode makes no identity claim. Curve handling verified: allowlist
   `objSupportedPemTypes` + safe-curves-only gate at `mci >= constants.pemCurvesFixMci`
   (signature.js:118-166). Wrong key → verification fails (signature check is key-bound; source is
   unambiguous — E1-4's measured true/false rows are consistent, though that probe's raw log was
   deleted and the claim rests on source alone).
2. **vrf_verify** (evaluation.js:1731-1761) — verified: RSA-only (`validateAndFormatPemPubKey(..., "RSA", ...)`),
   proof = signature over seed with the supplied key; no forgery without the key.
3. **is_valid_signed_package** (evaluation.js:1651-1698) — verified: anchor is the address's
   on-chain definition via `signed_message.validateSignedMessage(conn, signedPackage, evaluated_address, ...)`;
   `last_ball_unit` freshness check is optional (`if (typeof signedPackage.last_ball_unit === 'string')` at
   :1666) — the replay caveat is real and correctly framed as an AA-author concern, not an opcode flaw.
4. **is_valid_merkle_proof** (evaluation.js:1763-1802) — verified: proof {index, siblings, root} all
   prover-supplied; merkle.js:84-101 `verifyMerkleProof` with index=0/siblings=[] reduces to
   `hash(element) === proof.root` (root attacker-chosen). Sibling cap (evaluation.js:1787-1791,
   `siblings.length > 50`, mci-gated) does not bound the vacuous case. Raw empirical support:
   **IR-F1 preserved raw P9-RESULTS** — 4/4 vacuous rows `res:true`; in-merkle contrast row
   `res:false` with real `dataFeedExists` log ("0 / 0 records inspected"). Verified directly.
5. **Completeness of the "only one" claim** — verified by full enumeration: all formula opcodes
   (grep of `case '...'` in evaluation.js) and definition predicates (definition.js). No other
   verification primitive carries its commitment inside prover input. The sound contrast `in merkle`
   binds `proof.root` to a posted feed (definition.js:1020 `dataFeeds.dataFeedExists(..., '=', proof.root, ...)`).
   Escalation cap (F1 remains a one-off) — supported.

## Notes / residual risks

- **E1-12 is a wallet-layer finding** — outside the signed DLT surfaces (SF-1..SF-10). Scope
  decision is the operator's; the mechanism and reachability (attacker must know the wallet id =
  sha256(initiator_xpubkey); realistic vector = malicious invited cosigner / leaked id) are verified.
- **Raw-log preservation gap:** E1-12's and E1-4's throwaway probes left no raw logs; both were
  re-verified here (E1-12 empirically re-run; E1-4's F1 rows backed by IR-F1's preserved raw output).
- Severity framing (Low–Medium, availability, silent/permanent, no fund loss — H1 verified) is fair;
  the one overstated sub-claim (a8: un-set of an already-set ready_date) does not change the core
  mechanism or severity.

## Verdict JSON

```json
{
  "id": "ER-3",
  "verdict": "verified",
  "per_claim": [
    {
      "claim": "a1 my_xpubkey allowed from non-correspondents (device.js:214)",
      "verdict": "verified",
      "evidence": "device.js:214 allowlist + :215-217 gate"
    },
    {
      "claim": "a2 my_xpubkey handler validates only string/length (wallet.js:162-170)",
      "verdict": "verified",
      "evidence": "wallet.js:162-170, no wallet/membership checks"
    },
    {
      "claim": "a3 addDeviceXPubKey inserts member w/ approval_date, no membership check (wallet_defined_by_keys.js:361-378)",
      "verdict": "verified",
      "evidence": "wallet_defined_by_keys.js:361-367; no FK, byteball-sqlite.sql:573"
    },
    {
      "claim": "a4 wallet never finalizes (checkAndFinalizeWallet requires member_ready_date)",
      "verdict": "verified",
      "evidence": "wallet_defined_by_keys.js:123-133; reviewer sqlite re-run: ready_date NULL"
    },
    {
      "claim": "a5 no removal path (deleteWallet blocked by approval_date)",
      "verdict": "verified",
      "evidence": "wallet_defined_by_keys.js:332-338; cancel also blocked (initiator row has approval_date, addWallet:185-188); wallet id deterministic (createWallet:234-235)"
    },
    {
      "claim": "a6 full approval counts the attacker",
      "verdict": "verified",
      "evidence": "wallet_defined_by_keys.js:140-167; notifications to all rows incl. attacker"
    },
    {
      "claim": "a7 address leak + malformed-xpubkey crash in deriveAddress",
      "verdict": "verified",
      "evidence": "issueAddress:606-620; deriveAddress:554-563; derivePubkey:540 (Bitcore.HDPublicKey throws)"
    },
    {
      "claim": "a8 marginal: injection after final approval still blocks ready_date",
      "verdict": "overstated",
      "evidence": "an already-set ready_date cannot be un-set (finalize UPDATE WHERE ready_date IS NULL, wallet_defined_by_keys.js:132); DoS window = any point before ready_date is set"
    },
    {
      "claim": "b1 is_valid_sig sound-as-stated (pem_key is the anchor)",
      "verdict": "verified",
      "evidence": "evaluation.js:1699-1730; signature.js:28-38, 118-166 curve allowlist + mci gate"
    },
    {
      "claim": "b2 vrf_verify sound-as-stated (RSA-only, key is the anchor)",
      "verdict": "verified",
      "evidence": "evaluation.js:1731-1761"
    },
    {
      "claim": "b3 is_valid_signed_package anchored to on-chain definition; last_ball_unit optional",
      "verdict": "verified",
      "evidence": "evaluation.js:1651-1698 (:1666 optional check)"
    },
    {
      "claim": "b4 F1 is the ONLY prover-supplied truth-anchor primitive",
      "verdict": "verified",
      "evidence": "full opcode/predicate enumeration; merkle.js:84-101 vacuous reduction; in merkle anchored at definition.js:1020; raw IR-F1 P9-RESULTS 4/4 true + contrast false"
    }
  ]
}
```
