# D3 — assistant-to-the-branch-manager fork guard is ineffective (fork PRs reach the robot-key job)

- **Engagement:** angular-cli-2026-08 · **Pinned commit:** `d827ba9005b86b23d05ee7c62c0823367aa245c1`
- **Status:** PROMOTED (2026-08-15, gates G0-G6 clear) — cascading amplifier folded (E12 corrected); deep-phase robot-budget channel + novelty section.
- **Origin:** deepsec cross-scan (slug `github-workflow-security-ebb02c89c2`), adjudicated by the orchestrator against GitHub event semantics + the pinned action source.
- **Surface:** `.github/workflows/assistant-to-the-branch-manager.yml:10,16,18,23`

- **AMPLIFIED in the cascading phase (E0-R3/E12 + KP-E12 SURVIVES-narrowed):** the impact is
  NOT cosmetic-only. Three attacker-controlled event types per fork PR (`synchronize` per push, `reopened` per close/reopen, `ready_for_review` per draft toggle — workflow triggers :7-9) reach the assistant job, but — E1-R2/L3 CORRECTED — the action DISPATCH is gated on the `action: merge`/`target: *` labels: UNLABELED fork PRs consume ZERO API calls on the assistant job. The unbounded budget-consumption channel is the ungated `labels` + `post_approval_changes`/`issue_labels` jobs (see the DEEP-PHASE AMPLIFIER UPDATE). Kill-pair narrowing: the spam sub-claim is
  killed as primary (a fork attacker already induces fork-PR CI — GitHub's cost); the SURVIVING
  delta is the **robot-token rate-limit pressure** on the org's own merge automation (5,000 req/hr
  installation-token budget; hourly recovery — intermittent availability degradation, not lockout).
  Caps hold: no merge bypass, no exfiltration, no code exec.
## The defect (confirmed)

```yaml
on:
  push:
  pull_request_target:
    types: [opened, synchronize, reopened, ready_for_review, labeled]
jobs:
  assistant_to_the_branch_manager:
    if: github.event.repository.fork == false
```

On `pull_request_target` events, `github.event.repository` is the **base** repository (the repo the workflow lives in — never a fork), so `github.event.repository.fork` is always `false` and the guard is **always true** — fork PRs are never blocked. The correct expression is `github.event.pull_request.head.repo.fork == false`. This is a documented GitHub Actions semantics gotcha; the guard is provably ineffective as written.

Consequence: every fork PR (opened/synchronize/reopened/ready_for_review/labeled) triggers the job, which checks out the PR merge commit (attacker-influenced content, `persist-credentials: false` only removes the token) and runs the pinned branch-manager action with `ANGULAR_ROBOT_PRIVATE_KEY`.

## Why the impact is capped (adjudication)

- The pinned action (`angular/dev-infra/github-actions/branch-manager@04230133…`) is **API-only**: it reads `context.payload` (labels, head sha, PR number) and GitHub API, and dispatches dev-infra's own branch-manager workflow. It **never reads or executes workspace files** — the untrusted checkout is inert for the action's behavior. The workflow's inline zizmor justification ("does not checkout untrusted code") is wrong about the checkout but the *effect* (no execution of untrusted content by the secret-bearing step) holds.
- What a fork attacker CAN do: drive the ungated labels/post_approval_changes/issue_labels jobs (robot-token consumption without any label gate; ~7-13 API calls per fork-PR event, 7-10 + AI-key per issue event (source-counted — the corrected block), unbounded via PR churn and single-issue reopen cycles) plus, for `action: merge`-labeled PRs only, assistant-job dispatch — see the E12 CORRECTION block for the corrected, quantified channel (the unlabeled fork-PR dispatch over-claim in the earlier amplifier wording is superseded). The **merge decision** is made downstream in dev-infra's branch-manager workflow (attribution: dev-infra internals, audited in angular-dev-infra-2026-08; merge gates require approvals/labels/CI — no bypass demonstrated).
- No RCE, no unauthorized merge, no secret exfiltration demonstrated. **Caps (E5-verified):** the
dispatch inputs (`repo/owner/pr/sha`) are value-bounded — GitHub-constructed base repo, the
attacker's own PR number (integer), and a 40-hex head sha — attacker-controlled content cannot
travel beyond a PR number into the downstream merge evaluation.

## Staleness

Present at the pin; the guard line untouched by security fixes (git log). Not stale.

## Severity / category

- **Low** (ineffective security control; fork PRs reach secret-bearing jobs they should not; demonstrated impact = unbounded event-stream amplification + intermittent robot-token rate-limit pressure on the org's merge automation — the E12/KP-E12-narrowed delta; no merge bypass, no exfiltration, no code exec). CVSS:3.1/AV:N/AC:H/PR:N/UI:N/S:U/C:N/I:N/A:N (control-integrity). Category: Product Vulnerability (CI wiring) — defense-in-depth/control-ineffectiveness. Operator re-review.

## CHAINSTORM NOVELTY UPDATE (E2-R5/C5G): INDEPENDENT CO-DISCOVERY — filing urgency

- **angular/components #33653 (PENDING CLASS-FIX, 2026-08-15 refresh):** a components PR now exists addressing the same guard-defect class — the class is being fixed upstream; the angular-cli instance (this finding) remains unfixed at main (verified via the GitHub API). Filing urgency unchanged: file the angular-cli instance before the components fix lands and the class-fix sweeps.
- **angular/components #33632 (OPEN, public):** "github.event.repository.fork check is ineffective in pull_request_target workflows" — an INDEPENDENT reporter has publicly filed the SAME guard-defect class (verified via GitHub search API). The angular-cli-specific defect and the forward chain condition remain undisclosed, but the class is now public — **filing timing matters: the operator should file D3 promptly (co-credit / duplicate-preemption risk), and the filing must cite #33632.**
- Chain 5 (forward) verdict: FUTURE-CONDITIONAL — the key-exfiltration precondition (any file-read in the action) is verified ABSENT at the pin (C5A: zero FS ops on untrusted content; keys stay in-process); 5-trigger watch-list documented; no live exposure today.

## DEEP-PHASE NOVELTY (E1-R1, L9): NO public disclosure of the guard mechanism

- No GitHub issue/PR/advisory discloses the `github.event.repository.fork` always-false-on-PR-events mechanism IN ANGULAR-CLI at the time of writing — superseded for the CLASS by angular/components **#33632** (OPEN; the CHAINSTORM NOVELTY UPDATE above). Adjacent public context: angular-cli **#32116** (CLOSED, maintainers) already raised the fork-disable question for THIS workflow and closed it — the filing must cite it (two-sided: it strengthens "ineffective control the maintainers considered and left", and it pre-empts a known/considered dismissal by leading with the surviving channels: budget pressure + forward condition, not the guard alone); dev-infra issue **#961** documents robot-token rate limits (public support for the E12 rate-limit-pressure amplifier); dev-infra PR **#3746**/#3761 are adjacent fork-origin hardening (maintainers react fast to fork-origin issues — relevant to filing timing); a dev-infra PoC PR **#3827** discusses a DIFFERENT class (shared actions-cache key poisoning) — not related to D3, disclosed for operator context only.


## DEEP-PHASE AMPLIFIER UPDATE (E1-R2/L3, verified at pin): E12 correction + quantified robot-budget channel

- **E12 CORRECTION:** the "dispatch per synchronize/reopened/ready_for_review" sub-claim applies ONLY to PRs carrying the `action: merge` label (branch-manager action gates dispatch on action:merge/target labels) — unlabeled fork PRs consume ZERO API calls on the assistant job. The original E12 wording over-stated the dispatch channel.
- **STRONGER channel (replaces it):** the `labels` and `issue_labels` jobs in the same workflow consume robot-token budget WITHOUT any label gate — attacker-reachable unbounded streams are fork-PR synchronize/reopened/ready_for_review (labels job ~7-13 API calls per event) and **single-issue open/reopen cycles (issue_labels 7-10 calls + AI-key usage per event (source-counted), unbounded from one issue)**. The org-owner check does not gate fork PRs (base repo owner = angular).
- **Queue-wedge KILLED:** the branch-manager evaluation never merges and never gates (assertMergeReady/assertPassingCi/assertCompletedReviews/assertMinimumReviews=false at lib/main.ts:101-117 — status reporter only). No merge-queue corruption demonstrated. `git branch -r` at the pin: only main + numeric branches → `target: feature` auto-labeling never fires → the assistant dispatch chain is not auto-reachable.
- **Robot-token budget NARROWED-SURVIVES (E2-B3/D3KP corrected numbers):** per-event costs — issue_labels **7-10 + AI-key** (source-counted: issues.get x2-3, listMilestones paginated, listLabelsOnIssue, label mutations, token mgmt; L3 4-6 undercounted), labels **8-12** (pulls.listCommits/listFiles paginated, issues.get, listLabelsForRepo, mutations), assistant 0/2, dispatched evaluation 6-15 + full clone — vs the documented 5,000 req/hr **PER-INSTALLATION budget (shared across the org — angular/angular + components + cli; impact framing = org-wide merge-automation degradation)**. Scenario math (E2-B3/D3POC artifact, payload-proposals/d3-budget-math/): a single coordinated attacker EXCEEDS the budget (S1 120%, S5 200%); a single-issue reopen loop alone stays low (S2 6%) but compounds with PR churn; conservative rates (30-60 issue-reopen events/hr) yield 4.8-9.6% sustained; anti-abuse does NOT cap the rates. The cash-burn sub-claim (one Gemini call per issue event, no rate ceiling beyond anti-abuse) survives independently of the token-budget math. Peak-overlap assumption (org near its own ceiling when the attacker presses) is the honest uncertainty; live org traffic share not measured (no wire access).
- **Attribution (cascades.md rows added):** budget-consumption pattern + no-concurrency evaluation semantics = dev-infra; trigger sets + missing concurrency groups + the fork-guard expression = angular-cli.
- **Remediation extension:** add concurrency groups to all three workflows (assistant/labels/issue_labels) — this kills the amplification without touching the action.

- **Verified unfixed at main (2026-08-15, GitHub API, DR3-04/E2-D2):** the guard expression `if: github.event.repository.fork == false` remains verbatim in assistant-to-the-branch-manager.yml:21 at main; the pending class-fix is components **#33653** (not yet in angular-cli). Not stale; the filing window is open (co-discovery #33632/#33653).

## Remediation

1. `if: github.event.pull_request.head.repo.fork == false` (or scope secret-bearing steps to `push` only).
2. The dev-infra.yml labels/post_approval_changes jobs have no guard at all — same fork-reachability (the actions there are also API-only; add the same head-repo guard for defense-in-depth).
3. Add concurrency groups to all three workflows (assistant/labels/issue_labels) — kills the budget amplification without touching the action (E1-R2/L3 + E12 correction).
