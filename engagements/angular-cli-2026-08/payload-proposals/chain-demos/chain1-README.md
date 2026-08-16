# Chain 1 — Cloned-Repo Delivery Chain: end-to-end fixture

**Chain:** an attacker-authored Angular repo ships `.yarnrc`/`.npmrc` → attacker registry + malicious
`dist-tags` (**W1**) · malicious `angular.json` (`outputPath`, `cli.cache.path`, `i18n.locales` keys)
(**M3** delete + case-guard root-delete, **D2** cache purge, **E1-C1** webpack write escape) · poisoned
schematics defaults (**D1**, no `--route` flag). The dev runs the README workflow and the five
impact planes fire **silently**.

**Version:** 2026-08-15, E2-R9/DEMO-C1 hardening (added hop H7 — the `.npmrc`-native silent redirect).
Results: **9/9 hops pass in BOTH malicious and negative modes.**

## What the fixture proves (hop by hop)

| Hop | Claim | Proof |
|---|---|---|
| H1a | Real metadata fetch hits the repo-configured registry; the raw malicious `dist-tags` value is consumed unvalidated | real `npm view attacker-pkg --json` → registry.log `GET /attacker-pkg`; E404 output names the raw value verbatim |
| **H7 (NEW)** | **The repo `.npmrc` alone (PM-native precedence, NO `--registry` flag anywhere) redirects npm to the attacker registry — the silent-redirect channel (C1A)** | `npm view attacker-pkg --json` from repo cwd hits the attacker registry (`freshHit=true`, `registry=http://127.0.0.1:48731/` from `npm config get registry`); negative mode proves the benign value carries no payload |
| H1b | The yarn-classic dist-tags VALUE flows into the win32 shell:string specifier (quote-wrap, no escaping) | compiled `getManifest` builds `info --json --verbose "attacker-pkg@1.0.0" & echo W1-MARKER>%TEMP%\w1-poc & ""` |
| H1c | POSIX is safe (array spawn) — the execution rung is Windows-only | no W1 marker on this host |
| H2 | `outputPath: ../victim-out` → `deleteOutputDir` deletes outside the workspace (legacy builder) | victim marker deleted; negative (in-workspace `dist/app`) untouched |
| H3 | `cli.cache.path: ../victim-cache` → `purgeStaleBuildCache` deletes the stale sibling under the attacker-chosen base, silently, on every default build | stale marker gone; current version dir kept |
| H4 | i18n locale KEY `../../escaped-locale` becomes the default subPath → write lands outside the output base | `subPath=../../escaped-locale`, resolved `/tmp/escaped-locale`, outsideBase=true, written=true; negative (`en`) stays in-base |
| H5 | Workspace schematics-defaults `route` (no `--route` flag) reaches the generated routing module with the payload | `D1-MARKER` present in the generated file; negative benign route only |
| H6 | The M3 case-guard `resolvedOutputPath === root` string compare is bypassed by a case-variant on case-insensitive APFS | control (exact root) throws; case-variant deletes the workspace-root contents |

## How to reproduce

```bash
# 1. start the synthetic registry (127.0.0.1 only; serves malicious + benign packuments)
cd <fixture-dir> && node registry-server.mjs &     # port 48731; logs to registry.log
# 2. malicious run (malrepo/ ships .yarnrc, .npmrc, angular.json, schematics defaults)
node run-chain1.mjs                                 # expects ROOT=/tmp/chain1 with malrepo|goodrepo + lib/
# 3. negative control (goodrepo/ benign values)
node run-chain1.mjs --negative
# results: /tmp/chain1/chain1-results.json (9 hops, exit 0 = all pass)
```

The driver loads the **compiled pin modules** (package-manager, package-manager-descriptor, host,
delete-output-dir, purge-cache, i18n-options) from the lab build at
`upstream/angular-cli/dist/bin/packages/angular/cli/src/...` and the fixture `lib/` bundles — the
same real code the CLI ships. The registry server binds 127.0.0.1 only; no wires.

## The win32 caveat (the single evidence-grade gap)

- **H1b constructs the exact shell:string** the win32 spawn receives (`host.ts:157-164`, `shell:true`,
  `requiresQuoting` at `host.ts:110`). **H1c proves POSIX does NOT execute it.**
- Physical `cmd.exe` execution of the payload is **environment-blocked** (Darwin/arm64; no Windows
  host in the lab; wires forbid third-party systems). Running `run-chain1.mjs` on any Windows host
  (with a Windows-built CLI) closes the rung — see `WINDOWS-E2E-FIXTURE.md` in the W1 finding.
- Everything before and after the spawn is demonstrated with real commands and compiled code.

## Chain-level negative controls

- **goodrepo/** benign values: no registry redirect value, no deletion, no purge, no escape, no
  payload in the generated route — 9/9 with the payload absent.
- Anti-cheat: every hop uses real `npm`/compiled modules; the registry log is the only oracle for
  the HTTP hops; the driver asserts per-hop and exits non-zero on any failure.

## Filing note

The chain combination is **NOVEL** (no public disclosure of the combination; per-finding novelty:
M3/D2/E1-C1 NOVEL, D1/W1 NEAR-MISS with the maintainer doctrine documented in the findings).
The Chain 1 verdict is **CONFIRMED (mechanism-complete; W1 cmd.exe hop execution-pending)**;
survived the E2-R7 kill-pair (KP-C1 SURVIVES-NARROWED — the `--ignore-scripts` bypass + invisible
firing + persistence past the dev machine are the deltas vs install-script equivalence).
