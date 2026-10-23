# Harness engineering wiki

A maintained synthesis of product/engineering decisions, evidence and open questions.
Started on 5 September and extended through the October native-research discussion.
Accepted decisions and revision-bound source evidence retain their own authority.
This is curated topic coverage, not a complete repository ingestion or a live tracker.

## Read by question

| Question | Page |
| --- | --- |
| What are the product north stars and engineering choices? | [Product and engineering direction](product-and-engineering-direction.md) |
| What is implemented and what is actually qualified? | [Native research status](native-research-status.md) |
| What did the October discussion and external research establish? | [Discussion record and research lessons](../research/research-direction-discussion-2026-10.md) |
| What did the September offline engineering package deliver? | [Offline engineering evidence](engineering-evidence.md) |
| What are the September recovery and communication experiment plans? | [Recovery and communication experiments](comparison-experiments.md) |
| Which Q02 inputs can receive a new verdict? | [Q02 admission contract](../q02-admission.md) |
| Where are the concrete recovery cases and protocol? | [Recovery packet v1](../experiments/recovery-v1/README.md) |
| Where are the communication sources, bundles and grading rules? | [Communication packet v1](../experiments/communication-v1/README.md) |
| How do I inspect existing evidence without changing it? | [Dossier inspector](../dossier-inspector.md) |
| How do I prepare and inspect an offline study account? | [Study report contract](../study-report.md) |
| What was the September implementation assignment? | [Implementation goal prompt](../research/harness-engineering-2026-09-05/implementation-goal-prompt.md) |
| Which external evaluation ideas and benign cases are useful for future work? | [Future evaluation applications](future-evaluations.md) |
| What changed in this wiki? | [Chronological log](log.md) |
| How should an agent maintain these pages? | [Maintenance instructions](AGENTS.md) |

## Current direction and dated delivery

The [direction page](product-and-engineering-direction.md) owns durable rationale.
The [native status page](native-research-status.md) records the 23 October candidate,
including implemented continuation and its missing live evidence. The September
delivery below remains a separate, dated engineering result.

### September delivery state

All six slices have local implementation and bounded acceptance evidence as of 2026-09-08 under [specification #106](https://github.com/matheusht/redteam-harness/issues/106). Slices #107–109 and #111–112 previously completed both independent review axes; their exact reviewed boundary remains in the [evidence page](engineering-evidence.md#final-handoff). The [read-only dossier inspector](../dossier-inspector.md) now implements #110 with 23 public-command checks and integration into the existing scoped CI step. Both independent review axes for the new #110/integration diff are complete. All six scoped local slices are accepted with integrated tests and reviews done; no issue closure or merge is part of this delivery. PR publication was separately requested on September 10. The September 5 automatic execution errors are preserved as observations, not a finding that this offline task was prohibited; the resumed September 8 scoped work succeeded through normal tools. Recovery and communication candidate experiments remain UNEXECUTED. The [handoff](../research/harness-engineering-2026-09-05/handoff.md) preserves the approved plan and prior main repair.

This status is a dated observation, not a live tracker. Recheck the source commit and issue state when execution begins. Future completed slices must update the topic page and append to the log with their test evidence.

## Source map

| Source | How to use it |
| --- | --- |
| [Decision index](../decisions/README.md) | Canonical architecture decisions and supersession flags. The synthesis reviews relevant direction; it does not revalidate historical outcomes. |
| [October discussion record](../research/research-direction-discussion-2026-10.md) | Recorded operator choices, evolving mechanisms, dated research lessons and unfinished reading leads. |
| [Retained October source review](../research/native-session-source-review-2026-10.md) | Detailed external claim checks, counterarguments and original design proposals, with later-choice pointers. |
| [Native cutover contract](../agents/native-cutover-contract.md) | Source routing, retained callers and the qualification boundary; implementation permission is distinct from adoption. |
| [LLM domain scope](../agents/llm-domain-scope.md) | Concrete LLM-application benign-proxy and impact examples; the generic authority boundary is in the root README. |
| [Earlier engineering notes](../engineering/README.md) | Dated engineering evidence and decisions. Preserve their historical context. |
| [September 5 research index](../research/harness-engineering-2026-09-05/README.md) | Full evaluation, reconstruction, instruction, recovery and communication investigations. |
| [Approved specification and publication record](../research/harness-engineering-2026-09-05/handoff.md) | Accepted scope, native issue dependencies, exact published material and execution limits. |
| [Research validation](../research/harness-engineering-2026-09-05/validation.md) | Executed synthetic checks, source-reading coverage and limits; not implementation acceptance. |

Source records stay in those locations. The wiki links and reconciles them; it is not another source of approval or a replacement for code and test evidence.

## Origin of this wiki (5 September)

[Karpathy's LLM Wiki note](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) proposes maintained, linked Markdown synthesis over retained sources, with an index, history and agent conventions. We are applying that pattern to engineering decisions. This initial version needs no application, ingestion pipeline or search service; new tooling must demonstrate a need.

The linked note was read in full on 2026-09-05 through its [raw source](https://gist.githubusercontent.com/karpathy/442a6bf555914893e9891c11519de94f/raw). Retrieved content SHA-256: `dc3efe98ae62f23dd08acad13aba2e95287beb20b6bec2f4af0423557fe37401`. This identifies the read bytes; it is not a pinned Git revision, and the URL can change. The note is a design suggestion, not evidence that this wiki reduces effort.
