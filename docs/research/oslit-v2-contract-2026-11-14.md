# M0 v2 contract for implementation

Status: proposed implementation contract, 14 November 2026. Source inspected at
`89bcede2c1e62573767017251e8734f211fa3573` plus the approved planning edits. No code,
provider call, target run or new authority was created by this review. Parent owns
integration. The operator's fresh-target test remains separate.

## Decisions to carry into code

1. Keep `native_engagement.py` as the operator facade. Its existing v1 CLI and
   roots retain their reader and behavior. Select v2 from the immutable inputs
   kind once; never infer it from missing v1 files or silently switch a root.
2. Put v2 validation in `engagement_contract.py`, one journal/reducer/controller
   in `engagement_controller.py`. Runtime/environment adapters publish observations;
   they do not own assignments, usage totals, claim dispositions or ending state.
3. Use one immutable numbered event directory and a process lock. Reconstruct
   views from events. No second authoritative `state.json`, task queue or counter.
4. Bind worker requests to a host-owned endpoint private to an isolated worker.
   Worker JSON never chooses its identity, role or active generation. Separate
   runtime processes/containers are the default if native children cannot prove
   that boundary. Keep ordinary native tools within that worker's capability.
5. Reserve only enforceable hard quantities. Invocation count, maximum active
   workers and bounded worker execution seconds can be enforced by admission and
   owner leases. Strict provider request/token/money caps remain unsupported until
   their gateway/adapter can prove complete observation and pre-dispatch bounds.
6. Keep optional overall expiry distinct from renewable short execution leases.
   There is no fixed engagement age or v1 24-hour clamp in the v2 route.

## Signed input

The launcher input is configuration by reference, not authority:

```json
{
  "kind": "native-engagement-inputs-v2",
  "scope_file": "/private/operator/scope.md",
  "scope_signature": "/private/operator/scope.sig",
  "allowed_signers": "/private/operator/allowed_signers",
  "trusted_fingerprint": "sha256:<64 lower-case hex>",
  "goal_file": "/private/operator/goal.md",
  "access_files": {"source-main": "/private/input/source"},
  "runtime_profiles": {"codex-main": "/private/config/codex.json"},
  "environment_profiles": {"local-lab": "/private/config/docker.json"}
}
```

Paths are absolute, regular/private where applicable, no symlink or ancestor
symlink traversal, no overlap between worker inputs/workspaces and controller root.
Credentials are opaque host references in profiles, never copied into the journal,
workspace or export. No operator-provided recipe/catalog is mandatory.

The scope remains Markdown with exactly one `native-engagement-scope-v2` JSON
fence and one `Operator allowed signers SHA256` pin. Reject mixed versions,
duplicate JSON keys, non-finite numbers, unexpected keys and ambiguous identity.

| Signed field | Shape and enforcement |
| --- | --- |
| `kind`, `engagement_id`, `operator_id` | Exact kind and bounded stable identifiers. |
| `issued_at`, `expires_at` | UTC timestamp; expiry is null or strictly after issue. Issue must not be future. No 24-hour maximum. |
| `goal_sha256`, `goal_mode`, `patch_required` | Exact goal bytes; mode `bounded` or `broad`; patch required is Boolean. |
| `access` | Nonempty descriptors `{id, kind, identity, account_refs, permissions}`. Kind is `source`, `binary` or `application`; multiple kinds give combined access. Source/binary identity binds manifest/content digest and platform; application identity binds exact allowed endpoint and stated version/identity check. Unknown runtime facts remain explicit, never invented. |
| `environments` | Allowed `{id, kind, identity, capabilities, limits, cleanup}`. `docker` pins daemon/profile/image constraints; `ssh` pins host key, host identity and owned resource namespace. Capabilities enumerate privileged actions, resource classes and reset/readback support. Cleanup states permitted actions and owned path/resource boundaries. |
| `network` | Distinct `provider`, `acquisition`, `target` route lists. Each route gives protocol, destination/port and resolved-address policy. Redirects and direct sockets get the same enforcement. Empty list denies that class. |
| `effects` | Allowed internal effect classes with affected access/environment IDs, permitted account/role, escalation rung, artifact class and cleanup obligation. No free-form wildcard grant. |
| `application_states` (optional) | Exact references `{access_id, profile_sha256, environment_id, reset_effect_id}` for owned disposable application baselines. Each access has a unique logical HTTP `.invalid` origin and an explicit reset effect. |
| `escalation_ceiling`, `benign_objectives` | Explicit permitted rung and harmless expected signals. A signed rung still needs the prior effect and fresh review. |
| `runtime_assignments` | Allowed `{profile_id, profile_sha256, roles}` referencing the pinned profile below; roles lead/specialist/reviewer. Runtime credentials do not identify model or runtime by implication. |
| `limits` | Hard dimensions and positive ceilings, plus `max_workers` and `max_worker_lease_seconds`; optional informational budgets explicitly separate. Validate every hard dimension against installed adapter capabilities before run. No hidden duration limit. |
| `revocation` | Operator stop authority and renewable lease policy. Cleanup authority survives research expiry only for the defined owned-resource cleanup. |

Use `operator_signature.verify_operator_signature_bytes` unchanged, with a v2
namespace and canonical challenge:
`{kind: native-engagement-scope-challenge-v2, engagement_id, scope_sha256}`.
Compare the returned signer fingerprint with the independently supplied trusted
fingerprint. Freeze scope/goal/profile bytes and their digests before root creation.
Later dispatch rechecks pinned authority, revocation, optional expiry and remaining
reservations; a successful `inspect` does not authorize future effects.

### Exact parsing rules and profile binding

Use `sha256:` plus 64 lower-case hex for every new-contract digest; v1 retains its
existing bare-hex fields. A source identity is `{manifest_sha256}`. Its manifest
is a sorted mapping from safe relative path to `{sha256, mode, size}` (mode only
regular-file permission bits), serialized by the strict canonical serializer.
The manifest includes all supplied source files and rejects symlinks/special files;
an optional provenance note cannot change the identity. A binary identity is
`{sha256, platform}`. An application identity is `{base_url, version}` where version
may be null; null is explicitly unknown and the setup task must observe it. URL
userinfo, fragments and credential query parameters are rejected. No application
descriptor requires a fake source directory.

Each access descriptor has exactly `{id, kind, identity, account_refs, permissions}`.
`permissions` contains only `read`, `execute`, `write`, `reset`; effect admission
also requires the matching signed effect and environment, so `write` alone grants
no arbitrary target mutation. `access_files` must contain exactly the source/binary
IDs, mapped to the supplied directory/file. Application descriptors need no local
file. Inspect hashes local input bytes without contacting application endpoints.

An optional `application_profiles` input map must contain exactly the access IDs
in the signed `application_states` list. Each private profile is canonical JSON
with exactly `{kind, method, baseline_id, command, service_port}`. Kind is
`owned-application-state-v1`; method is `owned-container-recreate-v1`. The baseline
ID is a bounded identifier, `command` is a nonempty argument list starting with
an absolute executable, and the service port is 1–65535. Write these bytes with
`engagement_contract.canonical` before hashing and signing; initialization freezes
them as `applications/<access_id>.json`.

The referenced access must permit `reset` and use one unique HTTP origin under
`.invalid`, with no path except `/`. Its port must match the profile and its target
route must admit `127.0.0.1` through the protected connector. No other application
access can alias that origin. The reset effect must name exactly this access and
target environment, require cleanup and have empty account/artifact-class lists.
The signed environment supplies the immutable complete baseline image and bounded
disposable state. Only its exact instance can back that logical origin.

The existing `engagement_capture` optionally accepts `starting_state`, mapping
every selected application access to its baseline ID. Host start observations
precede the one frozen probe, bind its requests to exact target instances, and
are consumed once. Experiment records separate stable `application_state` from
physical `application_generations`; independent replay requires the same baseline
and different native session, client lab and target generation. Missing reset
capability preserves the ordinary application's explicit clean-start limitation.
An explicit but invalid reset request never silently falls back. Recovery cleans
recorded targets without repeating the probe. See the
[owner contract and failure cases](oslit-application-reset-contract-2026-11-14.md).

Each runtime profile requires:
`{kind, version, executable, protocol, config_file, config_sha256, provider, model,
credential_ref, required_capabilities, tool_bundle}`. Kind is `codex` or `omp`; executable is
`{path, sha256}`; protocol is `{mode, schema_file, schema_sha256}` with mode
`stdio-jsonrpc` or `stdio-jsonl`. Paths are local absolute regular files. The
credential reference is an opaque host lookup name or null, never a token or
secret-bearing file content. Required capability strings are `startup`,
`fresh_session`, `resume`, `steer`, `interrupt`, `usage_tokens`,
`usage_cost_estimate`, `native_tools`, `child_inventory`. Capabilities are required
observations, not a profile's self-attested proof; preflight compares installed
adapter reports. Active revocation/readback belongs to the environment owner and
cannot be supplied by the runtime's `interrupt` claim.

Two optional fields have strict schemas. `model_host` selects the implemented
local Linux container owner; omission retains the Darwin owner. It is exactly
`{kind, docker_binary, docker_endpoint, daemon_id, image_id, platform, uid, gid,
limits}`. Kind is `linux-docker-model-v1`; the Docker executable is an absolute
path, the endpoint is a local `unix:///` socket, the daemon identity is explicit,
and `image_id` is an inspected `sha256:` image ID. Platform is `linux/amd64` or
`linux/arm64`; UID/GID are positive nonroot integers. Limits are exactly
`{memory_bytes, cpu_count, pids, workspace_bytes}`, all positive, with integer
values except CPU count. The signed worker lease maximum bounds this separate
owner; it cannot extend authority. Host Linux, cgroup v2 and a non-rootless Docker
daemon are implementation prerequisites. The controller itself need not be root.
This model container is separate from the target/tool lab and has no target
inputs or direct network access. Its actual startup remains a qualification check.

OMP alone may also include `model_catalog: {path, sha256}` for its native
`models.yml`, separate from `config_file` settings. The catalog must contain no
credential values. Initialization freezes it as `runtimes/<id>.models.yml`, and
recovery uses those bytes. The model owner stages only configuration, this optional
catalog and public proxy trust. Credentials use the private host binding. Neither
optional field changes a previously signed profile or makes a preflight result
execution evidence.

The scope's `profile_sha256` pins the entire safe profile document. Inspect also
verifies executable/schema/config content pins. Initialization archives those safe
bytes and records the effective adapter version. Recheck immutable profile bytes
and executable identity before launching; changed binaries/config refuse until a
new signed profile is supplied. A CLI version string alone is insufficient.

Environment profile references use `{profile_id, profile_sha256, capabilities,
limits, cleanup}`. The profile's `kind` selects its strict adapter schema. Both
Docker and SSH profiles must bind host identity and owned resource namespace;
SSH additionally binds host-key fingerprint. Adapter owners define the remaining
schema before implementation. Unknown profile kind/capability is unsupported,
not passed through as an arbitrary command.

The environment profile may include `codex_tool_policy: docker-confined-v1`.
This optional field is included in the signed profile digest and selects fixed,
digest-checked seccomp bytes and a preinstalled named AppArmor profile only for
the main Codex tool container. Other containers retain their existing policy.
Omission preserves the old document contract; unknown values refuse admission.
The host operator owns profile installation. The runtime verifies configuration
and active enforcing mode, and never installs host policy. Receipt recovery
remains cleanup-only without activating this setting. See the
[operator prerequisites](../agents/engagement.md#codex-tool-policy-on-docker).

`limits` is exactly `{hard, max_workers, max_worker_lease_seconds, informational}`.
The initial hard map supports `invocations` and `worker_seconds`; positive integers
only, booleans excluded. Informational dimensions may include token counts/cost
but are not enforced caps. Additional hard dimensions require an adapter capability
that proves their enforcement. `max_workers` is a positive integer. The worker
lease limit is a positive integer and is independent of overall engagement age.
`revocation` is exactly `{operator_stop: true, disconnected_worker: "lease_expiry"}`.

The host's provider proxy journals each request attempt before sending bytes, with
worker/dispatch and optional invocation identity, then records a completed response
or unknown outcome. Startup/model-discovery requests have no invocation. Retries
are distinct attempts; repeated observations of one ID are idempotent. Historical
journals without this accounting marker retain incomplete provider coverage.
Native token and cost-estimate observations are separate: absent totals stay
incomplete, and `billed_cost` remains null unless a real billing receipt is available
(neither pinned adapter currently supplies one). See the
[accounting handoff](../agents/fresh-target-handoff.md#read-accounting-correctly).

Bound IDs to 1–128 ASCII letters/digits/`_.-`, text fields to explicit byte limits,
collections to declared practical cardinality limits, JSON nesting/total input
bytes to a parser budget. Reject an unexpected field rather than ignore it. Native
wire formats are adapter-private and must not leak into this signed contract.

Each runtime's `tool_bundle` contains `{path, manifest_sha256, platform}`; OMP
additionally requires `bun_version`. The path names a materialized
regular-file tree; its manifest uses the same byte, size and mode binding as source
inputs. Platform is `linux/amd64` or `linux/arm64`, and Bun version is an exact
release number for OMP. Preflight freezes `runtimes/<id>.bundle-manifest.json`; staging
rechecks every supplied byte. The support tree is not target access and grants no
target permissions. Codex bundles reject OMP-only fields.

The bridge separately verifies the fixed layout (`bin/bun`, the reviewed
`native_runtime_omp_tools.mjs`, and `node_modules/@oh-my-pi/pi-coding-agent`), matching
SDK/runtime versions and native platform compatibility. Codex's fixed bundle has
`bin/codex` for its native execution server in the isolated environment; the
separate host executable owns the model session. A manifest match proves
input identity, not that the bundle can execute. Native dependencies for another
OS do not qualify a Linux environment.

M1 fixes the following exact shapes after coordination with the runtime and
environment owners. They replace the descriptive field-table examples above:

- `environments` contains signed references with exactly
  `{profile_id, profile_sha256, capabilities, limits, cleanup}`. Each referenced
  profile has `{kind: "research-environment-profile-v2", transport, docker_binary,
  docker_endpoint, daemon_id, image_id, platform, uid, gid, ssh}`.
  Transport is `docker` or `ssh-docker`; Docker endpoint is a canonical absolute
  `unix://` socket reference. Daemon identity may be null only until setup observes
  and pins it before effects. Image is digest-pinned. Platform is `linux/amd64` or
  `linux/arm64`; uid is positive and gid nonnegative. Executable paths are canonical
  absolute paths. The lab's `/work` is a bounded container-local filesystem, not a
  host mount. The controller checks actual host worker directories at launch;
  there is no unused host-workspace field in this profile. An offline parser does
  not prove runtime boundaries work.
- Docker uses `ssh: null`. SSH uses exactly
  `{host, port, user, known_hosts_file, known_hosts_sha256, identity_file,
  python_binary}`. Known-host bytes are digest-pinned; the identity file is a
  reference whose credential contents are never read or archived by preflight.
  The adapter owns actual SSH host verification and credential availability.
- Environment capabilities are a subset of `source`, `binary`, `application`,
  `acquisition`, `network_proxy`, `shared_write`, `renewable_lease`. These request
  capabilities; runtime evidence must establish their support. Limits are exactly
  `{memory_bytes, cpu_count, pids, workspace_bytes, lease_seconds, output_bytes}`;
  all are positive, all except CPU count are integers, and the lease fits the
  signed maximum worker lease. Cleanup is exactly
  `{owned_resources: true, owned_workspace: true}`.
- Each network class contains `{protocol, host, port, address_policy}` rows.
  Protocol is HTTP or HTTPS, hosts are exact normalized DNS/IP values and ports
  are explicit. Address policy is `{public_only, cidrs}`: public-only routes use an
  empty CIDR list; other routes use nonempty canonical IPv4/IPv6 CIDRs. Wildcards,
  URL userinfo and duplicate destinations are rejected. Application access must
  have a corresponding target route. Adapters enforce DNS, redirect and socket
  policy; parsing a route does not establish that enforcement.
- Effect rows are exactly `{id, kind, access_ids, environment_ids, account_refs,
  rung, artifact_classes, cleanup_required}`. Kinds are `read`, `execute`, `write`,
  `reset`, `artifact_create`; rungs are `source_only`, `self`, `stored`, `cross_user` and
  must fit the signed ceiling. IDs resolve to the signed access/environment set,
  accounts/permissions fit each access, and environments request each access mode.
  Mutation/reset/artifact creation requires cleanup; artifact creation names classes.
  Reset is available only through the signed optional application owner above.
- Preflight returns `verified_inputs` with `capabilities_verified: false` and no
  runtime/target contact. Safe frozen files include authority, profiles/configs/
  schemas, known hosts and source manifests, never native credentials or source/
  binary payloads. The controller/environment must freeze and recheck payload bytes
  before use. Source inventory checks metadata again after its byte scan; its
  observation cannot promise that an external directory remains immutable later.

### Candidate owned lab state class

The implementation now recognizes the explicitly signed `owned-lab-state-v1`
class on an `artifact_create` effect. The artifact is one exact disposable lab
instance and its mutable files, processes and private IPC state. It covers first
creation inside that instance; publication is a later content snapshot. Status
counts lab instances and pending cleanup, never individually registered files.
This candidate mechanism does not adopt a replacement for current operator gates.

The class supports account-free source/binary resources in the existing owned
Docker or pinned SSH-Docker environment. The effect must require cleanup and use
`source_only` or `self`. A separate matching `execute` effect is required before
native tools or a capture probe starts. Capture's optional `artifact_effect_id`
selects creation authority; `effect_id` continues to select execution. Explicit unsupported or ambiguous
class selections refuse. Unselected unsupported grants confer no class capability;
scopes without this class preserve their existing meaning.
Application state, model-owner state, persistent storage and external effects are
outside this class.

The host records intent before allocation, then exact owner IDs, verified Docker
configuration and a fixed mount inventory before native admission. The inventory
covers `/work`, `/tmp`, `/dev/shm`, `/dev/pts`, `/dev/mqueue`, Docker-managed files
and restricted kernel mounts. Workspace capacity must be a positive multiple of
4096 bytes for this class. `/tmp` and shared memory each use
`min(workspace_bytes, 64 MiB)`; `/dev` is bounded at 64 MiB. These are separate
capacities within the signed memory/swap ceiling, not one combined workspace cap.
Unknown writable mounts, host/shared namespaces and additional devices refuse.

The immutable journal owns `lab_artifacts`: intended, ready and clean states,
exact environment nonce, initial dispatch/worker/generation/resources and named
host capture staging owners. Renewal or same-owner specialist continuation reuses
that record. Full container, staging-container, prepared-image and registered host
staging absence is required before final settlement, resource reconciliation or
unused preparation refund. Cleanup remains possible after revocation; uncertainty
retains the hold. Frozen evidence objects and published workspace copies remain
retained and are explicitly outside disposable lab cleanup. Physical Linux
qualification is separate from the [contained workflow](../../evals/native-qualification/OWNED-LAB-STATE-E2E.md).

## One journal and replay

Private root layout:

```text
contract/             frozen scope, signature, signer proof, goal and safe profiles
events/000000001.json immutable committed events; one contiguous sequence
objects/<sha256>      sanitized frozen publication and protected receipt bytes
receipts/<id>-<sha>   immutable host observations, including late terminal results
workers/<id>/         adapter-owned private session metadata, not model-writable
controller.lock       host process lease
```

Worker workspaces and native session history are outside host control directories
and isolated from each other. `objects` is writable only by the host; workers see
authorized read-only publications, never private runtime or credential material.

Each event has `{kind: engagement-event-v2, engagement_id, sequence, previous_sha256,
at, request_id, request_sha256, actor, type, payload}`. Actor is derived by the host:
`{kind: operator|worker|runtime|environment|controller, id, generation}`. Freeze and
validate referenced objects before event publication. Write to a unique temporary
file, fsync, publish without replacing an existing sequence, fsync directory.
The lease serializes allocation/publication. Temporary uncommitted files do not
become events. A gap, changed hash, unknown type or conflicting request ID holds
mutations; status reports corruption and export cannot claim completeness.

The request deduplication key is trusted actor/generation plus request ID. Identical
retry returns the original receipt even if the expected revision is now old;
changed bytes with the same ID fail `request_conflict`. A replayed old receipt
grants no present capability. Sequence is the global revision. Mutation requests
carry `expected_revision`; stale revision returns `revision_conflict` plus the
current cursor and has no effect. Retry only after refresh with a new request ID.

Use the accepted request payload itself as the event payload, rather than store
both a command log and mutable row copies. The reducer validates transitions and
produces state. Runtime native conversation history stays native.

## Host interfaces to runtime/environment owners

These are internal Python interfaces, never model-selectable authority:

```python
inspect_inputs(inputs_file: Path) -> dict
initialize(root: Path, inputs_file: Path) -> dict
status(root: Path, principal: Principal, since: Cursor | None, limit: int) -> dict
apply(root: Path, principal: Principal, request: dict) -> dict
prepare_dispatch(root: Path, principal: Principal, request: dict) -> dict
adopt_receipt(root: Path, dispatch_id: str, receipt_file: Path, adapter_identity: dict) -> dict
reconcile(root: Path, dispatch_id: str, readback_file: Path, adapter_identity: dict) -> dict
```

`Principal` is constructed by the host transport/adapter, not parsed from request
JSON. `prepare_dispatch` atomically verifies current assignment/role, dependencies,
resource leases, authority and available limits; it records reservation plus
write-ahead intent before returning a dispatch grant. Before actual execution the
owner revalidates the grant's worker/assignment generations and live lease. Frozen
request fields include dispatch ID, capability/authority digest, worker/task and
generation, model/runtime, input/object hashes, resource set, allowed effect class,
reservation, lease deadline and optional overall expiry.

The owner records start intent before an effect, then publishes a protected
`settled` or `unknown` receipt bound to those exact fields and actual owned resource
identity. `settled` means the adapter knows termination and observations; it never
means a security claim is confirmed. Exit code zero alone cannot settle target
effects. `adopt_receipt` verifies the owner identity, hashes and receipt meaning,
then settles once. Lost controller acknowledgment is recovered by receipt adoption,
not by redispatch. Missing receipt leaves the affected resources and unused
reservation held; other isolated resources remain eligible. `reconcile` requires
protected observation of those exact resources, never an agent narrative.

An unknown observation can be followed by a new terminal receipt for the same
complete dispatch grant. Both observations remain immutable. Only the terminal
transition releases its reservation and charges observed usage; repeating either
receipt returns its prior acceptance. Later receipts cannot reduce or discard
previously observed seconds, token counters or cost estimates. A resource-only readback cannot establish
that a still-unknown runtime has terminated.

Allowed host event families: `initialized`, `request_accepted`, `dispatch_intended`,
`dispatch_observed`, `effect_reconciled`, `worker_revoked`, `worker_stop_observed`,
`worker_started`, `direction_recorded`, `notice_delivered`, `stop_requested`,
`cleanup_observed`, `closed`. Keep each family's payload strict. Request types
below carry ordinary task/publication/review mutations in `request_accepted`.

## Worker interface

`status --since CURSOR` is read-only. Return own assignment/generation, allowed
capabilities, current holds/limits, relevant publications/reviews/directions and a
bounded page of stable event references. Return `next_cursor` and `has_more`;
never silently truncate. A cursor binds engagement ID, sequence and event digest.
All published knowledge remains readable to the lead/reviewers and scoped workers;
private runtime histories and secrets are excluded. Delivery notices are hints.
Status collection summaries are bounded and disclose total counts and truncation.
The cursor-paged event stream carries the complete publication bodies and artifact
references, with a byte limit as well as an event count limit.

`claim` is an authenticated mutation with request ID and expected revision. Select
the highest-priority eligible ready task, stable creation order for ties; one
worker owns it, with a new assignment generation. Validate prerequisites and all
resource holds/write leases atomically. An active owner cannot claim another
incompatible task. Stale claims, completed tasks and unknown effects do not become
new ownership through lease expiry.

`submit --file FILE` accepts `{request_id, expected_revision, type, payload}` only.
Reject caller-supplied actor/role/session/generation authority. Allowed types:

| Type | Payload and role |
| --- | --- |
| `publish` | Any active worker: observation/hypothesis/instrument/experiment/claim proposal with subject, conditions, supporting/contrary refs, correction links and source artifacts. Host freezes safe bytes. Scores bind instrument/candidate/environment digests and metric/reset definition; they do not confirm claims. |
| `task_create` | Any active worker: question, prerequisites, resources, evidence refs. Specialist follow-ups enter unprioritized ready backlog; lead sets priority. No implied permission expansion. |
| `task_priority`, `task_assign` | Lead only; explicit task/version/priority or assignment. Reassignment first revokes existing capability and reconciles effects. |
| `worker_request` | Lead only: allowed runtime/model/role, question and capabilities within signed scope. A specialist asking for a worker is a follow-up task/request for lead attention, never a spawn. |
| `task_result` | Assigned worker: disposition active/blocked/deferred/completed, evidence and unresolved effects. Completion never directly promotes a claim or resolves resource uncertainty. |
| `review_request` | Lead only: kind claim/strategy/closure/patch/escalation, exact packet digest and affected versions/resources. Escalation names the prior independently confirmed claim as `subject_id` and adds `next_effect_id`; the host derives the protected predecessor and freezes the exact adjacent transition. A specialist can publish a challenge that creates an obligation; it does not spawn a reviewer. |
| `review_result` | Assigned fresh reviewer only: bound packet, checks and protected receipt refs, findings and disposition; full published evidence is inspectable. |
| `review_response` | Lead: action linked to task/experiment or substantive rebuttal with evidence. Disputed explanation remains an obligation pending fresh review. |
| `closure_request` | Lead: goal/result version, all task/claim dispositions, unresolved paths and cleanup obligations. Broad goals cannot close merely on first finding. |
| `updates_ack` | Any worker: last delivered/consumed cursor. Durable acknowledgment changes only its cursor; `status` itself stays read-only. |

`direction` and `stop` are operator-authenticated facade operations. Worker content
cannot select those event types. Direction changes priority/attention, never signed
authority. Keep provenance/acknowledgment and human intervention in export.

## Review and replacement state

Keep task/search, claim and cleanup separately: task ready/assigned/blocked/deferred/
completed/reviewed_complete; claim unconfirmed/supported/independently_confirmed/
refuted/needs_review; cleanup pending/verified/unresolved. An accepted review binds
claim version, actor permissions, exact effect, causal control and clean independent
reproduction receipt identities. Material publication changes invalidate only the
affected review. Worker result labels alone cannot supply any missing evidence.

A strategy obligation records concrete evidence of contradiction, repeated
materially identical experiments without a discriminator, strong-lead dismissal or
closure. No timer/token count generates a stagnation verdict. Delivery plus a
completed lead decision checkpoint constitutes an opportunity to respond. After
two opportunities with neither action nor substantive evidence-backed response,
record replacement intent. A running experiment, crash or disputed response is not
nonresponse. Revoke old generation and creation rights, stop/read back owned tools,
hold unknown effects, then start one replacement lead. Pending review must be
fulfilled before affected research resumes; unrelated specialist work can continue.

## Existing code to reuse and caller limits

- `operator_signature.py:83`: exact SSH signature verification, pinned signers and
  fingerprint. Supply a v2 challenge/namespace; preserve v1 verification unchanged.
- `engagement_records.py:81,121,203`: secret-class scan, duplicate-key rejection,
  canonical JSON. Canonical helper currently permits NaN: validate finite numeric
  values before hashing, or add strict safe serialization in the new contract.
- `native_research.py:175–250`: owner/private regular-file/root checks and atomic
  writes. Preserve protections; v2 event publication also requires no overwrite
  and ancestor-safe bound reads. Importing runner private helpers risks bringing
  fixed OpenCode/capture semantics; extract only shared callers when necessary.
- `native_continuation.py:576–866`: freeze request/input, compare protected receipt,
  adopt exactly once, retain `security_effect: unproven`. Reuse semantics, not the
  old mutable state plus JSONL event pair or global unknown-effect hold.
- `native_research.py:3875–4044`: write-ahead dispatch and bounded trace observation.
  Its fixed roles, model pair, global lock and v1 scope/timers cannot drive v2.
- `native_patch_check.py:58–232`: bounded safe diff, `git apply --no-unsafe-paths`,
  original/patched manifests and review byte binding. Keep patch optional by goal.
- `native_closeout.py:286–363`: exact daemon/container/network identity and absence
  readback, verified producer stop. Generalize per-owned resource; do not interpret
  `target_state: not_assessed` as target cleanup or security confirmation.
- Secret scanning is not a universal classifier. The current shared patterns do
  not cover every auth-cookie form. Use structured capture allowlists, known-secret
  rejection and explicit cookie/header rules before persistence; arbitrary native
  session dumps cannot be declared sanitized merely because one regex passed.

Affected callers/readers: facade routing; v2 contract/controller; runtime adapters;
environment admission/receipts; patch/review/closeout callers; bootstrap/native and
root guides; scope/input examples; setup/install/preflight; CI/E2E evidence. Preserve
legacy readers, old scope signatures, historical evidence and current integrity pins.
No change to `CONTROL_SHA` is justified until its actual pinned source changes.

## Acceptance of this design

Parent confirmed on 14 November: one journal, per-worker host endpoint identity,
facade subprocess E2E and explicit host-only simulated adapter; enforceable
reservations only; no mandatory recipe/catalog. Runtime/environment owners still
must verify their actual isolation, receipt and revocation mechanisms. The two
serious alternatives were native pooled worker identity (reuse only when proved)
and isolated native sessions with private host endpoint (chosen safe base).
