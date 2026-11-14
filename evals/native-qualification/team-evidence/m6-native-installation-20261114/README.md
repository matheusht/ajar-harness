# Pinned native tool installation — 14 November 2026

Actual release/package downloads produced these private Linux arm64 bundles on
macOS. Every archive was checked against the repository lock before extraction.
No downloaded executable or package script was run.

| Bundle | Files | Bytes | Result |
| --- | ---: | ---: | --- |
| Codex 0.166.0 | 1 | 277,549,176 | Fixed ELF layout, manifest and static adapter preflight passed |
| OMP SDK 18.20.0 + Bun 1.4.4 | 17,467 | 402,980,704 | SDK/addon identity, ELF layout, sidecar, manifest and static adapter preflight passed |

The source release URLs, archive digests, resolved dependency versions and exact
bundle manifests are retained in the installation receipts. The amd64 lock entries
were read from the official release metadata but were not downloaded or executed.
The combined installed bytes are 680,529,880, within the authorized additional
storage allowance. The temporary archives were removed.

The first OMP attempt failed the existing source-manifest redaction gate on the
ordinary SDK filenames `task-specialization-advisory.md` and
`task-coordination-advisory.md`. The separate provider-token-boundaries evidence
records that fix and its positive secret controls. The SDK files were retained.

The failure-first public CLI fixture has ten passing workflows: both bundle
layouts, script nonexecution, digest failure, changed installed bytes, path
traversal, archive links, wrong platform, old Bun version, truncated download,
existing-directory preservation and a receipt alias into the bundle. The original
missing-command failures and the later alias failure are retained separately.
Fixture ELF headers do not establish executable compatibility.

Repeat using [the installation guide](../../../../docs/agents/native-tool-installation.md).
The source/result pins are in `manifest.json`. No real provider inference, Linux
execution, Docker/SSH containment or engagement qualification is claimed by these
receipts. Their status is explicitly `ready_for_environment_check` with
`execution_verified: false`.
