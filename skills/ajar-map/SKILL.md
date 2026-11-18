---
name: ajar-map
description: Map attack surfaces, trust boundaries, state invariants, and executable surface drivers at the start of an Ajar run.
---

# Ajar Map

Use this skill to build the initial attack-surface map, register executable surface drivers, and enqueue prioritized `investigate` tasks in `run.db`.

## Inputs and Orientation

1. Inspect the Personalized PageRank symbol graph within a bounded token budget:
   ```bash
   ajar map --budget-tokens 1500
   ```
2. Narrow onto high-centrality entrypoints or state modules when needed:
   ```bash
   ajar map --focus-file <rel_path> --focus-symbol <symbol> --budget-tokens 1500
   ```
3. Query local documentation, comments, ADRs, and test intent before labeling behavior anomalous:
   ```bash
   ajar ref query --kind intent "<subsystem or symbol>"
   ajar ref query --kind reachability "<entrypoint>"
   ```

## Surface Ranking Rules

Assign each surface one priority level based on trust boundary and state impact:

- `critical`: Unauthenticated network parsers, RPC/HTTP/GraphQL/gRPC entrypoints, cross-chain packet/proof handlers, VM state-transition hooks, or multi-tenant token/asset custody functions.
- `high`: Authenticated cross-tenant APIs, privilege-boundary transitions, signature/JWT/OAuth verifiers, deserializers, webhook fetchers, or sandbox/plugin execution boundaries.
- `medium`: Authenticated single-tenant mutations, background workers with indirect external input, or rate/accounting helpers.
- `low`: Local CLI flags, operator-only maintenance scripts, or read-only diagnostics with no secret exposure.

## Recording Surfaces and Drivers

1. Register every distinct attack surface with its `file:line` locus and explicit trust boundary:
   ```bash
   ajar surface add \
     --name "<surface_name>" \
     --kind "<http|rpc|contract|parser|ipc|cli>" \
     --subsystem "<module>" \
     --locus "<file:line>" \
     --priority critical \
     --trust-boundary "<untrusted caller -> guarded resource>"
   ```
2. Attach an executable surface driver whenever a test target, fuzz harness, local server, or Foundry test can reach the surface:
   ```bash
   ajar driver add \
     --surface <surface_id> \
     --setup-cmd "<build or fixture setup command>" \
     --invoke-template "<command invoking the entrypoint>" \
     --teardown-cmd "<optional cleanup command>"
   ```
3. Enqueue concrete `investigate` tasks tied to each `critical` and `high` surface:
   ```bash
   ajar task add \
     --kind investigate \
     --title "<specific boundary or invariant check>" \
     --surface <surface_id> \
     --subsystem "<module>" \
     --locus "<file:line>" \
     --priority high
   ```

## Exit Check

Verify that `ajar surface list` and `ajar task list` cover all external entrypoints and privilege boundaries before leasing `investigate` tasks. Closeout gate `G1` blocks run completion if zero surfaces exist or if any `critical` or `high` surface has zero completed tasks under `exhaustive-high`.
