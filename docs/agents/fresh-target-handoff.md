# Fresh-target operator handoff

Use the candidate branch `codex/oslit-research-autonomy-20261116`. It extends the
M0–M6 implementation with research autonomy, native helpers and the active knowledge
library. Read the [dated delivery and verification state](../wiki/oslit-research-autonomy-delivery-2026-11-16.md)
for the checked revision and runtime profiles before claiming support. The operator
owns the fresh-target investigation, native-agent comparison and sustained research
acceptance. A passing engineering fixture does not establish those outcomes.

## Prepare once

1. Select a controller host and a working local Docker or authorized SSH Docker
   lab. Install the selected pinned native runtime and tool bundle using
   [native tool installation](native-tool-installation.md). A Linux controller
   additionally needs the separate signed `model_host` image; the macOS controller
   uses the native sandbox owner. Match architecture, image and bundle hashes.
2. Copy the matching [input template](../../examples/native-engagement-v2/README.md)
   to a private durable directory outside the target and repository. Source,
   binary, application and combined access are supported. Choose Codex or OMP;
   both are unnecessary for one run. Keep credentials in the host's private
   environment/store, referenced by name only.
3. Select `authority_policy: "research-autonomy-v1"` for a new autonomy engagement.
   Fill the target, goal, provider/model, access, permitted effects, cleanup rights,
   machine capacity and real paths. Choose total research limits only when needed:
   `limits.hard: {}` adds none; supplied `invocations` or `worker_seconds` caps apply
   across workers and recovery. Worker seconds measure elapsed parent execution,
   including concurrent helpers without summing their overlapping time. Set no
   overall expiry when no deadline is intended; short worker leases still renew.
   Existing signed engagements retain their original policy and limits.
4. Follow [input pinning and signing](engagement.md#fill-and-sign-the-inputs).
   Every `REPLACE_` must be resolved. Keep the private operator key separate;
   signing is the operator's decision and is never done on their behalf.

No generic template can supply a target's authority, actual provider access or
reset semantics. For owned application replay, sign the supported reset descriptor.
For Docker database state, use the [v2 application profile](../research/oslit-v2-contract-2026-11-14.md)
with bounded `/state/<id>` volumes and a database command that uses those paths.
Every reset starts empty disposable volumes; the signed startup command initializes
them from its pinned image inside the memory-limited container. An optional
signed application artifact effect records their creation and cleanup lifecycle.
External databases and persistent state outside that owner need their own reset;
an ordinary restart does not establish clean replay. Unsupported artifact classes
remain refused. The research-autonomy policy admits initially signed effects without
repeated artifact confirmation or a generic escalation order. Independent review
and all signed boundaries still apply; additional authority requires the operator.

## Inspect, start and observe

Run from the candidate repository with canonical absolute paths. These commands
assume the prepared input directory and engagement parent already exist:

```sh
OSLIT_INPUTS=/absolute/private/inputs/inputs.json
OSLIT_RUN=/absolute/private/engagements/fresh-target
python3 tools/native_engagement.py inspect --inputs "$OSLIT_INPUTS"
python3 tools/native_engagement.py run --inputs "$OSLIT_INPUTS" --engagement-root "$OSLIT_RUN"
```

Resolve every inspect `blocked_codes` entry before running. Inspect is offline:
it validates the signature, local pins and prerequisites. Run verifies actual
runtime, environment and provider access. Keep the foreground owner and host awake.
The `run` command creates a new engagement; use `resume` for an existing one.

In a second terminal, set `OSLIT_RUN` to the same directory:

```sh
python3 tools/native_engagement.py status --engagement-root "$OSLIT_RUN"
python3 tools/native_engagement.py status --engagement-root "$OSLIT_RUN" --view board --query parser --limit 20
python3 tools/native_engagement.py direction --engagement-root "$OSLIT_RUN" --file /absolute/private/direction.md
```

Directions refine work within signed authority. They cannot expand scope.
Ordinary model turn completion does not end an investigation. The lead owns
priorities, team requests and continued work; unresolved paths remain visible.
The searchable board derives from the journal and is included in export. Agents
send typed `team_message` submissions through the existing tool; relevant peer
updates reach active turns through native steering. Durable acknowledgments recover
missed updates. Messages remain team-visible data and confer no authority.

## Recover, stop and retain the result

After controller loss, `resume` reconciles recorded owners before restarting work:

```sh
python3 tools/native_engagement.py resume --engagement-root "$OSLIT_RUN"
```

For an intentional stop and result export:

```sh
python3 tools/native_engagement.py stop --engagement-root "$OSLIT_RUN"
python3 tools/native_engagement.py status --engagement-root "$OSLIT_RUN"
python3 tools/native_engagement.py export --engagement-root "$OSLIT_RUN" --output /absolute/private/export
```

Inspect cleanup and resource holds. `stop` returning is not proof that every
remote effect is gone. Preserve unresolved resources and journal evidence for
reconciliation. Never delete historical engagement records to retry.

## Read accounting correctly

Status/export reports shared invocation and elapsed-parent worker-second use and
reservations under the autonomy policy. Optional total caps keep their signed
meaning, and older policies retain their original accounting. Helpers share the
parent's authority; their provider requests and tokens are still counted.
For new engagements, `provider_requests` counts proxy attempts journaled before
request bytes are sent, including retries and startup/model-discovery requests.
Completed means the HTTP response was fully read, not that inference succeeded.
Unknown includes interrupted responses and starts with no surviving finish receipt;
it never means zero provider work. Worker, dispatch and optional invocation IDs
live in the journal. The ledger stores no request bodies, URLs or credentials.
Old journals retain `provider_requests_complete:false` for unobserved history.

Native tokens and `known_estimated_cost` are observed subtotals, with completeness
flags. `cost` is null when a complete native estimate is unavailable. `billed_cost`
remains null with `provider_billing_receipt_unavailable`; native estimates are
not invoices. Hard dollar/token caps are unsupported and rejected at input
validation. Use provider-side limits when those constraints are necessary.

## What is already checked

The [current delivery page](../wiki/oslit-research-autonomy-delivery-2026-11-16.md)
separates local conformance, hosted native workflows, live-provider smoke checks and
remaining gaps. Its [verification record](../../evals/native-qualification/team-evidence/research-autonomy-20261116/README.md)
contains repeat commands and saved results. Historical
[integrated evidence](../research/oslit-implementation-assembly-2026-11-15.md) remains
valid for its recorded revision; it is not the current branch's qualification.

The current public OMP fixture uses the Responses API; the direct OMP fixture uses
Chat Completions. Remote-compaction continuity with Chat Completions remains
unqualified. Preserve the pinned native runtime's supported API/profile when using
its saved evidence. The live OMP source-read smoke is narrower than a full team
investigation; live Codex encountered a separate Mac Docker namespace prerequisite.
Live-model research quality, separate-host outages and sustained operation remain
unverified. No fresh target was run here.
