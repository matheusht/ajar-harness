# engine/gates.md — human-in-the-loop gates

**Route scope:** the historical gates below apply to legacy/v1 and v2 scopes
without `authority_policy: initial-scope-v1`. New v2 work follows the
[initial-scope policy](../docs/decisions/0015-initial-scope-autonomy.md) and
[native worker protocol](native-engagement-protocol.md); do not import legacy
per-artifact or operator-rung approvals into that signed workflow.

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
A Zone-2 artifact requires a fresh signed-operator confirmation bound to one future artifact id,
planned byte digest/size/path, active environment and scope, an open cleanup obligation, and at most a
30-minute expiry. The kernel rechecks all bindings under lock immediately before exclusive creation.

## 3. Operation tiers and asynchronous authority
Every public command and event is fail-closed through `engine/operation-capabilities.json`:

- **Notebook:** the local broker may collect and append truthful records non-interactively.
- **Authority:** the broker first records `pending_authority`; an operator may approve/reject/expire/
  supersede only the exact action digest. Approval is current, lane-bound, executor/session-bound,
  one-use, and never retrospective. Unrelated Notebook lanes continue.
- **Real-world:** fresh live confirmation is still required before capability-bearing bytes or effects.

Use `runtime-identity --role broker` for the OS-principal/POSIX-session provenance values. This is a
truthful local trust boundary, not authentication against another process with total access to the
same user account or filesystem. Agents never become the signed operator.

Required gates are correct behavior, not stalls. Only a Notebook operation blocked contrary to the
frozen capability matrix is an improper stall.

## 4. Impact-escalation confirm (blocking, Zone-2 only)
Before creating **any** real PoC artifact (worm/exfil chain/etc.):
1. `scope.md#impact_demo_authorized` must be true (category authorized), AND
2. a **live human confirmation** is obtained at the moment — the loop **pauses and asks**; it never
   creates a harmful artifact autonomously, even when the category is authorized, AND
3. the artifact is contained (inert where possible) and logged in `cleanup.md`.

## 5. Filing-boundary draft (#85 incomplete)

G3/G6 declarations and evidence-reference bindings are insufficient for new filing.
New supported/confirmed request, commit and activation admission is held with
`filing_original_observation_unavailable`; legitimate positive filings are blocked too.
The attempt schema has no original typed execution privilege or impact-state-origin
signal. Relabelling raw root/injected evidence as low-privilege/real-path passed in the
previous draft after signatures; the current hold refuses new positives instead. The draft is not full gate equivalence or
adoption qualification. Exact failing evidence is recorded in the implementation worktree.

`record-review` records the independent review and typed event. For new filings,
its `finding_digest` names the exact proposal and its commit retains the reviewer
SSH proof. `request-authority` accepts only a v2 exact finding action with filing
contract v1. Signed `resolve-authority` binds it to the ledger prefix; both
`settle-approved-revision` and `revise-finding` use one locked activation boundary.
The reducer repeats the retained GQ/GK/G0–G6 contract before deriving active state.
See [the gate mapping and applicability](finding-lifecycle.md#4-gate-checks-and-missing-evidence-in-contract-v1).

Mechanical signature/reference/rank/severity checks, signed execution assertions,
and the G4 generation heuristic remain distinct. An unsigned `attest.json`, actor
string, empty ledger, ambient kernel waiver or file waiver never authorizes filing.
Historical inspection remains advisory; historical signed records retain their
original replay semantics. The local draft refuses legacy promotion. Any role may demote a
legacy package; immutable canonical revisions use reviewed signed dispositions.

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
