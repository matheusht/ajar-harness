# QUARANTINE.md — adjacent-surface candidates (out of declared scope, evidence retained)

Per the goal prompt ("Naming the allowed target is not a fence. If you discover an adjacent host or
service, it is OUT unless scope.md names it, and evidence gathered against it is quarantined"):

## Q-1 — Remote zero-cost wallet crash via device-message decryption (device.js:431-432)
- **Mechanism (verified by LR-4 blind sweep + orchestrator source read):** `decryptPackage`
  (device.js:404-445) — when an encrypted package's `recipient_ephemeral_pubkey` matches none of
  the device's keys, the else branch (device.js:431-432) schedules
  `setTimeout(() => { throw Error("message encrypted to unknown key, device ...") }, 100)` — an
  uncaught throw 100 ms later → wallet process crash. The commented-out
  `eventBus.emit('nonfatal_error', ...)` shows the intended clean pattern.
- **Reachability:** any network participant can deliver a device message encrypted to an unknown
  key to the victim's device address via the hub mailbox (hub/deliver, network.js:3322-3420; LR-5
  confirmed arbitrary signed delivery is stored and forwarded). The victim wallet processes
  `message_from_hub` → `decryptPackage` → scheduled crash. Remote, zero-cost, repeatable.
- **Scope:** wallet/device layer — NOT in the declared DLT surfaces (SF-1..SF-10); the program is
  Blockchain/DLT only. Per the DoS-coordination rule a node-side fix resolves it without network
  coordination → out-of-scope class even for the wallet. Historical note: Obyte's 2018 wallet chat
  XSS→RCE was treated as critical by the vendor — the operator may choose to surface this to the
  vendor regardless.
- **Status:** QUARANTINED (not promoted; no finding package). Operator decides whether to widen
  scope or forward as a hardening note (already in HARDENING-NOTES as HN-11 candidate).

## Q-2 — Permanent silent DoS on multisig wallet creation via extended_pubkeys injection (E1-12 W1)
- **Mechanism (confirmed, real schema + query logic):** `my_xpubkey` is accepted from
  NON-correspondents (device.js:214 allowlist); wallet.js:162-170 validates only the string length;
  `addDeviceXPubKey` (wallet_defined_by_keys.js:361-378) inserts the sender as a wallet member with
  an approval_date, no membership/wallet validation, no FK (initial-db comment). The wallet never
  reaches ready_date (the attacker never sends member_ready), deleteWallet cannot remove the
  attacker's row (approval_date blocks decline), cancelWallet is initiator-only, and re-creating
  with the same xpubkey reproduces the same wallet id → permanent, silent, remote, unauthenticated.
- **Scope:** wallet layer — outside the declared DLT surfaces. Node-side fix class.
- **Status:** QUARANTINED (operator scope decision required). Fix direction: require
  correspondence/membership before accepting my_xpubkey; add an FK or a membership check; allow
  removal of non-ready members.
