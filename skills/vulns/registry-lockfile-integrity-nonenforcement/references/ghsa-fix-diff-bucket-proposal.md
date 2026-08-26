# Proposed NEW ghsa-fix-diff-corpus.md bucket — Supply-chain registry/lockfile integrity (CWE-345/494/353)

Status: **proposed, not yet merged into `skills/oracles/references/ghsa-fix-diff-corpus.md`.** Built
while authoring `skills/vulns/registry-lockfile-integrity-nonenforcement/SKILL.md` for the
`google-oss-vrp-2026-07` bazel/BCR asset, which found no existing bucket for this class. Formatted to
match the corpus's existing per-bucket convention (header + verdict line + per-anchor entries) so a
future promotion pass can paste it in directly after independent re-verification. Do not treat this
file as already part of the oracle's coverage-honesty count until it is merged and that count is
updated.

## Supply-chain registry/lockfile integrity (CWE-345 / CWE-494 / CWE-353)

Grounds card: `skills/vulns/registry-lockfile-integrity-nonenforcement`
Bucket verdict (proposed): **THIN — 2 clean IN anchors (golang/go, yarnpkg/yarn), below the >=6-anchor
bar this oracle otherwise requires before asserting a dominant-shape convention. Both anchors are
real, re-fetched, primary-sourced fix commits and are useful as illustrative taxonomy templates, but
this bucket should NOT be marked IN/promotable-convention until a wider mining pass (npm, pip, cargo,
container-registry/OCI digest verification, apt/dpkg, RubyGems) adds at least 3-4 more clean anchors.**
2 IN / 0 CONTESTED / 0 dropped this pass (a narrow, targeted 2-query pass, not an exhaustive mining
pass — do not read the 0-dropped count as "this class is easy to find," it reflects a small search
budget, not a saturated search).
Dominant guard shape observed across the 2 anchors so far (tentative, do not treat as a settled
convention with only 2 anchors): a **presence-before-match check** — verify the artifact/response
being validated actually contains a hash/integrity value for the SPECIFIC thing you asked about,
before (not instead of) comparing that value — inserted at the exact point an existing "if present,
does it match" check already lived, closing a gap where an absent/irrelevant hash silently passed.
The yarn anchor is a structural sibling (a whole verification step present on one code path — cache
write — and absent on a symmetric path — cache read — rather than a presence-vs-match split), kept in
this bucket because it shares the mechanism-family (fetched-artifact integrity not enforced on the
path that actually uses the artifact), not because it shares the exact guard shape.

- **CVE-2026-42501 (GHSA-qf3q-3h68-mmh2)** — CWE-347 (closest existing CWE the advisory itself uses;
  this bucket additionally frames it under CWE-345/494 as a registry-response-integrity gap) ·
  `golang/go` (`cmd/go`, GOSUMDB checksum-database client) · fixed go1.25.10 / go1.26.3 @
  `1a9af07120312d368815712a4dce2dd2070342e5` (Gerrit CL `go-review.googlesource.com/c/go/+/775321`,
  merged 2026-05-07) · **IN** (signature) · presence-before-match
  - Mechanism: the go command's sumdb `/lookup/` client verified "if the response contains a hash
    for this module, does it match the expected value" but never checked that the response actually
    contained an entry for the module being validated at all. A malicious/compromised module proxy
    could return an empty response, or a valid response for an unrelated module, and validation was
    reported as succeeding — permitting a corrupted/substituted module (or a substituted Go toolchain
    download fetched the same way) to pass with no detected mismatch.
  - Affected -> Fixed: cmd/go before go1.25.10, and go1.26.0-rc through before go1.26.3 -> go1.25.10 /
    go1.26.3
  - Vulnerable shape (conceptual — pre-fix code accepted a response and matched only what was
    present, per the commit message; verbatim pre-fix hunk not independently re-diffed this session,
    only the fix commit's own description of the removed behavior):
    ```
    // pre-fix: verify a returned sum matches the expected module hash IF one is returned;
    // no check that the sumdb response actually contains an entry for the requested module
    ```
  - Guard added (post-patch, per commit message — verbatim diff not fetched this session, only the
    commit metadata; re-diff before promoting to IN-with-verbatim-hunk status):
    "reject sumdb response lacking module hash" — report an error when a sumdb `/lookup/` response
    does not include a hash for the requested module, rather than silently proceeding.
  - Reachability: `cmd/go` checksum-database client, reached by any `go build`/`go get`/`go mod
    download`/toolchain-download operation configured to use a proxy or checksum database the
    attacker can serve responses through (untrusted `GOPROXY`/`GOSUMDB`, or a MITM position on that
    channel).
  - Verdict: IN — re-fetched the GitHub issue (https://github.com/golang/go/issues/79070) and the
    fix commit metadata (https://github.com/golang/go/commit/1a9af07120312d368815712a4dce2dd2070342e5)
    directly this session; commit message is unambiguous about the removed/added behavior. **Caveat:**
    the verbatim source diff (the actual removed/added Go source lines in the sumdb client) was not
    independently fetched and quoted this session — only the commit message's own description of the
    change. Re-fetch the actual `.diff`/patch before quoting source lines in a report; the mechanism
    description itself is solid (primary-sourced commit message + issue tracker, both re-verified).
  - Source: https://github.com/golang/go/issues/79070 ;
    https://github.com/golang/go/commit/1a9af07120312d368815712a4dce2dd2070342e5 ;
    https://go-review.googlesource.com/c/go/+/775321 · provenance: re-verified-this-session

- **CVE-2019-15608 (GHSA-hjxc-462x-x77j)** — CWE-353-shaped (TOCTOU on integrity re-verification,
  advisory does not carry a clean CWE tag) · `yarnpkg/yarn` · fixed 1.19.0 @
  `0474b8c66a8ea298f5e4dedc67b2de464297ad1c` (companion commit
  `c3d256fcf641de4fe8d4d6034a2b046fafae30c0`) · **IN** (signature) · missing-reverify-on-read
  - Mechanism: yarn computed and checked a package's integrity hash when WRITING it into the local
    package cache, but did not re-verify that hash when READING the same package back out of cache on
    a later install. A crafted `yarn.lock` (or any other means of placing an entry into the cache
    under an attacker-chosen name/version) could poison the cache once; every subsequent install of
    that name/version silently trusted the poisoned cache entry with no re-check.
  - Affected -> Fixed: yarn < 1.19.0 -> 1.19.0
  - Vulnerable shape (removed/implicit — the pre-fix `fetchCache` had no integrity parameter or check
    at all on the read path):
    ```
    async function fetchCache(dest: string, fetcher: Fetchers, config: Config): Promise<FetchedOverride> {
      // ... reads from cache with no integrity re-verification against the caller's expected hash
    }
    ```
  - Guard added (post-patch):
    ```
    async function fetchCache(dest: string, fetcher: Fetchers, config: Config, integrity: ?string): Promise<FetchedOverride> {
      const remote = await readMetadata(dest);
      if (integrity) {
        if (!remote.integrity || !ssri.parse(integrity).match(remote.integrity)) {
          throw new MessageError('Incorrect integrity when fetching from the cache');
        }
      }
      // ...
    }
    // call site updated: fetchCache(dest, fetcher, config, remote.integrity)
    ```
  - Reachability: `src/package-fetcher.js` cache-read path, reached on any `yarn install` that hits an
    already-cached package — i.e. the common case for a second install/CI run, not merely a first
    install.
  - Verdict: IN — re-fetched the OSV record (https://osv.dev/vulnerability/CVE-2019-15608) and the fix
    commit diff (https://github.com/yarnpkg/yarn/commit/0474b8c66a8ea298f5e4dedc67b2de464297ad1c)
    directly this session; the added `ssri.parse(...).match(...)` guard and the updated call site are
    a clean, isolable re-verification-on-read guard.
  - Source: https://osv.dev/vulnerability/CVE-2019-15608 ;
    https://github.com/yarnpkg/yarn/commit/0474b8c66a8ea298f5e4dedc67b2de464297ad1c ;
    companion: https://github.com/yarnpkg/yarn/commit/c3d256fcf641de4fe8d4d6034a2b046fafae30c0 ·
    provenance: re-verified-this-session

## Candidates checked this session and explicitly NOT added (do not invent anchors from these)

- **npm `EINTEGRITY` / `package-lock.json` integrity handling** — multiple open npm/cli GitHub issues
  discuss integrity-mismatch behavior and UX (e.g. `npm/cli#4460`, `npm/cli#2846`, `npm/npm#21015`),
  but none surfaced this session is a disclosed, fixed security advisory with a clean fix commit —
  these are open bugs/UX-quality issues, not verified security fixes. **Do not cite as an anchor.**
- **pip `--require-hashes` build-dependency gap** — real, currently open, well-documented design gap
  (`pypa/pip#13984`): hash checking is hard-coded off (`require_hashes=False`) when pip fetches a
  source distribution's PEP 517 `[build-system].requires` dependencies, even when the user has
  `--require-hashes` set for everything else. This is directly on-class (checksum-optional fetch that
  a transitive build-time dependency can exploit) and worth keeping in the vuln card's activation
  vocabulary as a pattern to check for — but it is an **open issue, not a disclosed/fixed CVE or
  GHSA**, so it does not belong in this corpus bucket (which is fix-diff-only) without a merged fix to
  diff. Re-check `pypa/pip` for a resolution before citing this as a fixed anchor.
- **cargo `Cargo.lock` checksum handling** — only long-open feature-request/behavior issues found this
  session (e.g. `rust-lang/cargo#4800`, `#7059`, `#7180`, `#10071`); no clean fixed-security-advisory
  anchor located. **Do not cite as an anchor without a fresh, successful search.**
- **Bazel/BCR itself** — the vuln card this bucket supports is the FIRST card for this class in this
  ecosystem; at authoring time no bazel/BCR-specific fixed advisory for registry/lockfile-hash
  non-enforcement was known or searched for (that is the live hunt this card exists to support, not
  a mined precedent) — do not backfill a bazel anchor here without an actual disclosed, fixed advisory.

## Promotion checklist (for whoever merges this into the real corpus)
1. Re-fetch the golang/go fix commit's actual source `.diff` (not just the commit message) and quote
   the verbatim removed/added Go lines before calling it a full IN-with-verbatim-hunk signature.
2. Run a wider mining pass (npm, pip fixed advisories only, cargo, OCI/container digest verification,
   RubyGems, apt/dpkg Release-file signature+hash chain) to try to clear the >=6-anchor bar before
   asserting a "dominant guard shape" convention for this bucket the way other IN buckets do.
3. Cross-check both anchors' CVSS vectors against `skills/oracles/references/severity-precedent-corpus.md`
   for a same-class severity join, per the sibling-oracle convention.
4. Only then fold this file's content into `skills/oracles/references/ghsa-fix-diff-corpus.md` and
   update `skills/oracles/ghsa-fix-diff-oracle.md`'s coverage-honesty paragraph and bucket-reference
   list (new bucket count, new total IN/CONTESTED/dropped tallies).
