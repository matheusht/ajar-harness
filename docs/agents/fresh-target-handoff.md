# Fresh-target operator handoff

Use the candidate integration branch `codex/oslit-integrated-e2e-20261115`
([PR #220](https://github.com/matheusht/redteam-harness/pull/220)). It contains the
M0–M6 implementation. The operator owns the fresh-target investigation and
full-day run. A passing engineering fixture is not research acceptance.

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
3. Fill the target, goal, provider/model, access, permitted effects, cleanup rights,
   budgets and real paths. Set no overall expiry if the authorized investigation
   should continue without a deadline; worker leases still renew and shared
   invocation/worker-second limits still apply. Choose budgets for the whole team.
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
remain refused, and the repository's artifact/escalation review gates still apply.

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

Status/export reports shared invocation and worker-second use and reservations.
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

The [integrated evidence](../research/oslit-implementation-assembly-2026-11-15.md)
records real pinned Linux Codex/OMP source workflows with deterministic provider
replies, continuity, isolation, owner-loss recovery and cleanup. The focused
[accounting scenario](../../evals/native-qualification/smoke/PROVIDER-ACCOUNTING-E2E.md)
covers proxy attempts and journal replay with an owned local provider.
The [shared-board workflow](../../evals/native-qualification/smoke/ENGAGEMENT-BOARD-STEERING-E2E.md)
checks searchable snapshots, native tool access, addressed messages, steering,
acknowledgments and export with a simulated runtime. The
[state-volume workflow](../../evals/native-qualification/APPLICATION-STATE-VOLUMES-SCENARIOS.md)
uses the signed controller/capture path and a real local HTTP service with simulated
Docker ownership. Physical Docker volume behavior still needs qualification.
Live-model investigation quality, separate-host outages and full-day operation
are deliberately left to the operator's test. No fresh target was run here.
