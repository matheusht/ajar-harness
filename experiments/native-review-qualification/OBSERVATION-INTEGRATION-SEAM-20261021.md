# Original-observation to fresh-review integration seam

21 October 2026. This is a source-level preparation boundary only. It does not
edit or call the shared managed launcher, dispatch inference, select a new handoff
manifest, access an engagement, or claim a fresh review.

## Producer contract

The launcher-owning lane can integrate
`experiments/native-observation-qualification/native_observation.py` around
arbitrary sanitized application-capture packets. A packet can preserve multiple
current or historical cases and chain transitions; each dispatched case binds
one exact native dispatch. Before each dispatch the caller freezes:

- current source/config/condition hashes and exact producer identity;
- the existing run/session identity, tool-call identity, and normalized intended
  application request digest;
- a host-owned application receiver/effect store that the producer cannot mount
  or write;
- the complete allowed application-route inventory and host-client activity
  ledger for the bounded window.

It then traces the exact native process subtree for network connection metadata
only, opens the dispatch window, consumes the native event containing session and
tool identity, observes the real application request/result/effect independently,
and closes the window. It supplies only the sanitized projection accepted by
`evaluate_observation_run`; raw tool arguments, commands, prompts, bodies,
responses, environment, authorization, cookies, capabilities, and signed URLs
never cross the seam.

The caller must return `process_attribution: unavailable` unless the native
request process is demonstrably inside that exact traced subtree. Container ID,
source IP, a producer-writable plugin record, a PHP access line, or a host replay
does not satisfy this; only that proof is normalized as
`process_binding: exact_spawned_subtree`. An unmatched effect, missing receipt, extra connect,
concurrent host request, writable observer, or unknown route fails closed. A
direct bypass remains `capture_claim_refused`; it is not converted into a captured
request.

The shared launcher retains ownership of mounts, containers, NativeRun, CONNECT,
CA/proxy configuration, allowance, final-send authority, stop, and cleanup. This
module returns evidence and required mount/process projections only; it does not
create a second pool, allowance, producer, or generic telemetry service.

The narrow interface is:

```sh
python3 experiments/native-observation-qualification/native_observation.py \
  --input /private/sanitized-app-capture-packet.json \
  --output /private/absent-observation-bundle
```

The caller, not this evaluator, verifies actual source bytes and protected
capture inputs before freezing the packet's self-digested manifest. The core
does not know or require the owned E2E's fixture IDs. Every chain-state case
reference must be accompanied by its sealed case evidence in the same packet.
It also requires the six portable cleanup categories, refuses route completeness,
and rejects discovery credit because this schema has no independently protected
discovery-origin event.

## Portable files and review selection

A passing native caller publishes the exact four-file observation bundle:

| File | Review-relevant meaning |
| --- | --- |
| `hypothesis.json` | Portable statement, source conditions, origin/help, status, and explicit discovery credit. Runtime IDs are excluded from core hypothesis state. |
| `observation.json` | Actual request/result/effect, host-replay distinction, session/tool/process evidence bindings, produced and consumed state, contrary results, missing transitions, and unfinished conditions. |
| `evidence.json` | Attribution method and coverage, observer protection, route limitations, redaction, stop, repeatability, and cleanup. |
| `result.json` | Exact hashes, case statuses, failure predicates, and nonclaims. |

These bytes are candidate inputs for a future independently frozen manifest. Do
not pass them through the historical T03 manifest, whose digest remains
`26056e8abd33e6b55cfac99929e611b7f8bc8b9193bf914c589c4592c15f7f74`
and whose accepted actual-predecessor set is empty. The coordinator must select a
new exact manifest/digest and keep the packet observer-owned and reviewer read-only
before a fresh reviewer can run. Prepared inputs remain `review_status: not_run`.

## Future caller order for fresh review

The existing managed launcher is not this caller. At the pinned source it tells
the researcher the exact before-to-after edit in
`opencode_v2_managed_owned.py:1333-1339`, then asks the reviewer for a one-sentence
answer with no tools at `:1394-1395`. That can qualify neither original
hypothesis discovery nor inspection of an observation packet, and its sentence
must not be accepted as a review-bound conclusion.

A later launcher integration must enforce this order:

1. Before producer results are revealed, preseal a fresh reviewer identity,
   isolated workspace/runtime, bounded authority, and non-leading review task.
   The task may describe acceptance criteria, but must not state the expected
   edit or conclusion.
2. Observe the arbitrary producer dispatch through the protected seam and keep
   host-authored replay explicitly separate.
3. Atomically seal the exact observation bundle, current source manifest, and a
   newly selected review-input manifest. Record their hashes; do not reuse the
   historical T03 manifest.
4. Give the presealed reviewer read-only access to exactly that packet and
   current source. Capture the reviewer-selected inspection/tool evidence and
   actual result without allowing the producer to write either store.
5. Seal a review conclusion that binds the reviewer identity/session/tool
   evidence, packet digest, source/version digest, selected inspection result,
   and conclusion digest. A changed source, packet, reviewer task, result, or
   conclusion invalidates the binding.
6. Only after independent acceptance, expose the accepted and contrary portable
   state to a separate unhinted adaptive run. That run must demonstrate the
   evidence changing its actual next investigation action and must preserve
   missing/unfinished transitions; a reconstructed success story does not pass.

This lane implements only the packet evaluator and this caller seam. Reviewer
presealing, native review execution, conclusion binding, and the later unhinted
adaptive run remain `not_run`.

## Resume and changed-state requirement

For a later authorized resumed engagement, the selected packet must carry the
actual workspace state rather than reconstructing a clean success narrative:

- every produced state and the observation that produced it;
- every consumed state and the check/action that actually consumed it;
- contrary and denied outcomes, including valid partial support;
- missing transitions, uncertain effects, and unfinished conditions;
- exact current source and conditions, remaining shared allowance, and cleanup
  state;
- any previous review only when its exact request/result pair was independently
  accepted for this successor.

Changed source, conditions, claim, or evidence invalidates affected review and
dependent conclusions. A fresh context may reconstruct portable state from these
files, but runtime-history restoration is a separate claim. Evidence-driven
revision and real chain-state transfer remain `not_run` until an authorized native
scenario shows an observation changing the actual next investigation action.

The owned local receipt in this implementation lane is intentionally
`agent_discovery_credited: false`, `managed_native: unavailable`, and
`fresh_independent_review: not_run`.
