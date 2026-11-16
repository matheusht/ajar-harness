# Codex external-authentication ordering

The production fix keeps the executor connection alive after native external-token
login. Live startup still stops at a separate Linux sandbox namespace prerequisite
in the macOS Docker lab. No model turn ran, no containment rule was weakened, and
both runs verified cleanup.

Failure-first scenario: create a fresh signed owned source fixture; start the pinned
Codex 0.166.0 app-server and separate Docker executor; verify effective configuration;
authenticate with the available native binding; request a new thread. Record only
operation names, peer exit status, readiness and static transport failure metadata.

- [Before](before.json): environment/info established a ready executor. After
  account/login/start, the bridge exited 0 before thread/start, with
  `to_executor/read/eof`. The thread request timed out. The original ordering
  registered the executor before external authentication.
- [After](after.json): the actual changed production constructor validates effective
  configuration before login, then registers and reads back the executor. Both
  peers stayed alive with no transport failure through thread/start. The request
  reached the filesystem sandbox and returned a `bwrap` namespace permission
  refusal. That remaining prerequisite is explicit; this is not live-model proof.

An isolated constructor-order experiment preceded the production change. The after
receipt uses the production module without that experimental replacement. The
original private receipts remain unchanged; these byte-identical copies passed the
publication credential scanner. Their source hashes identify dirty working-tree
code precisely; the base commit alone does not identify the repair.

| Receipt | Receipt SHA-256 | Runtime source SHA-256 |
| --- | --- | --- |
| before | `ed0077f4bf042c1c652f44818d6939d5d05c1a15cd3d1a74d2c67132e1c5e1a3` | `sha256:5272d5dad2e17b61f3b4da6da5dda506c37de73fc1e885aa7e672aca3d94f201` |
| after | `8e0ffa068fba15901095ac24accc4c54cc326d09244e1f44bbad1b6204c725f4` | `sha256:e12bea93ac61a5b91bc0a7cdc5eb185c3ff682e60ddf80a91804d161aebc3d50` |

## Repeat the owned scenario

Requirements: macOS, the pinned repository Python dependencies, Docker Desktop,
pinned Codex 0.166.0 and generated protocol schema, the prepared Linux tool bundle
and Python base image, and the operator's available native Codex credential binding.
The private scenario uses the prepared paths under
`/private/tmp/oslit-autonomy-e2e-20261116`. It generates a new signing key and owned
inputs; credential values remain inside the resolver/model boundary and are never
written to the receipt. Do not upload native credentials to hosted CI.

The following command preserves existing evidence and executes a fresh copy of the
after scenario against the current source:

```sh
/private/tmp/oslit-autonomy-e2e-20261116/venv/bin/python - <<'PY'
from pathlib import Path
import subprocess, sys, uuid
base = Path('/private/tmp/oslit-autonomy-e2e-20261116')
original = base / 'codex-threadstart-diagnostic-4.py'
name = 'codex-threadstart-diagnostic-' + uuid.uuid4().hex
replay = base / (name + '.py')
replay.write_text(original.read_text().replace('codex-threadstart-diagnostic-4', name))
subprocess.run([sys.executable, str(replay), 'codex'], check=True)
PY
```

Expected in the observed Mac environment: authentication precedes executor
registration, both peers remain live through thread/start, the tool sandbox refuses
its unavailable namespace, no model turn occurs, and cleanup is verified. Overall
status remains failed because the namespace prerequisite is unresolved. The receipt
includes scenario/source digests and bounded diagnostics. Two HTTP 200 responses
show provider traffic, not successful model execution. The hosted Linux signed tool
policy exercises a separate environment.
