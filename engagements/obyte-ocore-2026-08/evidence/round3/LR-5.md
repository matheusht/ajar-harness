# LR-5 — Hub surface (bServeAsHub)

**Pinned:** ocore `a7eb776afc68ed4bed05ba554f7f1e95f5d49b44`. **Role:** round-3 terminal audit.
**Scope:** network.js hub paths, device.js login, hub/deliver + hub/message mailbox,
device_messages storage, peer auth. Local-only source audit; no live contact.

## Verdict (one line)

**No fund-class finding on the hub surface.** Authentication is sound (challenge-response +
signature; device address pubkey-derived), cross-device operations are scoped to the caller,
message content is E2E-encrypted (the hub cannot read or forge it), and hub SQL is parameterized.
The only material observations are chat-layer storage/spam DoS vectors — below the program's
minimum impact (no theft/freezing class) and node-side-fixable (out of scope per the DoS
coordination rule).

## Surface covered (file:line)

- `network.js:3347-3421` — `hub/deliver` (message insertion + forwarding)
- `network.js:2839-2908` — `hub/login` (challenge-response auth)
- `network.js:2908-2956` — `hub/delete`, `hub/update_correspondent_settings`, `hub/repeat_challenge`
- `network.js:2956-2960` — `hub/message` / `hub/message_box_status` (from-hub dispatch)
- `network.js:2581-2620` — `sendStoredDeviceMessages` / `deleteOverlengthMessagesIfLimitIsSet`
- `network.js:3422-3442` — `hub/get_temp_pubkey` / `hub/temp_pubkey`
- `network.js:3984-4080` — `hub/enable_notification`, `hub/get_bots`, `hub/get_asset_metadata`,
  `hub/get_arbstore_*`, `hub/get_exchange_rates`
- `device.js:250-293` — `loginToHub` / `sendLoginCommand`
- `initial-db/byteball-sqlite.sql:540-548` — `device_messages` DDL (no purge, no count cap)

## Findings

### H1 — Hub auth: sound (HELD, positive control)
`hub/login` (network.js:2839-2889): challenge must match `ws.challenge` (issued per connection),
`pubkey`/`signature` length-checked, signature verified over
`getDeviceMessageHashToSign(objLogin)` (network.js:2875-2879). `ws.device_address =
getDeviceAddress(pubkey)` — the address is a hash of the pubkey, so only the private-key holder
can authenticate as that device. Failed login leaves `ws.device_address` unset; commands requiring
login (`hub/delete`, `hub/refresh`, `hub/update_correspondent_settings`) check it. No spoofing or
login-confusion path found. `hub/deliver` verifies the SENDER's signature (network.js:3373-3375)
and requires the recipient's ephemeral pubkey to match the registered device's pubkey/temp pubkey
(network.js:3385-3387) — an attacker cannot deliver a message encrypted to a key the victim does
not hold, and cannot forge a message as the victim.

### H2 — Cross-device access: scoped (HELD)
`hub/delete` (network.js:2917-2921) and `hub/update_correspondent_settings` (network.js:2937-2945)
scope every query by `ws.device_address` — a device can only delete its own messages and set its
own correspondent settings. No cross-device parameter found.

### H3 — Message content confidentiality/integrity: E2E (HELD)
`hub/deliver` stores the full signed, E2E-encrypted package; the hub never decrypts. A malicious
hub could not read message content (needs the recipient's key) and could not forge content as a
peer (needs the peer's key). It CAN censor/drop (liveness) — inherent to the store-and-forward
model, not a code defect.

### O1 — Unbounded device_messages storage growth (mailbox flood) — below minimum, hardening note
`hub/deliver` (network.js:3391-3395) inserts one row per message; `message_hash` is the PK (dup
ignored), but distinct content = distinct hash = new row. There is NO count-based or age-based
purge: the only deletes are overlength-at-refresh (network.js:2591) and owner-delete
(network.js:2918). `sendStoredDeviceMessages` reads at most `max_message_count` (default 100,
network.js:2602) — a READ cap, not a storage cap. Any key-holder can insert unlimited messages
for any REGISTERED device address (the recipient must exist: network.js:3378-3381), growing
`device_messages` until disk exhaustion on the hub. Chat-layer; no fund impact; a node-side fix
(count cap / TTL purge) resolves it without network coordination → **out of scope per the DoS
coordination rule**. Recorded for hardening.

### O2 — Push-notification spam amplification — below minimum
Every delivered message with `push_enabled` default (network.js:3409-3413) emits
`peer_sent_new_message` → push. A mailbox flood amplifies into push spam. Same class as O1.

### O3 — Light-vendor trust model (the only fund-adjacent hub path) — documented design, out of scope
The hub can also serve as light vendor (`light/*` commands); a malicious vendor could serve forged
history/balances to ITS light clients (whose keys remain local). This is the documented light-client
trust model (f3/f9/f10 adjudications: light clients trust their vendor by design; out of scope).
LR-1 owns the light-client side. No additional hub-side weakness found in the vendor command
surface (param validation thorough — f9 H3).

### O4 — hub/get_arbstore_* (network.js:4014-4080) — out of DLT-core scope
Arbiter-contract store lookups to an external HTTP service; arbiter/prosaic contracts are
wallet-layer features (f16: not DLT-consensus surfaces). Skimmed; no parameterization issue found.

## S2 sweep (hub handlers) — CLEAN
hub/deliver + hub/login + hub/delete + settings queries are parameterized (`?` placeholders); the
only concatenations are the constant keyword `db.getIgnore()` and error strings. No unescaped
interpolation of attacker input (contrast the V-001 family). Verified by reading each query site
in the hub handler ranges above.

## Dispositions vs the brief's questions

| question | disposition |
|---|---|
| (1) mailbox abuse with fund-adjacent impact | **none found** — flood is chat-layer (O1/O2), below minimum; no fund class reachable (E2E content, scoped ops, sound auth) |
| (2) hub spoofing / login confusion | **none found** — challenge-response signature auth; pubkey-derived addresses; cross-device scoping (H1/H2) |
| (3) fund classes (theft/freezing) or below-minimum | **no fund class**; O1/O2/O3 are below-minimum hardening notes; the light-vendor trust model (O3) is the only fund-adjacent surface and is documented design |

## Verdict JSON

```json
{
  "id": "LR-5",
  "verdict": "held (no finding) + 2 hardening notes",
  "evidence": "H1/H2/H3 auth+scoping+E2E verified at network.js:2839-3421; O1 storage-growth at network.js:3391-3395 + initial-db/byteball-sqlite.sql:540-548 (no purge); O2 at network.js:3409-3413; S2 sweep clean",
  "raw_evidence": "evidence/round3/LR-5.md"
}
```
