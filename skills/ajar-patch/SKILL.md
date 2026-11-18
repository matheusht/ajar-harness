---
name: ajar-patch
description: Upgrade a verified 4-arm micro-patch into a maintainer-grade remediation diff that matches codebase idioms and closes sibling variants.
---

# Ajar Patch

Use this skill during `Fixes` workflows to turn a minimal verified `micropatch` from `ajar claim reproduce` into a clean, review-ready production patch (`maintainer_patched`).

## 1. Inspect Callers, Idioms, and Fix Precedents

1. Lease the `patch` task and inspect all callers and callees of the affected function:
   ```bash
   ajar task lease --worker <worker_id> --kind patch --recover
   ajar ref query --kind reachability "<affected_symbol>"
   ajar ref query --kind intent "<affected_module>"
   ```
2. Check real-world fix shapes and incomplete-fix pitfalls in `skills/references/ghsa-fix-diff-corpus.md`:
   ```bash
   ajar precedent search "<cwe_or_vulnerability_class> fix"
   ```

## 2. Maintainer-Grade Engineering Requirements

A 1–5 line micro-patch proves causal root cause, whereas a production patch must satisfy four engineering constraints:

1. **Preserve Local Idioms:** Match existing error types, HTTP status mappings, lock/unlock/RCU ordering, memory-cleanup paths, Solidity custom errors, and logging conventions used in the surrounding module.
2. **Audit Sibling Routes and Parallel Implementations:** Search the repository for copied helpers, legacy API versions (`v1` vs `v2`), parallel protocol handlers, and batch/GraphQL resolvers sharing the same assumption. Patch all vulnerable siblings in one coherent change.
3. **Fix Root State Rather Than Input Blacklists:** Enforce structural invariants (parameterized queries, canonical path resolution after symlink expansion, principal re-derivation from session context, checks-effects-interactions + `nonReentrant`, checked arithmetic, or canonical domain-separated signatures) instead of regex denylists.
4. **Add Regression Tests:** Include both a security regression test (asserting the exploit payload is rejected) and normal-operation unit tests.

## 3. Variant Bypass and Regression Gate

Before closing the `patch` task:

1. Re-run `ajar claim reproduce` or the project's full test suite against the production patch to confirm Arm 3 (exploit blocked) and Arm 4 (all existing tests green).
2. Test at least **3 distinct bypass variants** against the patched code (for example, alternate encodings, redirect hops, batch/nested payloads, boundary integer values, or second-order state entrypoints).
3. Close the task once the test suite and all bypass variants hold:
   ```bash
   ajar task done <task_id> --worker <worker_id> --summary "<files patched, sibling paths audited, and regression tests run>"
   ```
