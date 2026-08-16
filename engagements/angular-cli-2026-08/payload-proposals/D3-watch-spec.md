# D3 WATCH SPEC — Chain 5 activation watch (operationalized C5D)

**Purpose:** detect the first change that turns D3's proven-ineffective fork guard into a real robot-key exposure primitive. Current state verified at the local pin clones (`dev-infra` 04230133, `angular-cli` d827ba9005): the chain is **armed-but-inactive**.

## §0 Verified caps (baseline for the watch — re-verified this lane)

| Cap | Evidence (local pin clone) |
|---|---|
| No PR-head content lands on a robot-key runner | assistant-to-the-branch-manager.yml:18 checkout exists but **default ref** (`persist-credentials: false`, no `ref:`/`repository:` override) — the PR head never lands on disk; dev-infra.yml's 3 checkouts (lines 19/28/37) also default ref |
| Action libs are API-only on the PR path | `github-actions/{branch-manager,labeling}/lib/*.ts` + `.github/local-actions/branch-manager/lib/main.ts`: zero `readFile/readdir/glob/execSync/spawn` (grep-verified). The one local action WITH fs/exec (`update-models/lib/main.ts`) is schedule-only + `workflow_dispatch`, `permissions: {}` — NOT PR-reachable, no secrets |
| Dispatch inputs typed + GitHub-constructed | branch-manager.yml `workflow_dispatch.inputs` = repo/owner/pr(+sha); `pr` re-validated as Number |
| Clone is base-repo-only, array-form | `.github/local-actions/branch-manager/lib/tmp.ts:14-19` — `spawnSync('git', ['clone','--depth=1', 'https://github.com/${repo.owner}/${repo.repo}.git', ...])`, dispatch-supplied base values |
| Guard still ineffective (D3, unfixed) | assistant-to-the-branch-manager.yml:24 `if: github.event.repository.fork == false` verbatim; dev-infra.yml jobs have no guard |

**Precision correction to C5D row 1 (recorded):** the assistant workflow DOES have a checkout (line 18, default ref). The class-1 watch is therefore a **one-line `ref:`/`repository:` override on the EXISTING checkout** — even cheaper for the maintainers to introduce by accident than adding a new checkout.

## §1 The 8 change classes — exact operator commands

Run from the operator's own `angular/dev-infra` and `angular/angular-cli` checkouts (no wire from the lab; the local pin clones validate the shapes).

**Class 1 — PR-head checkout on a secret-bearing job** (activation: `ref:`/`repository:` override appears)
```bash
git log -p 04230133d395dfb032d782b8e63b4fcbbd406aa5..@{u} -- .github/workflows/ | grep -nE 'ref: \${{|repository: \${{|pull_request\.head\.(sha|repo)' -B2 -A2
```
Trigger: any `ref: ${{ github.event.pull_request.head.sha }}` or `repository: ${{ github.event.pull_request.head.repo.full_name }}` inside a checkout block in `assistant-to-the-branch-manager.yml` or `dev-infra.yml`.

**Class 2 — file-read of the untrusted checkout in an action lib**
```bash
git log -p 04230133..@{u} -- github-actions/ .github/local-actions/ | grep -nE 'readFile\(|readdir\(|glob\(|loadConfig\(|fs\.' 
```
Trigger: any of the fs-verbs inside `{branch-manager,labeling,post-approval-changes}/lib/*.ts` or `.github/local-actions/branch-manager/lib/`.

**Class 3 — templating PR fields into shell/URLs**
```bash
git log -p 04230133..@{u} -- github-actions/ .github/local-actions/ | grep -nE 'execSync\(|spawn\(|`https?://' -B2 -A2
```
Trigger: a shell-form spawn or URL built from `payload.pull_request.*` (today's only spawn, `tmp.ts:14`, is array-form with base-repo values).

**Class 4 — dispatch inputs widened or fed from fork content**
```bash
git diff 04230133..@{u} -- .github/workflows/branch-manager.yml github-actions/branch-manager/lib/main.ts | grep -nE 'inputs:|pull_request.head|head\.repo'
```
Trigger: new inputs beyond repo/owner/pr/sha, or input values sourced from `payload.pull_request.head.*`.

**Class 5 — clone target switched to fork head**
```bash
git diff 04230133..@{u} -- .github/local-actions/branch-manager/lib/tmp.ts
```
Trigger: `clone_url`, `head.repo.full_name`, or `fork` appearing in the clone URL construction.

**Class 6 — config read re-pointed into the PR checkout**
```bash
git diff 04230133..@{u} -- .github/local-actions/branch-manager/lib/main.ts | grep -nE 'getConfig\(|process\.cwd\(|--cwd|config'
```
Trigger: `getConfig` shifting from the dev-infra checkout to a PR-path.

**Class 7 — new pull_request_target job combining checkout-override + secrets** (both repos)
```bash
git diff 04230133..@{u} -- .github/workflows/ && git -C angular-cli diff d827ba9005..@{u} -- .github/workflows/
```
Trigger: any new job with `pull_request_target` + `actions/checkout` + `ref:`/`repository:` + `${{ secrets.* }}`.

**Class 8 — fork-guard removed/changed on secret-bearing jobs**
```bash
git log -p 04230133..@{u} --all --grep='fork' .github/workflows/ && git -C angular-cli log -p d827ba9005..@{u} -- .github/workflows/assistant-to-the-branch-manager.yml
```
Trigger: the `if: github.event.repository.fork` expression (assistant-to-the-branch-manager.yml:24) changing or disappearing.

## §2 Cadence

1. **Monthly pin-diff** (or at each release cut) — all 8 commands; the first 30 lines of any workflow diff surface classes 1/3/4/6.
2. **On any workflow/action PR** in either repo (the maintainers react fast to fork-origin issues — #3746/#3761/#32116 precedent; review-hook: `zizmor` output + the manual one-line scan).
3. **Co-discovery sweep** (while #33632 is open): weekly `gh search issues "repository.fork" "pull_request_target" --repo angular/components --repo angular/angular-cli --repo angular/angular --limit 20` — watch for the reporter or maintainers filing the angular-cli instance.

## §3 Threshold → action

| Observation | Verdict | Action |
|---|---|---|
| Watch grep hits in commit history, change NOT yet merged | **watch-only** | note the PR/commit; re-run after merge |
| Merged change matches classes 1-6 with the robot key on the job | **CHAIN ACTIVATED** | full escalation path (§4) |
| Merged change is a guard fix (class 8) | **D3 partially remediated** | re-verify the guard on all 3 workflows + concurrency; update D3 status |
| New public report of the guard defect in angular-cli | **co-discovery race** | filing urgency escalates to immediate (duplicate-preemption) |
| No hits | **watch-clear** | log the date + snapshot hash |

## §4 Escalation path (if CHAIN ACTIVATED)

1. **Verify** — re-pin the new HEAD, reproduce the change locally (grep the actual file, not the diff), confirm the robot key (`ANGULAR_ROBOT_PRIVATE_KEY`) is wired into the job that now processes fork content, confirm the token is NOT excluded from the step env.
2. **Measure exposure** — the exfil rate model from C5C applies: one file-read+embed per event → API-response embedding (status description) or artifact upload; the E12 flood multiplies it.
3. **Update records** — D3 REPORT chain section: chain-5 status armed-but-inactive → ACTIVE with the activating commit; cascades.md row 14 watch → confirmed; kernel observation; rounds.md E2-R5 row amendment.
4. **Operator alert** — one-paragraph summary (change, exposure, evidence, filing reframe): D3 reframes from control-ineffectiveness to a **key-exfiltration primitive on attacker-triggered events**; severity reevaluation (Low → High, org-wide).
5. **Filing decision** — operator chooses: file D3 immediately with the new evidence, or authorize the wire-2 private-fork demo to prove the primitive end-to-end (fresh operator confirmation required at the moment of the act).

## §5 False-positive calibration (verified this lane)

- `pr.yml:33` `base.sha/head.sha` in `pnpm ng-dev commit-message validate-range` = **benign** (command args, not checkout refs) — class-1 grep must scope to `uses: actions/checkout` blocks.
- `update-models/lib/main.ts` fs/exec = **benign** (schedule-only, `permissions: {}`, no secrets) — class-2 grep must scope to the three PR-path actions + the local branch-manager action.
- Checkout lines without `ref:`/`repository:` overrides = **benign** (default ref = base repo).
