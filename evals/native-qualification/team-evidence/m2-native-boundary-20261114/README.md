# Native runtime boundary checks — 14 November 2026

These are engineering checks on macOS with installed Codex 0.166.0, OMP 18.20.0,
and the pinned OMP SDK. All model responses came from owned loopback fixtures.
No real provider inference, target research, Docker/SSH execution, or engagement
qualification occurred. Source and result hashes are in `manifest.json`.

The actual Codex workflow preserves its native shell, file reads/writes and patch
tool through its native remote executor. The actual OMP workflow preserves SDK
read/write/bash through a separate tool process. Both model processes use a host
sandbox that forbids child processes; their tools run in separate owners. The
Codex fixture uses its native command sandbox. A second outer macOS sandbox on
its executor prevents Codex from applying that native sandbox, so it is not used
as a substitute for the still-unverified Linux container boundary.

| Saved result | Observed result |
| --- | --- |
| `codex-native-tools.json` | 10 checks: native shell/read/write/patch; outside and symlink read denial; fake provider key absent from tools; model process inspection denied; provider endpoint denied to tools; spawn/MCP/web calls refused; revocation; no key persistence; exact owner stop. Seven simulated HTTPS Responses requests passed through the policy proxy with private trust. |
| `omp-native-tools.json` | Nine checks: actual SDK read/write; separate tool environment; fake key absent; outside read and model process inspection denied; private-trust HTTPS proxy; revocation; no key persistence; exact model-owner stop. Two simulated model requests. |
| `codex-external-tokens.json` | Actual experimental host-managed token login accepted a fake token in memory, without creating `auth.json` or persisting its bytes. Live token validity and account routing were not checked. |
| `credential-resolution.json` | Fake source-store workflows: exact provider/reference matching, missing and disabled keys, expiry, account-bound reload, no serialization/copy, revoked binding refusal. |
| `owner-recovery.json` | Actual no-fork denial and Darwin kernel birth identity. A changed receipt did not signal the live process; the correct receipt stopped it and repeated recovery was safe. |
| `pipe-backpressure.json` | An actual peer that did not read stdin caused a bounded `native_write_timeout`; admission did not wait for the peer's 30-second sleep. |
| `codex-native-control.json` | Actual native environment connection, wrong-bearer refusal, revoked admission and owned pipe shutdown. |
| `runtime-regression.json` | The previous six control/SDK workflow groups still pass. |

The external Bun used for the SDK fixture is 1.4.0, below the SDK's declared
`>=1.4.4` engine requirement. These checks prove only the exercised subset. The
portable bundle validator refuses that Bun version; no Linux compatibility is
claimed from these local results.

## Repeat

Use this integrated repository with the environment proxy module present. Supply
an isolated SDK installation with the exact native platform addon. Commands write
safe receipts to a caller-owned private output directory:

```sh
python3 evals/native-qualification/smoke/check_codex_native_tools.py \
  --tls-proxy --output /private/results/codex-native-tools.json
python3 evals/native-qualification/smoke/check_omp_provider_boundary.py \
  --omp-sdk /private/sdk/node_modules/@oh-my-pi/pi-coding-agent \
  --output /private/results/omp-native-tools.json
python3 evals/native-qualification/smoke/check_codex_external_tokens.py \
  --output /private/results/codex-external-tokens.json
python3 evals/native-qualification/smoke/check_native_credentials.py \
  --output /private/results/credential-resolution.json
python3 evals/native-qualification/smoke/check_native_owner_recovery.py \
  --output /private/results/owner-recovery.json
python3 evals/native-qualification/smoke/check_native_pipe_backpressure.py \
  --output /private/results/pipe-backpressure.json
python3 evals/native-qualification/smoke/check_codex_native_environment.py \
  --output /private/results/codex-native-control.json
python3 evals/native-qualification/smoke/check_native_runtime_adapters.py \
  --live --omp-sdk /private/sdk/node_modules/@oh-my-pi/pi-coding-agent \
  --output /private/results/runtime-regression.json
```

Requirements: macOS `sandbox-exec`, Python, OpenSSL, installed pinned Codex/OMP,
host Bun for WebSocket framing, the SDK for OMP checks, and permission to bind
owned ephemeral loopback listeners. The scripts create and remove their own fake
credentials and workspaces; they do not use the operator's credential stores.
TLS fixtures explicitly set `basicConstraints=CA:FALSE`. Presenting a CA:TRUE
signing certificate as the server leaf fails Codex's Rust TLS verification.

## Integration contract

`Runtime(..., protected_model=True, profile_sha256=<signed raw profile pin>,
credential_resolver=host_resolver, provider_environment=<public proxy variables>)`
keeps credentials in the model process. The host supplies the current admission
guard and an OS network policy that allows only its provider proxy and, for
Codex, its own executor WebSocket. The protected host owner currently supports
macOS; Linux host ownership requires a separately verified namespace/cgroup owner.

Codex's `NativeExecutor` connects a trusted host WebSocket bridge to the exact
`Environment.launch_stdio` process. The native handshake checks version/platform;
thread creation selects `oslit-worker` from the signed configuration and the
exact native environment. Both the signed and effective configuration reject
legacy permission overrides and enabled alternate tool routes. Never publish
`NativeExecutor.registration()`: it contains the private bridge bearer.

OMP's `ToolOwner` uses its signed portable bundle, the environment launcher, native
SDK schemas and cancellation, and the native ready report. `inspect_tool_bundle`
returns its fixed staging/launch data. `HostOperation(wait, cancel)` separates
host acceptance under the admission guard from asynchronous completion.

`owner_receipt()` binds the raw profile pin, runtime, native session and exact
kernel process birth identity. A startup receipt can have `session_id: null`;
that cannot stand in for a started worker session. `bridge_process` is omitted
when absent. Recovery refuses a changed identity before sending any signal.
Only proven process/group absence in the no-fork boundary produces
`child_absence: verified` and `capabilities_revoked: true`; tool-lab cleanup still
requires its separate environment readback. Generic process exit keeps child and
lab cleanup explicitly unverified.

Real-provider use still requires an authorized scope, working provider routes,
valid credentials, portable bundles that can execute in the selected environment,
and integrated environment/authority checks. These fixture receipts grant none
of that authority.
