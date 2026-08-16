# Committed production credentials in angular/dev-infra composite actions are decryptable by anyone

**Internal filing draft for operator re-authoring. Never paste verbatim (program AI-authorship policy).**

## Summary

`angular/dev-infra` ships three production credentials encrypted with AES-256-GCM where the key, the IV and the auth tag are all committed in the same public repository. The key is the org name padded to 32 bytes. The IV is a hardcoded literal. The GCM tags sit in `constants.ts` or in the composite action's action.yml as an env value. Anyone who can read the repo can decrypt all three offline, and one of them is the full RSA private key of a GCP service account used for remote build execution inside Google's `internal-200822` project.

## Affected component & versions

- `angular/dev-infra`, commit `04230133d395dfb032d782b8e63b4fcbbd406aa5` (2026-08-07), current `main`
- `github-actions/bazel/configure-remote/` (`gcp_token.data`, `constants.ts`, `encrypt.ts`, `index.ts`)
- `github-actions/browserstack/` and `github-actions/saucelabs/` (same pattern, tags in `target/action-browserstack.yml` and `target/action-saucelabs.yml`)
- Introduced by dev-infra's own code; not a third-party dependency issue

## Vulnerability details

The wrapper is in `constants.ts` for each action:

```ts
export const alg = 'aes-256-gcm';
export const at = process.env.NGAT!;                    // browserstack/saucelabs; committed literal for gcp
export const k  = process.env.GITHUB_REPOSITORY_OWNER!.padEnd(32, '<');
export const iv = '000003213213123213';                 // browserstack uses a different literal
```

`GITHUB_REPOSITORY_OWNER` for this repository is the public org name `angular`. Padded, that is the
entire key. The IVs are literals in the same file. For GCP the auth tag is a committed literal in
`constants.ts`; for BrowserStack and SauceLabs it is committed in each action's own action.yml under `NGAT` (shipped as `target/action-browserstack.yml`, `target/action-saucelabs.yml`). The
ciphertext blobs are committed next to all of it.

So the encryption does exactly one job: it keeps the plaintext out of GitHub's secret scanner. It
provides no confidentiality against a reader.

`index.ts` in each action decrypts at runtime with exactly these values and uses the result. The
GCP one writes the recovered service account JSON to
`~/.config/gcloud/application_default_credentials.json` and exports
`GOOGLE_APPLICATION_CREDENTIALS`.

## Steps to reproduce

**Fast path (triager):**

```sh
git clone https://github.com/angular/dev-infra.git
cd dev-infra && git checkout 04230133d395dfb032d782b8e63b4fcbbd406aa5
node poc/decrypt.mjs .
```

The script reads the key material from the checkout itself, decrypts all three blobs, prints a
sha256 per plaintext, and runs the negative controls. It exits 0 only if everything decrypts and
the controls reject.

**Full walkthrough:**

1. Read `github-actions/bazel/configure-remote/constants.ts`. The key derivation is
   `GITHUB_REPOSITORY_OWNER.padEnd(32, '<')`. `GITHUB_REPOSITORY_OWNER` is the repository owner,
   which is `angular`. That is the whole key: `"angular"` plus padding.
2. Read `github-actions/bazel/configure-remote/gcp_token.data`. 2368 bytes of ciphertext.
3. Decrypt with AES-256-GCM, key from step 1, IV `000003213213123213`, auth tag
   `QwbjZ/z+yDtD+XZjKj9Ynw==` (both committed in `constants.ts`).
4. Expected: valid service account JSON for `bazel-developer@internal-200822.iam.gserviceaccount.com`
   in project `internal-200822`, including a full RSA private key. sha256
   `6aef944b68cebd5e87a5ac8f362e1426979e5d7f8acb6eb19c48fbdf2b72d9a5`.
5. Repeat for `browserstack_token.data` and `saucelabs_token.data` using the `NGAT` values committed
   in each action's action.yml (shipped as `target/action-browserstack.yml`, `target/action-saucelabs.yml`). sha256s in the PoC README.
6. Negative control: flip one byte of the GCP ciphertext and decrypt again. GCM rejects it. Wrong
   tag, wrong IV: same. The discriminator only accepts the exact committed material.

I reproduced this from a clean clone on 2026-08-13. No live system was touched; the PoC is pure
local computation on the repository.

## Impact

Whoever can read the public repository, which is everyone, obtains:

- the full private key of GCP service account `bazel-developer@internal-200822.iam.gserviceaccount.com`. The repo's own CI uses this credential as the application default for Bazel remote execution and remote cache reads on instance `projects/internal-200822/instances/primary_instance` (`pr.yml` runs `configure-remote` with no credential input on fork-triggerable `pull_request` events). Public workflow run metadata shows that path completing successfully as recently as 2026-08-12, so the key is in active use.
- a BrowserStack account (`angularteam1`) and a SauceLabs account (`josephperrott`), both with access keys.

What the key can actually do beyond what the repo shows (RBE execution and cache reads) depends on the service account's IAM grants, which I cannot check from the repository. If the account holds write grants on the RBE cache or anything else in the project, the ceiling is considerably higher, up to build-output poisoning of the Angular org's CI. I am flagging that as a hypothesis the team can confirm in minutes, not as a demonstrated claim.

Two smaller points. The wrapper defeats GitHub's secret scanning, so the key has never been flagged or rotated by automation. And the same wrapping pattern exists in `angular/angular-cli` (MCP tooling), which I found during an org-wide sweep; that is a separate repository and I am mentioning it here only so it does not get lost.

## Severity

CVSS:3.1/AV:N/AC:H/PR:N/UI:N/S:U/C:H/I:N/A:N = 5.9 (Medium)

- AV:N: the attacker needs nothing but the public repository.
- AC:H: the impact depends on the recovered key being live and holding grants. The repo shows the credential in active daily CI use, which makes that plausible, but liveness and IAM are not provable from the repository alone. I am rating the uncertainty into complexity rather than pretending it away.
- PR:N / UI:N: no privileges, no interaction.
- S:U, C:H: the disclosure itself is confirmed; the confidentiality impact is high only if the key is live, which the CI evidence supports. I:N/A:N: no integrity or availability claim is demonstrated.

Leaked credentials of this kind land in the program's "Other" category. If the IAM check shows write access to the RBE cache or broader project access, this becomes a supply-chain issue and should be re-scored. I have not filed it as SCC because I cannot demonstrate the higher impact from a source audit alone.

## Supporting material

- `poc/decrypt.mjs` + `poc/README.md` (attached; reproduction script with negative controls)
- `evidence/calibration.txt` (matched positive/negative control runs)
- `target/` copies of the pinned `constants*.ts`, `action-*.yml`, `index-gcp.ts`, `bazelrc.common`, `pr.yml` files the claims cite

## Novelty / duplicate check

I searched for public disclosure of this scheme (decryptable committed token blobs with org-name keys in dev-infra) before finalizing. I found nothing describing the wrapper or the recovered credentials. The closest public items are general cache-poisoning discussions in the repo's own PR history, which are a different mechanism. A definitive duplicate check against the program's disclosed reports should still be done by the reviewer before filing; this is a source-audit finding and I could not verify every prior disclosure offline.

## Suggested fix

1. Rotate all three credentials now. The GCP key and both SaaS access keys must be treated as public.
2. Stop committing credentials with a reversible wrapper. The repository already does this correctly for its most valuable secrets: the Angular Robot App private keys live in workflow secrets and never in the tree. The `*_token.data` + `constants.ts` scheme should be deleted and replaced with secrets.
3. Remove `encrypt.ts` and the decrypt paths once rotation is complete, so the pattern cannot be reused by accident.

Happy to retest after rotation, and to share the full evidence trail if any step needs more detail.
