# DEMO-C2 — config-as-data CI-shape harness (Chain 2, in-lab)

Mimics a trusted CI pipeline that checks out PR content and runs ONLY the build (no install) —
the "config-as-data" shape that survived the E2-R2/E2-R7 kill-pairs (general fork-PR shape was
killed: an install with lifecycle scripts is already code-exec; this shape has no install).

Layout: runner/checkouts/<pr>/ = the PR content (untrusted angular.json); runner/victim-* = sibling
runner state. The driver reads the PR angular.json as-is (the build reads the untrusted config) and
drives the REAL compiled pin modules:

- HOP-M3:  deleteOutputDir(workspaceRoot, outputPath)   — findings/M3/evidence-caseguard/delete-output-dir.mjs (esbuild bundle of the pin source)
- HOP-D2:  purgeStaleBuildCache(context)                 — upstream/angular-cli/dist/bin/.../purge-cache.js (bazel-compiled pin, real)
- HOP-E1C1: createI18nOptions(projectMetadata, ...)      — upstream/angular-cli/dist/bin/.../i18n-options.js (bazel-compiled pin, real)
- HOP-CG:   deleteOutputDir case-variant of the root     — the M3 case-guard bypass (this host = case-insensitive APFS, like macOS runners)

Run: CI=1 node ci-run.mjs mal | node ci-run.mjs good | the case-variant snippet in README.

Results (2026-08-15):
- mal:  HOP-M3 PASS (escaped delete of sibling victim-out), HOP-D2 PASS (stale cache dirs deleted —
  cli.cache.path with environment 'ci' overrides the CI-disable), HOP-E1C1 PASS (locale key
  '../../../escaped-locale' -> subPath -> write landed outside the output base).
- good: all hops PASS as negatives (no outside target touched).
- case: control throws on the exact root; the case-variant WIPES the workspace root contents
  (guard is a case-sensitive string compare on a case-insensitive fs).

Verdict: config-as-data shape DEMONSTRATED in-lab. The wire-2 private-fork run (chain2-wire2-spec.md)
remains the only missing rung for the GH-runner semantics (billing, isolation, ephemerality).
