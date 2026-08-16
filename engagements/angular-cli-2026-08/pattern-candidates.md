# pattern-candidates.md — local, unpromoted observations

Capture repeated *shapes* you notice during this engagement that might generalize into a Plane-1
`skills/patterns/` card. This file is **engagement-local and append-only** — it is NOT a promotion.
Promotion is manual and scrubbed: candidate here → operator-reviewed `record-memory` disposition →
sanitized `casebooks/<id>/` PR → pattern card update. A `promote` disposition proposes that later PR;
it never writes Plane-1. `defer` and `no_novel_lesson` are equally valid terminal outcomes.

Keep entries abstract enough to survive scrubbing later: describe the shape, not the secret. Link
evidence by id (`finding://`, `attempt://`), never paste transcripts or live values.

## Format per candidate
- **observed shape:** the repeated thing (one sentence — the structure, not the payload)
- **seen on:** surfaces / endpoints (abstract)
- **evidence:** `finding://...  attempt://...`
- **why it may generalize:** what makes this bigger than this target
- **why it may NOT:** the honest counter — target-specific quirk? already covered by a card?
- **candidate destination:** existing pattern card to extend, or a proposed new `pattern.<id>`
- **lesson kind:** `positive | negative | refutation | reward_hacked_proof | environment_failure | mixed`
- **held counterexample (if any):** where the SAME class was enforced correctly here (strengthens the card)
- **sanitization:** target identifiers, credential values, and harmful recipes removed; evidence IDs retained
- **promotion status:** `local` → `proposed` → `promoted` / `dropped`

## Entries
## PC-9 — quote-wrap-without-escape on win32 shell strings (family: W1 + --registry + specifier wrappers)
- **observed shape:** a value is wrapped in double quotes before joining into a win32 shell string, but embedded quotes are NOT escaped — any `"` in the value closes the wrapper and the remainder executes on cmd.exe; URL.canParse accepts `"`/`&` in query strings, so URL-validated inputs carry the breakout
- **seen on:** angular-cli W1 (getRegistryManifest specifier, 85e3ce2e0), schematics package-manager task `--registry="…"` (executor.ts:115-117), package-manager host win32 spawn (host.ts:157-164)
- **evidence:** `finding://W1-yarn-classic-disttags-win32`, cascading R7-L5 note
- **why it may generalize:** every cross-platform tool that shell-joins args on win32 has this class; the fix pattern (array spawn, shell:false) is well-known and repeatedly missed
- **why it may NOT:** the reachable values are mostly developer-invoked (only W1's dist-tags path is registry-controlled)
- **candidate destination:** extend `skills/patterns/command-construction` (new `pattern.win32-quote-wrap-escape`)
- **lesson kind:** positive
- **held counterexample:** POSIX array-spawn; npa/semver filters on sibling paths
- **sanitization:** n/a
- **promotion status:** local
## PC-7 — registry-controlled VALUES interpolated into shell/exec args unvalidated
- **observed shape:** a registry response field (dist-tags value, version string) flows into a package-manager command arg with no semver/charset validation; the arg reaches a shell string on win32
- **seen on:** angular-cli W1 (yarn-classic getManifest tag path); the quoting fix (85e3ce2e0) wrapped but didn't escape
- **evidence:** `finding://W1-yarn-classic-disttags-win32`
- **why it may generalize:** every package-manager wrapper that builds specifiers from registry metadata has this class; quote-wrappers without escaping are a recurring false-fix
- **why it may NOT:** npm/yarn-modern descriptors skip the value path; POSIX array-spawn is safe
- **candidate destination:** new `pattern.registry-value-to-shell-arg` (command-construction family)
- **lesson kind:** positive
- **held counterexample:** npa.resolve + semver.lte throw on the malicious version in sibling paths
- **sanitization:** n/a
- **promotion status:** local

## PC-8 — validation asymmetry between main flow and a sibling flow (migrateOnly vs plain update)
- **observed shape:** one invocation path validates a dangerous field; the sibling path (same command, different flag) skips the validation entirely
- **seen on:** angular-cli ng update main flow vs --migrate-only (cli.ts:657 vs :340-355)
- **evidence:** `hypothesis://H12` (cascading note E11)
- **why it may generalize:** validation added for the CI-popular path leaves the interactive path open — the reverse of the usual asymmetry
- **why it may NOT:** the cap (install-exec) mostly neutralizes it
- **candidate destination:** new `pattern.flag-path-validation-asymmetry`
- **lesson kind:** positive
- **held counterexample:** migrateOnly validation is the positive control
- **sanitization:** n/a
- **promotion status:** local
## PC-4 — fork guard using `github.event.repository.fork` on PR-triggered workflows
- **observed shape:** a workflow gates a secret-bearing job with `github.event.repository.fork == false`, which is always true on pull_request/pull_request_target events (event.repository = base repo)
- **seen on:** angular-cli assistant-to-the-branch-manager.yml (D3); the pattern is common in the wild
- **evidence:** `finding://D3-branch-manager-fork-guard`
- **why it may generalize:** the correct expression (`pull_request.head.repo.fork`) is a known-but-frequently-missed gotcha; any PR-triggered workflow with this guard has an ineffective control
- **why it may NOT:** in many repos the action itself is API-only (like the branch-manager here) so the impact stays cosmetic
- **candidate destination:** new `pattern.fork-guard-event-repository` or CI checklist
- **lesson kind:** positive
- **held counterexample:** the action never executes workspace content
- **sanitization:** n/a
- **promotion status:** local

## PC-5 — template interpolation of options into generated source without escaping
- **observed shape:** a schematic interpolates a user/workspace option into a string literal in generated code with no validation or escaping; the string context (quotes) is the injection boundary
- **seen on:** angular-cli module `--route` (D1); the 59e5e967a fix family
- **evidence:** `finding://D1-route-codegen-injection`
- **why it may generalize:** every codegen tool with user-input options has this class; one-fix-per-sink audits miss siblings (the name path is validated, the route path is not)
- **why it may NOT:** requires attacker-influenced generation args (workspace schematics defaults in angular.json is the strongest channel)
- **candidate destination:** extend `skills/patterns/client-supplied-selector-authz` or new codegen card
- **lesson kind:** positive
- **held counterexample:** validateClassName on the component generator
- **sanitization:** n/a
- **promotion status:** local

## PC-6 — workspace-config path values reaching destructive fs ops with no containment
- **observed shape:** a config field (outputPath / cache.path) resolves against the workspace root, `..`/absolute values escape, and the value feeds rm/delete with force/recursive and no confirmation
- **seen on:** angular-cli M3 (builders) + D2 (cache clean) — the SAME family in two utilities
- **evidence:** `finding://M3-legacy-builder-outputpath-delete`, `finding://D2-cache-clean-deletion`
- **why it may generalize:** config→destructive-ops paths are everywhere in dev tooling; fixes land on one sink (8358805d3) while siblings remain
- **why it may NOT:** the config is developer-owned in the standard trust model (the malicious-project scenario is the real reach)
- **candidate destination:** new `pattern.config-sink-containment` (or extend path-traversal card)
- **lesson kind:** positive
- **held counterexample:** deleteOutputDir root-equality guard + application-builder write-path isSubDirectory
- **sanitization:** n/a
- **promotion status:** local
## PC-1 — root-confinement validated on INPUT, then module-resolution escapes the boundary
- **observed shape:** a tool validates a caller-supplied path against a sandbox root, then lets `createRequire`/module resolution walk ANCESTOR node_modules (or follows symlinks) and performs a raw fs read on the RESOLVED path without re-checking it
- **seen on:** angular-cli MCP `get_best_practices` (M2); same family as angular/dev-infra symlink/realpath asymmetries
- **evidence:** `finding://M2-mcp-best-practices-roots-escape` (attempts pending kernel)
- **why it may generalize:** every agentic-tooling surface with roots/sandbox promises (MCP servers, linters, language servers) parses package metadata; resolution asymmetries are structural
- **why it may NOT:** requires an ancestor-hoist layout + attacker-influenceable metadata; the input check usually blocks the obvious path
- **candidate destination:** extend `skills/patterns/client-supplied-selector-authz` or new `pattern.root-check-on-resolved-path`
- **lesson kind:** positive (new control bypass shape)
- **held counterexample:** `isAllowedWorkspacePath` on the input + host `checkPath` on host-mediated reads
- **sanitization:** target identifiers kept abstract; marker values removed
- **promotion status:** local

## PC-2 — fix lands on the flagship path; deprecated siblings keep the hole
- **observed shape:** a containment fix is scoped to the NEW implementation while deprecated-but-shipped siblings (same shared utility!) are untouched
- **seen on:** angular-cli 8358805d3 (application builder output validation) vs legacy webpack browser/server builders (M3)
- **evidence:** `finding://M3-legacy-builder-outputpath-delete`
- **why it may generalize:** deprecation = less review attention; shared utilities make the divergence subtle
- **why it may NOT:** legacy paths are eventually removed; triagers often accept "deprecated" as a fix
- **candidate destination:** new `pattern.fix-scope-sibling-audit`
- **lesson kind:** positive
- **held counterexample:** repo-init executor converted alongside (f1ed0257a did cover siblings there)
- **sanitization:** n/a
- **promotion status:** local

## PC-3 — encrypted credentials committed with the key material (obfuscation-as-security)
- **observed shape:** a symmetric blob (ciphertext + auth tag) shipped in a constants module alongside the hardcoded key derivation and fixed IV — anyone with the repository alone can decrypt; the obfuscation provides no secrecy, only the illusion of one
- **seen on:** a CLI docs-search integration (decrypts to a search-only API key — zero marginal secrecy, theater); a CI/automation repository's committed GCP-service-account + browser-testing credentials (real secrets, high value)
- **evidence:** `finding://F13-committed-decryptable-credentials` (high-value instance), observation (low-value instance, same shape)
- **why it may generalize:** the shape recurs within the same org's codebases; the VALUE of any instance is unknowable from the shape alone — every instance must be triaged by value, never assumed theater
- **why it may NOT:** client-side-obfuscated keys that are public by design carry no harm (the low-value instance); the harm concentrates in instances hiding real credentials
- **candidate destination:** extend the Plane-1 credentials/secret-detection card with a decryptable-blob pattern
- **lesson kind:** mixed (positive detection shape proven by the high-value instance; value-triage caution proven by the low-value instance)
- **held counterexample:** the low-value instance — a search-only key decryptable from public material — where the pattern exists but the marginal secrecy is zero; it bounds the class to value-triaged instances
- **sanitization:** key values, identifiers, and decryptable fragments removed (the evidence refs carry the sanitized records)
- **promotion status:** proposed (ready for record-memory)
- (none yet)
