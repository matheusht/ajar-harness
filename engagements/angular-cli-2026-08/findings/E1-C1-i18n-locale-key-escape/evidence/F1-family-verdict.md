# F1 VERDICT — E1-C1 i18n locale-key family sweep (verified at pin d827ba9005)

## LOCALE-PATH TABLE

| # | Site (file:lines) | Flow | Verdict |
|---|---|---|---|
| A1 | `packages/angular/build/src/builders/application/i18n.ts:121-130` | locale KEY → `subPath` default → `join(subPath, file.path)` → `generateFullPath` (index.ts:258, no re-containment) → `mkdir+writeFile` outside output base | **E1-C1 core member (output escape, write)** |
| A2 | `packages/angular_devkit/build_angular/src/utils/output-paths.ts:17` (webpack twin) | `join(baseOutputPath, i18n.locales[l].subPath)` + `mkdirSync recursive` | **E1-C1 core member (same class)** |
| A3 | `packages/angular_devkit/build_angular/src/utils/process-bundle.ts:192-197` (webpack twin) | `path.join(outputPath, subPath, filename)` + `writeFile` | **E1-C1 core member (same class)** |
| B | `packages/angular/build/src/utils/i18n-options.ts:103-104,118-121` | string-form `i18n.sourceLocale` bypasses ensureValidSubPath → becomes `subPath` default → same sinks as A | **E1-C1 validation-gap extension (same root cause)** |
| C | `packages/angular_devkit/build_angular/src/utils/i18n-webpack.ts:52-56` + `findLocaleDataPath` (:145-153) → `webpack-server.ts:290` (`webpackConfig.entry['main'].unshift(dataPath)`) / `process-bundle.ts:161-168` (`loadLocaleData` readFile) | locale KEY → `projectRequire.resolve(path.join('@angular/common/locales/global', locale))` → arbitrary module RESOLUTION + LOAD (webpack entry) / READ (readFile) | **DISTINCT SINK (module load; webpack-only)** |
| D | `packages/angular/build/src/utils/server-rendering/manifest.ts:86-89` (app-builder SSR) | subPath → `entryPoints[subPath] = () => import('./${subPath}/main.server.mjs')` → generated manifest (execute-build.ts:314-318) consumed by the server app engine | **DISTINCT SINK (server-runtime dynamic import escape; app-builder SSR-only)** |
| E | `packages/angular/build/src/builders/extract-i18n/options.ts:43` + `application-extraction.ts` | createI18nOptions used, but no subPath → filesystem flow | **CLEAN for this family** (its own write issue = X1/M3 amplifier #2) |

## ROOT CAUSE (single)

`ensureValidSubPath` (i18n-options.ts:69, `^[\w-]*$`) guards ONLY the explicit object-form `subPath` field (L128, L176). Locale KEYS (`Object.entries(metadata.locales)` at L163) and string-form `i18n.sourceLocale` (L103-104) are never validated, and both become the default `subPath` (`subPath ?? locale`, L185; `rawsubPath ?? i18n.sourceLocale`, L126). The workspace JSON reader treats `i18n` as a free-form extension (reader.ts:24) and the `localize` builder option is boolean-or-string[] without pattern constraints (application/schema.json:427-433).

## FAMILY-WIDTH: 4 members (A1/A2/A3 core + B same-root + C + D distinct sinks)

E1-C1 (the deepsec finding, filed against i18n-webpack.ts) is the CORE member, not unique. The family spans both builder stacks:
- App builder (esbuild): A1 (write), D (SSR import).
- Webpack builders: A2/A3 (write), C (module load).
- Shared: B (string-form sourceLocale — the guard-bypass that deepsec named).

## E1-C1-UNIQUENESS: NOT UNIQUE — family is wider (4 members, 1 root cause)

The finding package must be framed as a FAMILY: "unvalidated i18n locale identifiers bypass ensureValidSubPath → output-dir escape (app+webpack), webpack locale-data module load, and SSR runtime import escape". Members C and D are the highest-impact siblings (module load — code from an attacker-chosen module bundled/imported in the dev-server/server process), each needing compiled verification before any claim lands.

## Severity (config-controlled value; same trust channel as M3/D2 — malicious/cloned workspace metadata)

Low-Medium: write-outside-output (integrity/availability) + module load (C, webpack dev-server) + server-runtime import escape (D, SSR). Code-exec strength for C/D conditional on the resolved module being attacker-controlled — the same cloned-repo/supply-chain precondition as the base findings.

## Notes for the parent

- Kill-pair/remediation: validate locale KEYS and string-form sourceLocale with the same `^[\w-]*$` (or a stricter BCP-47-ish pattern) at createI18nOptions — single choke point; extend to `localize` schema.
- Members C/D need compiled-module verification (webpack entry load + manifest import) in the R4/R5 kill-pair round before the E1-C1 package promotes.
