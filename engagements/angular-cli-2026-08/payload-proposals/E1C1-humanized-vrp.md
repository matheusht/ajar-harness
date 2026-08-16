# Angular CLI: unvalidated i18n locale keys escape the output directory and load attacker code into the bundle (executes in the browser and in the SSR server process)

**Product:** `@angular-devkit/build-angular` / `@angular/build` (webpack/legacy builder stack)
**Affected:** angular-cli at `d827ba9005b86b23d05ee7c62c0823367aa245c1` (HEAD 2026-08-13). Verified unchanged on main as of 2026-08-15.
**Severity:** Low-Medium (browser venue, CVSS 4.0) / Medium (legacy-SSR venue, CVSS 6.3). Calculator variant of the SSR venue: 8.1 if the config value is treated as remotely supplied.

## Summary

The i18n locale keys in `angular.json` are not validated, and the same validation that exists for explicit `subPath` values never runs on them. A locale key becomes the default output subPath verbatim, so a key like `../../escaped` writes build artifacts outside the configured output base. The same unvalidated key feeds `findLocaleDataPath`, which resolves a module through `createRequire(projectRoot + '/')` and Babel-transforms its content straight into the bundle. On the legacy webpack stack that content ships in the client bundle and in the SSR server bundle, where it executes in the Node process at server boot.

I confirmed this end to end through the real i18n-inlining pipeline at the pinned commit. A workspace whose `i18n.locales` carries a crafted key gets attacker-authored JS executing in its production SSR process. That is the part that matters: this is not a build-time read only, it is code the deployed app runs.

## Steps to reproduce

1. Workspace with the legacy webpack builder and a localized build. Add to `angular.json`:

   ```json
   "i18n": { "locales": { "../../../outside/evil": { "translation": "./src/locale/messages.xlf", "baseHref": "" } } }
   ```

2. Place attacker-authored JS at the resolved landing path (a repo-shipped package in `node_modules`, or a file the key's depth resolves to).

3. Run the localized build:

   ```sh
   ng build --configuration=production --localize
   ```

4. Observed: the output lands outside the output base (member A, mkdir recursive), and the attacker module content is Babel-transformed and prepended into the emitted bundle. On the legacy server stack, the server bundle executes that content at module load: the runtime demo logs `[ATTACKER-EXEC] SSR-VENUE-7f3c1e` at boot, and the benign control is clean.

The self-reproducing demo is at `findings/E1-C1-i18n-locale-key-escape/evidence/chain4/` (drivers `demo.cjs`, `check4dot.mjs`, `neg.cjs`; the SSR venue at `ssr-e2e-real/` and `ssr-venue/`).

## Impact

Proved: output-dir write outside the base via the locale key; out-of-roots file content embedded into the client bundle and executed; and, on the legacy webpack stack, attacker-authored JS executing in the SSR Node process at boot. Members E and F sit in the same family: the translation path is read without containment, and `baseHref` is emitted into index.html via `emitRaw` unescaped, so a malicious baseHref injects a script tag into the production page (CSP-conditional; strict-CSP deployments are immune).

Where I stopped: the application (esbuild) builder is contained on the write side, so these venues are limited to the legacy webpack stack, and the SSR execution is boot-time, not per-request. I ran the full pipeline through the real option normalization, resolver, and inlining functions; I did not spin up a complete webpack build in the lab.

## Root cause

`ensureValidSubPath` (`i18n-options.ts:69`, regex `/^[\w-]*$/`) guards only the explicit `subPath` options. The locale KEY (L163) and the string-form `sourceLocale` (L103-104) are never checked, and the key becomes the default subPath (L194). The mitigation exists; it is keyed to the wrong field. One regex on the key at `createI18nOptions` covers members A/B/C.

## Remediation

1. Validate locale keys and string-form `sourceLocale` with the same regex as `ensureValidSubPath` at `createI18nOptions`.
2. Contain and extension-allowlist the translation path (member E).
3. Escape or validate `baseHref` at the schema or the `emitRaw` site (member F).

## References

Novelty: no public disclosure of this mechanism. Adjacent family: #33073 (local files copied into dist via CSS url(), severity6, closed same day), and the foxllb cluster #33074/#33076 (closed under the config-trust doctrine). Current-main status: `i18n-options.ts` is byte-identical to the pin (its newest commit is the pin itself); verified unfixed on main 2026-08-15. Not stale.

