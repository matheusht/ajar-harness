# DEV-INFRA HANDOFF NOTE — cross-engagement evidence package (angular-cli-2026-08 → angular-dev-infra-2026-08)

- **Prepared:** 2026-08-15 (deep phase E1-R12/L12 lane, angular-cli-2026-08 engagement)
- **Operator action:** decide whether to extend the angular-dev-infra-2026-08 engagement records with the items below; all are **advisory/hardening-grade** — none changes dev-infra's promoted findings (F13, R8, V1)
- **Pointer recommendation:** record these under angular-dev-infra-2026-08 plan.md §11 (operator decision points); the pointer line is a recommendation only — nothing here modifies dev-infra records

## The 4 NEW dev-infra items (mechanism + source refs at pin `04230133d395dfb032d782b8e63b4fcbbd406aa5`)

### N1 — Robot-token budget consumption pattern (unbounded, attacker-sustainable)
- **Mechanism:** angular-cli's assistant-to-the-branch-manager/labels/issue_labels workflows (pull_request_target triggers incl. `labeled`; no concurrency groups anywhere — 0 matches) drive dev-infra actions on every event: branch-manager action ~6-15 API calls + full clone per dispatch; labels job ~7-13 calls per fork-PR event; issue_labels ~4-6 calls + one GOOGLE_GENERATIVE_AI_KEY usage per issue event. Attacker-reachable unbounded streams: fork-PR synchronize/reopened/ready_for_review churn and **single-issue open/reopen cycles**.
- **Source refs (04230133):** `github-actions/branch-manager/lib/main.ts` (evaluation + dispatch gating), `github-actions/labeling/shared/labeling.ts` + `github-actions/utils.ts` (per-event token-mgmt x2 + paginated reads + mutations + revocation), `github-actions/labeling/issue/lib/main.ts` (AI-key usage).
- **Assessment:** advisory-grade — per-event costs vs the documented 5,000 req/hr installation budget imply a material share of the merge-automation budget can be consumed (hourly recovery, no lockout; live org traffic share NOT measured — no wire access). Queue-wedge itself was KILLED (see N2).

### N2 — No-concurrency evaluation semantics (status-reporter-only)
- **Mechanism:** the branch-manager evaluation NEVER merges and NEVER gates: `assertMergeReady`/`assertPassingCi`/`assertCompletedReviews`/`assertMinimumReviews=false` — the action is a status reporter by design (branch-manager/lib/main.ts:101-117). With no concurrency/dedupe in any workflow in the chain, every event runs a full evaluation + clone.
- **Assessment:** advisory-grade (availability/robustness; merge decision is made downstream by dev-infra's own branch-manager workflow with real gates — no bypass). Doubles as the **positive control** that closes dev-infra F4's 'unexplored' family entry (branch-manager auto-merge gating — see §F4).

### N3 — ng-dev lockfile substitution (supply-chain surface, untrusted job)
- **Mechanism:** angular-cli pr.yml (lint job) runs `pnpm admin validate` + ng-dev commands on PR content with the lockfile from the PR — a fork PR can substitute ng-dev dependency versions, executing substituted ng-dev code. Currently runs as an **untrusted job** (no secrets/GITHUB_TOKEN in scope), which is the only boundary.
- **Assessment:** advisory-grade — the boundary rests on GitHub's event-type secret scoping (platform behavior); hardening: add `pnpm install --frozen-lockfile` integrity enforcement at the check step + keep admin validate/templates OUT of any future `pull_request_target` workflow (token-steal risk if added there).

### N4 — googlers-org installation token channel (permission set unknown)
- **Mechanism:** `post_approval_changes` (dev-infra.yml) mints a googlers-org installation token on EVERY attacker-triggerable PR (`getGooglersOrgInstallationToken`, post-approval-changes/lib/main.ts:39-43; app 43341) as a membership oracle. The dev-infra D4 desk established the app REQUESTS a wide set — `administration:write`, `organization_user_blocking:write`, `emails/metadata:read` + `members:read` — so the **installed permission set on the googlers org is the blast radius** and it is out-of-repo evidence.
- **Assessment:** advisory-grade — repo code constrains the token's USE; the token's CAPABILITY depends on a Google-side fact (the granted installation permissions). Operator-verifiable with the dev-infra ws4 procedure (JWT script + decision matrix in payload-proposals/ws4/).

## Cascades row-7 correction note (angular-cli-2026-08 cascades.md)
- The row-7 attribution entry ("issue_labels Gemini cost-abuse … already held there (Gemini cost-abuse P1)") contained an **unsupported claim**: no P1 under that wording exists in the dev-infra visible records. Corrected E1-R6/L12 to advisory-grade. **Operator to eyeball dev-infra plan.md §11 before relying on any Gemini cost-abuse wording.**

## F4 family disposition suggestion (dev-infra)
- dev-infra's family table lists **F4 (branch-manager auto-merge gating bypass)** as 'unexplored'. The L3 lane (E1-R2) evaluation-semantics evidence **closes it as a positive control**: the pinned action cannot merge (asserts disabled by design, lib/main.ts:101-117) and merge decisions require approvals/labels/CI downstream — no bypass demonstrated. Suggest recording F4 = positive-control-closed with the L3 evidence.

## Boundary statement
- Nothing in this note modifies any angular-dev-infra-2026-08 record. It is a payload for the operator's decision; the operator (or a dev-infra-engagement session) applies any extensions.

