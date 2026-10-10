# engine/gates.md — human-in-the-loop gates

The harness runs autonomously *between* gates; the human supplies steering + authorization *at*
them. The agents supply tireless execution, validation, and bookkeeping.

## 1. Scope gate (blocking)
`engagements/<target>/scope.md` must be **filled and signed** before the loop runs: surfaces, the
benign safe-objective set, the escalation ceiling, **impact-demo authorization (y/n)**, accounts/
fixtures, operator sign-off. **No scope file, no run.**

## 2. Environment fidelity and safety preflight
`preflight` is a **Notebook** collection operation. The broker records exact source/runtime identity,
non-executed reproduction argv, cleanup state, automated secret-shape coverage, and truthful local
principal/session provenance. It cannot claim operator redaction or authorization. A complete,
credential-free, stable `clear_local` collection may activate automatically. `blocked` does not.
`needs_review` remains inactive until `review-preflight` applies a separate immutable operator review
through an exact digest-bound authority request. Only the newest pending preflight may be reviewed;
the collector record is never rewritten. Review does not authorize Zone-2.

Git collection uses a pinned executable, sanitized configuration, repeated FD-bound identity and
tracked/untracked/ignored secret scans. Package/local target and selected configuration bytes are
identity-bound across scanning. Only secret classes and hashes are retained, never secret values.
A clean shape scan is not proof that no secret exists.

The advisory Zone is only `clear_local`, `review_required`, or `unknown`; it is never authorization.
A Zone-2 artifact requires either fresh signed-operator confirmation (one future artifact id,
planned byte digest/size/path, active environment and scope, open cleanup, at most 30 minutes) or
a versioned `local_only_v1` standing grant in the current signed scope. The standing path still
binds planned bytes/path, current scope/environment, and an open cleanup obligation. The kernel
rechecks bindings under lock immediately before exclusive creation.
For a v2 signed standing grant with an explicit scoped-cleanup root, the broker may open and settle
the local obligation through `record-cleanup --scoped` only with exact root identity and effect
postcondition checks. Registered evidence remains immutable; arbitrary effects and terminal close
remain outside this grant.

## 3. Operation tiers and asynchronous authority
Every public command and event is fail-closed through `engine/operation-capabilities.json`:

- **Notebook:** the local broker may collect and append truthful records non-interactively.
- **Authority:** the broker first records `pending_authority`; an operator may approve/reject/expire/
  supersede only the exact action digest. Approval is current, lane-bound, executor/session-bound,
  one-use, and never retrospective. Unrelated Notebook lanes continue.
- **Real-world:** capability-bearing bytes require fresh live confirmation or the signed local-only
  standing grant enforced by the kernel. Effects outside that grant require human confirmation.

Use `runtime-identity --role broker` for the OS-principal/POSIX-session provenance values. This is a
truthful local trust boundary, not authentication against another process with total access to the
same user account or filesystem. Agents never become the signed operator.

Required gates are correct behavior, not stalls. Only a Notebook operation blocked contrary to the
frozen capability matrix is an improper stall.

## 4. Impact-artifact gate (blocking, Zone-2 only)
Before creating a PoC artifact, `scope.md#impact_demo_authorized` must authorize its category.
The broker then needs fresh human confirmation for that exact artifact or a signed
`local_only_v1` standing grant for contained local PoCs. An open cleanup obligation must precede
the artifact, and the artifact record must reference that obligation. No standing grant extends to
external effects, other assets, or an unsigned scope.

## 5. Review and filing gates
`record-review` commits an external independent review and its typed event through one canonical
Notebook boundary. The event truthfully names the broker that committed it and separately binds the
reviewer/run identity in the immutable review. Independence, current subject, controls, replay, and
claim tuple remain reducer-validated. A review cannot file a finding.

`revise-finding` is a separate Authority operation: an approved exact digest lets the broker commit
one contiguous revision, while operator authority, reviewer adjudication, evidence, and filing remain
distinct. Regrade and Pocinator review truth/proof; report acceptance remains another operator-owned
transition. Severity escalation (self → stored/persistent → cross-user) remains rung-by-rung.

For `decision-0006-v2`, action-version 3 retains GQ, GK, and G0-G6 at this one signed activation.
G3 privilege and G6 impact-state facts come from the exact primary attempt's typed execution context;
G5 recomputes CVSS 3.1. Independent review is authenticated judgement. The G4 corpus-generation
audit is a separate mechanical heuristic over the committed review corpus and blocks when applicable;
it never substitutes for independent review. Refuted and contaminated revisions remain fileable
negative records with informational severity and do not claim that positive proof gates passed.

## 6. Cleanup gate
Every artifact the harness created (test chat, shared object, uploaded fixture, planted canary) is
recorded in `cleanup.md` with its revert action and status. Unresolved cleanup **blocks pattern
promotion**. Redact secrets always.

## 7. Non-authoritative flow telemetry
`tools/flow_telemetry.py` deterministically exports kernel facts and optional advisory runtime
observations. Generic normalized JSON and sanitized Claude Code metrics are supported. Prompts,
responses, arguments, commands, environment values, file contents, credentials, and target payloads
are forbidden. Missing runtime values remain `null` with measured/record coverage; live exports are
always `flow_telemetry`, never efficacy evidence. Telemetry cannot alter authority, tiering, claim
truth, independence, calibration, routing, severity, reports, or gates. No database, daemon,
scheduler, service, dashboard, live score, cross-runtime average, or optimizer exists.

## 8. Memory disposition and closure gate
Every completed or blocked engagement records exactly one operator-reviewed `promote`, `defer`, or
`no_novel_lesson` disposition with typed provenance and sanitization metadata. Every retained text field in a
`promote` proposal is checked against operator-enumerated target terms, referenced IDs, endpoints,
commands, and recipe shapes; the operator also attests source comparison and abstraction review. Positive controls,
refutations, reward-hacked proof shapes, and environment failures may be lessons; promotion is never
forced. `record-memory` changes only engagement-local immutable records. Even `promote` cannot write
`skills/`, casebooks, or other Plane-1 memory; that requires a later scrubbed human-reviewed PR.

`close` is operator-only and requires terminal coverage, a structured cleanup disposition for every
obligation, no pending review, accepted/submitted current-revision reports for filed findings, and
the committed memory disposition. In addition, both `close` and every transition that moves coverage
out of `active` consult the same reduced-state predicate: the engagement may end only when no computed
work item has `blocking: true`. The check runs on the current ledger under the terminal transition's
lock. A closed or skipped candidate therefore remains accounted for until the record lifecycle
accounts for the lead: the queue first selects `reopen_candidate`, then a
`hypothesis.created` event whose `origin_type` is `candidate` and whose `origin_ref` is that exact
candidate closes the candidate-disposal item. Free-text disposal alone cannot shorten the blocking
queue.

An operator may deliberately end with blocking work only through a separately operator-signed,
first-class override event. The event records the reason and the exact blocker identities being left;
it also binds the exact attempt-ledger count and canonical prefix digest that produced those identities.
A later attempt therefore makes the override stale even when the coarse queue identity is unchanged.
The event does not erase those blockers or bypass cleanup, report, memory, scope, or other independent gates.
Reduced state therefore distinguishes a clean ending from an overridden one.

`budget_bounded` also requires a prior registered frozen corpus enumeration. Before the genesis
signed-scope snapshot is created, its exact manifest-byte digest must replace `none` on the scope's `Frozen corpus
enumeration SHA256` line. The terminal command or outer driver supplies the registered manifest
artifact ID as `--corpus-enumeration-ref`; the reducer verifies that its digest matches the signed
genesis pin, its `frozen_at` is no later than genesis attestation, its linked enumeration is registered and intact, and `enumerated_count` equals that
enumeration's row count. A missing reference, `none` pin, or mismatch is refused. At an outer-driver
budget boundary, an omitted reference returns `operator_required` rather than recording a terminal
coverage event. Consecutive `budget_bounded` declarations with no intervening work disposition
remain legal to reopen, but the reducer exposes the cycle as a countable fact.

Narrative edits cannot satisfy these gates. Operator identity is anchored in the trusted local OS,
signed scope, and engagement filesystem; repository hash chains are tamper-evident commitments, not
cryptographic authentication against total host/filesystem compromise.
