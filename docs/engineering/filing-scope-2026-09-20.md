# Remaining filing contract and local WIP disposition

Selected plan, 2026-09-20; implemented locally on 2026-09-22 for issue [#85](https://github.com/matheusht/redteam-harness/issues/85).
Reviewed source: `5e366a32af299fead09180b5ef349310d674d7cd` (origin/main).
Local WIP was inspected against `0d8fe0c4ffb57a3bf1cfd5d4db013113b51d8c8d`, not imported.
Implementation evidence is recorded in `filing-activation-failure-matrix.md`; this note alone does
not close #85.

## WIP disposition

The eight tracked WIP files contain 161 insertions and 10 deletions. Preserve them in place.

| Candidate | Disposition |
| --- | --- |
| Lifecycle prose and conformance cases treating revision-only stores as filed | Useful regression intent, incomplete implementation: current G0/status do not implement the promised distinction. Rework against canonical activation, not directory inference. |
| G4 canonical-review lookup | Evaluate separately against exact finding/review bindings; file presence alone cannot establish authority. |
| G4 file waiver | Reject from portable implementation. A named file must never turn a failed evidence gate into success. Do not import target-specific rationale. |
| More detailed lifecycle logging | Separate candidate; does not authenticate an actor or make move-before-log atomic. |
| Four reporting instruction files | Separate editorial review; unrelated to #85 acceptance. |
| Ten KB rows, untracked fixtures/preregistration and local artifacts | Preserve pending provenance, redaction and evidence review. No blanket commit, deletion or promotion. |

## Selected design direction

Under the authorized scope decision, select one signed record-kernel filing activation to own every
write that makes a revision active. This is a plan, with no runtime change.
Retain immutable revision history; a directory is storage, never proof. Filing is recording a
claim state, not declaring a vulnerability confirmed. Preserve supported/nonterminal,
contaminated and refuted records; current `FILEABLE_CLAIM_STATES` already includes supported,
confirmed, contaminated and refuted (`tools/engagement_state.py`). Do not silently broaden that set.

Extend the existing decision-0006 validation/commit path rather than add a third publisher.
Bind activation to exact record bytes, scope, environment, lane, session and current ledger state.
Make active membership derive only from a committed activation, so interrupted staging is inert.
Decide and test recovery under the existing lock/transaction mechanism before claiming crash safety.
Retire the legacy production move writer. Build no package adapter unless a concrete retained
consumer is demonstrated; any justified adapter can only stage input for that same signed activation.
Package-only gate inspection remains advisory. Retain historical signed records under their original
schema semantics. Version new checks; never retroactively manufacture missing evidence.
The writer and reducer retain pre-v2 request/action handling alongside v2; the new-activation
contract must cover both. Historical replay is distinct from accepting a new filing through an
old action version. Refuse weaker legacy-version activations rather than secure only v2.

Negative, refuted and contaminated filing must remain possible without successful exploit proof.
Positive claim promotion must satisfy applicable reachability and state-provenance requirements;
state-specific applicability must never become a shortcut for a positive claim.

## Gate mapping to preserve meaning

| Gate | Existing canonical evidence / remaining work |
| --- | --- |
| GQ | Bound source admission and quarantine checks exist. Require them at activation and retain exact source identity through commit. |
| GK | Kernel scope/ledger admission exists. Remove the legacy ambient environment-waiver route from production activation; no empty-ledger exemption. |
| G0 | Committed referenced records and digests provide stronger typed identity than prose path scans. Define retained source-artifact existence/digest requirements explicitly; do not equate a readable directory with activation. |
| G1 | v2 filing validation already checks committed primary attempts, non-model-only evidence, scope/environment and per-claim proof. Preserve these predicates and document their limits: valid records do not alone prove causal truth. |
| G2 | Existing control/replay kinds, linkage and per-claim proof checks cover substantial semantics. Preserve applicability, freshness and exact provenance; map each retained legacy predicate explicitly. |
| G3 | No typed equivalent of legacy privilege context. Add minimal typed attacker position/required privilege and evidence bindings; a prose attacker model alone is not equivalence. |
| G4 | Canonical exact independent review provenance exists. Legacy corpus-generation audit is a statistical heuristic, not the same predicate and not proof of judgement. Preserve the applicable quality bar, with the corpus heuristic distinct from independent review. Bind decisions to exact inputs; no default waiver, unsigned truthy flags or file waivers. |
| G5 | Canonical classification/severity exists, but legacy vector consistency is not thereby enforced. Define supported severity systems and their recomputation/applicability contract before activation. |
| G6 | No typed equivalent of impact-bearing state provenance. Distinguish ordinary seeded background from synthesized impact preconditions, with typed provenance and referenced evidence; unsigned attestation cannot establish reachability. |

Source anchors: `tools/engagement_state.py::_validate_revise_finding_v2_action`,
`tools/run-engagement.py::command_revise_finding`, `schemas/finding-v3.schema.json`,
`tools/finding_lifecycle.py::{run_gates,cmd_promote,gk_kernel,g3_privilege,g4_adjudication,g6_state_provenance}`,
`docs/decisions/0010-promotion-gates-and-fail-open.md` and `engine/finding-lifecycle.md`.
Legacy `cmd_promote` still accepts an arbitrary actor string and moves before appending its log.
Neither the WIP directory distinction nor signed canonical filing alone closes the combined contract.

## Smallest staged implementation

1. Freeze the activation/state definition and typed missing semantics above. Add focused adversarial
   cases for both entrypoints before changing their contracts; preserve negative-state storage.
2. Extend existing canonical validation with retained missing predicates; retire legacy production writes. Add conversion only for a demonstrated consumer, always through
   canonical activation. Fail closed on absent engagement and waiver paths.
3. Implement and fault-test commit/recovery: before staging, between file/ledger writes, and after
   authoritative commit. No active record without a committed activation; retries do not double-file.
4. Update root guidance, gates/lifecycle docs, ADRs, schemas and CLI help together. Close #85 only
   after arbitrary actors, direct v3 filings, old action-version requests for new filings, package-only
   calls, empty ledgers, waivers and interruption
   cannot bypass the same contract. Record mechanical, signed-review and heuristic results separately.

No implementation or gate-pass claim follows from this plan. Human-time savings and discovery
benefits remain unmeasured.
