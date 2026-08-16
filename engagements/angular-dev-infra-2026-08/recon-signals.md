# recon-signals.md — what recon saw → which cards it lit

Strength: `strong` (matches a card's `activation.strong` → load it) · `weak` (cheap look) ·
`negative` (the defense is present → likely-held + positive-control candidate, **not** a finding).

## Status

Rows below come from **read-only GitHub API recon on 2026-08-12**, during target selection. They are
real observations of the pinned tree, not priors. No live service was probed and no workflow was
triggered. Round 0 re-verifies each against the local clone at the pinned commit before acting.

## Activation signals

| Observation (abstract) | Where | Strength | Cards lit | Why / next move |
| --- | --- | --- | --- | --- |
| A `pull_request_target` + `issues` workflow feeds attacker-authored issue text to an LLM in a job that also holds a GitHub App private key | `.github/workflows/dev-infra.yml` → `github-actions/labeling/issue` with `ANGULAR_ROBOT_PRIVATE_KEY` + `GOOGLE_GENERATIVE_AI_KEY` | **strong** | `indirect-prompt-injection`, `llm05-improper-output-handling`, `llm06-excessive-agency`, `workflow-step-injection` | the decisive question is what constrains the model's output: a fixed label vocabulary, or anything that can steer a privileged call. Read the action's source before hypothesising |
| The same workflow carries a `zizmor: ignore[dangerous-triggers]` suppression whose stated reason is "workflow does not checkout untrusted code" | `.github/workflows/dev-infra.yml` line 1 | **strong** | same as above | a documented safety claim. It is correct about *checkout* — but checkout is not the only `pull_request_target` risk. Test whether the claim covers the actual exposure. This is a claim to falsify, not a control to trust |
| A second `pull_request_target` workflow holds the same App private key | `.github/workflows/assistant-to-the-branch-manager.yml` | **strong** | `workflow-step-injection`, `delegated-capability-attenuation` | independent entry point to the same crown jewel |
| An action exists whose sole job is detecting changes pushed **after** a PR approval, and all three consuming OT0 repos run it | `github-actions/post-approval-changes/` | **strong** | `unsafe-default-authz-helper`, `delegated-capability-attenuation` | defeat it and unreviewed code lands in three OT0 repos = source-integrity compromise, the top SCC shape |
| A publish action plus a `workflow_call` release workflow with `id-token: write` publishes four npm packages | `github-actions/release/publish/`, `.github/workflows/reusable-release.yml`, `ng-dev/release/publish/` | **strong** | `registry-lockfile-integrity-nonenforcement`, `verification-root-not-anchored` | "packages distributed via package managers" is verbatim SCC language |
| A built-package hashing step guards the publish path | `ng-dev/release/publish/directory-hash.ts` | **weak** | `verification-root-not-anchored` | an integrity control: read whether a mismatch hard-fails or is advisory. Do not infer enforcement from the field's existence |
| Release tooling constructs and runs external commands | `ng-dev/release/publish/external-commands.ts` | **weak** | `os-command-injection`, `injection` | check whether any input crossing into it is attacker-influenced at any tier |
| A self-hosted Renovate runner holds a **user** access token | `.github/workflows/ng-renovate.yml`, `.github/ng-renovate/runner-config.js` | **weak** | `registry-lockfile-integrity-nonenforcement`, `delegated-capability-attenuation` | a bot that rewrites dependency pins is a trust-anchor writer |
| A scheduled org-wide workflow holds **two** GitHub App private keys | `.github/workflows/org-wide-actions.yml` (`ANGULAR_ROBOT_PRIVATE_KEY`, `LOCK_BOT_PRIVATE_KEY`) | **weak** | `delegated-capability-attenuation` | scheduled, so no direct attacker trigger — reachability is the whole question |
| Remote-build-execution credentials sit in a scheduled workflow | `.github/workflows/update-models.yml` (`RBE_TRUSTED_BUILDS_USER`) | **weak** | `verification-root-not-anchored` | RBE cache poisoning reaches builds |
| Three credential blobs are committed to the repository | `github-actions/{bazel/configure-remote/gcp_token.data, browserstack/browserstack_token.data, saucelabs/saucelabs_token.data}` | **weak** | `information-disclosure` | check the wrapping. If properly wrapped this is a **negative** signal. Cheap to settle — settle it early and move on |
| Artifact pack-and-upload handles archives | `github-actions/previews/pack-and-upload-artifact/`, `.../upload-artifacts-to-firebase/` | **weak** | `path-traversal-lfi`, `arbitrary-file-upload` | archive entry handling on a preview path fed by PR builds |

## Held defenses noticed (negative signals) — positive-control candidates

- **All 208 `uses:` references from the three consuming OT0 repos are SHA-pinned** (angular 62,
  angular-cli 55, components 91). Measured 2026-08-12. This **closes the automatic-propagation path**:
  a later write to dev-infra `main` does not reach consumers on its own.
  **What it does not close, and where the fan-out argument survives:** a flaw already present in the
  pinned SHA; the **pin-bump review path** (who reviews a Renovate SHA bump, and against what?); and
  the **App-key path**, where a stolen `ANGULAR_ROBOT_PRIVATE_KEY` reaches every repository directly
  and pinning is irrelevant. Re-point the fan-out family at those three, not at mutable refs.
- **Every action reference inside dev-infra's own workflows is SHA-pinned** — 41 pinned, 0 unpinned.
  Sharply better hygiene than most of the tier list. Treat unpinned-action hunting as likely dry here
  and spend the budget elsewhere.
- `permissions: contents: read` is declared as the default in several workflows. Verify per job;
  a job-level override is what would matter.

## Override log (strong signals NOT pursued)

For any **strong** signal on a high-impact path that was skipped, one line on why.

- (none — nothing skipped yet)
