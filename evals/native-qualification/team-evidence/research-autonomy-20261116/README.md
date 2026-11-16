# Research autonomy: owned fixture evidence

The implementation began at `5684d9b4578d7681239f1bcb497560f53c93df4e`.
The hosted results below tested source commit `ba0a9a7438cd090b5bf767db1e9240c5a1140e48`.
These owned, benign fixtures verify workflow mechanics; they do not establish
fresh-target research success or qualify a model's research judgment.

| Area | Observed evidence | Remaining boundary |
| --- | --- | --- |
| M0: signed preparation | Signed new-policy fixture used by the hosted Codex native and public runs. | OMP public run stopped on lease renewal before review. |
| M1: research turns and source | Codex native tools read the actual harmless source through scripted provider turns. | Model-directed full research is not established. |
| M2: helpers | Codex native helper inherited authority, completed, reported usage, avoided duplicate accounting and stopped while active. | OMP public run stopped on lease renewal before review. |
| M3: environment and accounts | Hosted Docker environment, guardian, SSH, application reset, proxy and TLS checks passed. | These owned fixtures are not a claim about every access mode or production target. |
| M4: evidence and closure | Codex public Runner used a distinct reviewer, read its actual packet, accepted the bounded negative closure, and verified export. | Native independent technique evaluation and withdrawal remain unproven. |
| M5: recovery | Codex direct native fixture recovered exact owner receipts and verified cleanup. | Public-run interruption is not separately proven. |
| M6: public entry and export | Codex public CLI reached reviewed closure, verified export and cleanup. | OMP public run stopped on lease renewal before review. |
| Active knowledge | Codex direct native helper materialized and read the retained reference, including a new version. Separate host-only fixtures cover simulated fetch failure, independent technique evaluation and withdrawal. | Those latter knowledge cases have not been joined to both native public runs. |
| Live providers | [OMP live source read](LIVE-OMP-SOURCE-READ.md) reached an actual provider and observed the native tool output. | Complete live model-directed workflow in either runtime remains unproven. |

[Hosted run 43924808047](https://github.com/matheusht/redteam-harness/actions/runs/43924808047)
passed 42 Codex direct native checks and all five public Runner checks, with
verified cleanup and export. It used a scripted provider; its public run recorded
zero provider errors. [Codex summary](hosted-43924808047/codex-summary.json)
and [Docker summary](hosted-43924808047/docker-summary.json) retain check names,
source and artifact hashes, and bounded outcomes. The Docker job passed 96 checks
and verified the owned SSH listener and fixture cleanup.

Earlier hosted OMP direct native checks passed, but public runs exposed tool-call
identity and provider-protocol failures. The [failure-first identity regression](omp-composite-tool-id/README.md)
records the host-side fix and its local retest. The latest OMP direct suite passed all 42 checks. Its public run completed source
and helper work with zero provider errors, then stopped before review with
`environment_lease_exceeds_grant`; cleanup was verified. The
[renewal regression](renewal-bounds/README.md) records the current repair and
controlled-clock evidence; native requalification is pending. Direct OMP uses Chat Completions; the public fixture uses Responses to
exercise that native wire path. Chat Completions remote-compaction continuity is
not qualified by this scenario.

The real-runtime scripted-provider workflow, simulated checks, and live-provider
smoke have different evidentiary scope. Private raw outputs remain outside the
repository in `/private/tmp/oslit-autonomy-e2e-20261116`.

To repeat the hosted joined scenarios at the tested commit, use the
[OSLit environment workflow](../../../../.github/workflows/oslit-environment.yml),
which provisions Ubuntu 24.04, Docker and the pinned runtime bundles. An
operator with repository access can rerun the exact hosted job set:

```sh
gh run rerun 43924808047
```

At that historical commit, Docker and Codex passed; OMP public renewal failed as
recorded above. Acceptance for the repaired revision requires both direct and
public JSON results to report `passed`, with cleanup and export verified.
The workflow uploads its result artifacts. This is a scripted-provider mechanics
check; the live OMP source-read receipt has separate requirements and scope.

The [local acquisition scenario](acquisition-local.py) passed six checks against an
owned TLS server; the [result](acquisition-local-result.json) records source hashes.
Run it with Python 3 and OpenSSL from the repository root:

```sh
python3 evals/native-qualification/team-evidence/research-autonomy-20261116/acquisition-local.py /tmp/oslit-acquisition-result.json
```

It checks transfer bytes and digest, route/method/credential refusal, and incomplete
transfer recording. It does not run an agent or Docker lab.

The [knowledge host scenario](knowledge-host-e2e.py) and its
[result](knowledge-host-result.json) exercise two signed cases and real controller
journals. A fresh reviewer recommends an exact technique version using distinct
synthetic changed-case and counterexample artifacts; another withdraws it. The
scenario also simulates a fetch and retention failure, then verifies the recorded
gap and export. It uses simulated environments and no native runtime or network.

```sh
python3 evals/native-qualification/team-evidence/research-autonomy-20261116/knowledge-host-e2e.py /tmp/oslit-knowledge-result.json
```

## Local prerequisites and checks

Pinned dependencies were installed into a private virtual environment with
`python3 -m venv` and `pip install -r requirements-ci.txt`. Full conformance at checkpoint `b4740419` reported 900 checks and zero failures. ARM64 Linux model images were rebuilt from installer-generated contexts and
checked with network disabled: Codex 0.166.0
`sha256:31f1ef4b686216ceea3653afce7dbd364f1424e673708253cbb7b2942139e4a0`,
OMP 18.20.0 `sha256:3296813f4dc38b1a98267b6f5d6fc0dd9ea8aa51c12f3c1d8539f2dcdfe616c9`.
Both contained network bridge SHA-256
`7ce9705ea788de89bed6d7bb2bf0660f1d665896863c54f872227568b76ec91a`.
The subsequent tool-call ID fix runs on the host and is not embedded in these
images. These are build and version receipts, not complete workflow proof. Docker Desktop on the Mac is not a Linux controller
host with the required shared cgroup identity; hosted Ubuntu is required for the
Linux model-owner scenario.

The initial boundary regression run failed two cases because its fake runtime
omitted a field present in real runtime initialization. After fixing the fixture,
a binary-read case revealed that arbitrary evidence bytes were no longer returned.
Restoring the prior lossless behavior made the complete 23-scenario boundary
fixture pass. The Mistral resolver case was written with fake credentials and
failed before adding the provider mapping; it then passed including mismatch,
disabled and ambiguous-key refusals. Neither check made a provider call.
