---
id: supplychain.registry-lockfile-integrity-nonenforcement
name: Registry/Lockfile Response Used Without Enforced Integrity Check
description: >
  Prove that a package/module registry response (a registry index entry, module/source descriptor,
  or the artifact it points at) is fetched and USED to resolve or build a dependency graph without
  the client enforcing an integrity check that binds it to a value the client trusts independently of
  that same fetch — a hash mismatch is logged/warned rather than hard-failed, or a first-time
  resolution with no prior recorded hash is trusted on faith (TOFU) with nothing to detect a later
  swap. A theoretical "this field could in principle go unchecked" reading with no reproduced
  silent-accept is coverage, not a finding.
type: vuln
owasp: "A08:2021 Software and Data Integrity Failures / CWE-345 (Insufficient Verification of Data Authenticity) / CWE-494 (Download of Code Without Integrity Check) / CWE-353 (Missing Support for Integrity Check) — a package-manager/module-resolver class, not a web-app OWASP Top 10 category"
atlas: "—"
patterns: []

activation:
  strong:
    - "a registry-fetched artifact (index entry, module/source descriptor, or the archive/file it references) is written into the resolved dependency graph, extracted, or otherwise USED before any hash comparison against an independently-trusted value runs — the use happens on the fetch path itself, not gated behind the check"
    - "a hash/checksum comparison DOES run, but a mismatch is logged, warned, or downgraded to a non-fatal code path (a boolean flag, a best-effort retry, a soft warning) rather than a hard failure that aborts resolution/build"
    - "first-time resolution of a dependency (no prior lockfile/lockrecord entry exists yet) records whatever hash the registry/server returns AT THAT MOMENT with no separate, out-of-band or previously-pinned value to check it against — i.e. trust-on-first-use with no later re-verification channel, so an attacker who controls or MITMs that one fetch controls the value that becomes 'trusted' from then on"
    - "the lockfile/lockfile-enforcement mode DEFAULTS to a permissive/update/warn posture (silently rewriting or merging fresh registry data into the lock state) rather than an error/frozen posture that hard-fails on any divergence between the lockfile and a fresh fetch, and nothing forces integrators onto the strict mode"
    - "a TRANSITIVE dependency (not merely the root/top-level module's own declared inputs) can influence which registry URL, mirror, or index entry a fetch subject to this same gap resolves against — this is the detail that turns a self-inflicted local misconfiguration into a third-party-triggerable supply-chain path"
  weak:
    - "an integrity/hash field exists in the lockfile or registry-response schema, but whether a mismatch is enforced (hard error) or merely recorded/logged has not yet been confirmed by reading the actual branch — do not infer enforcement from the field's mere existence"
    - "a checksum-optional code path exists (the field is allowed to be absent/empty) but it has not yet been confirmed whether that path is reachable for artifacts a transitive dependency can trigger, or only for a root-declared, self-controlled input"
  negative:
    - "every fetched registry response / artifact whose hash the client can independently know is compared with a hard-fail (nonzero exit / uncaught exception / resolution aborts) against a value from a channel the fetch itself does not control — a previously-recorded lockfile entry, a value pinned in a signed manifest, or a separate transparency-log/checksum-database lookup whose own response-presence (not just its content) is itself validated → likely held"
    - "first resolution requires an explicit, separately-verifiable pin before the artifact is trusted (a maintainer-supplied hash checked into version control, a signed manifest, mandatory strict/frozen-lockfile mode) rather than accepting whatever the server said on that first contact → likely held"
    - "the checksum-database/registry-response validation logic itself checks not just 'if a hash is present does it match' but ALSO 'is a hash present for the artifact actually being validated, or did the response omit it / answer for something else' → likely held (this is the exact class of gap CVE-2026-42501 closed in the Go toolchain itself — presence-of-response is not presence-of-the-relevant-hash)"

safe_signal:
  proxy: >
    a LOCAL, self-controlled fake registry/index (a local HTTP server or local-registry mode the
    package manager itself supports) serving a module/package descriptor whose recorded hash
    deliberately MISMATCHES the bytes of the file it points at, or that omits the hash field entirely
    on a first-time (no-prior-lockfile-entry) resolution — run the real, unmodified client/resolver
    against it and observe whether the build/install/resolve proceeds and the mismatched or unpinned
    content is actually loaded/used (the benign marker), or whether the client hard-fails and refuses
    to proceed. No real registry, real package name, or real credential is touched; the substituted
    "malicious" file is an inert local fixture with no payload behavior of its own.
  never: >
    never point the real client at any public/production registry (npmjs.org, pypi.org, BCR, crates.io,
    proxy.golang.org, etc.) while attempting a hash-mismatch or absent-hash resolution; never publish,
    register, or claim a real package/module name; never use this technique against infrastructure you
    do not operate. All registry state, module files, and hashes are locally minted, disposable fixtures.

impact_escalation:
  enabled_by: scope.md#impact_demo_authorized
  requires: >
    benign/non-destructive local reproduction (local fake registry, local disposable build workspace)
    proceeds without a per-artifact pause under this engagement's standing Zone-2 authorization (see
    scope.md); a fresh human confirmation is still required before anything that would touch a real
    registry, real package publication, real credentials, or non-local infrastructure
  containment: "local disposable fake registry + local disposable build workspace only; no real registry, package name, or credential touched; logged in engagement cleanup.md"

oracle: [whitebox-analysis, regrade-oracle, pocinator-oracle]
severity_rubric: { transitive_dep_controlled_hash_mismatch_or_absent_hash_silently_accepted_module_substituted: critical, transitive_dep_controlled_first_resolution_toctou_confirmed_no_substitution_demoed: high, root_only_self_inflicted_bypass: medium, theoretical_design_gap_no_reachable_precondition: low }

procedure:
  - "LOCATE THE ENFORCE BRANCH, NOT JUST THE FIELD: find where a registry-fetched artifact's recorded/expected hash is actually COMPARED against the bytes fetched, and read precisely what happens on mismatch — an aborted resolution (hard-fail) vs. a logged warning, a retry, or silent continuation. Do not infer enforcement from a hash field merely existing in the schema (bzlmod: `registryFileHashes` is an aggregation map in `BazelModuleResolutionFunction.java`; the actual enforce/branch logic lives in `BazelLockFileFunction`/`Discovery.java` — read that code, not the aggregator)."
  - "TRACE PARAMETER/HASH PROVENANCE: for the value the fetch is checked against, determine whether it comes from a channel the client trusts INDEPENDENTLY of this fetch (a prior lockfile entry, a signed manifest, a separate checksum-database lookup) or is itself sourced from data the same fetch/registry supplied — the latter is not an integrity check, it's a tautology (CVE-2026-42501's exact shape: the go command checked 'if a sum is present does it match' but not 'is a sum present for the module I actually asked about')."
  - "CHECK FIRST-RESOLUTION / TOFU BEHAVIOR SEPARATELY: when no prior lockfile/lockrecord entry exists for a dependency, determine what the client does with the hash the registry returns on that first contact — is it merely recorded as the new 'trusted' baseline (TOFU, MITM-on-first-fetch wins permanently), or is there a requirement (maintainer-supplied pin, mandatory strict mode, a second independent source) before that value is trusted at all."
  - "CHECK THE LOCKFILE-MODE DEFAULT: determine the out-of-the-box lockfile enforcement mode (update/refresh/warn vs. error/frozen) and whether a divergence between the lockfile and a freshly fetched registry response is ever silently reconciled in the registry's favor rather than treated as tamper evidence."
  - "DECIDE REACHABILITY — THE GRADING QUESTION: determine whether a TRANSITIVE dependency (something the root module does not directly declare or control) can influence the registry URL, mirror selection, module version resolution, or which fetch is subject to this gap. If only the root/top-level module's own declared, self-controlled inputs can reach the gap, severity is capped hard — that's a self-inflicted misconfiguration, not a third-party-triggerable supply-chain path. This is the single deciding question for this card; do not skip it."
  - "CONSTRUCT A REAL LOCAL FAKE REGISTRY: using the real client's own supported local/custom-registry or local-HTTP-index mechanism (never a hand-rolled stub of the resolver itself), serve a module/package descriptor with a deliberately mismatched hash, or omit the hash on a first-time resolution."
  - "RUN THE REAL UNMODIFIED CLIENT AGAINST IT: execute the actual, unmodified package-manager/build-tool client (real `bazel build` / `npm install` / `pip install` / `go build` / `cargo build`, whichever is in scope) pointed at the local fake registry and observe whether resolution/build proceeds — and, critically, whether the SUBSTITUTED content is actually loaded/compiled/executed as part of the build graph, not merely that no error was printed."
  - "NEGATIVE CONTROL: repeat with a correctly hashed, honest local registry entry and confirm the client behaves identically (build succeeds) — isolating that it is the hash-mismatch/absent-hash case specifically, not local-registry usage in general, that produces the accept. Also confirm a KNOWN-bad hash on an entry the client already has an independently-pinned lockfile record for is correctly rejected, isolating the first-resolution/TOFU gap from the steady-state gap."
  - "ASSESS DOWNSTREAM IMPACT: trace what the accepted, substituted module/artifact can actually do once loaded into the build graph — arbitrary code execution during a Starlark/build-script phase, a swapped dependency shipped into a built artifact, or credential/environment access from a build sandbox — severity depends on that concrete downstream capability, not merely that a hash check was bypassed in isolation."

emits: [attempt, finding]
---

## What "confirmed" looks like here
A real, unmodified client (bazel/npm/pip/go/cargo, whichever is in scope) is pointed at a real local
fake registry serving a module/package artifact whose hash deliberately mismatches its content — or
that omits the hash on a first-time resolution — and is shown to ACCEPT it: resolution/build proceeds
and the substituted content is actually loaded/used, not merely that no error was printed. A matched
negative control confirms an honestly-hashed entry behaves identically and that a mismatch against an
already-pinned lockfile entry (steady-state, not first-resolution) is correctly rejected, isolating the
exact gap. The deciding severity question — can a TRANSITIVE dependency (not only the root module's own
declared, self-controlled inputs) reach the gap — is answered explicitly, with the answer traced to a
concrete downstream capability the substituted artifact gains (code execution during build, a swapped
dependency shipped into the built output, sandbox credential/environment access).

## Grading — the deciding reachability question
This class splits hard on one axis: **root-only vs. transitive-reachable.**
- **Root-only:** only the root/top-level module's own declared inputs (its own `MODULE.bazel`, its own
  `package.json`, its own requirements file) can steer the fetch into the gap. This is the operator
  attacking their own build — self-inflicted, capped at `medium` even when the accept is real and
  reproduced, because the threat model requires the victim to already have chosen a hostile
  configuration.
- **Transitive-reachable:** a dependency the root module did not directly author — a `bazel_dep`
  pulled in transitively, a nested `requirements.txt`, a sub-dependency's registry/mirror override —
  can influence the registry URI, mirror, or which specific fetch is subject to the gap. This is the
  supply-chain-compromise shape the reward category actually pays for: a third party the victim never
  directly chose to trust controls what lands on their machine. Confirm this explicitly with a real
  transitive-dependency chain in the local repro, not an assertion.

Do not average or split the difference between these two — grade to whichever one you actually
demonstrated, and say explicitly in the writeup which one it is.

## Stage-0 sink vocabulary (generalizes across ecosystems; bzlmod-anchored examples)
- **registry-fetch → hash-record-vs-enforce branch**: the fetch itself (`repository_ctx.download`,
  `npm pack`/tarball fetch, `pip download`, `go mod download`, `cargo` `.crate` fetch) is a distinct
  step from the comparison step; find both, and specifically find whether the comparison step's
  failure path is reachable and fatal. Bazel: `repository_ctx.download`'s `validateChecksum` path —
  confirm whether an empty/absent expected-hash short-circuits to "trust whatever was fetched"
  (`Optional.empty()` checksum) rather than requiring one.
  Symmetric to `skills/vulns/insecure-deserialization`'s existing sink split (deserialize call vs.
  the type-allowlist/signature check around it) — same "the dangerous operation and its guard are two
  separate lines, and only one of them is often actually reached" structure.
- **TOFU-on-first-resolution**: any lockfile/lockrecord format has a "no entry yet" case; that case's
  behavior is the actual attack surface for a new/unpinned dependency (the steady-state re-resolution
  path is usually the well-tested one). Bazel: `MODULE.bazel.lock`'s `registryFileHashes` on a
  dependency's first appearance. npm/yarn: initial `npm install` populating `package-lock.json`/
  `yarn.lock` before any prior lock state exists. go: first `go mod tidy`/`go get` populating `go.sum`.
- **lockfile-mode default**: is the out-of-the-box posture "reconcile silently toward whatever the
  registry says now" (`bazel build` with no `--lockfile_mode=error`, `npm install` without `--ci`/
  frozen-lockfile, `go` with a permissive `GOFLAGS`) or "fail loudly on any divergence"? A permissive
  default matters even when a strict mode exists, because most invocations use the default.
- **transitive-vs-root reachability**: see Grading above — this is the load-bearing distinction for
  severity, not a secondary detail.

## Real disclosed anchors for this class (verified against primary sources, re-fetched this session —
treat as taxonomy templates for finding structurally similar gaps elsewhere in scope, not as
currently-exploitable bugs in the patched, released versions cited)
- **CVE-2026-42501 / GHSA-qf3q-3h68-mmh2 (golang/go, `cmd/go`, fixed go1.25.10 / go1.26.3, CWE-347)**:
  the Go toolchain's checksum-database (`GOSUMDB`) client validated a `/lookup/` response by checking
  "if the response contains a hash for this module, does it match the expectation" — but did NOT
  separately verify that the response actually CONTAINED a hash for the module being validated at
  all. A malicious/compromised module proxy could return an empty response, or a valid-but-irrelevant
  response for a different module, and the go command "incorrectly permitted validation to succeed,"
  letting the proxy serve a corrupted/substituted module (including a substituted Go toolchain
  download) with no detected mismatch. Fix commit
  `1a9af07120312d368815712a4dce2dd2070342e5` (Go CL 775321, merged 2026-05-07) added the missing
  presence check ("reject sumdb response lacking module hash") ahead of the existing match check —
  exactly the `hash-record-vs-enforce branch` shape above, and the closest possible real-world
  anchor for the "response is present but doesn't actually cover what you asked about" absent-hash
  variant. Sources: https://github.com/golang/go/issues/79070 ,
  https://github.com/golang/go/commit/1a9af07120312d368815712a4dce2dd2070342e5 ,
  https://go-review.googlesource.com/c/go/+/775321 . Provenance: re-verified this session
  (issue text + commit message fetched directly).
- **CVE-2019-15608 / GHSA-hjxc-462x-x77j (yarnpkg/yarn, fixed 1.19.0, TOCTOU / CWE-353-shaped)**:
  yarn computed a package's integrity hash when WRITING it to the local cache, but did not
  re-verify that hash when READING the same package back out of cache on a later install — so a
  crafted `yarn.lock` (or anything able to place a file into the cache under an arbitrary
  name/version) could poison the cache once and have every subsequent install silently trust the
  poisoned entry with no re-check. Fix added an explicit integrity re-check on the cache-read path:
  `if (integrity) { if (!remote.integrity || !ssri.parse(integrity).match(remote.integrity)) { throw
  new MessageError('Incorrect integrity when fetching from the cache'); } }`. This is the sibling
  "steady-state re-verification is silently skipped on one of the two paths that touch the artifact"
  variant, distinct from but structurally adjacent to the TOFU/first-resolution gap above. Fix commit
  `0474b8c66a8ea298f5e4dedc67b2de464297ad1c` (file: `src/package-fetcher.js`); companion commit
  `c3d256fcf641de4fe8d4d6034a2b046fafae30c0`. Sources:
  https://osv.dev/vulnerability/CVE-2019-15608 ,
  https://github.com/yarnpkg/yarn/commit/0474b8c66a8ea298f5e4dedc67b2de464297ad1c . Provenance:
  re-verified this session.
- **Third/fourth ecosystem anchors — anchors: TBD, verify from primary before citing.** Candidates
  worth checking but NOT verified this session (do not cite a SHA or advisory id for these without
  re-fetching): npm's tarball `shasum`/`integrity` field enforcement on install (whether a
  `package-lock.json`-recorded `integrity` mismatch is ever a non-fatal `EINTEGRITY` warning rather
  than an install-abort in some code path — several open npm/cli issues discuss integrity-mismatch
  UX but none seen this session is a clean security-fix commit); pip's `--require-hashes` mode, which
  is opt-in and (per `pypa/pip#13984`, an open, unfixed issue, not a disclosed advisory) does not
  extend to PEP 517 build-system dependencies even when enabled — a real, currently-open design gap
  in the same family but NOT a fixed CVE/GHSA, so it belongs in this card's activation vocabulary as
  a pattern to check for, not in the anchor list; cargo `Cargo.lock` checksum handling (no clean
  fixed-vulnerability anchor found this session, only long-open feature-request issues).

## Not this card
- **BCR archive-extraction path traversal** (`ZipDecompressor`/`StripPrefixedPath` tar-slip during
  `download_and_extract`) — a different mechanism (containment-check-on-extraction, not
  hash-integrity-on-fetch); route to `skills/vulns/path-traversal-lfi`. Per this engagement's own
  dossier this sub-surface is reported already-hardened (`startsWith` containment on entries and
  symlink targets) and functionally saturated (3+ 2026 duplicate reports) — do not re-litigate it
  under this card.
- **`UrlRewriter` credential-attach-after-rewrite confused deputy** (`.netrc`/credential-helper
  leaking a credential to an unintended host after a URL rewrite) — a confused-deputy/credential-
  scoping bug, not an integrity-check bypass; closer to `skills/patterns/ssrf-server-side-fetch`'s
  destination-binding shape, though that card is a partial fit at best (per the dossier, it's
  keyword-only on "credential"). Track separately; do not fold a credential-leak finding into an
  integrity-nonenforcement writeup just because both live on the same fetch code path.
- **`IndexRegistry` unrestricted registry URI scheme/host** (the registry itself can be pointed
  anywhere, http/https/file, with no allowlist) — a distinct SSRF/destination-trust gap. It only
  strengthens THIS card's severity when it is the mechanism by which a transitive dependency
  achieves the reachability this card's Grading section asks about; on its own, with no integrity
  angle, it is a different finding.
- A hash-mismatch that IS correctly hard-failed, even if the error message is confusing or the
  failure mode is noisy/inconvenient — that is the control working, not a finding.

## Do not overclaim
- A hash/integrity field existing in a lockfile schema, or a `validateChecksum`-style function
  existing in source, is not evidence of enforcement. Read the exact branch on mismatch and on
  absent-hash before claiming anything beyond `weak`.
- "The client didn't print an error" is not the same as "the client used the substituted content."
  Confirm the substituted artifact was actually loaded/compiled/extracted into the build graph — a
  silently-skipped optional check with no actual downstream use of the unverified content is a much
  weaker claim than an accepted-and-used substitution.
- A reproduced accept that is reachable ONLY through the root module's own self-controlled
  configuration is real but capped at `medium` per the Grading section above — do not write it up as
  a critical supply-chain compromise without a demonstrated transitive path.
- Citing CVE-2026-42501 or CVE-2019-15608 as precedent for this class's severity/plausibility is
  legitimate; presenting either as a currently-exploitable bug in the patched, released versions
  cited (go1.25.10+/go1.26.3+, yarn 1.19.0+) — or presenting an unverified candidate anchor (npm
  `EINTEGRITY` UX issues, the open `pip#13984` build-dependency gap, cargo checksum feature requests)
  as a disclosed, fixed CVE — is overclaiming and must not appear in any report.
- The TOFU/first-resolution gap and the steady-state re-verification gap are DISTINCT mechanisms
  (see the two anchors above) — name which one your finding is before writing it up; do not blur them
  into one generic "integrity not enforced" claim.
