# WS4 — Googlers-org Permission Check Procedure
### Angular Robot GitHub App (id 43341) — installation on the `googlers` org

- **Engagement:** `angular-dev-infra-2026-08` (authorized white-box, Google OSS VRP; target `angular/dev-infra`, pinned `04230133d395dfb032d782b8e63b4fcbbd406aa5`)
- **Audience:** OPERATOR (holds the app private key; no agent has it)
- **Workstream context:** lane D4 left one Google-side unknown open: *"Installed permission set on `googlers` = the ONE Google-side unknown"* (rounds.md, D4). Lane D3 (update-models verbatim rewrite injection, TS breakout + YAML injection proven) defines the attack chain that would *use* whatever this installation grants. This procedure settles the unknown; the decision matrix (§6) maps each possible permission to its attacker-adjacent risk.
- **Constraint honored:** this document contains **no secrets**. The JWT script takes the key path as an argument; nothing is stored. Run on the operator's local machine, not on any shared runner.
- **Date prepared:** 2026-08-14 (facts verified against the pinned clone + public GitHub API on this date)

---

## 1. Why this check exists (30-second summary)

In-repo, statically provable (agent-side, already done):

| # | Fact | Where |
|---|---|---|
| 1 | App id `43341` = "Angular Robot" (`ANGULAR_ROBOT`), private key input `angular-robot-key` | `github-actions/utils.ts:11` |
| 2 | On **every `pull_request_target` event** (opened/synchronize/reopened) in dev-infra — and in the three consuming OT0 repos that run the same action — the `post-approval-changes` job mints a **`googlers` org installation token** for app 43341 (`getAuthTokenFor(ANGULAR_ROBOT, {org: 'googlers'})` → `apps.getOrgInstallation` → `createInstallationAccessToken`) | `.github/workflows/dev-infra.yml`; `github-actions/post-approval-changes/lib/main.ts:16,37-43`; `github-actions/utils.ts:37-60` |
| 3 | The minted token's only in-code use is a membership oracle (`orgs.checkMembershipForUser({org: 'googlers', username})`); it is revoked in `finally`; error paths redact the token (verified empirically, lane D4) | `post-approval-changes/lib/main.ts:26-27,153` |
| 4 | The **granted** permission set on the `googlers` installation is **not visible from any repo tree** — it lives on the GitHub side, decided by org admins at install time | — |
| 5 | Public API: app 43341 **requests** `members:read`, `administration:write`, `contents:read`, `actions/checks/statuses/workflows/pull_requests/issues:write`, `organization_user_blocking:write`, `emails/metadata:read` — and does **not** request `members:write`, `contents:write`, or `organization_administration` | `GET /apps/angular-robot` (verified 2026-08-14) |

**Why it matters:** the D3 chain (update-models rewrites network-parsed strings verbatim into committed TS/YAML; TS literal breakout executed code — PWNED.txt PoC, `node --check` PASS; YAML duplicate-key injection proven; no test coverage) is capped only by source control of the Google-authored deprecations page. Once injected code lands in `main` (bot PR, `action: merge` label, human merge), the **next** PR-triggered run checks out that base and executes it with `ANGULAR_ROBOT_PRIVATE_KEY` in scope — and the `googlers` org token is minted fresh in that same job. **The granted permission set on `googlers` is therefore the blast radius of the D3 chain** (and of any future RCE/key theft in the PR pipeline).

---

## 2. Prerequisites

- Node.js ≥ 18 (script uses only `node:crypto` / `node:fs` — zero dependencies). `jq` optional but recommended.
- The app private key PEM (operator-held, outside agent access). GitHub issues both PKCS#1 (`BEGIN RSA PRIVATE KEY`) and PKCS#8 (`BEGIN PRIVATE KEY`) PEMs; `node:crypto.sign` accepts either.
- Network access to `api.github.com` (HTTPS).
- Time budget: ~5 minutes. Three GETs; nothing is written; the only credential minted is the short-lived JWT (and, optionally in §4.4, a revocable installation token).

---

## 3. Step 1 — Mint the app JWT (RS256, `iss` = 43341, 10-minute expiry)

Save the script below as `mint-app-jwt.mjs` and run:

```sh
node mint-app-jwt.mjs /path/to/angular-robot-private-key.pem   # prints a JWT to stdout
JWT=$(node mint-app-jwt.mjs /path/to/angular-robot-private-key.pem)
echo "$JWT" | cut -d. -f2 | base64 -d   # sanity: {"iat":...,"exp":...,"iss":43341}
```

**Script source (ready to run, zero deps):**

```js
#!/usr/bin/env node
/**
 * mint-app-jwt.mjs — mint a GitHub App JWT (RS256, iss = app id, 10-min expiry).
 *
 * Usage:  node mint-app-jwt.mjs <path-to-app-private-key.pem>
 *
 * The private key is the GitHub-generated PEM for the Angular Robot GitHub App
 * (app id 43341). The operator holds it; it must never be committed or shared.
 * Output: a single JWT on stdout, valid for 10 minutes (GitHub rejects exp > iat + 600s).
 */
import {readFileSync} from 'node:fs';
import {sign} from 'node:crypto';

const APP_ID = 43341; // Angular Robot GitHub App (github-actions/utils.ts:11)
const keyPath = process.argv[2];
if (!keyPath) {
  console.error('usage: node mint-app-jwt.mjs <private-key.pem>');
  process.exit(1);
}

const privateKey = readFileSync(keyPath, 'utf8'); // PKCS#1 or PKCS#8 PEM both work
const now = Math.floor(Date.now() / 1000);

const header = {alg: 'RS256', typ: 'JWT'};
const payload = {iat: now, exp: now + 600, iss: APP_ID}; // exp <= iat + 600s is enforced

const b64 = (obj) => Buffer.from(JSON.stringify(obj)).toString('base64url');
const signingInput = `${b64(header)}.${b64(payload)}`;
const signature = sign('sha256', Buffer.from(signingInput), privateKey);

process.stdout.write(`${signingInput}.${signature.toString('base64url')}\n`);
```

*Validation performed on this script (throwaway key, 2026-08-14): header `{"alg":"RS256","typ":"JWT"}`, payload `{iat, exp=iat+600, iss=43341}`, RSA signature verifies against the matching public key, TTL exactly 600 s.*

**First, prove the JWT is accepted by GitHub** (optional but cheap):

```sh
curl -sS -H "Authorization: Bearer $JWT" -H "Accept: application/vnd.github+json" \
  https://api.github.com/app | jq '{id, slug, name}'
# Expected: {"id":43341,"slug":"angular-robot","name":"Angular Robot"}
# A 401 here means the key/JWT is wrong — do not proceed.
```

> **JWT hygiene:** the JWT is a valid credential for 10 minutes. Do not echo it into shared logs; export it only in the operator's shell. GitHub rejects `exp` > `iat + 600s`, so the 600-second window is a hard limit, not a suggestion.

---

## 4. Step 2 — The three API calls (all JWT-authenticated, read-only)

All three use the same pattern: `Authorization: Bearer $JWT`. None of them mints an installation token (that is §4.4, optional).

### 4.1 `GET /app/installations` — list every org/repo the app is installed on

```sh
curl -sS -H "Authorization: Bearer $JWT" -H "Accept: application/vnd.github+json" \
  "https://api.github.com/app/installations?per_page=100" | jq \
  '[.[] | {installation_id: .id, account: .account.login, type: .account.type, target_type, repository_selection, permissions}]'
```

What you are looking for: a row with `account == "googlers"` and `target_type == "Organization"`. Record its `installation_id` and `permissions`. If the app has many installations the array is paginated (`per_page=100`; follow `Link` headers if truncated).

### 4.2 `GET /orgs/googlers/installation` — the org installation record by name

```sh
curl -sS -H "Authorization: Bearer $JWT" -H "Accept: application/vnd.github+json" \
  https://api.github.com/orgs/googlers/installation | jq \
  '{installation_id: .id, account: .account.login, permissions, repository_selection, suspended_at, repositories_url}'
```

This is the authoritative record for the installation the PR pipeline mints against (`apps.getOrgInstallation({org: 'googlers'})` resolves to exactly this `id`).

- **HTTP 200** — app installed on `googlers`; `permissions` is the **granted** set (what org admins configured), `repository_selection` is `"all"` or `"selected"`, `suspended_at` non-null means the install is suspended (the mint would fail → see §7, fail-open fold-in).
- **HTTP 404** — the app is *not* installed on `googlers`. GitHub returns 404 for both "not installed" and bad auth, so confirm with §4.1 that your JWT works and no `googlers` row exists. Consequence: the mint on every PR fails, `getGooglersOrgInstallationToken` returns `null`, and the membership oracle falls back to the repo client (fail-open degradation, already folded into F3). The permission question is then moot; the org-side remediation is removing the minting path.

### 4.3 `GET /app/installations/{installation_id}` — same record, by id (cross-check)

```sh
curl -sS -H "Authorization: Bearer $JWT" -H "Accept: application/vnd.github+json" \
  https://api.github.com/app/installations/<INSTALLATION_ID_FROM_4.2> | jq \
  '{installation_id: .id, account: .account.login, permissions, repository_selection, suspended_at}'
```

Must match §4.2 exactly (same `id`, same `permissions`, same `account.login == "googlers"`). Mismatch = stale/duplicate installation — record it.

### 4.4 Optional — enumerate the repos covered (only if `repository_selection == "selected"`)

The granted set is only meaningful together with repo scope: does `administration:write`/`contents:read` reach *all* googlers repos or just `.github`? `repositories_url` on the installation record requires an installation token to follow. **This step mints a live 1-hour credential — do it only if §4.2 shows `"selected"` and the operator needs the repo list, and revoke immediately after.**

```sh
# 1) Mint a 1-hour installation token (this is a real credential — revoke after).
TOKEN=$(curl -sS -X POST \
  -H "Authorization: Bearer $JWT" -H "Accept: application/vnd.github+json" \
  https://api.github.com/app/installations/<INSTALLATION_ID>/access_tokens \
  | jq -r .token)

# 2) List the repos this installation can touch.
curl -sS -H "Authorization: Bearer $TOKEN" -H "Accept: application/vnd.github+json" \
  https://api.github.com/installation/repositories | jq '[.repositories[].full_name]'

# 3) Revoke — do this in the same terminal session, immediately.
curl -sS -X DELETE -H "Authorization: Bearer $TOKEN" \
  -H "Accept: application/vnd.github+json" https://api.github.com/installation/token
unset TOKEN
```

Note in the record which repos are covered. `googlers/.github` is the repo the code comment names as the intended access target ("Use the `.github` repo from googlers to get an installation that has access to the googlers user membership", `post-approval-changes/lib/main.ts:37`).

---

## 5. Baseline — the app's REQUESTED permissions (public, no auth)

```sh
curl -sS https://api.github.com/apps/angular-robot | jq '.permissions'
```

Verified 2026-08-14 (id 43341, slug `angular-robot`):

```json
{
  "actions": "write", "administration": "write", "checks": "write",
  "contents": "read", "emails": "read", "issues": "write",
  "members": "read", "metadata": "read", "organization_user_blocking": "write",
  "pull_requests": "write", "statuses": "write", "workflows": "write"
}
```

**Key point for the check:** GitHub org installations grant the app's *requested* set (the install UI does not let org admins trim individual permissions — they choose repo scope, not per-permission toggles). So the **expected** outcome of §4.2/§4.3 is `permissions` **identical** to the list above, with `repository_selection` scoping the repo-level permissions (`administration:write`, `contents:read`, `actions/checks/statuses/workflows:write`, …).

**Any permission in the granted set that is NOT in the requested set** (`members:write`, `contents:write`, `organization_administration`, or anything else) means the org explicitly granted extra access — that is the critical-flag condition in the matrix below.

---

## 6. Decision matrix — granted permission → attacker-adjacent risk

**Attack model (same for every row):** an attacker who can execute code in a PR-triggered dev-infra pipeline job — D3 post-merge injection (update-models bot commit → `action: merge` → next `pull_request_target` run executes the poisoned base with `ANGULAR_ROBOT_PRIVATE_KEY` in scope), or any future RCE/key theft — can read the freshly minted `googlers` org installation token from that job's environment (it is minted in the same job on every PR), or mint their own via the app key, and then act as app 43341 on `googlers` for the token's 1-hour life. Row = what that buys, per granted permission.

| Permission (granted) | GitHub semantic | Requested by app? | Attacker-adjacent risk (mint-on-every-PR) | Severity if granted |
|---|---|---|---|---|
| `members: read` | View org members & team structure | **Yes** (expected granted) | Information only. Marginal: googlers membership is already publicly enumerable (2,481 members, lane D4). The oracle data this token already reads leaks nothing new. | **Low** — expected, acceptable |
| `members: write` | Add/remove org members, change member roles | **No** | Token theft → attacker adds a controlled account to the `googlers` org. **Feedback loop:** the post-approval-changes oracle (`checkMembershipForUser`) then treats attacker PRs as Googler-authored, silently defeating the stale-approval control the token is minted to enforce. Org membership is also a trust signal beyond GitHub. | **Critical** — flag immediately |
| `administration: read` (repo-level) | View repo settings / protected-branch config on covered repos | **No** (app requests write, which implies read) | Recon on googlers repo config (branch protection, required checks, deploy keys) informs further attacks; no mutation. | Low–Med |
| `administration: write` (repo-level) | Full repo admin on covered repos: push to protected branches, change settings, manage collaborators | **Yes** (expected granted — **the important row**) | Token theft → admin takeover of every covered googlers repo. `googlers/.github` admin = edit org-shared workflows → workflow execution under org context on subsequent pushes → org-wide supply chain. If `repository_selection == "all"`, this is every googlers repo. | **Critical-adjacent** — expected, but repo *scope* (§4.4) decides how critical |
| `contents: read` | Read repo contents on covered repos (incl. any private repos in scope) | **Yes** (expected granted) | Read contents of `googlers/.github` and any other covered repo — workflows, configs, and any committed-credential blobs of the F13 class. Passive. | **Medium** — expected; verify scope |
| `contents: write` | Push commits / create refs on covered repos | **No** | Direct commit to googlers repos: inject workflow changes into `googlers/.github` (or any repo) without needing admin — org-context code execution on next push. | **Critical** — flag immediately |
| `organization_administration: read/write` | View / update org-level settings & projects | **No** | Org-level takeover: change org settings, manage projects. Not scoped by repo selection. | **Critical** — flag immediately |
| *(bonus)* `organization_user_blocking: write` | Block/unblock users org-wide | **Yes** (expected granted) | Token theft → block/unblock org users; nuisance / attacker can unblock themselves if blocked. No data or code impact. | **Low** |

**Matrix verdict rules (what the operator records):**

1. **Granted set == requested set (§5)** and `repository_selection` covers only the `.github`-class repos → D3 chain's org blast radius = read contents of covered googlers repos + repo-admin on those repos + membership oracle. A real googlers-org foothold, not org-wide.
2. **Any not-requested permission granted** (`members:write`, `contents:write`, `organization_administration`) → the app's compromise becomes org-level; file with the Angular team as a critical configuration issue regardless of the D3 outcome.
3. **`repository_selection == "all"`** → repo-scoped permissions (`administration:write`, `contents:read`, `actions/workflows/checks:write`) extend org-wide; re-rate rows accordingly.

---

## 7. Risk statement — proven in-repo vs settled by this check

**Proven in-repo (agent-side, static + empirical, no Google-side data needed):**

1. App 43341's private key is a workflow secret (`ANGULAR_ROBOT_PRIVATE_KEY`) present in `pull_request_target`-triggered jobs in dev-infra (and the three consuming OT0 repos), including the job that mints the googlers token on every PR.
2. A googlers org installation token is minted in the runtime environment of **every** `pull_request_target` run (opened/synchronize/reopened) — D4: mint-on-every-PR confirmed.
3. In-code use of that token is oracle-only (`checkMembershipForUser`), revoked in `finally`, error-redacted (empirically verified); **no path from fork PR code to the token** (pull_request_target checks out base; lane R7/D4).
4. The D3 primitive is real: verbatim, unescaped rewrite of network-parsed strings into committed TS/YAML (`main.ts:103 writeFile`, glob `dot:true` incl. `.github/workflows/**`, only filter `replacement.includes('gemini')`, needle unfiltered); TS literal breakout executed code (computed-key IIFE → PWNED.txt, `node --check` PASS); YAML duplicate-key injection proven; regenerated bundle (`esbuild_checked_in`) ships the poison; no test coverage. End-to-end exploitation is capped by source control of the Google-authored deprecations page — that is the only reason D3 is not already a finding.
5. Public API: the app requests `members:read`, `administration:write`, `contents:read` and repo/PR/actions-scoped writes — **not** `members:write`, `contents:write`, `organization_administration`.

**What this check settles (Google-side, operator-only, §3–§5):**

1. **Is the app installed on `googlers` at all?** (404 → the mint fails on every PR → fail-open degradation already folded into F3; remediation = remove the minting path, and the entire question is moot.)
2. **The GRANTED permission set** on that installation, vs the requested baseline (§5). Any delta is a critical flag per §6.
3. **Repo scope** (`repository_selection`, and the repo list via §4.4 if `selected`) — decides how far `administration:write` / `contents:read` reach.
4. **Installation health** (`suspended_at`).

**Bottom line:** in-repo, we can prove the *mechanism* (token mints on every PR; D3 gives an attacker code execution in the job that holds it) and the *requested* ceiling (public API). We cannot prove what the token is actually worth on the `googlers` org — that is exactly the one unknown this procedure settles. If granted == requested and scope is `.github`-class, the D3 chain's org reach is a contained-but-real googlers foothold (repo-admin + contents read + membership oracle). If any not-requested org permission is granted, the D3 chain is an org-compromise chain and the operator should file accordingly.

---

## 8. Cleanup & redaction (always)

- Do **not** store the JWT, any installation token, or the private key in the engagement repo, evidence, or this document.
- `unset JWT TOKEN` after use; close the shell if the key path was on the command line in a shared environment.
- Record only: installation id, `permissions` (permission names + levels are fine), `repository_selection`, repo list, and the delta verdict — no token values, no key material.
- If §4.4 was used, confirm the `DELETE /installation/token` returned 204 (or at least did not 404) before closing the session.
