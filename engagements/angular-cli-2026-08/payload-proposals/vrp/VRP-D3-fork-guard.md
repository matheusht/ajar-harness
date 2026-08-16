Title: Ineffective fork guard lets fork PRs reach secret-bearing CI jobs and consumes the org robot-token budget at an unbounded rate

**Report as (Google OSS VRP vulnerability type):** Security control ineffectiveness in CI/CD (fork-guard bypass + org token-budget exhaustion) — form category: **Other** (security misconfiguration / CI control bypass; fallback: Insufficient authorization).

Product: angular-cli (workflow: .github/workflows/assistant-to-the-branch-manager.yml)
Affected: pinned d827ba9005b86b23d05ee7c62c0823367aa245c1 (2026-08-13); verified still present at main on 2026-08-15
Severity: Low, CVSS:3.1/AV:N/AC:H/PR:N/UI:N/S:U/C:N/I:N/A:N (control-integrity)

Summary

The job that runs the branch-manager action with ANGULAR_ROBOT_PRIVATE_KEY is gated with `if: github.event.repository.fork == false`. On pull_request_target events, `github.event.repository` is always the base repository, never a fork, so that expression is always true. The guard does nothing. Every fork PR fires the job, and the ungated sibling jobs (labels, issue_labels) consume the org robot-token budget without any label gate at all.

I checked this against the documented GitHub Actions event semantics and the pinned workflow, and an independent reporter has since filed the same guard class (angular/components #33632, open).

Steps to reproduce

1. Open the workflow:
   sed -n '10,21p' .github/workflows/assistant-to-the-branch-manager.yml
   The guard reads `if: github.event.repository.fork == false` (line 21).

2. Open a fork PR (opened, synchronize, or reopen it). The job runs. The guard was intended to skip forks, and it never skips them, because on PR events `github.event.repository` is the base repo and `.fork` is false by construction. The correct expression is `github.event.pull_request.head.repo.fork == false`.

3. For the budget math, the per-event cost was counted from the pinned action source:
   - issue_labels: 7-10 calls plus one AI (Gemini) call per event
   - labels: 8-12 calls per fork-PR event
   - assistant job: 0 (unlabeled) or 2
   - dispatched evaluation: 6-15 plus a full clone

   Against the documented 5,000 req/hr installation-token budget, which is shared org-wide across angular/angular, angular/components and angular/cli, a single coordinated attacker exceeds it (scenario S1 reaches 120%, S5 200% in the attached budget model). A lone issue reopen loop stays low (~6%) but compounds with PR churn, and GitHub's own anti-abuse does not cap these rates.

Impact

What I proved: the guard is provably ineffective as written, fork PRs reach a secret-bearing job they should not, and an attacker can consume a material share of the org merge-automation token budget, causing intermittent degradation with hourly recovery. No lockout.

Where I stopped: the action itself is API-only. It reads event payloads and calls the GitHub API; it never reads workspace files, and the private key stays in-process. So there is no exfiltration and no merge bypass today. If the action ever gains a step that reads untrusted checkout content, the same flood becomes a key-exfiltration primitive, but that is a forward condition, not a current impact.

Why it matters anyway: this is a security control that does not control. The maintainers previously closed an issue raising the fork question for this exact workflow (#32116), which makes the ineffective guard worth filing as a control-integrity defect rather than a one-off typo.

Remediation

1. `if: github.event.pull_request.head.repo.fork == false`, or scope the secret-bearing step to `push` only.
2. Add the same head-repo guard to the labels and post_approval_changes jobs, which have no guard at all.
3. Add concurrency groups to all three workflows. That alone kills the budget amplification.

References

- angular/components #33632 (open, independent co-discovery of the guard class)
- angular/components #33653 (pending class-fix; the angular-cli instance is not covered)
- angular/cli #32116 (closed; maintainers previously considered the fork question for this workflow)
- dev-infra #961 (robot-token rate limits)
- Budget model: payload-proposals/d3-budget-math/budget-math.mjs (S1 120%, S5 200%)
