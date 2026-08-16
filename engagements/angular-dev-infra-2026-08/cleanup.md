# cleanup.md — artifact ledger (chain-of-custody)

Every artifact the harness creates is recorded here with a revert action and status. Unresolved
cleanup **blocks pattern promotion** and closure. Redact secrets always.

**Nothing has been created yet.**

| Artifact | Type | Created (when) | Canary id | Revert action | Status |
| --- | --- | --- | --- | --- | --- |
| _(none)_ | — | — | — | — | — |

## Pre-registered expected footprint

| Artifact | Expected revert |
| --- | --- |
| dev-infra clone + `node_modules` + pnpm store | delete tree; record reclaimed GB |
| Bazel output base / disk cache | `bazel clean --expunge`; delete |
| `act` runner container images | `docker rmi` |
| Local mock GitHub API + recorded call logs | delete; logs retained redacted under `evidence/` |
| **Private throwaway fork** (method 3 only, wire-2 gated) | **delete the fork**; revoke every synthetic canary; confirm no Actions run remains queued |
| Synthetic canary secrets | revoke / expire; record disposal state |
| Minimized PoCs, raw output, transcripts | **retain**, redacted, under `evidence/` |

## Canary disposal

Every canary issued gets an id and a disposal state (`live / revoked / expired`). A canary that
leaves the local machine — which only happens under a wire-2 confirm — is tracked until revoked.

- `canary-f13-gcp-sink-bee61c499c88` — label `f13-gcp-sink`, issued 2026-08-13, **revoked 2026-08-13** (generated locally, never deployed anywhere; no external exposure possible). Disposal: revoked-at-source.

## Rig artifacts

| Artifact | Type | Created | Revert action | Status |
|---|---|---|---|---|
| `tmp/rig/mock-api.mjs` + `tmp/rig/calls.jsonl` | local mock GitHub API (records method/path/body/auth-shape) | 2026-08-13 | **DELETED 2026-08-14** (tree removed; log held one synthetic curl call, no target data) | closed |
| `tmp/rig/canary.py` + `tmp/rig/canaries.jsonl` | canary generator + ledger | 2026-08-13 | **DELETED 2026-08-14** (generator removed; ledger was local-only, no external exposure) | closed |

## Closure cleanup (2026-08-14)

| Artifact | Type | Revert action | Status |
|---|---|---|---|
| `upstream/dev-infra` clone (101 MB) + toolchain caches | target clone | **DELETED 2026-08-14** | closed |
| `/tmp/deepsec` (tool repo + node_modules, 1.9 GB) | scanner tooling | **DELETED 2026-08-14** | closed |
| `/tmp/deepsec-scan` (101 MB target copy + deepsec workspace w/ node_modules, 1.7 GB) | scan workspace | **DELETED 2026-08-14** | closed |
| `/tmp/deepsec-{findings,report}` + triage artifacts | scan outputs (copies; canonical evidence retained in findings/) | **DELETED 2026-08-14** | closed |
| `/tmp/opencode-key` (staged provider credential) | **CREDENTIAL** | **DELETED 2026-08-14** (zeroed by unlink; never written into the repo or engagement) | closed |
| `/tmp` scratch (PoC harnesses, dossiers, patches, report drafts) | scratch | **DELETED 2026-08-14**; canonical copies retained in findings/ + payload-proposals/ | closed |
| Canary `canary-f13-gcp-sink-bee61c499c88` | synthetic canary (generated, never deployed) | revoked at source 2026-08-13; generator deleted | closed |

**Retained (redacted evidence per finding-lifecycle §5):** `findings/F13-*/`, `findings/R8-*/`, `findings/V1-*/` (evidence, PoC, reviews), `payload-proposals/` (operator deliverables), ledgers. No secrets retained anywhere; plaintext credential values were never written to any plane.
