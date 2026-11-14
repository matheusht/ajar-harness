# Optional owned application reset evidence

Candidate implementation, 14 November 2026, based on
`db70eada835c79c1d10bf10e4f1cecc43f1c317e`. The signed contract and workflow are in
[the implementation contract](../../../../docs/research/oslit-application-reset-contract-2026-11-14.md)
and [failure-first scenarios](../../APPLICATION-RESET-SCENARIOS.md).

The local workflow observed an owned counter change from `0` to `1`, then return
to `0` in a distinct target generation. Actual HTTP requests and private stdio
relays passed through the production capture, account gateway and journal. Docker
and native model owners were explicit simulations. The result records the target
start, request and cleanup identities, exact source hashes and replay comparison.
It does not qualify Docker isolation, SSH, a joined native workflow or research.

| Saved result | Observed outcome |
| --- | --- |
| `owner-after.json` | 13 owner/connector checks passed, including actual HTTP/stdio, response timeout, revocation and cleanup after connector failure. |
| `workflow-after.json` | Seven signed workflow families passed: contract, capture, cleanup, recovery, fresh reviewer replay, source plus two applications, and missing/stale authority. |
| `native-boundary-regression.json` | 23 boundary scenarios passed; actual host network/certificate cases are labeled separately from simulations. |
| `ordinary-application-regression.json` | Six existing limited application-capture scenarios passed. |
| `contract-regression.json` | 75 signed-contract checks passed. |
| `evidence-regression.json` | 16 evidence scenarios passed. |
| `bridge-regression.json` | Ten private relay checks passed. |
| `journal-regression.json` | Eight target-network journal scenarios passed. |
| `conformance.txt` | 900 structural checks, zero failing, using the existing Python environment with `jsonschema`. |

Files ending `before.json` retain failing checks captured before their respective
implementation or correction. The owner timeout and cleanup failures were found
in independent review. `owner-independent-review.json` and its separate replay
record the fixed owner/connector review; that limited verdict does not certify
the complete shared contract and capture changes.

The adjacent evidence, ordinary-capture and journal checks ran before the final
status field that exposes permitted baseline IDs to the worker. The final
seven-family workflow and 23 boundary scenarios include that field. The manifest
preserves each result unchanged and records current source bytes; it does not
relabel older receipts as executions of later code.

Run from the repository root with Python 3, `ssh-keygen` and OpenSSL installed:

```sh
python3 evals/native-qualification/smoke/check_application_owner_e2e.py --output /private/results/application-owner.json
python3 evals/native-qualification/smoke/check_application_reset_e2e.py --output /private/results/application-reset.json
```

Expect `status: passed`. The fixtures stop their owned counter and relay processes
before returning. No Docker daemon, SSH server, provider or external target is
contacted. `manifest.json` binds the source and saved result bytes.

The opt-in `check_application_owner_docker_e2e.py` requires an explicit disposable
Docker endpoint and an already installed image ID containing Python. Its command
and limits are documented in the scenario file. It was not run for this bundle;
actual Docker results must be retained separately.
