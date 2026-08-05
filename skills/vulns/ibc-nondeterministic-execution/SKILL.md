---
id: cosmos.ibc-nondeterministic-execution
name: Non-Canonical Serialization Causing Consensus Divergence
description: >
  Prove that a state-machine code path (IBC packet/acknowledgement handling, or any other
  message-processing logic) trusts untrusted input bytes without verifying they are the CANONICAL
  serialization of the logical value they claim to represent — most concretely, when two or more
  independent code paths (an application module and a middleware wrapping it, or a relayer and the
  chain) can each produce their own serialization of the same logical value, and nothing forces
  those independent serializations to agree byte-for-byte before the value is trusted as committed
  state. Logically-equivalent input can then produce different committed bytes depending on which
  code path produced them, causing divergent app hashes across validating nodes. This is NOT simply
  "the code uses a Go map" — Go's own `encoding/json.Marshal` already sorts map keys, so a bare
  unmarshal-into-map-then-remarshal-via-stdlib round trip is not inherently order-unsafe. The real
  defect is missing canonicalization/byte-equality enforcement across independent serializers, not
  raw map iteration order.
type: vuln
owasp: "No single CWE fits cleanly — a determinism-violation class specific to replicated state machines, distinct from ordinary memory-safety or logic bugs"
atlas: "—"
patterns: []

activation:
  strong:
    - "a logical value (e.g. an IBC acknowledgement, a packet payload) can be produced or re-serialized by more than one independent code path (an application module's own canonical marshal function vs. a middleware wrapping it, e.g. packet-forward-middleware or ibc-hooks) and nothing checks that the bytes from each path are byte-identical before the value is trusted as committed"
    - "untrusted bytes are unmarshalled into a Go interface{}/map[string]interface{} (or equivalent dynamically-typed structure) and then manually iterated, concatenated, or re-serialized WITHOUT going through a canonicalizing marshal function (i.e. NOT simply passed to encoding/json.Marshal, which already sorts map keys) — this is the actual order-unsafe case, not a bare unmarshal-into-map by itself"
    - "the vulnerable path is reachable by ANY user able to trigger the input (e.g. opening an IBC channel, sending a packet) — no privileged access required, which is the difference between a low-severity theoretical concern and a directly reachable chain-halt"
  weak:
    - "a dynamically-typed unmarshal exists, feeds into state-affecting logic, but only a single serialization implementation ever touches the value (no middleware/app divergence, no manual non-canonical re-serialization) — lower priority, confirm there's genuinely no second code path before treating as strong"
  negative:
    - "the same single canonical serialization function is the sole path used both to CREATE and to RE-VERIFY the committed bytes everywhere the value is produced or consumed, including every middleware layer that touches it → likely held. Note: a fixed, statically-typed struct alone does NOT establish this — the real disclosed anchor for this class used a fixed protobuf oneof struct and was still vulnerable, because a middleware's independent serialization of that same struct type could diverge from the app's own canonical marshal. Confirm single-serializer-everywhere, not just fixed-struct-type, before treating as held."

safe_signal:
  proxy: >
    a local, small multi-node test cluster (minimum viable size to actually observe divergence
    between validators — a single node cannot demonstrate consensus divergence) running the real,
    unmodified module and middleware code, where a locally-crafted payload that is byte-different
    but logically-equivalent across two real serialization paths in scope is submitted, and the
    resulting app hashes are compared across nodes to show they diverge, reproduced via real code,
    not a description of what non-canonical serialization theoretically allows.
  never: >
    never submit the triggering payload against any live public mainnet or testnet; the local
    multi-node cluster must be entirely self-operated with locally-generated validator keys and no
    real economic value at stake.

impact_escalation:
  enabled_by: scope.md#impact_demo_authorized
  requires: >
    benign/non-destructive local reproduction proceeds without a per-artifact pause under this
    engagement's standing Zone-2 authorization (see scope.md); note this class specifically may
    require a small local multi-node cluster rather than a single node to demonstrate divergence —
    still within the authorized local/disposable/self-controlled boundary, not an escalation beyond it
  containment: "local disposable multi-node test cluster only; logged in engagement cleanup.md"

oracle: [whitebox-analysis, regrade-oracle, pocinator-oracle]
severity_rubric: { unauthenticated_reachable_consensus_divergence_reproduced: critical, privileged_precondition_required_for_divergence: high, dynamic_unmarshal_confirmed_no_reachable_divergence_path: medium }

procedure:
  - "IDENTIFY EVERY PLACE A LOGICAL VALUE IS SERIALIZED/DESERIALIZED across more than one independent code path: an application module's own canonical marshal function AND any middleware wrapping it (packet-forward-middleware, ibc-hooks, custom middleware in scope) that also touches the same value's bytes."
  - "CHECK FOR A CANONICALIZATION/BYTE-EQUALITY GATE: does the code re-marshal received bytes via the single canonical function and reject if the result doesn't byte-equal what was submitted (the actual fix pattern used in the disclosed anchor), or does it simply trust whatever bytes arrived from any path?"
  - "SEPARATELY, GREP FOR MANUAL NON-CANONICAL SERIALIZATION: unmarshal into interface{}/map[string]interface{} followed by hand-rolled iteration/concatenation that does NOT go through a canonicalizing marshal (encoding/json.Marshal, protobuf marshal, or equivalent) — this is genuinely order-unsafe, unlike a bare unmarshal-then-stdlib-remarshal round trip."
  - "IDENTIFY THE REACHABILITY BAR: who can trigger this path? The disclosed anchor for this class is reachable by any user who can open an IBC channel — no special privilege. Confirm the actual reachability bar for any candidate before treating severity as high."
  - "BUILD A REAL LOCAL MULTI-NODE REPRODUCTION: stand up a small local cluster (the minimum needed to observe cross-node divergence, not just single-node crash behavior) running the real module AND middleware code, and submit a payload constructed to be byte-different but logically-equivalent across the two real serialization paths identified above."
  - "OBSERVE ACTUAL APP-HASH DIVERGENCE (or absence of it): compare state roots/app hashes across the local nodes after processing the payload. A negative result here is real evidence worth logging, not grounds to force a 'confirmed' — but don't conclude negative from a single run without first confirming you actually constructed a genuinely divergent-serialization payload, not just a plain map that stdlib Marshal would sort identically anyway."
  - "CHECK RELEASE ELIGIBILITY: this exact disclosed instance was patched (ibc-go v7.10.0/v8.7.0, extending an earlier narrower fix at v7.9.2/v8.6.1) — confirm the pinned/released version in scope for any candidate."

emits: [attempt, finding]
---

## What "confirmed" looks like here
A real local multi-node reproduction, using the actual unmodified module and middleware code, shows
that a payload which is byte-different but logically-equivalent across two independent real
serialization paths in scope produces divergent state/app hashes across nodes, with the exact
reachability bar (who can trigger it) and the two diverging code paths both stated precisely.

## Real disclosed anchor for this class (verified against the primary advisories and the live source
- patched; use as a taxonomy template for the canonicalization-gap pattern, not for "uses a Go map")
- IBC-Go's `Acknowledgement` type is a fixed protobuf oneof struct, not a dynamically-typed map — a
  fixed struct type alone did not prevent this bug. The actual gap: acknowledgement bytes arriving
  via a relayer or a middleware (e.g. packet-forward-middleware, ibc-hooks) were not checked for
  byte-equality against the channel keeper's own canonical marshal
  (`ModuleCdc.MarshalJSON` wrapped in `sdk.MustSortJSON`) before being trusted as committed state. A
  middleware using a different serialization implementation than the transfer app's own could
  produce non-canonical-but-semantically-equal bytes for the same logical acknowledgement, causing
  divergent app hashes across nodes that received the value via different paths. Reachable by ANY
  user able to open an IBC channel — no privileged access required. Fixed by adding an explicit
  re-marshal-and-byte-compare canonicalization gate. ASA-2025-001 / GHSA-4wf3-5qj9-368v
  (2025-03-12), High/Critical, affecting ibc-go v7 < 7.10.0 and v8 < 8.7.0, touching the core channel
  keeper so the fix applies to all IBC applications (extending an earlier narrower fix,
  GHSA-jg6f-48ff-5xrw / ASA-2025-004, that had only covered the ICS-20 transfer-app instance).

## Not this card
- A dynamic-unmarshal path whose result never influences serialized state, hashing, or branching
  logic in an order-sensitive way (e.g. purely used for a single deterministic field lookup) →
  weak/negative, not this card's strong activation.
- A bare `json.Unmarshal` into `map[string]interface{}` immediately followed by
  `json.Marshal` with no other serialization path touching the same value → not order-unsafe on its
  own; Go's stdlib `Marshal` sorts map keys. Only strong-activation if a second independent
  serializer also touches the value, or if re-serialization bypasses the canonicalizing marshal.
- A crash reproducible identically on every node (deterministic panic) → that's
  `cosmos.unchecked-arithmetic-panic-dos` or a similar deterministic-fault class, not this one; the
  defining feature of this card is *divergence between nodes*, not merely *failure*.

## Do not overclaim
- "This uses map[string]interface{}" alone is not a finding and not even a strong activation signal
  by itself — Go's `encoding/json.Marshal` already sorts map keys, so this pattern alone is not
  inherently order-unsafe. The real signal is a second independent serialization path (middleware vs.
  app) or a hand-rolled, non-canonicalizing re-serialization.
- "This is a fixed struct type, so it's safe" is also not a valid negative — the real disclosed
  anchor used a fixed protobuf oneof struct and was still vulnerable, because independent
  serialization implementations touching that same struct type could diverge. Confirm there is a
  single canonical serializer used everywhere the value is produced or consumed, not just that the
  type itself is statically typed.
- A single test run showing no observed divergence is weak evidence of safety for this class,
  especially if the test payload was never actually constructed to diverge across two real
  serialization paths in the first place — don't claim `refuted` from one negative run without first
  confirming the payload construction genuinely exercised the canonicalization gap.
