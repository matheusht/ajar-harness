# Native original-application observation qualification

This directory implements one narrow, provider-free observation seam. Its core
accepts a sanitized application-capture packet with arbitrary case IDs, source
versions, request/path/result classifications, binary changed/unchanged effects,
hypotheses, contrary results, missing or unfinished transitions, and
produced/consumed state. For
each dispatched case, it joins an exact process subtree's `connect` projection
with an independently owned application request/result/effect receipt. The
retained projection is portable across models, providers, and agent runtimes;
the owned fixture names below are not part of the core contract.

Dispatched packets use the closed portable process proof class
`exact_spawned_subtree`. Container identity, source IP, or an unavailable
attribution label cannot be promoted to that class.

The owned E2E deliberately distinguishes a host replay, authorized read, denied
change, allowed effect, consumption of that produced state, and a direct bypass.
The bypass is evidence that this observer is not route enforcement: it returns
`capture_claim_refused` and preserves the missing observer transition.

## Run

Requirements are Python 3, Linux `strace`, and bubblewrap with unprivileged user
namespaces. The command uses only host loopback. It empties inherited proxy
variables in each producer, makes no provider/model/target/CI call, and writes a
fresh mode-0700 output with mode-0600 files.

```sh
PYTHONDONTWRITEBYTECODE=1 python3 \
  experiments/native-observation-qualification/check_owned_e2e.py \
  --output /absolute/absent/private-output
```

Expected status:

```text
owned_e2e_pass_not_managed_native_qualified
```

The command runs the scenario twice, compares normalized bundles, exercises all
frozen failure predicates with offline mutations, stops both exact listeners,
rebinds their ports, reaps owned bubblewrap descendants through a Linux child
subreaper, removes raw traces/private scratch, and retains only:

- `hypothesis.json`: portable statement, origin, conditions, and non-credit for
  agent discovery;
- `observation.json`: bounded requests/results/effects, process/session/tool
  bindings, produced/consumed state, contrary results, missing transitions, and
  unfinished conditions;
- `evidence.json`: observation boundary, attribution scope, sanitization,
  negative fixtures, repeatability, and exact cleanup booleans;
- `result.json`: artifact hashes, case outcomes, failure checks, and nonclaims.

`native_observation.py` also exposes a narrow caller API:

```python
bundle = evaluate_observation_run(sanitized_run_projection)
write_bundle(bundle, fresh_private_output)
```

That API remains the terminal path. It returns `observation_packet_valid` only
after all six cleanup checks pass and stop is verified. A caller that must keep
one shared runtime active for review uses the separate capture path:

```python
capture = evaluate_capture_run(sanitized_capture_projection_without_cleanup)
write_bundle(capture, fresh_capture_output)
sealed_digest = capture_manifest_sha256(fresh_capture_output)

final_receipt = finalize_observation_capture(
    fresh_capture_output,
    sealed_digest,
    final_cleanup_projection,
)
write_finalization_receipt(final_receipt, fresh_receipt_output)
```

The capture status is `observation_capture_ready_not_finalized`. Its evidence
records stop and cleanup as `not_run`, and its result contains only capture
checks. It is not an `observation_packet_valid` result. The digest covers a
manifest of the exact bytes of all four capture files, including `result.json`.
The finalizer rereads those files after stop, rejects changed or noncanonical
bytes, symlinks, or a changed inventory, and emits a separate receipt linked to
that digest. It never rewrites the reviewed capture.

The terminal path also has an equivalent public command:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 \
  experiments/native-observation-qualification/native_observation.py \
  --input /private/sanitized-app-capture-packet.json \
  --output /private/absent-bundle
```

The corresponding pre-review command takes the same projection without the
top-level `cleanup` field:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 \
  experiments/native-observation-qualification/native_observation.py \
  --pre-review \
  --input /private/sanitized-capture-projection.json \
  --output /private/absent-capture-bundle
```

On success, the command prints the capture-manifest digest that the caller must
seal before reviewer access. Finalization is a Python caller operation because
the launcher already owns the final cleanup projection and lifecycle order.

Output must be an absolute, lexically absent, non-symlink path beneath an
existing directory. Relative paths and dangling symlinks fail before any bundle
write.

The input is already-sanitized observer evidence. It must not contain prompts,
raw request/response bodies, tool commands, environment, auth, cookies, tokens,
or signed URLs. The evaluator's sensitive-pattern scan is defense in depth; it
does not prove that arbitrary input is secret-free, so sanitization remains the
caller's responsibility. The caller must verify actual source bytes before
freezing the self-digested source manifest; the evaluator checks that the
manifest has not changed afterward. Unknown, duplicate, ambiguous, or
unexplained route evidence fails closed. A valid observed bypass remains explicit as
`capture_claim_refused`: it refuses a completeness claim rather than erasing the
packet's other bounded observations.

The Python API accepts only strict portable JSON shapes: string-key objects,
arrays, and finite JSON scalar values. Duplicate CLI object keys, tuples,
non-string mapping keys, and non-finite numbers are rejected rather than coerced.

This schema has no independently protected discovery-origin event, so the core
rejects `agent_discovery_credited: true`; a later caller must extend and qualify
that evidence before discovery can be credited. It likewise never accepts a
route-completeness claim. Every `capture_claim_refused` case must retain its
`application-observer-receipt` missing transition.

A packet may contain one or many current or historical cases. Every produced,
consumed, contrary, or missing-transition case referenced by its chain state
must be included, so the evaluator can bind state digests and causal order to
actual receipts. Every changed receipt must also have exactly one matching
produced-state entry; it cannot be omitted from the portable chain. Each
dispatched case binds exactly one dispatch, receipt,
response, process subtree, session, and tool identity. One-run packets use
`runs: 1` with `normalized_match: null`; the owned qualification above requires
two exact normalized runs. Every traced `connect` syscall is represented. The
fixture classifies known failed local name-service probes separately and rejects
every unsupported or unexplained family.

Final cleanup is a closed portable projection with exactly six required
categories: producer and observer processes stopped, observer endpoints
released, private scratch and raw capture removed, and owned resources only.
Runtime adapters may retain more detailed receipts outside this seam, but cannot
omit these categories. A pre-review capture makes no cleanup claim. The separate
final receipt succeeds only when the same six fields are true, cleanup status is
`complete`, and `stop_verified` is true. An ordinary `incomplete` projection
remains invalid.

Any receipt classified as a changed effect must name an outcome expressly
allowed by that packet's hypothesis. The generic evaluator records provider and
target accounting as `not_observed`; only the fixed owned checker replaces those
fields with independently bounded zero-call evidence. Generic network scope is
caller-declared and not independently verified; the owned checker narrows its
receipt to host loopback only. The generic evaluator likewise records body
retention as not observed and requires caller sanitization; the owned checker
can establish that no application bodies were retained. Its source manifest names
the actual implementation commit and retains handoff commit `ac6348b` as the
predecessor dependency.

## Qualification boundary

This proves process attribution only for the exact owned subprocess tree started
by the check. It does not prove attribution for the managed OpenCode researcher,
autonomous hypothesis selection, adaptive investigation, provider/model behavior,
fresh independent review, route enforcement, or a live target. OpenCode remains
an adapter, not the research-state format.

The shared managed-launcher owner must supply a reviewed exact-process boundary
and independently verified source manifest before using this seam for native
evidence. No launcher, transport, CA, allowance, provider, handoff manifest,
engagement, default, or retirement file is modified here. See
[the source-level integration seam](../native-review-qualification/OBSERVATION-INTEGRATION-SEAM-20261021.md).

The frozen predicates and E2E order are in [FAILURE-CHECKS.md](FAILURE-CHECKS.md).
The checked-in result is a sanitized owned-fixture receipt, not managed or
provider proof.

On a late owned-check failure, the checker preserves the deterministic failed
predicate list, resolved source pins when available, owned zero-call accounting,
and accumulated cleanup projection. Failure-receipt publication is best-effort
and cannot replace the original failure code.
