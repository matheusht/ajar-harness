---
name: ajar-patch
description: Author minimal, maintainer-grade root-cause patches verified through Ajar v3.6 verify.py (fuzzy apply, mandatory post-patch rebuild, 3x repro pass, and upstream test_cmd regression suite).
---

# Ajar Patch (`v3.6-Balanced`)

Use this skill to craft an idiomatic, root-cause `patch_diff` for a `Candidate` in `.ajar/candidates.jsonl` and prove it mechanically via `ajar verify`.

## 1. Maintainer-Grade Engineering Constraints

Consult `skills/references/ghsa-fix-diff-corpus.md` for real-world fix shapes and incomplete-fix pitfalls before writing the diff:

1. **Fix the Structural Invariant, Not a Denylist:** Enforce canonical bounds checks, post-symlink path containment, checked arithmetic, checks-effects-interactions / reentrancy locks, session-derived principal checks, or domain-separated signatures instead of fragile string blacklists.
2. **Match Local Idioms:** Preserve surrounding error codes, return conventions, lock/unlock ordering, memory cleanup (`goto cleanup` / RAII / `defer`), and custom errors.
3. **Audit Callers on New Error Returns:** Whenever a patch introduces a new `NULL`, `None`, error code, or revert on a previously infallible function, inspect all callers (`repomap.py` / `search`) to verify they handle the error cleanly without leaking locks or memory.
4. **Audit Sibling Routes & Peer Hooks:** Inspect parallel endpoints (`v1`/`v2`, batch/single, `create`/`update`) sharing the same broken helper or assumption so the fix closes the whole root cause rather than one caller.
5. **No Cheating or Test Edits:** Never modify test files, disable the feature unconditionally, swallow all exceptions, or inject early `exit(0)` stubs. Both `verify.py` and the Cross-Family Critic reject sham patches.

## 2. Mechanical Verification (`ajar verify`)

Attach the unified diff (`git diff`) as `patch_diff` on the candidate in `.ajar/candidates.jsonl` and run:

```bash
ajar verify <repo> --candidate-id <id> --runs 3 --profile upstream
```

`src/ajar/verify.py` validates the patch inside a clean `git worktree` across four patch-bearing stages:

1. **`apply_patch_fuzzy`:** Confirms the unified diff applies cleanly to `HEAD` without rejecting hunks.
2. **Mandatory Post-Patch Rebuild:** Re-executes `.ajar/build.sh` so compiled artifacts genuinely reflect the patch (stale binaries or broken builds fail closed as `REJECTED`).
3. **Post-Patch Pass (`3x`):** Re-runs `repro_cmd` `3` times requiring exit code `0`, zero `CrashSignature` detections, and zero `failure_oracle` matches.
4. **Upstream Regression Suite (`recipe.test_cmd`) & Cross-Family Critic:** Executes `BuildRecipe.test_cmd` (if configured) to confirm zero regressions, then submits the diff and crash proof to the Cross-Family Critic to mint `C3`.

## 3. Bypass Variant Check Before Finalizing

Before treating a patch as maintainer-ready for `ajar report`, manually test `2–3` bypass variants against the patched worktree (alternate encodings, boundary lengths `0` / `MAX` / off-by-one, or sibling routes) to ensure the fix closes the underlying defect class rather than only the initial PoC input.
