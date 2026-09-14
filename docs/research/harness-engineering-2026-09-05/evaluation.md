# Reliable inputs and complete accounting for offline comparisons

Research for [issue #101](https://github.com/matheusht/redteam-harness/issues/101), 2026-09-05. Source: `6a47b64264b6bf8f1edf8923847cfc9952cd1ab8`, isolated branch `codex/research-harness-engineering-2026-09-05`. Research only: no production patch, target engagement execution, historical recomputation, target contact, model/provider call, or tracker mutation. Isolated synthetic record initialization in the original flow checks is documented below.

## Decision supported by this investigation

**Proposed:** specify one strict input-admission boundary for Q02, an explicit result-unit contract, and a small study-level accounting record. Preserve the existing frozen rule and its limited license. Do not treat the current package inventory, a completed worksheet, or a passing self-test as sufficient evidence for a whole-harness comparison.

This is a bounded specification direction, not a recommendation for another evaluation framework. Q02 asks whether a hand-authored prompt helps in one two-arm case. Its pinned checkpoint expressly licenses only a hypothesis and another case, not a doctrine change. A broader offline comparison needs its own frozen outcome definitions and analysis contract; repairing Q02 does not expand its inferential scope. [Q02 purpose][q02-purpose]; [frozen checkpoint][checkpoint].

**Observed** means inspected committed code or documentation. **Measured** means the named synthetic check ran in this investigation. **Inferred** means a consequence consistent with those observations. **Proposed** means future behavior, not implementation or an accepted experimental outcome.

## Callers and the current admission contract

All statically discoverable Q02 call sites in tracked repository text were traced. This does not inventory unknown operator scripts, generated invocations or external callers.

| Entry/caller | Actual path | Admission or test coverage |
|---|---|---|
| Public `measure` | CLI → `cmd_measure` → locked arm snapshots → `_measure_arm_snapshot` | Checks source identity, coordination, quarantine and safe publication. Produces an inventory and optionally a blank worksheet. It does not reduce the arms or validate finding eligibility. |
| Public `verdict` | CLI → `cmd_verdict` → safe file reads → frozen-checkpoint validation → JSON decoding → `decide` | Strong checkpoint identity; no complete measurement/worksheet schema or semantic admission before the decision. |
| Internal `self_test` | Ten direct `decide` calls plus checkpoint/license checks | 26 named assertions. Tests explicit adverse flags and missing overlap, but not missing integrity fields, result identity/type, or reconciled overlap. Its helper repeats the ID `f` and sets all overlap counts to zero even for nonzero arm counts. |
| `check-conformance.py` | Subprocess `q02_compare.py --self-test` | Consumes the self-test exit code; adds no worksheet admission. Broad conformance was not run here. |
| `quarantine-self-test.py` | Public measure/verdict subprocesses and imported `cmd_measure`/`cmd_verdict` | Tests quarantine, path replacement and final publication checks. These do not add evidence-quality validation to ordinary calls. This broader test file was inspected in the relevant ranges, not executed. |

Sources: [public measure][q02-measure], [public verdict and decision][q02-admission], [self-tests and CLI][q02-tests], [conformance caller][conformance], [quarantine callers][quarantine-callers]. The older `measure_arm`/`count_packages`/`subagent_spend` helpers have no discovered external caller; the public measurement path uses the snapshot implementation instead. No dedicated Q02 measurement or worksheet JSON Schema was found. [Older helpers and active counter][q02-counting].

The checkpoint itself has closed fields, a pinned whole-file SHA-256, duplicate-key rejection, threshold consistency checks and a bounded license. The complete source preregistration and outcome are deliberately absent and opaquely pinned; their contents and historical provenance are not independently reconstructed here. Its checks must remain. They validate the decision-rule checkpoint, not the two data inputs. [Checkpoint admission][checkpoint-admission].

By contrast, `decide` blocks blinding only when `blinding_held is False`, blocks cross-arm reading and limit truncation only on truthy values, and checks overlap fields only for `None`. It does not require an adjudicator, a complete run record, boolean flags, nonnegative integer overlap counts, unique result IDs, or a list-valued result field. `ran_concurrently` and sequential order are never consulted. M7's waste branch accepts any truthy description. Duplicate JSON keys in measurements/worksheets use ordinary last-value-wins decoding. Malformed decoded shapes can raise outside the CLI's read-error handler. [Decision and caller][q02-admission].

Neither the measurement nor worksheet carries a required source digest, case/run identity, model/tool configuration or a binding to each other. Therefore file-read stability does not establish that two individually readable files describe the same experiment. This is an observed absence in their constructed shapes and call boundary, not proof of a historical mix-up. [Measurement and worksheet shapes][q02-measure]; [worksheet fields][q02-worksheet].

## Denominator integrity is a separate problem

**Observed:** the active M1 counter returns every second path component under `findings/` when that subtree contains any file. It does not require `finding.json`, inspect claim state, establish independent review, or validate ledger support. M3 only reads legacy `findings/<id>/finding.json`; a versioned `rev-1.json` can affect M1 while supplying no severity entry. Missing attempt/event ledgers become zero counts. M5 subagent spend is a regex sum over prose, not a resource receipt. [Active counter][q02-counting].

**Measured through the public CLI:** three harmless `notes.txt` folders and one minimal `rev-1.json` with `claim_state=needs_review`, without a valid record kernel or reviewed result, produced M1=4 and M3={}. Missing ledgers produced zero attempts/events. `Agents budget: 12` followed by `Agents used: 2` produced subagent spend 14. The test input had only three coordination locks and synthetic text/metadata. No security artifact or target was involved. [Measurement output](checks/evaluation/canonical/q02-public-measure-nonresults.stdout).

**Inferred:** Q02's meaning of “finding” depends on an upstream directory convention that the measurement path does not establish. This is particularly ambiguous across legacy promoted packages and revisioned records. It does not show that any prior reported finding was invalid.

There are at least three distinct denominators:

1. **Assigned cases:** every case/arm/repeat in the frozen roster, including no-output, interrupted, failed and incomplete cases. Produced records cannot define this roster retrospectively.
2. **Produced packages or claims:** inventory, useful for tracing workload; not automatically accepted results.
3. **Independently adjudicated unique results:** the outcome unit used by the comparison, with a mapping from the original packages/claims and a declared within-arm duplicate rule.

**Proposed:** validate overlap against an explicit identity mapping. The equalities `A = both + A_only` and `B = both + B_only` are appropriate only after A and B use the same unique-result unit. Do not impose them on raw package counts while allowing several packages to represent one root cause. Preserve raw records and map them to the admitted unit; never silently change the denominator or frozen rule. The present worksheet names a root-cause rule but contains only aggregate counts, so it cannot establish this mapping. [Worksheet][q02-worksheet].

## What the synthetic checks establish

Canonical logs and generated metadata inputs are retained in [checks/evaluation](checks/evaluation/README.md). The [original manifest](checks/evaluation/canonical/results.json) records executable, source hashes, exact subprocess arguments, return codes and outcomes. Original script bytes remain as a [text archive](checks/evaluation/canonical/original-probes.py.txt). The original flow checks initialized a minimal synthetic kernel with one `scope.attested` event, zero attempts and zero artifacts; generated kernel scaffolding is deliberately omitted. The batch used Python 3.14.6 and jsonschema 4.26.0; bytecode writes were disabled. Its four principal module hashes match the pinned commit.

| Check | Measured result | Interpretation |
|---|---|---|
| Q02 self-test | 26/26 named assertions pass | Existing assertions hold; they do not cover complete input admission. |
| Flow self-test | 7/7 named assertions pass | Determinism, null coverage and advisory/privacy restrictions hold in this small fixture. |
| Public Q02 verdict with missing integrity; inconsistent or wrongly typed overlap; scalar instead of ID array; duplicate result IDs; duplicate JSON field; whitespace-only waste description | Each returned `prompt_earns_its_keep`, exit 0, no blockers | Seven input-quality characterizations reach the public boundary, rather than only an internal helper. |
| Explicit failed blinding or truncated-arm flags | `inconclusive` with blockers | Existing adverse-flag guards work for their tested types. |
| Invalid decoded measurement shape | Exit 1 with traceback; no verdict | Rejects accidentally through an exception; not a structured admission result. |
| Public measure on nonresults | Four folders counted as findings; prose budget and use added together | Inventory and effort proxies do not establish eligible output or spend. |
| Flow export with an identical observation twice | Two calls, 200 input tokens, $0.40 | No observation identity/idempotency rule deduplicates repeated delivery. |
| Flow export with nested turn/model/tool durations, each 10 seconds | `active_seconds=30` | The field is a sum of supplied durations, not necessarily elapsed or nonoverlapping active time. |
| Two model observations, one cost $0.20 and one unknown | Flow: $0.20, records=2, measured=1; research cost helper: null | A partial measured subtotal and an all-known total have intentionally different semantics. |

There are 15 characterization cases plus two built-in self-test runs in the original canonical batch. Their checks assert observed current behavior, including defects; “all characterizations hold” does **not** mean repaired acceptance. An initial identical characterization batch used the OS default temporary directory; it was repeated under `/tmp` before the evidence was retained here. That repetition is not an independent experimental sample. No broad conformance, quarantine suite, historical result, provider workload or target workflow was executed.

The retained [reproducer](checks/evaluation/probes.py) uses a new OS temporary directory and executes no kernel initialization or lifecycle operation. It repeats the public Q02 cases/self-test and uses only normalization/coverage/cost helpers for the three flow accounting cases. One bounded validation produced [16 matching characterizations](checks/evaluation/reproduction-results.json), including Q02's 26 self-test assertions. This verifies the revised reproduction entrypoint; it does not repeat the original flow CLI or seven-assertion flow self-test coverage. [Retention and coverage details](checks/evaluation/README.md).

## Accounting: useful existing parts and material limits

**Observed:** research telemetry retains the candidate funnel and derives a denominator from recorded candidate proposals. It totals attempt and review costs and returns null for a cost dimension unless all included records measure it. That is a useful conservative convention, but its denominator cannot detect an assigned case or unrecorded work that never became a candidate. [Research totals and denominator][research-costs].

**Observed:** flow telemetry exports source hashes, runtime identities, linked-record coverage, kernel timings and elapsed authority intervals. Unknown values retain measured/record counts. Runtime data stays advisory and cannot grant authority or establish claim truth. These are useful semantics to retain. [Flow export][flow-export]; [flow schema][flow-schema]; [capture boundary][flow-runbook].

The accounting limits are concrete:

- Coverage is relative to submitted observations, not all actual calls or all assigned cases. An omitted call disappears from both numerator and denominator. Observation records have no unique receipt ID. Identical rows may represent duplicate delivery or two genuine calls; dropping equal rows automatically would also be unsafe. [Normalization and fields][flow-normalization].
- Duration rows may overlap across turn, model and tool levels. Active-duration sums are not human minutes or wall time. Authority intervals measure elapsed waiting; they must not be counted as labor. [Flow aggregation][flow-export].
- Runtime subtotals and kernel cost totals can describe the same underlying work. Adding them without a source/identity reconciliation rule can double count. A partial flow subtotal must retain its coverage and must not be presented as a complete total. [Flow aggregation][flow-export]; [conservative helper][research-sum].
- The intervention schema requires a correction, before/after claims and a latency category; it has no active-duration field and cannot represent successful setup, clarification, steering, review or administration without inventing a correction. Its report denominator is correction entries. Live and backfilled entries are correctly separated. [Intervention schema][intervention-schema]; [reporting][intervention-report].
- The intervention writer prevents an existing ID in the loaded file but rewrites the document without a lock or atomic publication. This is a static concurrency/interruption risk if promoted into shared accounting; no concurrent-write test ran. Do not turn this correction tool into the complete study ledger by assumption. [Writer][intervention-write].

**Proposed minimum accounting:** one short record per assigned case/arm/repeat plus attributable activity/cost receipts. Record the case family and outcome, actor/role, phase, active human duration, elapsed duration separately, runtime/model identity, unique observation/receipt identity, tokens/cost where available, and measurement coverage. Include preparation, successful assistance, retries, aborted work, recovery, synthesis, grading, reporting, cleanup and logging itself. Keep development/maintenance and comparison-grading overhead visible with an allocation rule frozen in advance. Avoid counting the same person's overlapping time twice; distinguish summed worker effort from elapsed time. Do not invent dollar costs from message counts or label unknown usage zero.

This can begin as a versioned offline JSON/CSV study artifact. Reuse existing telemetry as attributed inputs; keep the correction ledger for corrections. A permanent collector, database, runtime replacement or target-work automation is not required to establish the accounting contract.

## Fixed configuration and admission for a useful comparison

The separate A/B readiness scaffold already commits arm source files/Git trees, a common safety overlay, model/tool runtime evidence, matching budgets, isolation, holdouts and adjudication references. It is not called by Q02. It deliberately always returns `not_ready` and never authorizes execution; it is a design/reference source, not completed comparison evidence. [Readiness implementation][ab-prepare]; [matching schema][ab-matching].

**Proposed:** freeze before held-out results:

- The question, outcome unit, source/case roster and family split, inclusion policy, duplicate rule, independent adjudication procedure and permitted conclusion. Keep all assigned cases in operational/accounting reports; missing or blocked work is not an unobserved success, and no effect should be invented for it.
- Model/provider version or alias limitation, runtime/client version and artifact identity, reasoning/sampling settings when exposed, instruction/skill/context policy and source hashes, tools/environment, allowed data, and retry/termination policy. Record what actually ran, not only intended configuration. A floating alias requires explicit qualification; it cannot be made immutable by renaming it in a manifest.
- Equal total resource ceilings and the single intended treatment difference. Include every worker and coordinator. Equal ceilings do not require equal actual spend: spend is an outcome to measure. Use matched cases and a predeclared order/randomization scheme; concurrent versus sequential execution is not by itself proof of independence or fairness.
- Arm-independent grading with a bound source packet and opaque labels. A nonempty reviewer name, signature or `blinding_held=true` is evidence of a declaration, not independent proof of isolation. Record deviations and retain the affected case.

Keep trustworthy evidence, reliable completion/recovery, and useful reviewed output as separate endpoints. Choose acceptable tradeoffs before opening held-out results. A small pilot finds failure classes and estimates burden; it does not establish a low rare-failure rate or general harness efficacy. These are proposed experimental constraints, not measured results of this investigation.

## Smallest compatible remedy and external behavior seam

**Proposed specification boundary:**

1. Add one shared Q02 admission function used by the public verdict path before `decide`. Reject duplicate-key/nonstandard numeric JSON and malformed types/identities. Require explicit integrity answers, an attributable adjudication record, source/measurement binding and a declared count unit. Preserve unknown/incomplete evidence as `inconclusive` with reasons; malformed records should fail without a verdict or traceback. Do not weaken the frozen-checkpoint or quarantine checks.
2. Separate package inventory from eligible results. Retain the inventory for diagnosis, but admit M1 only from an explicit independently assessed result manifest, with source revision and package-to-result mapping. Version this measurement contract; do not silently reinterpret old measurements or recompute historical verdicts. Legacy inputs lacking the admission evidence should remain inconclusive for new comparisons. Resolving the original private preregistration, if later authorized, may refine compatibility but must not change historical facts retrospectively.
3. Preserve the distinction between M1's legacy package count and M6's root-cause equivalence groups. Validate a supplied package-to-group mapping; do not collapse M1 by root cause or assume group totals equal package totals. Compatibility with the frozen rule must be established before a newly decisive use; otherwise remain inconclusive. Validate the evidence supporting any M7 waste conclusion. General whole-harness comparisons use their own preregistered endpoints and study account, rather than inheriting Q02's threshold or subagent-count proxy.
4. Add no new executor. Exercise the existing public CLI with temporary synthetic measurement/worksheet files. Assert result text, blocker reasons, exit behavior and license; do not test only the pure helper. Retain explicit-failure and null-result controls. Test duplicate identities, contradictory mappings, missing run/config/source bindings, wrong types, input mismatch and partial accounting. Add public measurement cases covering legacy inventory versus revisioned/unreviewed folders. Existing quarantine tests remain regression obligations for a later implementation.

The retained metadata reproducer demonstrates this external Q02 seam already. A later implementation should change the seven favorable invalid-input outcomes into explicit admission failures or inconclusive results, while preserving an eligible control and the frozen license. The future eligible control must have real synthetic identity mappings and bound evidence; the present loose control is only a characterization of the old branch.

## Rival interpretation and unknowns

**Rival:** Q02 is a trusted operator's small case-study worksheet, and upstream human review supplies all omitted validation. This fits its limited scope and can make a manually checked, explicitly qualified use reasonable. It does not support the tool's stronger refusal claim, establish that callers performed those checks, or justify reuse for whole-harness decisions. A valid alternative to implementing the admission repair is to retire Q02 from future decision-making and use an independently reviewed offline protocol. Do not quietly retain its favorable verdict as authoritative while moving the checks into undocumented operator memory.

**Rival:** legacy `findings/` location already means “promoted.” That may explain the original counter. The active command neither proves that contract nor distinguishes it from the revisioned layout; current evidence supports explicit input-version admission rather than a historical invalidity claim.

**Rival:** flow telemetry was intentionally advisory, so duplicate observations and overlapping durations are not defects in its promised semantics. Agreed: they become material when its totals are used as unique compute, elapsed time or complete labor. Keep the advisory export; establish those additional semantics at the comparison boundary instead of turning telemetry into an authority source.

Unknown: actual incident frequency, completeness of private prior comparisons, all effective runtime settings, actual human minutes and spend, generalization across models/cases, and whether bookkeeping or model judgment dominates cost. No evidence here selects a new storage or runtime foundation. The narrower evidence is sufficient to specify reliable comparison inputs and complete accounting before such a choice.

## Read and execution inventory

Fully read in this lane: `AGENTS.md` 1–123; `docs/decisions/README.md` 1–26; `tools/q02_compare.py` 1–795; portable Q02 checkpoint 1–29; `tools/flow_telemetry.py` 1–239; `schemas/flow-telemetry.schema.json` 1–91; Decision6 measurement contract 1–171; `tools/intervention_ledger.py` 1–353; intervention schema 1–137; `tools/prepare-ab-study.py` 1–91. Research skill and GitHub-routing skill/reference were also read. The issue body was retrieved read-only.

Sampled: `tools/check-conformance.py` 910–943; `tools/quarantine-self-test.py` 440–472, 790–1000; `docs/engineering/002-decisions.md` 257–281; roadmap 136–156; template long-run README 42–66; `tools/research_telemetry.py` 1–45, 124–196; A/B preregistration schema 1–200, 205–303; `tools/engagement_state.py` 1270–1333, 1500–1511, 1919–1983; `tools/engagement_quarantine.py` 426–451; operator runbook 86–112; `engine/gates.md` 65–78; conformance workflow 1–38. Other files appearing in search output were search hits, not full reads. No intervention fixture contents or historical results were recomputed. A/B study-evidence schema was inventoried but not fully read; no claim of a complete readiness audit is made.

Principal read commands were `nl -ba <file> | sed -n '<range>p'` for the exact ranges above, plus `cat` for the two compact JSON artifacts. Caller searches and exact output are retained in [Q02 caller search](checks/evaluation/canonical/q02-all-static-callers.txt), [broad caller search](checks/evaluation/canonical/caller-search.txt), and [accounting caller search](checks/evaluation/canonical/accounting-callers.txt).

```sh
gh issue view 101 --repo matheusht/redteam-harness --json title,body,state,url
git rev-parse HEAD
git status --short
rg -n --hidden -g '!.git' -g '!.scratch/**' 'decide\(|q02_compare|M6_overlap|M1_findings|M5_subagents' .
git grep -n -I -E 'q02_compare|q02_module|M6_overlap|_measure_arm_snapshot|measure_arm\('
rg -n --hidden -g '!.git' -g '!.scratch/**' 'flow_telemetry|intervention_ledger|normalize_claude_code|export_flow\(' .
PYTHONDONTWRITEBYTECODE=1 python docs/research/harness-engineering-2026-09-05/checks/evaluation/probes.py
```

The original manifest includes every executed Q02/flow subprocess argument; the archived script also records the inspected benign bootstrap and pure conservative cost helper. The retained narrower reproduction manifest records its Q02 calls and explicitly limits flow coverage to pure helpers. The pre-existing `.scratch/` directory was untouched. Production source hashes were checked against `git show` at the pinned commit after the original probes. This lane added the research note and the retained benign evidence under `checks/evaluation/`; no production source was changed.

[q02-purpose]: https://github.com/matheusht/redteam-harness/blob/6a47b64264b6bf8f1edf8923847cfc9952cd1ab8/tools/q02_compare.py#L2-L30
[checkpoint]: https://github.com/matheusht/redteam-harness/blob/6a47b64264b6bf8f1edf8923847cfc9952cd1ab8/fixtures/preregistration/phase5-q02-prompt-ablation-portable.json#L1-L29
[checkpoint-admission]: https://github.com/matheusht/redteam-harness/blob/6a47b64264b6bf8f1edf8923847cfc9952cd1ab8/tools/q02_compare.py#L97-L216
[q02-counting]: https://github.com/matheusht/redteam-harness/blob/6a47b64264b6bf8f1edf8923847cfc9952cd1ab8/tools/q02_compare.py#L219-L398
[q02-worksheet]: https://github.com/matheusht/redteam-harness/blob/6a47b64264b6bf8f1edf8923847cfc9952cd1ab8/tools/q02_compare.py#L401-L418
[q02-measure]: https://github.com/matheusht/redteam-harness/blob/6a47b64264b6bf8f1edf8923847cfc9952cd1ab8/tools/q02_compare.py#L421-L519
[q02-admission]: https://github.com/matheusht/redteam-harness/blob/6a47b64264b6bf8f1edf8923847cfc9952cd1ab8/tools/q02_compare.py#L522-L603
[q02-tests]: https://github.com/matheusht/redteam-harness/blob/6a47b64264b6bf8f1edf8923847cfc9952cd1ab8/tools/q02_compare.py#L608-L795
[conformance]: https://github.com/matheusht/redteam-harness/blob/6a47b64264b6bf8f1edf8923847cfc9952cd1ab8/tools/check-conformance.py#L931-L933
[quarantine-callers]: https://github.com/matheusht/redteam-harness/blob/6a47b64264b6bf8f1edf8923847cfc9952cd1ab8/tools/quarantine-self-test.py#L797-L997
[research-costs]: https://github.com/matheusht/redteam-harness/blob/6a47b64264b6bf8f1edf8923847cfc9952cd1ab8/tools/research_telemetry.py#L129-L188
[research-sum]: https://github.com/matheusht/redteam-harness/blob/6a47b64264b6bf8f1edf8923847cfc9952cd1ab8/tools/research_telemetry.py#L22-L40
[flow-normalization]: https://github.com/matheusht/redteam-harness/blob/6a47b64264b6bf8f1edf8923847cfc9952cd1ab8/tools/flow_telemetry.py#L22-L89
[flow-export]: https://github.com/matheusht/redteam-harness/blob/6a47b64264b6bf8f1edf8923847cfc9952cd1ab8/tools/flow_telemetry.py#L134-L184
[flow-schema]: https://github.com/matheusht/redteam-harness/blob/6a47b64264b6bf8f1edf8923847cfc9952cd1ab8/schemas/flow-telemetry.schema.json#L10-L87
[flow-runbook]: https://github.com/matheusht/redteam-harness/blob/6a47b64264b6bf8f1edf8923847cfc9952cd1ab8/docs/decision-0006-operator-runbook.md#L97-L108
[intervention-schema]: https://github.com/matheusht/redteam-harness/blob/6a47b64264b6bf8f1edf8923847cfc9952cd1ab8/schemas/intervention.schema.json#L5-L107
[intervention-write]: https://github.com/matheusht/redteam-harness/blob/6a47b64264b6bf8f1edf8923847cfc9952cd1ab8/tools/intervention_ledger.py#L133-L167
[intervention-report]: https://github.com/matheusht/redteam-harness/blob/6a47b64264b6bf8f1edf8923847cfc9952cd1ab8/tools/intervention_ledger.py#L179-L233
[ab-prepare]: https://github.com/matheusht/redteam-harness/blob/6a47b64264b6bf8f1edf8923847cfc9952cd1ab8/tools/prepare-ab-study.py#L16-L74
[ab-matching]: https://github.com/matheusht/redteam-harness/blob/6a47b64264b6bf8f1edf8923847cfc9952cd1ab8/schemas/ab-preregistration.schema.json#L59-L139
