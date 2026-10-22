# Native Go source research

This is an implemented candidate adapter. Docker execution, the paid provider
route, credential containment and target replay are **not qualified** by the local
contract checks. Complete [SOURCE-SDK-CHECKS](../../evals/native-qualification/SOURCE-SDK-CHECKS.md)
before using it as live target authorization.

## Prepare the environment

Use a new harness worktree and a new run root. Keep the existing prepared source
and earlier engagement records unchanged until their replacements have new pins.
The source mode needs:

- A regular-file source export, a brief and a signed scope. The scope must permit
  the selected source commands and any effects. Do not import ambient Git or home
  state. `.native-source` is reserved for executor state.
- A complete, extracted Go module cache, including module metadata. A cache with
  only `.info` or `.lock` files is insufficient. The runner never fetches modules.
  Prepare required `go.sum` files separately. If this changes the source export,
  record the new manifest and bind the scope and plan to that manifest.
- Locally available image IDs for the native agent and offline executor. Both
  need the exact Go version. The agent image also needs the pinned OpenCode
  version. The same combined image can serve both roles. Go must be on the
  existing image PATH; keep the native image's required environment unchanged.
- The same exact Go version on the host, used only to inspect frozen binary
  metadata with `go version -m`. Preparation pins its path and file hash.
- A relay binary for the selected Linux architecture and a pinned public TLS
  trust file. Build images, obtain dependencies and prepare credentials only
  under their applicable authorization.

For a combined image, copy `/usr/local/go` from an already obtained, digest-pinned
Go image into the pinned OpenCode image, then link `/usr/local/bin/go` to
`/usr/local/go/bin/go`. Build without network access and record the resulting
image ID. Do not add secrets or change PATH. This guide does not pull or build an
image for you.

The executor uses Docker network `none`, a read-only root, one CPU, 1 GiB RAM,
64 PIDs and writable private source/cache directories. Go uses `GOTOOLCHAIN=local`,
`GOPROXY=off`, `GOSUMDB=off`, `GOWORK=off`, `GOENV=off`, `-mod=readonly` and
`CGO_ENABLED=0`. The module cache is mounted read-only. Startup checks the exact
Go version and rejects module graph entries without an extracted directory.
Commands must still establish that their package and test dependencies work.

## Prepare the source profile

Put the build or test command in a JSON argv array, for example
`["go", "test", "./..."]`. This is an input file, not a command to run during
preparation. A source script can run a batch of experiments and controls.

Use the common `prepare --help` inputs for the run root, source, brief, scope,
relay, trust file, images and platform. Add these arguments instead of
`--target-command` and `--target-port`:

```text
--source-only
--build-command /absolute/private/build-command.json
--go-toolchain go1.26.4
--module-cache /absolute/private/prepared-module-cache
--model opencode-go/deepseek-v4.1-flash
--provider-route opencode-go
--provider-authority opencode.ai:443
--max-connections 64
--max-bytes 67108864
--duration-seconds 28800
```

Preparation copies and pins inputs. It starts no container or model session.
Source mode has no listener, target URL or TCP readiness probe. The existing
service profile retains its target command and port.

## Paid provider boundary

The paid route accepts only `opencode-go/deepseek-v4.1-flash`. It has no free-model
fallback. Startup reads back the loaded model, provider policy and endpoint.
The fixed endpoint comes from OpenCode's local provider metadata; the provider
configuration shape follows the [official schema](https://opencode.ai/config.json).
This establishes the intended configuration, not live provider compatibility.

The native process receives a non-secret placeholder. A host-only TLS gateway
replaces it with the real key for `POST
/inference/go/openai/v1/chat/completions`, with exactly the selected model.
The gateway sits behind the existing metered CONNECT transport. It rejects other
paths, models, methods, redirects and ambiguous request framing. It does not log
request/response bodies or upstream error text. The shared connection, byte and
wall-time limits still apply; they are not a monetary budget or request counter.

For this route, the pinned `--runtime-ca` file must contain the public certificate
chain used by the host gateway, with a valid `opencode.ai` TLS server identity.
Prepare its matching private key outside all source, engagement and run trees.
Keep the provider key in a separate private host file outside those trees. Neither
private file is copied or mounted. The gateway uses system trust to verify the
real upstream service. Do not reuse these files as target input or place them in
a review packet.

After the environment and route have been qualified and the new plan has fresh
approval, keep the owner in the foreground:

```sh
python3 tools/native_research.py start \
  --run-root /absolute/private/run \
  --approval /absolute/private/live-approval.json \
  --provider-key-file /absolute/host-private/provider-key \
  --provider-tls-key /absolute/host-private/gateway-key.pem
```

Use the existing approval schema with the **new** plan digest, scope digest,
paid model/route, exact image IDs, limits and expiry. Old approvals cannot be
reused. The keyless service route needs neither private file.

## Research, capture and review

Use the normal `research`, `resume` and `reconstruct` commands. The researcher can
read and edit its source copy, use Go, and keep scripts and results in ordinary
files. `/workspace/SOURCE.json` describes this profile. Native tool output is
research evidence, not an independently verified result.

When the research batch is ready, run `source-execute --run-root RUN` on the host.
Its optional `--command-file` selects a different bounded argv array, within the
same signed scope. It freezes both workspace writers, captures the actual current
source, then releases them. It runs the captured command in three separate
offline executors: the initial execution and two replays. Each executor is paused
before final files and Go binary metadata are collected. A nonzero exit still
produces a receipt. A timeout, lost acknowledgement or excessive output stops the
run and retains an unknown execution; no retry is automatic.

There is **one protected replay batch per run**. Put all required cases and
controls in that batch. Frozen executors are not reused. A changed batch needs a
new run; do not unpause the executors manually. Each command has at most the
original run duration, and the shared run deadline can end it earlier. Each
stdout/stderr stream is limited to 1 MiB. Credential-like output is withheld,
with its hash retained.

Evidence lives under `controls/source-executions/<id>/`: the captured input tree,
input manifest, receipt, separate output manifests, stdout/stderr and binary
metadata. The receipt binds the plan, original source, actual captured input,
module closure, command, environment, image, platform, Go version, exact executor
IDs, exit codes and output hashes. Matching replay output is a reproducibility
observation. It does not prove a security claim. Verify the causal link and a
counterexample/control separately.

Use the normal frozen-packet `review` flow to examine source claims and public
execution evidence. Include relevant receipts, original source, changed inputs,
controls, failures and limits. The reviewer can inspect the read-only original
source and use its own workspace. Generic source review remains unassessed:
`independent_host_check=unavailable`. Host replay is not automatically original
target impact proof, and the adapter does not emit `confirmed` or open filing.
Stop with the normal `stop` command and inspect the final stop/cleanup receipt.

## Verification status

The four prewritten offline contracts passed: source CLI arguments, exact paid
tuple/policy, unchanged keyless configuration, and gateway request validation.
Python syntax parsing and `git diff --check` passed. These checks used no Docker,
SDK code, provider key, dependency retrieval or model call. The full failure matrix,
Docker containment, TLS streaming/stop behavior and live route remain unverified.
The [saved local check receipt](../../evals/native-qualification/SOURCE-SDK-LOCAL-CHECKS.json)
binds the exact checked Python files and records the repeatable command.
