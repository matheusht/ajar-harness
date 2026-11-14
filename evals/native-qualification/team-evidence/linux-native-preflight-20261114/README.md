# Native fixture preflight correction

The first hosted Linux native attempt stopped before model startup. The recorded Codex
tool binary was 319,346,888 bytes, exceeding the fixture's 134,217,728-byte lab
limit. The signed lab limit is now 1 GiB; the separate model workspace remains
128 MiB. [Signed-input inspection](signed-limits-after.json) verifies those limits
using inert local inputs and records the original hosted source hash and run ID.
It does not claim that the subsequent native workflow passed.

Original result bytes are retained for [Codex](codex-hosted-before.json) and
[OMP](omp-hosted-before.json) from [run 43592742977](https://github.com/matheusht/redteam-harness/actions/runs/43592742977)
at `4fc1a402b3da0fb3c6e7bd4d306430b7ed30651f`, jobs `132440735584` and
`132440735867`. Each image packaging stage passed 16 checks and cleaned its exact
owned image/probe. No model started. Codex recorded `input_workspace_limit` with
verified setup-only cleanup; OMP recorded the installer assertion without a
diagnostic.

The OMP tool installer returned nonzero, but its output was previously discarded.
The fixture now retains its exit code and the first 2,048 input bytes of stdout
and stderr, passes each through the existing publication filter, and marks
truncation. Rejected diagnostics become `[diagnostic redacted]`. The production
installer is unchanged; its actual failure still needs a hosted diagnostic run.

[Four failure cases](installer-diagnostic-e2e.py) were written and observed failing
before that diagnostic change: plain installer failure, sensitive output,
oversized output and successful installation. They run an owned inert installer
CLI through the actual fixture's `tool_bundle` call. They do not download assets,
run a native model, use Docker, contact a provider or contact a research target.
All four pass after the change; the [before](diagnostics-before.json) and
[after](diagnostics-after.json) results bind the exact scenario source hashes.

Repeat from the repository root with Python 3:

```sh
python3 evals/native-qualification/team-evidence/linux-native-preflight-20261114/installer-diagnostic-e2e.py \
  --source evals/native-qualification/smoke/check_linux_model_native_e2e.py \
  --output /tmp/native-installer-diagnostics.json
```

Expected result: four passing checks, retained nonzero status, bounded safe
diagnostics and redaction of the synthetic sensitive marker. Actual Linux native
startup and the OMP installer cause remain unverified by these local checks.
