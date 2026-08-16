# N1-D — E1-C1 legacy-SSR venue E2E: REAL pipeline demonstration

**VERDICT: SSR-venue E2E DEMONSTRATED (y) — through the REAL production i18n-inlining pipeline at the pin (d827ba9005).**

## Pipeline (all real pin-source code, esbuild-bundled)
1. `createI18nOptions` (packages/angular/build/src/utils/i18n-options.ts — bundled as i18n-options.bundle.mjs): workspace metadata `i18n.locales['../../../../evil-locale']` — the KEY is accepted UNVALIDATED and becomes `subPath` (the `ensureValidSubPath` guard applies only to explicit subPath OPTIONS, not the key).
2. The `configureI18nBuild` locale-data loop (i18n-webpack.ts:57-89 VERBATIM) + `findLocaleDataPath` (:145-153 VERBATIM): the deep-dot key resolves via `createRequire(projectRoot + '/')` to the ATTACKER file `fixture/node_modules/evil-locale.js` → `desc.dataPath`.
3. `BundleActionExecutor` (action-executor.ts — REAL, Piscina worker threads) → the REAL `process-bundle.ts` worker (`inlineLocales` → `inlineLocalesDirect` → `loadLocaleData`): the attacker file is read, Babel-optimized, and **ConcatSource-prepended** into the produced main server bundle (process-bundle.ts:255-290 shape).
4. The inliner writes the bundle to `outputPath + subPath + filename` — the KEY escape lands the write OUTSIDE the output base (`builder-tmp/evil-locale/`, 4 levels out of the 4-deep base) — the member-A2 write escape demonstrated in the real pipeline.
5. `node` on the produced bundle: **the attacker top-level code executes FIRST at module load** (SSR boot-time): `[ATTACKER-EXEC] SSR-VENUE-E2E-7f3c1e load-count=1`.

## Negative control (benign locale `fr`)
- dataPath resolves IN-PACKAGE (`fixture/node_modules/@angular/common/locales/global/fr.js` — benign data); the write lands INSIDE the output base (`builder-tmp/1/2/3/4/fr/main.js`); the produced bundle has **0 attacker markers**; runtime prints no ATTACKER line.

## Evidence
- `/tmp/n1d/` : run-driver.mjs (driver), pb.worker.cjs (real process-bundle worker bundle), executor.cjs (real executor, worker path patched), i18n-options.bundle.mjs (real createI18nOptions), malicious-main.js / fr-main.js (produced bundles), fixture/ (workspace: tsconfig, xlfs, evil-locale.js, benign fr locale data), emitted/main.js (input), out/ (landing dirs).
- The synthetic input main.js is DATA (the legacy server bootstrap shape); the pipeline is the real code. A full webpack server build of a real app was not run (webpack infra not spun up) — the option-normalization + resolution + inlining + write + execution chain are the load-bearing proof points, all REAL.
