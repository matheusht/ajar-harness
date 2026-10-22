# Legacy Docker work-queue backend

This is the explicit legacy queue procedure for existing engagements and supported workflows.
New local source research in this candidate implementation uses `tools/native_research.py` and the
[native local research procedure](native-local-research.md). Preparing that source route does not
record a scoped adopt decision or verify the final native E2E.

The legacy public work-queue CLI runs every queue session in an explicit Docker boundary. It has no
implicit host-process fallback. The parent driver continues to own queue reduction, action
admission, record writes, and cleanup; the container owns only one bounded model session and its
descendants.

## Supported host contract

The backend currently supports one fail-closed host profile:

- non-root Darwin on Apple Silicon;
- a local Unix-socket Docker endpoint owned by root or the invoking user;
- a Docker Desktop Linux/arm64 engine with cgroup v2;
- memory, swap, and PID limits enabled;
- the built-in seccomp profile enabled; and
- live restore disabled, so a daemon restart cannot intentionally preserve the session.

Every one of those properties is checked before a model process starts. Intel macOS, Linux hosts,
remote Docker endpoints, root invocation, a mismatched engine architecture, or a Docker daemon that
does not expose the required controls returns a sanitized preflight error. Do not weaken the check
or add a host fallback to make an unsupported machine run. Qualify a new backend separately.

## Image contract

`--docker-image` must be an immutable `repository@sha256:<64 lowercase hex>` reference with no tag.
The exact image must already be present in the local Docker image store, and its inspected
`RepoDigests`, OS, and architecture must match the request. The runtime always uses `--pull never`;
it never pulls or builds an image as part of queue execution.

Image acquisition is an explicit operator preparation step outside the queue run. The image must
contain both:

- the Claude executable named by the absolute `--claude-executable` container path; and
- a Python interpreter named by the absolute `--docker-python-executable` container path.

The latter runs the harness-owned PID-1 supervisor, action client, and Stop hook from the read-only
`/harness` mount. Pin and review the image that supplies those runtimes. A digest pin proves byte
identity, not provenance or trust by itself.

## Mount and lifecycle boundary

The driver creates a uniquely named bridge network and a stopped container, then inspects both
before admitting any action. It binds only operator-supplied canonical paths:

| Host source | Container path | Access |
| --- | --- | --- |
| the exact target repository passed as `--workspace` | `/workspace` | read-only |
| this portable harness checkout | `/harness` | read-only |
| each repeated regular-file `--read-only-input`, in argument order | `/inputs/000`, `/inputs/001`, ... | read-only |
| one private per-session control directory | `/run/lrh-control` | read-only after preparation |

The target is mounted directly from its own repository. It is not copied into this harness, placed
under a central target directory, or discovered by scanning. Optional inputs are regular files only;
directories and special files (including Unix sockets, devices, and FIFOs) are rejected so a
read-only bind cannot smuggle ambient authority or another workspace tree into the container.
Overlapping target/harness mounts, same-inode aliases, symlinks, duplicate inputs, and non-canonical
paths fail before activation.

The container has a read-only root filesystem, no added devices or published ports,
`no-new-privileges`, private cgroup and IPC namespaces, finite memory/CPU/PID/open-file limits, no
core dumps, no restart policy, and no Docker log driver. It runs as the invoking non-root uid/gid.
The trusted supervisor profile uses `--cap-drop ALL --cap-add SYS_PTRACE`; this exact HostConfig
selector makes Docker's built-in seccomp profile admit `pidfd_getfd` and `process_vm_readv`. It does
not give the non-root processes a usable capability: before reading session or authentication
material, PID 1 requires `CapInh`, `CapPrm`, `CapEff`, and `CapAmb` all to be zero and
`NoNewPrivs` to be one, and the trace child repeats that check before installing its filter. A
generic direct-entrypoint runtime does not receive the selector. The supervisor profile also
rejects a Python executable under the target, harness, control, input, or writable tmpfs mounts.

A parent-lifetime watchdog owns the exact container and network IDs plus a random ownership nonce.
Normal completion, timeout, interrupt, parent death, or a failed activation removes only those
exact resources. No same-uid process scan or broad Docker cleanup is used.

PID 1 is `tools/container_session_supervisor.py`. The model is its child. Exiting PID 1 causes the
container runtime to terminate every remaining descendant even if one closes descriptors,
double-forks, calls `setsid`, changes cwd, or execs another program.

## Bootstrap, broker, and Stop flow

Preparation and activation are deliberately two phase:

1. The parent creates the private network and stopped container and revalidates their exact IDs,
   labels, mounts, limits, image, and immutable configuration digest.
2. The parent writes a bounded canonical `session.json` and broker manifest into the private control
   directory. The SHA-256 of the exact session bytes is already bound into the container argv.
3. The parent starts an action broker bound to the exact container ID, configuration digest,
   engagement inode, reducer state, admitted action, and deadlines.
4. Under the target-local record lock, the parent binds the action admission to that same container
   identity. Only then may the stopped container start.
5. Model authentication and the fresh 32-byte broker session key are delivered once to PID 1 over
   bounded stdin. They are not placed in Docker argv, Docker environment, the control directory, or
   Docker logs.

PID 1 keeps the broker key in hardened process memory and exposes a bounded Unix relay at
`/scratch/.lrh-broker.sock`. The model-side client can request only the typed `action` and
`session_end_check` operations. PID 1 validates the semantic request, signs the exact canonical
frame, and sends it over the per-session network to the host broker. The host verifies HMAC,
nonce/replay state, deadlines, container identity, admission, exact inline files and digests, and
the target-local state before it executes anything. A model cannot gain host path authority by
putting a path in a broker request.

Queue sessions opt in through driver-generated `--settings`; repository `.claude/settings.json`
does not automatically register the queue Stop hook. The native entry route does not need queue
selection, a queue reviewer-model pool, or queue-draining Stop continuation. Global user and target
project settings are outside this repository change.

The legacy host compatibility path still uses `load_stop_hook_settings()` and
`claude-stop-hook.py --print-additional-settings` to generate absolute hook paths. The public
Docker path uses `_container_stop_hook_settings()` to register only its top-level `Stop` hook:
inside the container it runs:

```text
<docker-python> /harness/tools/container_broker_client.py stop-hook
```

The hook derives opaque session and delivery references from Claude's bounded stdin, sends
`session_end_check` through the same PID-1 relay, and returns only the broker's bounded response.
Malformed or unavailable Stop input uses Claude's fail-open `{}` response without printing broker
or credential details. Queue truth and action consumption remain parent-owned; the Stop hook is only
the session-end backstop.

The child receives only `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`,
`CLAUDE_CODE_OAUTH_TOKEN`, and `ANTHROPIC_BASE_URL` when the operator has set them, plus bounded
runtime and ledger-binding variables. Host Git, SSH, operator-signing, Docker, and unrelated
environment authority are not forwarded. The session bridge permits general outbound network access
because Claude Code needs provider egress; it is not endpoint-allowlisted to Anthropic. Container
teardown removes that process and network authority, but it cannot undo a credential or data
disclosure that occurred before teardown and does not revoke the upstream token. Use appropriately
scoped, short-lived provider credentials.

## Aggregate storage boundary

Both writable filesystems are tmpfs and have independent hard byte and inode limits:

- `/scratch`: Claude state, temporary files, and the local broker relay;
- `/dev/shm`: shared memory, mounted `noexec`.

The supervisor checks free blocks and inodes before launch and at exit. During execution it traces
every synchronous syscall boundary from the complete model descendant tree. Other syscalls that
return `ENOSPC` or `EDQUOT`, plus `SIGBUS`, remain conservatively latched.

Scalar `write` and `pwrite64` use a narrower kernel-mediated path. The trace child installs an
inherited seccomp user-notification filter and hands its only listener to PID 1 before model exec.
For each request, PID 1 validates the notification ID, opens a thread-scoped pidfd for the exact
writer TID, duplicates that task's numbered descriptor into one stable open-file description, and
copies at most 16 MiB of tracee buffer into local immutable memory. It revalidates the notification
immediately before emulating the write through that duplicate and returns the exact value or
negative errno. It never uses `SECCOMP_USER_NOTIF_FLAG_CONTINUE`. Killable notification waits keep a
signal from aborting after the emulated side effect and then restarting the same write.

Only a regular file whose stable device is `/scratch` or `/dev/shm` can latch a positive short
result or `ENOSPC`/`EDQUOT` as storage exhaustion. Partial writes to pipes and sockets preserve their
ordinary result. A scalar request larger than the 16 MiB emulation ceiling fails the session closed
with internal exit 74; callers must chunk larger writes. Brokered writes are serialized through PID
1, and a blocking pipe/socket write can remain blocked until the ordinary session timeout kills the
container. These are intentional compatibility and throughput costs of the deterministic
classification boundary.

The inherited filter rejects `CLONE_UNTRACED`, descriptor-table divergence, and later seccomp-filter
installation, and reports `clone3`, kernel asynchronous-I/O families, vectored writes, ambiguous
regular-file transfer paths (`sendfile`, `splice`, and `copy_file_range`),
`process_vm_writev`, and file-backed shared mappings as unavailable. Those paths could otherwise
allocate storage without one immutable descriptor/request/result tuple. The filter remains active
across fork and exec, while `ENOSYS` permits scalar direct-write, synchronous-copy, and pthread
fallbacks. Anonymous shared memory remains available and memory-cgroup bounded. Syscall numbers at
or above the reviewed arm64 table limit also return `ENOSYS`; a newer kernel syscall must be
explicitly classified before use.

Multi-file allocation, inode exhaustion, and sparse-file attempts therefore remain inside the
session's tmpfs and memory cgroup instead of consuming the target or harness volume. Exhaustion
terminates the session with reserved supervisor exit code 73; the parent maps that to the sanitized
`driver_session_storage_exceeded` error. The target-local ledger and cleanup machinery remain
outside the bounded session store. Full syscall tracing adds overhead to syscall-heavy local
workloads; budget wall time accordingly. The deterministic qualification exercises the provider-
shaped, network-dominated path but is not a throughput benchmark for every digest-pinned image.

## CLI template

All isolation and budget arguments are explicit:

```sh
./.venv/bin/python tools/run-work-queue.py run \
  --workspace /absolute/target-repository \
  --engagement /absolute/target-repository/engagements/example-2026-08 \
  --corpus-enumeration-ref <registered-frozen-manifest-artifact-id> \
  --runtime claude-code \
  --session-backend docker \
  --model claude-subject-20260826 \
  --reviewer-model claude-independent-reviewer-20260826 \
  --max-sessions 8 \
  --max-wall-seconds 3600 \
  --session-timeout-seconds 600 \
  --session-max-budget-usd 5 \
  --claude-executable /usr/local/bin/claude \
  --docker-image operator/claude-runtime@sha256:0000000000000000000000000000000000000000000000000000000000000000 \
  --docker-python-executable /usr/local/bin/python3 \
  --docker-executable /usr/local/bin/docker \
  --docker-memory-bytes 2147483648 \
  --docker-cpus 2 \
  --docker-pids 128 \
  --docker-nofile 1024 \
  --docker-scratch-bytes 268435456 \
  --docker-scratch-inodes 16384 \
  --docker-shm-bytes 16777216 \
  --docker-shm-inodes 1024 \
  --read-only-input /absolute/extra-input
```

Replace the all-zero example digest with the exact already-cached image digest. Repeat
`--reviewer-model` for the ordered independent-reviewer pool and `--read-only-input` only for regular
files the session actually needs. Before signing the engagement scope, pin the exact manifest-byte
digest on its `Frozen corpus enumeration SHA256` line. After kernel initialization and before the
run, register that exact manifest plus its linked enumeration as artifacts.
`--corpus-enumeration-ref` takes the manifest artifact ID, not that digest. If a budget boundary is
reached without the option, the driver returns `operator_required` and does not record
`budget_bounded`.

## What the test lanes prove

The default, credential-free suites prove protocol shape, admission binding, PID-1 behavior, Stop
parsing, sanitized failures, and the generated Docker contract. They do not prove an OS boundary
unless the opt-in Docker tests run.

The opt-in Docker lane uses an already-cached immutable Python image and a fake Claude-shaped
executable. It exercises a real Docker Desktop container, an evasive descendant, timeout/interrupt/
parent-death cleanup, exact-ID ownership, aggregate byte/inode/sparse exhaustion, a one-shot positive
short-write/delete/exit attempt from a detached descendant, a nonleader-thread partial pipe write,
zero usable model capabilities, stable thread-scoped descriptor duplication, rejection of untraced
clone and unobservable file-transfer paths, pthread fallback, PID-1 relay, and the Stop/broker path
without contacting Anthropic. This is
authoritative evidence for the local containment mechanism, not evidence that a particular Claude
image can authenticate or complete a provider request.

A credentialed live-Claude qualification is a separate operator run with a reviewed digest-pinned
image containing Claude Code and Python plus deliberately scoped credentials. A green fake-Claude
or CI run must never be reported as that qualification. Conversely, provider availability is not
used as the oracle for the deterministic containment tests.

Focused commands:

```sh
python3 tools/container-broker-protocol-test.py
python3 tools/container-session-supervisor-test.py
python3 tools/docker-session-runtime-test.py
python3 tools/docker-work-queue-integration-test.py
python3 tools/docker-work-queue-drain-test.py

HARNESS_RUN_DOCKER_INTEGRATION=1 \
  python3 tools/docker-session-runtime-test.py

HARNESS_DOCKER_QUEUE_TEST_IMAGE='python@sha256:<exact-cached-digest>' \
  python3 tools/docker-work-queue-integration-test.py

HARNESS_DOCKER_QUEUE_TEST_IMAGE='python@sha256:<exact-cached-digest>' \
  python3 tools/docker-work-queue-drain-test.py
```

The environment-gated commands must skip rather than pull when their exact image is unavailable.
