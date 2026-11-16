# OMP Responses tool-call identity regression

A pinned OMP 18.20.0 Responses parser produced the synthetic composite call ID
`call-public-lead-1|fc_public-lead-1`. Before the host fix, the actual OMP
`host_tool_call` event rejected that ID before dispatch. The [before receipt](before.json)
records the failure-first scenario and hashes of the scenario and source as they
were then. The [after receipt](after.json) records the same parser-produced ID
successfully reaching an owned host operation, with reply correlation, duplicate
counting, changed-argument refusal, distinct components, length bounds and malformed
IDs checked. Its source hashes identify the tested post-fix files.

The [parser receipt](parser-replay.json) comes from a separate offline replay of the
actual pinned OMP Responses parser against the fixture's synthetic SSE frames. It
made no provider call. The parser replay script and its exact hash are retained in
the private task workspace; this receipt is not an end-to-end native model run.
The [adapter regression summary](adapter-regression.json) records the existing
controlled protocol subprocess checks for both runtimes.

From the repository root, with the pinned CI requirements installed, repeat the
adapter boundary scenario:

```sh
python3 evals/native-qualification/smoke/check_omp_responses_tool_id_e2e.py --output /tmp/omp-tool-id-result.json
```

Expected: six checks pass. This command uses the same representative synthetic ID;
`--parser-output` can instead consume the offline parser replay JSON containing
`stopReason`, `toolNames` and `toolIds`. The scenario runs the real adapter event
handler with an owned host operation; it does not start a model or external provider.
