# cascades.md — second-order discovery ledger

Every discovery is a branch, not an endpoint. When a finding or a significant research discovery
survives, interrogate it with two questions and record an answer for each, **even when the answer is
"nothing"**.

- **Q1 — how do I detect this same behaviour elsewhere?**
- **Q2 — does the ORIGIN of that behaviour enable a different attack?**

**Q1 mostly yields siblings. Q2 is where a new class comes from.** Every cascade lead re-enters the
funnel like any other hypothesis and may cascade again.

## Domain seeds

**Q1 seeds.** A flaw in one composite action → every action sharing that helper, that input-parsing
idiom, or that `@actions/*` call. A flaw in one `pull_request_target` workflow → the other one. A gap
in one bot's output handling → every other bot in `github-actions/` and `.github/local-actions/`. A
gap in `labeling/issue` → `labeling/pull-request`. A weakness in one Bazel rule → the sibling rules
shipped in the same package.

**Q2 seeds.** Read access to a workflow's environment becomes secret disclosure. Secret disclosure of
an App private key becomes org-wide write. Org-wide write becomes source compromise in three OT0
repos. Influence over a label becomes influence over a merge gate. Influence over a merge gate
becomes unreviewed code. A published-package write becomes execution in every consumer's CI. A
dependency-pin rewrite becomes a persistent trust-anchor change that survives the original access.

## Ledger

| cascade id | parent discovery | Q1 answer | Q2 answer | leads (file:line, hypothesis, why real or fake, confidence) | disposition |
|---|---|---|---|---|---|
| c1 | F13 committed decryptable credentials | NO siblings: full-repo sweep (createCipheriv/padEnd/NGAT/constants.ts idioms; *.data/*.enc/*.pem/*.key globs; public-derived key material) — the three known blobs are the entire class; the App private keys are correctly secret-sourced (utils.ts:16) | YES: GCP SA (bazel-developer@internal-200822) authenticates RBE exec+cache on instance internal-200822/primary_instance (bazelrc.common:53-71). IF key live AND SA holds ActionCache/CAS write IAM → cache poisoning → compromised build outputs in Angular org CI (SCC top band). Both conditions unassessable in scope. Also: pr.yml materializes the credential in fork-PR test jobs (no delta — credential public already) | SCC escalation chain documented in findings/F13 REPORT.md; hypothesis presented to program, not claimed | recorded; escalation capped at in-scope ceiling |
| c2 | F13 disclosure → wrapper hygiene | Q1: the encrypt-with-public-key idiom is unique to the three actions | Q2: wrapper defeats GitHub secret scanning (raw PEM never appears) — negative hygiene; rotation recommendation regardless of finding status | remediation list in findings/F13 REPORT.md | recorded |
| c3 | F6-CB CI-path dead hash | Q1: assertIntegrityOfBuiltPackages absent from entire github-actions bundle (tree-shaken) | Q2: artifact feed attacker-unreachable (same-run artifact binding + secret-gated workflow_call) → hardening gap only | recommend wiring hash compare in PublishCiTool | recorded |
| c4 | F9-A Renovate runner | Q1: sibling runners? ng-renovate is the only self-hosted runner in tree | Q2: postUpgradeTasks execute repo commands in PAT-holding tree; transitive caret deps bumpable with pnpm 1-day age gate; named candidates escalade/yargs-parser/string-width/zod | hardening recommendations: restrict allowedCommands, drop bazelModDeps, pin transitive deps | recorded |

| c5 | R8 preview metadata race | Q1: same metadata pattern in other consumers? (components docs-preview + cli dev-app use the same actions - same race surface, consumer wiring dependent); the inject/extract idiom is unique to previews/* | Q2: artifact-derived unvalidated values -> channelId -> Firebase channel overwrite (content substitution) -> phishing on preview infra; comment number -> bot impersonation on arbitrary issues | leads: consumer wiring state check (operator), Firebase channel semantics | recorded |
| c6 | R8 org-scale cascade (F13) | Q1: angular-cli MCP wrapper = SAME decryptable-credential idiom (boundary info, consumer-attributed, quarantined per scope); no other org instances | Q2: the class is systemic across the org's CI tooling - org-wide credential hygiene review recommended | operator notification of angular-cli team | recorded |
