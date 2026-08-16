# M3 — Legacy webpack builders delete directory contents outside the workspace root via unvalidated `outputPath`

- **Engagement:** angular-cli-2026-08 · **Pinned commit:** `d827ba9005b86b23d05ee7c62c0823367aa245c1`
- **Surface:** `packages/angular_devkit/build_angular/src/builders/browser/index.ts:92,109` and `server/index.ts:236` → `packages/angular/build/src/utils/delete-output-dir.ts`
- **Status:** PROMOTED (2026-08-15, gates G0-G6 clear) — adversarial refuter (R2-2): **CONFIRMED —
  with escalation to the flagship application builder** (see `reviews/review-r2-2.json`)

- **Population sweep (E0-R10, SWEEP-COMPLETE):** no `deleteOutputDir` members beyond
  application / legacy-browser / legacy-server (+ internal recursion at delete-output-dir.ts:46);
  the unit-test builder's own `rm` consumes the same uncontained cache base (subdir-scoped,
  debug-flag-gated — covered by the D2-family); app-shell/prerender delegate indirectly; no
  spin-off.
- **Cascading-phase reach + durability notes (E0-R1/E1, E0-R3/E9, KP-M3):**
  (a) **run_target (MCP tool) is a genuine new caller** — `serializeOptions` passes option values
  verbatim (keys regex-validated only), so `run_target {options:{outputPath:'/any/writable/dir'}}` →
  `ng run <p>:build --output-path=…` → `options.ts:331` resolve (absolute wins, no containment) →
  the unguarded `deleteOutputDir` at `application/index.ts:176-178`. Severity delta KILLED by the
  marginal critique (the intended MCP client has shell — identical effects via direct `ng build`),
  but the caller matters for future shell-less sandboxed MCP clients.
  (b) Durability (E9): the delete fires once per build invocation (per-invocation `initial` flag;
  watch rebuilds do not re-delete); repeated standalone `ng build` invocations each re-fire the
  uncontained wipe (as filed, per-invocation).
## One sentence on why it is real

The legacy webpack browser/server builders pass `options.outputPath` **unvalidated** into the shared `deleteOutputDir`, which resolves it against the workspace root, refuses only equality with the root itself, and recursively deletes the resolved directory's contents — so an `outputPath` of `../victim` (the workspace config file or `--output-path`) silently deletes any writable directory on the developer machine, in the exact family the new application builder was fixed for (`8358805d3`).

## Mechanism

- `browser/index.ts:92` — `const originalOutputPath = options.outputPath;`
- `browser/index.ts:109` — `await deleteOutputDir(context.workspaceRoot, originalOutputPath);` (when `options.deleteOutputPath` — default true)
- `server/index.ts:236` — identical pattern.
- `delete-output-dir.ts` — `resolve(root, outputPath)`; only guard is `resolvedOutputPath === root`; then `readdir` + `rm(recursive)` of every entry (Node `fs.rm` unlinks entry symlinks without
  following them; the utility's comment about mounted/symlinked dirs refers to the output dir's own
  mount handling — the deletion primitive is the contents-wipe).

The fix `8358805d3` (v22.1.4) was thought to cover the flagship `@angular/build:application`
builder — **it covered only the WRITE path** (`isSubDirectory` at `application/index.ts:284` in
`generateFullPath`); the DELETE path (`application/index.ts:176-178`:
`deleteOutputDir(context.workspaceRoot, outputOptions.base, [browser, server])`) is unguarded, and
`base` is plain `normalizeDirectoryPath(path.resolve(workspaceRoot, outputPath))`
(`options.ts:331`) — no containment. The legacy webpack browser/server builders are likewise
unvalidated (`browser/index.ts:92,109`; `server/index.ts:236`).

## PoC (compiled module from the pinned build)

```
victim BEFORE: important-file.txt,nested,sub.txt
victim AFTER : EMPTY (deleted)
NEG1: root delete refused: Output path MUST not be project root directory!
NEG2: in-root delete ok
```
- Positive (legacy shape, `evidence/poc.mjs`): `deleteOutputDir('/tmp/del-poc/ws', '../victim')` — the exact call the legacy builders make with the raw option — deletes the outside-root directory's contents.
- Positive (application shape, `evidence/poc2.mjs`): the builder's own call shape
  `deleteOutputDir(workspaceRoot, resolve(workspaceRoot, '../victim'), ['browser','server'])` —
  unrelated contents (a.txt, b.txt, unrelated/) removed; only browser/server preserved for the
  build's writes.
- Negative control 1: root itself refused (fail-closed check present).
- Negative control 2: in-root output path deletes only its own dir (correct behavior).
- Evidence: runs against `dist/bin/.../delete-output-dir.js` from the pinned build.

Call-chain provenance (G6): the deletion is demonstrated through the real compiled module; the two-line call chain from the legacy builders is source-verified (no intervening validation). Full `ng build` webpack invocation not run in the lab (builder requires full webpack config generation); `initialize()` runs the delete **before** any webpack work.

## Trust boundary crossed

`outputPath` (workspace-config value, plain string in the builder schema) → `deleteOutputDir` → `rm -rf` outside the workspace root. Attacker-influenceable via: an attacker-authored project/template (dev runs `ng build` on a cloned repo), a schematic/tool modifying the workspace config outputPath, or `--output-path` in a scripted flow.

## Impact (honest)

- **Confirmed:** recursive deletion of any directory (and its contents) the developer can write to, outside the workspace, through the real build path — in BOTH the flagship application builder (the very file the fix landed in — partial fix) and the legacy webpack builders; silent, no traversal validation.
- **Capped:** the attack requires the developer to build a project whose config (or flag) carries the malicious path — the value comes from the dev's own invocation context. No remote trigger; no code execution; availability-only (data loss).
- Not claimed: RCE or privilege gain. Deletes only in the base mechanism (and only contents of the resolved dir, never the dir itself); the deep-phase amplifiers add WRITE variants (extract-i18n single-file overwrite — amplifier #2, Low; prerender route escape — amplifier #3, Low) — the base finding remains delete-only, the family includes the write variants at their own severity.

## Negative control

- New `@angular/build:application` builder rejects the same `outputPath` (`../`) via the `8358805d3` `isSubDirectory` validation on the WRITE path (`generateFullPath`); the DELETE path (`application/index.ts:176-178`) is itself unguarded — that is the flagship-builder escalation this finding documents. The discriminator proves the legacy path is the sibling miss, not the intended behavior.

## DEEP-PHASE AMPLIFIER (E1-R1, verified 2026-08-15): root-guard bypass on case-insensitive filesystems

- **New claim (marginal delta):** the ONLY containment in `deleteOutputDir` — `resolvedOutputPath === root` errors out on the project root — is a **case-sensitive string compare** bypassable with a case-variant of the workspace root on case-insensitive filesystems (macOS default APFS, Windows NTFS, GitHub Actions macOS runners).
- **Verified end-to-end with the compiled production module** (esbuild bundle of `delete-output-dir.ts`, evidence-caseguard/; the extract-i18n write verification artifacts are at findings/M3/evidence-x1-extract-i18n/ — see L10a inventory): control throws `Output path MUST not be project root directory!` on the exact root; `readdir(CASEV)` resolves to the real root (case-insensitive fs proven); the case-variant call deletes the workspace root's contents (sources, node_modules, .git). `resolve` preserves input case on darwin + win32 (both demonstrated).
- **Marginal delta:** the root itself becomes deletable via malicious `outputPath` — the guard's stated purpose is defeated on CI filesystems. Impact class unchanged (availability-only, config-controlled value), severity stays Medium; the containment story in the remediation must treat the guard as ineffective on case-insensitive fs (fix: compare with `fs.realpath`-normalized canonical case, or case-fold both sides).
- On case-sensitive fs (Linux) the case-variant path ENOENTs → `deleteOutputDir` returns early — no impact (negative control holds there).
- Kill-pair (E1-R4): the bypass requires the same attacker channel as the base finding (malicious config value) — no new trust boundary; marginal = the guard removal only.

## Replay / staleness

- PoC replayed twice against the compiled module at the pin. Legacy builders are still shipped and usable at the current stable release (v22.1.4; `b7940dbcb` deprecates webpack builders but they remain functional and are not removed); `git log` on `browser/index.ts` shows no traversal fix at v22.1.4. **Not stale.**

## Severity / category

- **Medium** (data-loss primitive on the developer machine, sibling miss in a just-fixed family). CVSS:3.1/AV:L/AC:H/PR:N/UI:N/S:U/C:N/I:N/A:H — see finding.json for the computed vector. Category: Product Vulnerability (CLI builder).
- Refuter round (R2-2) adjudicated CONFIRMED (reviews/review-r2-2.json); operator re-review before any filing decision.



## NOVELTY UPDATE (E2-R2/C2G): delete-guard proposal — disclosed-but-unfixed (strengthens the filing)

- Issue **#32873**: a delete-path guard was PROPOSED but **never merged** — the delete variant is disclosed-but-unfixed (vs the write path, twice-fixed). Any filing must cite #32873 explicitly: the maintainers considered the delete guard and did not ship it.
- RCE sibling context: **#33479** (PR-triggered `ng serve` RCE class) was MERGED 2026-06-29 (fix `2d3eb7fb3`, verified IN the pin) — the CI-execution class is real and was treated as security; the delete/write variants were not.

## NOVELTY UPDATE (E2-R1/C1G): upstream follow-up fix — filing must cite

- PR **#33312 / bd413b0eb** (2026-06-04, main-only) extends the application-builder WRITE containment (8358805d3 family) to the browser-dir escape — the same write-path class; the DELETE path (the base finding) and the case-guard amplifier are **unaffected** (likely still live on main — Wave D must re-verify current main before filing). Filing must state this follow-up fix explicitly (the finding is a sibling-miss in a twice-fixed family).

## CHAINSTORM CHAIN-ROLE NOTE (E2-R8): M3 is the destructive core of Chains 1 and 2

- Chain 1 (cloned-repo delivery): `outputPath: ../victim-out` in the malicious repo's angular.json → `ng build` deletes outside the workspace (fixture H2); the case-guard variant deletes the workspace root on case-insensitive fs (fixture H6).
- Chain 2 (CI sabotage): the config-as-data shape — a PR-shipped angular.json processed by a trusted CI build → runner deletion; macOS runners make the root-delete reachable (C2B verified).
- Delivery is silent: no confirmation, no output line at the delete sites.

## DEEP-PHASE AMPLIFIER #2 (E1-R2/X1, verified 2026-08-15): extract-i18n uncontained arbitrary WRITE (write-variant sibling)

- **New claim (marginal delta):** the extract-i18n builder family — BOTH implementations (`@angular/build:extract-i18n` options.ts:63-67 + builder.ts:157 and `@angular-devkit/build-angular:extract-i18n` options.ts:63-67 + builder.ts:157, byte-identical twin copies, mirroring the D2 getCacheBasePath twin pattern) — writes the serialized translation file with **zero path containment**: `outFile = path.resolve(workspaceRoot, outputPath/outFile)` then `fs.writeFileSync(outFile, content)` (+ `mkdirSync recursive` for parents). No `isSubDirectory`, no root guard, no realpath — grep confirms NONE in either builder; schema.json has no `pattern` on outputPath/outFile.
- **Impact (source-verified):** arbitrary single-file OVERWRITE/truncate anywhere the dev can write (existing config, another project's files) + arbitrary directory creation. Content is serializer-shaped structured text (XML-escaped XLIFF/XMB; `JSON.stringify` for JSON/ARB/legacy-migrate) — attacker-authored sources in the cloned-repo scenario control message text verbatim-within-escaping; **no raw bytes, no code execution**.
- **Marginal delta vs base M3:** write-variant of the same missing-containment class — direction (write vs delete), scope (single file vs recursive dirs), severity (Low vs Medium). Same trust channel (workspace-config/flag value in a cloned-repo or scripted flow). The case-guard amplifier does NOT extend (no guard exists here to bypass); unlike M3, the write is uncontained on ALL filesystems including Linux.
- **Kill-pair (E1-R4):** same attacker channel as M3 (malicious config value) — no new trust boundary; content not executable; the delta is the write capability itself.
- **Remediation (same family):** apply `isSubDirectory(workspaceRoot, resolvedOutFile)` at option-normalization time in BOTH extract-i18n implementations; extend the 8358805d3 regression test to the extract-i18n write path (its own test only covered application-builder writes).


## DEEP-PHASE AMPLIFIER #3 (E1-R8/FS-M3, verified at source): legacy prerender route-escape write (write-variant, Low)

- **New claim (marginal delta):** the legacy devkit prerender builder writes per-route `index.html` files at `join(join(outputPath, route), 'index.html')` (`render-worker.ts:143-148`) with the route string taken UNVALIDATED from `options.routes`/`routesFile` — a `..` route escapes the output base (mechanically verified with node join semantics: route `../evil` → write target outside the output base). The `routesFile` read side also traverses at `join(workspaceRoot, routesFile)` (read of arbitrary project-relative file).
- **Bound (verified):** join with a leading-slash second arg does NOT escape on POSIX (absolute-route variant bounded); the write is a single small HTML file per route (Low, integrity/availability).
- **Marginal delta vs base M3:** write-variant in the same missing-containment class (unvalidated option string → uncontained fs write); distinct site (prerender render-worker) and value (route vs outputPath); same trust channel (workspace-config options in a cloned-repo flow).
- **Remediation (same family):** validate/normalize route strings (reject `..`, absolute, backslash) at option normalization; extend the family regression test to the prerender write path.

- **Verified unfixed at main (2026-08-15, GitHub API + raw-content diff, DR3-04):** packages/angular/build/src/utils/delete-output-dir.ts is byte-identical to the pin — the case-sensitive `resolvedOutputPath === root` guard survives; the application-builder DELETE path (application/index.ts:176, clean-gated `deleteOutputDir`) is byte-identical with no delete-side containment; legacy browser/server/extract-i18n/prerender builders all still exist at main (no post-pin commits on the browser builder). `bd413b0eb`/`#33312` fixed the WRITE path only. Not stale at main.

## Remediation

1. Contain `base` at option-normalization time (`options.ts:331`) with `isSubDirectory(workspaceRoot, base)` — same place the write path is contained.
2. Add the guard **inside** `deleteOutputDir` itself (root-bound the resolved path) so every caller — the 3 shared-utility callers (application, legacy browser/server) — is protected; compare with **case-folded/canonicalized** paths (realpath-normalized) so the guard also holds on case-insensitive filesystems (macOS APFS, Windows NTFS — the E1-R1 case-guard bypass).
3. Extend the 8358805d3 regression test to cover the DELETE path (its own test only covered writes).
4. Apply `isSubDirectory(workspaceRoot, resolvedOutFile)` containment at option-normalization time in BOTH extract-i18n implementations (the E1-R2 amplifier #2 write side) and extend the regression test there.
5. Validate/normalize route strings (reject `..`, absolute, backslash) at option normalization in the legacy prerender builder (the E1-R8 amplifier #3 write side) and extend the family regression test there.
