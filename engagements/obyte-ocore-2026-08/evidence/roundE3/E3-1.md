# E3-1 — Vulnerable-AA demo: merkle-whitelist-gated AA bypassed by the vacuous proof (F1 fund-impact)

Pinned `a7eb776afc68ed4bed05ba554f7f1e95f5d49b44`. Real two-process Obyte network (hub 6611 +
node 6612, deterministic shared genesis `LAB_GENESIS_TS=1700000000` → genesis
`wcR3ogCtxN5w...`), real relay websocket protocol, real composer/validation/writer/stabilization,
real `aa_composer` trigger machinery (the E2-6-confirmed AA path).

## Verdict

**ESCALATED (evidence) — F1's fund-impact class demonstrated end-to-end on the network.** A
withdrawal-gated AA (only merkle-tree members may withdraw) is bypassed by the vacuous
`is_valid_merkle_proof` proof: an attacker who is NOT in any merkle tree triggers the withdrawal
and the AA's funds move. The identical trigger with a wrong-root proof is correctly rejected
("neither case is true" bounce, no response). F1's severity framing is strengthened from
"engine footgun, usage-capped" to "engine footgun with a demonstrated end-to-end fund-movement
bypass on the real network path" — the cap is now only "which deployed AAs use the construct"
(individual AA logic remains out of scope; the engine defect and its exploitability are in scope).

## The AA under test (the whitelist pattern)

```js
["autonomous agent", {
  bounce_fees: { base: 10000 },
  messages: {
    cases: [
      { if: "{is_valid_merkle_proof(trigger.data.element, trigger.data.proof)}",
        messages: [{ app: "payment", payload: { asset: "base",
          outputs: [{ address: "{trigger.address}", amount: 1000 }] } }] }
    ]
  }
}]
```
Realistic whitelist semantics: only holders of a merkle-membership proof for `trigger.data.element`
may withdraw 1000 base per trigger. AA address: `PK4VVIAB7DC54PLBHZJJ4BBCTW5KYOF7`.

## The attack

Trigger unit: payment of 10000 base to the AA + a `data` message (aa_composer.js:372-373:
`if (message.app === 'data' && !trigger.data) trigger.data = message.payload;`) carrying:
- `element: "attacker-NOT-A-MERKLE-MEMBER-2026"` — NOT in any real merkle tree
- `proof: "0-G8sKi+qJrfhSpeehuT63TryHRKaMx4bp31jYeh8S230="` — the vacuous proof:
  `"0-" + base64(sha256(element))` (index 0, no siblings, root = hash(element); the attacker's own
  root; merkle.verifyMerkleProof with siblings=[] reduces to `hash(element) === root`).

The case `if` formula evaluated the gate → `is_valid_merkle_proof(...)` → **TRUE** (vacuously) →
the case matched → the AA composed a payment response.

## Measured results (raw evidence)

### ATTACK scenario (vacuous proof) — BYPASS
- Node final state (`evidence/lab/.e31-attack-node/byteball.sqlite`):
  - AA registered: `aa_addresses=[{address: PK4VVIAB…, unit: 0P8xeeEFnkY2…, mci: 1}]`
  - **AA response committed**: unit `CweplQ9rKcvKY0p8Hudqi46NPTCbnU0P60//hrlhHz4=`,
    `is_aa_response=1, sequence=good`
  - **Withdrawal output**: `(CweplQ9rKcvK…, output_index=1, address=TXJ6JUSEAG7LPHHLOVDYF652QOCW67ZF
    [the trigger author / attacker], amount=1000)`
  - Response input: `(src_unit=aCa72kZdlq1Y…, src_output_index=0)` — spent the trigger's 10000
    payment to the AA (the AA's received funds); value conservation held (10000 − 1000 −
    response commissions = change).
- Hub final state: identical response unit present; `HUB-DONE stable=5 aa_addresses=1`.
- Log anchors: `[hub] ATTACK data: element=attacker-NOT-A-MERKLE-MEMBER-2026
  proof=0-G8sKi+qJrfhSpeehuT63TryHRKaMx4bp31jYeh8S230=`; the trigger relayed and stabilized;
  `executing AA triggers` / `handleAATriggers … 3 PK4VVIAB7DC54PLBHZJJ4BBCTW5KYOF7`.
- Node exit: `SCENARIO-RESULT: attack withdrawals=1 BYPASS-CONFIRMED` (exit 0).

### CONTROL scenario (wrong-root proof) — correctly rejected
- Same AA, same trigger path, same stabilization, `data = {element: "some-member", proof:
  "0-" + sha256("different-root")}` (wrong root).
- Hub final state: `aa_addresses=1`, **responses=0**, withdrawals=0 — and the log shows the exact
  rejection path:
  ```
  message: 'neither case is true in messages',
  at bounce (aa_composer.js:903)
  ```
  The gate evaluated FALSE → no case matched → the AA **bounced** (no response, no withdrawal).
- Node exit: `SCENARIO-RESULT: control withdrawals=0 CONTROL-CONFIRMED (no withdrawal)` (the node
  run also showed no response; the node-side relay stalled on a get_joint race in this run — the
  hub-side result is the clean network-level control).

### The gate semantics (P9 cross-reference)
The same vacuous proof + `is_valid_merkle_proof` evaluated through the real formula engine
(evidence/lab/p9/p9-poc.js + evidence/round2/IR-F1.md): 4/4 arbitrary elements TRUE; wrong-root
FALSE; the sound `in merkle` predicate rejects the same proof without a posted feed.

## Why this is an escalation (marginal contribution)

- World without the bug: `is_valid_merkle_proof` would bind the root to an anchored value (like
  `in merkle`), so a non-member's withdrawal request would bounce — the whitelist holds.
- The delta: ANY actor can satisfy the gate with a self-consistent proof and withdraw the AA's
  funds. The AA's balance is drainable by anyone who can compute `sha256(element)` for any element.
- **Cap (unchanged):** which deployed AAs use the construct cannot be enumerated from ocore
  (individual AA repos out of scope). The ENGINE defect (F1) and its network-level exploitability
  are in scope; the fund impact is real for any AA using the pattern.

## Deliverables

- `evidence/lab/e31-aa-demo.js` — the runnable two-scenario demo
  (SCENARIO=attack|control, ROLE=hub|node, LAB_GENESIS_TS=1700000000).
- Raw DB state: `evidence/lab/.e31-attack-node/`, `.e31-attack-hub/`, `.e31-control-hub/`
  (synthetic genesis + lab keys only; retained for the record, destroyed at cleanup).
- Raw logs: `/tmp/e31-attack-node.log`, `/tmp/e31-attack-hub.log`, `/tmp/e31-control-hub.log`.

## Run instructions (independent reproduction)

```
cd /Users/matheusvsky/Documents/trab/obyte-ocore-2026-08-ocore  # not needed; run from the lab dir
cd <harness>/engagements/obyte-ocore-2026-08/evidence/lab
# terminal 1 (node):  LAB_GENESIS_TS=1700000000 ROLE=node PORT=6612 SCENARIO=attack node e31-aa-demo.js
# terminal 2 (hub):   LAB_GENESIS_TS=1700000000 ROLE=hub  PORT=6611 SCENARIO=attack node e31-aa-demo.js
# then repeat with SCENARIO=control (fresh scratch dirs). Expect: attack -> BYPASS-CONFIRMED
# (withdrawal output amount=1000); control -> 'neither case is true' bounce, no response.
```

## Residual risks / honest notes

1. The attack run's node-side path was fully exercised (definition → trigger → response on the
   node); the control run's NODE side stalled on a relay get_joint race (lab flakiness, not a
   mechanism issue) — the clean control is the HUB side, which ran the complete path (AA
   registered, trigger fired at stabilization, gate evaluated, bounce). Both sides ran identical
   real code; the control's rejection anchor is the `bounce('neither case is true')` log line.
2. The AA uses the `cases` form; the same result holds for any condition form (the gate is the
   evaluated formula — the engine result is what matters).
3. Individual AA logic (which deployed AAs gate on `is_valid_merkle_proof`) is out of scope —
   the finding remains the engine defect (F1) with this demonstration as its exploitability
   evidence.

## Cleanup

Lab processes killed after the runs; scratch dirs `.e31-*` retained as evidence (synthetic keys
only, no secrets) and destroyed at engagement cleanup; no ocore tree modifications (verified
`git status` clean apart from the pre-existing lab symlink).
