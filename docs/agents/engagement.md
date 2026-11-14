# Operate a candidate v2 engagement

Use this guide for the versioned Codex/OMP engagement route. It is candidate
implementation work: local checks, packaging and preflight do not establish
qualification, adoption or research success. Existing native/legacy records keep
their original contract. The signed scope defines authority; repository access and
these instructions grant none.
The field and authority contract is recorded in [Decision 0014](../decisions/0014-native-engagement-team.md).
Read the [dated delivery state](../wiki/oslit-v2-delivery-2026-11-14.md) before
claiming support or readiness. The complete M0–M6 engineering assignment remains
unfinished. The repository impact-artifact and escalation-review gates still
apply: a signed ceiling does not supply fresh artifact confirmation, an artifact
cleanup ledger or review of the preceding escalation rung.

## Prepare the host and tool lab

Pin the repository revision and use a private, durable engagement directory. Keep
the host awake during a run. The current protected model owner uses macOS
`sandbox-exec` and Darwin process birth identity. Linux host ownership is blocked;
a Linux tool container is a different process boundary.

Runtime prerequisites are Python 3.11+ with its standard library, OpenSSH
`ssh-keygen` for local signature verification, OpenSSL for private proxy trust,
the selected pinned native CLI, and its signed config/protocol schema. Codex
0.166.0 also uses host Bun for its private executor bridge. OMP 18.20.0 uses the
pinned Linux SDK bundle with Bun 1.4.4. Preserve the reviewed
`engine/native-engagement-method.md` and `engine/native-engagement-protocol.md`
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

## Fill and sign the inputs

1. Copy the [source, binary, application or combined template](../../examples/native-engagement-v2/README.md)
   into a private directory. Replace every `REPLACE_` value, including the actual
   goal, resource budgets, selected model, access identities and absolute paths.
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
   Renewable worker leases do not impose an overall engagement-age limit. Aggregate
   invocation and worker-second budgets still apply across workers and recovery.
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
conversation state during an active worker session. A later task or recovered
worker reconstructs context from the published journal and frozen inputs; exact
native conversation continuity across tasks is not established. Ordinary model-turn
completion does not finish an engagement. The lead can continue, create tasks and request allowed
specialists; reviews use fresh context. Confirmation requires an observed effect,
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
contains referenced evidence/receipts. `result.json` includes per-claim acceptance,
tasks, experiments, reviews, patches, closure/coverage obligations, directions,
usage completeness, cleanup and resource holds. Its `research_guidance` map pins
`contract/methodology.md` and `contract/protocol.md`. Give a native comparison the
exported portable `methodology.md`; the protocol file contains OSLit-specific
worker operations. Inspect those states before
calling the result complete. Export neither grants external-action authority nor
publishes a report.

The operator owns the future fresh-target acceptance test and comparison with a
capable native agent. Engineering fixtures, local runtime controls, live provider
behavior and research acceptance must remain distinct in every status report.

## Linux service template — currently blocked

This is an uninstalled example for the future supported Linux host owner. Current
preflight reports `native_model_boundary_unsupported` on Linux; do not enable this
unit as a workaround. Once that boundary and sustained recovery are verified, a
standard service manager can own the same foreground `resume` command:

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
