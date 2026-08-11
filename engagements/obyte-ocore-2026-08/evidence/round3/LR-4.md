# LR-4 — Blind no-new-family sweep (prior-free)

**Role:** LR-4, terminal-round blind sweep. **Rule honored:** read ONLY the pinned source tree
(`/Users/matheusvsky/Documents/trab/obyte-ocore-2026-08-ocore` @ `a7eb776afc68ed4bed05ba554f7f1e95f5d49b44`),
no engagement files, no priors. This is the coverage-dry requirement: an honest negative is the
expected outcome; I did not manufacture findings.

## Surfaces covered (blind, by mechanism rather than by file)

| surface | files read | verdict |
|---|---|---|
| E2E device-message layer (encryption, hub login, temp-key rotation, message processing) | device.js (full), network.js hub/deliver + hub/message | **NEW FAMILY — one candidate (see F1)** |
| Formula object building & key handling | formula/evaluation.js (state/local/response var assignment, assignByPath, json_parse, dictionary, selectSubobject), formula/common.js (assignField/assignObject), string_utils.js cloneDeep | held (safe) |
| External payload / SSRF | validation.js payload_location/uri checks; grep of all outbound http | held (no core fetch) |
| Deep-link / URI parsing | uri.js | held (wallet, operator-gated) |
| DB layer | sqlite_pool.js, kvstore.js, db.js | held (known pattern: no query-callback try/catch) |
| Signed-message validation | signed_message.js (full validation path) | held |
| Multisig wallet plumbing | wallet_defined_by_addresses.js, wallet_defined_by_keys.js | held (wallet-side, signing-path checks present) |
| Graph inclusion heuristic | graph.js determineIfIncluded/OrEqual | held (sound limci/level/wl fallbacks) |
| Wallet contracts money math | arbiter_contract.js (cut/floor arithmetic), prosaic_contract.js | held (floor-conservative; wallet feature) |
| Trigger params / data-feed param evaluation | formula/evaluation.js evaluated_params | held (self-inflicted by AA author only) |

## NEW FAMILY F1 — E2E device-message layer: remote wallet crash via a scheduled uncaught throw

**Mechanism (device.js:431-432, inside `decryptPackage`):**
```js
else{
    console.log("message encrypted to unknown key, device "+my_device_address+" ...");
    setTimeout(function(){
        throw Error("message encrypted to unknown key, device "+my_device_address+" ...");
    }, 100);
    return null;
}
```
When an incoming E2E device message's `dh.recipient_ephemeral_pubkey` matches none of the wallet's
temp key, previous temp key, or permanent key, the handler **schedules** a throw 100 ms later. The
`try/catch` around `decryptPackage` (device.js:177-181) does **not** catch it (the throw fires after
the catch scope has exited) → `uncaughtException` → process death.

**Reachability (verified in source):**
1. Attacker (any peer with a signing key) delivers an E2E message via `hub/deliver`
   (network.js:3322-3380): the entry validates only presence of fields + signature + address shape;
   **no pairing/correspondent requirement** is visible — the attacker addresses the victim's device
   address (public — appears in the DAG) and chooses `dh.recipient_ephemeral_pubkey` arbitrarily.
2. The hub stores/forwards the message; the victim's wallet processes it when online
   (`message_from_hub` → device.js:136-200 `handleJustsaying` → `decryptPackage`).
3. The attacker-chosen key matches nothing → the else branch → scheduled throw → crash 100 ms later.
4. Repeatable: the attacker can deliver repeatedly; each delivery re-crashes.

**Why this is a NEW family:** the 16 round-0 families covered validation, main-chain, signature,
definition, formula, assets, private payments, network protocol, storage/catchup, AA engine,
encoding/hash, races, fail-open, composer/signing, and economics — none covered the E2E
device-message decryption layer's crash behavior. This is a distinct crash class from the
validation-layer throws (which were refuted as unreachable): this one is **reachable remotely with
zero cost** on any wallet processing hub messages.

**Scope/severity note (honest):** this is the **wallet/device layer**, not the DLT full-node
(relays/hubs don't hold device keys and don't run this handler). The program scope is
"Blockchain/DLT only" per the operator; a wallet-process crash is a client-availability issue whose
fix is node-side (replace the throw with a clean event) → per the engagement's DoS-coordination
rule this is the **out-of-scope class** for the bounty, but it is a genuine, remotely-triggerable
robustness defect in the fund-handling client shipped by this library (and Obyte has historically
treated wallet-layer fixes as critical — the 2018 chat XSS→RCE). Flag for the operator; do not
self-promote beyond a Low/robustness candidate.

## Checked-and-held observations (with the decisive control)

- **H1 — `__proto__` as a formula state-var name: held/safe.** `readVar` and the assignment paths
  use `assignField` (`Object.defineProperty`, formula/common.js), which creates an own property
  instead of setting the prototype; `storage.js:17` confirms `__proto__` state vars are deliberately
  supported and the freeze was rejected because of it. `assignByPath`, local/response var
  assignment, and `cloneDeep` (string_utils.js:401) all handle `__proto__` via defineProperty.
  No prototype-pollution path found.
- **H2 — outbound HTTP: no core SSRF.** Only `arbiter_contract.js:388` performs an outbound
  `http.request` (to the operator-configured arbstore). `payload_uri` messages are validated
  (length ≤500, trimmed, hash-bound; validation.js:1581-1593) but **never fetched by the core**.
- **H3 — formula object building is key-safe.** Dictionary literals, `selectSubobject`,
  `filterBySearchCriteria`, `json_parse`, and `assignByPath` all either use `assignField` or
  JSON.parse's own-property semantics. No raw `obj[key]=` with formula-controlled `__proto__`.
- **H4 — decryptPackage recursion depth-capped** (device.js:404 `depth > 2` → stop).
- **H5 — signed_message validation is complete** (field allowlist, author sorting, definition-chash
  binding, authentifier length caps).
- **H6 — graph.js inclusion heuristic is sound** (limci/level/witnessed-level fallbacks; the
  worst-case outcome is the standard fork race, not a validity error).
- **H7 — trigger/data-feed param evaluation** (`evaluated_params[param_name] = ...`,
  formula/evaluation.js:680-892): a `__proto__` param_name would corrupt only the local
  `evaluated_params` object's prototype — self-inflicted by the AA author (they author the trigger
  config), no cross-party impact.
- **H8 — arbiter_contract cut math** uses `Math.floor` (conservative rounding) and the `cut` comes
  from the operator's arbstore config; wallet feature, out of DLT scope.

## No-new-family verdict (coverage-dry contribution)

One new candidate family (F1, E2E device-layer wallet crash, remote/zero-cost, wallet-layer scope
question) — everything else checked and held. No second new family surfaced.

## Files

- This report: `evidence/round3/LR-4.md`
- No scripts run (blind source-trace only, per the brief)
