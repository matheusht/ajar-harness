# DOSSIER — Snapshot distribution repos of angular/dev-infra (visibility, contents, consumers, mislabel)

**Workstream:** WS3 — operator deliverables · **Engagement:** angular-dev-infra-2026-08
**Target pinned:** `angular/dev-infra` @ `04230133d395dfb032d782b8e63b4fcbbd406aa5` (2026-08-07)
**Evidence date:** 2026-08-13 (all API/curl reads performed this session)
**Method:** GitHub REST API via `gh api` (authenticated) + anonymous `curl` + `git ls-remote` + raw file reads (`repos/<owner>/<repo>/contents/<path>?ref=<sha>`) of the three consuming repos. Read-only; no interaction with any live Angular system.
**Companion lanes:** D1 (distribution channel), D3 (update-models rewrite injection), PC-6 (mislabel pattern candidate).

---

## 0. TL;DR

- The four snapshot repos are **all public** — verified two independent ways (`gh api` authenticated and anonymous `curl` 200, `private:false`, `visibility:"public"`), including `dev-infra-private-ng-dev-builds`, whose name and description both say "Private. Do not use."
- They are **the production distribution channel** for pre-release `@angular/ng-dev` builds and the `rules_*` Bazel modules. dev-infra CI force-pushes compiled build output to them on every push to `main` (`publish-snapshots.yml` + `snapshots.ts`).
- Consumers pin them **by commit SHA** and fetch them **anonymously**: pnpm resolves the git dep to `codeload.github.com/.../tar.gz/<sha>` (verified anonymous 200, ~1 MB download), and Bazel `git_override` clones the plain `https://…git` remote with no credential plumbing anywhere in consumer CI.
- **Verdict on the mislabel:** the *public visibility is intentional and architecturally required* (the anonymous-clone distribution model breaks otherwise, including for three external orgs). The **name and description are the mistake** — a vestigial label from the pre-public era, still saying "Private. Do not use." while the repo is the live production channel. This is a *naming/description staleness* issue, **not** a visibility misconfiguration; making the repo private would break every consumer.
- **Operator actions:** (A) leave as-is; (B) keep public + rename/redescribe (recommended, cheap); (C) make private + migrate consumers (large, breaks external consumers, no security gain). Tradeoffs per option in §5.

---

## 1. Visibility of the four snapshot repos

Configured channel (source of truth, `angular/dev-infra` @ pinned SHA): `.ng-dev/release.mjs` maps the four npm/Bazel packages to snapshot repos; `snapshots.ts` pushes to `https://github.com/${owner}/${packageRepo}.git` where `owner` = configured GitHub owner (`angular`).

| Repo | `private` (gh api) | `visibility` | anonymous curl (no auth) | default branch | `pushed_at` | Description (as of 2026-08-13) |
|---|---|---|---|---|---|---|
| `angular/dev-infra-private-ng-dev-builds` | **false** | **public** | **HTTP 200** | `main` | 2026-08-06T14:44:07Z | **"Private. Do not use."** Snapshot builds for `ng-dev` from https://github.com/angular/dev-infra |
| `angular/rules_angular` | **false** | **public** | **HTTP 200** | `main` | 2026-08-06T15:34:07Z | Bazel rules for Angular with `rules_js` |
| `angular/rules_browsers` | **false** | **public** | **HTTP 200** | `main` | 2026-08-06T15:32:43Z | Bazel rules for browser automation & testing |
| `angular/rules_sass` | **false** | **public** | **HTTP 200** | `main` | 2026-08-06T12:00:11Z | High-performance dart-sass ruleset for compiling Sass files |

All four: `archived:false`, `fork:false`, single branch `main` (verified for `dev-infra-private-ng-dev-builds`), last pushed 2026-08-06 (same day — consistent with the snapshot publish workflow). Anonymous access proven three ways:

```
$ curl -s https://api.github.com/repos/angular/dev-infra-private-ng-dev-builds → 200, "private": false
$ curl -s -o /dev/null -w "%{http_code}" https://codeload.github.com/angular/dev-infra-private-ng-dev-builds/tar.gz/c71d9b6… → 200 (1,004,053 bytes)
$ git ls-remote https://github.com/angular/dev-infra-private-ng-dev-builds.git → c71d9b6… HEAD, refs/heads/main
```

Anonymous tarball for `rules_angular` @ pinned SHA also 200 (121,173 bytes).

## 2. What is in them (default branch `main`)

### 2.1 `dev-infra-private-ng-dev-builds` — the `@angular/ng-dev` snapshot channel
- **Contents:** compiled build output of `@angular/ng-dev` (no sources): `auth/`, `bundles/` (incl. `bundles/cli.mjs`), `caretaker/`, `cli.d.ts`, `index.d.ts`, `commit-message/`, `config/`, `format/`, `misc/`, `ngbot/`, `perf/`, `pr/`, `pullapprove/`, `release/`, `ts-circular-dependencies/`, `utils/`, plus `package.json`.
- **`package.json`:** `name: "@angular/ng-dev"`, `version: "0.0.0-92c6b596e59e320c9edbc6d6490c1047264c4a0d"` — the snapshot version string **embeds the source dev-infra commit SHA** (`92c6b59…`), `bin: "./bundles/cli.mjs"`, `private:true` (npm field, irrelevant to git visibility).
- **HEAD on main:** `c71d9b6af7560faa3d002534d416a8045111adae` (2026-08-06T14:44:04Z), commit message `main - 92c6b59 fix(ng-dev): prevent current working directory executable injection on Windows` — the message format is `<branch> - <source-sha> <source-subject>`, i.e. each snapshot commit records which dev-infra commit it was built from.
- **History shape:** ~100 commits visible, oldest 2026-03-11 — history is periodically rewritten/truncated (force-push channel). Consumer SHA pins stay valid because current history is a linear chain; GitHub keeps old objects reachable via the branch while they remain ancestors.
- **Size:** 143,133 KB. Created 2022-07-26.
- **Publish mechanics (source, dev-infra @ pinned SHA):** `.github/workflows/publish-snapshots.yml` runs `pnpm ng-dev release publish-snapshots --skip-non-affected-snapshots` (token `SNAPSHOT_BUILDS_GITHUB_TOKEN`) on **every push to `main`** (also branch `snapshot-test`); `ng-dev/release/snapshot-publish/snapshots.ts` clones the target repo, deletes all files, copies the build output, commits, and **force-pushes** the branch (`push --force -- <branch>`).

### 2.2 `rules_angular`
- **Contents:** Bazel rules module: `MODULE.bazel`, `MODULE.bazel.lock`, `BUILD.bazel`, `REPO.bazel`, `.bazelrc`, `.bazelversion`, `setup/`, `src/`, `test/`, `package.json`, `pnpm-lock.yaml`, `pnpm-workspace.yaml`, `README.md`.
- **`MODULE.bazel`:** `module(name = "rules_angular")` — **no `version` field** (consumed exclusively via `git_override`). Dev deps use `local_path_override` to `../rules_browsers` and `../../../` (dev-infra), showing the snapshot repos are built from a common workspace.
- **`package.json`:** version `1.0.0`.
- **HEAD on main:** `20a373d609c4f5765b9ad367a205f3a635dd2cda` (2026-08-06), message `main - 81abc14 build: update cross-repo angular dependencies`.

### 2.3 `rules_browsers`
- **Contents:** `MODULE.bazel`, `MODULE.bazel.lock`, `BUILD.bazel`, `.bazelrc`, `.bazelignore`, `browsers/`, `wtr/`, `server_test/`, `protractor_test/`, `test/`, `package.json`, `pnpm-lock.yaml`, `pnpm-workspace.yaml`, `README.md`.
- **`MODULE.bazel`:** `module(name = "rules_browsers", version = "0.4.0")`; browser/toolchain extension repos for chrome/chromedriver/firefox across linux/mac/mac_arm/win64.
- **HEAD on main:** `37853f23de9a9a70f53c02a9baa27e08d7d12003` (2026-08-06), message `main - cf0ed17 build: update rules_browsers browsers metadata to latest versions` — this is the cron bot ("rules_browser-update-browsers") channel.

### 2.4 `rules_sass`
- **Contents:** `MODULE.bazel`, `MODULE.bazel.lock`, `BUILD.bazel`, `REPO.bazel`, `.bazelrc`, `.bazelversion`, `src/`, `test/`, `pubspec.yaml`, `pubspec.lock`, `README.md` (dart-sass ruleset; 113,681 KB — large prebuilt toolchain payloads).
- **`MODULE.bazel`:** `module(name = "rules_sass")` — no version. Sass toolchain repos for darwin/linux arm64+amd64.
- **HEAD on main:** `c14ca0f1f901a86515cf89a930c0ed8a011a6e20` (2026-08-06), message `main - e3e93a9 build: update dependency bazel_lib to v3.7.1`.

## 3. Who consumes them (raw file reads, pinned refs)

### 3.1 First-party: commit pins match snapshot repo HEADs exactly
All reads below are raw-file reads at the consumer's current main-branch commit (2026-08-13).

**`angular/angular`** (HEAD `d3d3bc62eae0ac3401eedc1618f06d1a50fc15cf`)
- `package.json:139` — `"@angular/ng-dev": "https://github.com/angular/dev-infra-private-ng-dev-builds.git#c71d9b6af7560faa3d002534d416a8045111adae"` (= snapshot repo HEAD)
- `MODULE.bazel` — `git_override`: `rules_angular` → `20a373d609…` (= rules_angular HEAD), `rules_sass` → `c14ca0f1f9…` (= rules_sass HEAD), `rules_browsers` → `37853f23de…` (= rules_browsers HEAD), `devinfra` → `04230133d3…` (the pinned dev-infra SHA)
- `pnpm-lock.yaml:1603-1605` — resolves to `https://codeload.github.com/angular/dev-infra-private-ng-dev-builds/tar.gz/c71d9b6…`, `{gitHosted: true, integrity: sha512-/32ipA…}`, version `0.0.0-92c6b596…` (integrity-hashed, anonymous codeload)

**`angular/angular-cli`** (HEAD `8d731ec4465f6d65a29817680ecb29f507ba588f`)
- `package.json:57` — same ng-dev pin `#c71d9b6af7…`; lockfile resolves to same codeload tarball
- `MODULE.bazel` — `git_override`: `rules_angular` → `20a373d609…`, `rules_browsers` → `37853f23de…`, `devinfra` → `04230133d3…` (no rules_sass)

**`angular/components`** (HEAD `5fcd95217f3fe8d0bd99bba2bd5abaf6b2168583`)
- `package.json:80` — same ng-dev pin `#c71d9b6af7…`; lockfile resolves to same codeload tarball
- `MODULE.bazel` — `git_override`: `rules_browsers` → `37853f23de…`, `rules_sass` → `c14ca0f1f9…`, `rules_angular` → `20a373d609…`, `devinfra` → `04230133d3…`

### 3.2 External orgs (cannot authenticate to angular-private repos → would break if made private)
- `mesop-dev/mesop` `package.json:83` — `#36946be4df61f6549ae3829c026022e47674eae2` (older pin)
- `ng-packagr/ng-packagr` `package.json:74` — `#c71d9b6af7…`
- `sbb-design-systems/sbb-angular` `package.json:77` — `#c71d9b6af7…`
- Plus mirrors/forks observed by code search: `ng-docs/angular-cn`, `ng-docs/components`, `ng-Classic/ng-classic`, and ~20 copycat/scan forks (codacy scans, `ep-infosec/56_npm_angular`, etc.).

### 3.3 Breadth and cadence
- GitHub code search for `dev-infra-private-ng-dev-builds`: **39 hits** (first-party: angular, angular-cli, components, dev-infra's own `release.mjs` + `config/index.ts`; external: mesop, ng-packagr, sbb-angular, ng-docs; rest forks/scans). The D1 estimate of "6+ repos" is confirmed and conservative.
- `git_override` of `rules_angular` (Bazel language search): exactly the three first-party consumers.
- Pin cadence: `angular/angular` shows near-weekly `build: update cross-repo angular dependencies` commits (07-30, 08-03, 08-07, 08-12, 08-13) — pins auto-track the force-pushed channel (Renovate-managed; `renovate.json` packageRules cover `bazel-module` + `npm` managers).
- **Anonymous fetch is the only path:** no `netrc`, no `BAZEL_CREDENTIAL_HELPER`, no git-credential setup found in angular/angular CI (code search empty). pnpm specifiers are plain `https://…git#<sha>`; Bazel `git_override` remotes are plain `https://…git`. Both fail against a private repo.

## 4. The MISLABEL question: intentional or mistake?

### 4.1 Evidence the public visibility is INTENTIONAL (and required)
1. **The consumption model demands public anonymous clone.** pnpm resolves the dep to an anonymous codeload tarball; Bazel `git_override` clones the https remote; no credential plumbing exists in any consumer CI. Making the repo private hard-fails `pnpm install` and `bazel build` in all consumers.
2. **External orgs consume it.** mesop, ng-packagr, sbb-angular, ng-docs are not in the angular org and have no path to authenticate to angular-private repos. A private repo removes their access entirely.
3. **Org-wide pattern.** The angular org publishes ~60 `*-builds` snapshot repos, all public: `core-builds`, `common-builds`, `compiler-builds`, `material-builds`, `cdk-builds`, `cli-builds`, `angular-devkit-*-builds` (9), `rules_angular`, `rules_browsers`, `rules_sass`, `bazel-builds`, etc. The `dev-infra-private-*` family sits inside this public family.
4. **The publishing code never checks visibility.** `snapshots.ts` clones and force-pushes over plain https with a token; it works for public or private. Nothing in dev-infra relies on privacy.

### 4.2 Evidence the NAME/DESCRIPTION are a stale mislabel (the mistake)
1. **The description literally says "Private. Do not use."** on the live production channel that 6+ repos consume. Same wording on archived siblings.
2. **The naming convention predates the public model.** `dev-infra-private-ng-dev-builds` was created 2022-07-26; the modern commit-pin consumption model (rules repos 2023–2025, history rewritten ~2026-03, `main - <sha>` messages) came later. The "private" prefix and the "INTERNAL USE ONLY" descriptions are leftovers from when these channels were actually private.
3. **Sibling evidence — the whole family is public:** `dev-infra-private-builds` (archived, public, desc "INTERNAL USE ONLY - Angular internal DevInfra tooling/scripts - INTERNAL USE ONLY"), `dev-infra-private-build-tooling-builds` (archived, public, desc "Private. Do not use. …"), `dev-infra-private-docs-builds` (archived, public, 2024-07-30).
4. **Maintainer-facing tooling still calls them "private":** dev-infra `ng-dev/release/config/index.ts:55-56` documents `snapshotRepo` with the example `'dev-infra-private-ng-dev-builds'`; Allstar (OSSF) bot opened branch-protection violation issues against these repos by name in 2024-03 (`angular/dev-infra` issues #1919, #1924, #1925).
5. **No indication of deliberate deception:** nothing in the repos, the publishing code, or the docs suggests the name was chosen to mislead. It reads as an un-updated legacy label.

### 4.3 Verdict
> **The visibility is intentional-by-architecture (public is required for the distribution channel). The name and description are the mislabel — a vestigial "private" label on a public production channel.** This is a naming/documentation defect (and an operational belief-mismatch risk: maintainers reading "Private. Do not use." may assume obscurity), **not** a visibility misconfiguration. Security exposure delta vs. the npm `next` dist-tag is nil — the content is derived from reviewed public `main` and contains no secrets — but the public channel does carry pre-release builds of the privileged `ng-dev` tool, so it is part of the attack surface of the D3 (update-models rewrite) finding: a poisoned bundle committed to dev-infra would be force-pushed here and auto-pinned by all consumers.

## 5. Operator action options (with tradeoffs)

### Option A — Leave as-is
- **Effort:** none. Channel keeps working.
- **Tradeoffs:** (+ zero risk of breakage; + no coordination) (− misleading name/description persist; − "Private. Do not use." is factually wrong on the production channel, so any future maintainer triaging it gets the wrong access-control model; − Allstar/security tooling confusion persists; − the belief gap ("we're obscure") stays available as a rationale for sloppy handling).
- **Verdict:** acceptable short-term, but it is the *status quo that produced the finding*.

### Option B — Keep public + rename & redescribe (RECOMMENDED)
- **What:** rename `dev-infra-private-ng-dev-builds` → e.g. `angular/ng-dev-builds`; update description to e.g. "Public snapshot channel for @angular/ng-dev pre-release builds; consumed via commit pins"; do the same for archived siblings (`dev-infra-private-builds` → `dev-infra-builds`/archive note, `dev-infra-private-build-tooling-builds`, `dev-infra-private-docs-builds`); update the `snapshotRepo` example in `ng-dev/release/config/index.ts` and the Allstar org policy if it references names.
- **Tradeoffs:** (+ removes the mislabel and aligns with the ~60 other public `*-builds` repos; + GitHub auto-redirects old git/codeload URLs on rename, so existing pins keep resolving until Renovate bumps them; + cheap: no code change, no auth change) (− needs a coordinated rename + a consumer pin refresh cycle (Renovate handles it on next bump; lockfiles update on next `pnpm install --frozen-lockfile` run); − archived repos still carry the old name in their history/URLs unless renamed too; − old URLs depend on GitHub's rename redirect for the transition window).
- **Verdict:** lowest-cost fix that makes the access-control model honest.

### Option C — Make private + migrate consumers
- **What:** flip the repos to private, add credential plumbing (netrc/token/SSH) to every consumer CI job and every contributor machine, and/or migrate the ng-dev channel from git pins to npm (`@angular/ng-dev@0.0.0-<sha>` snapshot publishes).
- **Tradeoffs:** (− breaks the current anonymous model hard: pnpm codeload tarballs and Bazel `git_override` in all three first-party consumers fail until migrated; − **external consumers (mesop, ng-packagr, sbb-angular, ng-docs) have no access to angular-private repos and would be cut off entirely**; − large coordinated migration across 3+ repos with zero security benefit — content is already public-derived, reviewable, and secret-free; obscurity is not a control) (+ only real gain: shrinks the diffable pre-release attack surface of the privileged ng-dev tool — but the same builds ship on npm as `next` dist-tags, so even that gain is marginal).
- **Verdict:** not viable as a response to this finding; only sensible if the team independently wants to move ng-dev to npm-based snapshot distribution (separate project, out of scope here).

### Suggested operator follow-ups
1. File the naming fix with the angular/dev-infra team (Option B) — low severity, one-line description fix plus a rename.
2. Note the channel's role in the D3 blast radius when filing D3 (public channel auto-distributes poisoned bundles to pinning consumers).
3. No credential rotation needed: nothing in these repos is secret; `SNAPSHOT_BUILDS_GITHUB_TOKEN` is a workflow secret and stays one.

## 6. Raw evidence commands (reproducible)

```sh
gh api repos/angular/dev-infra-private-ng-dev-builds --jq '{private, visibility, default_branch, description, pushed_at}'
curl -s https://api.github.com/repos/angular/dev-infra-private-ng-dev-builds   # anonymous
curl -s -o /dev/null -w "%{http_code}" https://codeload.github.com/angular/dev-infra-private-ng-dev-builds/tar.gz/c71d9b6af7560faa3d002534d416a8045111adae
git ls-remote https://github.com/angular/dev-infra-private-ng-dev-builds.git
gh api repos/angular/dev-infra-private-ng-dev-builds/contents/package.json --jq '.content' | base64 -d
gh api repos/angular/dev-infra-private-ng-dev-builds/commits/main --jq '.sha + " | " + .commit.message'
gh api -H "Accept: application/vnd.github.raw" "repos/angular/angular/contents/package.json?ref=d3d3bc62eae0ac3401eedc1618f06d1a50fc15cf"
gh api "search/code?q=dev-infra-private-ng-dev-builds"
```

*Written for the operator. No changes to any target tree; all reads public API; no credentials stored.*
