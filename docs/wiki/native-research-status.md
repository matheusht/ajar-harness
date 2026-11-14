# Native research: implementation and evidence status

For the newer candidate Codex/OMP team route, read the
[14 November v2 delivery state](oslit-v2-delivery-2026-11-14.md) and
[operator guide](../agents/engagement.md). The October assessment below describes
its original route and revision; its fixed provider and 24-hour limits do not
describe v2. Neither route is adopted by this pointer.

Observed 23 October 2026 at source baseline
`cf8b213aa9979297def3b71f8f63a05dcc7945d6`. This page is a dated source/evidence
assessment, not a live tracker or a grant to run a target. At the readback,
[PR #191](https://github.com/matheusht/redteam-harness/pull/191) was draft/open at
that head and [#165](https://github.com/matheusht/redteam-harness/issues/165) was
open. Recheck actual source and tracker state before acting.

For durable product choices read [product and engineering direction](product-and-engineering-direction.md).
For task procedure use [native local research](../agents/native-local-research.md)
or the explicit [legacy entry](../agents/legacy-local-research.md).

## Reading the status

**Chosen direction** records an operator's product choice. **Implemented** means
the source contains the mechanism. **Local checks** establish only their stated
contract and inputs. **Qualified** requires actual workflow evidence for a defined
class. **Adopted scope** requires the corresponding operator decision. None of
these states follows automatically from the preceding one.

## Capability map

| Capability | Source and evidence | What is established and what is missing |
| --- | --- | --- |
| Native default routing | [Cutover contract](../agents/native-cutover-contract.md), root entrypoints and bootstrap skill | Candidate source routing is implemented for new local source work. Final workflow qualification and a scoped #165 outcome remain separate. |
| Persistent native workspace | [Native guide](../agents/native-local-research.md), [runner source](../../tools/native_research.py) | Native research, exact-session resume, and workspace reconstruction are exposed. A fresh context alone does not prove that material state was recovered. |
| Generic source execution | [Source guide](../agents/native-source-sdk.md), [source checks](../../evals/native-qualification/SOURCE-SDK-CHECKS.md) | Source-only execution accepts runtime/dependency probes and prepared commands; Go is an optional preset. Generic target runtimes do not imply generic agent engines or providers. |
| Source execution and review | [Source guide](../agents/native-source-sdk.md#research-capture-and-review) and [saved local receipt](../../evals/native-qualification/SOURCE-MODE-LOCAL-CHECKS.json) | Host capture, repeated clean copies, compact reviewer evidence, and full hashed manifests are implemented. The saved synthetic scenario substitutes test authority. Actual native source review and real-target behavior remain unqualified. |
| Continuation | [Controller source](../../tools/native_continuation.py), [check inventory](../../evals/native-qualification/CONTINUATION-CHECKS.md) | An implemented controller continues bounded turns over one active run using researcher-supplied checkpoints. It retains lease, stop, pending-dispatch, and journal state. Useful research progress is not established by that mechanism alone. |
| Continuation checks | [Offline test source](../../tools/test_native_continuation.py), [smoke source](../../evals/native-qualification/smoke/check_native_continuation.py) | Offline checks exist. The smoke calls the controller function with a synthetic child-runner CLI; it does not exercise the public `native_research.py continue` entrypoint. Native, provider, target, comparative, and multi-day outcomes remain unqualified. |
| Stopping review | [Continuation checks](../../evals/native-qualification/CONTINUATION-CHECKS.md) | Explicit checkpoint stop proposals and a strong-lead true-to-false change trigger a review request. The controller does not infer every negative conclusion from prose. File validation binds fields to a request; the operator must establish fresh independent review. |
| Shared allowance | [Runner source](../../tools/native_research.py), [controller source](../../tools/native_continuation.py) | Connection, byte, and elapsed-time limits exist. Continuation checks decreasing connection/byte counters. These are not a monetary cap, a complete provider-request count, or reconciled billing. |
| Current provider support | [Runner source](../../tools/native_research.py), [provider boundary](../agents/native-source-sdk.md#paid-provider-boundary) | The integration allows exact OpenCode free and OpenCode Go paid DeepSeek tuples through the configured authority. Broader model/provider independence is a product requirement. Paid transport and credential containment remain live-qualification gaps. |
| Service acceptance | [Acceptance inventory](../../evals/native-qualification/NATIVE-ACCEPTANCE-INVENTORY-CHECKS.md) | Available receipts can establish bounded transport/effect facts and at most a partial operator-review candidate. Inventory completeness or stopped status does not establish clean replay, a fixed control, or adoption. |
| Historical records | [Legacy entry](../agents/legacy-local-research.md), [cutover caller inventory](../agents/native-cutover-contract.md#caller-and-control-inventory) | Supported legacy readers and writers retain their own semantics. Native internal output is not a canonical confirmed filing. Retention is not evidence that every historical claim is valid. |

## Important limits

- The run and approval validators retain the 24-hour ceiling. Current continuation
  is not a demonstrated multi-day run. Changing a timeout would not establish
  multi-day operational reliability or extend authority.
- Repeated identical checkpoints/no-progress detection is not implemented in the
  current controller. Neither the journal nor a changed checkpoint proves a
  revised causal explanation or a useful next experiment.
- Source review checks original bytes before and after a command. It does not
  exclude temporary source changes. Scripts and causal controls still need review.
- An already-dispatched action may settle after stop or expiry. New-dispatch
  rejection, uncertain-effect reconciliation, and verified cleanup are different
  properties.
- Completing qualification checks never grants target permission. Scope, allowed
  effects, dependencies, provider access, and approval remain target-local inputs.

The [long-horizon comparison plan](../../evals/native-qualification/LONG-HORIZON-PREREGISTRATION.md)
is a hypothesis and acceptance specification. It contains no comparative result.
Its cost-normalized outcome is unavailable without complete charged-cost evidence.

## Evidence chronology

The 22 October #166 to #170 cutover pass was source/caller inspection with testing
deferred. Later source-mode and continuation work added local checks. Those later
checks do not retroactively qualify the cutover or earlier source revisions.

The [source-mode receipt](../../evals/native-qualification/SOURCE-MODE-LOCAL-CHECKS.json)
and [initial source receipt](../../evals/native-qualification/SOURCE-SDK-LOCAL-CHECKS.json)
record the exact hashes they checked. Some runner/check-script hashes differ from
this page's baseline. Preserve their bytes and use their recorded revision scope;
do not describe them as a fresh pass of the current tree.

The continuation check inventory was added after candidate implementation. It is
offline contract coverage, not failure-first provenance or native acceptance. The
documentation review that produced this page ran no controller, provider, or target.

## What would support stronger claims

Use the existing [adoption contract](https://github.com/matheusht/redteam-harness/issues/165)
and qualification documents for their exact criteria. The missing evidence includes
actual native research and interruption/recovery, independently observed effects
and controls, fresh claim/lead review, containment and uncertain-effect behavior,
historical readback/rollback, and the final integrated workflow. A historical hidden
case does not establish novel discovery or a general success rate.

A comparison is optional for a supported-class adoption decision. It is necessary
when asserting comparative benefit. A genuine wall-clock multi-day run is needed
for a multi-day reliability claim. Target readiness and execution decisions belong
in the target's own records; this portable status page does not replicate them.
