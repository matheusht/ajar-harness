# W1 — FILING PACKAGE (operator re-authors before submission)

**Finding:** `findings/W1-yarn-classic-disttags-win32/REPORT.md` — Windows command injection via unvalidated registry `dist-tags` values (finding #6, PROMOTED, 7/7 gates CLEAR).
**Pin:** `d827ba9005b86b23d05ee7c62c0823367aa245c1` (2026-08-13). **Package date:** 2026-08-15.
**Assembled from:** W1 REPORT (all deep-phase + chainstorm amplifiers), `W1-filing-viability.md`, `humanized-W1-draft.md`, `w1poc/OUTPUT.txt`, `w1-windows-e2e-runbook.md`, `FILING-COVER.md`, `FILING-SEQUENCE.md` (row 3).

---

## 0. Delta-first opening (the lede — what the triager reads first)

A fork PR to a repo whose Windows CI runs `ng add` or `ng update` on the PR checkout — or a developer who runs those commands in a cloned repo — executes the attacker's command **from registry metadata alone, with zero interaction**: the unvalidated `dist-tags` value from the configured registry is interpolated into a double-quoted, unescaped win32 shell string (`"pkg@1.0.0" & calc & ""`), and `cmd.exe` runs the trailing command before any confirmation prompt, before any install, and regardless of `--ignore-scripts`. On a Windows CI runner the injected process **inherits the job's tokens** (read-scoped `GITHUB_TOKEN`, `ACTIONS_RUNTIME_TOKEN`, and an OIDC cloud token when `id-token: write` is granted) — the exfil goes straight to the attacker's registry server over outbound HTTP. The same value also **poisons the developer's package.json** so later installs re-fetch it.

This is a regression/bypass of the maintainers' prior fix **#32509** (2026-03, `severity6: security`, same injection shape): the full fix PR **#32892 was rejected**, but the *narrow channel this report describes — the registry-controlled dist-tag VALUE — was not covered by that decision*, and it is **undisclosed** (searched). We cite #32509, #32892, #32678, and the quote-wrap commit `85e3ce2e0` up front because the first response will otherwise be "covered by the doctrine".

---

## Part A — Core claim: registry-controlled `dist-tags` VALUE → win32 RCE (mechanism, source-verified at the pin)

1. `getManifest` tag case (`packages/angular/cli/src/package-managers/package-manager.ts:572-590`): `versionSpec = fetchSpec ?? 'latest'`; for `requiresManifestVersionLookup` descriptors: `versionSpec = metadata['dist-tags'][versionSpec]` — **no semver/charset validation** of the value.
2. `getRegistryManifest` (`:520-523`): `specifier = requiresQuoting ? "${packageName}@${version}"` — the `85e3ce2e0` quoting fix wraps but does **not escape embedded `"`**.
3. `host.ts:157-164` (win32): `spawn(`${command} ${args.join(' ')}`, { shell: true })` — the wrapped specifier with an embedded quote closes the wrapper; `&`/`|`/`;` after it execute on `cmd.exe`.
4. Malicious value shape (from `w1poc/OUTPUT.txt` CASE A): `dist-tags.latest = "1.0.0\" & echo W1-POC-MARKER-4f7c2a & \""` → joined string `yarn info --json --verbose "attacker-pkg@1.0.0" & echo W1-POC-MARKER-4f7c2a & ""` → **marker executed as a standalone command** (CASE A: YES; CASE B benign control: NO; CASE C POSIX array-spawn negative: NO — the discriminator proving the win32 shell-string join is the sink).

**Trust boundary crossed:** registry response `dist-tags` (attacker-influenceable via a cloned repo's `.npmrc`/`.yarnrc` registry line or a compromised mirror) → unvalidated string → win32 shell command → arbitrary command execution on the developer machine / CI runner, **ungated and unconfirmed**.

**Marginal delta (why this is not the already-rejected fix):** without the bug an attacker registry can still serve a malicious tarball, but its install scripts are gated by `--ignore-scripts` (when enabled) plus the interactive confirmation. With the bug: arbitrary command execution **from metadata alone**, before both gates — `--ignore-scripts`-mitigation bypass.

**Trigger ordering (verified in the Listr flow):** the metadata fetch (`loadPackageInfoTask`, add/cli.ts:520-531) executes BEFORE the confirmation task (:570) and the install task; the non-TTY abort at confirmation does not prevent the already-executed fetch+injection. Additional triggers at add/cli.ts:363 and :458.

## Part B — Entry-point venues

| Venue | Entry | Manager bound | Confirmation | Order proof |
|---|---|---|---|---|
| `ng add <pkg>` (bare specifier → `getManifest('pkg@latest')`) | yarn-classic metadata fetch | **yarn-classic only** (requiresManifestVersionLookup) | fetch precedes the confirmation task | add/cli.ts:221 precedes :227 (kill-pair-adjudicated) |
| `ng update <pkg>@latest` | `update-resolver.ts` dist-tags resolution — `_buildPackageInfo` (:495-527), `resolvePackageVersion` (:604-627), `_addPackageGroup` (:630-668) → `getRegistryManifest` (:515-523) | **MANAGER-INDEPENDENT (npm default — `view --json`)** | **no gate at all** | resolve loop (:947-992, spawn :967) runs BEFORE `packageInfoEntries` (:997-1008); the `semver.lte` throw (:527) is post-injection masking |
| **Version-check venue (WAVE-B addition)** | `cli-version.ts:63` — runs on **EVERY** `ng update`; the version-check fetch uses the same tag-case + quote-wrap + shell:true chain (the FS-W1 V7 "compared only" claim is true only post-fetch; the FETCH itself interpolates) | manager-agnostic | no gate | same sink chain |
| **CI-token venue (chainstorm amplifier)** | fork PR → repo CI runs `ng add`/`ng update` on the PR checkout (e2e/scaffolding jobs; app-update flows) on `windows-latest`; PR ships the malicious `.yarnrc`/`.npmrc` (silent registry redirect, no validation) | manager-independent | none | env inheritance `host.ts:150-165` |

**Secret reach (CI venue, verified at source):** the injected cmd.exe inherits the step env — **read-scoped `GITHUB_TOKEN` by default** on `pull_request` (repo default permissions), `ACTIONS_RUNTIME_TOKEN`/`ACTIONS_RUNTIME_URL` (always present), `ACTIONS_ID_TOKEN_REQUEST_TOKEN`/`URL` only when `permissions: id-token: write`. Arbitrary repo secrets (incl. robot keys) are NOT in the step env unless explicitly mapped. Exfil: attacker registry server over outbound HTTP (default-allowed).

**Shape framing (honest caps):** the CI venue is per-repo conditional (primary = e2e/scaffolding CI on PR content; Angular's own CI is structurally not reachable — S6); dependency-update BOT runs are a different attacker model (bot token) and are excluded.

## Part C — Persistence: package.json poisoning (WAVE-B addition, W1-CS V3)

On the update path the unvalidated dist-tags value is ALSO written into the dev's `package.json` dependencies (`updateDependencies`) — the poisoned version string survives the run; a later install re-fetches it (second-stage vector).

## Part D — Severity (venue-split, derived; operator decides the filing split)

| Venue | Vector | Score | Filing recommendation |
|---|---|---|---|
| Dev machine (`ng add`/`ng update` interactive) | CVSS:3.1/AV:N/AC:H/PR:N/UI:R/S:U/C:H/I:H/A:H | 7.5 | File as Low-Medium per the doctrine (won't-fix risk); the delta framing carries it |
| Fork-PR CI (attacker-triggered, no user interaction) | AV:N/AC:H/PR:N/UI:N/S:U/C:H/I:H/A:H | **8.1 base; conditional High with the OIDC/ID-token branch** | Strongest counter to the won't-fix doctrine; file as part of W1 or as a separate entry (operator choice) |

Both vectors share one root cause (unvalidated dist-tags value → quote-wrap → win32 shell:string); the CI venue changes only the interaction/precondition constants.

## Part E — Doctrine citations + novelty (MANDATORY for the filing)

- **#32509** (2026-03): the sink class triaged `severity6: security`, same injection shape; the pin POSTDATES it.
- **#32892**: the full fix PR — **REJECTED** (maintainers documented a won't-fix doctrine 2026-03-27 treating package-manager specifier handling under config-trust).
- **#32678**: fixed the git executor only (a different spawn site).
- **`85e3ce2e0`** (2026-02-23): the quote-wrap (the bypass vehicle — wraps without escaping); **`d8b76e93d`** (2025-12): the unvalidated dist-tag lookup.
- **Novelty:** the registry-controlled VALUE channel is undisclosed (searched: no issue/PR/advisory). NEAR-MISS framing: fix-bypass/regression, not first-report.
- **Co-credit disclosure:** same-day same-reporter cluster **#33074/#33075/#33076/#33077** (foxllb, 2026-04-28) on adjacent injection surfaces — an active independent researcher; disclose it in the filing.

## Part F — Evidence (what to attach)

1. **`payload-proposals/w1poc/`** — `w1poc.cjs` (compiled pin-source host + package-manager modules) + `OUTPUT.txt` (CASE A/B/C transcript: injection marker executes as a standalone command on the win32 shell-string shape; benign control clean; POSIX array-spawn negative clean — the discriminator).
2. **Static-only argument (in REPORT)** — the closed-loop 3-hop value trace + the Listr ordering proof; the single evidence-grade gap is physical cmd.exe on Windows (environment-blocked; every hop source-verified; the mechanism is not contested).
3. **`WINDOWS-E2E-FIXTURE.md`** (in the finding dir) + **`w1-windows-e2e-runbook.md`** (payload-proposals) — the exact commands a Windows run executes as the confirmation rung (local synthetic registry; no wires).
4. **Pin source copies** — `findings/W1-…/evidence/{package-manager.ts, host.ts, package-manager-descriptor.ts}` + `evidence/update-resolver-amp/README.md` (the ng-update amplifier anchors).

## Part G — Remediation (for the report)

1. Validate `versionSpec` from `dist-tags` with `semver.valid` at the SOURCE in BOTH `getManifest` and `getRegistryManifest`.
2. Never join args into a shell string on win32 — spawn array-form with `shell: false`, or escape embedded quotes.
3. Apply the same validation in the npm/pnpm descriptors' metadata paths (audit `getRegistryMetadata` for parallel unvalidated values).
4. Sanitize control characters from registry-derived display strings (the terminal-escape sibling note).

## Filing notes for the operator

- **Options:** (a) file-with-delta now, static-only (defensible: every hop source-verified; fixture documents the exact commands); (b) hold until the Windows E2E rung closes (any Windows host, method-2, no wires — the runbook is one command away); (c) split the CI-token venue into its own entry.
- **Sequence:** FILING-SEQUENCE.md row 3 — W1 sits after M3+D2 and E1-C1, before D3 (the D3 co-discovery race pulls it up). If a Windows host appears before the operator session, run the fixture and W1's risk drops.
- **The zero-interaction CI-token delta is the strongest counter to the doctrine** — keep it in the first paragraph.
- Redaction: no credentials in the evidence; the w1poc outputs are synthetic markers only.
