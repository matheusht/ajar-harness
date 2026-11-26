---
name: ajar-reproduce
description: Prove candidates to mechanical C3 truth inside a clean git worktree using autobuild.py (.ajar/build.sh), Input Encoder micro-fuzzing, and verify.py 5-stage verification.
---

# Ajar Reproduce (`v3.6-Balanced`)

Use this skill to convert a candidate in `.ajar/candidates.jsonl` into a mechanically verified `C3` verdict in `.ajar/verdicts.jsonl`. Only `src/ajar/verify.py` creates `git worktree` sandboxes and mints `C3`.

## 1. Build Harness & Input Encoder (`autobuild.py`)

1. Ensure `.ajar/build.sh` and `.ajar/build_recipe.json` exist and compile cleanly under the selected profile (`upstream`, `debian`, or `al2023`, enabling `-fsanitize=address,undefined -fno-omit-frame-pointer` for native targets).
2. If the target fails to compile, let `autobuild.run_build_doctor` repair `.ajar/build.sh` inside its write-allowlist jail rather than hacking target source files.
3. When narrow framing, checksum, or length guards block a parser sink, use `autobuild.py`'s sandboxed `Input Encoder` micro-fuzzer (unless `--disable-microfuzz` is set; forbidden from importing `os`, `subprocess`, `socket`, `ctypes`, etc.) to synthesize valid wire/file inputs that reach the sink and capture deterministic crash inputs.

## 2. The 5-Stage Mechanical `C3` Gate (`verify.py`)

Run `ajar verify` against the repository:

```bash
ajar verify <repo> --runs 3 --profile upstream
ajar verify <repo> --candidate-id <id> --runs 3 --profile upstream
ajar verify <repo> --candidate-id <id> --runs 3 --offline   # C2 cap (skips Cross-Family Critic)
```

Inside a fresh `clean_worktree(repo)` with scrubbed credentials (`scrub_subprocess_env`), `verify_candidate` enforces five fail-closed stages:

| Stage | Mechanical Check | Failure Outcome |
| --- | --- | --- |
| **1. Pre-Patch Fail (`3x`)** | Rejects tautological repros, runs `.ajar/build.sh`, runs `repro_cmd` `3x`, requires deterministic `CrashSignature` (or concrete `failure_oracle`), verifies `sink_symbol` appears in output, and enforces identical `stack_hash` across all runs | `REJECTED` (`C0`) |
| **2. Fuzzy Patch Apply** | Applies `cand.patch_diff` cleanly via `apply_patch_fuzzy` inside the isolated worktree | `REJECTED` (`C0`) |
| **3. Mandatory Rebuild** | Re-runs `.ajar/build.sh` after patching so stale binaries or comment-only edits can never pass | `REJECTED` (`C0`) |
| **4. Post-Patch Pass (`3x`) + Suite** | Re-runs `repro_cmd` `3x` requiring exit code `0`, zero crash signatures, and zero `failure_oracle` hits, then runs `recipe.test_cmd` if configured | `REJECTED` (`C0`) |
| **5. Cross-Family Critic** | Submits candidate and `CrashSignature` to a distinct non-GLM model family (`resolve_role_model("critic")`) | `VERIFIED` (`C3`) if approved; `C2` if `--offline` or inconclusive; `REJECTED` if denied |

## 3. Reproducer Quality Checklist

Before running `ajar verify`, confirm your `Candidate` meets every requirement:

- **Real Entrypoint:** `repro_cmd` invokes the compiled target binary, server, contract test (`forge test`), or public library API—never a static source `grep` or tautological `exit 1`.
- **Deterministic Oracle:** `failure_oracle` matches a real sanitizer error, panic, assertion, revert, or invariant mismatch, and `sink_symbol` appears in the crash/failure output.
- **No Flaky State:** `repro_cmd` uses self-contained temp inputs and cleans up or runs idempotently so all `3` pre-patch runs yield the exact same `stack_hash`.
- **No Environment Leakage:** Do not rely on host secrets, external network calls, or hardcoded developer home paths (`scrub_subprocess_env` strips `*KEY*`, `*TOKEN*`, `*SECRET*`, `*PASSWORD*`, `*AUTH*`, `*CREDENTIAL*`).
- **Real Root-Cause Patch:** `patch_diff` modifies target production code at the defect locus (never edits tests or inserts no-op exits).

## 4. Inspecting Verdicts

Read `.ajar/verdicts.jsonl` after `ajar verify`. If a candidate fails Stage 1–4, inspect `verdict.notes` (`pre-patch repro did not crash`, `sink_symbol missing`, `flaky stack_hash`, `post-patch rebuild failed`, `post-patch failed`, or `regression test_cmd failed`), fix the reproducer or patch, and re-run `ajar verify --candidate-id <id>`.
