# Native v1 source-mode compatibility

For new research, use the [v2 engagement guide](engagement.md). The procedure
below is retained for explicit v1 inputs or existing v1 records; its approvals,
limits and signatures keep their original meaning. Do not apply them to v2.


This is shared source-mode code. It is not a separate adapter for each target.
Target inputs are source, runtime images, prepared dependencies, and commands.
Go is an optional preset. Other runtimes use the same execution and review path.

The paid provider route, credential containment and native reviewer are **not
qualified** by the local checks. Synthetic Docker execution passed; it does not
qualify a real target. Complete [SOURCE-SDK-CHECKS](../../evals/native-qualification/SOURCE-SDK-CHECKS.md)
before claiming live source-mode qualification. Signed target-local authority
remains a separate requirement; checks cannot grant it. The
[dated status](../wiki/native-research-status.md) records the broader evidence boundary.

## Prepare the environment

Use a new harness worktree and a new run root. Keep the existing prepared source
and earlier engagement records unchanged until their replacements have new pins.
For the Go preset, source mode needs:

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

New source plans pin `native-offline-source-effect-v1`. The live approval signs
the exact plan, including this class. Before a requested action, the host reads
back all three executors: network `none`, only the writable owned `/target`
copy and read-only offline `/modules` mount, read-only container root, non-root
user, dropped capabilities, no privilege gain, and finite CPU, memory and
process limits. This class permits an agent-selected argv and script only inside
those disposable copies. An older source plan without this envelope can still
use its manual `source-execute` path, but cannot dispatch a researcher-requested
host action. A matching scope hash or a sentence in `NEXT.json` is not a grant.

## Other runtimes

Use `--source-runtime /absolute/private/runtime.json` instead of `--go-toolchain`.
The JSON file has exactly these fields (use the installed version):

```json
{
  "version_command": ["python3", "--version"],
  "version_stdout": "Python 3.13.0",
  "dependency_command": ["python3", "-c", "import required_package"]
}
```

Keep this file private (`chmod 600`). The version command must exit zero and its
trimmed stdout must equal `version_stdout`. The dependency command must exit zero
with empty stdout. If no dependencies are needed, use `["true"]`. Both commands
run in the source directory at startup. Choose probes that do not change source.
The runtime must exist in both the native-agent image and executor image.
Preparation does not install it. No host Go installation is needed for this form.

`--module-cache` is optional for a custom runtime. If supplied, the runner copies
and pins the directory and mounts it read-only at `/modules`. The build/test argv
must select that offline dependency location as needed. This mode does not apply
Go environment variables. For example, an argv may start with `env` to set a
language-specific cache path. The executor has no network access. Do not put
credentials in command arguments, dependencies or runtime configuration.

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
read and edit its source copy, use its configured runtime, and keep scripts and results in ordinary
files. `/workspace/SOURCE.json` describes this profile. Native tool output is
research evidence, not an independently verified result.

When the research batch is ready, run `source-execute --run-root RUN` on the host.
Its optional `--command-file` selects a different bounded argv array, within the
same signed scope. It freezes both workspace writers, captures the actual current
source, then releases them. It runs the captured command in three separate
offline executors: the initial execution and two replays. Each executor is paused
before final output bytes are saved. The Go preset also collects binary metadata. A nonzero exit still
produces a receipt. A timeout, lost acknowledgement or excessive output stops the
run and retains an unknown execution; no retry is automatic.

Multiple batches can use the same run. Before each execution, the host stops the
old executor processes, restores original source, clears private caches, and
starts the same sealed container ID under the existing run authority. It then
copies the new captured input. Earlier inputs, output bytes and receipts remain
in their own evidence directories. Do not reset or unpause executors manually.

Each command has at most the original run duration; the shared deadline can end
it earlier. Each
stdout/stderr stream is limited to 1 MiB. Credential-like output is withheld,
with its hash retained.

Evidence lives under `controls/source-executions/<id>/`: the captured input tree,
input manifest, receipt, separate output trees and manifests, stdout/stderr and binary
metadata. The receipt binds the plan, original source, actual captured input,
dependency closure, command, environment, image, platform, runtime, exact executor
IDs, exit codes and output hashes. Matching replay output is a reproducibility
observation. It does not prove a security claim. Verify the causal link and a
counterexample/control separately.

## Researcher-requested source check

In a newly prepared source-only run with the approved offline envelope, the
researcher may choose a command and script in its ordinary source workspace,
then put one typed request in `/workspace/NEXT.json`:

```json
{
  "kind": "native-continuation-next-v1",
  "last_result": {"state": "inconclusive", "rules_out": "none", "unresolved": "entry path"},
  "capabilities": [], "coverage": [], "strong_lead": false,
  "proposed_stop": false, "next": null,
  "host_action": {"kind": "native-source-execute-v1", "command": ["sh", "check.sh"]}
}
```

`continue` checks live approval, shared allowance, the source-only plan and
actual executor isolation. It freezes the command and current source copy,
assigns an action ID, saves the request and frozen hashes, then marks dispatch
before calling the existing `source_execute` executor once. A captured result
appears at read-only `/research/source-actions/<id>/RESULTS.json` for the next
native turn. The projection shows exit codes and output hashes; raw stdout,
stderr and files remain withheld because a generic regex cannot establish
that arbitrary target output is safe to expose. The full protected source
receipt and immutable action terminal stay under `controls/`. The controller
prompts the next turn to read this result and revise `NEXT.json`.
A duplicate request cannot start another batch.

After a crash, `continue` may adopt a captured source receipt only when the
pending action ID, exact command, frozen input manifest, plan and receipt bytes
match. A prepared action can dispatch after those checks. Missing, corrupt or
unknown post-dispatch results stop for readback. Missing or unfinished receipts
use `unknown_effect`; a later exact captured receipt can be adopted without
another execution. An observed invalid captured receipt records its hash and
reason as `evidence_changed`. Replacing those bytes does not resume the run;
the operator must reconcile the evidence outside this controller before any
new effect. A crash before the
prepared state is saved can recover one complete frozen request only when no
executor directory or dispatch event exists. An incomplete freeze is moved to
`controls/continuation/aborted-source-actions/<id>/` with an abort receipt,
then a fresh ID is prepared if the same run remains active. Any executor
directory, dispatch event, or ambiguous journal stops for reconciliation.
Earlier captured action directories are checked against their terminal receipts
and capture history before a later action's orphan is recovered. If a crash
saved captured state but interrupted its journal event, the controller verifies
the terminal, receipt and projection, then restores the event before replacing
that state with a new action.
An action outside the offline class
records `authority_required` separately from research help. The source request
does not grant a service or external effect.

An older plan without the class stops as `authority_required`. Count that as a
human authority intervention and retain the blocked run; the immutable plan
and approval cannot be upgraded in place. Prepare and approve a new run if the
operator grants the class.

The projection always says `security_effect: unproven`. Three matching runs
establish repeated output. The original entry path, starting state, actor
permission, protected effect and causal control still need independent evidence
and fresh review.

## Researcher-requested fresh source review

The same active source-only run may request one fresh review with a separate
`host_action` in `/workspace/NEXT.json`:

```json
{"kind": "native-source-review-v1", "claim": "The after branch may preserve the harmless note."}
```

Set `next` to `null` and `proposed_stop` to `false` as in the source-check
example. This is one typed request, with no agent-selected evidence paths. The
host checks the current signed plan and approval, shared allowance, unresolved
effects, original source, and an empty reviewer handoff and session store before
creating a packet. It then freezes the claim, original and current source,
research note and checkpoint, and independently enumerates every protected
researcher source-action receipt. Raw output, including adverse batches, enters
the existing six-role packet only when it is present, hash-bound and safe to
disclose. An unfinished action or missing, unsafe or oversized required evidence
holds the request incomplete before a reviewer session starts.
An optional `researcher/project/RESULT.md` is frozen with the current source
and repeated in the unfinished role with its hash and agent-statement label.
For checked-setup agent-owned closeout, the researcher writes this result before requesting
review. Before that request, write the final claim, coverage, capabilities, and
lead state in `NEXT.json`. After review, propose a stop while leaving those
reviewed fields, the result, and source bytes unchanged. The continuation host
then checks the exact result, evidence and review, requests the existing owner
stop, and verifies cleanup and resource absence. A reviewer decision to reopen
puts its concrete next check in a new agent prompt under the same approval and
remaining allowance. User, allowance and unknown-effect stops bypass a new
review and preserve an incomplete result and teardown receipt. The contained
workflow is in [AGENT-CLOSEOUT-E2E](../../evals/native-qualification/AGENT-CLOSEOUT-E2E.md).
If a stop proposal has no valid `RESULT.md`, the controller prompts one agent
turn to repair it. A stale review prompts the agent to request a new review.
Unchanged result and checkpoint bytes after that turn stop the run incomplete.

The existing fresh source reviewer and host effect/control path consumes this
packet. A completed internal assessment is returned to the same run at read-only
`/research/reviews/<review_id>/RESULTS.json` on the next native turn. The
projection binds the plan, `NEXT.json`, observer selection, packet request and
protected reviewer receipt by hash. It always says `security_effect: unproven`
and `filing_or_escalation_authorized: false`. An uncertain or unfinished review
does not automatically dispatch again or use the other reviewer slot. The
cached readback rechecks the protected receipt and host evidence, sealed packet,
observer selection, source-action corpus and live researcher source; a changed
or missing binding holds the review incomplete.
The contained request-to-readback scenario and its limits are in
[AGENT-REQUESTED-REVIEW-E2E](../../evals/native-qualification/AGENT-REQUESTED-REVIEW-E2E.md).

Both manual and researcher-requested reviews use the frozen-packet `review`
flow. The packet includes the exact claim, relevant receipts, original source,
changed inputs, controls, failures and limits. A fresh
reviewer receives the pinned packet and a clean source copy. It adds scripts and
writes `/workspace/source-check.json` with `kind: native-source-check-v1`, the
packet `input_id`, separate `effect` and `control` argv arrays, and a `rationale`.
The runner requests this file; no target-specific runner code is needed.

The host freezes the review scripts and definition together. It rejects changed
or deleted original files. It executes the effect and control on three clean
copies each and compares original file bytes after each command. Results include
exit codes, streams, and receipt hashes. The reviewer receives file counts and
changed or missing paths with hashes in the small summary. The full manifests
remain in protected host receipts and are also available as separately hashed,
read-only reviewer files. This keeps unchanged source files from filling the
summary. Nonzero exit codes remain observations. The reviewer then reads and hashes
`/source-evidence/RESULTS.json`
and returns its conclusion in the same native session. The final receipt binds
that conclusion to the packet, source, scripts, executions and native trace.
There are two fresh reviewer slots per run, as in service mode.

The result can be `candidate_for_operator_review`. It does not emit `confirmed`
or open filing. The original-file checks establish the starting and ending bytes;
they cannot exclude temporary source changes made by a script. The operator must
inspect the scripts and causal control. Host execution is labeled as such; it is
not claimed as a native tool action directly observed on a target service.

## Conditional paired patch check

When the frozen goal explicitly contains `Patch goal: required`, the researcher
may write a regular UTF-8 `/workspace/PATCH.diff` and request one paired check:

```json
{"kind": "native-patch-check-v1", "claim": "The proposed diff removes the observed effect."}
```

Put this object in `host_action` in `NEXT.json`, with `next: null` and
`proposed_stop: false`. Write the candidate `project/RESULT.md` before this
request if the same review should support closeout. A goal without the opt-in
line needs no patch action. An unrequested patch is rejected.

The host copies the pinned original source, applies the exact diff there, and
records the full original and patched byte and mode manifests, the diff hash,
goal, plan, approval, actor, initial state, and remaining allowance. It never
applies the diff to `original/`. The diff and both manifest hashes enter the
immutable fresh-review packet; full manifests remain in protected host records.
Unsafe paths, symlinks, binary patches, changed originals,
or a diff that does not reproduce the patched manifest stop before review.
An applicable mode-only diff counts as a nonempty patch.

The independent reviewer writes `source-check.json` with kind
`native-paired-source-check-v1`, the packet `input_id`, distinct `effect`,
`control`, `normal`, and `connected` argv arrays, and a rationale. Its scripts
are frozen separately from the patch and must have identical bytes on both
copies. The host runs each command on three clean original copies and three
clean patched copies under the same offline source executor. Every execution
receipt labels its variant; a patched run cannot count as original replay.
The host compares exit status, streams, changed or missing output files, and
file modes across all replays. It recomputes output deltas from saved input and
output manifests at readback.
The reviewer reads and hashes the paired result, checks the material fix link,
and states limits. Its checked link must bind the evidence hash, diff hash,
original effect, changed line, and patched result. A changed effect with stable
replays, preserved normal and connected outputs, and an unchanged control can
become a **checked-fix candidate**
for internal operator review. It is not a confirmed security result or external
filing authority. Any mismatch stays unproven. A supported closeout under a
patch goal requires this exact reviewed candidate and the normal stop/cleanup
readback. A blocked or dry ending may close without a patch.

The contained scenario and its synthetic limits are in
[AGENT-PAIRED-PATCH-E2E](../../evals/native-qualification/AGENT-PAIRED-PATCH-E2E.md).
Stop with the normal `stop` command and inspect the final stop/cleanup receipt.

## Verification status

The saved receipts record the earlier offline contract results at their exact
source hashes. The source-mode check covers
runtime input, reviewer check/control input, and preservation of original files.
A synthetic local Docker scenario runs two batches on the same three executors,
checks that old output remains intact, executes a frozen reviewer script, rejects
changed originals, and blocks a new batch after an unknown effect. Its local test
owner replaces the normal authority checks. It does not test live owner loss,
provider access, native review, or engagement behavior.

Repeat it with an existing local image that has `sh`:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 tools/check_native_source_mode.py --docker sha256:LOCAL_IMAGE_ID
```

The [saved source-mode receipt](../../evals/native-qualification/SOURCE-MODE-LOCAL-CHECKS.json)
records the image, command, checked source hashes and output; it is not a fresh
result for later runner or check-script revisions. The earlier
[SOURCE-SDK-LOCAL-CHECKS.json](../../evals/native-qualification/SOURCE-SDK-LOCAL-CHECKS.json)
records the initial adapter checks at their older source hashes. Full native
review, TLS streaming, stop/owner-loss behavior and real-target E2E remain unverified.
