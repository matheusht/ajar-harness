# OMP compaction accounting — 16 November 2026

Hosted run [43928320912](https://github.com/matheusht/redteam-harness/actions/runs/43928320912)
completed the public OMP fixture, accepted its independent review and verified
export/cleanup. Its retained CLI result also reported `native_usage_invalid` for
the lead after one remote compaction. The passing workflow label did not establish
error-free continuation.

The pinned OMP 18.20.0 `SessionStatsTracker.getSessionStats()` sums assistant usage
in `agent.state.messages` and model usage in the active transcript window. It is
not a lifetime counter. `pinned-stats.json` was produced by that actual class:
replacing the active history changed its total from 300 to 15. Another replacement
changed it from 300 to 360; subtracting those snapshots would still invent an
unsupported per-invocation delta. The replay overrides only the unrelated context
display calculation; no provider or native agent process runs in this check.

`before.json` records the prewritten nine-case adapter workflow before the repair.
Normal accounting and refusal of an unexplained reset passed; committed-compaction
cases failed. `after.json` passes all nine. It drives actual OMP adapter invocation,
event handling and completion with the pinned statistics and simulated native
events. The checks cover falling and growing totals, repeated and manual
compactions, next-invocation recovery, malformed values and refusal of unsupported
reset events. `adapter-regression.json` retains the three existing controlled
Codex/OMP adapter scenarios, which also passed.

The repair recognizes a native compaction-end event only with a result object,
`aborted:false` and no skipped flag. The affected invocation completes with native
token/cost deltas unavailable and explicit missing dimensions. The next invocation
starts from its current statistics. It does not replace unavailable usage with
zero, reuse the post-compaction total as a delta, change earlier journal usage or
alter the independent provider-request ledger. Other malformed counters remain
errors. The subsequent [hosted OMP public run](../hosted-43934112061/omp-summary.json)
completed one compaction and reached reviewed closure, verified export and cleanup
without `native_usage_invalid`. Usage across that compaction remains unavailable;
the hosted result is scripted-provider mechanics evidence.

## Repeat

Use Python with the repository's pinned dependencies. The retained statistics
already supply the adapter scenario's inputs:

```sh
python3 evals/native-qualification/smoke/check_omp_compaction_usage_e2e.py \
  --stats evals/native-qualification/team-evidence/research-autonomy-20261116/omp-compaction-usage/pinned-stats.json \
  --output /absolute/private/omp-compaction-usage-result.json
python3 evals/native-qualification/smoke/check_native_runtime_adapters.py \
  --output /absolute/private/native-adapter-result.json
```

Expected outcome: nine scenario checks pass; the three controlled adapter results
pass. Source hashes in the receipts identify the checked code.

To reproduce the upstream statistics, use the installed OMP 18.20.0 package and its
dependencies. The script verifies the package version and exact source hash before
importing it. The recorded offline source replay used Bun 1.4.0 on macOS arm64;
it does not qualify that Bun version as an OSLit native runtime.

```sh
bun evals/native-qualification/team-evidence/research-autonomy-20261116/omp-compaction-usage/pinned-stats-replay.ts \
  /absolute/path/to/node_modules/@oh-my-pi/pi-coding-agent \
  /absolute/private/pinned-stats-result.json
```

This is bounded source/adapter evidence, not a new full hosted run, live-provider
research result, billing receipt or multiday continuity claim.
