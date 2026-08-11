# LR-6 — Dependency surface audit (pinned dependency set)

**Target:** ocore @ `a7eb776afc68ed4bed05ba554f7f1e95f5d49b44` (verified `git rev-parse HEAD`)
**Role:** round-3 terminal audit, dependency family. Local only; no network contact.

## 1. Pinned vs installed versions

| dependency | declared | installed | note |
|---|---|---|---|
| async | ^2.6.4 | 2.6.4 | throw-boundary behavior verified in-engagement (r1) |
| decimal.js | 10.6.0 | 10.6.0 | exact pin; precision config deterministic (f5 R3) |
| secp256k1 | ^4.0.3 | 4.0.5 | low-S enforced + fail-closed pubkey handling (f3 tested) |
| sqlite3 | ^5.1.7 | 5.1.7 | bundles SQLite 3.44.2 (past 3.40.1 fix for CVE-2022-35737) |
| ws | ^8.21.0 | 8.21.3 | ≥ 8.17.1 (past CVE-2024-37890 zlib-DoS fix) |
| lodash | ^4.18.1 | 4.18.1 | past prototype-pollution CVEs (fixed ≥ 4.17.12) |
| nearley | 2.16.0 | 2.16.0 | parse-input bounded (measured) |
| moo | 0.5.1 | 0.5.1 | lexer for the same bounded grammar |
| level-rocksdb | ^5 | 5.0.0 | local kvstore (joints); ops concern only |
| thirty-two | ^1.0.2 | 1.0.2 | lenient base32 decode — gated by charset regex + checksum |
| bitcore-mnemonic | ~1.0.0 | 1.0.1 | wallet key derivation, not consensus |
| mysql | ^2.18.1 | 2.18.1 | mysql backend "not currently supported" (conf.js:66-68) |
| dotenv / https-proxy-agent / socks-proxy-agent / nodemailer / jszip | — | — | config/proxy/mail/archive; off consensus paths |

## 2. Validation-correctness focus (the brief's four questions)

### nearley grammar parsing of attacker formulas — BOUNDED (no issue)
- The formula source is **attacker-typed oscript text** (e.g. `{...}`-braced strings in AA
  definitions and messages; `aa_validation.js` cases at :44/:68/:87/:247/:381 accept string
  formulas), parsed by the nearley-compiled grammar (`formula/grammars/oscript.js`) in
  `formula/validation.js:251-262`.
- **Input bounds:** (a) `variableHasStringsOfAllowedLength` (`aa_validation.js:824-845`) caps every
  string in an AA definition at `MAX_AA_STRING_LENGTH = 4096` (`constants.js:64`); (b) the whole
  unit is depth/nodes-capped (`isTooDeeplyNestedOrHasTooManyNodes`, depth 100 / nodes 10000) at
  `validation.js:153` before AA-definition validation (f11 held 4); (c) the parser cache is bounded
  (`cacheLimit` eviction, `formula/validation.js:255-262`).
- **Measured worst case at the cap:** deep-parens 4001 chars → 54ms; deep-brackets 4001 → 61ms;
  2000 tokens → 38ms. No parse-cost explosion; Earley chart bounded by the string cap.
- **Stack overflow protection:** the AST-walk chunks via `count % 100 → setImmediate`
  (`formula/validation.js:256-258`); the recursion depth cap at `:278` carries the
  `|| getMinRetrievableMci() >= pemCurvesFixMci` disjunct (048fbdb) so it applies network-wide.
- **Verdict: held.** No parser crash/explosion path reachable within the caps.

### decimal.js precision/rounding — DETERMINISTIC (held, matches f5 R3)
- `formula/common.js` pins `Decimal` precision 15, `ROUND_HALF_EVEN`, `toDoubleRange` expunges
  `-0`/underflow; `decimal.js 10.6.0` is an exact pin. Cross-node determinism verified in round 0
  (f5 R3, f12 N3/N4). No dependency behavior affects consensus.

### ws framing edge cases — HELD
- `ws` 8.21.3 is past the known zlib-DoS CVE-2024-37890 (fixed in 8.17.1). The node sets
  `maxPayload` 6MB (`network.js:45`) and depth-caps device messages and joints
  (`string_utils.js:260`; f9 H5). No framing edge case found that reaches validation.

### async 2.6.4 throw handling — DOCUMENTED, ALREADY ADJUDICATED
- async 2.6.4's iterators catch throws (verified by r1 against `_eachOfLimit`); completion-callback
  throws escape to `uncaughtException`. This is exactly the crash-family mechanism — the four
  reachability-refuted sites (validation.js 1667/1686/2292/2451) rely on it. **No new behavior;**
  the engagement's hardening note stands (convert full-node throw sites to `cb(err)`).

## 3. Other dependency observations

- **thirty-two base32 leniency:** `base32.decode` maps invalid characters to data without throwing
  (measured: `'!'*32` → 20 zero bytes). **Not reachable as an issue:** `isValidAddress` requires
  `/^[A-Z2-7]{32}$/` (the `f3b253e` charset fix, verified in `validation_utils.js:60-61`) before
  `isChashValid`, and the embedded 4-byte sha256-derived checksum (`chash.js:70-82`) is a 32-bit
  work factor — not forgeable in practice. Held.
- **sqlite3 5.1.7:** bundled SQLite 3.44.2 (verified via `SELECT sqlite_version()`), past the known
  3.40.x-era CVEs. All queries in the audited consensus paths are parameterized (S2 held); the DB is
  local and attacker data never becomes SQL.
- **level-rocksdb 5.0.0:** deprecated/discontinued upstream (install-time warnings), but the kvstore
  is local persistence for joints; corruption risk is an ops concern, not attacker-reachable
  through validation (read paths are hash-verified — f10 T3).
- **Known-CVE routing note (not findings):** none of the installed versions carries a high-severity
  issue on a consensus/validation path. The old-style pins (async 2.6.4, lodash 4.18.1) are stale
  but their known issues do not touch validation correctness.

## 4. Verdict

**No dependency-caused validation-correctness issue found.** All four focus surfaces are bounded or
deterministic, and the dependency behaviors that could matter (async throw boundary, secp256k1
malleability, base32 leniency) were already exercised and adjudicated earlier in the engagement
(r1 crash-family, f3 signature tests, f3b253e charset). This family contributes **zero new leads**;
the honest result is a negative.

## 5. Residual risks

- Known-CVE matching used local knowledge + the installed manifests only (no live advisory DB fetch,
  per the no-network rule); the version set is recent enough that this is low-risk.
- `bitcore-mnemonic` 1.0.1 and `thirty-two` 1.0.2 are unmaintained; neither is on a consensus path
  (wallet-local key derivation / checksum-only encoding) — noted for the operator's supply-chain
  hygiene review, not a finding.
- The `ws`/`level-rocksdb`/`sqlite3` native bindings were installed from source at preflight; a
  supply-chain tamper check of node_modules was not performed (out of the dependency-behavior scope).

## 6. Files

- This report: `evidence/round3/LR-6.md`
- No code modified; no files outside `evidence/round3/` touched; ocore clone untouched.
