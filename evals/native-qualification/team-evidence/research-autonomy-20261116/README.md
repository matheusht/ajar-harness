# Research autonomy: owned fixture evidence

The implementation began at `5684d9b4578d7681239f1bcb497560f53c93df4e`.
[Hosted run 43934112061](https://github.com/matheusht/redteam-harness/actions/runs/43934112061)
tested source commit `0983d8b1547d7d9e4f7e3c022e50b088c6b3a68c` on
Ubuntu 24.04. Both pinned native runtimes and the Docker job passed. These
owned, benign fixtures verify workflow mechanics with scripted provider responses;
they do not establish fresh-target research success or qualify model judgment.

| Area | Observed evidence | Remaining boundary |
| --- | --- | --- |
| M0: signed preparation | Both runtimes used signed research-autonomy fixtures in direct and public runs. | Fixture grants apply only to the owned test. |
| M1: research turns and source | Both native leads read actual harmless source through scripted provider turns. | Full model-directed research remains unproven. |
| M2: helpers | Both direct runs verified native helper authority, completion, once-only usage accounting and active stop; both public runs read the completed helper. | OMP per-invocation token and estimated cost usage across compaction is unavailable. |
| M3: environment and accounts | Hosted Docker environment, guardian, SSH, application reset, proxy and TLS checks passed. | These fixtures do not prove every access mode or a production target. |
| M4: evidence and closure | Both public Runners used distinct reviewers, read the actual packets, accepted bounded negative closures and verified exports. | Native independent technique evaluation and withdrawal remain unproven. |
| M5: recovery | Both direct native fixtures recovered exact owner receipts and verified cleanup. | Public-run interruption is not separately proven. |
| M6: public entry and export | Both public CLIs reached reviewed closure, verified export and cleanup. | Scripted turns demonstrate mechanics rather than live research. |
| Active knowledge | Both direct native helpers materialized and read retained references, including a new version. Separate host-only fixtures cover simulated fetch failure, independent technique evaluation and withdrawal. | Those latter knowledge cases have not been joined to both native public runs. |
| Live providers | [OMP live source read](LIVE-OMP-SOURCE-READ.md) reached an actual provider and observed native tool output. | Complete live model-directed workflow in either runtime remains unproven. |

The direct native runs passed 42 checks per runtime; the public runs passed six
Codex and seven OMP checks. The [Codex](hosted-43934112061/codex-summary.json),
[OMP](hosted-43934112061/omp-summary.json), and
[Docker](hosted-43934112061/docker-summary.json) summaries retain check names,
source and artifact hashes, and bounded outcomes. The Docker job passed 96 checks
and verified the owned SSH listener and fixture cleanup.

Each public run recorded one authenticated upload interrupted by the verified
reviewed-closure stop, with the matching journal event inside the upload interval.
The strict worker-failure check accepted only `engagement_stopped` in the verified
closed and reviewed state. Neither run timed out: Codex took 132.540 seconds and
OMP 343.753 seconds against the 360-second fixture limit. The OMP result therefore
has limited timing headroom and a slower host could hit the test limit.

OMP public execution included one compaction and no `native_usage_invalid` failure.
The [compaction accounting evidence](omp-compaction-usage/README.md) explains why
usage across that boundary is marked unavailable rather than inferred from the
native active-window totals. Direct OMP uses Chat Completions; the public fixture
uses Responses. Chat Completions remote-compaction continuity is not qualified by
this scenario.

Earlier runs exposed [tool-call identity](omp-composite-tool-id/README.md),
[renewal](renewal-bounds/README.md), and
[worker-failure acceptance](public-worker-failure/README.md) defects. Their
failure-first receipts and retests remain separate from the final hosted result.
Private raw outputs remain outside the repository in
`/private/tmp/oslit-autonomy-e2e-20261116`.

To repeat the hosted joined scenarios at the tested commit, use the
[OSLit environment workflow](../../../../.github/workflows/oslit-environment.yml),
which provisions Ubuntu 24.04, Docker and pinned runtime bundles. An operator
with repository access can rerun the exact hosted job set:

```sh
gh run rerun 43934112061
```

Expected: all three jobs pass; each direct and public result reports `passed`,
with export and cleanup verified. The workflow uploads result artifacts. This is
a scripted-provider mechanics check; the live OMP source-read receipt has
separate requirements and scope.

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
`python3 -m venv` and `pip install -r requirements-ci.txt`. [Full conformance](conformance-2b7dc8ac.json) at product checkpoint `2b7dc8ac` reported 900 checks and zero failures. ARM64 Linux model images were rebuilt from installer-generated contexts and
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
