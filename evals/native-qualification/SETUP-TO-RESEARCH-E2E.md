# Checked setup to native research: failure-first scenario

Issue #204 joins the checked offline setup package to the existing source-only
native route. The agent's recipe and threat model are proposals. The host must
verify the checked package and still require the separate, exact research-plan
approval before starting research. A caller must not supply a new build command
or dependency set at this transition.

## Failure cases written before implementation

| Case | Required result |
| --- | --- |
| No checked package, proposal only, or package not `ready` | Reject before creating a research run. |
| Changed source, scope, goal, setup output, builder output, or dependency bytes | Reject the changed input; an old receipt cannot authorize it. |
| Changed or stale setup/build approval, missing signature, or changed signer | Reject before research preparation or Docker contact. |
| Invalid image/platform, runtime probe, build argv, or dependency closure | Reject; do not substitute an operator command or fetch packages. |
| Package says cleanup complete but an owned resource remains | Reject until exact resource absence is verified. |
| Research plan or approval omits or changes the checked-package pin | Reject before research start. |
| Transition interrupted after preparation | Resume only against the same immutable plan and package; do not duplicate setup build or reset setup spend. |
| Threat model correction in research | Preserve the original pinned threat model and record the correction as a new observation. |
| Setup result or repeated build presented as a security effect | Keep it as setup evidence; require original entry-path evidence and independent review for a claim. |

## Public end-to-end scenario

1. Use a fresh harmless multi-file source and a signed scope with only the
   approved setup effects. Save the source, goal, scope, model/image IDs,
   signers, approvals, allowance, and expected source output. Run the bounded
   setup turn and the offline host builder. Keep their exact receipts and
   cleanup readback.
2. Prepare research from the checked package, without an operator build command
   or dependency selection. Assert the research plan pins the source, setup
   output, builder receipt, runtime, dependencies, build argv, initial threat
   model, setup allowance used, and separate research allowance.
3. Present a human-authored research approval bound to that exact plan. Start
   the native owner, run one real research turn, pause, and resume. Verify that
   the workspace exposes the pinned initial threat model and setup trace and
   that the target runtime matches the checked package. A later correction must
   appear as a new research observation.
4. Mutate each input from the failure table in disposable copies. Assert that
   no target build or native turn is dispatched. Stop and verify exact owned
   resource absence and remaining effects. Save CLI output, plan and receipt
   hashes, trace, allowance, assistance, and cleanup as the repeatable result.

The executable provider-free slice is:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 \
  evals/native-qualification/smoke/check_native_setup_to_research.py \
  --output /tmp/native-setup-to-research-e2e.json
```

It needs local Docker with an already-local `busybox:1.37` image, Go,
OpenSSL and `ssh-keygen`. It calls the #202 public builder scenario to create a
fresh synthetic v2 checked package, then invokes public `prepare-checked` with
a separate research scope and explicit research connection, byte and duration
allowance. It checks the sealed plan, copied package and read-only `/research`
inputs, source and dependency bytes and modes, and changed input refusal before
run creation. A local network-none Docker replay mounts checked dependencies
read-only at `/deps`, reads their exact bytes, and builds a disposable source
copy. The scenario also checks exact plan-approval mismatch before Docker,
plan swap refusal, interrupted preparation refusal, and ordinary source-only
preparation. The JSON output records input hashes, checks, results and limits.
Pass `--keep-root /absolute/new/private/dir` to retain the harmless fixture
and prepared research run; the builder removes the synthetic operator signing
key first.

The 2026-11-12 local run passed 28 of 28 checks recorded in
`setup-evidence/native-setup-to-research-synthetic-e2e.json`; the fixture roots
were removed, and the result records hashes, refusal codes, and the Docker
`/deps` readback. The observed passing gate with an exact research approval
was the existing pinned-agent-image check, before a native research turn.

The builder's v2 fixture fabricates setup turns, stop records and provider
accounting. Its research scope is an unsigned synthetic fixture. This
transition scenario does not run a native model turn or
provider. The live research turn and pause/resume in step 3 require a fresh
authorized target, actual runtime image, signed scope and provider route.
No prepared plan or passing synthetic check is a research result.

## Host transition

After a checked setup build and its cleanup are verified, prepare a new private
research run from that exact setup root:

```sh
python3 tools/native_research.py prepare-checked \
  --run-root /absolute/new/private/research-run \
  --checked-setup-root /absolute/private/stopped-setup-run \
  --scope-file /absolute/private/research-scope.md \
  --scope-sha256 <sha256-of-research-scope> \
  --max-connections <approved-count> \
  --max-bytes <approved-byte-limit> \
  --duration-seconds <approved-duration>
```

The operator must supply a separately authorized research scope. The command
enforces a different scope hash and refuses the structured setup-only scope,
including a byte-edited copy. It does not verify a research-scope signature.
The command accepts no replacement build command, runtime, image, or
dependency catalog. It checks that the setup and build grants are still fresh,
then seals the copied package, consumed setup allowance, source bytes and
modes, runtime, dependencies, and initial threat model into `plan.json`.
`start` still needs a human-authored `native-research-live-approval-v1` for the
exact new plan and its research allowance. Its existing approval mechanism
checks the plan and scope hashes and expiry; this scenario does not qualify a
cryptographic signature on that research approval.
