# Native invocation accounting — 14 November 2026

The actual Codex 0.166.0 and OMP 18.20.0 processes ran against an owned loopback
HTTP provider fixture. The fixture returned known input, output, cached input,
and reasoning counts. It requested harmless host tools through the adapters; no
real model, credential, target, or external provider was used. macOS's network
sandbox restricted each native process to that fixture's loopback port.

Each runtime completed this workflow:

1. Three provider rounds and two host-tool calls: 66 total tokens.
2. A new invocation with one HTTP 500 retry, then two reported provider rounds
   and one host-tool call: 98 total tokens, excluding the prior invocation.
3. An invocation interrupted after one completed provider/tool round while the
   next request was pending: 60 observed tokens retained.
4. A new invocation after interruption: 66 total tokens, excluding prior use.

`native-after.json` contains the exact observed per-invocation dimensions,
completion state, fixture request inventory, native executable pins, and OMP cost
deltas. Input includes cache reads/writes; output includes reasoning. Cached and
reasoning counters are subsets, so adding them again would double-count. OMP
native `input` excludes caches, and its adapter now adds those categories to match
Codex's meaning. The fixture's OMP rates are input=1, output=2, cacheRead=0.5 and
cacheWrite=1 per million tokens. These estimates are simulated, not billed spend.
Runtime `provider_requests` and `monetary_spend` remain explicitly unavailable;
fixture requests are a test observation and do not fill those production fields.

Failure-first results preserve three observed defects and their checks:

- `omp-completion-before.json`: the real OMP process produced duplicate completion
  because final statistics readback handled settlement events reentrantly. Events
  are now deferred until that one completion is recorded.
- `omp-input-before.json`: native OMP cache exclusions made the common input field
  underreport total input (41 versus 51, including 10 cached tokens).
- `events-before.json`: controlled native protocol subprocesses exposed stale
  prior-turn notifications replacing the active Codex turn, and cumulative token
  rollback or lost dimensions erasing observed usage. Response-bound turn identity
  and monotonic session totals now prevent these. Duplicate events already passed.

Run from an integrated checkout with Python 3.11+, macOS `sandbox-exec`, and the
pinned native executables on PATH:

```sh
python3 evals/native-qualification/smoke/check_native_usage_accounting_e2e.py --output /tmp/native-usage.json
python3 evals/native-qualification/smoke/check_native_usage_events_e2e.py --output /tmp/native-usage-events.json
python3 evals/native-qualification/smoke/check_native_runtime_adapters.py --output /tmp/native-adapters.json
```

The first command expects both native workflows to pass. The second expects four
controlled event-order checks, and the third runs the two existing adapter groups.
All passed in the saved after/regression results. The authoring branch obtained
its unchanged `engagement_contract` dependency from the integrated checkout via
`PYTHONPATH`; runtime implementations and scenarios came from this branch.

This is local native accounting evidence, not live provider billing, Linux
execution, full engagement-boundary qualification, or fresh-target research proof.
Provider work without reported usage still cannot be inferred from these counters.
