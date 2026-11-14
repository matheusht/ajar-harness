# Linux model owner workflow

This scenario is defined before implementation. The optional signed runtime
profile selects a separate local Docker model owner. The existing lab remains the
only target/tool environment. The new owner privately reuses `Environment` for
creation, immutable public config/CA inputs, leases and cleanup. Model credentials
cross a bounded private stdin bootstrap only. Darwin v1 records retain their
original recovery contract.

Run the contained checks:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 evals/native-qualification/smoke/check_linux_model_host_e2e.py --output /tmp/linux-model-host.json
```

Requires Python 3.11 or later and `ssh-keygen`. It uses signed disposable input, the actual
controller journal, controlled native protocol subprocesses and a private
bootstrap subprocess with fixture paths. Docker, host namespace observations and
native model inference are simulated or absent. A green result is not Linux
containment or provider qualification.

The failure scenarios are:

1. A signed optional model profile freezes exactly; unknown keys, remote daemon,
   missing daemon/image pin, root model UID and unbounded limits reject. Changing
   it after signing rejects. A Darwin profile without the field keeps its meaning.
2. Ownership is durable before any container effect. Exact null identities may
   become observed identities; existing identities and dispatch bindings never
   change. A running owner has a host PID namespace and cgroup identity. Active
   duplicate receipt is idempotent. Missing or uncertain owner never refunds setup.
3. Bootstrap rejects malformed/oversized/truncated frames, changed model/config
   bytes, unsafe environment names and symlinked state. It consumes exactly one
   private frame, preserves the following native message, and never writes the
   synthetic credential to argv, config, files, stdout or stderr.
4. Codex and OMP use explicit container executable/config/state/cwd paths through
   the existing Transport launcher. Host pins still verify. Credential values do
   not enter the public launch environment or Docker arguments. Fresh/live-resume
   identity and terminal events retain existing semantics.
5. The composed boundary checks image/helper identity before resolving a
   credential. Model provider traffic crosses a separate stdio ProxyBridge into
   the provider gate. No host socket or target path enters the model container.
   Both owners renew; stop closes gates and verifies both owners. Failed model
   cleanup holds the resources.
6. Reopened recovery validates the exact signed profile, host/boot, daemon,
   container, PID-start/namespace and cgroup identity. A missing daemon, changed
   identity or uncertain creation stays held. Recovery does not launch a model or
   resolve credentials. Cleanup is idempotent and preserves unrelated resources.
7. OMP's optional `model_catalog: {path, sha256}` is signed with its runtime
   profile and frozen as `runtimes/<profile-id>.models.yml`. Reopened work uses
   those frozen bytes. Changed files, literal secrets, unsupported runtime kinds
   and extra catalog fields reject. Linux stages the catalog only in the private
   model input, and bootstrap copies the pinned file to `/work/.model/models.yml`.
   Native host OMP uses the same optional catalog in its private state directory.
   Changed or symlinked state catalogs reject before native startup.

A separate hosted scenario must run the production owner against actual local
Linux Docker and actual pinned Codex/OMP distributions. It must retain source and
image pins, sanitized inspect output, namespace/cgroup facts, model/provider/tool
route probes, synthetic credential canary results, fresh/resume control,
controller/attach/watcher loss, detached descendants, lease expiry, receipt-based
cleanup and cleanup readback. No live provider or target is required for that
engineering scenario. Those hosted results remain distinct from the contained
checks and from fresh-target research or multi-day operation.
