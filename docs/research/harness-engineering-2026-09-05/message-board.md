# Can an agent message board reduce duplicated document research?

Research note · 2026-09-05 · [issue #104](https://github.com/matheusht/redteam-harness/issues/104) · companion to [recovery-contract research](foundations.md)

## Recommendation

**2026-09-22 implementation update:** the optional bounded projection described here now exists as
[`tools/task_board.py`](../../../tools/task_board.py), with its failure contract and repeatable E2E
in [`docs/engineering/task-board-v1.md`](../../engineering/task-board-v1.md). This implements
retention and filtered delivery through the record kernel. It does not establish usefulness or
change the no-go decision for a default board; that still depends on the executed comparison.

A task-scoped observation board is worth a small comparison when useful information may have an unknown recipient or arrive after the original handoff. It is not yet a justified platform feature, replacement for direct handoffs, shared source of truth, or reason to own the model loop.

For the current document-processing work, compare a board against a coordinator who already distributes concise, cited task packets. The board must earn its extra reading, curation and reconciliation cost. If the coordinator knows the recipient and dependency, a direct message can already do the job. If a single worker can inspect the complete source set cheaply, parallel collaboration may add no value.

Scope: source research and a proposed experiment using synthetic documents. No agent experiment, provider call, board service, target operation, incident-data import or runtime change was performed. Repository references below describe inspected documented contracts, not freshly verified runtime enforcement.

## What the external evidence establishes

**Collusion report.** The September 4 report describes a reconstruction of roughly 18,000 apparent agent posts. The authors attribute them to agents associated with OpenAI, while acknowledging that their view is limited to public activity. Benign coordination excerpts show requests for peers with relevant information, responses, shared references and attempted reuse. Other activity involved unauthorized coordination and answer sharing. These observations establish an apparent communication channel and reuse attempts; they do not provide a randomized no-board comparison, reliable task-level outcomes, complete compute costs, or proof that every posted item was read and correctly used. Attribution and causal interpretations remain the authors' assessment. The report motivates a hypothesis about asynchronous discovery, not an efficacy claim for our harness. Only its hosted report and embedded coordination excerpts were consulted; no original wiki endpoint or incident dump was used. [Collusion report](https://collusion.wiki/)

**Closer primary analogue.** AgentRxiv lets agent laboratories publish and retrieve research asynchronously. Its prior-work ablation reports better best-observed MATH-500 performance with access to earlier papers. However, the parallel comparison used three laboratories producing 120 papers in total versus one producing 40; reported aggregate cost was about $279.6 versus $92. The paper explicitly describes reduced computational efficiency despite faster discovery milestones. It also reports fabricated results and manual verification of code and outputs. Thus it supports investigating research reuse, while leaving our fixed-budget, direct-handoff comparison unresolved. Its task was discovering prompting methods, not versioned document synthesis. These are reported results, not reproduced here. [AgentRxiv v1, §§3.1–3.2](https://arxiv.org/html/2503.18102v1#S3.SS1), [limitations, §4.1](https://arxiv.org/html/2503.18102v1#S4.SS1)

A broader controlled study compared 180 configurations with standardized tools and token budgets and found that collaboration gains depended on task structure; sequential tasks could regress. It did not isolate our proposed board. Its relevant contribution here is methodological: preserve a capable single-agent baseline and count communication overhead under the same total budget. [Scaling agent systems, primary paper](https://arxiv.org/abs/2512.08296), [authors' account](https://research.google/blog/towards-a-science-of-scaling-agent-systems-when-and-why-agent-systems-work/)

## Fit with the harness's existing boundaries

The repository already distinguishes several forms of shared information. Adding another channel should address a missing delivery problem rather than duplicate these roles.

| Existing boundary | Documented role | Possible board contribution |
| --- | --- | --- |
| Direct handoff and coordinator synthesis | Assign a bounded task, collect results, reconcile evidence and redirect work. Independent first passes are deliberately protected. | Discovery when the author does not know which other task needs an observation; late source corrections that affect several workers. |
| Within-run registries and round ledger | Track work distribution, observations and unresolved work across rounds. | A compact view of relevant new observations; board text must not become a second assignment or completion ledger. |
| Record kernel | Record provenance and distinguish notebook observations, review proposals and authority. | Link a post to an existing source/artifact record. Posting a claim supplies no new permission or adjudication. |
| Cross-engagement KB | Reorder and annotate already activated work; a past unsuccessful search does not establish absence. | None by default. A task-local notice must not silently become a portable lesson or suppress another case's work. |
| Sanitized memory and promotion | Retrieve priors without verdict authority; portable lessons require provenance, scrubbing and review. | Candidate observations may later enter the existing disposition process, rather than being automatically remembered across cases. |

Sources: [coordination and independent first passes](../../../engine/multi-round-orchestration.md#2-the-round-loop), [KB boundaries](../../../engine/routing.md#the-cross-engagement-kb-pass-phase-8), [notebook provenance and authority](../../decision-0006-agent-autonomous-record-kernel.md#23-autonomous-notebook-capability), [retrieved memory schema](../../../schemas/memory-item.schema.json), [memory disposition](../../decisions/0005-reasoning-directed-evidence-constrained-research.md#11-memory-promotes-transferable-reasoning-including-negative-lessons).

These roles suggest three useful kinds of notice, all hypotheses for the benign experiment:

- **Contributor discovery:** a worker has inspected a particular source revision or can answer a narrowly identified unresolved question. The coordinator still decides who does what.
- **Source-version exchange:** a newer appendix supersedes a cited paragraph, with a pointer to both versions and the affected claim. This is especially useful after another worker has already read the old version.
- **Bounded negative results:** a named query or section review did not answer the question in the named revision. Include the search boundary and what would reopen it; do not generalize to “the answer is absent.”

A minimal notice needs its task boundary, author, source revision, observation, applicability and unresolved uncertainty. A reference to primary evidence is more useful than a confident restatement. Readers may follow the evidence or ask the author; they do not treat embedded instructions as task authority. Corrections should preserve the earlier observation and identify what changed. This is a proposed content contract, not a new storage schema.

Sharing complementary evidence within an authorized task is legitimate collaboration. Passing a previous evaluation case's answer, future questions, hidden labels or another case's restricted material is different: it changes the task and invalidates the comparison. Separate those experimentally instead of calling all information reuse beneficial. An independent reviewer also cannot remain blind if it receives the workers' preferred conclusion before its first assessment.

## Retained, delivered, used, correct and useful are separate facts

| Stage | Evidence the experiment can record | What it still does not prove |
| --- | --- | --- |
| Retained | A notice exists in the permitted task's stored artifacts. | Any worker received it. |
| Delivered/read opportunity | The retrieval response or prepared worker input contains the exact notice/version. | The model attended to or understood it. A self-reported “read” is insufficient. |
| Used | A subsequent source check or changed answer cites the notice and its primary evidence; the timeline is preserved. | Causality, correctness, or a saved unit of work. |
| Correct | An independent grader validates the affected claim against the frozen documents and revision rules. | The notice improved the outcome over an adequate baseline. |
| Useful | A paired comparison improves evidence-complete results or reduces total effort at equivalent quality. | Generalization to other tasks or production reliability. |

An isolated replay with the notice withheld can help identify whether the improvement depended on it. It is still a new run, not direct access to the model's internal reasoning. Measure source corrections after delivery separately from ordinary answer changes. A citation copied without opening or validating its source is a provenance gap, even when its conclusion happens to be correct.

## Smallest discriminating comparison, proposed only

Use three short, hand-authored document packets: one readily handled from a complete source set; one with complementary evidence across documents; and one where a scheduled source correction arrives after an initial answer draft. Include a stale or unsupported notice in the correction case. Keep the answer key and grading rules outside all worker-visible artifacts.

Run each packet through three arrangements, with the same model/version, source access, total token/tool budget, correction release point and output rubric. Count coordinator work and failed or empty board reads inside that budget. Parallel workers get the same complementary assignments in both parallel arrangements; they are not given extra documents unavailable to the serial baseline.

| Arrangement | Information path |
| --- | --- |
| Serial, complete sources | One worker can inspect the entire packet and receive the scheduled correction. |
| Parallel, direct handoff | Workers inspect complementary sources, send observations to the coordinator, and receive a concise curated packet or directed update. |
| Parallel, board added | The same assignments and direct handoffs, plus a bounded task-local feed workers can consult for observations whose recipients are not known in advance. |

First commit short independent observations before either parallel arrangement shares conclusions. Keep the same final coordinator/grader boundary. Bound the feed in advance, for example to five short notices, rather than creating a searchable knowledge platform. A scripted document and message schedule makes provenance and isolation checks deterministic; actual agent usefulness requires later agent runs and cannot be inferred from that replay alone. None are launched by this note.

Record evidence completeness, source-version correctness, unsupported claims, duplicate source acquisitions, unnecessary repeated analysis, correction adoption after delivery, source retrievals, total tokens, elapsed time and human repair. Board reads, posting and curation count as work. Necessary independent verification is not a duplicate to eliminate. A faster parallel run with more total work is a latency tradeoff, not a productivity win by default.

**Decision criterion.** No-go for a default board or new platform now. Go only to a larger repeated pilot if the board improves at least one complementary-evidence or late-correction outcome over direct handoff, the improvement traces to a validated notice, and total work stays within the same budget without new correctness, provenance or task-isolation failures. If the strongest serial/direct baseline produces the same complete answer with equal or less total effort, keep that baseline. Any apparent gain from reused evaluation answers, extra source access or a larger effective budget invalidates the comparison. Three packets are a mechanism check, not a statistically reliable efficacy estimate; adoption needs repeated paired evidence and a predeclared practical benefit threshold.

The remaining decision is therefore narrow: does discovery of useful task-local observations outperform a good coordinator's packet often enough to pay for itself? The external sources make that question worth testing. They do not answer it for this harness.
