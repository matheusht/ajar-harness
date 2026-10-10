# Decision 0006 operator runbook

Use `.venv/bin/python` locally (`python3` in pinned CI).

## 1. Establish local broker provenance

```bash
.venv/bin/python tools/run-engagement.py runtime-identity --role broker
```

Use the returned generic broker actor and POSIX-session identifiers. They describe the local trust
principal; they do not make an agent the signed operator.

## 2. Notebook work

`preflight`, `classify-artifact`, `register-artifact`, `append-attempt`, and `record-review` are
non-interactive when their capability evidence is complete. Unknown commands/events/variants fail
closed. Preflight collection cannot assert operator review. `review-preflight` is separate.

`tools/run-work-queue.py run` is classified once as the external broker Notebook operation
`run-work-queue`. Its evidence is an exact target-local workspace, one reducer-owned action at a
time, and an outer budget; none of those controls is delegated to the launched model session.
The public command requires the explicit Docker backend and has no host-process fallback. It accepts
only the fail-closed Apple Silicon Docker Desktop profile, an already-cached immutable digest-pinned
image, absolute in-image Claude/Python paths, and finite memory, CPU, PID, open-file, scratch, and
shared-memory byte/inode limits. The target and harness are mounted directly and read-only; repeated
`--read-only-input` values may add only canonical regular files. Optional directories and special
files are rejected. The target is never collected beneath a central harness path.

The stopped-container phase binds the exact image, mounts, limits, container/network IDs, immutable
configuration digest, target inode, action, and deadlines before activation. PID 1 retains the
broker key, relays only typed action/Stop operations, and owns all descendants. Timeout, interrupt,
parent death, normal completion, and storage exhaustion remove the exact session resources. Read
[`docs/agents/docker-work-queue.md`](agents/docker-work-queue.md) before operating this path; it is
the canonical host/image contract and includes the full CLI template, descendant-wide storage
error latch, syscall-tracing cost, and qualification limits.

## 3. Request exact authority

1. Write a canonical JSON action containing `action_kind`, `lane_id`, broker executor/session, and
   every command argument that affects the transition.
2. Run `request-authority` with a current timestamp and expiry no more than 24 hours away.
3. The operator reviews the exact digest. Bind an SSH allowed-signers file digest in signed
   `scope.md` as `Operator allowed signers SHA256`. Run the command once to print its canonical,
   ledger-bound challenge; sign those exact bytes with `ssh-keygen -Y sign -n
   llm-redteam-harness-operator-v1`, then rerun with `HARNESS_OPERATOR_SIGNATURE_FILE` and
   `HARNESS_OPERATOR_ALLOWED_SIGNERS_FILE`. A pseudo-TTY or typed phrase is not authority.
4. Pass the request id and identical lane/executor/session/arguments to the dependent command.

Approval is one-use, non-retrospective, current-scope/environment-bound, and lane-local. Other signed-
scope Notebook work may continue while it is pending. Rejection, expiry, supersession, scope drift,
or changed proposal bytes require a new request.

## 4. Review, finding, and reports

`record-review` commits reviewer work but cannot file it. Configure an SSH allowed-signers public-key
file and bind its SHA-256 digest in signed `scope.md`; each review must carry an `ssh-keygen -Y`
signature over canonical review bytes in namespace `llm-redteam-harness-review-v1`. This prevents a
broker from inventing a reviewer principal. `revise-finding` requires separate operator
authority and one contiguous revision. Report generation/acceptance, submission, memory disposition,
and closure each require their own exact authority request. Adjudication and filing remain separate.

## 5. Terminal coverage and closure

Before moving coverage out of `active` or closing an engagement, reduce the current ledger and inspect
the computed work queue. Both paths use one rule: the normal ending is refused while any item has
`blocking: true`. A closed or skipped candidate remains in that accounting. Follow the queue's
`reopen_candidate` action, then create a hypothesis whose `origin_type` is `candidate` and whose
`origin_ref` names that selected candidate. The origin hypothesis accounts for the lead; a free-text
reason does not.

`budget_bounded` additionally requires a prior registered frozen corpus enumeration. Before signing
scope, replace `none` on the exact `Frozen corpus enumeration SHA256` line with the digest of the
manifest bytes, then register that manifest and its linked enumeration as engagement artifacts. Pass
the manifest artifact ID—not its digest—to the outer driver as
`--corpus-enumeration-ref <artifact-id>`. Its `enumerated_count` must equal the enumeration artifact's
row count; no frozen enumeration, a signed-scope mismatch, or a damaged link is a hard refusal. If the
driver reaches its session or wall boundary without the CLI reference, it returns
`operator_required` and records no `budget_bounded` event. Reopening and redeclaring without an
intervening work disposition is permitted but appears as a fact in reduced state and must not be
presented as new coverage.

When the operator judges that an engagement should end with blockers, use the separately signed
first-class ending override rather than adding a payload flag or editing prose. Review the exact
blocker list and reason before signing. The resulting record leaves the blockers visible and marks the
ending as overridden. Its signed context includes the exact attempt-ledger prefix, so any later
attempt invalidates reuse even when the blocker identity remains the same. It does not bypass scope, cleanup, report, memory, or other independent
closure gates.

## 6. Zone-2

Do not create or pipe capability-bearing bytes before either `confirm-zone2` or a current signed
scope with the versioned `local_only_v1` standing grant and an open cleanup obligation. Fresh
confirmation binds one planned artifact digest, size, path, scope, environment, cleanup, operator,
and short expiry. The standing path binds planned bytes/path, scope, environment, and cleanup
without per-artifact confirmation. `create-artifact` revalidates under lock before exclusive
creation. A scope with only `impact_demo_authorized: yes` is insufficient.

For a v2 scope that also signs `scoped_cleanup_closure: yes` and an exact safe
`scoped_cleanup_root`, the broker may use `record-cleanup --scoped` to open one local obligation,
reference its opening event from repeated evidence artifacts, and complete it after the fixed inert
scoped effect is removed and absence is checked. If no effect was created, use verified
`not_applicable`. Evidence files remain immutable. This grant covers no arbitrary transient effect;
report acceptance and terminal close still require their own operator authority.

## 7. Flow telemetry

```bash
.venv/bin/python tools/flow_telemetry.py normalize --adapter claude-code \
  --engagement-id ENGAGEMENT --input sanitized-metrics.json --output observations.json
.venv/bin/python tools/flow_telemetry.py export --engagement engagements/ENGAGEMENT \
  --observations observations.json --output flow-export.json
```

Adapters accept counts/timing/link IDs only. Never provide transcripts, prompts, responses, arguments,
commands, environment values, file contents, credentials, or target payloads. Live output is advisory
`flow_telemetry`; it cannot alter gates or claims.
