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
