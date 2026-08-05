---
id: cosmos.ics23-proof-verification-laxity
name: ICS-23/Merkle Proof Verification Laxity (Forgeable Membership Proof)
description: >
  Prove that a merkle/ICS-23 proof-verification code path accepts a proof that does not actually
  establish what it claims — most concretely, checking a leaf or inner-node prefix by containment
  (substring match) rather than exact match, or deriving verification parameters (prefix, hash
  function, encoding) from data carried inside the proof itself rather than from a fixed, pinned
  spec — such that an attacker can construct a proof for a key/value pair that was never actually
  committed to the tree, and have it VERIFY as valid. A theoretical laxity in the spec with no
  actually-forged, actually-accepted proof is coverage, not a finding.
type: vuln
owasp: "CWE-347 (Improper Verification of Cryptographic Signature) / CWE-354 (Improper Validation of Integrity Check Value) — applied to merkle-proof verification specifically, not signature schemes"
atlas: "—"
patterns: []

activation:
  strong:
    - "a proof-verification code path checks a leaf/inner-node prefix using containment (bytes.Contains / strings.Contains / HasPrefix-as-sufficient-condition) rather than exact match (bytes.Equal) against the expected value"
    - "verification parameters (leaf prefix, hash function identifier, key/value length encoding) are read from data carried inside the proof itself rather than from a hardcoded/pinned specification the verifier controls independently of the prover"
    - "a module allows user-controlled arbitrary-bytes storage into the same merkle-tree namespace that IBC/cross-chain proofs are verified against, without domain-separating leaf-value bytes from nested-substore-root bytes (the tree can't distinguish 'this is a value' from 'this is a pointer to another subtree')"
  weak:
    - "a proof-verification path exists but the specific comparison function used (exact-match vs. containment) has not yet been read directly from source — confirm before treating as strong; do not infer from documentation alone"
  negative:
    - "prefix/parameter checks use exact-match comparisons throughout (bytes.Equal-style), and verification parameters are pinned by the verifier independently of prover-supplied data → likely held"
    - "the merkle store namespace domain-separates raw values from substore roots such that a value leaf can never be reinterpreted as a subtree root → likely held"

safe_signal:
  proxy: >
    a local test chain with the real, unmodified ICS-23/IAVL verification code, where you construct
    a proof (using real proof-construction code, not a hand-built fake) for a key/subkey-value pair
    that was never actually stored, and demonstrate the real verifier function ACCEPTS it as valid —
    the benign marker is the verifier's own accept/reject return value on a locally-crafted case you
    fully control, never an attempt to forge a proof against any real cross-chain state.
  never: >
    never construct or submit a forged proof against any live IBC connection, public mainnet, or
    public testnet; all proof construction and verification happens against a local, self-controlled
    test tree with locally-created, non-sensitive test data.

impact_escalation:
  enabled_by: scope.md#impact_demo_authorized
  requires: >
    benign/non-destructive local reproduction proceeds without a per-artifact pause under this
    engagement's standing Zone-2 authorization (see scope.md)
  containment: "local disposable test chain/tree only; no real cross-chain proof interaction; logged in engagement cleanup.md"

oracle: [whitebox-analysis, regrade-oracle, pocinator-oracle]
severity_rubric: { forged_proof_accepted_for_unstored_value_reproduced: critical, comparison_laxity_confirmed_forgery_not_yet_demonstrated: high, theoretical_design_pattern_no_reachable_precondition: low }

procedure:
  - "READ THE ACTUAL COMPARISON CODE: locate every place in scope (ics23, iavl, ibc-go's client-state verification) that compares a proof-supplied prefix, hash, or encoding against an expected value, and determine exactly which comparison primitive is used — exact-match or containment/prefix-sufficient."
  - "IDENTIFY PARAMETER PROVENANCE: for each verification parameter used (leaf prefix, hash function, length encoding), determine whether it comes from a value the verifier pins independently, or from data the prover/proof itself supplies — the latter is the historically exploited pattern (Dragonberry)."
  - "CHECK RELEASE ELIGIBILITY FIRST: the historical anchor for this class (Dragonberry) was fixed cosmos-sdk-wide via a custom ics23 fork with explicit length checks, affecting only pre-2022-10-16 IBC versions and cosmos-sdk <=0.45.9 — confirm any candidate is either a genuinely distinct gap or a regression at the exact pinned/released version in scope, not the already-patched historical bug."
  - "CONSTRUCT A REAL FORGED PROOF: using the real proof-construction library/types in scope (not a hand-rolled proof object), build a proof for a key/subkey-value pair you know was never actually stored in a local test tree you control."
  - "SUBMIT TO THE REAL VERIFIER: call the actual, unmodified verification function with your forged proof and observe whether it returns accept or reject — this is the entire finding; a forged proof that gets rejected is a negative result, not a finding."
  - "NEGATIVE CONTROL: verify a genuine, honestly-constructed proof for actually-stored data is accepted (establishing the verifier works at all) and a proof for a genuinely different, real key is rejected, isolating that your specific forgery technique (not general verifier breakage) is what succeeds."
  - "ASSESS DOWNSTREAM IMPACT: if the forged proof is accepted, trace what a caller (an IBC light client, a cross-chain query) would do with the now-falsely-verified value — the severity depends on what state/action that falsely-proven value can unlock, not merely that a proof was forged in isolation."

emits: [attempt, finding]
---

## What "confirmed" looks like here
A real, constructed forged proof (using the actual in-scope proof types, never a hand-built
emulation) for a key/value pair never actually stored is shown, via the real unmodified verifier
function on a local test tree, to be ACCEPTED as valid — with a negative control confirming genuine
proofs still work correctly and a false claim for a genuinely different key is still rejected, and
the downstream impact of the false accept traced to a concrete consequence.

## Real disclosed anchors for this class (verified, cited — both historical/patched or explicitly
theoretical; use as taxonomy templates for finding regressions or structurally similar gaps, not as
currently-exploitable bugs in patched, released code)
- **Dragonberry (high confidence)**: ICS-23 checked a proof's leaf prefix by CONTAINS rather than
  EXACT match, and allowed proof parameters to be proof-supplied rather than verifier-pinned; for
  any already-stored key with a suffix of the form `len(subkey) | subkey`, an attacker could forge a
  membership proof for a subkey-value pair never actually stored, forging IBC state proofs across a
  connection. VSA-2022-103 (Verichains), affected all IBC-enabled Cosmos chains on IBC released
  before 2022-10-16 and cosmos-sdk <=0.45.9. Framed by Verichains and the official Cosmos Hub
  retrospective as billions of dollars theoretically at risk ecosystem-wide; no funds actually lost.
  Fixed via a cosmos-sdk-maintained ics23 fork adding explicit length checks.
- **Fake-subtree proof splicing (low confidence, theoretical, weaker signal)**: cosmos-sdk#5440
  (filed by Aditya Sripal, Dec 2019, closed Jun 2020), documenting a concern raised by Zaki Manian
  and crediting Jae Kwon, per a contemporaneous comment, as having originally proposed the attack —
  a design-pattern warning that a chain allowing arbitrary user data into
  the same merkle namespace IBC proofs are verified against could, in principle, let an attacker
  submit a fabricated subtree root as an ordinary leaf, obtain a genuine proof it's committed, then
  splice on a locally-fabricated nested proof. A core-team maintainer noted a scoping mitigation (IBC
  only trusts the `ibc/` subtree) that likely blocks direct exploitability without an additional
  compromise; treat this as a design-review-style weak activation signal, not a confirmed
  exploitable mechanism — do not claim `confirmed` from this anchor alone without your own fresh,
  concrete reproduction.

## Not this card
- A signature-verification bypass (ordinary cryptographic signature, not a merkle/inclusion proof)
  → route to `skills/vulns/cryptographic-weakness`.
- A proof that is correctly rejected but causes some other side effect (e.g. resource exhaustion
  from processing a malformed proof) → that's a different class; this card is specifically about a
  forged proof being wrongly ACCEPTED.

## Do not overclaim
- Reading that a comparison "looks like" containment without confirming the exact function/semantics
  used is `needs_review`, never `confirmed` — string/byte comparison functions have subtle exact
  behavior that must be read precisely, not assumed from a name.
- Citing Dragonberry or the fake-subtree issue as precedent for severity reasoning is legitimate;
  presenting either as if it were a currently-exploitable bug in the pinned, released version in
  scope (rather than a patched historical bug or an unconfirmed theoretical pattern) is overclaiming
  and must not appear in any report without a fresh, independently-reproduced finding backing it.
