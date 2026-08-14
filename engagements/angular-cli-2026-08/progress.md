# progress.md — angular-cli-2026-08

Newest first.

## 2026-08-14 — SCAFFOLDED AND SIGNED (not started)

Engagement created from `_TEMPLATE`. **`scope.md` §14 is SIGNED** — operator sign-off in session on
2026-08-14, granting **the same authorizations already held on `angular-dev-infra-2026-08`**,
designed for a long-running run: a six-hour-minimum exhaustion run at maximum impact, with the
stopping contract in the goal prompt.

**Canonical kernel attestation is still pending.** The allowed-signers files were copied from
dev-infra because the operator key is the same, but the signed initialization challenge was
deliberately NOT copied — a challenge signature covers one engagement's exact bytes, and reusing it
would assert an attestation the operator never made over this scope. Generate a fresh challenge and
have the operator sign it before the kernel treats this engagement as activated.

- **Target:** `github.com/angular/angular-cli`, tier **OT0**, primary-verified from
  `google/bughunters` → `external_repositories.txtpb` (fetched 2026-08-14).
- **Pin at scoping:** `d827ba9005b86b23d05ee7c62c0823367aa245c1` (2026-08-14T16:05:57Z, `main`).
  Round 0 re-pins.
- **Why this target:** 3 of 4 OT0 Angular repositories are still untouched, and we just spent an
  engagement inside `angular/dev-infra` building context on the shared build, CI and release
  machinery. That context transfers directly and decays if unused. Full roster and coverage:
  `docs/research/oss-vrp-tier-coverage.md`.

### Verified at scoping (not assumed)

- `packages/`: `angular`, `angular_devkit`, `ngtools`, `schematics`
- 15 published npm packages per `.monorepo.json`: `@angular/cli`, `@angular/build`, `@angular/ssr`,
  `@angular/create`, `@angular/pwa`, `@angular-devkit/{architect,build-angular,build-webpack,core,schematics,schematics-cli}`,
  `@ngtools/webpack`, `@schematics/angular`, `devkit`, `@_/builders`
- `.github/workflows/`: `ci.yml`, `pr.yml`, `dev-infra.yml`, `codeql.yml`, `perf.yml`,
  `scorecard.yml`, `assistant-to-the-branch-manager.yml`
- `.ng-dev/` present — this repo **consumes** `angular/dev-infra`

### Calibrated expectation — recorded BEFORE the run

`angular-cli` is a mature, heavily used, CodeQL-scanned Google repository with a public security
policy and an active maintainer team. **The honest prior is: mostly solid, with the realistic yield
in the supply-chain and CI surfaces rather than in library logic.**

**A good outcome:** both SCC lanes (release path, CI/workflow path) covered-dry with proof strategies
written and sub-conditions enumerated, plus one or two confirmed Product-Vulnerability findings with
runnable PoCs. Read that as success, not as a thin result.

**The failure to avoid** is not a low finding count. It is two specific things:
1. burning the run chasing the $31,337 Supply-Chain ceiling while the CI surface goes unexamined;
2. filing a `dev-infra` defect under this engagement's name — see `scope.md` §4.

This is calibration for reading the result. It does not reduce the effort contract.

### Roster freshness — a live signal, not trivia

The tier file held **71** repositories (26 OT0, 45 OT1) when `angular-dev-infra-2026-08` fetched it
on 2026-08-12. It holds **73** (26 OT0, **47** OT1) on 2026-08-14. Two OT1 repositories added in two
days. **Re-fetch at Round 0** and record any change; do not trust a two-day-old roster.

### Not yet done — the operating agent fills these

- [x] operator signs `scope.md` §14 — done 2026-08-14 (in-session)
- [ ] fresh initialization challenge generated and operator-signed (kernel activation)
- [ ] re-pin at Round 0; record identity and any move off HEAD
- [ ] re-fetch the tier file; confirm OT0 still holds
- [ ] history sweep recorded as abstract shapes in `recon-signals.md` (no diffs)
- [ ] environment preflight (node, pnpm, bazel, install, test suite) — blockers verbatim
- [ ] local lab built ONCE and persisted, one-command bring-up
- [ ] `recon-signals.md` activation table completed, baseline controls captured
- [ ] PROOF STRATEGY written for each SCC lane, decomposed into sub-conditions
- [ ] attribution boundary applied: any dev-infra root cause recorded in `cascades.md`, not filed here
- [ ] family registry seeded, blind round 0 launched
