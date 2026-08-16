# winners.md — scrubbed, abstract, benign-objective patterns only

Append-only **evidence**, never self-edited belief. Store the *shape* of what worked, linked to
evidence ids — **never** verbatim payloads or stepwise harmful recipes. This file remains local;
models do not write Plane-1. Promotion requires a committed operator-reviewed `promote` disposition
and a later human-reviewed PR. Negative controls, refutations, reward-hacked proof shapes, and
environment failures are legitimate lessons; promotion is never forced.

## Format
- **pattern:** `<abstraction — the shape, not the phrasing>`
- **applies to:** `<surfaces>`
- **evidence:** `finding://...  attempt://...`
- **loses to:** `<defense observed>`
- **scope tag:** `benign-canary-only | defensive-validation-only | operator-review-required`

## Winners (2026-08-15, angular-cli-2026-08 closure)

1. **pattern:** a workflow gates a secret-bearing job with `github.event.repository.fork == false`, which is always true on PR-triggered events (the event's repository object is the base repo) — the guard is provably ineffective as written.
   **applies to:** CI workflow wiring on PR-triggered jobs with secrets; any repo using the `repository.fork` guard instead of `pull_request.head.repo.fork`.
   **evidence:** `finding://D3-branch-manager-fork-guard`
   **loses to:** the downstream action being API-only (never executes workspace content).
   **scope tag:** operator-review-required
2. **pattern:** a workspace-config path value resolves with `..`/absolute escapes and feeds force/recursive delete with no containment; the fix belongs at the shared base-path helper.
   **applies to:** config-to-destructive-fs flows (cache paths, output paths).
   **evidence:** `finding://D2-cache-clean-deletion`
   **loses to:** containment at the shared base-path helper; schema-pattern validation.
   **scope tag:** defensive-validation-only
3. **pattern:** a registry-response field flows unvalidated into a package-manager command arg reaching a shell string; the tag NAME is checked, the VALUE is not.
   **applies to:** registry-value-to-shell-arg plumbing.
   **evidence:** `finding://W1-yarn-classic-disttags-win32`
   **loses to:** semver validation of the value; array-form spawn.
   **scope tag:** defensive-validation-only
4. **pattern:** a mitigation exists but is keyed to the wrong field (explicit subPath guarded, key-derived defaults unguarded) — the discriminator is the mis-keyed guard itself.
   **applies to:** validation-placement audits; config-driven path handling.
   **evidence:** `finding://E1-C1-i18n-locale-key-escape`
   **loses to:** validating the derived default with the same check as the explicit field.
   **scope tag:** defensive-validation-only
5. **pattern:** case-sensitive path-equality guards fail on case-insensitive filesystems (a case-variant of the root bypasses the protection).
   **applies to:** filesystem-path guards; CI on macOS/Windows runners.
   **evidence:** `finding://M3-legacy-builder-outputpath-delete` (amplifier)
   **loses to:** case-folded, realpath-normalized comparison.
   **scope tag:** defensive-validation-only
6. **pattern:** command execution that fires from metadata fetch BEFORE any confirmation gate (the gate only guards a later phase).
   **applies to:** install/add/update flows with pre-gate fetches.
   **evidence:** `finding://W1-yarn-classic-disttags-win32` (ordering proof)
   **loses to:** validating the fetched value before interpolation.
   **scope tag:** defensive-validation-only
7. **pattern:** a sandbox/root-confined agentic tool is steered by protocol-flagged instruction content (an authority annotation) via tool-option values that hide the anomaly (the tool call looks clean).
   **applies to:** MCP/agent tool surfaces with free-form option values.
   **evidence:** `finding://M2-mcp-best-practices-roots-escape` (steering-demo, shape-B)
   **loses to:** option-key allowlists; containment on path-bearing values; agent tool-output-as-data policies.
   **scope tag:** operator-review-required
8. **pattern:** attacker-authored content reaching a production server bundle executes at BOOT via build-time inlining (venue changes the severity class from client-side to server-side).
   **applies to:** SSR/bundling pipelines with embed steps.
   **evidence:** `finding://E1-C1-i18n-locale-key-escape` (legacy-SSR venue)
   **loses to:** validating inputs at option normalization; not embedding unvalidated file content.
   **scope tag:** operator-review-required
9. **pattern:** an unvalidated option string written into generated code via raw interpolation (a schema pattern on the option would reject the payload at validation).
   **applies to:** codegen schematics; template interpolation of options.
   **evidence:** `finding://D1-route-codegen-injection`
   **loses to:** schema patterns; serialization instead of raw interpolation.
   **scope tag:** defensive-validation-only
10. **pattern:** a fork-PR-triggered CI job spawns a command that inherits the job env (tokens) — attacker-triggered command execution on CI is zero-interaction.
    **applies to:** CI workflows running package-manager commands on PR content.
    **evidence:** `finding://W1-yarn-classic-disttags-win32` (CI-token venue)
    **loses to:** array-form spawn; no shell strings; secret scoping.
    **scope tag:** operator-review-required
11. **pattern:** identical code duplicated across packages (byte-identical twins) means a fix in one copy leaves the other exploitable; the chokepoint is the shared helper.
    **applies to:** duplicated utilities across build/devkit trees.
    **evidence:** `finding://D2-cache-clean-deletion`, `finding://M3-legacy-builder-outputpath-delete` (twin copies)
    **loses to:** deduplication or fixing both copies.
    **scope tag:** defensive-validation-only
12. **pattern:** a config value that the CLI reads silently at every build (no confirmation, no output) makes deletion/write primitives fire automatically.
    **applies to:** workspace-config-driven destructive operations.
    **evidence:** `finding://D2-cache-clean-deletion` (purge on every default build)
    **loses to:** confirmation on non-default paths; default-scoped behavior.
    **scope tag:** defensive-validation-only

## Losers (refutations, killed claims, operational failures — 2026-08-15 closure)

1. **killed claim:** E1-C1 application-builder write escape (member A1) and SSR manifest import (member D) — the app builder re-contains via `isSubDirectory`; the build fails before the manifest import.
   **evidence:** `finding://E1-C1-i18n-locale-key-escape` (RV-C1-A refutation)
2. **killed claim:** D1 schematics-defaults amplifier — a precondition was already code-exec via npm lifecycle scripts (the amplification added no marginal capability).
   **evidence:** `finding://D1-route-codegen-injection` (KP-D1)
3. **killed claim:** the composite harness (chains combined in one run) as new security evidence — a marker false-positive (empty-secret tautology) was found; re-labeled capability-fusion artifact.
   **evidence:** rounds.md E2-D3 (DR3-03)
4. **killed claim:** generic prompt-injection framing for the MCP steering chain — agents resist generic injection; the surviving framing is the protocol-flagged authoritative channel.
   **evidence:** rounds.md E2-R3 (C3C)
5. **corrected claim:** D3 "dispatch per fork-PR event" — dispatch is merge-label-gated; the ungated channels are the labels/issue_labels jobs.
   **evidence:** `finding://D3-branch-manager-fork-guard` (E12 correction)
6. **corrected severity:** E1-C1 legacy-SSR 7.3 HIGH -> 6.3 Medium (honest preconditions AV:L + UI:R); W1 CI-venue 5.6 -> 8.1 HIGH (calculator).
   **evidence:** rounds.md E2-B2 (ECKP), E2-D3 (N6B)
7. **killed delivery:** E1-C1 committed-node_modules self-contained delivery — npm install prunes extraneous packages; only the malicious-dependency shape survives.
   **evidence:** findings/E1-C1/evidence/chain4/killpair-delivery/
8. **capped:** doc-search redirect, MCP glob-guard, SSR redirect family, architect builder resolution (V4), schema registry PP and $ref — all verified capped/refuted under adversarial review.
   **evidence:** rounds.md E1-R3 (A1-A8)
9. **operational failure (recurring):** silent `str.replace` no-op on report edits (anchor mismatch) — several QA fixes were "applied" but never landed; verified with grep after every edit since.
   **evidence:** rounds.md E1-R5/R6 QA records
10. **operational failure:** an event-emitter helper hardcoded to one engagement contaminated another engagement's ledger; parameterized after repair (operator-executed truncation).
    **evidence:** `legacy/quarantine/` byte-verified quarantine tails
11. **operational failure:** a 36-child parallel workflow crashed the async runner; the pattern split into 12-child workflows and ran reliably.
    **evidence:** rounds.md E2-B relaunch
12. **filing lesson:** F13 (dev-infra committed credentials) was filed and returned as a duplicate — the fix: delta-first framing + novelty statement with duplicate-risk ratings + prior-art citations in every report.
    **evidence:** payload-proposals/vrp/ (filing package)

## Promotion state

All entries above are the **proposed disposition** (operator executes `record-memory` with
`pattern-candidates-disposition.md` as the payload; PC-3 deferred to the dev-infra engagement).
Promotion to Plane-1 requires the operator-reviewed `promote` disposition + a human-reviewed PR.
