# 0013 — One versioned signed finding activation

19 October 2026. **Implementation draft; #85 incomplete and open.** Implements part
of the scoped direction in PR #115; it does not establish full retained-gate equivalence.
Local synthetic qualification was recorded in the implementation worktree and is not part of this
commit; independent integration review is separate.

## Proposed boundary and implemented draft behavior

Extend decision-0006 rather than add a package adapter. Only the signed kernel
activation makes a new revision active. `settle-approved-revision` and
`revise-finding` share the same locked writer; kernel append admission and reducer
replay enforce the same versioned contract. The local draft refuses legacy `promote`. Any role
may still demote legacy packages; moving immutable revision history is refused.

New finding-v3 records require `filing_contract.version: 1` at admission. The field
remains optional in the schema to preserve historical records and inert legacy
`needs_review` imports. The writer rejects new filing through old action versions
or without the contract; the reducer preserves historical semantics for old bytes.
This distinction is enforced at the lowest supported append API, not just CLI help.
Direct filesystem modification by a process with total host access remains outside
the local trust boundary; hash chains do not authenticate an entire host.

The operator signs approval of the canonical v2 action, including exact proposal
bytes, scope/environment, code-owned lane, executor/session and current adjudication.
The retained approval signature binds the ledger prefix at resolution. The filing
independent review signs its exact `finding_digest` and input hash; its commit
retains the review signature for replay. Altering typed gate declarations changes
both digests and requires fresh review/approval. Arbitrary role/actor strings and
unsigned truthy flags cannot substitute for either signature.

## Evidence checks and missing original observations

G3/G6 currently remain signed-review assertions in the finding. Original attempt-v2
records contain no typed observed attacker/execution privilege, and no typed origin
or reachability signal for each impact-bearing precondition. Generic artifact bytes
and a free-text setup basis cannot be mechanically compared to these declarations.
The earlier gap probe preserved original root/injected evidence while signing a
low-privilege/real-path finding and exposed that failure. Current new positive
request/commit/activation admission is held with
`filing_original_observation_unavailable`. Legitimate positives are also blocked.
No current producer measures the required target facts; no accepting enum or mock
collector has been added. Signed negative filings and historical replay remain
available. This is a fail-closed interim hold, not completion or production qualification.

Completing #85 requires an original per-attempt privilege observation and per-state
origin/reachability record, with a defined collector/oracle and immutable evidence
links, plus checks that compare the filing to those observations. Merely adding
another author-entered enum would repeat the problem. This broader evidence capture
contract is not implemented by this patch.

Other draft checks follow.

GQ/GK require bound source, usable attested scope/environment and intact ledgers.
G0 checks typed references, commitments and artifact digests. G1/G2 retain fresh
primary/control/replay and per-claim checks. G3 adds typed claimed/proven privilege
positions and signalling evidence. G6 adds typed impact-state provenance, rejecting
injected impact preconditions for positive filings and itemising seeded background
with evidence and reachability bases. These are signed reviewed assertions plus
mechanical bindings; the code does not establish physical execution truth.

G4 retains exact independent review provenance and runs the committed-corpus
generation heuristic separately. A heuristic clear verdict is not proof of judgement.
No G4 file waiver or ambient kernel waiver can authorize a filing. G5 supports
CVSS:3.1 with recomputed score and label, or informational `none` without score/vector.
Other severity systems need a separately specified contract, not a free-form waiver.

Supported remains a nonterminal bounded positive claim; inferred/undemonstrated
impact and uncertainty remain in the record. Positive supported/confirmed filings
require their reachability/provenance evidence. Negative refuted/contaminated
filings retain reviewed evidence identity and exact signed authority without
fabricating successful exploit proof. They retain informational severity and
undemonstrated impact. The fileable state set is unchanged.

## Commit and recovery

Revision bytes are immutable, atomically written and fsynced under the bound
engagement lock. The durable record commit precedes activation. Admission validates
the proposed event with the reducer before appending it. Active membership derives
from committed activation, never from storage location or cached views.

Before activation, interrupted bytes/commits are inert. The same exact authority
and digest can resume the expected staging path without a blanket orphan exemption.
After activation, identical retries rebuild projections without another commit or
activation. Conflicting bytes are refused, never repaired by overwriting committed
history. An interrupted partial JSONL append fails closed and uses the existing
signed tail repair; process-kill checks do not establish power-loss durability.

## Compatibility and limits

Historical signed records keep their original grades and weaker schema semantics;
replay does not manufacture missing G3/G6 data. New admission cannot use that
compatibility branch. The reference index still resolves historical stored revisions
without granting authority. Reporting/queue read active reducer state; status labels
unauthenticated storage explicitly. Legacy packages stay inspectable and demotable.
Unproven proposals and partial stages remain durable research inputs.

The draft refuses Decision 0010's package promotion writer and separates G4's
heuristic from authenticated review. Acceptance of a replacement for 0010 remains open. Its historical failure evidence remains useful.
The original PR #115 scope note remains a decision record, not qualification proof.
