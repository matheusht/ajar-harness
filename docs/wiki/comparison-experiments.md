# Recovery and communication experiments

**Status:** recovery and communication packets implemented and locally checked; candidate execution UNSTARTED; adoption undecided. **Updated:** 2026-09-05. **Authority:** [specification #106](https://github.com/matheusht/redteam-harness/issues/106), [recovery ticket #111](https://github.com/matheusht/redteam-harness/issues/111) and [communication ticket #112](https://github.com/matheusht/redteam-harness/issues/112).

Both packets depend on the implemented [offline study account](engineering-evidence.md). They prepare concrete benign documents, expected accounts and fixed protocols. They do not justify implementation of the design being compared.

## Recovery: select observable requirements before a runtime

The [foundation research](../research/harness-engineering-2026-09-05/foundations.md) inspects pinned sources and upstream tests for the present baseline and alternative foundations. Those upstream tests were read, not executed here. Existing supported interfaces may satisfy some requirements; deeper ownership needs a specific unmet contract.

The approved packet covers document revisions, a late correction, a recorded-but-unsupplied result, cooperative pause and simulated loss after an artifact write without a receipt. Keep admission, adapter invocation and unobserved provider receipt separate. Preserve error, termination, uncertain effects and unknown usage rather than collapsing them into one success label. Saved conversation state does not establish exactly-once artifact work.

Persisted rollover without a summary stays an optional diagnostic until explicitly selected as necessary. Fix the required contract before inspecting candidate outcomes. A source citation or illustrative trace cannot earn a passing execution result. The remaining choice is which supported foundation meets the chosen requirements with the least maintenance, not which feature list is longest.

## Implemented recovery packet

The [v1 packet](../experiments/recovery-v1/README.md) supplies [document revisions](../experiments/recovery-v1/documents.md),
[scheduled expected accounts](../experiments/recovery-v1/expectations.json), a frozen
[definition](../experiments/recovery-v1/definition.json) and [synthetic observations](../experiments/recovery-v1/observations.json).
Three cases are paired across the present repository baseline `ea3e5c69222c9a1a471915af56bf9485429b53ea`
and OpenAI Agents Python SDK `f1f35031d364f9f0d8e94dda0853c92abefdccff`. The historical source-reading
provenance remains limited; Git confirms only the two named baseline files are unchanged since that
inspection. Neither pin establishes an installed ordinary-session configuration.

The [packet test](../../tools/recovery-packet-test.py) checks source release order, declared worker/grader
separation, trace distinctions and eight invocations of the unchanged public study reporter. Complete
case coverage, a fully measured artificial variation, missing cases, unknown usage, adverse output and
contamination remain distinct; malformed binding/schema fails. Packet/input bytes and inventories are
preserved. These are packet/account checks, not executed isolation or candidate recovery proof.

Required contracts, whole-study ceilings including coordination/repair, separate development/maintenance
allocation, optional rollover, fixed reference grading and run-readiness/stop criteria are recorded before
outcomes. Effective configuration and run authorization remain absent; candidate execution is **UNSTARTED**.
Source references and invented expectations earn zero candidate execution passes. #110 remains pending:
two automatic safety checks blocked its attempts; two uncommitted WIP files remain preserved, and it is not a completed slice.

## Communication: test discovery against capable handoffs

The [message-board research](../research/harness-engineering-2026-09-05/message-board.md) finds enough reason to investigate discovery and late corrections, but no established benefit for this harness. A useful example is a source-version correction relevant to a worker whose identity the observer does not know.

| Arrangement | Input and communication |
| --- | --- |
| Serial | One worker with complete sources and the scheduled observations. |
| Direct handoff | Complementary workers, directed messages and a curated coordinator packet. |
| Board | The same parallel arrangement plus a task-local feed capped at five short notices per packet. |

Use three short cases: complete sources, complementary evidence and a late correction, with a stale or unsupported notice included. Keep source access, effective configuration, total budget and the release point of external observations equal. Count preparation, coordinator work, reading, posting, curation, failed lookups, repeated analysis and human repair. Necessary independent checking is not waste by definition.

Commit independent initial observations before shared conclusions. Fix the reference assessment first and grade anonymized final outputs without treatment labels, peer discussion, self-grades or other cases' answers. Notices retain task, author, source version, observation, applicability and uncertainty; corrections identify their predecessor. Retention, delivery opportunity, use, correctness and usefulness are separate observations.

## Implemented communication packet

The [communication v1 packet](../experiments/communication-v1/README.md) contains three concrete
source cases, independent observation/curated handoff examples, bounded notices and physically
separate fixed grader references and illustrative finals. Its [manifest](../experiments/communication-v1/manifest.json)
fixes source hashes, identical direct/board assignments, exact worker/grader file lists, matched
external releases and a five-notice ceiling. Serial receives complete sources; every role can
inspect every released current-case source. Graders receive only their current-case reference and
neutral designated finals, with assignment mappings withheld.

The [definition](../experiments/communication-v1/definition.json) and
[fully admitted synthetic account](../experiments/communication-v1/observations.json) pass the
unchanged public reporter for all nine assignments. The supplied nine technical eligibility
assessments are artificial, not nine agent successes. Whole-study work includes coordinator and
communication effort, failed lookup, repeated analysis, human repair and overhead. Budget adherence
in the illustrative closed-world account establishes no observed real spend or budget enforcement.

The [packet test](../../tools/communication-packet-test.py) passed **7 bundle controls and 9 public-command
checks**. It materializes and byte-checks exact worker/release/grader bundles; negative controls reject
reference leakage, other-case answers, early corrections and assignment drift. Report variations retain
contaminated/missing/failed cases and distinguish technical eligibility from comparison contamination,
unknown measurement from zero, and known budget overrun. Source/input inventories stay unchanged.
This proves prepared-file/account checks, not physical runtime access control or cognitive isolation.

Effective run configuration and authorization remain absent. No board/adapter/runtime was built and
no agent experiment ran. The gate remains a validated notice explaining improvement over capable
direct handoff at the same total budget without new correctness/provenance/isolation failure. Equal
complete results with equal or lower effort favor the simpler baseline; adoption requires later
predeclared repeated paired evidence. #110 remains blocked with two preserved uncommitted WIP files. The integrated safe regression
passed for the five committed slices; independent review remains pending and #106 is incomplete. Both candidate experiments are **UNEXECUTED**.

## What earns the next step

A deterministic packet check establishes accounting and isolation behavior only. A later mechanism pilot may justify a larger study when a validated notice explains an improvement over capable direct handoff at the same budget, without a new correctness, provenance or isolation failure. Equivalent complete output with equal or less effort favors the simpler baseline.

Adoption needs repeated paired evidence and a practical benefit threshold declared before the adoption study. Neither three cases nor a busy feed establishes that threshold. Recovery selection likewise requires executed evidence for the chosen contract, not source inspection alone.

Before either actual comparison, establish effective model/runtime/configuration, resource ceilings, case/source roster, grading isolation and run scope/authorization. Ordinary-session conclusions also need the representative launch path, still unknown. The [implementation prompt](../research/harness-engineering-2026-09-05/implementation-goal-prompt.md) stops after validated preparation packets; provider calls, model experiments and infrastructure adoption remain separate work.
