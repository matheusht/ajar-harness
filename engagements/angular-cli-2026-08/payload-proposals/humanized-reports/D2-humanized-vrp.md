# ng cache clean and the build-time cache purge delete any directory via workspace-controlled cli.cache.path

**Product:** @angular/cli (the `ng` CLI) · **Pinned version:** commit `d827ba9005b86b23d05ee7c62c0823367aa245c1` (repo HEAD as of the testing date; behavior present in current releases since the value has no containment at any point in the chain)
**Severity:** Medium · CVSS:3.1/AV:L/AC:H/PR:N/UI:N/S:U/C:N/I:N/A:H

## Summary

The workspace config value `cli.cache.path` reaches an `rm(path, { force: true, recursive: true })` with no containment check and no confirmation, in two places. The explicit `ng cache clean` command force-deletes the configured directory. Independently, `purgeStaleBuildCache` reads the same value and force-deletes every sibling directory under the attacker-chosen base on **every default build** (9 builder entrypoints: application, dev-server x2, ng-packagr x2, legacy browser/server, extract-i18n, karma). Absolute paths pass through unchanged; relative paths escape the workspace root through `..`; git-worktree resolution can move the base outward. I could not find any place that validates the value or confirms the deletion.

## Steps to reproduce

1. Create a workspace and set the cache path to a victim directory, e.g. `/tmp/cache-poc/victim`, in `angular.json`:

```json
"cli": { "cache": { "path": "/tmp/cache-poc/victim" } }
```

2. Drop a file in it (`echo x > /tmp/cache-poc/victim/doc.txt`).
3. Run `ng cache clean`.
4. Observe: the victim directory itself is gone (`find /tmp/cache-poc/victim` → No such file or directory).

The same value deletes automatically without any command: put `cli.cache.path` at any path outside the workspace, then run a plain `ng build`. `purgeStaleBuildCache` fires during option normalization and removes every directory under that base except the current-version cache dir. I reproduced this with a compiled module of the purge against the pinned tree; the victim directories were deleted, the version dir was kept. The relative form (`../../victim`) works too, and a git-worktree layout resolves the base from the common git dir, which pushes it further outward.

## Impact

Confirmed: force-recursive deletion of an arbitrary directory the developer can write to, through the real built CLI (`ng cache clean`) and through the automatic purge on any default build in a crafted project. Silent: `force: true` swallows the errors, and the purge logs nothing at the delete sites. This is the keystone hop of a broader delivery chain, where a cloned repository ships a malicious `cli.cache.path` and the developer's routine `ng build` wipes an unrelated directory on their machine. I did not demonstrate writes, code execution, or any remote trigger. The value comes from the workspace config, so the attack requires the developer to build inside a crafted project, which is the same trust channel as the rest of this family.

## Remediation

- Contain the resolved path in `getCacheBasePath` (there are two byte-identical copies, `cache/utilities.ts` and `normalize-cache.ts`) with an explicit in-workspace check, rejecting absolute paths and `..` escapes.
- Drop `force: true` so failures surface, and add lstat + cycle/depth guards to the shared walk (the `ng cache info` variant hangs on a symlink cycle today).
- A confirm prompt when the resolved path differs from the default `.angular/cache` would close the operational gap.

## References

- `packages/angular/cli/src/commands/cache/clean/cli.ts:28-34` (`rm(force, recursive)`)
- `packages/angular/cli/src/commands/cache/utilities.ts:27-96` and `packages/angular/build/src/utils/normalize-cache.ts:43` (`getCacheBasePath`)
- `packages/angular/build/src/utils/purge-cache.ts:29-53` (the purge; 9 callers)
- Novelty: I searched GitHub issues, PRs, and advisories for `cli.cache.path` deletion and the purge behavior; no disclosure found (the only adjacent items are the feature PR and a worktree-cache discussion). The chain combination (cloned repo, registry redirect, cache-path wipe) is not described anywhere public.

Happy to retest once you have had a look.
