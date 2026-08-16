# hypotheses.md — angular-cli-2026-08

One row per hypothesis. A hypothesis is a claim that can be wrong; if it cannot be wrong it is a
mood, not a hypothesis.

| # | Hypothesis | Family | Disposition | Settled by |
|---|---|---|---|---|
| H1 | MCP `get_best_practices` reads/injects content from outside declared MCP roots via `createRequire` ancestor resolution (sibling gap of 34e1e0bb5) | MCP surface | **PROMOTED → findings/M2** (real-but-capped per R2-1) | orchestrator PoC 2026-08-14 |
| H2 | Builders delete directory contents outside the workspace root via unvalidated `outputPath` → `deleteOutputDir` (sibling gap of 8358805d3; application builder delete path included) | architect builder output | **PROMOTED → findings/M3** (confirmed-escalated) | orchestrator PoC 2026-08-14 |
| H3 | Schematics package-manager task spawns shell string with raw `packageName` (shell:true) — command-injection primitive | schematic tasks | **real-but-capped** (no first-party attacker-influence path; third-party schematic = by-design exec) | L5 hunter + orchestrator source trace |
| H4 | JSON schema registry fetches remote `$ref` URLs at validation time | workspace/schema | **capped** (only third-party schemas, by-design trust) | L7 hunter |
| H5 | JSON parser honors `__proto__` keys (per-instance prototype injection) — sink TBD | workspace/schema | **capped** (prototype-replace into getSchematicDefaults confirmed; input = self-authorized config) | R2-3 |
| H6 | SSR route matcher `decodeURIComponent` throws on malformed percent-encoding → 500 | @angular/ssr | **real-but-capped (Low)** (500-only; %C3 class; not stale — in v22.0.0) | R2-8 |
| H7 | Legacy win32 package-manager spawn uses weak quoting (quote-break chars) | package-managers | **real-but-capped** (win32 shell-string real; input = developer-invoked) | R2-5 |
| H8 | Release prereleaseCheck (dependency-ranges) skippable via env var | release path | **capped** (documented escape hatch; release-operator-only) | R2-7: real-but-capped |
| H9 | dev-infra.yml fork-triggered jobs with robot key lack explicit fork guard | CI | **wiring-clean** (no PR content checked out; robot key only to pinned base-repo actions — attribution dev-infra) | R2-6: wiring-clean; note: eslint cache key not ref-scoped (capped hardening) |
| H10 | `memory.ts`/visitor dead parent-collision check — protection gap | schema visitor | **capped** (staging inconsistency only; no boundary crossed) | R2-4 |
| H11 | `ng add` already-installed path runs the schematic without the confirmation/TTY gate (asymmetry) | ng add | **real-but-capped (low)** (scripted contexts; schematic = already-installed package's own code) | R3-1 + orchestrator source check |
| H12 | `ng update` migration collection resolution: `path.join(packagePath, collection)` honors `..` + `createRequire` parent-walk fallback | ng update | **real-but-capped** (package.json-controlled precondition = by-design exec) — **cascading note (E0-R3/E11):** main-flow `ng update` has NO validation on the collection field while the sibling `--migrate-only` flow VALIDATES (rejects absolute + `../`, cli.ts:340-355) — asymmetry; the escape is also live from the TARGET VERSION'S REGISTRY METADATA (update-resolver.ts:1050); surviving delta: scripts-suppressed CI / vendored node_modules where the collection is the first exec channel. Hardening: apply migrateOnly's validation to the main flow | R3-2 + E11 |
| H13 | MCP run_target watch-guard bypass via string-typed `watch` option → long-running watch build (agent-loop stall) | MCP run_target | **real-but-capped (low)** | R3-6 |
| H14 | Generator codegen injection: `dasherize` keeps quotes/backticks/`$()`/newlines; names land in generated code | schematics/angular generators | **capped for names** (class-name validation aborts) — **CONFIRMED for `--route`** (module generator interpolates raw, no schema pattern) → **PROMOTED findings/D1** (real-but-capped: input-trust) | R4-1 + deepsec + orchestrator + IR-D1 |
| H15 | `ng cache clean` force-deletes arbitrary directory via workspace `cli.cache.path` (absolute/`..`-escaped, no containment, no confirmation) | cache command | **PROMOTED → findings/D2** (real-command PoC; IR: missed-sibling discriminator) | deepsec + orchestrator + IR-D2 |
| H16 | assistant-to-the-branch-manager fork guard `github.event.repository.fork == false` ineffective on PR events (always base repo) | CI wiring | **PROMOTED → findings/D3** (real-but-capped: API-only action; merge gates downstream = dev-infra) | deepsec + orchestrator + IR-D3 |
| H17 | MCP run_target option VALUES unvalidated (output-path/file-replacements) → build reads/writes outside roots when agent is prompt-injected | MCP chain | **capped** (agentic amplification; chains with M2) | deepsec + R3-6 |
| H18 | doc-search redirect-follow/http-scheme/port checks bypassable on the includeTopContent fetch | MCP doc-search | **capped** (URL from Google-controlled Algolia index; defense-in-depth) | deepsec |
| | | | | |
