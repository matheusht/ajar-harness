# Native engagement worker protocol

Read `methodology.md`, `goal.md` and `scope.md` in `/input/bootstrap` before work.
The methodology is portable research guidance; this file describes the OSLit
interface. The controller freezes both at engagement initialization. Neither
adds authority to the operator-signed scope.

Your native shell, filesystem and research tools operate in an owned lab. Original
inputs are read-only under `/input/<access_id>`; use `/work` for copies, tools and
results. Model/provider access and lab/target access are separate. Host credentials,
controller records and other workers' private files are unavailable to your tools.
A denied operation is a boundary or missing prerequisite to report, not a reason
to attempt a host escape. Only your authenticated tool channel supplies identity.

## Read the current state

Call `engagement_status` with `{"since":null,"limit":30}`. It returns the current
revision, assignment, usage, summary counts and bounded journal updates. Continue
with `since` set to `next_cursor` while `has_more` is true. To reconstruct state,
read from null, then apply events in order. Do not infer missing state from one page.

A large status page may return `ephemeral_read_view:{sha256,bytes,instruction}`.
Fetch that digest's full bytes with `engagement_read` before processing or
acknowledging the page. Another status call replaces this temporary view; if it
expires, requery the same cursor. A transient view is not a published evidence
object or claim reference. Separately, a runner prompt may contain
`read_request:{since,limit}`: pass those arguments to `engagement_status` to obtain
the deferred page. That request contains no readable digest.

`engagement_read` takes `{"sha256":"sha256:<digest>","offset":0,"max_bytes":65536}`.
Use the returned `next_offset` until null. Respect `encoding`: bytes may be UTF-8
or base64, including a UTF-8 code point split across byte ranges. Reassemble bytes
before decoding a whole text or JSON document. The result reports total bytes and
whether the source is published evidence or a transient view.

After reading a whole page, submit `updates_ack` with its `next_cursor`. An
acknowledgment only advances your durable delivery cursor; it does not grant
permission. Reading or acknowledging a notice is never required for revocation.

## Submit exact typed requests

Every `engagement_submit` call has this envelope:

```json
{"request":{"request_id":"unique-request-1","expected_revision":12,"type":"claim","payload":{}}}
```

Use the latest observed revision. Revisions can change during tools or peer work.
On a revision conflict, refresh, reconsider the action and use a new request ID.
An identical retry uses the same ID and exact request bytes. Do not change accepted
content under an old ID. IDs use letters, digits, dots, underscores or hyphens.
The schemas below show payloads; substitute existing public IDs and real evidence.
Do not put role, identity, grants, credentials or host receipts in the envelope.

| Type | Required payload | Who can use it |
| --- | --- | --- |
| `worker_request` | `{"worker_id":"specialist-1","role":"specialist","profile_id":"runtime-main","question":"Inspect this concrete question."}` | Lead; role may also be `reviewer`. Select a signed runtime profile. |
| `task_create` | `{"task_id":"question-1","question":"Trace this input to its consumer.","priority":10,"resources":["source-main"],"prerequisites":[],"evidence_refs":[]}` | Any worker; only the lead may set nonzero priority. |
| `task_priority` | `{"task_id":"question-1","priority":20}` | Lead. Higher priorities are claimed first. |
| `task_assign` | `{"task_id":"question-1","worker_id":"specialist-1"}` | Lead; assignee must be idle and eligible. |
| `claim` | `{}` | Idle worker; atomically claims the highest-priority eligible task. |
| `publish` | `{"publication_id":"observation-1","kind":"observation","subject":"Observed condition","body":"Describe the exact observation and limit.","refs":[],"supersedes":[],"artifacts":[]}` | Any worker. Kinds: `observation`, `hypothesis`, `instrument`, `experiment`, `claim`, `challenge`. |
| `task_result` | `{"task_id":"question-1","generation":1,"disposition":"completed","result":"State the supported outcome or exact limit.","evidence_refs":["observation-1"]}` | Assigned owner. Use the **task assignment generation**. Dispositions: `completed`, `blocked`, `deferred`. |
| `updates_ack` | `{"cursor":"<fully-read-next_cursor>"}` | Any worker, for its own delivery cursor. |

A task result may be deferred until the host settles effects and stops that task's
owned resources. A finished model turn is neither a task result nor closure. The
controller can grant a subsequent task after cleanup and reconstruct context from
the journal. Keep useful scripts and results published before ending an assignment.

## Publish files and capture experiments

Call `engagement_artifact` with `{"path":"probe.py","max_bytes":1048576}` for a
file relative to `/work`. It reads back the actual lab file and returns a frozen
`path` and `sha256`. In a `publish` payload, use `artifacts:[{"path":"<returned-path>"}]`.
Do not submit a lab path directly as a controller path. Publications contain public
facts only. Credential-like output may be withheld rather than stored.

Register a frozen instrument with `instrument_register`:

```json
{"instrument_id":"instrument-1","artifact_sha256":"sha256:<artifact>","metric":"Describe what is measured","reset":"Describe starting-state restoration","conditions":{"version":"observed-version"},"supersedes":[]}
```

An instrument is a versioned file used by the probe. Publish a revised instrument
under a new ID with `supersedes`; rerun candidates before comparing measurements.

`engagement_capture` runs pinned bytes in a separately reserved owned lab:

```json
{"instrument_id":"instrument-1","candidate_path":"candidate.bin","probe_path":"probe.py","interpreter":"python3","arguments":[],"conditions":{"version":"observed-version"},"seconds":60,"patch_id":null,"patch_arm":null}
```

The optional `resources` field selects a nonempty, unique subset of public access
IDs in the current grant; omission selects the whole grant. Source/binary subjects
are `/input/<access_id>` paths, and application subjects are their signed base URLs.
For source/binary-only capture, optional `effect_id` names the signed effect used
for probe execution. It must cover the selected resources and environment without
account references; higher rungs require the current transition review below.
Omission uses the initial read effect. Preparation and cleanup use the unique
initial account-free read effect. Application captures select actual request effects
with `X-OSLit-Effect`, so they reject this capture-level selector.
The probe receives the frozen instrument path, candidate path, each selected subject,
then `arguments`. An interpreter may be null for an executable probe. It must
be available in the signed environment. The host binds executed bytes, conditions,
output and operation identity; a later assertion cannot replace this capture.
The time limit bounds the operation while short grants renew within remaining
allowance. Any application subject returns `clean_start:false` with
`remote_application_reset_unverified`; a fresh local container does not establish a
remote reset. Returned `network_request_ids` bind actual auxiliary target requests
to protected account/effect observations. A capture refusal is not an experiment.

After a successful settled capture, submit `experiment_record`:

```json
{"experiment_id":"effect-1","instrument_id":"instrument-1","candidate_sha256":"sha256:<capture-candidate>","probe_sha256":"sha256:<capture-probe>","operation_id":"<capture-operation>","purpose":"effect","conditions":{"version":"observed-version"},"score":null,"resources":["source-main"],"explains":null,"supersedes":[]}
```

Conditions, resources and digests must match the protected execution. Purpose is
`effect`, `control`, `replay`, `normal_function`, `variant` or `exploration`. A control
uses `explains:{"experiment_id":"effect-1","variable":"The removed causal condition"}`;
a replay points to the effect with `variable:null`. A score is optional and finite.
An experiment with unobserved or unsettled execution cannot be registered as fact.

`experiment_compare` takes `{"comparison_id":"comparison-1","experiments":["candidate-1","candidate-2"]}`.
The controller requires matching instrument, conditions, input, environment,
effect, accounts and resources. Comparison ranks observations; it proves no claim.

## Use signed application accounts

For a scoped target HTTP request, select the public access/account IDs with
`X-OSLit-Access: <access_id>` and `X-OSLit-Account: <account_ref>`. Omit the account
selector for an anonymous request. Select a signed effect with
`X-OSLit-Effect: <effect_id>` when several read/write effects fit that request;
omission is accepted only when exactly one fits. Do not supply Authorization, Cookie or another
authentication value yourself. The gateway strips selectors and binds private
credentials to the exact signed origin and account. Redirects need independent
admission. Target authentication never applies to provider or acquisition routes.

The gateway records request intent and result with access, account, effect, method,
origin and a path hash. These facts identify the selected binding, not an independent
proof of the user the target recognized. Check target identity through benign
observable behavior. Missing account bindings are an operator setup prerequisite;
do not ask another worker to publish or copy the credential.

## Claims and independent review

`claim_propose` takes:

```json
{"claim_id":"claim-1","text":"Bounded claim under exact conditions","effect":"effect-1","control":"control-1","replay":null,"contrary":["contrary-observation"],"resources":["source-main"],"supersedes":[]}
```

Missing effect/control/replay may be null where accepted, but cannot become an
independently confirmed claim. Contrary references name publications. Independent
confirmation requires a fresh reviewer's own replay, not merely a researcher
supplying a replay ID or agreeing with its summary.

The lead first creates a fresh `reviewer` worker, then submits `review_request`:
`{"review_id":"review-1","kind":"claim","subject_id":"claim-1","reviewer_id":"reviewer-1"}`.
Kinds are `claim`, `strategy`, `closure` or `patch`. The reviewer reads the frozen
packet and contrary evidence through `engagement_read`, performs necessary checks,
and submits `review_result`:

```json
{"review_id":"review-1","packet_sha256":"sha256:<assigned-packet>","disposition":"accept","checks":{"measurement":true,"permissions":true,"causal_control":true,"clean_replay":true,"completeness":true},"evidence_refs":["reviewer-replay-1"],"contrary_refs":["contrary-observation"],"reason":"Explain what was independently observed and its limit."}
```

Dispositions are `accept`, `reject`, `reopen` or `unresolved`. Set checks to the facts
observed; true flags alone do not supply evidence. Claim acceptance needs the
reviewer's protected replay and all required contrary references. Material changes
invalidate earlier review; a fresh reviewer and packet are required.

For a declared internal escalation, use a fresh reviewer and submit:

```json
{"review_id":"transition-1","kind":"escalation","subject_id":"claim-1","reviewer_id":"reviewer-2","next_effect_id":"signed-stored-effect"}
```

`subject_id` names a current independently confirmed prior claim. The controller
derives its protected preceding effect and freezes the original claim review,
effect/control/replay, instruments, contrary evidence and next signed effect in the
packet. Only adjacent `self` → `stored` → `cross_user` transitions qualify. The
resource identities, environment and observed accounts must match that transition.
The reviewer submits the existing `review_result` shape, citing every experiment
and contrary reference in the packet. Boolean checks alone cannot authorize it.

Each new effect rechecks the exact material and current authority. Reopening the
prior claim or superseding its evidence blocks further admission, including from
an active worker; matching late outcomes and owned cleanup remain recordable.
A fresh review request for the same prior claim and next effect holds that
transition immediately. It replaces earlier pending or accepted reviews; an older
reviewer's late answer cannot restore admission. The new review must accept before
effects resume. Reviews of other transitions retain their own decisions.
An accepted transition does not change a claim, widen scope or prove semantic
containment. Shared-application reset, generic artifact classes and route activation
remain separate limits; current human gates apply, and generic `artifact_create`
admission is unsupported.

`strategy_challenge` takes `{"obligation_id":"challenge-1","kind":"contradiction","refs":["contrary-observation"],"resources":["source-main"],"reason":"State the concrete unresolved conflict."}`.
Kinds are `contradiction`, `repetition`, `strong_lead_dismissal`. Repetition requires
comparable recorded experiments, not a time or message count. The lead addresses
an obligation with `review_response`, for example:
`{"obligation_id":"challenge-1","action":"task","refs":["question-2"],"reason":"This discriminating test addresses the conflict."}`.
Actions are `task`, `experiment`, `rebuttal`, `review`; references must match that kind.
A substantive disputed response remains explicit and needs fresh judgment.

## Requested patches and ending

Only a signed patch-required goal admits `patch_propose`:
`{"patch_id":"patch-1","claim_id":"claim-1","source_access":"source-main","diff_sha256":"sha256:<published-diff>","supersedes":[]}`.
The host freezes original and patched manifests. Use capture with `patch_id` and
`patch_arm:"original"` or `"patched"` for the requested verification. Patch review
requires relevant original/patched effect, control, normal-function and variant
experiments; a diff alone is not acceptance.

The lead proposes closure using `closure_request`:
`{"closure_id":"closure-1","outcome":"goal_met","claim_ids":["claim-1"],"remaining":[],"reason":"Explain the evidence and precise stopping reason."}`.
Outcomes are `goal_met`, `covered_dry` or `blocked`. List every unresolved task in
`remaining`. A broad goal cannot close as met with material work remaining; a
covered-dry result is bounded, never universal absence. Obtain a fresh closure
review through the same review protocol. The host then revokes workers, verifies
cleanup and settles usage before final closure. Unknown effects block completion.
An operator stop or exhausted authority takes effect immediately without waiting
for another model decision or review.
