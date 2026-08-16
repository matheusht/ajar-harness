# MEMORY-DISPOSITION PAYLOAD — angular-cli-2026-08 (deep phase E1, prepared 2026-08-15)
# Operator runs: `record-memory` (operator authority required — see §4). Agent-side prep complete; nothing below is a model write.

Source scrubs: `pattern-candidates-scrubbed.md` (PC-4..9), R11 lane outputs (PC-1..3), deep-phase lane L11b (PC-10..12).
All evidence refs verified to resolve under the angular-cli reference index EXCEPT PC-3 (see §2).

---

## §1 — ORDERED DISPOSITION LIST (per L11a recommendation)

1. **PC-4**
   - **pattern:** a workflow gates a secret-bearing job with `github.event.repository.fork == false`, which is always true on pull-request-triggered events (the event's repository object is the base repo, never a fork) — the guard is provably ineffective as written
   - **applies to:** CI workflow wiring on PR-triggered jobs with secrets; any repo using the `repository.fork` guard instead of `pull_request.head.repo.fork`
   - **evidence:** `finding://D3-branch-manager-fork-guard`
   - **loses to:** the downstream action being API-only (never executes workspace content) — the control-integrity defect stands even when the impact is capped
   - **scope tag:** operator-review-required
   - **lesson kind:** positive

2. **PC-6**
   - **pattern:** a workspace-config path value resolves with `..`/absolute escapes and feeds force/recursive delete with no containment/confirmation; the fix belongs at the shared base-path helper
   - **applies to:** config→destructive-fs flows (cache paths, output paths); any uncontained config value reaching rm/delete
   - **evidence:** `finding://D2-cache-clean-deletion`
   - **loses to:** containment at the shared base-path helper (the chokepoint); schema-pattern validation on the value
   - **scope tag:** defensive-validation-only
   - **lesson kind:** positive

3. **PC-7**
   - **pattern:** a registry-response field flows unvalidated into a package-manager command arg reaching a shell string; the tag NAME is checked, the VALUE (dist-tags) is not
   - **applies to:** registry-value-to-shell-arg plumbing; any metadata field interpolated into command construction
   - **evidence:** `finding://W1-yarn-classic-disttags-win32`
   - **loses to:** value validation (semver/charset) at the source; array-spawn with shell:false on win32
   - **scope tag:** defensive-validation-only
   - **lesson kind:** positive

4. **PC-9**
   - **pattern:** a value is wrapped in double quotes before being joined into a win32 shell string, but embedded quotes are NOT escaped — any quote in the value closes the wrapper and the remainder executes on cmd.exe; URL validation accepts quotes/ampersands in query strings, so URL-validated inputs can carry the breakout
   - **applies to:** cross-platform tooling that shell-joins arguments on win32; quote-wrappers without escaping are the recurring false-fix
   - **evidence:** `finding://W1-yarn-classic-disttags-win32` (same family; cascading R7-L5 note)
   - **loses to:** POSIX array-spawn (safe) and semver/name filters on sibling paths — the reachable values are mostly developer-invoked (one registry-controlled path is the W1 instance)
   - **scope tag:** defensive-validation-only
   - **lesson kind:** positive

5. **PC-1**
   - **pattern:** a root/sandbox-confined tool validates a caller-supplied path against its declared allowed roots, then performs an unmediated module-resolution walk (ancestor `node_modules`) or symlink-following read on a path derived from that input — the *resolved* path is never re-checked, so the read lands outside the declared boundary even though the input check passed
   - **applies to:** agentic tooling, language servers, linters, and package-metadata readers that promise root confinement (declared roots/workspace sandboxes) but resolve modules or follow symlinks with raw filesystem access
   - **evidence:** `finding://M2-mcp-best-practices-roots-escape` (primary/control/replay attempts recorded in the kernel; promoted with gates G0-G6 clear)
   - **loses to:** realpath containment on the post-resolution target; host-mediated reads routed through the sandbox object; input validation that blocks the obvious direct path (ancestor-hoist + attacker-influenceable-metadata precondition narrows reach)
   - **scope tag:** defensive-validation-only
   - **lesson kind:** positive
   - **correction applied in scrub:** the source entry's "(attempts pending kernel)" is stale — evidence attempts ARE recorded (4 refs on `attempt-m2-001-primary`)

6. **PC-2**
   - **pattern:** a containment/validation fix lands on the flagship path while deprecated-but-shipped siblings — or a duplicated copy of the same logic — keep the hole; the divergence stays subtle precisely because the shared utility or duplicated helper is what both paths trust
   - **applies to:** build/package-manager tooling where a path-bearing config value feeds destructive fs ops (delete/rm) or shell args; fix-hygiene audit of every security fix
   - **evidence:** `finding://M3-legacy-builder-outputpath-delete`, `finding://D2-cache-clean-deletion`
   - **loses to:** a fix that audited siblings in the same change (the repo-init executor was converted to array-spawn alongside the command-injection fix — the counterexample proving the class is auditable)
   - **scope tag:** defensive-validation-only
   - **lesson kind:** positive
   - **operator note:** the R11 widening (duplicated-helper divergence, two byte-identical `getCacheBasePath` copies) merits confirming whether a new card or an extension of an existing path-traversal card

7. **PC-5**
   - **pattern:** a code generator interpolates a user/workspace option into a string literal in generated source with no validation or escaping — the string context (quote characters) is the injection boundary; the same-class sink is validated on one path and not another
   - **applies to:** codegen/schematic tooling that emits source from options; any generator with unvalidated option → string-literal sinks
   - **evidence:** `finding://D1-route-codegen-injection`
   - **loses to:** class-name validation on the sibling path (identifier regex aborts generation); the config-default amplification channel is marginal under the attacker-authored-project precondition
   - **scope tag:** defensive-validation-only
   - **lesson kind:** positive
   - **caveat carried from the kill-pair:** the original demo payload was compile-invalid; the comma-exec corrected payload is the verified instance

8. **PC-8**
   - **pattern:** validation added for the CI-popular invocation path (same command, different flag) rarely propagates to the sibling flag path sharing one resolver — the CI-popular path is protected, the interactive path is not
   - **applies to:** CLI commands with flag-selected execution modes sharing one resolution routine; validation added for one mode rarely propagates to the sibling
   - **evidence:** `hypothesis://H12` (cascading note E11)
   - **loses to:** the vulnerable path's precondition (installed-package control) is largely code-exec-equivalent — a real hardening gap, low severity delta
   - **scope tag:** defensive-validation-only
   - **lesson kind:** positive

9. **PC-10** (deep phase)
   - **pattern:** a filesystem-path guard compares the resolved path against a protected root with a plain string-equality test (`resolved === root`); on case-insensitive filesystems (macOS default APFS, Windows NTFS) a case-variant of the root passes the string test and the filesystem resolves it to the real directory — the guard's only protected case is silently defeated
   - **applies to:** any containment guard that uses `resolve(...) === root` (or prefix/startsWith checks) without canonicalizing case; delete/write primitives with a "never touch the root" exception; CI runners on case-insensitive filesystems make it reachable in automation
   - **evidence:** `finding://M3-legacy-builder-outputpath-delete` (deep-phase amplifier, E1-R1; compiled-production-code PoC: control throws on the exact root, case-variant deletes the root's contents; `path.resolve` preserves input case on both darwin and win32 — demonstrated)
   - **loses to:** on case-sensitive filesystems (Linux) the variant path fails resolution and the operation returns early (no impact); the value channel still requires the config-controlled precondition of the parent finding (no new trust boundary — the bypass only removes the guard's protection)
   - **scope tag:** defensive-validation-only
   - **lesson kind:** containment-bypass (a control exists, is bypassable via filesystem case semantics — not an absent guard)

10. **PC-11** (deep phase)
    - **pattern:** validation is keyed to the wrong field: an explicit option field is validated (regex/pattern guard), while the SAME value arriving through a sibling channel — a map key or a string-form alias that becomes the default for the guarded field — bypasses the guard entirely; the schema-level pattern is present but never enforced on the execution path
    - **applies to:** option-normalization code where a validated field has a key-derived or alias-derived default; configuration maps (locale keys, strategy names, profile names) whose keys flow into paths/identifiers; the discriminator is a live test: the explicit field throws, the key channel silently passes
    - **evidence:** `finding://E1-C1-i18n-locale-key-escape` (unproven candidate at time of scrub; deep phase E1-C1; live mechanism proof: explicit subPath with a malicious value throws the validation error, the same value as a locale key is accepted and reaches mkdir/write + module resolution)
    - **loses to:** the value still requires the config-controlled (cloned-repo/supply-chain) precondition; schema patterns exist but are unenforced — the defect is a validation-placement gap with a one-point fix (validate at the merge/default point, not per-field)
    - **scope tag:** defensive-validation-only
    - **lesson kind:** validation-placement (an existing mitigation is bypassed by sibling placement — distinct from an absent mitigation)
    - **prefix note:** evidence ref uses the candidate prefix because the finding was still in `unproven/` at scrub time (E1-C1 was promoted later the same day — operator may re-point to `finding://E1-C1-...`; pattern promotion is independent of the finding's promotion)

11. **PC-12** (deep phase)
    - **pattern:** a metadata fetch executes BEFORE the user-confirmation gate of an install/update flow, and the fetched metadata value is interpolated into a command that runs during the fetch — the confirmation prompt (or a later validation abort) masks the already-executed injection rather than preventing it; "the abort fires after the payload" is the recurring shape
    - **applies to:** package-manager/installer flows that fetch registry metadata ahead of confirmation; any flow where a validation failure later in the task list hides an earlier side-effect; automated/CI invocations of such flows (no TTY) widen the reach
    - **evidence:** `finding://W1-yarn-classic-disttags-win32` (deep-phase amplifiers, E1-R2/X3: order proof — the resolve loop with the spawn executes before the semver check that throws; no confirmation gate exists in the update flow; packageGroup spread multiplies the spawns)
    - **loses to:** the injected value still requires registry control + the platform-specific shell path + the specific descriptor (same trust boundary as the parent finding); POSIX array-spawn and sibling descriptors are safe — the ordering defect is the amplifier, not the root cause
    - **scope tag:** defensive-validation-only
    - **lesson kind:** ordering (side-effects precede gates — the fix is to move validation/fetch AFTER confirmation or validate the value before any command construction)

12. **PC-3** — ⚠️ **DEFER in this engagement** (see §2)
    - **pattern:** a symmetric encrypted blob (ciphertext + auth tag) shipped in a constants module alongside its hardcoded key derivation and fixed IV — decryptable by anyone with the repository alone; the obfuscation provides no secrecy, only the illusion of one
    - **applies to:** credential/secret storage in client-side tooling and CI/automation repositories (constants modules, config blobs)
    - **evidence:** `finding://F13-committed-decryptable-credentials` (high-value instance — real GCP SA + browser-testing credentials); observation (low-value instance — a search-only API key, same shape, in the CLI docs-search integration)
    - **loses to:** the low-value instance itself — a search-only key decryptable from public material, where the pattern exists but the marginal secrecy is zero; it bounds the class to value-triaged instances (never assume theater, never assume value — triage each instance)
    - **scope tag:** operator-review-required
    - **lesson kind:** mixed (positive detection shape proven by the high-value instance; value-triage caution proven by the low-value instance)

---

## §2 — PC-3 DISPOSITION NOTE (blocker)

- **Blocked in this engagement:** `finding://F13-committed-decryptable-credentials` does NOT resolve under angular-cli-2026-08's reference index — F13 lives in `angular-dev-infra-2026-08/findings/` (cross-engagement). `record-memory` runs per-engagement; a disposition carrying an unresolvable ref fails reference validation.
- **Operator decision required (two options):**
  - **(a) Record PC-3 under `angular-dev-infra-2026-08`** where F13 lives (recommended — the pattern's high-value instance is a dev-infra finding; the angular-cli low-value instance (doc-search Algolia key, hardening note H10/A2c) can be cited as the second instance in the dev-infra disposition or as a separate observation-scoped entry), or
  - **(b) Re-scope PC-3's angular-cli evidence** to the doc-search Algolia observation (hardening note A2c — no `finding://` ref; would need an observation-ref form the disposition schema accepts — verify against `schemas/` before use).
- Until decided: PC-3 stays local; 11 of 12 candidates are disposition-ready in this engagement.

## §3 — PC-1 minor correction (pre-write)

- The source `pattern-candidates.md` entry still says "(attempts pending kernel)" — stale. The scrubbed text (this payload) carries the correction; if the operator's record-memory reads the SOURCE file, apply the one-line fix first (evidence attempts ARE recorded: `attempt-m2-001-primary`, 4 refs in the kernel ledger).

## §4 — RECORD-MEMORY COMMAND HINT (operator-only)




## N-phase additions (2026-08-15) — PC-18..PC-20

## §1b — NEXT-PHASE CANDIDATES (N-phase scrub, 2026-08-15)

13. **PC-18** (next phase; chainstorm C3)
    - **pattern:** a sandbox/root-confined agentic tool is steered by protocol-flagged instruction content (an authority annotation like priority 0.9 + audience:assistant) that arrives via a legitimate-looking channel, and the harmful option value is hidden so the anomaly NEVER appears in the tool call (e.g. the traversal rides inside a repo setup — a symlinked build entry — rather than as a visible dot-dot argument) — a hardened agent that refuses visibly anomalous directives follows the clean-looking call; refusal behavior splits on option-value plausibility, not on the injection channel
    - **applies to:** MCP/agent tool surfaces where client-supplied option values pass to privileged operations (run_target-style builders); any agent boundary where tool-output-as-data hardening (OWASP MCP-01) is bypassed by hiding the payload behind a legitimate-looking repository state; the shell-less-client case (no native shell tool) is where this becomes a capability, not just stealth
    - **evidence:** `finding://M2-mcp-best-practices-roots-escape` (evidence/steering-demo/shape-B/ — N4C: unprepared real agent FOLLOWED the symlink-hidden traversal; run_target argv clean; exfil complete; the visible-anomaly shape was REFUSED in N1C); M2 REPORT "N4C CLOSING BRANCH" + "Promotion trigger (N2F refined)"; the disclosed class = #32766 (severity6, OWASP MCP-01, closed won't-fix 2026-03-16) — the STEALTH SHAPE combination is undisclosed
    - **loses to:** the standard shell-capable client retains the R7 cap (stealth/steerability, not new capability); the payload still requires the attacker-authored repo + the agent being steered + a build step that embeds the exfil; visible-anomaly directives are refused — the hiding mechanism (repo symlink/layout) is the load-bearing part
    - **scope tag:** operator-review-required
    - **lesson kind:** evasion (authority-flagged content + hidden-in-layout payloads defeat tool-output hardening)

14. **PC-19** (next phase; chainstorm C4 / E1-C1)
    - **pattern:** build-time "embedding" of a config/registry-derived value into an output bundle is NOT inert: the embedded content executes at MODULE EVALUATION in the server process (boot-time, once per process, persistent) when the bundle is the SSR server bundle — a build-time file-read primitive becomes server-side code execution in the deployed app, and the execution timing is boot-time (not per-request), which changes both the severity class and the detection surface (no per-request trigger to observe)
    - **applies to:** i18n/localization inlining, bundle prepends, any build step that reads a config-controlled file into the server bundle (legacy webpack stack; the application/esbuild builder contains the write path and is NOT affected); localize/SSR pipelines that consume workspace-controlled paths
    - **evidence:** `finding://E1-C1-i18n-locale-key-escape` (evidence/chain4/ssr-e2e-real/ — N1D E2E through the real i18n-inlining pipeline: attacker locale content executes at server boot; benign negative clean; venue-split severity 6.3 Medium with the honest AV:L/AC:H/UI:R vector; boot-time precision in the REPORT Mechanism + Impact sections)
    - **loses to:** the config-trust precondition (attacker-controlled file/package reachable via the unvalidated locale key) + the legacy-stack-only bound + the Babel-parseable read bound (binary targets abort the build); CSP/strict deployments bound the sibling member F
    - **scope tag:** defensive-validation-only
    - **lesson kind:** venue (build-time embed → runtime server execution; execution timing = module-eval, not request-time)

15. **PC-20** (next phase; E1-C1 member F)
    - **pattern:** a config string option is written into a generated HTML document through a raw-emit path (no escaping), while a sibling path through the SAME builder escapes/validates the same value — a malicious value (e.g. baseHref) breaks out of the attribute and injects a literal `<script>` into the PRODUCTION page; the fix discriminator is the raw-emit site vs the update-attribute site, and execution is CSP-conditional (inline scripts run in default static deployments, strict-CSP deployments are immune)
    - **applies to:** HTML-generation in build tooling (index.html generation, template emitters) where option values are interpolated raw; any emitRaw-style sink with an escaping sibling — the divergence is the recurring shape (same class as the false-fix quote-wrap and the flagship-vs-sibling containment misses)
    - **evidence:** `finding://E1-C1-i18n-locale-key-escape` (evidence/chain4/member-f/ + payload-proposals/next-phase-demos/nr2-mf/ — N2C kill-pair: raw quote-breakout + literal script tag FIRST in the head; benign control clean; parse5 zero errors; discriminator emitRaw (head) vs updateAttribute (base-tag); schema.json:401-404 unpatterned; unfixed at main, DR3-04/N1H)
    - **loses to:** config-trust doctrine (the foxllb #33073/#33074/#33076 rejection pattern applies at filing) + CSP-conditional execution + the baseHref value being dev/workspace-controlled (cloned-repo precondition)
    - **scope tag:** defensive-validation-only
    - **lesson kind:** divergence (raw-emit sibling of an escaping path; fix at the schema or the emitRaw site)

