# F13 — Committed decryptable credentials in composite actions (google OSS VRP candidate)

- **Engagement:** angular-dev-infra-2026-08 · **Pinned commit:** `04230133d395dfb032d782b8e63b4fcbbd406aa5` (2026-08-07T14:06:09Z)
- **Attribution:** `angular/dev-infra` — the wrapping scheme is dev-infra code (target/constants-gcp.ts, target/encrypt-gcp.ts, target/index-gcp.ts, target/action-saucelabs.yml). Not a consumer-wiring bug, not a platform bug, not third-party.
- **Attacker position:** unauthenticated reader of the public repository. No GitHub account needed. Proven from this position (local decryption, no privileges).

## One sentence on why it is real

The repository commits three production credentials encrypted with AES-256-GCM whose key (`GITHUB_REPOSITORY_OWNER` padded = `"angular"` + 25×`<`), IV (hardcoded literal), and GCM auth tag (committed literal) are all **public** — so any reader of the public repo deterministically decrypts them, including the full RSA private key of Google-internal GCP service account `bazel-developer@internal-200822.iam.gserviceaccount.com` (project `internal-200822`).

## Mechanism (source → sink → path)

1. `target/constants-gcp.ts:9-12` — `alg='aes-256-gcm'`, key `process.env.GITHUB_REPOSITORY_OWNER!.padEnd(32,'<')` (→ `"angular"+padding`, public), IV `'000003213213123213'` (committed), auth tag `'QwbjZ/z+yDtD+XZjKj9Ynw=='` (committed).
2. `target/action-saucelabs.yml:10` and `target/action-browserstack.yml:10` commit the other two GCM tags as the `NGAT` env value their `constants.ts:10` reads.
3. `target/index-gcp.ts` (each action) decrypts the committed `*_token.data` blob with exactly those public values at action runtime.
4. Recovered plaintexts (secret values redacted; sha256 recorded as evidence):
   - `gcp_token.data` → GCP service-account JSON: project `internal-200822`, client_email `bazel-developer@internal-200822.iam.gserviceaccount.com`, full RSA `private_key` (PEM). sha256 `6aef944b68cebd5e87a5ac8f362e1426979e5d7f8acb6eb19c48fbdf2b72d9a5`.
   - `browserstack_token.data` → `{BROWSER_STACK_USERNAME: "angularteam1", BROWSER_STACK_ACCESS_KEY: <redacted>}`. sha256 `b2c3dcc2abb7c5d768c5383c39531539d39477a3535045db87ceb4616d5d9e09`.
   - `saucelabs_token.data` → `{SAUCE_USERNAME: "josephperrott", SAUCE_ACCESS_KEY: <redacted>}`. sha256 `8250713a4cad1bde2b05d69d64269f3751eee86e2ced4d1b1d8d40fe97e3f645`.

## Controls and why they do not hold

- GCM integrity tag **is** enforced (tampered ciphertext / wrong tag / wrong IV all reject) — integrity is fine; confidentiality is zero because key, IV and tag are public.
- `setSecret()` masking only hides values in job logs — irrelevant to recovery from the repo.
- GitHub secret scanning is defeated by the wrapper: the raw `-----BEGIN PRIVATE KEY-----` never appears in the tree, so the committed key is invisible to the platform's own scanners (negative-hygiene effect of the wrapper).

## Negative controls (byte-identical harness)

- Tampered ciphertext (1 byte flipped) → GCM reject. Wrong tag → reject. Wrong IV → reject. (attempts f13-002, f13-003; evidence/calibration.txt.)
- The discriminator is proven to distinguish correct-material decrypt from anything else.

## Replay / contamination

- Four independent fresh-process decryptions (orchestrator ×2, three independent fresh-context agents) produce identical sha256 values. Contamination ruled out: pure local computation on public repo content.

## Impact (honest ceiling)

- **Confirmed:** full private-key material of a GCP service account used by Angular's RBE remote execution/cache (`target/bazelrc.common:53-71` — instance `projects/internal-200822/instances/primary_instance`, `--google_default_credentials`) plus two third-party SaaS credential sets, recoverable by anyone, with zero non-public material.
- **Liveness — inferred HIGH (2026-08-13):** public workflow-run metadata shows the Pull Request workflow (which materializes this exact credential via configure-remote on fork-triggerable pull_request events) completed `success` on 2026-08-12 and is in production use today; the DevInfra workflow succeeded 2026-08-13T06:55Z. The key authenticates in production CI on every PR. (Not cryptographic proof — CI observability, metadata only.)
- **Unverified (out of scope, requires Google-side facts):** the SA's IAM grants. Repo evidence shows the SA is used for remote *execution* and cache *reads* (uploads disabled via `--remote_upload_local_results=false`, `target/bazelrc.common:81-86`; the trusted-build tier uses a separate secret `RBE_TRUSTED_BUILDS_USER`).
- **Conditional escalation (hypothesis, not claimed):** if the key is live and the SA holds ActionCache/CAS write IAM on `primary_instance`, the same credential enables RBE cache poisoning → compromised build outputs in Angular org CI → SCC (top band). This is presented to the program as a hypothesis requiring their triage-side facts, not as a demonstrated claim.
- **OSS VRP category:** Other — leaked credentials (~$1,000 at OT0). Not filed as SCC.

## Severity vector

CVSS:3.1/AV:N/AC:H/PR:N/UI:N/S:U/C:H/I:N/A:N = 5.9 (Medium).
Rationale: vector is network (public repo), complexity HIGH because the impact requires the recovered key to be live and to hold grants (unverified out-of-scope), confidentiality HIGH if live. Matches the claimed severity `medium`.

## Remediation

1. Rotate all three credentials immediately (GCP SA key, BrowserStack, SauceLabs).
2. Stop committing credentials with public-key wrappers — use workflow/org secrets (the repo already does this correctly for the Angular Robot App keys, which are secret-sourced: `target/utils.ts:16`).
3. Delete `encrypt.ts`/`constants.ts` token wrapping; keep the credential in CI secrets only.

## Impact addendum (verified 2026-08-13) — the credential's role in CI

- The embedded credential is not dormant: `pr.yml` (pull_request, fork-triggerable) runs `configure-remote` with NO `google_credential` input on every PR (`pr.yml:28,74`) — the embedded key materializes on the runner and authenticates the PR test job to RBE.
- The PR test job submits REMOTE EXECUTION (not just cache reads) to `internal-200822/primary_instance` (`.bazelrc.common:54,69-71`; `configure-remote/index.ts:34,38`; `pr.yml:78`), with the default platform `platform_with_network` (`dockerNetwork: standard`, `.bazelrc.common:75-77`; `BUILD.bazel:28-38`).
- The PR's checked-out tree defines the platform: `@devinfra` resolves via `local_path_override` to the fork-controlled checkout, so `exec_properties` (network mode incl. `google_private`, `Pool`, `container-image`) are attacker-editable. Whether the RBE backend honors them for this project is a Google-side unknown.
- Marginal contribution (adjudicated): a fork PR adds no capability beyond the already-public key — anyone can already authenticate as the SA. The PR path is the demonstration that the credential IS the gate on internal remote execution for unauthenticated actors. Named Google-side facts that decide severity: (a) SA liveness + IAM, (b) exec_properties/network-mode enforcement, (c) instance-level access controls (IP allowlists).

## Unresolved caveats

- Liveness and IAM of the GCP SA (out of scope to test; live probing is wire 2/4 and forbidden).
- Novelty not yet checked (deliberate late act; operator performs before filing).
- Kernel-level adjudication review records: three independent reviews accompany this package (`reviews/`); claim adjudication and promotion gates run by the operator before any filing. Filing is operator-only (wire 5).

*Internal research artifact for operator re-authoring — never pasted verbatim into a submission.*
