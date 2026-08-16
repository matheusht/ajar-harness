# BUILD-PLAN.md — angular-cli-2026-08 local lab

## Purpose

Local, disposable, operator-owned lab for white-box verification of the pinned
`angular/angular-cli` tree at `d827ba9005b86b23d05ee7c62c0823367aa245c1`. No live Angular/Google/npm
system is a target; all proofs run against the pinned source or local replicas.

## One-command bring-up

```sh
! .lab-cache/angular-cli-lab.sh
```

This sets node 24.15.0 (engines-compliant), installs via `pnpm install --frozen-lockfile`, and
reports the test command. **Persisted test command:**

```sh
export NVM_DIR="$HOME/.nvm"; source "$NVM_DIR/nvm.sh"; nvm use 24.15.0 >/dev/null
export PATH="$HOME/.nvm/versions/node/v24.15.0/bin:$PATH"
cd upstream/angular-cli
bazel test //packages/angular/build:test --test_output=errors --distdir=/Users/matheusvsky/Documents/trab/llm-redteam-harness/.lab-cache/angular-cli-distdir
```

## Toolchain (verified 2026-08-14)

| Tool | Version | Notes |
|---|---|---|
| node | v24.15.0 | engines `^22.22.3 \|\| ^24.15.0 \|\| >=26.0.0`; system node 25 NOT compliant — nvm 24.15.0 is the lab node |
| pnpm | 11.21.0 | matches `packageManager` exactly |
| bazel | 8.7.0 | matches `.bazelversion` exactly |
| vitest | 4.1.10 (store-only) | suite runs through bazel `jasmine_test`/`ts_project` rules; standalone vitest has no config in-repo |

## Blocker record (verbatim, with workaround)

- `bazel` first fetch failed for every `http_archive` (aspect rules_ts, rules_cc, bazel_features,
  rules_python, rules_pkg, rules_js, rules_esbuild, bazel-lib spawn_binary):
  `java.io.IOException: Error downloading [https://github.com/.../releases/download/...]: Connect timed out`
  — while `curl` downloads the same URLs instantly. `--host_jvm_args=-Djava.net.preferIPv4Stack=true`
  did NOT fix it. **Workaround:** pre-seed `/Users/matheusvsky/Documents/trab/llm-redteam-harness/.lab-cache/angular-cli-distdir/`
  (7 archives; fetched via curl from the URLs the lock file lists) and pass
  `--distdir=/Users/matheusvsky/Documents/trab/llm-redteam-harness/.lab-cache/angular-cli-distdir`.
  Bazel's output_base now caches all fetched repos, so later runs are network-free.

## Test suite status

- `bazel test //packages/angular/build:test` — **PASSED** (16.4s run; 3129 actions built;
  includes the `unit_test_lib` jasmine specs: path_spec, debug-id_spec, bundle-calculator_spec, …).
- This proves the toolchain + compile path; per-candidate tests are added in the lab as needed.

## Hygiene

- The lab lives under `.lab-cache/` + `upstream/angular-cli` at the harness root — both are
  cleanup-ledger items (recorded in `cleanup.md`).
- No network interaction with the real npm registry happens: `pnpm install --frozen-lockfile`
  uses the local store; any registry fixture work uses local stubs.
