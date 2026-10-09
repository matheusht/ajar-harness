# Harness engineering wiki

A maintained synthesis of engineering decisions, their evidence and the questions still open. Started on 2026-09-05 at the user's request. The initial coverage is the approved offline engineering investigation; this is not a complete ingestion of the repository.

## Read by question

| Question | Page |
| --- | --- |
| What did we decide to build, and why? | [Offline engineering evidence](engineering-evidence.md) |
| How will recovery and a message board be compared fairly? | [Recovery and communication experiments](comparison-experiments.md) |
| Which Q02 inputs can receive a new verdict? | [Q02 admission contract](../q02-admission.md) |
| Where are the concrete recovery cases and protocol? | [Recovery packet v1](../experiments/recovery-v1/README.md) |
| Where are the communication sources, bundles and grading rules? | [Communication packet v1](../experiments/communication-v1/README.md) |
| How do I inspect existing evidence without changing it? | [Dossier inspector](../dossier-inspector.md) |
| How do I prepare and inspect an offline study account? | [Study report contract](../study-report.md) |
| What should the implementation task do? | [Implementation goal prompt](../research/harness-engineering-2026-09-05/implementation-goal-prompt.md) |
| Which external evaluation ideas and benign cases are useful for future work? | [Future evaluation applications](future-evaluations.md) |
| What is the current local candidate delivery and qualification status? | [September 22 delivery status](delivery-status-2026-09-22.md) |
| What changed in this wiki? | [Chronological log](log.md) |
| How should an agent maintain these pages? | [Maintenance instructions](AGENTS.md) |

## Current delivery state

The current three local candidate heads and their qualification gaps are recorded in the
[September 22 delivery status](delivery-status-2026-09-22.md). They remain separate local review
inputs rather than a merged or fully qualified delivery. The paragraph below preserves the prior
2026-09-08 state and its then-current experiment status.

All six slices have local implementation and bounded acceptance evidence as of 2026-09-08 under [specification #106](https://github.com/matheusht/redteam-harness/issues/106). Slices #107–109 and #111–112 previously completed both independent review axes; their exact reviewed boundary remains in the [evidence page](engineering-evidence.md#final-handoff). The [read-only dossier inspector](../dossier-inspector.md) now implements #110 with 23 public-command checks and integration into the existing scoped CI step. Both independent review axes for the new #110/integration diff are complete. All six scoped local slices are accepted with integrated tests and reviews done; no issue closure or merge is part of this delivery. PR publication was separately requested on September 10. The September 5 automatic execution errors are preserved as observations, not a finding that this offline task was prohibited; the resumed September 8 scoped work succeeded through normal tools. Recovery and communication candidate experiments remain UNEXECUTED. The [handoff](../research/harness-engineering-2026-09-05/handoff.md) preserves the approved plan and prior main repair.

This status is a dated observation, not a live tracker. Recheck the source commit and issue state when execution begins. Future completed slices must update the topic page and append to the log with their test evidence.

## Source map

| Source | How to use it |
| --- | --- |
| [Decision index](../decisions/README.md) | Canonical architecture decisions and supersession flags. Indexed here; the older decision set has not been re-ingested or revalidated for this wiki. |
| [Earlier engineering notes](../engineering/README.md) | Dated engineering evidence and decisions. Preserve their historical context. |
| [September 5 research index](../research/harness-engineering-2026-09-05/README.md) | Full evaluation, reconstruction, instruction, recovery and communication investigations. |
| [Approved specification and publication record](../research/harness-engineering-2026-09-05/handoff.md) | Accepted scope, native issue dependencies, exact published material and execution limits. |
| [Research validation](../research/harness-engineering-2026-09-05/validation.md) | Executed synthetic checks, source-reading coverage and limits; not implementation acceptance. |

Source records stay in those locations. The wiki links and reconciles them; it is not another source of approval or a replacement for code and test evidence.

## Why this shape

[Karpathy's LLM Wiki note](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) proposes maintained, linked Markdown synthesis over retained sources, with an index, history and agent conventions. We are applying that pattern to engineering decisions. This initial version needs no application, ingestion pipeline or search service; new tooling must demonstrate a need.

The linked note was read in full on 2026-09-05 through its [raw source](https://gist.githubusercontent.com/karpathy/442a6bf555914893e9891c11519de94f/raw). Retrieved content SHA-256: `dc3efe98ae62f23dd08acad13aba2e95287beb20b6bec2f4af0423557fe37401`. This identifies the read bytes; it is not a pinned Git revision, and the URL can change. The note is a design suggestion, not evidence that this wiki reduces effort.
