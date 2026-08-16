# Unvalidated `outputPath` in the Angular CLI deletes directory contents outside the workspace root (and the project root itself on case-insensitive filesystems)

## Product and version

- **Product:** Angular CLI (`@angular/cli`, `@angular-devkit/build-angular`, `@angular/build`)
- **Affected version:** verified against pinned `d827ba9005b86b23d05ee7c62c0823367aa245c1` (2026-08-13) and current `main` (2026-08-15, byte-identical for the affected code)
- **Package:** `packages/angular/build/src/utils/delete-output-dir.ts` (shared by the application builder and the legacy webpack browser/server builders)

## Severity

**Medium.** CVSS:3.1/AV:L/AC:H/PR:N/UI:N/S:U/C:N/I:N/A:H. Availability loss on the developer machine, no code execution.

## Summary

Hi Angular CLI team,

I found that the delete side of the build output handling has no real containment. The write side was fixed twice, in the exact file this delete lives in, and the delete side was never touched.

`deleteOutputDir` resolves `outputPath` against the workspace root, refuses only exact equality with the root, then recursively deletes the contents of whatever directory the resolved path points to. The legacy webpack browser and server builders pass `options.outputPath` straight through with no validation. So a workspace config that sets `outputPath: "../victim"` (or a scripted `--output-path`), in a project the developer clones and builds, silently deletes any writable directory on the machine.

There is more. The one guard that exists, the `resolvedOutputPath === root` string compare, is case-sensitive. On case-insensitive filesystems, which is the default APFS on macOS and NTFS on Windows, a case variant of the workspace root, `WS` instead of `ws`, passes the guard, and the root itself gets wiped: sources, node_modules, .git. GitHub Actions macOS runners are case-insensitive, so this reaches CI too.

## Steps to reproduce

I verified this with the compiled production module, bundled from the pinned source with the tree's own esbuild. The kit is at `findings/M3-legacy-builder-outputpath-delete/evidence-caseguard/`.

```bash
# ws is the "workspace root"; a case-variant of it is WS
mkdir -p ws && echo keep > ws/important.txt
node - <<'EOF'
import { deleteOutputDir } from './delete-output-dir.mjs';
// control: exact root is refused
try { await deleteOutputDir('/abs/path/ws', '/abs/path/ws'); }
catch (e) { console.log('control throws:', e.message); }
// case-variant: guard passes, contents deleted
await deleteOutputDir('/abs/path/ws', '/abs/path/WS');
EOF
```

The control prints `Output path MUST not be project root directory!`. After the second call, `ls ws` is empty. The original `../victim` form is the same call without the case trick.

## Impact

What I proved: recursive deletion of any writable directory outside the workspace through the real build path, in the flagship application builder (where the write fix landed, so it is a partial fix) and the legacy builders; and deletion of the workspace root itself via the case guard on case-insensitive filesystems, on the developer machine and on macOS CI runners.

Where I stopped: the attack needs the developer to build a project whose config or flag carries the malicious path. No remote trigger, no code execution, availability only. I did not run a full webpack `ng build` end to end; the load-bearing steps, the option normalization, the resolve, and the delete, are the compiled module itself.

## Remediation

1. Contain `outputPath` at option normalization with `isSubDirectory(workspaceRoot, base)`, same place the write path is contained.
2. Root-bound the resolved path inside `deleteOutputDir` and compare with realpath-canonicalized paths, not raw strings, so the guard holds on case-insensitive filesystems.
3. Extend the `8358805d3` regression test to the delete path. That fix, and the follow-up `bd413b0eb` in #33312, covered writes only.

## References

- #8358805d3: write-path containment for the application builder (the sibling fix, partial)
- #33312 / `bd413b0eb` (2026-06-04): write-path follow-up, main only
- #32873: a delete-path guard was proposed and never merged
- #33479 / `2d3eb7fb3` (2026-06-29): PR-triggered build RCE class, treated as security and fixed; the delete side was not

I verified all of this is still live on main as of 2026-08-15. Happy to retest once you have a look.
