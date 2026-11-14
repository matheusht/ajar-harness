# Optional owned application reset contract

Implementation contract approved by the coordinating agent on 14 November 2026.
Implemented in the candidate branch with local signed-workflow and actual HTTP/
stdio evidence; integrated acceptance and actual Docker qualification are separate.
This adds no authority to an existing signature.
The [failure-first scenarios](../../evals/native-qualification/APPLICATION-RESET-SCENARIOS.md)
are written before production code.

## Caller and authority

Keep the existing `engagement_capture` operation. Its optional `starting_state`
maps selected application access IDs to a signed baseline ID. Omission preserves
current behavior; a requested reset that fails never becomes a limited capture
silently. There is no separate agent-facing reset tool.
`engagement_status.application_baselines` exposes the signed access-to-baseline
map so a worker can select the permitted value without host configuration access.

An optional signed application-state reference binds `access_id`, owner profile
digest, target environment ID and explicit reset effect ID. Initial inputs bind
that profile's exact bytes. Existing scopes without the reference remain reset
unavailable even if they contain the older unused `reset` permission.

The scope field is `application_states`, a list of exactly
`{access_id, profile_sha256, environment_id, reset_effect_id}`. The optional input
field `application_profiles` maps those exact access IDs to private profile files.
Each profile is canonical JSON, frozen under `contract/applications/<access>.json`.
Its exact keys are `{kind, method, baseline_id, command, service_port}`; kind is
`owned-application-state-v1` and method is `owned-container-recreate-v1`.

The concrete versioned owner profile contains one baseline ID, signed application
command and service port. Its target environment supplies the pinned image,
Docker/SSH owner, bounded resources and cleanup authority. The access origin must
be HTTP in the reserved `.invalid` namespace and match the profile's port; it
cannot name an arbitrary remote deployment. A clone is a separately signed access.
No second application access may alias that origin. The signed route must admit
target-container loopback, and a managed origin has no DNS fallback without its
owner connector.
The initial owner method is `owned-container-recreate-v1` only.

## Ownership and minimal interface

`ApplicationOwner` composes the existing `Environment`. It controls a distinct
target container with the existing unprivileged/no-network/no-mount policy and
short renewable lease. The application command is signed startup code; its stdout
is never reset authority. The target's entire writable state is disposable.
Declared volumes, external databases or unowned writers are unsupported.

```text
ApplicationOwner(profile, access, environment_profile, limits,
                 authorize, observe, grant, dispatch_guard, bootstrap)
  reset(baseline_id) -> protected starting-state observation
  connect(exact_origin) -> socket through the exact owned container
  renew(seconds) -> existing environment renewal
  cleanup() -> exact target absence/readback
```

The existing `recover_boundary` reconstructs `Environment` from its recorded
identity and performs exact cleanup/readback; it never revives the target or probe.

The private connector reuses the existing bounded stdio byte protocol. Its remote
opener is fixed to the signed service port on target-container loopback. The host
returns a socket to the existing `NetworkGate`; request parsing, effect/account
binding, response redaction and request receipts stay with their existing owners.
No published container port or generic forwarding service is needed. The target
connector cannot choose a destination from a worker frame.

The controller keeps resource exclusivity and the only journal. Owner observations
bind scope/grant/dispatch, access, baseline/profile, exact container identity and
target generation. The executor owns those observations. A worker may request a
baseline but cannot submit a clean-start flag, owner receipt or host command.

## Evidence integration

The host completes the reset before the frozen probe begins and excludes parent
or competing target traffic throughout capture. Target request receipts bind the
access/account/effect and actual owner generation. A protected start receipt is
valid for one capture, not a reusable assertion that an application is always clean.

Experiment validation derives `clean_start` from a verified client lab plus one
protected start receipt per application. An independent replay requires a distinct
reviewer session, client lab and target generation with the same stable baseline,
scope/account and configuration. Differing physical generation IDs are not included
in stable-comparability equality. Review still assesses whether the baseline and
measurement support the claimed behavior.

The journal owns `application_starts`, keyed by the observed target nonce. The
frozen probe's execution intent consumes its starts once; later start receipts
cannot change that execution. Protected target HTTP observations carry the target
nonce separately from worker-selected account/effect headers. Experiment records
derive stable `application_state` and physical `application_generations` from
these observations. A signed profile, stdout marker or recreated client alone
does not supply either receipt.

Ordinary target HTTP completion or removal of only a client lab cannot reconcile
application state. Recovery/cleanup must use actual owner readback for the exact
recorded target. An uncertain operation stays held until that evidence arrives;
it is never retried blindly. Cleanup includes every owned target container and
staging image, preserves unrelated resources, and keeps old observations immutable.

## Evidence and limits

The [failure-first scenarios](../../evals/native-qualification/APPLICATION-RESET-SCENARIOS.md)
name the runnable checks and proof tiers. Local composition exercises signed
inputs, the production capture/controller flow, actual counter requests over
private stdio, clean independent replay eligibility, combined source/two-app
capture, unavailable authority and cleanup recovery. Native model and container
owners are explicit simulations in that fixture.

An opt-in Docker fixture exercises the production application/environment owner
against an explicitly selected daemon and already installed Python image. It
performs no pull or provider call. Actual Docker results and any joined native
workflow must be retained separately before claiming that qualification. Neither
fixture is the operator-owned fresh-target research acceptance. No impact-artifact
or escalation-policy activation is part of this unit.
