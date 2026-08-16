# Unvalidated `outputPath` in the Angular CLI deletes directory contents outside the workspace root (and the workspace root itself on case-insensitive filesystems)

**Report as (Google OSS VRP vulnerability type):** Arbitrary file deletion via unvalidated config path (incl. project-root deletion on case-insensitive filesystems) — form category: **Path Traversal** (fallback: Other).

Hi Angular CLI team,

I found that the `outputPath` option is used for recursive deletion with no containment on the delete path. The write side of this family was fixed twice, the delete side was proposed and never merged, and on case-insensitive filesystems (macOS APFS, Windows NTFS, GitHub Actions macOS runners) the one guard that protects the project root is bypassable with a case-twisted path. A workspace config value can wipe arbitrary directories, including the project itself. Full details below.

## Product and version

- @angular/cli + @angular/build, pinned commit d827ba9005 (2026-08-13). Verified unfixed at main on 2026-08-15: delete-output-dir.ts is byte-identical, the application delete path is unchanged, legacy builders still exist.

## Severity

- Medium. CVSS:3.1/AV:L/AC:H/PR:N/UI:N/S:U/C:N/I:N/A:H (data loss, availability only).

## Summary

`deleteOutputDir` (packages/angular/build/src/utils/delete-output-dir.ts) resolves `outputPath` and removes its contents with `rm(..., { recursive: true, force: true })`. Its only guard is `resolvedOutputPath === root`, a case-sensitive string compare that throws when the resolved path equals the workspace root. The guard is not reached by the delete path in the application builder (application/index.ts:176 calls the delete unguarded), and the string compare itself is bypassable: on case-insensitive filesystems, an `outputPath` that differs from the root only by case resolves to the real root for the filesystem while failing the string equality, so the guard never fires and the workspace root's contents are deleted.

The same family includes the legacy browser/server builders (unguarded delete), extract-i18n (uncontained single-file write), and the legacy prerender route escape.

## Steps to reproduce

The compiled-module PoC is in the report evidence. The core sequence:

1. Workspace at `/tmp/poc/ws` with a file inside.
2. `outputPath = /tmp/poc/WS` (case variant) in angular.json, or the sibling escape `../victim-out`.
3. Run the build (or drive `deleteOutputDir` directly from the compiled module).
4. Exact-root control throws ("Output path MUST not be project root directory!"); the case variant deletes the workspace contents (verified: readdir returns empty).

The victim-out variant deletes a sibling directory's contents outside the workspace. The macOS runner implication: GitHub Actions macOS runners are case-insensitive APFS, so a PR-shipped config can wipe the checkout in the config-as-data CI shape.

## Impact

What I proved: recursive deletion outside the workspace root through the real compiled module, the root-delete via the case guard bypass on this machine's case-insensitive APFS, and the application-builder delete path being unguarded. What I did not prove: no remote trigger, no code execution, no writes (the family's write variants are separate members, filed with their own severity). The value comes from the developer's invocation context; the attacker channel is a cloned or attacker-influenced workspace, or a PR-shipped config in CI.

## Prior art and the delta

- The write side was fixed twice: #8358805d3 and #33312/bd413b0eb (2026-06-04, main-only). The delete guard was proposed in #32873 and never merged, so the delete variant is disclosed-but-unfixed. #33479 (a PR-triggered ng serve RCE class) was fixed at the pin and is context only.
- The delta: the delete path itself, plus the case-guard bypass that defeats the root protection on case-insensitive filesystems.

## Remediation

1. Contain the resolved `outputPath` at option normalization with `isSubDirectory(workspaceRoot, resolved)` (same place the write path is contained).
2. Add the guard inside `deleteOutputDir` with case-folded, realpath-normalized comparison so it holds on case-insensitive filesystems.
3. Extend the 8358805d3 regression test to the delete path.
4. Apply the same containment to the extract-i18n write and the prerender route escape.

Happy to retest once you've had a look. The compiled PoC scripts are in the report bundle and self-contained.
