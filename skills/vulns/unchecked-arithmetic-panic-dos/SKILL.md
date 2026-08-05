---
id: cosmos.unchecked-arithmetic-panic-dos
name: Unchecked Arithmetic Causing Chain-Halting Panic
description: >
  Prove that untrusted, network-reachable input (a transaction, a message, a governance/group
  proposal) drives an arithmetic operation (decimal division/exponent handling, integer
  multiplication, or a type-boundary conversion between arbitrary-precision types) into an
  unrecovered panic during state-machine execution, and that the panic is not caught/handled in a
  way that keeps the chain live — i.e. it is a genuine availability/consensus-safety issue, not
  merely a returned error. A theoretical overflow with no reproduced panic is coverage, not a
  finding.
type: vuln
owasp: "CWE-190 (Integer Overflow), CWE-1284 (Improper Validation of Specified Quantity in Input), CWE-755 (Improper Handling of Exceptional Conditions — a checked, correctly-returned error treated as fatal further up a consensus-critical call chain) — not an OWASP Top 10 category, this is a blockchain state-machine class"
atlas: "—"
patterns: []

activation:
  strong:
    - "a decimal/arbitrary-precision arithmetic call (.Quo, .Add, .Mul on a Dec/apd-context type) on a value influenced by untrusted or attacker-controllable input (group member weight, proposal parameter, deposit amount) is followed by narrow-cased error handling — e.g. only a divide-by-zero/IsZero() guard — rather than a blanket check of every possible error the call can return"
    - "a helper/library function DOES correctly check and return every error it can produce, but the CALLER, one or more layers up, treats ANY error returned from that helper as fatal (panics, or lets a returned error propagate uncaught) inside a consensus-critical path (BeginBlock, EndBlock, or any code that runs unconditionally during block processing) instead of gracefully rejecting the specific input that caused it — this is the pattern behind the flagship disclosed anchor for this card and is easy to miss if you only look at the arithmetic call site itself rather than tracing the error one or more layers up the call stack"
    - "monetary/reward/stake accounting arithmetic (ratio computation, multiplication) on a user- or validator-supplied amount lacks an explicit overflow-safe bound or sanity ceiling before use"
    - "a value is converted or compared across two arbitrary-precision types with different maximum bit-lengths (e.g. a Dec-typed value coerced into or compared against an Int-typed bound) without re-validating against the narrower type's limit"
  weak:
    - "arithmetic on user input exists but the specific error-return paths of the library function used have not been enumerated (does .Quo/.Add actually have an unhandled-error path, or does it always return a caught error?) — needs library-source confirmation before treating as strong"
  negative:
    - "every documented error return of the arithmetic call is checked before use, including non-obvious ones (exponent-out-of-range, not just divide-by-zero) — AND every layer above that checks the error handles it gracefully (rejects the specific bad input) rather than treating it as fatal in a consensus-critical path → likely held"
    - "the operation is wrapped in a recovered panic handler at a layer where recovery keeps consensus live and deterministic across all validating nodes (not just avoids a crash on one node) → likely held, but confirm the recovery is itself deterministic"

safe_signal:
  proxy: >
    a local, single-node (or small local-cluster) test chain, built from the actual pinned
    release/module code (never a hand-rolled emulator of the arithmetic), that observably panics or
    halts when fed a locally-crafted transaction/message carrying the triggering value — reproduced
    via a real Go/Rust test exercising the real keeper/module code, per this program's own PoC
    requirement (mock-only or database-only calls are insufficient). The benign marker is the
    observed panic/halt itself on your own disposable node, not any live network effect.
  never: >
    never submit the triggering transaction/message against any live public mainnet or testnet;
    never attempt this against infrastructure or validators you do not operate; the local test chain
    must use only locally-generated test keys and locally-minted test-denomination tokens with no
    real value.

impact_escalation:
  enabled_by: scope.md#impact_demo_authorized
  requires: >
    benign/non-destructive local reproduction proceeds without a per-artifact pause under this
    engagement's standing Zone-2 authorization (see scope.md); a fresh human confirmation is still
    required only if the candidate PoC would require anything beyond a local, disposable,
    single-operator-controlled environment
  containment: "local disposable test chain only; locally-minted test tokens only; logged in engagement cleanup.md"

oracle: [whitebox-analysis, regrade-oracle, pocinator-oracle]
severity_rubric: { unauthenticated_chain_halt_reproduced: critical, authenticated_or_privileged_precondition_chain_halt: high, panic_recovered_no_consensus_impact: low }

procedure:
  - "IDENTIFY THE SINK: find an arithmetic call (decimal/Dec, sdk.Int, apd context, or a raw Go/Rust numeric type) that consumes a value reachable from an unauthenticated or low-privileged transaction/message field."
  - "READ THE LIBRARY'S ACTUAL ERROR CONTRACT: don't assume — read the exact source of the arithmetic function being called (e.g. cockroachdb/apd's Quo, cosmossdk.io/math's Int/Dec) and enumerate every error/panic path it can produce, not just the obvious divide-by-zero case."
  - "TRACE THE CALLER'S ERROR HANDLING, ONE LAYER AT A TIME: confirm whether the immediate caller checks only a subset of the library's error paths (the common miss: guarding IsZero() but not an exponent-overflow or bit-length error) — AND, separately, whether a fully-checked, correctly-returned error from that immediate caller is then treated as fatal by something ONE OR MORE LAYERS FURTHER UP the call stack (e.g. an EndBlocker that panics on any returned error instead of rejecting just the offending input). The real, disclosed flagship anchor for this card is the second pattern, not the first — read the full call chain, not just the arithmetic call site."
  - "CONFIRM THE RELEASED-VERSION PRECONDITION: check whether this exact code path, at the exact pinned/released commit in scope, still has the gap — a fix landed >90 days ago and already released takes this out of scope per program policy; a very recently landed fix is worth flagging but check the release-family timing."
  - "BUILD A REAL LOCAL REPRODUCTION: stand up a local single-node (or minimal multi-node if the bug needs cross-validator interaction) test chain running the real, unmodified module code, and submit a locally-crafted transaction/message carrying the triggering value."
  - "OBSERVE THE ACTUAL PANIC/HALT: confirm via node logs/process state that the node panicked or the chain halted, not merely that a test assertion 'looks like' it should have — this is the harness-fidelity check per engine/whitebox-analysis.md §4."
  - "NEGATIVE CONTROL: confirm a well-formed, in-bounds value of the same field does NOT trigger the panic, isolating that the specific out-of-bounds/adversarial value (not the code path in general) causes it."
  - "CLASSIFY RECOVERABILITY: determine whether any panic-recovery layer exists above the sink, and if so, whether recovery is deterministic across all nodes (a non-deterministic recovery is itself a distinct, serious finding, not a mitigation) — see cosmos.ibc-nondeterministic-execution for that adjacent class."

emits: [attempt, finding]
---

## What "confirmed" looks like here
An untrusted-input-reachable arithmetic call is shown, via a real local test-chain reproduction
using the actual module code, to trigger an unrecovered panic that halts the chain (or produces
non-deterministic recovery across nodes) — with a negative control showing an in-bounds value does
not trigger it, and the exact triggering condition named precisely (which field, which value range,
which function's specific error path was missed).

## Real disclosed anchors for this class (verified against primary sources and actual pre-fix
commits, not just advisory summaries — treat as taxonomy templates for finding structurally similar
regressions/variants elsewhere in scope, not as currently-exploitable bugs in patched, released
versions)
- x/group `PercentageDecisionPolicy.Allow`: `yesCount.Quo(totalPowerDec)`'s error IS correctly
  checked and returned inside `Allow()` itself — the arithmetic call site is not the bug. The actual
  gap is one layer up, in `doTallyAndUpdate`: any error returned by `Allow()` (of whatever kind) was
  fatally propagated through the EndBlocker, which panics on any returned error, instead of being
  caught and turned into a graceful proposal rejection. This is CWE-755 (Improper Handling of
  Exceptional Conditions), not a raw unchecked-arithmetic bug — the arithmetic itself was fine; the
  failure to gracefully handle a legitimate error in a consensus-critical path is the actual class.
  GHSA-47ww-ff84-4jrg / ISA-2025-002, HackerOne report #3018307 (High severity; bounty figure not
  independently confirmed, treat any specific dollar amount cited elsewhere as unverified until
  checked against the live report). **Scope note**: x/group is one of the modules this program has
  explicitly excluded as unmaintained (per program-policy.md) — this anchor is a taxonomy template
  only, not itself a reportable target.
- x/distribution `DepositValidatorRewardsPool`: reward-ratio computation overflows on a crafted
  deposit amount. GHSA-p22h-3m2v-cmgh / ISA-2025-005, CWE-190, CVSS v4 **7.7** High (not 8.7 — that
  figure belongs to the next anchor; verify the exact score from the live advisory before citing it
  in any report, don't copy from memory across anchors).
- `cosmossdk.io/math` Int/Dec bit-length misalignment: a value valid as `Dec` can overflow when
  coerced into an `Int`-context operation. ASA-2024-010 / GHSA-7225-m954-23v7, CVSS v4 8.7 High.

## Not this card
- An arithmetic bug that produces a wrong-but-non-panicking result (silent accounting drift, no
  crash) → no dedicated card exists for this yet in this engagement; note it separately in
  recon-signals.md as a distinct class rather than force-fitting it here — the mechanism and impact
  differ even though the root cause (unchecked arithmetic) rhymes.
- A panic in a purely local/offline tool (CLI, viewer) not reachable from consensus-relevant
  transaction processing → out of this program's scope by its own release/deployment-environment
  requirement.
- DoS that is already mitigated by existing gas/fee/operational controls per program policy — this
  card is specifically about panics that escape those controls (occur before or outside normal gas
  accounting), not generic expensive-computation griefing.

## Do not overclaim
- "This function could theoretically overflow" without reading the library's actual error contract
  and reproducing a real panic is `needs_review`, never `confirmed`.
- A panic reproduced only in a hand-built harness that doesn't exercise the real module/keeper code
  does not satisfy this program's explicit PoC requirement — rebuild against the real code before
  claiming confirmation.
- "This is unmaintained code" (x/group, x/circuit, x/crisis, x/nft) is out of scope regardless of a
  real bug being present — check module scope before investing further.
