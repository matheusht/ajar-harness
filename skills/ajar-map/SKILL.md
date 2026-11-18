---
name: ajar-map
description: Map bi-directional attack surfaces, trust boundaries, workspace Steers, and executable surface drivers at the start of an Ajar run.
---

# Ajar Map

Use this skill to build the initial component and attack-surface map, record operator `Steers`, register executable surface drivers, and enqueue bi-directional `investigate` tasks in `run.db`.

## 1. Inputs, Quote, and Orientation

1. Preview deterministic `Code` LOC scope and the `35%` COGS cap when sizing a repository or PR diff (persist a Lead Orchestrator campaign brief via `--brief-file`, disable caps on open-ended research via `--uncapped`, and carry forward prior verified state on PR runs via `--parent-run`):
   ```bash
   ajar quote <target_dir> [--diff <base..head>]
   ajar init <target_dir> [--diff <base..head>] [--brief-file <brief.md>] [--uncapped] [--parent-run <baseline_run_id>]
   ajar brief
   ```
2. Inspect the Personalized PageRank symbol graph and cohesive subsystem call cones (`--slice-cap 15000` soft focus target; workers may still inspect any caller or callee across the repository):
   ```bash
   ajar map --budget-tokens 1500 --slice-cap 15000
   ajar map --focus-file <rel_path> --focus-symbol <symbol> --budget-tokens 1500
   ```
3. Query local documentation, comments, ADRs, and test intent before labeling behavior anomalous (target docs carry `[UNTRUSTED_TARGET_DOC: verify in code]` so prose claims are always verified in code):
   ```bash
   ajar ref query --kind intent "<subsystem or symbol>"
   ajar ref query --kind reachability "<entrypoint or sink>"
   ```
4. Record explicit operator threat-model or scope boundaries as attributable `Steers` (`scope_authority` preserves autonomous finding attribution; `research_steering` marks human-guided hypotheses):
   ```bash
   ajar steer add --scope global --kind scope_authority --rule "<explicit scope or threat-model boundary>"
   ```

## 2. Surface Ranking Rules

Assign each surface one priority level based on trust boundary and state impact:

- `critical`: Unauthenticated network parsers, RPC/HTTP/GraphQL/gRPC entrypoints, cross-chain packet/proof handlers, VM state-transition hooks, or multi-tenant asset/token custody functions.
- `high`: Authenticated cross-tenant APIs, privilege-boundary transitions, signature/JWT/OAuth verifiers, deserializers, webhook fetchers, FFI/unsafe boundaries, or sandbox/plugin execution hosts.
- `medium`: Authenticated single-tenant mutations, background workers with indirect external input, or rate/accounting helpers.
- `low`: Local CLI flags, operator-only maintenance scripts, or read-only diagnostics with no secret exposure.

## 3. Bi-Directional Task Seeding (`--direction`)

Do not map external HTTP/RPC routes alone. Enqueue `investigate` tasks across all four search directions so inner state bugs and native parser bugs are never missed:

1. **`outside_in` (Entrypoint -> Sink):** Trace untrusted inputs from HTTP/RPC/CLI/contract entrypoints through middleware to state transitions.
2. **`inside_out` (High-Value Sink -> Callers):** Start at sensitive state mutations, accounting/settlement math, role/permission writes, SQL/command/template builders, and cache deserializers; trace backward to find unguarded callers.
3. **`native_ffi` (Memory / Unsafe / FFI Boundary):** Target `ext/`, `cgo`, `ctypes`, `wasm`, JNI/N-API bridges, `unsafe` Rust blocks, `@IntrinsicCandidate` intrinsics, and custom binary/archive parsers.
4. **`peer_symmetry` (Sibling Routes & Lifecycle Hooks):** Compare parallel endpoints (`v1` vs `v2`, REST vs GraphQL/batch), outbound client response parsers, and paired lifecycle hooks (`create`/`update`/`delete`, `deposit`/`withdraw`, `lock`/`unlock`) for missing checks present on peers.

## 4. Recording Surfaces, Drivers, and Tasks

1. Register every distinct attack surface with its `file:line` locus, explicit trust boundary, and optional `--requires-tags` (`ns:name` preconditions needed to trigger guarded sinks):
   ```bash
   ajar surface add \
     --name "<surface_name>" \
     --kind "<http|rpc|contract|parser|ffi|ipc|cli>" \
     --subsystem "<module>" \
     --locus "<file:line>" \
     --priority critical \
     --trust-boundary "<untrusted caller -> guarded resource>" \
     [--requires-tags "<ns:tag1,ns:tag2>"]
   ```
2. Attach an executable surface driver whenever a test target, fuzz harness, local server, or Foundry test reaches the surface:
   ```bash
   ajar driver add \
     --surface <surface_id> \
     --setup-cmd "<build or fixture setup command>" \
     --invoke-template "<command invoking the entrypoint>" \
     --teardown-cmd "<optional cleanup command>"
   ```
3. Enqueue bi-directional `investigate` tasks tied to each `critical` and `high` surface:
   ```bash
   ajar task add \
     --kind investigate \
     --direction <outside_in|inside_out|native_ffi|peer_symmetry> \
     --title "<specific boundary, sink, or peer-symmetry check>" \
     --surface <surface_id> \
     --subsystem "<module>" \
     --locus "<file:line>" \
     --priority high
   ```
4. Export the deterministic `Platform` component and attack-flow graph when inspecting coverage:
   ```bash
   ajar export-graph --output graph.json
   ```

## Exit Check

Verify that `ajar surface list` and `ajar task list` cover external entrypoints (`outside_in`), critical state sinks (`inside_out`), native/unsafe bridges (`native_ffi`), and sibling route/hook pairs (`peer_symmetry`). Closeout gate `G1` blocks run completion if zero surfaces exist or if any `critical` or `high` surface has zero completed tasks under `exhaustive-high`.
