# PoC — committed credentials decrypt with public repo material only

Finding: F13-committed-decryptable-credentials
Target: `angular/dev-infra` @ `04230133d395dfb032d782b8e63b4fcbbd406aa5`

## What this demonstrates

Three credential blobs are committed under `github-actions/`, wrapped in AES-256-GCM. The key is
derived from the public org name (`GITHUB_REPOSITORY_OWNER` padded to 32 bytes), the IV is a
hardcoded literal in `constants.ts`, and the GCM auth tags are committed too (in `constants.ts` for
GCP, in the composite action's action.yml as `NGAT` for the other two). Every value needed to decrypt is in the public
repository. The encryption provides integrity, not confidentiality.

Recovered (sha256 of the plaintext):

| blob | sha256 | recovered kind |
|---|---|---|
| `github-actions/bazel/configure-remote/gcp_token.data` | `6aef944b68cebd5e87a5ac8f362e1426979e5d7f8acb6eb19c48fbdf2b72d9a5` | GCP service account JSON, project `internal-200822`, `bazel-developer@internal-200822.iam.gserviceaccount.com`, full RSA private key present |
| `github-actions/browserstack/browserstack_token.data` | `b2c3dcc2abb7c5d768c5383c39531539d39477a3535045db87ceb4616d5d9e09` | `{BROWSER_STACK_USERNAME: angularteam1, BROWSER_STACK_ACCESS_KEY}` |
| `github-actions/saucelabs/saucelabs_token.data` | `8250713a4cad1bde2b05d69d64269f3751eee86e2ced4d1b1d8d40fe97e3f645` | `{SAUCE_USERNAME: josephperrott, SAUCE_ACCESS_KEY}` |

The script pulls the key material out of the checkout itself (constants*.ts, action-*.yml, the blobs).
Nothing is hardcoded except the org name, which is public. That is the point: a stranger with only
the repository can do exactly what the PoC does.

## Prerequisites

- Node.js 18+ (uses only the standard library)
- A checkout of `angular/dev-infra` at the pinned commit

```sh
git clone https://github.com/angular/dev-infra.git
cd dev-infra && git checkout 04230133d395dfb032d782b8e63b4fcbbd406aa5
```

## Fast path

```sh
node decrypt.mjs <path-to-checkout>
```

Expected output (trimmed):

```
[gcp] DECRYPT-OK  sha256=6aef944b68cebd5e87a5ac8f362e1426979e5d7f8acb6eb19c48fbdf2b72d9a5  fields={"project_id":"internal-200822","client_email":"bazel-developer@internal-200822.iam.gserviceaccount.com",...}
[browserstack] DECRYPT-OK  sha256=b2c3dcc2abb7c5d768c5383c39531539d39477a3535045db87ceb4616d5d9e09  fields={"BROWSER_STACK_USERNAME":"angularteam1"}
[saucelabs] DECRYPT-OK  sha256=8250713a4cad1bde2b05d69d64269f3751eee86e2ced4d1b1d8d40fe97e3f645  fields={"SAUCE_USERNAME":"josephperrott"}

negative controls:
  tampered ciphertext byte: rejected as expected
  wrong auth tag: rejected as expected
  wrong iv: rejected as expected

RESULT: PASS
```

Exit code 0. Add `--full` to print the plaintexts (not needed to verify the claim; they are public
anyway, but keeping them out of logs is good hygiene).

## Why the negative controls matter

A detector that fires on everything proves nothing. Here the GCM tag makes the discriminator
cryptographically exact: correct material decrypts, one flipped byte, a wrong tag, or a wrong IV all
reject. That is what rules out coincidence.

## What this does not claim

- The key's liveness and IAM scope are not verified here. The finding is the disclosure: the wrapper
  has zero confidentiality and the payload is a full service account key for a Google-internal
  project. Whether that key is still active and what it can do are Google-side facts.
- Nothing here touches any live system. The PoC is pure local computation on the public repository.
