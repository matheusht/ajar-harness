# D2 — `ng cache clean` recursively deletes an arbitrary directory via workspace-controlled `cli.cache.path`

- **Engagement:** angular-cli-2026-08 · **Pinned commit:** `d827ba9005b86b23d05ee7c62c0823367aa245c1`
- **Origin:** deepsec cross-scan finding (slug `path-traversal-012a6d67ad`), verified by the orchestrator against source AND via the real command.
- **Status:** PROMOTED (2026-08-15, gates G0-G6 clear) — amplified in the cascading phase (E0-R2/E2 + KP-D2 SURVIVES); deep-phase note (E1-R4/L6b cache-info hang variant) folded.
- **Surface:** `packages/angular/cli/src/commands/cache/clean/cli.ts:28-34` + `packages/angular/cli/src/commands/cache/utilities.ts:27-96`

- **AMPLIFIED in the cascading phase (E0-R2/E2 + KP-D2 SURVIVES, E0-R5/R6 verified):**
  `purgeStaleBuildCache` (packages/angular/build/src/utils/purge-cache.ts:29-53) consumes the same
  uncontained `getCacheBasePath`/`cli.cache.path` and force-deletes EVERY sibling directory under the
  attacker-chosen base (only the current-version cache dir is excluded by name) — called by **9
  builder entrypoints on every build/serve/test/extract-i18n/ng-packagr invocation** (application
  /index.ts:46, dev-server ×2, ng-packagr ×2, legacy server:198, legacy browser:146, extract-i18n,
  karma — caller list verified at the pin). PoC via compiled module: all victim dirs deleted
  (orchestrator-reproduced). **Marginal delta vs as-filed:** deletion now fires AUTOMATICALLY on any
  default local build in a crafted project (cache enabled by default; CI/local switch does not
  disable it in the default dev case), not just the explicit `ng cache clean` — same root cause,
  unconditional trigger, set-deletion. Shared chokepoint (fix target): `getCacheBasePath`
  (cache/utilities.ts + normalize-cache.ts duplicate — byte-identical logic). **Family sweep (R10): 8 consumers
  total** — destructive: `ng cache clean` + `purgeStaleBuildCache` ×9 entrypoints (both covered);
  read-only: `ng cache info` (harmless walk); guarded: the tempDirectory consumer
  (command-runner.ts:68 → package-manager.ts:649 relative() containment — the in-repo positive
  control); write-only under base: application/dev-server/unit-test dump/ng-packagr cache locations
  (capped). Containing `getCacheBasePath` once per copy fixes all 8. Durability (E9): the purge re-fires on every
  invocation — no one-shot exhaustion. Scoping correction: the original sink list missed this
  occurrence.
## One sentence on why it is real

`ng cache clean` runs `rm(path, { force: true, recursive: true })` on a path taken from the workspace config's `cli.cache.path` — absolute paths are accepted unchanged, relative paths resolve with `..` escaping the workspace (and git-worktree resolution moves the base outward), there is no containment check and no confirmation — a crafted project makes a routine troubleshooting command force-delete an arbitrary directory.

## Mechanism

- `utilities.ts:27-96` `getCacheConfig`/`getCacheBasePath`: `isAbsolute(cachePathSetting)` → returned **unchanged**; otherwise resolved via the git worktree's common dir or `resolve(workspaceRoot, cachePathSetting)` — `..` segments escape the workspace root.
- `clean/cli.ts:28-34`: `rm(path, { force: true, recursive: true, maxRetries: 3 })` — no containment, no confirmation.
- The value is fully workspace-controlled (`cli.cache.path` in angular.json).

## PoC (REAL COMMAND, built CLI at the pin)

Workspace with `cli.cache.path: "/tmp/cache-poc/victim"` in its config (absolute form; relative `../../victim` also works). Running the built `ng cache clean`:

```
victim BEFORE: doc.txt, nested/keep.txt
victim AFTER : directory itself is GONE (find: No such file or directory)
```

The entire target directory (not just contents) is force-deleted recursively. Evidence: reproduced with the built CLI at the pin; source cited above.

## Trust boundary crossed

`cli.cache.path` (workspace config, attacker-influenceable via cloned/malicious project) → `rm -rf`-equivalent on any path the developer can write. `ng cache clean` is a documented troubleshooting step a developer runs routinely in a broken project.

## Impact (honest)

- **Confirmed:** force-recursive deletion of an arbitrary directory (absolute or `..`-escaped) through the real command, silent (force suppresses errors), no confirmation.
- **Capped:** the developer must run `ng cache clean` inside the crafted project; deletion only (no writes/RCE); same class as M3 (workspace-config → uncontained recursive deletion) — sibling in the same family.
- Not claimed: remote trigger, privilege gain, or writes.

## Negative control

- The default cache path (`.angular/cache` — in-root) deletes only the cache dir (correct behavior); the workspace-root-equality style guard present in `deleteOutputDir` (M3's utility) does not exist here at all.

## Replay / staleness

- Reproduced twice with the built CLI. Code untouched by security fixes since 2025-03 (git log). Not stale.

## Severity / category

- **Medium** (silent recursive deletion of arbitrary directory via a routine command on a crafted project; data loss). CVSS:3.1/AV:L/AC:H/PR:N/UI:N/S:U/C:N/I:N/A:H. Category: Product Vulnerability (CLI). Sibling of M3 — operator may want to file M3 + D2 together as one family report.


## CHAINSTORM CHAIN-ROLE NOTE (E2-R8): D2 is the keystone hop of Chains 1 and 2

- Chain 1 (cloned-repo delivery): the malicious repo's angular.json sets cli.cache.path — the dev runs ANY default build (`ng build`/`ng serve`/`ng test`) and `purgeStaleBuildCache` deletes the attacker-chosen path silently (unconditional firing — no malicious command needed).
- Chain 2 (CI sabotage): `ng build` on PR content (config-as-data shape) → full-checkout wipe candidate; cross-platform (verified on case-sensitive fs; the case-guard root-delete on macOS is M3's amplifier).
- Filing value: D2 is NOVEL + unconditional — the chain demo (fixture 8/8) demonstrated the purge hop.

## DEEP-PHASE NOTE (E1-R4/L6b): ng cache info hang variant (folded, zero delta)

- The `ng cache info` command walks the same uncontained `cli.cache.path` (no visited-set/lstat/depth caps) — a symlink cycle in the hostile path hangs the walk (self-inflicted: dev runs info on a hostile repo); the traversal is display-only (path printed, sizes computed). Folded into D2 (same root cause, same containment remediation); add lstat + cycle/depth guards to the shared walk when fixing.

## Remediation

1. Reject absolute `cli.cache.path` and `..`-escape from the workspace root (containment check in `getCacheBasePath`).
2. Confirm interactively when the resolved path differs from the default `.angular/cache`.
3. Drop `force: true` so failures surface.
4. Add lstat + cycle/depth guards to the shared cache-path walk (the ng cache info hang variant; E1-R4/L6b).
