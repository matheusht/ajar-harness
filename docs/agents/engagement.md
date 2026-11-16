# Operate a candidate v2 engagement

Use this guide for the versioned Codex/OMP engagement route. It is candidate
implementation work: local checks, packaging and preflight do not establish
runtime qualification or research success. Policy adoption is recorded separately
in [Decision 0016](../decisions/0016-research-autonomy.md). Existing native/legacy records keep
their original contract. The signed scope defines authority; repository access and
these instructions grant none.
The field and authority contract is recorded in [Decision 0014](../decisions/0014-native-engagement-team.md).
Read the [current dated delivery state](../wiki/oslit-research-autonomy-delivery-2026-11-16.md) before
claiming support or readiness. Start with the [fresh-target handoff](fresh-target-handoff.md)
for installation, input preparation and run/recovery commands. Select
`authority_policy: "research-autonomy-v1"` in the initial scope before signing once.
The initial grant covers its permitted owned lab state and exact effects. Scientific
adequacy belongs to fresh independent review; preserved execution facts and actual
permissions remain enforced. Strategy advice cannot hold resources or force lead
replacement, and signed effects need no universal self/stored/cross-user sequence.
Existing signed policies keep their original rules. New authority and external
actions still require the operator's explicit authorization.

Optional `limits.hard` entries select total caps; `{}` adds none. A supplied
`worker_seconds` budget measures elapsed parent execution time including concurrent
helpers, not the sum of their overlapping durations. Provider requests and tokens
include all helper activity. Renewable short leases still control abandoned owners.
Full E2E and provider checks are authorized and underway; the dated delivery page
records their actual outcomes. Fresh-target acceptance and the research comparison
remain separate operator-owned work.

## Prepare the host and tool lab

Pin the repository revision and use a private, durable engagement directory. Keep
the host awake during a run. The protected model owner uses either macOS
`sandbox-exec` with Darwin process birth identity or the optional signed Linux
Docker model owner. The model container and target/tool lab are separate owners.
Both pinned runtimes have actual Linux startup and joined source-workflow
evidence with controlled provider replies, including owner-loss recovery and cleanup.
Read the [current verification record](../../evals/native-qualification/team-evidence/research-autonomy-20261116/README.md)
for the tested revision, profiles and limits. The public OMP fixture uses Responses;
the direct OMP fixture uses Chat Completions. Chat Completions continuity through
remote compaction remains unqualified. A live OMP source-read turn completed; live
Codex reached a separate Mac Docker namespace prerequisite before a model turn.
Full live-team research and sustained operation remain unverified.

Runtime prerequisites are Python 3.11+ with its standard library, OpenSSH
`ssh-keygen` for local signature verification, OpenSSL for private proxy trust,
the selected pinned native CLI, and its signed config/protocol schema. Codex
0.166.0 uses host Bun on macOS or pinned image Bun for its private Linux executor
bridge. OMP 18.20.0 uses the
pinned Linux SDK bundle with Bun 1.4.4. Preserve the reviewed
policy-selected guidance: new scopes freeze `engine/native-engagement-autonomy-method.md`
and `engine/native-engagement-autonomy-protocol.md`; earlier scopes retain their original files
from the pinned repository. `/tmp` must permit
short private Unix-socket directories.

The tool lab is either a local Docker endpoint or Docker reached through an
authorized SSH host. Its Linux platform and immutable image ID must match the
selected bundle; the image needs Python 3 and the bundle's native dependencies.
SSH uses an existing identity reference and independently verified known-hosts
bytes. Preflight reads local prerequisites without contacting Docker, SSH, a target
or a provider. Native startup must still verify the actual daemon/image and tool
boundary. The installer creates no VM, Docker image or host runtime.

Follow [native tool installation](native-tool-installation.md) for the pinned,
private Codex/OMP tool bundles. Keep their installation receipts. Install
`requirements-ci.txt` only in a separate environment when running repository
conformance and governed-schema checks; those test dependencies are not the v2
model/tool runtime or provider setup.

The installed Codex CLI can export its experimental protocol bundle without a
model turn:

```sh
codex app-server generate-json-schema --experimental --out /private/native-protocols/codex-0.166
```

Pin the generated `codex_app_server_protocol.v2.schemas.json`. For OMP, pin the
18.20.0 SDK's `src/modes/rpc/wire/rpc-wire.schema.json`. The config/schema pins record
exact reviewed inputs; the native startup handshake remains a separate check.

For a Linux model host, first prepare and verify a
[model image](native-tool-installation.md#prepare-a-linux-model-image). Retain its
host executable and tool-bundle paths. Add the following `model_host` object to
that runtime profile, resolve the placeholders, then sign the complete profile:

```json
{
  "kind": "linux-docker-model-v1",
  "docker_binary": "/usr/bin/docker",
  "docker_endpoint": "unix:///var/run/docker.sock",
  "daemon_id": "REPLACE_OBSERVED_LOCAL_DAEMON_ID",
  "image_id": "sha256:REPLACE_BUILT_MODEL_IMAGE_ID",
  "platform": "linux/amd64",
  "uid": 1000,
  "gid": 1000,
  "limits": {
    "memory_bytes": 1073741824,
    "cpu_count": 2,
    "pids": 256,
    "workspace_bytes": 1073741824
  }
}
```

The daemon must run on this Linux controller host with cgroup v2 and without
rootless mode. A remote tool lab remains a separate choice. The model image ID is
the inspected built image, not the Python base digest. The example limits are
unsigned choices, not measured runtime requirements. OMP custom provider/model
definitions may additionally use `model_catalog: {path, sha256}` pointing to a
private nonsecret `models.yml`; settings still use `config_file`. Both are frozen
at initialization. See the [runtime contract](../research/oslit-v2-contract-2026-11-14.md)
for exact fields and retained compatibility.

### Codex tool policy on Docker

If the Docker host's defaults block Codex's native user namespace, the environment
profile can include `"codex_tool_policy": "docker-confined-v1"`. Select it before
pinning and signing the profile. It applies only to the main Codex tool container;
staging, model, application and OMP containers retain their existing configuration.
An omitted setting preserves the existing profile and receipt contract.

On the authorized tool Docker host, verify the pinned policy files and install
the named AppArmor profile once, from the repository root:

```sh
PYTHONPATH=tools python3 -c 'from codex_tool_policy import load_policy; load_policy()'
sudo apparmor_parser -Ka engine/codex-tool-policy-v1/oslit-codex-tool-v1.apparmor
```

The add-only install refuses a preexisting name. Keep the profile installed while
its owned containers run; remove it only after their cleanup is verified. The
runtime supplies the pinned seccomp bytes to Docker and checks the exact security
options, absent added capabilities, AppArmor name and active enforcing mode.
Missing or mismatched policy stops setup or execution; recovery remains cleanup-only.
The runtime does not install host policy or switch to an unconfined mode.

The host operator owns the loaded policy bytes. Runtime readback establishes the
name and enforcing mode, not a kernel content hash. See the
[fixed policy's provenance](../../engine/codex-tool-policy-v1/SOURCE-PROVENANCE.md)
and the [dated integrated evidence](../research/oslit-implementation-assembly-2026-11-15.md)
before making qualification claims. The signed full-workflow integration passed
with the pinned native runtime and owned deterministic provider. Live-provider
behavior, broader access modes and research acceptance require their own evidence.

## Fill and sign the inputs

1. Copy the [source, binary, application or combined template](../../examples/native-engagement-v2/README.md)
   into a private directory. Replace every `REPLACE_` value, including the actual
   goal, any selected total budgets, machine limits, selected model, access identities and absolute paths.
   Review permitted routes/effects, benign objectives, cleanup rights and the
   escalation ceiling. For authenticated applications, configure the private
   account references below; target account identity still needs an observation.
2. Pin actual executable, native config, protocol schema, image and tool-bundle
   identities. Use the installation receipt's `profile_fields.tool_bundle`.
   Resolve executable symlinks and use their canonical absolute paths.
   Populate the complete source manifest for a source tree, or the binary digest
   and platform for binary access. Source and binary inputs become read-only
   copies in the selected lab; disposable working copies live under `/work`.
3. Pin each runtime/environment profile's final bytes into the scope. Pin the goal
   bytes. The scope's `issued_at` must be current or past; `expires_at` is optional.
   Renewable worker leases do not impose an overall engagement-age limit. Any selected
   total invocation and elapsed-parent worker-second caps apply across workers and
   recovery; omit them under `research-autonomy-v1` when none are intended.
4. Put the operator's **public** key and exact `operator_id` in `allowed_signers`.
   Add the hash of that file to the scope's `Operator allowed signers SHA256` line.
   Set `inputs.trusted_fingerprint` to the trusted key's SHA-256 fingerprint as
   lowercase hexadecimal, prefixed by `sha256:`. This differs from OpenSSH's
   displayed base64 fingerprint. Keep the private signing key outside input and
   engagement directories.
5. Review the final scope, mark its review checkbox, generate the challenge below,
   and sign it. A later edit
   to the scope, goal, profiles or pinned bytes requires a new reviewed signature.

These helpers hash public inputs without displaying their contents:

```sh
python3 - <<'PY'
import base64, subprocess, sys
from pathlib import Path
sys.path.insert(0, 'tools')
from engagement_contract import canonical, digest, source_manifest
print(digest(Path('/private/inputs/runtime-codex.json').read_bytes()))
print(digest(canonical(source_manifest(Path('/private/target-source')))))
fingerprint = subprocess.check_output(['ssh-keygen', '-lf', '/private/operator_key.pub',
                                      '-E', 'sha256']).decode().split()[1].split(':', 1)[1]
print('sha256:' + base64.b64decode(fingerprint + '=' * (-len(fingerprint) % 4)).hex())
PY
```

The signature covers the exact scope bytes through this canonical challenge:

```sh
python3 - <<'PY'
import json, re, sys
from pathlib import Path
sys.path.insert(0, 'tools')
from engagement_contract import canonical, digest
root = Path('/private/inputs')
scope_bytes = (root / 'scope.md').read_bytes()
scope = json.loads(re.search(r'```native-engagement-scope-v2\n(.*?)\n```',
                            scope_bytes.decode(), re.S).group(1))
(root / 'scope.challenge.json').write_bytes(canonical({
    'kind': 'native-engagement-scope-challenge-v2',
    'engagement_id': scope['engagement_id'], 'scope_sha256': digest(scope_bytes)}))
PY
ssh-keygen -Y sign -f /private/operator_key \
  -n llm-redteam-harness-native-engagement-v2 /private/inputs/scope.challenge.json
mv /private/inputs/scope.challenge.json.sig /private/inputs/scope.sig
chmod 600 /private/inputs/*
```

Provider credentials stay in the host environment or supported native credential
store. `env_NAME`, `codex_default` and `omp_default` are references, not secret
values. A reference must match the selected provider. Preflight checks local
presence/expiry without login, refresh, copying or printing the credential. It
does not prove that the provider will accept it. Target text and worker requests
cannot add credential references or widen signed authority.

## Bind target accounts by reference

For an application with signed `account_refs`, create a mode-600 reference file
outside the engagement directory, all worker workspaces, source/binary inputs and
runtime bundles. Set `OSLIT_ACCOUNT_BINDINGS` to its absolute path in the controller
host environment. The file contains environment-variable references, never values:

```json
{
  "kind": "target-account-bindings-v1",
  "bindings": [{
    "access_id": "app-main",
    "account_ref": "operator-account",
    "origin": "https://target.example.invalid:443",
    "headers": {"Authorization": "env_TARGET_ACCOUNT_AUTH"}
  }]
}
```

Supply `TARGET_ACCOUNT_AUTH` through the host's private environment. Its value is
the complete authorized header value. The name, access ID, account reference and
origin must match the reviewed configuration and signed scope. A configured
`Cookie` header can likewise reference a host variable. The host keeps cookie jars
separate by account and origin. Preflight checks presence and shape without target
contact; it does not prove the identity the target recognizes.

The worker selects a signed account using public `X-OSLit-Access` and
`X-OSLit-Account` request headers. Omitting the account selects anonymous access
and requires its own allowed effect. The target gateway strips these selectors,
adds credentials for that exact origin, rejects worker auth overrides and binds
each request observation to its account, effect, grant and environment. Provider
traffic uses a separate gateway. Known credential and cookie values reflected in
responses are withheld; this is not recognition of every possible transformed
secret. Retain the [account workflow's exact limits and receipts](../../evals/native-qualification/team-evidence/m3-target-accounts-20261114/README.md).
The [native-boundary integration](../../evals/native-qualification/team-evidence/m5-boundary-integration-20261114/README.md)
checks these bindings with the real controller and owned HTTP receivers while
native/container peers are simulated. Actual target identity and Docker/SSH
containment remain separate verification requirements.

## Capture effects and escalation

`engagement_capture` runs a pinned probe in a separate reserved lab over a nonempty
subset of the worker's resources. For source/binary-only capture, optional
`effect_id` selects a signed local execution effect; omission uses the initial
read effect unless the signed owned-lab-state class below requires a separate
`execute` effect. Setup requires exactly one account-free `read` effect at
`source_only` or `self` covering the selected resources and environment. Capture
with application resources rejects this local selector. Its target requests use
`X-OSLit-Effect` to select a signed effect; omission requires exactly one compatible
effect. The host strips that selector before forwarding.

An application capture without an owned reset profile records `clean_start:false`
and `remote_application_reset_unverified`. A fresh client lab does not reset the
application, so that capture alone cannot establish a clean independent remote replay.
Under historical policies it also cannot supply a required escalation predecessor. A source-only subset of
combined access can use its separately created local input as a clean start.
See the [capture evidence and limits](../../evals/native-qualification/team-evidence/m5-application-capture-20261114/README.md).

For a disposable application whose entire state belongs to the signed owner,
configure the optional [owned application reset contract](../research/oslit-application-reset-contract-2026-11-14.md).
Give this access a unique logical HTTP origin under `.invalid`; an owned clone
has its own access identity. Pin the complete baseline image in a separate target
environment profile, and pin an application profile containing its baseline ID,
absolute startup command and service port. Add the matching `application_states`
scope reference, `application_profiles` input path, `reset` permission and exact
reset effect. That effect requires cleanup rights and has no account selector.
Target HTTP effects and private account bindings remain separately required.

The status tool exposes signed names in `application_baselines`. The worker
requests this start through the existing capture tool, for example
`starting_state:{"app-main":"baseline-1"}`. Include every selected application;
combined access can select a source-only subset without this field. Each capture
creates a separate target container with no direct network, mounts or published
port. The existing target gateway reaches its exact container through a private
connector. A managed origin has no DNS fallback when its owner is unavailable.

The host records the baseline and exact target identity before the frozen probe
starts, then binds its target requests to that instance. A fresh reviewer needs
a new session, client lab and target instance with the same signed baseline.
Cleanup observes target absence; an uncertain cleanup holds the application until
recovery reads back the recorded owner. An unsupported reset request fails
explicitly. The first owner supports wholly disposable HTTP applications; existing
remote deployments, persistent volumes and external databases need another
qualified owner. This optional capability adds no reset authority to older scopes
and does not widen signed authority.

Run the local composition checks with
`python3 evals/native-qualification/smoke/check_application_reset_e2e.py --output /private/results/application-reset.json`.
They use actual HTTP, private relays and the signed journal with simulated native
and container peers. The separate opt-in
`check_application_owner_docker_e2e.py --endpoint unix:///... --image-id sha256:... --output /private/results/application-docker.json`
requires an already installed Python image and exercises the production owner.
Neither fixture is a fresh-target research acceptance test.

For preserved historical scopes, before a new `stored` or `cross_user` intent the controller requires an accepted
current escalation review of the independently confirmed preceding claim and
exact next signed effect. The frozen worker protocol describes the request and
review evidence. Reopened claims, superseded instruments or a replacement review
request invalidate the old transition's admission. Matching late observations
and owned cleanup remain recordable. Under `initial-scope-v1`, that agent review
is sufficient for the already signed rung; no operator approval is added. Artifact
creation uses the owned-state lifecycle below, not a generic network effect.
The [source capture workflow](../../evals/native-qualification/team-evidence/m5-capture-effects-20261114/README.md)
checks declared adjacent rungs using harmless local probes and simulated native,
container and reviewer behavior. It does not establish a security escalation.

For `research-autonomy-v1`, each effect instead checks its actual signed resources,
accounts, destinations, ownership and limits. Actual state dependencies still
matter to the experiment. Independent claim review evaluates the causal relevance
of controls and reproductions; different valid probe bytes or account conditions
need not match mechanically. The clean reproducer must be an actual distinct
worker/session, but need not be the final reviewer personally. Requested patch
review requires relevant actual original/patched evidence, not a universal matrix.

## Track explicitly signed disposable lab state

`owned-lab-state-v2` treats one owned tool/client lab and all its mutable state
as the artifact across source, binary, application and combined access. It includes native writes from their first
creation inside `/work`, `/tmp`, bounded shared memory and private IPC. It does
not classify content or register each generated file separately. Every content
type is covered inside the signed envelope, including contained Zone-2 artifacts.
`owned-lab-state-v1` retains its historical source/binary-only meaning.

The signed access needs `write` permission, plus a matching
`artifact_create` effect with `artifact_classes:["owned-lab-state-v2"]`,
`cleanup_required:true`, no accounts and a `source_only` or `self` rung. Keep the
separate setup `read` effect and execution `execute` effect. Main startup requires
one matching class effect. Capture may use `artifact_effect_id` to choose between
matching class effects; its existing `effect_id` selects execution. Creation-only
authority cannot start native tools or run a probe.

The host persists intent before allocation and checks actual Docker configuration
and every supported writable/kernel mount before native admission. Additional
mounts/devices, shared host namespaces and unsupported class selections refuse.
An application resource in this client-lab grant does not authorize remote mutation;
its network effects and owned target-state lifecycle require their own signed grants. Class workspace capacity must be a multiple of 4096 bytes. The
[contract](../research/oslit-v2-contract-2026-11-14.md#candidate-owned-lab-state-class)
records the precise storage bounds and exclusions.

Status exposes `lab_state_artifacts` with the instance count, pending cleanup and
retained evidence-object count. A ready instance may survive a specialist's next
related assignment. Final settlement and resource reconciliation require exact
container, staging container, prepared image and registered host capture staging
absence. A failed host cleanup remains held even when the container is gone.
Recovery uses the recorded owner, including intent-only preparation. Evidence
objects and published workspace copies remain retained; “clean” describes the
disposable instance. Run the [repeatable workflow](../../evals/native-qualification/OWNED-LAB-STATE-E2E.md)
to distinguish contained journal checks from actual Linux readback evidence.

## Inspect and run

From the pinned repository, inspect the fully signed input set:

```sh
python3 tools/native_engagement.py inspect --inputs /private/inputs/inputs.json
```

Resolve every reported `blocked_codes` entry. `ready_for_runtime_check` means the
signed bytes and local prerequisites passed. Version/platform handshakes, provider
acceptance, tool isolation, network routes and cleanup remain unverified until
actual execution readbacks establish them. The standalone equivalent is
`python3 tools/engagement_preflight.py --inputs /private/inputs/inputs.json`.

Start one foreground owner in a new private engagement directory:

```sh
python3 tools/native_engagement.py run --inputs /private/inputs/inputs.json \
  --engagement-root /private/engagements/example
```

The controller freezes the contract, methodology and worker protocol at
initialization and owns the append-only engagement journal. Native runtimes own
conversation state. An eligible specialist can keep its live session, workspace
and resource ownership for the next ready task with the same resources and
runtime authority after a completed invocation, idle native readback and no
pending or unknown target/tool executions or auxiliary captures. The same owned
native-tool and proxy services remain active.
This reuse supplies no cleanup or clean-replay claim. Reviewers start fresh;
incompatible work, failed readback and controller recovery use cleanup and
reconstruction from published records and frozen inputs. The
[retention evidence](../../evals/native-qualification/team-evidence/m2-retained-specialists-20261114/README.md)
separates actual Codex/OMP continuity with fake provider replies from the simulated
controller transition. Later [joined Docker results](../research/oslit-implementation-assembly-2026-11-15.md#signed-codex-integration-and-repeated-turn-repair)
verify two retained native invocations. Ordinary model-turn
completion does not finish an engagement. The lead can continue, create tasks and request allowed
specialists. Confirmation requires an observed effect,
a relevant control and clean independent reproduction. Broad work also needs an
honest account of remaining paths and coverage limits.

Use another terminal for read-only status or a signed-scope-compatible direction:

```sh
python3 tools/native_engagement.py status --engagement-root /private/engagements/example
python3 tools/native_engagement.py direction --engagement-root /private/engagements/example \
  --file /private/operator-direction.md
```

Directions record operator steering and do not expand authority. Status summaries
are bounded; use `--since CURSOR --limit N` and the returned `next_cursor`/`has_more`
for subsequent update pages. Worker status/claim/submit endpoints are assigned by
the host; a claimed role or native session ID is not authentication.

Search the shared board without changing work:

```sh
python3 tools/native_engagement.py status --engagement-root /private/engagements/example \
  --view board --query parser --kind publication --kind claim --limit 20
```

Use `--since` with the returned board cursor and the same filters for stable
snapshot pagination. Agents use `engagement_status` with `view:board` and can send
typed `team_message` submissions. Relevant peer updates are delivered through
native steering; durable acknowledgments recover missed updates after restart.
The board retains source references and review state, and export includes it.

## Active knowledge and native helpers

`engagement_knowledge` searches, reads exact versions, fetches permitted public
sources, publishes experimental procedures and records independent evaluations.
Read the [library guide](knowledge-library.md) for retention gaps, helper files,
applicability and narrowed/withdrawn status. A source above the evidence-object
limit is retained as a file and read in bounded parts. The optional signed
`reference_web` grant is separate from target and provider access; its template is
in the [input examples](../../examples/native-engagement-v2/README.md).

`engagement_helper` exposes spawn/read/steer/stop for native children under their
authenticated parent. Their permissions, resource ownership and total limits come
from that parent. They are not independent reviewers or separate controller workers.
Parent revocation stops descendants. Use a fresh controller reviewer for independent
claim or technique evaluation. Optional technique evaluation never blocks closure.
The adapter creates native Codex threads in the parent's app-server and native OMP
RPC sessions with the same protected host tools. It does not enable the upstream
spawn/task tool UI; those paths do not provide the required inherited tool binding.

For a new Linux autonomy run, rebuild the model image with the current
`install_native_tools.py model-image-context` output and pin its actual image ID.
The updated bootstrap supports isolated helper session state. Startup verifies its
bytes and refuses an incompatible old image. Existing no-helper scopes retain
support for their exact original bootstrap; their signatures are not rewritten.

After lost context, status supplies current orientation alongside durable notes and
source links. An acknowledged notice may need rereading in the replacement context;
its earlier acknowledgment does not establish current understanding. Adapter-owned
request identities and exact retries keep transport chores out of research notes.

## Stop, recover and export

```sh
python3 tools/native_engagement.py stop --engagement-root /private/engagements/example
python3 tools/native_engagement.py status --engagement-root /private/engagements/example
python3 tools/native_engagement.py resume --engagement-root /private/engagements/example
python3 tools/native_engagement.py export --engagement-root /private/engagements/example \
  --output /private/results/example-export
```

`stop` records revocation, then attempts owned recovery under the runner lock.
When the active owner still holds that lock, the command reports `stopping` with
`runner_stop_pending`; that owner remains responsible for shutdown. Read status
for cleanup and unresolved resource holds. A terminal authority status alone is
not proof that owned processes/resources are gone. After host/process loss,
`resume` reconciles retained owner/environment receipts before admitting new work.
Unknown effects retain their reservations and block redispatch until reconciled.
An operator stop does not authorize restarting research; resume can finish recovery
and cleanup under the retained terminal authority. A new investigation needs its
own appropriate signed input. Preserve the original engagement directory and
historical events. Historical v2 records without frozen guidance remain readable
and stoppable, but cannot resume active research by silently using today's files.

Export requires a new output directory and takes a snapshot at one journal
revision. `manifest.json` has kind `engagement-result-bundle-v2` and a SHA-256 digest
for every exported file. `contract/` contains the frozen scope/signature, goal,
profiles and input manifests; `events/` preserves the ordered journal; `objects/`
contains referenced evidence/receipts. The engagement-local `knowledge/` archive
contains selected retained source/package versions; delivery records identify
retention gaps instead of implying a complete archive. `result.json` includes per-claim acceptance,
tasks, experiments, reviews, patches, closure/coverage obligations, directions,
usage completeness, cleanup and resource holds. Its `research_guidance` map pins
`contract/methodology.md` and `contract/protocol.md`. Give a native comparison the
exported portable `methodology.md`; the protocol file contains OSLit-specific
worker operations. Inspect those states before
calling the result complete. Export neither grants external-action authority nor
publishes a report.

Check the bundle using the [byte-integrity guide](engagement-export-integrity.md)
and [reference and result verification guide](export-reference-verification.md).
These checks establish exported-byte and journal consistency, not signer identity
or research acceptance.

The operator owns the future fresh-target acceptance test and comparison with a
capable native agent. Engineering fixtures, local runtime controls, live provider
behavior and research acceptance must remain distinct in every status report.

## Linux service template — not yet verified

This uninstalled example requires a signed Linux `model_host` profile and passing
preflight. A profile without that field still requires the Darwin boundary. The
service itself and sustained recovery remain unverified; it cannot substitute for
the foreground startup, revocation and recovery checks. A standard service manager
can own the same foreground `resume` command:

```ini
[Unit]
Description=OSLit signed engagement owner
After=network-online.target

[Service]
Type=simple
User=oslit
WorkingDirectory=/opt/oslit/PINNED_REVISION
UMask=0077
ExecStart=/opt/oslit/venv/bin/python tools/native_engagement.py resume --engagement-root /var/lib/oslit/engagements/example
Restart=on-failure
RestartSec=30
KillMode=control-group
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
```

The service user must already own the appropriate private state and credential
references. A restart preserves the same signed scope and remaining aggregate
budget. It cannot clear a hold, extend expiry or reverse an operator stop.
