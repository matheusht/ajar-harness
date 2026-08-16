# recon-signals.md — angular-cli-2026-08

Recon output. Each observation names the cards it lights up and at what strength
(`strong` / `weak` / `negative`), per `engine/routing.md`. A `negative` signal is a control that
looks correctly enforced — it is recorded as likely-held and as a **positive-control candidate**,
never as a finding.

**Updated 2026-08-14 (history sweep complete; activation table seeded from sweep shapes).** The tables below are the shape to fill, plus the priors carried in
from scoping. Do not treat a prior as an observation.

---

## 1. Activation table

| # | Observation (file:line) | Cards lit | Strength | Note |
|---|---|---|---|---|
| R-1 | New MCP server surface (`ng mcp`): 8 stable tools, root-restricted host, client-controlled roots, executes `ng` subprocesses from workspace | client-supplied-selector-authz, unsafe-default-authz-helper | **strong** (new high-value surface, recent fixes show it was missed) | Rounds: MCP tool input → fs/exec boundary; every tool's `server` plumbing; `listRoots`/`setRoots` flows; generic run_target path |
| R-2 | History: OS-command-injection fixes (spawn shell:true, git task `-m` shell) — family may have surviving siblings | command-construction | **strong** (two independent fixes in one family = siblings likely) | grep all spawn/exec; check schematics tasks (npm, repo-init, tsc, run-schematic), builders with config-derived args |
| R-3 | History: build-output containment fixes (outputPath escape, asset input escape, symlink workspace roots) | path-traversal, symlink-confusion | strong | sibling builders: test/karma/extract-i18n/e2e/dev-server; watch-mode deletions; `delete-output-dir` |
| R-4 | History: MCP workspace-root fix landed recently (get_best_practices) | client-supplied-selector-authz | strong | verify every other MCP tool passes `server` to `resolveWorkspaceAndProject`; docs/search path handling |
| R-5 | History: SSR proxy-header trust → explicit opt-in (percent-encoding defeated regex filters) | request-forgery | weak-medium | remaining `X-Forwarded-*`/host-derived logic in ssr; URL construction with user data |
| R-6 | History: registry credential parsing removed (forceAuth, unscoped) — plumbing still worth tracing | credential-handling | weak | how tokens reach fetch headers; npmrc parsing; any leftover auth variants |
| R-7 | History: SRI for dynamically loaded modules (new) — validation surface | integrity-bypass | weak | manifest → hash → comparison; data:/inline bypass |
| R-8 | History: `createRequire` parent-path escape fixed — module-resolution trust boundary | resolution-asymmetry | weak-medium | other resolve() sites seeded by workspace values |
| R-9 | `ng add`/`ng update` = fetch-and-execute by design; boundary question = wrong package / skipped integrity / silent downgrade | supply-chain | strong (priority lane) | package.json name collision, alias handling, version range satisfaction, `--registry` override paths |
| R-10 | 7 workflows, `.ng-dev/` + `dev-infra.yml` consumed from dev-infra (attribution boundary!) | supply-chain (CI) | strong (priority lane) | fork PR head checkout, secrets scope, cache poisoning, `pull_request_target` usage |
| R-11 | Lockfile/build-graph integrity: `MODULE.bazel.lock`, pnpm lock, `constants.bzl`, `goldens/`, `.monorepo.json` | integrity | medium | what validates them at release time |
| | | | | |

The orchestrator may use, ignore, or override any activated card, but records **one line on why**
for a `strong` signal on a high-impact path.

---

## 2. Baseline controls — what the code refuses with no attack

Capture these before attacking anything. Without them a later "it rejected" means nothing.

| Control | Where enforced (file:line) | Observed refusal | Positive control? |
|---|---|---|---|
| MCP file access confined to declared roots (client roots or cwd) via realpath containment | `packages/angular/cli/src/commands/mcp/host.ts` `createRootRestrictedHost` → `checkPath` (realpath + `relative(root, path)` guard) | `Access denied: path ... is outside allowed roots` | yes — used as positive control for any MCP path claim |
| MCP glob rejects `..` traversal patterns and checks both cwd and target dir | host.ts `glob` wrapper | `Access denied: glob pattern ... contains path traversal sequences` | yes |
| MCP child processes spawn with `shell:false` (no shell string interpolation) | host.ts `executeNgCommand` / `startNgProcess` (`spawn(..., {shell:false})`) | n/a (static) | yes — post-`2d3eb7fb3`/`f1ed0257a` family |
| MCP tools resolve caller workspacePath against allowed roots before parsing (`isAllowedWorkspacePath`, realpath both sides) | `packages/angular/cli/src/commands/mcp/workspace-utils.ts` `resolveWorkspaceAndProject` | `Workspace path is outside the allowed MCP roots` | yes — post-`34e1e0bb5` fix; **verify every tool passes `server`** (get_best_practices was the missed one) |
| Workspace parse requires `angular.json` presence before load | workspace-utils.ts (existsSync guards) | `No angular.json found at ...` | yes |
| Build output writes scoped to outputPath (post-fix) | `packages/angular/build/src/builders/application/index.ts` + utils/path.ts `isSubDirectory` | n/a (static) | yes — post-`8358805d3`/`163a03264`; check sibling builders |
| SSR proxy headers require explicit opt-in (post-fix) | `packages/angular/ssr/node/src/request.ts` | n/a (static) | yes — post-`5adc92541`; check remaining header-derived paths |
| `ng add`/`ng update` package resolution (to be verified per candidate) | packages/angular/cli/src/commands/add (to read) | tbd | tbd |
| | | | |

---

## 3. History sweep — shapes only, never diffs

Recorded **once**, at the start. It seeds routing and does not steer the loop.

**A fixed bug marks a FAMILY, not a target.** Where one instance was wrong, siblings live. Any
candidate that maps to a swept shape is checked against the actual fix before promotion, and
**a fix is never reported as a find**.

| Shape | Where the family lives | Sibling sites to check |
|---|---|---|
| Command/args joined into a shell string before `spawn`/`exec` (`shell:true`, manual quoting) → OS command injection | `2d3eb7fb3` fixed ssr-dev-server builder (`outputPath` → `$()`); `f1ed0257a` fixed schematics git task (`-m` message via shell) | all `spawn`/`exec`/`execFile` call sites across `packages/` (build, ssr, devkit, cli); any remaining `shell:true`; args built from config or package-manifest data |
| Network-facing request handler trusts `X-Forwarded-*` without explicit opt-in; percent-encoded payloads defeat regex filters | `5adc92541` fixed `@angular/ssr` request.ts/app-engine.ts (secure-by-default opt-in) | remaining header-derived URL/logic in ssr; cookie/host handling; URL constructor decoding edges |
| Caller-supplied workspace path crosses into filesystem access without an allowed-roots check | `34e1e0bb5` fixed MCP `get_best_practices` (missing `isAllowedWorkspacePath`); `2b060630c`, `4815a5417` adjacent | every MCP tool taking `workspacePath`: run_target, devserver_start/stop/wait_for_build, projects, get_best_practices — plus non-MCP callers of path consumers |
| Builder file writes/deletes escape the configured output root (relative `..` segments, symlink/junction workspace roots) | `8358805d3` fixed application builder output scoping; `163a03264` fixed asset input containment; `751adb9d7` remapped metafile paths for symlinked roots | other builders (test, karma, extract-i18n, e2e, dev-server); asset glob follow-ups; delete paths; watch-mode deletions |
| Registry auth/credentials parsed non-standardly from config and forwarded | `f8c3df4e2` removed `forceAuth` + unscoped credential parsing in package-metadata.ts | how tokens reach `fetch` headers in package resolution; any other config-driven auth plumbing; npmrc parsing |
| Subresource-integrity hashes for dynamically loaded modules | `0c18dc0f6`, `58c7c7a9d` added SRI validation for dynamic imports | can a manifest/attacker influence which hashes are emitted or compared; bypass via inline/`data:` URLs |
| Module resolution from builder code can escape its package (`createRequire` parent paths) | `0010b922f` scoped `createRequire` with `paths` | other `createRequire`/`require.resolve` sites in build/ssr/devkit where a workspace value seeds resolution |
| Generated-code escaping in schematics (user/package strings embedded into TS without safe quoting) | `59e5e967a` multiline comment-out in refactor-jasmine-vitest | all codegen templates stringifying external values (class names, file paths, messages); `ng generate` routes |
| Symlink/realpath asymmetries between validators and writers (check one path, write another) | `751adb9d7`, `41bd100dd`, `dc27e17fc` (preserveSymlinks family) | anywhere a check resolves realpath while the write follows symlinks, or vice versa |

**Fixed-bug note:** every shape above is a *recently fixed* defect — the program rejects
stale-version-only findings. These mark families; each candidate is checked against the actual fix
commit before promotion.
| | | |

---

## 4. Proof strategies — the two Supply-Chain lanes

The SCC band tops out at **$31,337**, roughly 4× the best Product-Vulnerability outcome. Each lane
gets a **proof strategy, not a feasibility verdict**. "No path found" is not an answer — it closes
the highest-value lane early. A lane with a strategy and no path stays **OPEN**.

### Lane A — the release and publish path

*What would count as proof to a Google triager?* — write it before hunting.
*What sub-conditions does "attacker code reaches a published artifact" decompose into?*
*What must the lab show?*

- [ ] sub-conditions enumerated
- [ ] what a reviewer would accept as proof, stated
- [ ] lab requirement stated
- **status:** OPEN

### Lane B — CI and workflow compromise

Seven workflows. The questions that decide this lane: does any workflow run untrusted PR content
with secrets in scope; can a fork poison a cache the trusted path consumes; is there a
`pull_request_target` with a checkout of the PR head.

- [ ] sub-conditions enumerated
- [ ] what a reviewer would accept as proof, stated
- [ ] lab requirement stated
- **status:** OPEN

---

## 5. Priors carried from scoping — NOT observations

These are reasons to look, not evidence of anything. Delete or convert each one as Round 0 settles it.

- `ng add` / `ng update` fetch and execute third-party code **by design**. The design intent is the
  baseline; a finding must show a boundary the design does not intend — wrong package resolved,
  integrity check skipped, a downgrade silently accepted.
- `@angular/ssr` is the only surface that faces a network request at runtime.
- `@angular-devkit/core` holds the path and virtual-fs primitives — the natural home for traversal
  and normalization defects.
- Builder resolution in `architect` reads workspace files; whether a workspace file can redirect a
  builder to arbitrary code is a question, not a claim.
- `.ng-dev/` and `dev-infra.yml` bind this repo to `angular/dev-infra`. **Root causes that resolve
  into dev-infra are attributed there** (scope.md, the Attribution boundary section) and recorded in `cascades.md`.

---

## 6. Negative signals — controls that look correctly enforced

Recorded as likely-held and as positive-control candidates. Not findings.

| Control | Why it looks held | Where it would be a positive control |
|---|---|---|
| | | |
