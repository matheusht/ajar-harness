Title: Angular CLI i18n locale keys bypass the subPath validation and ship attacker-authored JS into the client bundle and the legacy SSR server

**Report as (Google OSS VRP vulnerability type):** Path traversal + server-side code execution (locale key escapes validation; attacker-authored JS executes in the client bundle and the SSR server process) — form category: **Path Traversal** for the write/read escape; **RCE (server-side)** for the SSR venue (file the SSR venue, so: RCE).

Hi Angular CLI team,

I found that locale identifiers in workspace i18n config are not validated the way explicit `subPath` values are, and the key becomes a filesystem path verbatim. That produces an output escape, and worse, the locale-data resolution can load an attacker-authored file into the build, where it executes in the client bundle and, on the legacy SSR stack, inside the production server process. Full details below.

## Product and version

- @angular/cli, pinned commit d827ba9005 (2026-08-13). i18n-options.ts at main is byte-identical to the pin (its newest commit is the pin itself); verified 2026-08-15.

## Severity

- Browser venue (webpack client bundle): Low-Medium, CVSS:3.1/AV:L/AC:H/PR:N/UI:N/S:U/C:L/I:L/A:N (4.0).
- Legacy-SSR venue (server bundle): Medium, CVSS:3.1/AV:L/AC:H/PR:N/UI:R/S:U/C:H/I:H/A:H (6.3). Attacker-authored JS executes in the SSR Node process at server boot. A remote-supply variant computes to 8.1; I file the honest 6.3.

## Summary

`ensureValidSubPath` (i18n-options.ts:69) applies a `/^[\w-]*$/` check to explicit `subPath` options only. Locale KEYS (`i18n.locales`) and string-form `sourceLocale` never pass through it, and the key becomes the default subPath (`subPath: subPath ?? locale`). Two consequences:

1. Write side: the key escapes the output base (webpack stack; mkdir + write outside). Compiled demo on file.
2. Read side, member C: `configureI18nBuild` resolves `@angular/common/locales/global/<key>` with `createRequire(projectRoot + '/')`; a deep-dot key lands on an attacker file (5-dot: parent-of-workspace file; 4-dot: a repo-shipped or dependency-confusion package). The content is Babel-transformed and embedded in the bundle. It executes in the client bundle, and in the legacy-SSR server bundle at boot through the real i18n-inlining pipeline (I ran that end to end; marker executes, benign control clean).

Two more members in the same family: member E (translation path read, uncontained) and member F (`baseHref` written into index.html with `emitRaw`, no escaping; a malicious value injects a script tag into the production page; CSP-conditional execution).

## Steps to reproduce

1. Workspace with:

```json
// angular.json
{ "i18n": { "locales": { "../../../../evil": { "translation": "src/locale.xlf" } } } }
```

2. Place an attacker module at the landing path (or ship it as a repo package for the 4-dot variant).
3. Run the webpack/legacy localized build. The module content lands in the bundle and executes (client and legacy-SSR server).

The evidence dirs (chain4/) are self-reproducing: `node demo.cjs`, `node check4dot.mjs`, `node neg.cjs`, and the SSR venue demos.

## Impact

What I proved: the escape and the module load through the real production pipeline, with execution in both venues. The SSR execution is boot-time module evaluation, not per-request. What I did not prove: nothing runs on the application/esbuild builder (that stack re-contains the write path), and the attacker file must actually be reachable (repo package or landing path).

## Prior art and the delta

- No disclosure of this mechanism found (searched 2026-08-15). The adjacent class (local file content into dist) is #33073, triaged severity6 and closed same-day without a fix, under the config-trust doctrine.
- The delta: the mis-keyed guard (the mitigation exists but protects the wrong field) and the SSR server execution venue.

## Remediation

1. Validate locale keys and string-form `sourceLocale` with the same regex at `createI18nOptions` (one change covers the family).
2. Contain and extension-allowlist the translation path (member E).
3. Escape or validate `baseHref` at the schema or the `emitRaw` site (member F).
4. Extend the localize schema and enforce it on the build path.

Happy to retest, and to adjust the venue split if triage prefers a single severity.
