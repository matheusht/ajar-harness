# D3 FILING PACKAGE — fork guard ineffective + org robot-token budget pressure + forward-condition watch

**Engagement:** angular-cli-2026-08 · **Finding:** D3-branch-manager-fork-guard · **Pin:** `d827ba9005b86b23d05ee7c62c0823367aa245c1` (angular-cli) / `04230133d395dfb032d782b8e63b4fcbbd406aa5` (dev-infra actions)
**Status:** PROMOTED (2026-08-15) · gates G0-G6 CLEAR · **Severity:** Low (CVSS:3.1/AV:N/AC:H/PR:N/UI:N/S:U/C:N/I:N/A:N — control-integrity)
**Prepared:** Wave D records assistant (D-R2), assembled from the adjudicated records. Operator re-authors the humanized draft before submission; no filing by agents.

---

## §1 — The guard defect (confirmed at the pin)

```yaml
# .github/workflows/assistant-to-the-branch-manager.yml:10-21
on:
  push:
  pull_request_target:
    types: [opened, synchronize, reopened, ready_for_review, labeled]
jobs:
  assistant_to_the_branch_manager:
    if: github.event.repository.fork == false   # <-- the defect
```

On `pull_request_target` events, `github.event.repository` is the **base** repository (the repo the workflow lives in — never a fork), so `github.event.repository.fork` is always `false` and the guard is **always true** — fork PRs are never blocked. The correct expression is `github.event.pull_request.head.repo.fork == false`.

**Why this matters beyond the expression:** the job checks out the PR merge commit (attacker-influenced content; `persist-credentials: false` only removes the token from the checkout — it does not stop the checkout) and runs the pinned branch-manager action with `ANGULAR_ROBOT_PRIVATE_KEY`. Today the action is API-only (never reads the checkout), which caps the impact to budget pressure + control-ineffectiveness — but the guard is the *enabling condition* for a future key-exposure primitive (see §5).

**Maintainer precedent (must cite):** angular-cli **#32116** (CLOSED, maintainers) already raised the fork-disable question for THIS workflow and closed it — the filing must cite it: it strengthens "an ineffective control the maintainers considered and left", and it pre-empts a "known/considered" dismissal by leading with the surviving channels (budget pressure + forward condition), not the guard alone.

## §2 — Corrected robot-budget numbers (E2-B3/D3KP, source-counted)

| Job | Trigger | Calls per event (source-counted) | Notes |
|---|---|---|---|
| `labels` | fork-PR synchronize / reopened / ready_for_review | **8-12** | pulls.listCommits/listFiles (paginated), issues.get, listLabelsForRepo, label mutations, token mgmt |
| `issue_labels` | issue opened / reopened | **7-10 + AI-key** | issues.get x2-3, listMilestones (paginated), listLabelsOnIssue, mutations, + one Gemini call per event (cash burn) |
| `assistant` | unlabeled fork PR | 0 | dispatch gated on `action: merge`/`target: *` labels (E12 CORRECTION) |
| `assistant` | `action: merge`-labeled PR | 0-2 | label-gated |
| dispatched evaluation | merge-label-gated | 6-15 + full clone | merge-label-gated |

**Budget:** 5,000 req/hr **PER-INSTALLATION** token budget — shared across the ORG (angular/angular + components + cli all draw on it) → **impact framing = org-wide merge-automation degradation**.

**Scenario math (artifact: payload-proposals/d3-budget-math/):**
- **S1** single attacker PR-churn flood (200 forks x 3 pushes): 6,000 calls/hr → **120% — EXCEEDS the hourly budget**
- **S5** coordinated attacker network (10 accounts x 100 PR events): 10,000 calls/hr → **200% — EXCEEDS**
- **S3** combined churn + issue loop: 3,150 calls/hr → **63% — material share (>=50%)**
- **S2** single-issue reopen loop alone: 300 calls/hr → 6% (low, but compounds with PR churn; unbounded per issue)
- **S4** bot-driven churn: 4.8% (low)
- Conservative rates (30-60 issue-reopen events/hr) yield **4.8-9.6% sustained**; **anti-abuse does NOT cap the rates** (KILL-1 FAILS)
- **Cash-burn sub-claim (survives independently):** one Gemini call per issue event, no rate ceiling beyond anti-abuse — attacker-authored issue bodies drive paid AI inference with the org's key, unbounded per issue reopen cycle

**Exceeding the budget =** the robot token throttles (429) for the window → labels/status-check/merge-evaluation jobs fail intermittently → PRs stall without labels/status; hourly recovery, **no lockout** (NARROWED-SURVIVES; queue-wedge KILLED — the action never merges; asserts disabled by design at lib/main.ts:101-117).

**Honest uncertainty:** the peak-overlap assumption (org near its own ceiling when the attacker presses) and no live org-traffic share measurement (no wire access).

## §3 — Co-discovery + filing timing (HIGH priority)

- **angular/components #33632 + the pending class-fix PR **#33653** (components; the class is being fixed upstream — the angular-cli instance remains unfixed at main, verified E2-D2) (OPEN, public):** "github.event.repository.fork check is ineffective in pull_request_target workflows" — an INDEPENDENT reporter filed the SAME guard-defect class (verified via GitHub search API). The angular-cli-specific instance + the forward condition remain undisclosed.
- **Filing sequence (FILING-SEQUENCE.md row 4):** file D3 NOW, positioned after the top-severity findings (W1 CI-token RCE, M3, E1-C1), **never deferred past the next operator session** — the #33632 + the pending class-fix PR **#33653** (components; the class is being fixed upstream — the angular-cli instance remains unfixed at main, verified E2-D2) reporter is the single most likely entity to file the angular-cli instance, and the foxllb cluster (#33073-#33077) shows an active independent researcher on this surface.
- **Risk:** maintainers fix reactively → the guard sub-claim goes stale (the budget channel + forward condition survive); #32116 shows they consider this workflow.

## §4 — Delta-first draft (humanized, corrected numbers; under 300 words)

```markdown
# D3 — Fork PRs consume the org robot-token budget with no concurrency cap (and the fork guard never fires)

**The one-line ask:** replace `if: github.event.repository.fork == false` with
`if: github.event.pull_request.head.repo.fork == false` on the workflow jobs, and add concurrency
groups to the labels/issue_labels workflows.

**Why it matters, quantified.** On pull_request_target events, github.event.repository is always
the base repo, so the fork guard is always true and never blocks anyone. I verified the math from
the action sources: a fork PR's synchronize/reopen/ready_for_review events drive the labels job at
roughly 8 to 12 API calls each, and a single issue reopened in a loop drives issue_labels at 7 to
10 calls plus an AI call per event, against a 5,000 request per hour installation-token budget
shared across the org. A single coordinated attacker can exceed the hourly budget outright (two
scenarios at 120% and 200%), and even conservative churn holds a material 63% share. That is
availability pressure on the org's own merge pipeline, caused by events any fork PR can generate,
with real money attached (paid AI inference per attacker-authored issue).

**Not claimed:** no merge bypass, no exfiltration, no code execution. The action is API-only; the
robot key stays in process. The concern is a broken security control with a quantified
availability cost, and a latent key-exposure condition if the action ever reads untrusted content
(watch-list documented).

**Co-discovery:** angular/components #33632 + the pending class-fix PR **#33653** (components; the class is being fixed upstream — the angular-cli instance remains unfixed at main, verified E2-D2) (open) reports the same guard-defect class; this
instance should be fixed promptly.
```

## §5 — Forward-condition watch (operationalized: D3-watch-spec.md)

Chain 5 is **armed-but-inactive** (FUTURE-CONDITIONAL). Five activation triggers, verified at the pin clones:

1. **One-line `ref:`/`repository:` override on the EXISTING checkout** (assistant-to-the-branch-manager.yml:18 — the checkout exists with default ref; this is the cheapest accidental introduction). **Precision correction recorded:** the assistant workflow DOES have a checkout (line 18, default ref) — class-1 watch is the one-line override, not a new checkout.
2. Any file-read (readFile/readdir/glob/exec) added to `branch-manager` or `labeling` action libs on a PR-reachable path (today: zero FS ops, grep-verified; keys stay in-process).
3. A new PR-reachable workflow/action in angular-cli's .github that consumes `ANGULAR_ROBOT_PRIVATE_KEY` or `GOOGLE_GENERATIVE_AI_KEY` with a checkout of the PR head.
4. The `update-models` action (has fs/exec today) being wired to a PR-reachable trigger (currently schedule + workflow_dispatch, `permissions: {}`).
5. Removal/misconfiguration of the `persist-credentials: false` + default-ref checkout settings on the existing checkouts.

**If any trigger fires:** the E12 flood becomes a robot-key/Gemini-key exposure primitive on attacker-triggered events — org-wide supply-chain exposure; re-open the engagement (operator decision).

## §6 — Evidence pointers

- `findings/D3-branch-manager-fork-guard/REPORT.md` — defect section, E12 CORRECTION, DEEP-PHASE AMPLIFIER UPDATE (corrected numbers), CHAINSTORM NOVELTY UPDATE (#33632 + the pending class-fix PR **#33653** (components; the class is being fixed upstream — the angular-cli instance remains unfixed at main, verified E2-D2)), caps, remediation.
- `findings/D3-branch-manager-fork-guard/evidence/assistant-to-the-branch-manager.yml` — the workflow at the pin.
- `findings/D3-branch-manager-fork-guard/reviews/` — 2 adjudication reviews (claim_adjudication).
- `payload-proposals/d3-budget-math/` — budget-math.mjs + OUTPUT.txt (scenario table; note: the artifact's per-event table predates the E2-B3 correction — the REPORT §2 numbers above are authoritative).
- `payload-proposals/D3-watch-spec.md` — the operationalized Chain-5 watch.
- `payload-proposals/D3-filing-draft.md` — the pre-correction draft (numbers 7-13/4-6; superseded by §2/§4 here).
- `payload-proposals/FILING-SEQUENCE.md` row 4 + `payload-proposals/FILING-COVER.md` — sequence and cover.
- `cascades.md` rows 11-15 — attribution ledger (dev-infra budget pattern vs angular-cli guard + concurrency).
- Kernel attempts: attempt-d3-001-primary / attempt-d3-002-control / attempt-d3-002-control-ns; hypothesis-d3 closed.

## §7 — Filing mechanics (operator)

1. Re-author the §4 draft in the human report voice (delta-first; keep the #33632 + the pending class-fix PR **#33653** (components; the class is being fixed upstream — the angular-cli instance remains unfixed at main, verified E2-D2) and #32116 citations visible).
2. File as the D3 finding (Low, control-integrity) — NOT as a new report; the budget channel + forward condition are amplifiers of the same root cause (the ineffective guard).
3. Sequence: after W1 CI-token / M3 / E1-C1 (top-severity first), never deferred past the next operator session.
4. Do NOT file the Chain-5 forward condition as a live claim — it is a watch-list + enabling-condition note.

## §8 — Residual risks

- The #33632 + the pending class-fix PR **#33653** (components; the class is being fixed upstream — the angular-cli instance remains unfixed at main, verified E2-D2) reporter may file the angular-cli instance first (duplicate/co-credit risk) — the filing window is the next operator session.
- Maintainers may fix the guard reactively (reactive-fix staleness): the budget channel + forward condition survive; the guard sub-claim becomes historical.
- The peak-overlap assumption and the absence of live org-traffic measurement are the honest uncertainties in the budget math.
- The budget-math artifact's per-event table predates the E2-B3 correction (cosmetic; REPORT numbers authoritative).
- No live CI/runner demonstration (wire-2 is operator-gated; the private-fork demo spec exists at payload-proposals/chain2-wire2-spec.md).
