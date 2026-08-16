# KP-M3D2 verdict — Wave B kill-pair (case-guard root-delete / CI wipe)

**Verdict: SURVIVES-NARROWED (1 case-guard STRENGTHENING + 1 D2/Chain-2 precision condition).**

## Kill hypothesis 1 — case-guard root-delete (M3 amp #1): NOT KILLED, STRENGTHENED
- (b) Relative variant: `deleteOutputDir(ws, '../PROJ')` — resolve → guard `===` passes (case differs) → workspace contents deleted (LIVE, compiled module). No absolute-path knowledge needed — the attacker ships a RELATIVE case-variant of the workspace dir name; ANY case mismatch works on case-insensitive fs ('../PROJ' and '../MyProject' both deleted).
- (a) REALPATH-FIX FAILS on APFS: `realpathSync('/tmp/kp-m3/PROJ')` → `/private/tmp/kp-m3/PROJ` — input case PRESERVED, no canonicalization → a naive `realpathSync(out) === realpathSync(root)` guard is STILL bypassed. Fix must explicitly case-fold (M3 remediation item 2's "case-folded/canonicalized" wording is load-bearing).
- (d) Exact-root control still throws — the guard works only for the byte-identical case.
- Self-limiting: contents-only (the resolved dir itself is never removed — matches the finding; no further bound).

## Kill hypothesis 2 — CI wipe (D2 purge / Chain 2 config-as-data): NOT KILLED, NARROWED
- NEW PRECISION CONDITION: in CI (CI=1), the DEFAULT `cli.cache.environment` ('local') DISABLES the purge (normalize-cache.ts: environment local → cacheEnabled = !isCI). LIVE control: CI + default → workspace intact.
- The CI wipe REQUIRES the malicious angular.json to also set `cli.cache.environment: 'ci'` → then the purge runs: LIVE (compiled module): CI + environment:'ci' + path:'.' → the workspace root is DESTROYED (deleted outright in the test).
- Both keys are config-controlled in the same malicious angular.json (same trust channel — one extra field). Dev-machine shape (Chain 1): default local + not CI → fires unconditionally (no extra key).
- Self-limiting: GH-hosted ephemeral (failed PR + Actions-minute burn); self-hosted persistent (already scoped in the claim).

## Actions for the parent
1. M3 remediation item 2: keep + sharpen — "realpath is NOT case-canonicalizing on APFS; explicit case-fold required".
2. Chain-2 record + D2 chain note: state the `environment:'ci'` requirement for the CI wipe (the C2H config-as-data shape analysis should carry it).
3. No claim/severity changes; no engagement files modified.
