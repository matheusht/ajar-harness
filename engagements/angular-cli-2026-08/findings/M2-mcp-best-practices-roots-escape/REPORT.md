# M2 — MCP `get_best_practices` reads outside the declared MCP roots and injects the content into the agent context

- **Engagement:** angular-cli-2026-08 · **Pinned commit:** `d827ba9005b86b23d05ee7c62c0823367aa245c1`
- **Surface:** `packages/angular/cli/src/commands/mcp/tools/best-practices.ts` (`getVersionSpecificBestPractices`, ~lines 88-185) + `workspace-utils.ts` (`isAllowedWorkspacePath`)
- **Status:** PROMOTED (2026-08-15) — **AMPLIFIED in the cascading phase (E0-R2/E6):**
  **re-poisoning persistence note (R6-E6, narrowed):** `createBestPracticesHandler` caches only
  the bundled guide (`bundledBestPractices ??=`); the version-specific (attacker-influenceable)
  guide is re-read fresh on EVERY call (no memoization/TTL/backoff at best-practices.ts:88-190) —
  mechanically confirmed, no intermediate caching layers. The delta survives as a
  persistence/adaptivity NOTE (the poisoning re-fires per consultation and adapts to file changes),
  not a capability increase (the first injection already controls the agent's subsequent actions).
  **Cascade note (E0-R2/E8):** `resolveNgCommand` (host.ts:124-140) is a same-shape sibling —
  `createRequire(join(cwd,'package.json')).resolve('@angular/cli/package.json')` walks the ancestor
  hoist, and the resolved binary is spawned with only the cwd root-checked — real-but-capped
  (≈ zero marginal delta: the resolved binary is the developer's own build tooling; structure came
  from the security-intent refactor 240936daf — sibling-miss in a security-focused change).
  Bounded sub-angles: tool results do not reach server-side logs (warn-only fallback messages);
  ai_tutor/instructions resources are static (no cross-tool contamination).
- **Adjudication history:** adversarial refuter (R2-1): REAL-BUT-CAPPED (see reviews/review-r2-1.json); promoted 2026-08-15; amplified in cascading phase (E0-R2/E6) and deep phase (E1-R3/A3 run_target amplifier; E1-R4/L8 trigger refinement; E1-R6/KP-M2RT mechanism correction).

## One sentence on why it is real

The MCP security model confines every tool to the client's declared roots, but `get_best_practices` validates only its *input* workspace path and then lets Node module resolution (`createRequire`) escape to an **ancestor** `node_modules` outside the roots; the resolved package's `angular.bestPractices.path` guide is read with raw `readFile` and returned to the assistant — a demonstrated byte-for-byte injection of attacker-influenceable content across the sandbox boundary.

## Mechanism

`getVersionSpecificBestPractices(workspacePath, logger, server)`:
1. `isAllowedWorkspacePath(server, workspacePath)` — checks the **input** against client roots (the fix `34e1e0bb5` — present at the pin).
2. `createRequire(workspacePath)` then `resolve('@angular/core/package.json')` — Node walks `workspace/node_modules` **and then every ancestor** `node_modules` up to `/`. Two firing modes:
   - directory input (schema describes `workspacePath` as "the absolute path to the workspace"): `createRequire(dir)` treats the dir as a filename in its **parent**, so resolution starts at the parent — the workspace's own `node_modules` is skipped entirely.
   - file input (the documented `list_projects` value, `…/angular.json`): resolution checks the workspace's `node_modules` first, then ancestors — in a **hoisted pnpm monorepo** the workspace has no own `@angular/core`, so the hoist at the repo root (outside narrow roots) wins.
3. The resolved `pkgJsonPath` is read with raw `readFile` — **never re-checked against roots**.
4. `bestPracticesInfo.path` (from that package.json's `angular.bestPractices`) is resolved **within the resolved package dir only** (the `relative()` guard) and read (1 MB cap), then returned as `{ type: 'text', annotations: { audience: ['assistant'], priority: 0.9 } }` — i.e. **injected into the LLM agent's context as instructions**.

## PoC (real path, built CLI at the pin)

Layout: workspace `/tmp/mcp-poc/workspace` (declared root, `file:///tmp/mcp-poc/workspace`), **no** workspace-local `node_modules`; hoisted `@angular/core` at `/tmp/mcp-poc/node_modules/@angular/core` (the workspace's parent — outside roots) whose `package.json` declares `angular.bestPractices.path = "guide.md"` containing `MARKER-ATTACKER-GUIDE-9f3c1e`.

Client: raw stdio JSON-RPC against `dist/bin/packages/angular/cli/bin/ng.js mcp` (built at the pin), answering `roots/list` with the workspace root.

Result (both the file-path and directory-path input forms):
```
TOOL-RESP: {"result":{"content":[{"type":"text",
  "text":"MARKER-ATTACKER-GUIDE-9f3c1e\nATTACKER-CONTROLLED BEST PRACTICES CONTENT\n",
  "annotations":{"audience":["assistant"],"priority":0.9}}]}}
```
Evidence: `evidence/mcp-client4.mjs` (directory input), `evidence/mcp-client5.mjs` (file input), `evidence/workspace/`, `evidence/hoisted-node_modules/`.


## NOVELTY UPDATE (N5-F, verified via GitHub API): the tool-poisoning CLASS is disclosed + won't-fix — the stealth delta answers the doctrine

- **#32766 (severity6: security, closed 2026-03-16, gemini-triaged):** "Indirect Prompt Injection via Unsanitized Code Comments in Angular CLI MCP Server" — the MCP tool-output prompt-injection class (OWASP MCP-01 Tool Poisoning) was DISCLOSED and TRIAGED by the maintainers. Their won't-fix response: "you need to already have a hook to poison the agent's context... implies already compromised" (the same config-trust-style doctrine as the other rejections); the reporter pushed back (postinstall-comparison). The ZONELESS echo (our L4a bounded note) is the disclosed instance.
- **The C3/M2 filing counter-delta (from the novelty):** the STEALTH SHAPE (N4C) answers the doctrine — the steering hook is metadata/stealth (symlink-hidden traversal via run_target; the anomaly never appears in the tool call), not a malicious visible component. The chain combination (stealth shape + priority-0.9 guide channel + run_target option-values) is NOT disclosed. Filing must cite #32766 + its discussion to preempt the doctrine dismissal.
- **Population citations:** #33628 (Claude desktop failure — the desktop-assistant population), #33653 (enforce MCP roots — the fix PR, already cited).

## DEEP-PHASE STATUS (E1-R2/X4 + L9c): re-PoC at the pin + novelty

- **Fix status (verified at the pin):** the pin contains three upstream fixes — 34e1e0bb5 (2026-07-25, enforce MCP roots), 2b060630c (2026-07-25, handle isAllowedWorkspacePath errors), 24fd8fce2 (2026-08-11, throw on out-of-roots workspace) — i.e. the input-level channel of the ORIGINAL PoC is fixed upstream. The promoted claim was always the residual, and the residual **stands**.
- **Re-PoC at the pin (E1-R2/X4, compiled from pin source):** built the MCP server from the pin's source (esbuild bundle of mcp-server.ts + serveStdio, containing all three fixes) with roots=[workspace]; get_best_practices with an in-roots workspacePath returned MARKER-ATTACKER-GUIDE-2 byte-for-byte from a hoisted @angular/core at the parent (outside roots) for BOTH directory and file input forms; the out-of-roots negative control was correctly rejected ("Workspace path is outside the allowed MCP roots"). Evidence: findings/M2/evidence/repoc-pin/ (mcp-server.cjs, client2*.mjs, workspace/, hoisted node_modules).
- **Novelty:** the residual ancestor-walk channel is undisclosed (no follow-up issue/PR found on it; L9c).
- **Positive control (E1-R1/L4a):** the new onpush-zoneless-migration MCP tools family is CLEAN — all reads flow through the restricted host (checkPath realpath containment); no roots-escape, no writes, no exec — the restricted host contains the MCP family everywhere except this tool's raw createRequire+readFile, strengthening the negative control.


## DEEP-PHASE AMPLIFIER (E1-R3/A3, verified at source): run_target option-VALUE channel bypasses the restricted host

- **Mechanism (verified):** run_target accepts free-form `options` values (keys regex-validated in serializeOptions; VALUES verbatim as `--key=value`); executeNgCommand checks cwd only — no value containment. Builder side (E1-R6/KP-M2RT corrected): `browser`/`main`/`polyfills`/`tsConfig` string options with RELATIVE `..` traversal escape the workspace root via `path.join` normalization and read out-of-roots parseable files into the build (live-verified: join(ws, '../outside/secret.ts') resolves above ws; content embedded in output); `fileReplacements` object arrays are mangled by serializeOptions ([object Object]) and are NOT a channel through run_target; outputPath uncontained on legacy/extract-i18n/custom targets (application builder contained via 8358805d3).
- **Delta:** (a) SILENT read+write via a legitimate build (evades the restricted host AND process-level monitors); (b) STEERABLE — the tool description endorses run_target as the native interface, so repo-content prompt injection can route exfil through it; (c) FUTURE-REACH — for shell-less MCP clients this is the concrete arbitrary file read+write primitive that bypasses the restricted host entirely (the L8/M2 future-reach condition, now mechanized).
- **Capped:** standard shell-capable clients retain the R7 cap (agent has shell); exfil via contained outputPath still requires the agent to retrieve the in-workspace bundle (allowed, within roots).
- **N4C CLOSING BRANCH (2026-08-15): the in-lab real-agent run CLOSED — stealth shape FOLLOWED.** An unprepared agent (fresh context, no framing) received the stealth guide (priority 0.9) and FOLLOWED the steered option when the traversal was hidden behind a legitimate-looking repo setup (symlinked build entry — the anomaly never appears in the tool call): run_target argv clean, exfil complete. Evidence: findings/M2/evidence/steering-demo/shape-B/. The C3 chain verdict is now ARMED-WITH-MECHANICALLY-PROVEN-STEALTH-SHAPE (the visible-anomaly shape remains refused — N1C).
- **Promotion trigger (N2F refined — ARMED with a mechanically-proven stealth shape):** the blind harness (N1C) showed an unprepared agent REFUSES a visibly anomalous traversal directive; the ONE-LEVEL INDIRECTION shape survives (N2F mechanically proven): an option value that does not look anomalous in the tool call (hidden behind a legitimate-looking build step) bypasses even a hardened agent that flags visible dot-dot — the anomaly never appears in the tool call. C3 verdict refined accordingly. **Promotion trigger (E2-R3/C3D baseline — ARMED-BUT-UNCONFIRMED):** the shell-less population is REAL today (Claude Desktop / ChatGPT Desktop: documented local stdio MCP, no native shell tool for the model); run_target mechanics PROVEN (isReadOnly:false, options verbatim, traversal exfil — KP-M2RT); the ONLY boundary (restricted host) is bypassable via a single tool call. Two closing branches: (a) an in-lab harness demo with a real LLM agent following the steered instruction (the E2-R6 integration item — H2 hop), or (b) documented deployment evidence of a shell-less client with the angular-cli MCP server. The N4C closing branch has since CLOSED one branch in-lab (stealth shape followed); the desktop-client deployment branch remains open; the chain itself (repo content -> priority-0.9 instructions -> steered run_target -> out-of-roots exfil into the build artifact) is DEMONSTRATED with real modules (E2-R3/C3B).
- **Remediation (M2 family):** apply checkPath-style containment to resolved values of path-bearing options (outputPath, fileReplacements, tsConfig, browser, main, polyfills, entryPoints) in the run_target strategies, and restrict run_target option keys to the target's schema-defined options.

## Trust boundary crossed

`workspacePath` (client-supplied, root-checked) → `createRequire` module resolution → raw `readFile` **outside the declared roots** → assistant-context instructions (priority 0.9) framed as official Angular guidance (`source: framework version X`). The agent can then act on the injected content using the server's own tools (`run_target` / `devserver_*` — code execution with developer privileges).

## Impact (honest)

- **Confirmed:** control bypass — the tool reads files outside the declared roots in standard hoisted-monorepo layouts, and attacker-influenceable content reaches the assistant context byte-for-byte (demonstrated).
- **Capped:** the *attacker-influence* precondition requires the resolved `@angular/core` metadata to be attacker-controlled — a malicious/compromised/vendored `@angular/core` in the hoist location (dependency-confusion or supply-chain precondition), or a shared dev machine where an ancestor `node_modules` holds attacker content. In a fully benign hoist the content is the real package's (fallback to bundled guide). The read itself is bounded to the resolved package dir (1 MB cap) — no arbitrary-path read.
- Not claimed: arbitrary file disclosure (guide path is package-dir-confined), nor remote exploitation (MCP is stdio-local).

## Negative control

- The root-restricted host (`host.ts` `checkPath`) rejects the same paths when they flow through `stat/existsSync/readFile/glob/executeNgCommand` — i.e., the *control* exists and is enforced everywhere except this tool's raw `fs` usage. `isAllowedWorkspacePath` rejects an out-of-roots *workspace input* (the fix's scope).

## Replay / staleness

- Replayed via the compiled pin source (twice, both input forms — E1-R2/X4 re-PoC: MARKER-ATTACKER-GUIDE-2 returned at the pin; the out-of-roots negative control rejected). The INPUT-level roots fixes (34e1e0bb5/2b060630c/24fd8fce2) are in the pin; the residual ancestor-walk channel is live at the pin. Stable-release reach (v22.1.4 vs the 22.2-line claim) is UNVERIFIED in-lab — operator to confirm on the release branch before filing. The deep-phase re-PoC confirms the residual at the pin; not stale.

## Severity / category

- **Low-Medium.** CVSS:3.1/AV:L/AC:H/PR:N/UI:N/S:U/C:L/I:L/A:N  (vector rationale in this report; finding.json cvss field pending operator population). Category: Product Vulnerability (MCP tooling). The control-bypass is deterministic; the adversarial content requires the supply-chain precondition; the injection sink (agent context) amplifies but is agent-dependent.
- Refuter (R2-1) verdict: **real-but-capped** — bypass fully confirmed; cap = the attacker-control
  precondition on the resolved `@angular/core` metadata (dependency confusion / vendored override /
  compromised package), which is already code-exec at install time — the injection channel's
  marginal contribution over that baseline is small. Additional finding: the guide-path `relative()`
  check is string-based (no realpath), so a symlink inside the resolved package dir follows to an
  arbitrary file (same precondition). Operator re-review before any filing decision.

## Remediation

1. Re-check the **resolved** `pkgJsonPath` (and the guide path) against the client roots before reading (same `isAllowedWorkspacePath` semantics on the resolved realpath).
2. Resolve `@angular/core` from the workspace root **without ancestor traversal** (`createRequire` scoped with `paths: [workspace/node_modules]`, or explicit `require.resolve` with paths).
3. Audit the other MCP tools for raw-fs reads outside the host (`doc-search` fetch, `projects.ts` package.json walk-up).
