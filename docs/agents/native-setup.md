# Bounded native source setup

Use this route for a **new, authorized source** before a target runtime recipe
exists. It ends with an agent proposal for host review. The source stays
read-only at `/source`; the agent's `/workspace` is a disposable tmpfs with a
fixed byte limit. The setup container joins only the internal research network
and reaches the existing metered model relay. No target executor is created.
The operator owns the signing key, the scope, the setup approval, the pinned
image and the run root. The agent cannot approve its own turn.

## 1. Sign the scope

Keep the key and all signature material outside the source and run root. Use an
operator key already trusted by the host; the following commands show the
format with placeholders. The key's public fingerprint is supplied independently
to `prepare`, not read from the proposed scope.

Create an `allowed_signers` file containing exactly the operator identity and
their SSH public key, for example `matheus ssh-ed25519 AAAA...`. Put its exact
SHA256 in the target-local `scope.md` and include one fenced setup section:

````text
- Operator allowed signers SHA256: sha256:<allowed-signers-hex-sha256>

```native-setup-scope-v1
{
  "kind": "native-setup-scope-v1",
  "engagement_id": "ID",
  "operator_id": "matheus",
  "source_manifest_sha256": "<manifest-hex-sha256>",
  "goal_sha256": "<brief-hex-sha256>",
  "surfaces": ["owned original source tree for this engagement"],
  "benign_objectives": ["propose an offline runtime recipe and initial threat model"],
  "escalation_ceiling": "setup_only",
  "impact_demo_authorized": false,
  "accounts": [],
  "cleanup": "Stop and remove every owned setup container and network.",
  "effect_class": "read-only-original-and-disposable-offline-proposal",
  "network_class": "metered-model-relay-only",
  "expires_at": "<UTC date/time no later than the operator grant>"
}
```
````

The host computes the source manifest from regular files in the authorized
export and binds its digest in this signed section. `accounts: []` means the
setup uses no target accounts. Name every actual source surface and benign
objective; replace all sample text before signing.

```sh
python3 tools/native_research.py setup-source-manifest \
  --source /absolute/source > /private/setup-source-manifest.json
shasum -a 256 /private/setup-goal.md
```

Copy `source_manifest_sha256` from that JSON and the brief's hex SHA256 into
the signed scope block. This identity pass does not execute source code. The
runner checks the declared source and goal hashes, expiry, and detached
signature before its preparation inventory. Generate the canonical challenge
for the exact scope bytes:

```sh
PYTHONPATH=tools python3 - <<'PY' > /private/setup-scope.challenge
from pathlib import Path
from engagement_records import canonical_json_bytes
import hashlib, sys
scope = Path('/absolute/target/engagements/ID/scope.md')
sys.stdout.buffer.write(canonical_json_bytes({
    'kind': 'native-setup-scope-challenge-v1',
    'engagement_id': 'ID',
    'scope_sha256': hashlib.sha256(scope.read_bytes()).hexdigest()}))
PY
ssh-keygen -Y sign -f /private/operator_key \
  -n llm-redteam-harness-native-setup-v1 \
  < /private/setup-scope.challenge > /private/setup-scope.sig
```

Convert the **independently trusted** public key's SSH fingerprint to the
hex format accepted by `prepare`. The fingerprint must be `sha256:<64 hex>`.
For the public key already authorized by the operator:

```sh
python3 - <<'PY'
import base64, subprocess
value = subprocess.check_output([
    'ssh-keygen', '-lf', '/private/operator_key.pub', '-E', 'sha256'], text=True)
encoded = value.split('SHA256:', 1)[1].split()[0]
print('sha256:' + base64.b64decode(encoded + '=' * (-len(encoded) % 4)).hex())
PY
```

Compare that output with the trusted fingerprint obtained outside the source
tree before passing it to `prepare`.
Completion check: `prepare` below verifies the exact scope signature, allowed
signers pin, and trusted fingerprint before making a run root.

## 2. Prepare the setup run

Use a private run root outside the source and engagement tree. Obtain a pinned
Linux OpenCode image with the version and environment required by
`tools/native_research.py`, a matching relay binary, and a public TLS trust
file. Read `prepare --help` for current defaults and limits. Example:

```sh
python3 tools/native_research.py prepare --setup-only \
  --run-root /private/setup-run --source /absolute/source \
  --brief /private/setup-goal.md \
  --scope-file /absolute/target/engagements/ID/scope.md \
  --scope-sha256 <scope-hex-sha256> \
  --setup-engagement-id ID --setup-operator-id matheus \
  --setup-scope-signature /private/setup-scope.sig \
  --setup-allowed-signers /private/allowed_signers \
  --setup-trusted-fingerprint sha256:<trusted-key-hex-sha256> \
  --relay /private/relay --relay-sha256 <relay-hex-sha256> \
  --runtime-ca /private/ca.pem --runtime-ca-sha256 <ca-hex-sha256> \
  --image-id sha256:<pinned-image-id> --platform linux/amd64 \
  --max-connections 2 --max-bytes 1048576 --duration-seconds 120 \
  --setup-max-workspace-bytes 67108864
```

`prepare` freezes at most 10,000 regular source files and 128 MiB; changed,
added, removed, or symlinked files fail the pin check. It records the plan but
starts no model, network, or container. Inspect `plan.json` and the source
manifest. Completion check: the plan's `setup_only` section names the exact
authority, effect class, network class, workspace cap and source pins.

## 3. Approve that exact plan

The human operator reviews the plan and writes a **separate** setup approval.
Generate an unsigned template with explicit UTC times, no more than 24 hours
apart:

```sh
python3 tools/native_research.py setup-approval-template \
  --run-root /private/setup-run \
  --approved-at 2026-11-12T19:00:00Z \
  --expires-at 2026-11-12T20:00:00Z \
  > /private/setup-approval-unsigned.json
```

The template includes `monetary_cap_usd: null`. A requested monetary cap
cannot be enforced by this provider boundary and `start` rejects it. If the
operator requires a monetary cap, stop before dispatch.

For an owner-loss continuation, sign a v2 linked-epoch grant instead of v1.
Choose an absolute UTC deadline no later than both the approval expiry and
`approved_at + duration_seconds`. The signed v2 grant binds the initial run
root and plan, original connection and byte ceilings, source, scope, goal,
image, model route, relay, trust material, and setup effect and network classes.
It permits only checked successor epochs under residual allowance; it does not
authorize a target build.

```sh
python3 tools/native_research.py setup-approval-template \
  --run-root /private/setup-run \
  --approved-at 2026-11-12T19:00:00Z \
  --expires-at 2026-11-12T20:00:00Z \
  --linked-epochs --absolute-deadline 2026-11-12T19:02:00Z \
  > /private/setup-approval-unsigned.json
```

Sign and attach the v2 template with the same commands below. A v1 approval
remains a single-run grant.

Sign the canonical unsigned JSON and attach its proof. The signing key remains
outside the harness. `allowed_signers` is the same file pinned in the scope.

```sh
PYTHONPATH=tools python3 - <<'PY' > /private/setup-approval.challenge
from pathlib import Path
from engagement_records import canonical_json_bytes
import json, sys
value = json.loads(Path('/private/setup-approval-unsigned.json').read_text())
sys.stdout.buffer.write(canonical_json_bytes(value))
PY
ssh-keygen -Y sign -f /private/operator_key \
  -n llm-redteam-harness-native-setup-v1 \
  < /private/setup-approval.challenge > /private/setup-approval.sig
PYTHONPATH=tools python3 - <<'PY'
from pathlib import Path
from operator_signature import encode_operator_signature_proof
import json
unsigned = json.loads(Path('/private/setup-approval-unsigned.json').read_text())
challenge = Path('/private/setup-approval.challenge').read_bytes()
unsigned['operator_signature'] = encode_operator_signature_proof(
    challenge_bytes=challenge,
    signature_bytes=Path('/private/setup-approval.sig').read_bytes(),
    allowed_signers_bytes=Path('/private/allowed_signers').read_bytes(),
    signer_fingerprint='sha256:<trusted-key-hex-sha256>')
Path('/private/setup-approval.json').write_text(json.dumps(unsigned, sort_keys=True) + '\n')
PY
```

Completion check: `start` verifies the exact signed approval, expiry, source,
scope, model route, relay, trust material, effect class and fixed allowance
before any Docker call. It archives the proof outside agent write access.

## 4. Run, freeze, stop

Keep `start` in a foreground terminal. It owns the provider relay and cleanup.
Use a second terminal for the bounded turn. A paid model route also needs the
host-only provider key and TLS key flags described by `start --help`.

```sh
python3 tools/native_research.py start --run-root /private/setup-run \
  --approval /private/setup-approval.json
python3 tools/native_research.py setup-turn --run-root /private/setup-run
python3 tools/native_research.py setup-freeze --run-root /private/setup-run
python3 tools/native_research.py stop --run-root /private/setup-run
python3 tools/native_research.py status --run-root /private/setup-run
```

The agent writes `recipe.json` and `THREAT_MODEL.md` in its bounded workspace.
The host freezes only these two validated files, the native event trace hash,
approval, source pins, dispatch receipt, and remaining connection/byte/time
allowance under `controls/setup-output/`. `setup-freeze` stages bytes first;
a missing or invalid proposal remains in `controls/setup-staging/` and can be
revised with `setup-resume` on the same active run. After `setup-freeze` commits
the host receipt, further setup turns are refused; a revised proposal needs a
separate reviewed protocol. The frozen proposal is not
an executed build or security result. Complete only when `status` reports a
stopped run with `final.cleanup.status=complete`, exact absent resource IDs,
and a pinned setup output receipt. If cleanup is unresolved, retain the run
root and reconcile owned resources before another setup run.

An acknowledged turn may use `setup-resume --session <session-id> --prompt-file
/private/prompt.md` while the same run and allowance are active. An unknown
dispatch remains blocked and must not be retried automatically. Under a v2
grant, each acknowledged turn freezes the bounded proposal files and a
checkpoint receipt under `controls/setup-checkpoints/<dispatch-id>/`, outside
agent write access.

If a v2 run loses its foreground owner, run `recover-start` after the native
stop owner has recorded `REVOKED`. Inspect its exact resource cleanup and the
provider ledger. Then prepare one successor root:

```sh
python3 tools/native_research.py recover-start --run-root /private/setup-run
python3 tools/native_research.py setup-next-epoch \
  --run-root /private/setup-run --next-run-root /private/setup-run-2
python3 tools/native_research.py start --run-root /private/setup-run-2 \
  --approval /private/setup-approval.json
python3 tools/native_research.py setup-turn --run-root /private/setup-run-2
```

`setup-next-epoch` requires the exact stopped producer proof, absent owned
containers and networks, a settled provider ledger, no unknown dispatch, and
the last acknowledged host checkpoint. It reserves remaining connections and
bytes and keeps the original absolute deadline. The successor has a fresh
native store and session; the agent reconstructs its proposal from a read-only
checkpoint at `/research/setup-checkpoint/`. It does not restore the previous
model conversation. A failed check leaves the old run blocked for operator
reconciliation. A crash after preparing a successor but before the predecessor
marker leaves an inert root that cannot start; inspect and remove it only after
confirming it created no resources. The v1 approval cannot authorize a linked
epoch.

## Local evidence boundary

Run `PYTHONDONTWRITEBYTECODE=1 python3
evals/native-qualification/smoke/check_native_setup_e2e.py --output
/tmp/native-setup-e2e.json` to repeat the synthetic signed-authority and local
Docker boundary checks. That scenario uses a Docker shim for the public setup
approval path and an already-local BusyBox image for source read-only, tmpfs,
network-none and cleanup readback. It does not execute a native model turn or
qualify a live provider. A fresh target requires its own signed scope, images,
approval, effect review and cleanup proof.

The linked-epoch CLI scenario is:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 \
  evals/native-qualification/smoke/check_native_setup_epoch.py \
  --output /tmp/native-setup-epoch-e2e.json
```

It uses synthetic signed authority, fabricated stop and provider receipts,
and a Docker absence shim. It checks the successor's original pins, residual
caps, checkpoint, empty native store, and ancestor path exclusion. It does not prove live owner loss,
model reconstruction, provider billing or production cleanup. A saved 21-check
result is at
`evals/native-qualification/setup-evidence/native-setup-linked-epoch-synthetic-e2e.json`.

After the final proposal is frozen and its run has stopped, the host can
prepare an offline runtime with `tools/native_setup_builder.py`. Its separate
signed build authority, catalog format, public scenario and evidence limits are
documented in
[`SETUP-BUILDER-E2E.md`](../../evals/native-qualification/SETUP-BUILDER-E2E.md).
The checked build is still not a research approval or security result.
