# pattern-candidates — SCRUBBED set (PC-4..PC-9), ready for operator `record-memory` review

Source: `pattern-candidates.md` (engagement-local, append-only). This file is the scrubbed,
sanitized view: shapes only — no target identifiers, no payloads, no harmful recipes. Evidence is
referenced by id only. Promotion is a manual, operator-reviewed `record-memory` disposition →
sanitized `casebooks/<id>/` PR → card update. `defer` and `no_novel_lesson` are equally valid
terminal outcomes.

Scope tag meanings (per `memory/winners.md`):
- `benign-canary-only` — proven only against synthetic canaries
- `defensive-validation-only` — proven as a control-bypass/validation-gap shape on a defended surface
- `operator-review-required` — involves platform/workflow semantics or wiring where a human must confirm the framing

---

## SCRUBBED-CANDIDATE PC-4

- **pattern:** a workflow gates a secret-bearing job with `github.event.repository.fork == false`,
  which is always true on pull-request-triggered events (the event's repository object is the base
  repo, never a fork) — the guard is provably ineffective as written
- **applies to:** CI workflow wiring on PR-triggered jobs with secrets; any repo using the
  `repository.fork` guard instead of `pull_request.head.repo.fork`
- **evidence:** `finding://D3-branch-manager-fork-guard`
- **loses to:** the downstream action being API-only (never executes workspace content) — the
  control-integrity defect stands even when the impact is capped
- **scope tag:** operator-review-required
- **lesson kind:** positive
- **promotion status:** proposed (ready for record-memory) — shape verified against the pinned
  workflow + event semantics; the correct-expression discriminator is documented in the finding

## SCRUBBED-CANDIDATE PC-5

- **pattern:** a code generator interpolates a user/workspace option into a string literal in
  generated source with no validation or escaping — the string context (quote characters) is the
  injection boundary; the same-class sink is validated on one path and not another
- **applies to:** codegen/schematic tooling that emits source from options; any generator with
  unvalidated option → string-literal sinks
- **evidence:** `finding://D1-route-codegen-injection`
- **loses to:** class-name validation on the sibling path (identifier regex aborts generation);
  the config-default amplification channel is marginal under the attacker-authored-project
  precondition (install-time script execution is already code-exec-equivalent)
- **scope tag:** defensive-validation-only
- **lesson kind:** positive — with an honest note: the as-demonstrated breakout payload required a
  compile-valid correction (the comma-exec shape); the class is real, the demo needed fixing
- **promotion status:** proposed (ready for record-memory)

## SCRUBBED-CANDIDATE PC-6

- **pattern:** a workspace-config path value resolves against the workspace root with `..`/absolute
  escapes allowed, then feeds a destructive filesystem op (force/recursive delete) with no
  containment check and no confirmation
- **applies to:** developer-tooling surfaces where config fields reach rm/delete sinks; build
  output paths and cache paths are the recurring instances
- **evidence:** `finding://M3-legacy-builder-outputpath-delete`, `finding://D2-cache-clean-deletion`
- **loses to:** the root-equality guard + write-path containment present in one sibling (the
  discriminator proving the unguarded sink is the missed member)
- **scope tag:** defensive-validation-only
- **lesson kind:** positive
- **promotion status:** proposed (ready for record-memory) — family sweep confirms the shared
  chokepoint (one base-path helper) is the fix target

## SCRUBBED-CANDIDATE PC-7

- **pattern:** a registry-response field (a dist-tag or version value) flows into a
  package-manager command argument with no semver/charset validation, and the argument reaches a
  shell string on one platform
- **applies to:** package-manager wrapper code that builds specifiers from registry metadata; the
  value-interpolation site vs the tag-name passthrough site is the discriminator
- **evidence:** `finding://W1-yarn-classic-disttags-win32`
- **loses to:** sibling descriptors skip the value path (tag name passes through) and POSIX
  array-spawn is safe — the vulnerable descriptor is the only member taking the registry VALUE
- **scope tag:** defensive-validation-only
- **lesson kind:** positive
- **promotion status:** proposed (ready for record-memory) — a quoting fix wrapped the specifier
  without escaping embedded quotes (a false-fix shape worth recording)

## SCRUBBED-CANDIDATE PC-8

- **pattern:** one invocation path of a command validates a dangerous field while a sibling path
  (same command, different flag) skips the validation entirely — the CI-popular path is protected,
  the interactive path is not
- **applies to:** CLI commands with flag-selected execution modes sharing one resolution routine;
  validation added for one mode rarely propagates to the sibling
- **evidence:** `hypothesis://H12` (cascading note E11)
- **loses to:** the vulnerable path's precondition (installed-package control) is largely
  code-exec-equivalent — a real hardening gap, low severity delta
- **scope tag:** defensive-validation-only
- **lesson kind:** positive
- **promotion status:** proposed (ready for record-memory) — the asymmetry is verified at source
  with the validated sibling as the positive control

## SCRUBBED-CANDIDATE PC-9

- **pattern:** a value is wrapped in double quotes before being joined into a win32 shell string,
  but embedded quotes are NOT escaped — any quote in the value closes the wrapper and the remainder
  executes on cmd.exe; URL validation accepts quotes/ampersands in query strings, so URL-validated
  inputs can carry the breakout
- **applies to:** cross-platform tooling that shell-joins arguments on win32; quote-wrappers
  without escaping are the recurring false-fix
- **evidence:** `finding://W1-yarn-classic-disttags-win32` (same family; cascading R7-L5 note)
- **loses to:** POSIX array-spawn (safe) and semver/name filters on sibling paths — the reachable
  values are mostly developer-invoked (one registry-controlled path is the W1 instance)
- **scope tag:** defensive-validation-only
- **lesson kind:** positive
- **promotion status:** proposed (ready for record-memory) — family note: URL validation accepts
  the breakout characters, so "validated" inputs still close the quote wrapper

---

## Notes for the operator's record-memory review

- All six evidence refs verified to resolve (`findings/` present for D1/D2/D3/M3/W1; `H12` settled
  in hypotheses.md with the cascading note).
- Lesson kinds are honest to the cascading adjudications: PC-5 carries the kill-pair caveat
  (config-default channel marginal; demo payload required a compile-valid correction); PC-4 carries
  the API-only cap; PC-8 carries the install-exec cap.
- Sanitization: no payload strings, no registry values, no target-specific identifiers beyond the
  evidence IDs. Harmful recipes (quote-breakout payloads, dist-tag injection values) removed.
- PC-1..PC-3 are outside this scrub set (Phase-1 candidates); if the operator wants them reviewed
  in the same disposition, request a second pass.
