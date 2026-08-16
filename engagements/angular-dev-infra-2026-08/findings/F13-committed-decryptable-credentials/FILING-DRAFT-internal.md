# F13 INTERNAL FILING DRAFT (superseded)

> **Superseded 2026-08-14 by `HUMANIZED-REPORT.md`** (filing-ready draft in the humanized voice, per reporting/human-report-voice). Keep this file for the technical corrections record (browserstack IV, RBE_TRUSTED_BUILDS_USER citations).

# F13 — INTERNAL FILING DRAFT (operator re-authors; never paste verbatim)

Engagement: angular-dev-infra-2026-08 · Pin: `04230133d395dfb032d782b8e63b4fcbbd406aa5` (2026-08-07T14:06:09Z)
Category target: leaked credentials ("Other"), with a conditional SCC hypothesis (unproven).

---

## 1. Advisory writeup (~25 lines)

**Title:** Publicly decryptable production credentials committed to `angular/dev-infra` composite actions

**Summary.** Three production credentials are committed to the public repository encrypted with
AES-256-GCM whose key, IV, and auth tag are all public, so any unauthenticated reader of the repo
deterministically recovers them — including the full RSA private key of Google-internal GCP service
account `bazel-developer@internal-200822.iam.gserviceaccount.com` (project `internal-200822`), plus
BrowserStack and SauceLabs credential sets.

**Affected asset + commit.** `github.com/angular/dev-infra` @ `04230133d395dfb032d782b8e63b4fcbbd406aa5`.

**Technical details.** The scheme is dev-infra's own wrapper (attribution = dev-infra, not consumer
wiring):
- `github-actions/bazel/configure-remote/constants.ts:9-12` — `alg='aes-256-gcm'`; key
  `process.env.GITHUB_REPOSITORY_OWNER!.padEnd(32,'<')` (= `"angular"` + 25×`<`, public); IV
  `'000003213213123213'` (committed); auth tag `'QwbjZ/z+yDtD+XZjKj9Ynw=='` (committed).
- `github-actions/saucelabs/action.yml:10` and `github-actions/browserstack/action.yml:10` commit the
  other two GCM tags as the `NGAT` env value read by each action's `constants.ts:10`.
- `github-actions/bazel/configure-remote/index.ts:59-63` (and the sibling saucelabs/browserstack
  `index.ts`) decrypt the committed `*_token.data` blob with exactly those public values at runtime.

**Proof (decrypt steps; sha256 of recovered plaintexts):**
1. key = `Buffer.from('angular'.padEnd(32,'<'))`; IVs: GCP and SauceLabs use 000003213213123213; BrowserStack uses a distinct IV 104149904141653713 (constants.ts:12). Per-blob auth tags from the lines above.
2. `createDecipheriv('aes-256-gcm', key, iv).setAuthTag(Buffer.from(tag,'base64'))` over the committed
   `*_token.data` blob.
3. `gcp_token.data` → GCP SA JSON (project `internal-200822`, client_email
   `bazel-developer@internal-200822.iam.gserviceaccount.com`, full RSA `private_key` PEM).
   sha256 `6aef944b68cebd5e87a5ac8f362e1426979e5d7f8acb6eb19c48fbdf2b72d9a5` (len 2368).
4. `browserstack_token.data` → `{BROWSER_STACK_USERNAME:"angularteam1", BROWSER_STACK_ACCESS_KEY:<redacted>}`.
   sha256 `b2c3dcc2abb7c5d768c5383c39531539d39477a3535045db87ceb4616d5d9e09` (len 100).
5. `saucelabs_token.data` → `{SAUCE_USERNAME:"josephperrott", SAUCE_ACCESS_KEY:<redacted>}`.
   sha256 `8250713a4cad1bde2b05d69d64269f3751eee86e2ced4d1b1d8d40fe97e3f645` (len 101).

**Negative controls (byte-identical harness).** Tampered ciphertext (1 byte flipped) → GCM reject;
wrong tag → reject; wrong IV → reject. GCM integrity is enforced; confidentiality is zero because key,
IV, and tag are public.

**Impact.**
- *Confirmed:* full private-key material of a GCP SA used for Angular RBE remote execution/cache
  (`.bazelrc.common:54,69-71` — instance `projects/internal-200822/instances/primary_instance`,
  `--google_default_credentials`) plus two third-party SaaS credential sets, recoverable with zero
  non-public material.
- *Liveness — inferred HIGH (2026-08-13):* public workflow-run metadata shows the fork-triggerable
  `pull_request` workflow that materializes this credential via configure-remote completed `success`
  2026-08-12, and the DevInfra workflow succeeded 2026-08-13T06:55Z; the key authenticates in
  production CI. This is observability inference, not cryptographic proof.
- *IAM caveat (unverified, Google-side):* repo evidence shows remote *execution* and cache *reads*
  (`--remote_upload_local_results=false`, `.bazelrc.common:81,86`); the trusted-build tier uses a
  separate secret (`secrets.RBE_TRUSTED_BUILDS_USER (ci.yml:65, update-models.yml:29, rules_browser-update-browsers.yml:29)`, `.bazelrc.common:91`).

**Conditional SCC escalation — hypothesis only.** If the key is live **and** the SA holds
ActionCache/CAS write IAM on `primary_instance`, the same credential enables RBE cache poisoning →
compromised build outputs in Angular org CI → SCC (top band). The two named missing facts are:
(1) **GCP SA key liveness** (is the credential still valid/rotated?), and
(2) **the SA's IAM grants** (does it hold CAS/ActionCache write on `primary_instance`?).
Neither is testable in-scope (live probing is forbidden); both require Google-side triage facts.

**Remediation.**
1. Rotate all three credentials immediately (GCP SA key, BrowserStack, SauceLabs).
2. Stop committing credentials behind public-key wrappers — use workflow/org secrets (the repo already
   does this correctly for the Angular Robot App keys: `github-actions/utils.ts:16`).
3. Remove the `encrypt.ts`/`constants.ts` token wrapper; keep credentials in CI secrets only.

---

## 2. Eligibility self-check (program-policy.md §1-8)

- **§1 Tier:** `angular/dev-infra` → **TIER_OT0**, `SCOPE_OSS_VRP` (primary-verified via
  `google/bughunters` `external_repositories.txtpb`). Top payout band.
- **§2 Scope / up-to-date:** repo configuration and GitHub Actions workflows are explicitly in scope;
  pinned to `main` HEAD `04230133…` — re-pin before filing to satisfy "up-to-date".
- **§3 Category:** disclosed credential → **Other / leaked credentials (~$1,000 at OT0)**. SCC applies
  only as the conditional hypothesis; do not inflate the category.
- **§4 March-2026 rules:** memory-safety gate **N/A** (TS/JS/YAML/Starlark — no memory corruption).
- **§5 Hard constraints:** latest version only (re-pin); no third-party dependency flaw (upstream-first
  N/A); no destructive/production testing (all work was local, disposable, public-repo reads only);
  operator attests not a Google/partner employee or sanctioned party.
- **§6 Attribution:** **dev-infra-attributable** — the wrapper scheme is dev-infra code, not consumer
  wiring, not platform, not third-party.
- **§7 Recon facts:** consistent with recon (secret wrapper surface, RBE secrets, SHA-pinned fan-out).
- **§8 AI-authorship:** this is an internal research artifact; the operator personally re-authors the
  final submission and files (wire 5). Never paste verbatim.

---

## 3. CVSS vector + rationale

`CVSS:3.1/AV:N/AC:H/PR:N/UI:N/S:U/C:H/I:N/A:N = 5.9 (Medium)`

- **AV:N** — recovery requires only the public repository (network).
- **AC:H** — impact requires the recovered key to be live and hold IAM grants (unverified,
  out-of-scope); confidentiality is only realized if liveness holds.
- **PR:N / UI:N** — no privileges or interaction; unauthenticated public reader.
- **S:U / C:H / I:N / A:N** — scope unchanged; confidentiality high if live; no direct integrity or
  availability impact demonstrated. Matches claimed severity `medium`.

---

## 4. Operator MUST verify before filing

1. **Novelty** — definitive search for prior disclosure of the wrapper scheme / committed
   decryptable-token blobs (preliminary web search found none; only adjacent PR #3827 cache-poisoning
   context). File only if not previously disclosed/already fixed.
2. **Liveness confirmation** — re-pin to `main` HEAD; confirm the GCP SA key is still active (rotation
   status / metadata), satisfying the "up-to-date" and impact requirements.
3. **Reward-category pick** — choose **leaked credentials ("Other")** vs the conditional **SCC**
   escalation; keep the SCC framing a hypothesis unless the two missing facts (liveness + IAM write
   grants) are confirmed.
4. **Re-verify reward amounts / rules** at `bughunters.google.com/open-source-security` (SPA — the
   amounts here are secondary-source corroborated, not primary-verified).
