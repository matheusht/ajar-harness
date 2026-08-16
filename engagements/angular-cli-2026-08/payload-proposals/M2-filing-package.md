# M2 — FILING PACKAGE (assembled E2-B part 3 / M2-FD; read-only synthesis)

**Finding:** MCP `get_best_practices` reads outside the declared MCP roots and injects the content
into the agent context.
**Engagement:** angular-cli-2026-08 · **Pin:** `d827ba9005b86b23d05ee7c62c0823367aa245c1`
**Severity:** Low-Medium · CVSS:3.1/AV:L/AC:H/PR:N/UI:N/S:U/C:L/I:L/A:N (4.3)
**Status:** PROMOTED (2026-08-15) · gates CLEAR · confidence confirmed · 8 independent reviews on file.
**Recommendation (M2-FD, Wave B):** **FILE THE RESIDUAL NOW (file-as-is)** — with the run_target
amplifier + C3 chain as CONTEXT, not as the core claim. Do NOT hold for the shell-less trigger
(it is the condition for a SEPARATE, higher-severity filing, not a blocker for this one).

---

## 1. Residual claim summary (the core filing claim)

The MCP security model confines every tool to the client's declared roots, but
`get_best_practices` validates only its **input** workspace path (`isAllowedWorkspacePath`) and then
lets Node module resolution (`createRequire(workspacePath).resolve('@angular/core/package.json')`)
walk **ancestor** `node_modules` up to `/`; the resolved package's `angular.bestPractices.path`
guide is read with raw `readFile` (never re-checked against roots) and returned to the assistant
as `{type:'text', annotations:{audience:['assistant'], priority:0.9}}` — attacker-influenceable
content injected across the sandbox boundary, byte-for-byte.

- **Deterministic control-bypass:** the boundary defect fires on ANY hoisted-monorepo layout
  (both directory and file input forms) — no agent action required for the bypass itself.
- **Sibling-miss framing (the delta):** the INPUT channel was fixed three times upstream
  (34e1e0bb5 2026-07-25, 2b060630c 2026-07-25, 24fd8fce2 2026-08-11 — all present at the pin);
  the RESIDUAL ancestor-walk channel is the sibling miss in a thrice-fixed security family.
  Novelty: the residual channel is undisclosed (no follow-up issue/PR found; L9c).
- **Reach:** live at the pin (E1-R2/X4 re-PoC, compiled from pin source): MARKER-ATTACKER-GUIDE-2
  returned byte-for-byte for both input forms; out-of-roots input correctly rejected.
- **Capped:** the attacker-INFLUENCE precondition requires the resolved `@angular/core` metadata to
  be attacker-controlled (dependency-confusion / vendored override / compromised package —
  already code-exec at install time); the read is bounded to the resolved package dir (1 MB cap).
  Not claimed: arbitrary file disclosure, remote exploitation (MCP is stdio-local).

## 2. run_target amplifier (CONTEXT for the remediation family)

- run_target accepts free-form `options` VALUES verbatim (`--key=value`); `executeNgCommand` checks
  cwd only — no value containment. Builder side (E1-R6/KP-M2RT corrected): `browser`/`main`/
  `polyfills`/`tsConfig` string options with RELATIVE `..` traversal escape the workspace root via
  `path.join` normalization and read out-of-roots parseable files into the build (live-verified).
- Delta: (a) SILENT read+write via a legitimate build (evades the restricted host AND process
  monitors); (b) STEERABLE — the tool description endorses run_target as the native interface;
  (c) FUTURE-REACH — for shell-less MCP clients this is the concrete arbitrary read+write primitive
  bypassing the restricted host entirely.
- Capped: standard shell-capable clients keep the R7 cap (agent has shell) — delta is stealth, not
  capability.
- Filing role: remediation-family context (the fix for the residual should also apply checkPath
  containment to run_target option values); NOT the core claim of this filing.

## 3. Armed-but-unconfirmed trigger (future-reach condition)

- Shell-less population REAL today (Claude Desktop / ChatGPT Desktop: documented local stdio MCP,
  no native shell tool for the model); run_target mechanics PROVEN (isReadOnly:false, options
  verbatim, traversal exfil — KP-M2RT); the ONLY boundary (restricted host) is bypassable via a
  single tool call.
- Closing branches: (a) in-lab harness demo with a real LLM agent following the steered
  instruction (H2 hop — scored MEDIUM-HIGH, self-assessment; BLIND-BRIEF + chain-run.log on file);
  (b) documented deployment evidence of a shell-less client with the angular-cli MCP server.
- **The C3 chain is explicitly NOT claimed in this filing** (repo content → priority-0.9
  instructions → steered run_target → out-of-roots exfil is DEMONSTRATED mechanically with real
  modules — E2-R3/C3B — but the agent-follow hop is scored, not demonstrated). It is filed as
  evidence/context only; a separate higher-severity filing is conditional on the trigger.

## 4. Delta-first opening (M2-FD draft, for the humanized report)

> Angular CLI's MCP server promises that every tool is confined to the roots the client declares.
> One tool — `get_best_practices` — validates only its input path and then lets Node's module
> resolution walk OUT of those roots to an ancestor node_modules. We built the server from the
> pinned source with all three upstream input fixes present, and the tool still returned a guide
> file from OUTSIDE the declared roots, byte-for-byte, into the assistant's context at priority
> 0.9. This is the sibling miss in a family fixed three times in six weeks: the input checks were
> patched, the resolved path was never re-checked. The impact is capped — the guide content must
> come from attacker-controlled package metadata (a dependency-confusion or vendored package) —
> but the boundary defect itself is deterministic and the injection channel is the assistant's
> own instruction context.

## 5. Evidence inventory

| Evidence | Path (findings/M2-.../evidence/) | What it proves |
|---|---|---|
| mcp-client4.mjs + mcp-client5.mjs | mcp-client4/5.mjs | Original PoC: built CLI + stdio JSON-RPC client, directory + file input forms, MARKER content returned byte-for-byte |
| workspace/ + hoisted-node_modules/ | workspace/, hoisted-node_modules/ | The fixture layout: declared root, attacker @angular/core at the parent with angular.bestPractices.path=guide.md |
| re-PoC at pin (compiled pin source) | repoc-pin/ (mcp-server.cjs, client2*.mjs, workspace/, node_modules/) | All three input fixes present at the pin; residual still returns MARKER-ATTACKER-GUIDE-2; out-of-roots negative rejected |
| run_target amplifier (live) | run-target-kp/ (kp-m2rt.mjs, driver.mjs, CORRECTION-NOTE.md, ws/, outside/secret.ts) | serializeOptions verbatim pass-through + relative-.. traversal exfil (content read) |
| C3 steering chain (mechanics live) | steering-demo/ (chain-run.log, client-steer.mjs, driver-steer.mjs, mcp-server.cjs, dist/, BLIND-BRIEF.md) | priority-0.9 content → steered run_target → out-of-roots exfil into the build artifact; INT2-VERDICT.md (H2 MEDIUM-HIGH, self-assessment) in payload-proposals/chain-demos/ |
| Reviews | reviews/ (8 files incl. review-adjudication.json) | adversarial refuter real-but-capped; kill-attempts + lane adjudications |
| Kernel attempts | attempt-m2-001-primary / -002-control(-ns) / -003-replay | attested real-path execution + negative control + replay |

## 6. Filing composition (operator's humanized re-authoring)

1. Core residual claim FIRST (mechanism + deterministic bypass + thrice-fixed-family sibling-miss;
   cite 34e1e0bb5/2b060630c/24fd8fce2 as the fix family).
2. run_target amplifier as remediation-family context (the fix must contain option values too).
3. C3 chain as explicit non-claim evidence (armed-but-unconfirmed; H2 scored MEDIUM-HIGH only).
4. Shell-less trigger as the future-reach condition for a SEPARATE higher-severity filing.
5. Remediation: re-check the resolved pkgJsonPath/guide realpath against roots; scope createRequire
   with paths: [workspace/node_modules]; audit doc-search fetch + projects.ts package.json walk-up.

## 7. Residual risks (honest)

- Shell-less chain (H2 agent-follow) NOT demonstrated in-lab — must not be claimed; scored only.
- Stable-release reach (v22.1.4) unverified in-lab — operator to confirm on the release branch
  (the M2 report marks this explicitly).
- A future fix sweeping the residual (i18n-inliner caching refactors touch the same family)
  argues for filing now.
- Config-trust doctrine (the foxllb-cluster rejection pattern) may be applied by triage — the
  counters are the deterministic boundary defect + the sibling-miss-in-a-thrice-fixed-family
  framing + the assistant-instruction injection sink.
