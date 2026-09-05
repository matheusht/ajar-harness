# Recovery comparison preparation v1

**Packet prepared; candidate execution UNSTARTED.** This is the document-only deliverable for
[#111](https://github.com/matheusht/redteam-harness/issues/111). Effective configuration and run
authorization are absent. All supplied observations are explicitly invented accounting examples.
They prove neither candidate behavior nor receipt of input. No adapter or experiment is implemented.

Inspect [documents](documents.md), [scheduled expected accounts](expectations.json), the frozen
[definition](definition.json) and [illustrative observations](observations.json). The latter two
use the unchanged [study-report contract](../../study-report.md):

```sh
python3 tools/study-report.py --study docs/experiments/recovery-v1/definition.json \
  --observations docs/experiments/recovery-v1/observations.json
python3 tools/recovery-packet-test.py
```

The definition hash binds supplied bytes. The declared freeze time belongs to the illustrative
chronology, not a witnessed preregistration. This packet's local commit fixes preparation inputs;
a future authorized run must record a fresh pre-outcome manifest of these files and its effective
configuration. Freeze required contract, grading reference, schedule, ceilings and exclusions before
any candidate output. A changed requirement creates a new version and new paired assignments;
never revise the reference after seeing a candidate fail.

## Required contract and matched schedule

The question is whether supported interfaces can truthfully account for revision/correction,
recorded-but-unsupplied result, cooperative pause, and uncertain artifact work after simulated loss.
Use three independent fresh cases in the declared order: `late-correction`, `cooperative-pause`,
`lost-receipt`, baseline then SDK within each case, one repeat each. Identical source bytes,
release boundaries, scripted response text, source retrieval opportunity and limits apply to both
arms. No between-case state or answer reuse. Release is by event ordinal, never by wall-clock speed.
Do not pre-deliver v2, correction, expected artifact or another case's answer. The full packet is
review material; it is NOT the future worker input. The curator gives workers only the sources
released in their current case, and gives the grader only that case's fixed reference and anonymized
final account. Curator and reference grader are separate from both candidate workers.

Default observation point: **arguments received by a future scripted adapter under client-managed
history**. The `argument_items` mapping resolves expected input IDs to roles, calls and exact source text.
Record instructions, ordered input, settings, tool descriptors, output schema and
continuation identifiers, including absent values. A local admission record precedes invocation;
filter/hook observations alone are insufficient to establish those final arguments. Server-managed
continuation is outside this version. The packet contains only EXPECTED arguments, no received ones.
Provider acceptance is unobserved and cannot be upgraded from either local admission or invocation.
No model comprehension or provider-effective history claim is permitted.

The fixed reference is the `cases` section of expectations.json plus document revisions above.
Grade source revision, correction order/duplication, unfinished work, flags, unknown effects and
usage separately, then account completeness. Preserve any raw subtype separately from `is_error`,
`stop_reason`, `terminal_reason` and error details. A success subtype cannot override an error or
unfinished artifact. Missing telemetry remains unknown. The reference grader is isolated from
arm labels, peer discussion/material, self-grades and other-case answers. Curator retains the
assignment mapping outside grader inputs. Missing evidence is unknown, explicit unsupported
interface is unsupported, and neither counts as a pass. A truthful interrupted account may be a
correct output; it does not mean the underlying document task completed.

Saved conversation state never establishes exactly-once artifact work. In `lost-receipt`, the
curator's simulated write is a fixture fact; the recovered account initially lacks the receipt.
Require uncertainty and inspection/reconciliation before any repeat write. Even seeing expected
bytes afterward proves present content, not execution count or atomic checkpoint/effect storage.
This is a static process-loss scenario, not an actual crash or filesystem-durability test.

Persisted no-summary rollover/reopen is a **separate OPTIONAL diagnostic**, excluded from the six
required assignments, required grade and budget. If later authorized, preregister a separate
account and ceiling. Lack of this interface does not fail v1 or justify owning a loop. Deeper design
work becomes eligible only after an executed comparison identifies an unsupported REQUIRED
contract; compare a small wrapper or another supported runtime before a fork or owned loop.

## Pins and provenance

Reuse the limited historical inspection in [foundations](../../research/harness-engineering-2026-09-05/foundations.md#source-identity-and-confidence),
not a new survey or a claim about installed versions:

| Arm | Frozen source identity | Available evidence; remaining gap |
| --- | --- | --- |
| baseline | repository `ea3e5c69222c9a1a471915af56bf9485429b53ea` | Earlier bounded driver/adapter source reading; limited-content metadata. Required adapter-argument receipt and recovery interface support remain unknown. |
| sdk | OpenAI Agents Python SDK `f1f35031d364f9f0d8e94dda0853c92abefdccff` | Selected source/test bodies inspected for preparation, pending input, soft cancellation and RunState compatibility. Tests were read, not executed here. Complete crash/effect/usage account remains unknown. |

Historical baseline inspection was at `6a47b64264b6bf8f1edf8923847cfc9952cd1ab8`.
Read-only Git blob comparison found unchanged `tools/work_queue_driver.py`
(`0a068b53f735f323207277dd6399de95fbaa9c57`) and `tools/claude_work_session.py`
(`796a27be735f4b57f1753f72ac7d40c69c7aca32`) at the present baseline above. This establishes
those two files' byte continuity only, not installed/runtime or ordinary-session equivalence.
Supported SDK entry points are promising candidates, not executed contract passes. Foundations
references O1–O10 identify exact upstream files and lines; no upstream source was re-inspected or
installed for this packet. No provider receipt interface is supported by this offline protocol.
The optional native no-summary boundary is not established for either selected arm.

## Frozen resources and ownership

Definition ceilings cover the WHOLE six-assignment study, not a per-worker allowance:
3,600 human-active seconds, 7,200 elapsed seconds, 14,400 summed machine seconds,
0 model input/output tokens and $0 total attributable cost, including provider and infrastructure. Include preparation, curator coordination,
source release, useful assistance, retries, interruption, recovery, synthesis, grading, reporting,
cleanup, accounting and human repair. Coordination is activity in preparation/synthesis/accounting;
repair is activity in recovery/retry. Stop before a ceiling would be exceeded. No paid/model work is
permitted; unknown attributable infrastructure cost cannot be silently treated as zero. Record actual labor and machine intervals independently; shared elapsed time is one clock,
not a sum of concurrent workers. Reserve half the study ceiling for preparation, coordination,
grading, repair and accounting; each arm may use at most one quarter for case execution. Unused
allowance cannot fund extra repeats or unequal assistance.

Development and maintenance are separate accounts, never silently hidden in study receipts.
Development ceiling: 7,200 human seconds, 14,400 elapsed, 14,400 machine, zero tokens/$.
Maintenance ceiling: 3,600 human seconds, 7,200 elapsed, 7,200 machine, zero tokens/$.
Combined project maximum including all three accounts: 14,400 human, 28,800 elapsed upper-bound
allowance (not a measured elapsed sum), 36,000 machine seconds, zero tokens/$. No work under
these proposed future ceilings is authorized now. Packet-authoring/check effort is not measured by
the illustrative receipts and no resource-savings claim follows from them.

Allocate directly attributable receipts once to their assignment/account. Shared study work is
study-wide and split equally between arms only for an explicitly labeled secondary comparison;
keep raw totals. Common development is allocated equally; candidate-specific adapter and repair
work goes to its arm. Maintenance uses the same allocation over a fixed 30-day post-pilot window.
Do not double-count time that crosses scope boundaries: record an explicit sourced partition.
Record adapter lines/dependencies, setup, human interventions, repair steps, upgrades, compatibility
fixtures and removed machinery with attributable evidence. Before future execution, name owners
and retention/upgrade obligations for baseline/native-client compatibility and SDK agent/context
restore definitions, serialized schema/migrations, cancellation consumption and source pins. Unknown
maintenance remains unknown; a small diff is not a low-maintenance result.

## Run readiness and stop criteria

Before a future run, all of these must be supplied and reviewed:

- Explicit run authorization, allowed synthetic data roster, disposable artifact directory and cleanup owner.
- Exact installed runtime/build, scripted adapter identity, instructions/hashes, settings and source pins;
  witnessed effective loading and declared client-managed history. No provider, network or paid path.
- Supported interface feasibility for each REQUIRED checkpoint; unavailable interfaces recorded as
  unsupported, with no invented trace or substitution that changes the contract.
- Pre-outcome file manifest, matched schedule/access, fixed grader reference, anonymization and isolation
  check, budget enforcement/measurement sources, repair rules and all development/maintenance owners.

Stop or reject the pair on changed sources/schedule, unequal access/assistance, grader leakage,
undeclared configuration drift, missing required observation boundary, an exceeded/unenforceable
ceiling, unexpected sensitive data or any attempted model/provider/network call. Retain blocked,
incomplete and failed assignments and all attributable work; do not silently rerun or drop them.
Unknown measurements prevent budget-adherence claims. Protocol contamination rejects unqualified
comparison even if an output is technically correct. Ordinary-session generalization additionally
requires a representative ordinary-session launch configuration, presently absent; that absence
limits a future claim but does not prevent packet completion.

## What was checked

The packet test calls the real public reporter with complete illustrative case coverage, missing
case, interrupted/error output, unknown usage, contamination, unknown loading, and malformed binding
variations. It checks document release order, grader/source separation, exact pins and the three
receipt distinctions. It verifies packet/input bytes and file inventories remain unchanged.
These are executed packet/account checks only. The reporter retains source-reference strings but
never opens or validates the referenced expectations; the packet test checks those local links.
There are zero independently eligible candidate results. Actual comparison remains UNSTARTED.
