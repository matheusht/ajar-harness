# engine/finding-lifecycle.md — findings start unproven

## 1. The local filing-boundary draft

**Current operational hold:** no qualified original-observation producer exists.
New `supported`/`confirmed` authority requests, revision commits and activations
are refused with `filing_original_observation_unavailable`, even if the positive
claim is legitimate and its review/operator signatures are valid. Signed refuted/
contaminated filings and historical replay remain available. This prevents the
known contradictions from becoming new active positives; it does not implement
an accepting truthful-positive path or qualify #85 for production use.

The original limitation motivating that hold is recorded below.

**#85 remains incomplete; this patch is for independent review.** G3/G6 use
signed finding declarations bound to attempt references. Existing attempts contain
no original typed execution-privilege or impact-state-origin observation. A review
can therefore sign `proven: authenticated-user` or `mode: real-path` even when a raw
artifact describes root execution or injected impact state, and the previous draft could not
mechanically detect that contradiction. Current admission therefore refuses all
new positive filings instead of trusting that declaration. Free-text `reachability_basis` does not
establish background-state reachability. These are signed-review assertions, not
full retained-gate equivalence or adoption/retirement qualification.

The runtime behavior of the draft follows.

New filings use finding-v3 with `filing_contract.version: 1`. The operator approves
an exact v2 `revise-finding` action through `request-authority` and signed
`resolve-authority`; `settle-approved-revision` or `revise-finding` applies it.
Both commands share `_apply_finding_revision`; the kernel append boundary and
reducer enforce the same versioned contract. An old action version cannot authorize
a new activation. Historical signed revisions replay with their original semantics.

`findings/<id>/rev-N.json` is immutable storage. Active membership comes only from
its `record.committed` plus validated `finding.revised` event, with matching bytes,
current scope/environment, lane, principal/session, exact adjudication and unconsumed
operator approval. The approval retains an SSH proof over its action digest and
ledger prefix. A directory name, package gate result or unsigned `attest.json` is
never activation. Legacy `promote` always refuses, including with environment/file
waivers. Package `gates` is explicitly advisory historical inspection.

Filing records the actual claim state. `supported` remains nonterminal; inferred or
unproven impact remains labelled and uncertainty is retained. `refuted` and
`contaminated` can retain negative evidence without successful exploit proof. These
states require the same exact independent review and signed authority. `needs_review`
remains notebook/unproven work or a signed legacy import, not a newly fileable state.

The writer holds the existing identity-bound engagement lock. It writes and fsyncs
immutable revision bytes, commits the record, then appends the activation. All gates
are validated before append. Staging without activation is inert; only the exact
expected orphan path is admitted during recovery. Identical retries complete a
missing commit/activation or rebuild projections after activation, without overwriting
bytes or consuming authority twice. Conflicting bytes fail closed. A torn ledger
append fails closed and uses the existing signed tail-repair workflow. Process-kill
checks are local process-crash evidence, not physical power-loss qualification.

## 2. Why the default matters

Every system that produces claims picks one of two defaults.

| default | with no action | an unattended run drifts toward | failure mode |
|---|---|---|---|
| accept | the claim stands | **more** claims | silent, and it compounds |
| reject | the claim is nothing | **fewer** claims | loud, and it self-limits |

Most software is default-accept because most software trusts its input. This pipeline takes claims
from an unreliable narrator, so it must be default-reject.

The reason is unattended operation. Under default-accept a check that does not run is a silent pass,
so a broken run produces confident garbage and looks productive. Under default-reject a check that
does not run is a silent block, so a broken run produces nothing. Choose the failure that is visible.

**The case that produced this doc.** In spotify-backstage-2026-07 (2026-08-09) seven findings were
written straight into `findings/` with `claim_state: supported` set by the script that created them.
Nothing objected, because nothing had to. See `fixtures/preregistration/spotify-phase2-OUTCOME.md`.

## 3. Proposal, filing and safety demotion

Hunters and orchestrators may retain proposals and partial packages in `unproven/`.
The broker files only the exact independently reviewed, operator-approved canonical
revision. Any role may still run `finding_lifecycle.py demote` on a **legacy package**;
this removes its old promoted location without asserting new positive evidence.
A package containing immutable `rev-N.json` history cannot be moved. Kernel findings
use independent claim review and a signed successor disposition, preserving history.

## 4. Gate checks and missing evidence in contract v1

| Gate | Enforced input and meaning | Kind and limit |
| --- | --- | --- |
| GQ | Bound, non-quarantined source throughout the locked transaction | Mechanical source admission |
| GK | Attested scope, current usable environment and validated ledger; no empty-ledger or ambient waiver | Mechanical authority/provenance, not truth |
| G0 | Canonical schema, typed references, committed records and artifact-byte digests | Mechanical identity/existence, not prose path scanning |
| G1 | Fresh primary attempts with non-model evidence and exact scope/environment; per-claim mappings | Mechanical record checks; causal truth remains reviewed |
| G2 | Distinct linked held/no-signal negative control and signalling replay, per-claim binding, declared fresh state and reviewed applicability/freshness | Mechanical bindings plus signed human/reviewer attestations |
| G3 | Finding-declared `filing_contract.privilege_context`, rank and primary/replay refs | Signed-review assertion; no original typed execution-position observation to compare |
| G4 | Exact proposal digest in an independent authenticated review, retained SSH proof, recomputed input hash and committed corpus audit | Signature/identity checks plus a separate generation heuristic; clear is not proof of thoughtful judgement |
| G5 | `CVSS:3.1` vector recomputes to numeric score and severity label, or informational `none` with no score/vector | Mechanical recomputation; unsupported systems fail closed |
| G6 | Finding-declared impact-state mode/refs and free-text background reachability bases | Signed-review assertion; explicit synthesized mode blocks, but signed relabelling is not checked against original typed state observations |

G1/G2/G3/G6 positive-success checks remain defined for historical `supported` and
`confirmed` replay. New positive admission additionally remains unavailable until
a qualified original-observation collector/oracle exists.
Negative-state filings preserve evidence identity, scope/environment, review and
severity checks, but do not invent a successful primary/replay or clean contamination.
Negative states label impact `not_demonstrated` and use informational `none` severity;
contaminated records explicitly retain present/unresolved contamination.

The following package-gate explanations describe historical inspection semantics.
Their unsigned declarations and legacy carve-outs do not authorize new filings.

### G2 — the control-role gate

For v3 findings, naming a control is no longer enough. With `--engagement`, G2 resolves every
`proof.negative_control_refs` entry against `attempts.jsonl`, requires `kind=negative_control`,
requires a `held`/`no_signal` outcome, and rejects any reference also cited as a primary attempt or
replay. If a modern attempt carries `control_of`, it must point to one of the finding's cited primary
attempts. Missing ledgers and unresolved refs fail closed.

This split matters: a replay asks whether a signal happens again; a negative control asks whether
the signal disappears when one causal variable changes. The same attempt cannot prove both.

Legacy flat v1 packages predate addressable proof refs. They retain the old attestation check until
they are migrated; they do not receive a false claim that attempt semantics were mechanically
verified.

### G3 — the privilege gate

A program cannot decide whether a proof truly ran as a low-privilege user. It can decide that the
package **declares both positions** and that they agree.

The package declares `privilege_context: {claimed, proven}`. The gate ranks both on a ladder —
unauthenticated 0, authenticated or co-tenant 1, privileged or admin 2, system or root 3 — and
requires `rank(proven) <= rank(claimed)`.

Proving from **less** privilege than claimed passes: that is a stronger result. Proving from more
privilege fails, because it does not establish that the attacker can reach the code at all.

This is the failure ZSec documented: a named pipe that looked exploitable from SYSTEM and was
unreachable as a standard user. Our own equivalent is any finding whose PoC ran as the operator.

**`proven: not-established`** is a valid declared value. Use it when the proof does not start from an
attacker position at all — a unit test that constructs the post-bypass state, a harness that begins
mid-chain. It always blocks, but it blocks as a STATEMENT rather than as an omission. "We know this is
missing" and "nobody looked" should not look the same in the record.

First real use, 2026-08-10: all eleven spotify findings declare it. The A2 keystone PoC calls
`mockCredentials.service()`, which constructs the post-bypass state and asserts the real
`ServerPermissionClient` allows it. That proves the CONSUMER against real code; the PRODUCER half is
source-verified, not executed.

### G4 — the adjudication gate

`tools/adjudication_audit.py` over the package's `reviews/` **and over the engagement's whole
claim_adjudication set**. It blocks a review corpus that carries the signature of generation: one
reviewer identity, no dissent, and boilerplate rationale, all together.

**Version 2, 2026-08-10 — hardened after an evasion.** A run on another engagement read
`adjudication_audit.py`, then generated reviews that satisfied it: three reviewer identities,
non-empty corrections, one sentence with the finding id interpolated. Version 1 returned `clear` on
30 generated reviews. Two fatal signals now catch it — an `input_hash` with no entropy (a real
digest shows 14-16 distinct hex characters, a typed one shows one), and every review recording the
same instant. Three of five smells now condemn, instead of all of three. The lesson is Goodhart: a
detector whose signals are all satisfiable by editing declared fields will be satisfied by editing
declared fields. The durable fix is an `input_hash` the verifier recomputes.

Auditing the engagement corpus is not optional. The signature is a property of the **corpus**, not of
one review. A package normally carries the single review that adjudicated it, and one review can
never show all three signals. Running the gates over the eleven spotify findings on 2026-08-10 passed
G4 on all eleven, while the engagement's 15-review corpus audited `synthetic`. If the corpus was
generated, no finding resting on it may promote.

## 5. Canonical records and historical packages

`filing_contract` contains typed privilege context and impact-state provenance.
Both bind referenced evidence to the signed review's exact `finding_digest`.
The review's committed signature proves its declared reviewer identity; it does not
prove the reviewer performed the experiment. G4 audits only committed review inputs
at the relevant ledger prefix, so future reviews cannot retroactively change a gate.

Historical `finding.json`, `attest.json`, reports and reviews remain readable.
`gates PACKAGE` can inspect them. `status` reports reducer-derived canonical claim
states and labels unauthenticated stored packages `stored-unverified`, never proven.
The reference index resolves stored revisions but grants no filing authority.
Signed legacy migration preserves `needs_review` and never manufactures proof.

## 5b. Partials live in `unproven/`. That is what it is for.

Added 2026-08-16 after an audit measured this directly: across three post-gate engagements the
gates blocked **zero** promotions out of twelve, and `unproven/` was **empty** in both angular
engagements. One hundred per cent promote, zero partial. The designed home for incomplete work
existed and nobody used it.

That is the failure mode a peer named: *"making your tool's judging phase too rigorous can lead to
dropping valid severe vulnerabilities."* It did not reach us through the gates — the gates never
said no. It reaches us through **what never gets written down**. A three-stage chain with stages 1
and 2 proven and stage 3 argued has real value, and if the only two states are "passes seven gates"
and "a line in a hardening note", that value evaporates.

**Write the partial.** A package in `unproven/` is not a failure and not a draft. It is a finding
whose completion is bounded and stated.

A partial package declares, in `finding.json`:

```json
"stages": [
  {"n": 1, "claim": "...", "state": "proven",   "evidence": "attempt://..."},
  {"n": 2, "claim": "...", "state": "proven",   "evidence": "attempt://..."},
  {"n": 3, "claim": "...", "state": "argued",   "blocked_by": "scope-ceiling",
   "what_would_close_it": "one live probe of the RBE ActionCache IAM binding"}
]
```

`state` is one of `proven` · `argued` · `refuted`. A partial is any package with at least one
non-`proven` stage. It stays in `unproven/`, it never claims a severity above what its proven
stages support, and it is **not** promoted — promotion still means every gate passed.

What a partial buys: it survives the round, it is re-readable by a later run, its proven stages
enter the primitive registry, and its `what_would_close_it` is a concrete next action rather than
a shrug. A hardening note is a dead end. A partial is a queue.

## 5c. A scope-blocked ceiling is a REQUEST, not a cap

Operator standing instruction, 2026-08-16: **scope will always widen if more authorization is what
it takes to prove a ceiling. Always.**

That does **not** authorize anyone to widen it. The five wires in `scope.md` are unchanged, and the
acts that need a fresh confirm still need one. What changes is the disposition of a ceiling that
only authorization is holding down.

Before: the run wrote *"conditional escalation, out of scope to test"* and moved on. The highest-
value finding in `angular-dev-infra-2026-08` is exactly this shape — the GCP service-account key to
RBE cache-poisoning chain, the Supply-Chain top band, written out in full in `cascades.md` and
marked "hypothesis, not claimed" because liveness and IAM are Google-side facts and probing them
trips wires 2 and 4. That is the correct call about the act. It was the wrong call about the
record: it capped silently instead of asking.

Now: record it in `ceiling-requests.md` and **surface it to the operator**. One row per blocked
ceiling:

| what the ceiling is | the band it would reach | the exact act required | which wire it trips | what would be irreversible | cleanup path |

The orchestrator does not perform the act. It states the request precisely enough that the operator
can answer yes or no in one reading. A ceiling nobody asked about is a finding we chose not to have.

## 6. What this does not do

It does not decide whether a vulnerability is real. It decides whether the package's own claims
survive mechanical checking, which is the same boundary `tools/score_finding.py` draws.

A bounded negative research result (`record-negative`, `docs/research-lifecycle.md`) is not a
finding revision: it is a notebook event citing attempts, limits and residual candidates. Filing a
`refuted` or `contaminated` claim still requires the independently reviewed, operator-approved
revision described above; recording a negative result neither files a finding nor demotes one.

Novelty, reportability, and attribution stay at Stage 5.25. Zone-2 artifacts and the operator's
review before submission are unchanged and are not gates in this file
(`engine/autonomy.md` §2 — those two do not graduate).

## 7. Increasing autonomy

The way to run more of this unattended is **not** to trust the model more. It is to convert
judgement into decidable checks. Every check that becomes computable is autonomy gained while
trusting nothing extra.

The legacy G3 rank check was added on 2026-08-10. The legacy G4 heuristic was added on 2026-08-09. Neither establishes causal truth. The next
candidates are G1 and G2, whose remaining execution-truth assertions still need independent evidence beyond their typed record checks.
