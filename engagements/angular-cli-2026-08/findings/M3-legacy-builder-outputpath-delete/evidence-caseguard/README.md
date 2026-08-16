# Case-guard bypass PoC — M3 amplifier (verified 2026-08-15, deep phase E1-R1)

**Claim:** `deleteOutputDir`'s root protection (`resolvedOutputPath === root`, a case-sensitive
string compare) is bypassable on case-insensitive filesystems (macOS default APFS, Windows NTFS)
with a case-variant of the workspace root.

**Verification (real, compiled production code):**
1. `esbuild` (tree's own, v0.28.2) bundles `packages/angular/build/src/utils/delete-output-dir.ts` → `delete-output-dir.mjs` (committed here).
2. Control: `deleteOutputDir(WS, WS)` → throws `Output path MUST not be project root directory!` ✓
3. `readdir(CASEV)` on case-insensitive APFS resolves to the real workspace root (proves CI fs).
4. `deleteOutputDir(WS, CASEV)` → guard passes (string compare), workspace root contents deleted (`readdir` → `[]`). ✓
5. Path semantics: `resolve` preserves input case on both darwin and win32 (`path.win32.resolve('C:\\WS','c:\\ws')` ≠ root).

**Marginal delta (vs base M3):** the only contained case — "outputPath = project root errors out" —
is defeated on case-insensitive filesystems; the workspace root (sources, node_modules, .git) is
deletable via a malicious `outputPath` config value. GitHub Actions macOS runners are
case-insensitive APFS → applies to CI. On case-sensitive fs (Linux) the variant path ENOENTs and
returns early — no impact there.

**Files:** delete-output-dir.mjs (compiled prod code), poc.mjs (driver).
