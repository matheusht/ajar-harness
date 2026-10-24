# Portable adaptive research acceptance

This records the operator's 21 October requirements for the new research route:
model, provider and agent runtime are replaceable execution choices; OpenCode is
the current qualification integration. Adaptation means observations changing the
investigation within a run. These checks supplement the native qualification
issues before adoption; they do not establish qualification or authorize a target.

## Implemented entry path

The shared [research workflow](../../engine/native-research-workflow.md) uses an
ordinary notebook, scripts and results. A filesystem-capable agent can follow it
with a task brief and an independently enforced run boundary; no native session
ID is needed to express the investigation. This is a portable method, not proof
that another runtime's tools or effect limits work.

The current OpenCode integration is `tools/native_research.py`. `prepare` freezes
the workflow and brief and seeds `/workspace/RESEARCH.md`. Research and continuation
receive those files through read-only `/research`, including a host-derived
`RUN.json` snapshot before each turn. The snapshot reports the shared allowance
at that instant; it does not grant effects, reset spend, or replace the host's
enforcement. Use `resume --help` for the existing native session, or
`reconstruct --help` for a fresh session using the same workspace and run. Both
retain the run's allowance and refuse unresolved prior dispatches. Keep material
observations and the final internal result in ordinary files: a transcript or a
successful dispatch alone cannot establish that those records are complete.

The [provider-free workflow checks](PORTABLE-RESEARCH-WORKFLOW-CHECKS.md) exercise
this plumbing. The observable research behaviors below still need native runs.

## Keep the research state portable

The ordinary workspace must preserve the objective, target/source identity,
allowed effects and roles, remaining allowance, hypotheses, experiment scripts,
observations, unfinished conditions, review and cleanup state. Use existing files
and tools. Runtime-specific session storage can add continuity, but it cannot be
the sole source of the research state.

Keep native launch, session restoration, tool capture and provider configuration
in the runtime integration. The research workflow must not require an OpenCode
session ID, provider-specific message format, fixed action queue, or new optimizer
to express a hypothesis, run its experiment, preserve a result or request review.
Runtime identity still belongs in evidence and in the effect-control boundary.

Before each acceptance scenario, freeze the supplied brief, checks, source and
runtime configuration, allowance and independent observations. Preserve failed
and unavailable results. Report support for the combinations actually exercised;
an implementation boundary alone does not prove a second runtime works.

## Required observable behavior

| Check | Passing evidence | Failure or limitation |
| --- | --- | --- |
| Portable continuation | A fresh context can reconstruct the actual hypotheses, experiments, source, pending effects and remaining allowance from the workspace and independent run record. Native-history restoration and reconstruction are distinguished. | A lost native conversation erases a material condition, silently resets spend, or causes an uncertain effect to be repeated. |
| Evidence-driven revision | An observed experiment result changes a stated hypothesis, required condition, instrument or next discriminating experiment. The trace identifies the relevant observation and actual subsequent action. | A restated plan, cosmetic input variation, or setup failure presented as a security result. Immediate valid discovery remains valid, but does not demonstrate this capability. |
| Alternatives and refutation | A held path is narrowed or refuted while an independently supported alternative remains available. A genuinely refuted lead can end; a budget stop preserves unreviewed work as unfinished. | A strong prior overrides contradictory evidence, one failed path closes every alternative, or persistence mandates endless work. |
| Discovered conditional chain | The researcher identifies a connection without receiving the sequence. Actual output/state from one step supplies the next step under compatible actors, resources, version, timing and environment. Clean complete replay and a relevant control establish the claimed effect. | Independently reproduced parts cannot compose, synthetic state supplies the missing transition, or a written narrative substitutes for execution. Preserve valid partial results. |
| Original observation | Protected capture binds the researcher's actual test and result to the source, conditions and session/tool dispatch. Host replay is separately labeled; missing capture or bypass stays visible. | Host-issued checks are credited as the researcher's original observation, or an unobserved route is silently treated as captured. |
| Fresh review | A fresh context receives the exact claim, source, raw and contrary evidence; performs a material independent check; and produces its own conclusion. Changed inputs invalidate affected reviews and dependent claims. | A role label, fixture transfer, signature or synthetic response is called independent model review. |
| Stop, resume and output | The chosen runtime observes the shared allowance, stops new effects at its tested boundary, reconciles uncertain effects before retry, preserves useful state, and verifies owned cleanup. The final internal result reflects the final evidence and review. | A new context restores budget, a stopped provider leaves uncontrolled target dispatch, or a cleanup/status statement substitutes for observation. |

These can share a small set of scenarios; each need not create another fixture or
framework. The first unhinted application run remains governed by
[#160](https://github.com/matheusht/redteam-harness/issues/160). If it does not
exercise revision or chaining, report those as unobserved and use a separate
bounded scenario. Do not supply the hidden answer to manufacture a pass.

## Completion boundary

Use actual original effects, clean replay/control, fresh review and relevant
boundary/recovery checks to decide readiness for the explicitly tested local
research class. Save repeatable commands, exact inputs, requirements, expected and
observed results, source changes and assistance. The final integrated revision
must pass the affected public workflows before default cutover or retirement.

Ordinary internal reporting, legacy signed filing and external submission have
separate authority and evidence. Cross-run harness optimization, model rankings,
distributed swarm infrastructure, and an optional procedure comparison are not
prerequisites for this in-run capability.
