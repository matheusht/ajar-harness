---
name: ajar-patch
description: Upgrade a verified 4-arm micro-patch into a maintainer-grade production fix verified by the hardened 9-Arm Remediation Gate (ajar patch verify).
---

# Ajar Patch (`Fixes` 9-Arm Gate)

Use this skill during `Fixes` workflows (`campaign_phase = 'remediate'`) to upgrade a minimal `1–5` line `micropatch` from `ajar claim reproduce` (`remediation_state = 'micropatched'`) into a locally verified production patch (`remediation_state = 'verified_local'`).

## 1. Hunt vs. Remediate Phase Split (`ajar phase`)

Ajar strictly separates active vulnerability/chain hunting from heavy 9-arm test-suite remediation so runs never burn discovery hours recompiling full suites prematurely:

- **Default `hunt` Phase:** `ajar patch verify` is blocked (`EXIT_GATE_BLOCKED`) and `ajar task lease` skips `patch` tasks while discovery, Open-Door bridge hunts, and Stage-5 chain synthesis remain underway.
- **Advancing to `remediate`:** Advance only when explicitly running a `Fixes` workflow or after discovery and chain synthesis have finished:
  ```bash
  ajar phase status
  ajar phase advance --to remediate
  ```

## 2. Inspect Callers, Sibling Routes, and Fix Precedents

1. Lease the `patch` task and query all callers, callees, and sibling routes:
   ```bash
   ajar task lease --worker <worker_id> --kind patch --recover
   ajar ref query --kind reachability "<affected_symbol>"
   ajar ref query --kind intent "<affected_module>"
   ```
2. Check real-world fix shapes and incomplete-fix pitfalls in `skills/references/ghsa-fix-diff-corpus.md`:
   ```bash
   ajar precedent search "<cwe_or_vulnerability_class> fix"
   ```

## 3. Maintainer-Grade Engineering Constraints

1. **Preserve Local Idioms:** Match surrounding error types, HTTP status mappings, lock/unlock/RCU ordering, resource-cleanup paths, Solidity custom errors, and logging conventions.
2. **Fix Structural State Rather Than Input Denylists:** Enforce canonical invariants (parameterized queries, post-symlink canonical path containment, session-derived principal checks, checks-effects-interactions + reentrancy guards, checked arithmetic, or domain-separated signatures) instead of regex blacklists.
3. **Audit Caller Error/NULL Paths (`GhostLock` Rule — Arm 7):** Whenever your patch introduces a new error return, `None`/`NULL` return, or revert on previously infallible paths, inspect every caller and supply `--caller-cmd` where executable caller tests exist.
4. **Audit Sibling Routes and Peer Hooks (Arm 8):** Check parallel endpoints (`v1` vs `v2`), batch/GraphQL resolvers, and paired lifecycle hooks (`create`/`update`/`transfer`) sharing the same assumption; supply `--sibling-cmd` where executable sibling tests exist.

## 4. Run the Hardened 9-Arm Production Remediation Gate

Execute `ajar patch verify` (preserving compiled `.o`/`.a` objects across resets with a default `1800s` `--suite-timeout`) to promote the finding to `verified_local`:

```bash
ajar patch verify <finding_id> \
  --worker <worker_id> \
  --patch <path/to/production_fix.diff> \
  --suite-cmd "<project or subsystem regression suite command>" \
  [--suite-timeout 1800] \
  --variant-cmd "<bypass variant 1: alternate encoding or normalization>" \
  --variant-cmd "<bypass variant 2: boundary value or nested/batch payload>" \
  --variant-cmd "<bypass variant 3: sibling route or second-order path>" \
  --caller-audit "<verified callers of patched function handle error/NULL returns cleanly>" \
  --sibling-audit "<verified v1/v2/batch sibling handlers and peer hooks>" \
  [--caller-cmd "<executable caller error-handling test>"] \
  [--sibling-cmd "<executable sibling-route symmetry test>"]
```

| Arm | Verification Check |
| --- | --- |
| **Arms 1–4** | Clean PoC fires, clean control passes, production patch blocks PoC, production patch passes control at `finding.locus` |
| **Arm 5** | Regression suite (`--suite-cmd`) introduces zero new failures vs cached clean-`HEAD` `repro/baseline_suite.json` |
| **Arm 6** | `>= 3` distinct `--variant-cmd` tests all pass on patched worktree AND `>= 1` triggers the defect oracle on clean `HEAD` |
| **Arm 7** | Caller NULL/error-return audit (`--caller-audit`) + optional `--caller-cmd` exits `0` |
| **Arm 8** | Sibling-route symmetry audit (`--sibling-audit`) + optional `--sibling-cmd` exits `0` |
| **Arm 9** | `git apply -R` patch-revert check on the same worktree proves the PoC re-triggers the defect oracle |

Close the `patch` task once `ajar patch verify` exits `0`:

```bash
ajar task done <task_id> --worker <worker_id> --summary "<finding_id promoted to verified_local across 9 arms>"
```
