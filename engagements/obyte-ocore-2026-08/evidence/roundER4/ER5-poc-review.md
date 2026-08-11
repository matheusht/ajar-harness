# ER5 — Independent PoC verification: obyte-2026-08-001 (E3-1 fund-impact demo, e31)

**Role:** independent reviewer, fresh context. **Pinned target:** ocore
`a7eb776afc68ed4bed05ba554f7f1e95f5d49b44` (re-verified this review via `git rev-parse HEAD`;
working tree clean except untracked lab files `e32-flood.js`, `lab-obyte.js` — no tracked
modifications).
**Task:** run the maximum-impact PoC (e31-run.sh) from scratch, verify it runs cleanly and is
REAL (not mocked), spot-check the post-run DBs, and answer the program concern about
over-mocked/hypothetical scenarios.
**Disconfirming default:** nothing below is taken from prior summaries; every claim re-derived
from the pinned source, the raw logs of THIS run, and the fresh post-run sqlite DBs.

---

## Verdict

```json
{
  "id": "ER5",
  "verdict": "clean_pass",
  "evidence": "Fresh run of e31-run.sh: attack node exited 0 with 'SCENARIO-RESULT: attack withdrawals=1 BYPASS-CONFIRMED'; withdrawal output (amount=1000 to the trigger address TXJ6JUSEAG7LPHHLOVDYF652QOCW67ZF) found in the fresh .e31-attack-node/byteball.sqlite inside AA-response unit sGlVKS8x/DMFFqJNRcxV5bQDcczvIrU/4NCMi081qu8= (is_aa_response=1, sequence=good, authored by the AA PK4VVIAB7DC54PLBHZJJ4BBCTW5KYOF7); value conserved exactly (10000 = 8401 change + 1000 withdrawal + 288 hcomm + 311 pcomm). Control: withdrawals=0 on node AND gate bounce 'bouncing with error {message: \"neither case is true in messages\", xpath: \"/messages/cases\"}' at aa_composer.js:903 in BOTH control logs (node + hub); control DBs have 0 aa_responses and 0 outputs of 1000. Vacuous proof construction verified in script and recomputed: proof = '0-' + base64(sha256('attacker-NOT-A-MERKLE-MEMBER-2026')) = '0-G8sKi+qJrfhSpeehuT63TryHRKaMx4bp31jYeh8S230=', identical to the stored DB payload and the relayed joint; merkle.js deserialize('0-<root>') -> {index:'0', siblings:[], root} and verifyMerkleProof with 0 siblings reduces to hash(element)===root (source-verified at merkle.js:75-101, formula/evaluation.js:1763-1810). No mocks: real composer/validation/writer/stabilization/aa_composer/formula engine/network.js relay from the unmodified pinned tree.",
  "raw_lines": [
    "OVERALL-VERDICT: PASS — attack moves funds, control does not (full chain, real code path)",
    "RUNNER-EXIT=0",
    "[attack] node exit code: 0",
    "[node] SCENARIO-RESULT: attack withdrawals=1 BYPASS-CONFIRMED",
    "[node] AA_RESPONSES: [{\"u\":\"sGlVKS8x/DMF\",\"seq\":\"good\"}]",
    "[node] WITHDRAWAL-OUTPUTS (to non-AA addresses): ... {\"unit\":\"sGlVKS8x/DMFFqJNRcxV5bQDcczvIrU/4NCMi081qu8=\",\"output_index\":1,\"address\":\"TXJ6JUSEAG7LPHHLOVDYF652QOCW67ZF\",\"amount\":1000}",
    "[control] node exit code: 3 (demo aaFired polling heuristic; scenario outcome verified via withdrawals=0 + gate bounce on node AND hub)",
    "[node] SCENARIO-RESULT: control withdrawals=0 CONTROL-CONFIRMED (no withdrawal)",
    "bouncing with error { message: 'neither case is true in messages', xpath: '/messages/cases' }  at bounce (aa_composer.js:903:45)",
    "sqlite .e31-attack-node: is_aa_response=1 -> 1 row (sGlVKS8x/..., good); outputs amount=1000 -> 1 row (address TXJ6JUSEAG7LPHHLOVDYF652QOCW67ZF)",
    "sqlite .e31-control-hub: aa_responses=0, outputs=1000 -> 0",
    "sqlite .e31-control-node: aa_responses=0, outputs=1000 -> 0"
  ]
}
```

---

## 1. Fresh run (this review)

Command (run from the lab dir, ports 6611/6612 verified free, no leftover e31 processes):

```
bash e31-run.sh          # both scenarios, fresh scratch dirs (rm -rf per scenario)
```

Result: `OVERALL-VERDICT: PASS`, runner exit 0.

| scenario | node exit | node SCENARIO-RESULT line | gate anchor |
|---|---|---|---|
| attack | 0 | `attack withdrawals=1 BYPASS-CONFIRMED` | AA response composed + committed |
| control | 3 | `control withdrawals=0 CONTROL-CONFIRMED (no withdrawal)` | `bouncing with error {message: 'neither case is true in messages', xpath: '/messages/cases'}` at aa_composer.js:903 **in both the control-node and control-hub logs** |

The control node exit code 3 is a **demo polling heuristic, not a scenario failure**: the
node-side loop sets `aaFired` only when a 1-second poll catches `aa_triggers>0` or a response
unit; in control the whole chain (trigger stabilize → AA evaluate → bounce) completes faster
than the poll interval and the bounce correctly creates **no** response unit, so `aaFired`
stayed false (`process.exit(pass ? 0 : 3)` in e31-aa-demo.js). The gate was nevertheless
evaluated on the control node itself: its log shows `executing AA triggers` →
`handleAATriggers ... PK4VVIAB...` → `bouncing with error {message: 'neither case is true in
messages'}` — the wrong-root proof was rejected by the real formula engine on both processes.
The runner's fallback logic (CONTROL-CONFIRMED or hub bounce) is thus sound; both anchors
actually fired this run.

## 2. Independent DB spot-checks (fresh post-run DBs)

`.e31-attack-node/byteball.sqlite`:
- `SELECT unit, sequence, is_aa_response FROM units WHERE is_aa_response=1` →
  `sGlVKS8x/DMFFqJNRcxV5bQDcczvIrU/4NCMi081qu8= | good | 1`
- `SELECT ... FROM outputs WHERE amount=1000` →
  `sGlVKS8x/DMFFqJNRcxV5bQDcczvIrU/4NCMi081qu8= | 1 | TXJ6JUSEAG7LPHHLOVDYF652QOCW67ZF | 1000`
  (the trigger/attacker address — the withdrawal recipient)
- `SELECT payload FROM messages WHERE app='data'` →
  `{"element":"attacker-NOT-A-MERKLE-MEMBER-2026","proof":"0-G8sKi+qJrfhSpeehuT63TryHRKaMx4bp31jYeh8S230="}`
- Response unit author (unit_authors) = `PK4VVIAB7DC54PLBHZJJ4BBCTW5KYOF7` — the AA itself.
- Value conservation: trigger paid 10000 into the AA; response spends it as
  8401 (change) + 1000 (withdrawal) + 288 (headers_commission) + 311 (payload_commission)
  = 10000 exactly. Real funds moved.

`.e31-control-hub/byteball.sqlite` and `.e31-control-node/byteball.sqlite`:
- `aa_responses = 0`, `outputs WHERE amount=1000 = 0` in both.
- Hub stored control trigger payload: `{"element":"some-member","proof":"0-pmQ4NsZj5Ux5X6LrX0DIHP4znb4pakhyUeMlJDCP2nY="}` (wrong root).

Note: `messages.payload` is NULL for payment/definition messages on ALL units including the
genesis — confirmed normal ocore writer behavior (writer.js:166-180 stores payload text only
for `text`/`data`/`profile`/`attestation`/`definition_template`; payments are parsed into the
`outputs` table, which is the authoritative fund record used by validation/balances).

## 3. Source verification (pinned commit a7eb776)

- `formula/evaluation.js:1763-1810` — `case 'is_valid_merkle_proof'`: element must be a
  nonempty string; proof cap 1024 (`:1781`); bare-`mci`-gated sibling checks (`:1787-1791`,
  ≤50 siblings when `mci >= pemCurvesFixMci`); then `merkle.verifyMerkleProof(element,
  objProof)` with **no binding of the root to any committed/anchored tree** — matches the
  report's claim tuple.
- `merkle.js:75-78` `deserializeMerkleProof` splits on `-`, root = last element, index =
  first, siblings = the rest → `"0-" + b64(hash(X))` yields `{index:"0", siblings:[],
  root: hash(X)}`.
- `merkle.js:84-101` `verifyMerkleProof` with zero siblings computes `the_other_sibling =
  hash(element)` and returns `hash(element) === proof.root` → attacker-chosen root always
  verifies. The predicate is NOT always-true (negative control: wrong root → false, observed
  in control runs) — it proves self-consistency, not membership. Exactly the finding.
- `merkle.js:5` `hash()` = `sha256(str, utf8).digest('base64')` — byte-identical to the demo's
  `sha256b64`. Recomputed independently:
  - `sha256b64("attacker-NOT-A-MERKLE-MEMBER-2026")` = `G8sKi+qJrfhSpeehuT63TryHRKaMx4bp31jYeh8S230=` ✓ (DB payload + relayed joint)
  - `sha256b64("different-root")` = `pmQ4NsZj5Ux5X6LrX0DIHP4znb4pakhyUeMlJDCP2nY=` ✓ (control proof)
- `aa_composer.js:903` bounce() and `:729` "neither case is true in …" — both stack traces in
  the control logs cite `aa_composer.js:903:45`, matching the report's citation.
- AA address independently recomputed via `object_hash.getChash160(["autonomous agent",
  {bounce_fees:{base:10000}, messages:{cases:[{if:"{is_valid_merkle_proof(trigger.data.element,
  trigger.data.proof)}", messages:[…amount:1000…]}]}}])` =
  `PK4VVIAB7DC54PLBHZJJ4BBCTW5KYOF7` — matches the address both nodes registered.

## 4. Mock / reward-hacking audit

- **Real stack, unmodified tree.** e31-aa-demo.js + e17b-boot.js load and drive the real
  `db.js`, `storage.js`, `network.js`, `validation.js`, `object_hash.js`, `composer.js`,
  `writer.js`, `aa_composer.js`, `formula/evaluation.js`, `merkle.js`, `conf.js`,
  `desktop_app.js` from the pinned ocore tree (git status: clean except untracked lab files).
  Logs show the real chain end-to-end: `composer.composeJoint` → `validation.validate`
  ("VALIDATION OK sequence=good", "AA validated, complexity = 1, ops = 8") →
  `writer.saveJoint` → stabilization (`stabilized MCI …`, ball computation, `updateTpsFees`)
  → `executing AA triggers` → `handleAATriggers` → formula evaluation → response composition →
  validation + commit ("committed unit …", "SENDING result accepted").
- **Real two-process relay network.** Node runs a real `WSS running at port 6612` server;
  hub connects `ws://127.0.0.1:6612`, does the real version handshake
  (`justsaying/version`, `request/subscribe`, `response subscribed`) and relays joints
  (`justsaying/joint`, `result accepted`) — all visible in the raw logs with byte counts.
- **Real AA, no stub engine.** The AA is a standard `["autonomous agent", {bounce_fees,
  messages:{cases:[{if:"…", messages:[payment]}]}}]` definition — the exact shape
  aa_composer.js evaluates. Its `if` is `{is_valid_merkle_proof(trigger.data.element,
  trigger.data.proof)}` — a realistic membership/whitelist gate pattern.
- **No hardcoded expectations.** The demo derives the verdict from the real `outputs` table
  (withdrawals = outputs of amount 1000 to non-AA addresses) and real `units` rows; the
  proof strings are computed, not hardcoded. The runner's per-scenario PASS/FAIL comes from
  grep on the node's printed verdict plus exit code.
- **Only synthetic elements:** (1) fixed lab keys + synthetic genesis (e17b-boot.js, clearly
  commented "lab-only, synthetic; never used on any real network") and (2) the AA itself —
  the realistic vulnerable pattern under test. No engine, protocol, or DB layer was stubbed,
  faked, or patched.

## 5. Program concern: overly-mocked/hypothetical?

**No.** The mechanism is real, unmodified ocore code (formula engine, merkle.js, aa_composer,
composer, validation, writer, stabilization, relay networking) demonstrated end-to-end on a
real two-process network with real websocket relay, real signatures (secp256k1 via the real
signer path), and real funds movement verified in the DB with exact value conservation. The
**only** synthetic element is the vulnerable AA itself — and that is the honest and minimal
demonstration vehicle: the finding is precisely that *any AA using `is_valid_merkle_proof` as a
membership gate is bypassable*, so the PoC builds exactly such an AA (a withdrawal gated on
merkle membership — a realistic whitelist/authorization pattern) and shows a non-member
triggers the withdrawal with a self-consistent proof. This is not a hypothetical scenario: the
construct is a real shipped formula primitive (source-verified) and the AA pattern mirrors how
such gates appear in practice.

## Findings / residual risks

- **Note (demo heuristic, not a finding):** control node exit 3 comes from the 1-second
  `aaFired` polling heuristic missing the fast bounce (no response unit to observe). The
  scenario outcome is unaffected (withdrawals=0 verified in DB; gate bounce logged on both
  control processes). Cosmetic: the runner's "[control] PASS — node-side" message is accurate
  here only because the node did evaluate and bounce; on a future run where the node misses the
  relay entirely, the hub bounce anchor (also present in the runner) carries the proof.
- **Note (environment):** ran on Node v25.9.0 (ocore targets older LTS); ran cleanly, but
  reproducibility on a different Node version is unverified.
- **Note (severity framing unchanged):** Medium, usage-capped — which deployed AAs use
  `is_valid_merkle_proof` is not enumerable from ocore (AA repos out of scope); the engine
  defect and its end-to-end exploitability are confirmed.
- **Residual (inherent):** the demo's AA is synthetic-by-design (the vulnerable pattern); the
  engine-level claim rests on source (root never bound) + negative control (wrong root →
  bounce; `in merkle` soundness previously measured in p9/IR-F1).

## Files

- This report: `evidence/roundER4/ER5-poc-review.md`
- Fresh logs: `evidence/lab/e31-attack-node.log`, `e31-attack-hub.log`,
  `e31-control-node.log`, `e31-control-hub.log` (overwritten by this run)
- Fresh DBs: `evidence/lab/.e31-attack-node/byteball.sqlite`, `.e31-control-hub/`,
  `.e31-control-node/` (recreated by this run)
