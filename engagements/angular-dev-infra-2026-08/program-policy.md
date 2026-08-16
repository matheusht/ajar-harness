# program-policy.md — Google OSS VRP rules for `angular/dev-infra` (captured 2026-08-12)

> Authoritative program brief for `angular-dev-infra-2026-08`.
>
> **Source-quality warning, stated once and binding.** `bughunters.google.com` is a JS SPA. It
> returns a ~3.8 KB empty shell to a fetcher. The Wayback capture of the rules page (2026-08-05,
> HTTP 200) is the same shell — 15 KB of HTML rendering to 423 characters of text with no tier
> labels, no category names, and no amounts. **The tier assignment below is primary-verified. The
> reward amounts are corroborated from secondary sources and are NOT primary-fetch-verified.**
> Re-verify at `bughunters.google.com/open-source-security` before the operator files.

## 1. Tier — primary-verified

`https://github.com/angular/dev-infra` → **`TIER_OT0`**, `product_vuln_scope: SCOPE_OSS_VRP`.

Source: `github.com/google/bughunters` → `oss-repository-tier/external_repositories.txtpb`, fetched
2026-08-12. That file holds 71 tiered repositories (26 OT0, 45 OT1). Four Angular repositories are
OT0: `angular/angular`, `angular/angular-cli`, `angular/components`, `angular/dev-infra`.

OT0 is the flagship tier — the top payout band.

## 2. Scope boundary

- **In scope:** all **up-to-date** versions of open-source software in the public repositories of
  Google-owned GitHub orgs. **Repository configuration is explicitly in scope** — GitHub Actions
  workflows, app configs, and access-control rules. That sentence is what makes this engagement's
  primary surface reportable at all, so it is quoted here rather than paraphrased loosely.
- **"Up-to-date" is load-bearing.** Issues that only affect a stale or unpatched version are not
  rewarded. Pin to `main` HEAD and re-pin before filing.
- **Third-party dependencies** are in scope only when the flaw is triggerable in the Google project,
  and with a hard **upstream-first** requirement: report to the dependency owner first, let the fix
  land, then notify Google.

## 3. Reward categories — and which one this engagement targets

| Category | What it covers | OT0 range |
|---|---|---|
| **Supply-Chain Compromise (SCC)** | ability to compromise Google OSS **source**, **build artifacts**, or **packages distributed via package managers** | **$3,133.70 – $31,337** |
| Product Vulnerability | design or implementation flaw in the shipped software | $500 – $7,500 |
| Other | leaked credentials, insecure install instructions, credential leaks | ~$1,000 |

**This engagement targets SCC.** `angular/dev-infra` is a build-and-release asset: it publishes four
npm packages and supplies the composite actions and reusable release workflow that three other OT0
repositories run in their CI. Its natural failure mode is precisely "compromise source, build
artifacts, or published packages."

Google states SCC remains a top priority **across every project tier** after the 2026 update. It is
both the highest-paying category and the stated priority. Grade every candidate against the category
it would actually file under; do not inflate a Product Vulnerability into an SCC claim to reach the
higher band. The adjudication oracle checks this.

## 4. The March-2026 rule update — what binds here

- **Memory-safety gate:** OT0/OT1 memory-corruption reports now require an exact OSS-Fuzz
  reproduction through an **existing** fuzz target, or a merged patch. **Not applicable to this
  engagement** — the target is TypeScript, JavaScript, YAML, and Starlark. There is no memory
  corruption to gate. Do not manufacture one; that would push a candidate *into* a gate it is
  currently outside of.
- **OT2/OT3** lost eligibility for Product Vulnerability and Other entirely; only SCC still pays
  there, at a lowered cap. Recorded so that tier drift on any pivoted asset is caught. `dev-infra` is
  OT0, so this does not bind today.
- Google publicly attributed the tightening to a surge of AI-generated reports carrying hallucinated
  triggers or negligible impact. See §8.

## 5. Hard constraints

- Target only the **latest** version. Stale-version-only findings are rejected.
- **Upstream-first** for any third-party-dependency flaw.
- **No production-disruptive or law-violating testing.** Testing must not disrupt or compromise any
  data. This engagement is local and disposable; see `scope.md` for the hard wall around the real
  Angular org.
- No participation by Google or partner-company employees, or sanctioned individuals or entities.
  The operator attests eligibility.
- Unclaimed rewards are donated to charity after 12 months; a voluntary charity donation pays 2x.

## 6. Out of scope / excluded

- Non-Google-owned orgs and forks.
- Software running only outdated or unpatched versions.
- Any destructive or production-impacting testing.
- **Attribution:** a finding must be **`angular/dev-infra`-attributable**. A flaw in how a *consuming*
  repository wires a dev-infra action is that repository's bug, not dev-infra's. State the attribution
  per candidate. This gate killed candidates in `google-oss-vrp-2026-07` and it will bite here.
- Previously disclosed items, and issues already fixed or already on a published roadmap. Real, but
  not reportable — record both facts separately.

## 7. Verified target facts (recon, 2026-08-12)

**Published npm packages** (`.ng-dev/release.mjs`): `@angular/ng-dev` (representative),
`rules_angular`, `rules_browsers`, `rules_sass`. The repository's own `package.json` is
`@angular/build-tooling`, marked private.

**Secrets held by dev-infra workflows:**

| Secret | Workflow(s) | Why it matters |
|---|---|---|
| `ANGULAR_ROBOT_PRIVATE_KEY` | `dev-infra`, `branch-manager`, `assistant-to-the-branch-manager`, `org-wide-actions` | **GitHub App private key.** Org-wide write. The crown jewel. |
| `LOCK_BOT_PRIVATE_KEY` | `org-wide-actions` | second App key, org-wide |
| `GOOGLE_GENERATIVE_AI_KEY` | `dev-infra` | Gemini key, in a job that also holds the robot key |
| `SNAPSHOT_BUILDS_GITHUB_TOKEN` | `publish-snapshots` | snapshot publishing |
| `NG_RENOVATE_USER_ACCESS_TOKEN` | `ng-renovate` | user PAT driving self-hosted Renovate |
| `ANGULAR_ROBOT_ACCESS_TOKEN`, `RBE_TRUSTED_BUILDS_USER` | `update-models` | remote build execution credentials |
| `id-token: write` | `reusable-release` | OIDC, npm trusted publishing |

**Privileged triggers:** `dev-infra.yml` uses `pull_request_target` **and** `issues`.
`assistant-to-the-branch-manager.yml` uses `pull_request_target`. `reusable-release.yml` is
`workflow_call` with `id-token: write`.

**Fan-out — measured.** Consuming OT0 repositories referencing dev-infra actions:

| Consumer | Workflows referencing dev-infra | `uses:` references | Pinning |
|---|---|---|---|
| angular/angular | 11 | 62 | **62/62 SHA-pinned** |
| angular/angular-cli | 5 | 55 | **55/55 SHA-pinned** |
| angular/components | 13 | 91 | **91/91 SHA-pinned** |

**208 of 208 references are SHA-pinned.** This is a **held control** and a positive-control
candidate, not a finding. It closes the automatic-propagation path. It does **not** close:
the flaw already present in a pinned SHA; the pin-bump review path; or the App-key path, where a
stolen `ANGULAR_ROBOT_PRIVATE_KEY` reaches every repository directly and pinning is irrelevant.

## 8. AI-authorship — binding resolution for the filing step

The OSS VRP publishes no blanket AI-submission ban, but Google attributed the 2026 tightening to
AI-generated reports with hallucinated triggers and negligible impact. This engagement therefore
carries the harness's standing cautious resolution: **the operator personally re-authors all final
submission text.** Everything produced here is an internal research artifact for that re-authoring,
never pasted verbatim. **Filing is operator-only** and is wire 5 in `scope.md`.

## 9. Sources

- `github.com/google/bughunters` — `oss-repository-tier/external_repositories.txtpb` + README
  (primary fetch, 2026-08-12): the OT0 tier assignment.
- `bughunters.google.com/about/rules/open-source/...` — live page and 2026-08-05 Wayback capture,
  both SPA shells, **no readable rules content**.
- `bughunters.google.com/blog/ossvrp-rule-updates-2026` (Mar 2026) — the tightening; secondary.
- Google Online Security Blog, OSS VRP launch (Aug 2022) — categories and the $100–$31,337 range.
- BleepingComputer, SecurityWeek, Cybersecurity Dive, Help Net Security — corroboration of amounts.
- `angular/dev-infra` @ `04230133d395dfb032d782b8e63b4fcbbd406aa5` and the three consuming
  repositories — direct GitHub API reads, 2026-08-12, for every fact in §7.
