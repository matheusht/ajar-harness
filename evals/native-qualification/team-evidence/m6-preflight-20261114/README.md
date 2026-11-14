# Read-only engagement preflight — 14 November 2026

Eighteen signed-fixture workflows pass after the retained missing-module and
environment-selection failures. Each fixture uses a real ephemeral SSH signature,
a supplied executable that would leave a sentinel if started, an owned local Unix
socket and fake credential markers. The preflight never executed the sentinel,
connected to the socket or emitted the credential. Python network connections
were explicitly refused during the workflow. No provider or target was contacted.

Checks cover valid local prerequisites; missing/mismatched credential references;
changed scope/source; unsupported runtime, host and required capability; missing
executable permission; native alternate-tool config; wrong bundle/environment
platform; missing Docker socket or SSH identity; provider-route absence; target
account binding; and effect-aware initial environment selection. The Linux host
case substitutes the platform value in a subprocess and proves only that branch.
It does not establish Linux execution support.

```sh
python3 evals/native-qualification/smoke/check_engagement_preflight_e2e.py \
  --output /private/results/engagement-preflight.json
python3 tools/engagement_preflight.py --inputs /private/engagement-inputs/inputs.json
```

`inspect_engagement(inputs)` loads the signed contract, reuses native bundle and
environment inspectors, and checks credential references only in host memory.
`ready_for_runtime_check` means those local prerequisites were present. Native
startup, provider validity, daemon/image state, network containment, cleanup and
research qualification remain explicitly unverified. This command writes no
engagement record and dispatches no research.
