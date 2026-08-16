# Angular CLI — uncontained configuration-driven directory deletion (output paths + cache path)

**Family report combining M3 (outputPath deletion family) and D2 (cli.cache.path purge) · Angular CLI · Pin `d827ba9005b86b23d05ee7c62c0823367aa245c1` (2026-08-13) · verified unfixed at main 2026-08-15**

## Opening (delta-first)

Two builders' options take workspace-config strings and turn them into **recursive directory deletion with no containment and no confirmation** — and a third routine command (`ng cache clean`) does the same through a path that fires **automatically on every default build**. A project you clone can wipe arbitrary directories on your machine, or on a CI runner, the first time you run the documented commands — silently, with no traversal validation, no prompt, and (for the cache path) no output line at all. The write side of this family was already fixed twice by the maintainers; **the delete side was proposed and never merged**, and it is still live on `main` today. These are not three separate defects; they are one missing containment discipline across two option-normalization chokepoints.

## Shared root cause

Workspace-config path values (`outputPath`, `cli.cache.path`) are resolved and passed to `fs` deletion utilities **without a root-bound containment check**:

- `packages/angular/build/src/utils/delete-output-dir.ts` — `rm` of every entry under the resolved output path; the ONLY guard is `resolvedOutputPath === root`, a **case-sensitive string comparison** (see the case-guard below).
- `packages/angular/build/src/utils/normalize-cache.ts:43` + `packages/angular/cli/src/commands/cache/utilities.ts:27` — **byte-identical twin** `getCacheBasePath` helpers with **no root guard at all**, feeding force-recursive purge.
- Callers: `deleteOutputDir` has exactly 3 (application `index.ts:176`, legacy browser `:109`, legacy server `:236`); `purgeStaleBuildCache` has **9 builder entrypoints** through the two twin helpers.

Same trust boundary for every member: the value is a workspace-config string (attacker-authored project the dev clones, or a PR-shipped `angular.json` a CI build consumes). No remote trigger, no privilege gain — **data loss, availability, and (with the write variants) integrity**, on the developer machine and in CI.

## Member 1 — M3: `outputPath` delete (Medium)

`outputPath` from the workspace config (or `--output-path`) → `deleteOutputDir` → contents recursively deleted outside the workspace. Confirmed in **both** the legacy webpack builders and the flagship application builder — the very file where the write-path fix landed (`8358805d3`) — the application DELETE path (`application/index.ts:176-178`) is itself unguarded. The write side was fixed a second time by `bd413b0eb`/`#33312` (2026-06-04, main-only, browser-dir escape); **the delete side has never been fixed**. A delete-guard was proposed in **#32873 and never merged** — disclosed-but-unfixed, which strengthens this report. A PR-triggered `ng serve` RCE sibling (`#33479`) was treated as security and merged (fix `2d3eb7fb3`), confirming the CI-execution class is in scope for the maintainers; the delete variants were not.

**Compiled-module PoC on file:** `outputPath: ../victim-out` → victim marker deleted; negative control (application write path) rejects the same `../`.

## Member 2 — M3 amplifier: the case-guard bypass on case-insensitive filesystems (verified, compiled)

The only containment — `resolvedOutputPath === root` — is a **case-sensitive string compare**. On case-insensitive filesystems (macOS default APFS, Windows NTFS, GitHub Actions macOS runners), an `outputPath` set to a case-variant of the workspace root bypasses the guard: `resolve` preserves the input case, the comparison fails, `readdir` resolves to the real root, and the **workspace root itself (sources, node_modules, .git) is deleted**. Verified end-to-end with the compiled production module: the exact-root control throws ("Output path MUST not be project root directory!"), the case-variant call deletes the root contents (`readdir` → `[]`). On case-sensitive filesystems (Linux) the variant path ENOENTs and returns early — no impact there. The fix must case-fold/canonicalize both sides of the comparison; **at main (2026-08-15) `delete-output-dir.ts` is byte-identical to the pin — the bypass survives.**

## Member 3 — M3 write-variant amplifiers (Low, same family)

- **extract-i18n** (both builders, byte-identical twins): `outFile = path.resolve(workspaceRoot, outputPath/outFile)` → `fs.writeFileSync` — arbitrary single-file **overwrite/truncate** + `mkdir -p` anywhere, no containment in either implementation (compiled write PoC on file; application-builder `isSubDirectory` rejects the same path — the discriminator). Content is escaped structured text (XML/JSON) — no raw bytes, no code execution.
- **Legacy prerender**: route strings from `options.routes`/`routesFile` flow unvalidated into `join(join(outputPath, route), 'index.html')` — a `..` route escapes the output base (join-semantics verified); the `routesFile` read side traverses at `join(workspaceRoot, routesFile)`.

## Member 4 — D2: `cli.cache.path` purge (Medium)

`ng cache clean` force-recursively deletes the configured `cli.cache.path` — **uncontained and silent** (`ng cache clean` prints no output line at all; `force` suppresses errors; there is no root-equality guard of any kind in the cache path, unlike M3's). Demonstrated with the real built CLI at the pin. A symlink-cycle in the hostile path additionally hangs `ng cache info` (folded: same root cause, add lstat/cycle guards with the fix).

## Member 5 — D2 amplifier: the purge is UNCONDITIONAL (the keystone hop)

`purgeStaleBuildCache` runs **on every default local build** — `ng build`/`ng serve`/`ng test` — across **9 builder entrypoints**. No malicious command is needed: a crafted `angular.json` value deletes the attacker-chosen directory whenever the developer runs any routine build. This is what makes the family dangerous in **CI**: a fork PR shipping a malicious `angular.json` to a repo whose CI runs `ng build` on PR content (the config-as-data shape — installs with `--ignore-scripts` or sandboxed) deletes checkout/runner paths **cross-platform**; the M3 case-guard adds the macOS root-delete. Wire-level demonstration on GitHub-hosted runners is operator-gated (spec on file).

## Impact (honest)

- **Confirmed:** uncontained recursive deletion via real build paths and the real cache command (compiled + real-command PoCs); workspace-root deletion via the case-guard on case-insensitive filesystems; unconditional purge on every default build; arbitrary single-file overwrite via the write variants.
- **Capped:** config-trust channel only (the value comes from the project being built — the same trust class the maintainers applied in the #33074/#33076 doctrine); no RCE, no privilege gain, no writes in the base members; write variants are structured content only.
- Not claimed: remote trigger, code execution, or exfiltration.

## Remediation (one discipline, four fixes)

1. **Root-bound the delete chokepoint:** add containment INSIDE `deleteOutputDir` with **case-folded/canonicalized** comparison (realpath-normalized) so every caller is protected on all filesystems — the case-guard bypass dies with it.
2. **Root-bound the cache chokepoint:** the twin `getCacheBasePath` helpers need the same containment (and lstat/cycle/depth guards for the walk); one fix covers all 9 purge entrypoints.
3. **Contain the write variants:** `isSubDirectory(workspaceRoot, resolvedOutFile)` at option-normalization in BOTH extract-i18n implementations; validate/normalize prerender route strings (reject `..`, absolute, backslash).
4. **Regression tests:** extend the `8358805d3` tests to the DELETE path, the cache purge, the extract-i18n write path, and the prerender route write; add a case-variant-of-root case on a case-insensitive filesystem.

## Replay / staleness

PoCs replayed against the compiled pin modules; **verified unfixed at main (2026-08-15)** — `delete-output-dir.ts` byte-identical (case-guard survives), application DELETE path byte-identical with no delete-side containment, legacy/extract-i18n/prerender builders all present. `bd413b0eb`/`#33312` (write path) and `2d3eb7fb3` (RCE sibling) are in-tree; `#32873` (delete guard) was never merged. Not stale.

## Suggested filing

One family report (this document) — M3 + D2 under the shared containment-chokepoint framing — severity Medium per member, with the case-guard root-delete and the CI-wipe as the marginal deltas; cite `#32873`, `#33312`/`bd413b0eb`, `#33479`/`2d3eb7fb3`, and the write-path fix `8358805d3` explicitly.

