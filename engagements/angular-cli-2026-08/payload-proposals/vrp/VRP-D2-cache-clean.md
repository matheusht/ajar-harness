Title: Angular CLI deletes arbitrary directories through the workspace cache path, silently, on every build

**Report as (Google OSS VRP vulnerability type):** Arbitrary file deletion via unvalidated config path — form category: **Path Traversal** (arbitrary file deletion; fallback: Other).

Hi Angular CLI team,

I found that `cli.cache.path` in a workspace angular.json is taken as-is and used as the base for recursive deletes with no containment check, and the path fires automatically on every default build. A project you clone can wipe a directory on your machine without any prompt and without a single line of output. Full details below.

## Product and version

- @angular/cli, pinned commit d827ba9005 (2026-08-13). The pin git log shows no security fixes touching the cache path since 2025-03; the last change was a 2026-07-06 worktree-sharing feature, before the pin. I did not run a full main diff for the cache files, so I flag this as pin-verified rather than main-verified.

## Severity

- Medium. CVSS:3.1/AV:L/AC:H/PR:N/UI:N/S:U/C:N/I:N/A:H (availability only; data loss).

## Summary

`cli.cache.path` (workspace config, plain string, no schema pattern) flows into `getCacheBasePath` (packages/angular/cli/src/commands/cache/utilities.ts:27 and the byte-identical twin in packages/angular/build/src/utils/normalize-cache.ts:43). An absolute path is returned verbatim. `purgeStaleBuildCache` then removes stale version dirs with `rm(..., { recursive: true, force: true })` from that base. There is no containment check, no confirmation, and the purge runs on every default build through nine builder entrypoints. `ng cache clean` deletes the configured path entirely and prints nothing when it succeeds.

## Steps to reproduce

1. Create a workspace with a sibling victim directory:

    ```json
    // angular.json
    { "cli": { "cache": { "path": "../victim-cache" } } }
    ```

2. Run a default build, then check the victim:

    ```bash
    mkdir -p victim-cache/stale
    ng build
    ls victim-cache   # empty: the stale dir is gone
    ```

3. `ng cache clean` with the same path removes the whole victim directory with no output.

I verified this with the real built CLI at the pin: the victim directory itself was force-deleted (not just its contents). A compiled-module PoC (purgeStaleBuildCache + getCacheBasePath) is included with the report.

## Impact

What I proved: arbitrary recursive deletion of any directory the developer can write to, driven by a workspace config value, firing automatically during normal builds. The deletion is silent, which makes it worse than it looks. What I did not prove: nothing remote, no code execution, no writes. The value comes from the developer's own invocation context, so the attack requires a cloned or otherwise attacker-influenced workspace. That said, it is the same trust channel as the outputPath deletion finding, and the two share a remediation pattern.

## Remediation

1. Contain `cli.cache.path` (reject absolute paths and `..` escapes) inside `getCacheBasePath`, the shared chokepoint, so all nine entrypoints are covered at once.
2. Confirm interactively when the resolved path differs from the default `.angular/cache`.
3. Drop `force: true` so failures surface instead of vanishing.
4. Add lstat plus cycle and depth guards to the walk (a symlink cycle in the configured path hangs `ng cache info`).

## References

- No public disclosure of this channel found (checked 2026-08-15). The `ng cache` feature PR is #22851; an adjacent worktree-cache discussion is #33321; neither covers arbitrary deletion via the path value.

Happy to retest once you've had a look. I can also provide the compiled-module PoC as a standalone script if that is easier.
