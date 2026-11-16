# Research autonomy: verification in progress

This file records the state of the owned engineering fixture checks. It is not a
claim that either runtime has completed the new research-autonomy workflow, that
a live provider is qualified, or that a fresh-target investigation succeeded.
Initial implementation commit: `5684d9b4578d7681239f1bcb497560f53c93df4e`.
The fixes and checks below were performed on top of that commit; the final source
commit must be recorded alongside the final rerun.

| Area | Current evidence | Outstanding proof |
| --- | --- | --- |
| M0 signed contract and preparation | Local public CLI signed fixtures passed; no real native boundary in this lane. | Joined new-policy preparation in both runtimes. |
| M1 research turns and source/tool boundaries | Existing Linux CI scenario can exercise pinned native runtimes against a deterministic provider. | Current-head results and separate model-directed live runs. |
| M2 teams and native helpers | Local team and recovery fixtures passed as engineering simulations. | Real Codex and OMP helper sessions, inherited tool authority, once-only usage and stop. |
| M3 environment and accounts | Native-boundary fixture passed 23 scenarios; mostly simulated, two local host cases. | Joined runtime environment and cleanup readback for this revision. |
| M4 evidence, experiments and closure | Export integrity checks passed locally. | Joined reviewed closure with independent evidence on the same signed engagement. |
| M5 continuity and recovery | Local runner recovery fixture passed three simulated scenarios. | Interruption and recovery of the new-policy joined run in both runtimes. |
| M6 public entry and export | Public CLI fixture and local export integrity checks passed. | Same-run verified export and cleanup after reviewed closure. |
| Active knowledge | Local implementation checks were reported separately before this run. | Native-wire read/fetch/materialize, version update, retention failure, independent evaluation and withdrawal in both runtimes. |
| Live providers | Codex native credential and one supported OMP provider credential resolve on the private host. | Actual provider acceptance, model-directed research turns and completion in both runtimes. No secret is included here. |

The real-runtime deterministic-provider workflow and simulated fixture checks are
mechanics evidence, not model-directed behavior or research qualification. Private
raw outputs live outside this repository in `/private/tmp/oslit-autonomy-e2e-20261116`.

## Local prerequisites and checks

Pinned dependencies were installed into a private virtual environment with
`python3 -m venv` and `pip install -r requirements-ci.txt`. Full conformance
reported 900 checks and zero failures. Current-bootstrap ARM64 Linux model images
were built with network disabled from the installer-generated contexts. The
bootstrap SHA-256 was `8d333b4b0b55577069020a37078c07bccec390bbd92edc17884ace4d77d3120f`.
Image IDs: Codex `sha256:6de3fed4b65ea168fd49d1263a1314992fdee1c0b88aad18943ad2d96e6adc9a`;
OMP `sha256:55420c73830e07a6d0704e528b7803ddadcd9163b007f316df977b8c5a6459cc`.
These are build receipts only. Docker Desktop on the Mac is not a Linux controller
host with the required shared cgroup identity; hosted Ubuntu is required for the
Linux model-owner scenario.

The initial boundary regression run failed two cases because its fake runtime
omitted a field present in real runtime initialization. After fixing the fixture,
a binary-read case revealed that arbitrary evidence bytes were no longer returned.
Restoring the prior lossless behavior made the complete 23-scenario boundary
fixture pass. The Mistral resolver case was written with fake credentials and
failed before adding the provider mapping; it then passed including mismatch,
disabled and ambiguous-key refusals. Neither check made a provider call.
