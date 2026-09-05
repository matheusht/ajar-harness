# Supported recovery contracts for offline document processing

Research note · 2026-09-05 · [issue #103](https://github.com/matheusht/redteam-harness/issues/103)

## Answer and boundary

Supported interfaces already express selected context changes, ordered late input and cooperative pause/resume. The inspected evidence does **not** make a compact fork or an owned loop necessary for those capabilities alone. It also does not establish complete effective-history reconstruction, arbitrary-crash recovery or complete cost accounting. The next specification must name the receipt and interruption boundary it requires before selecting a foundation.

The strongest deeper-ownership case is a missing compound contract: the same durable state must identify the prepared request, outstanding offline artifact work and a context boundary, without reconstructing those relationships across incompatible interfaces. That is a hypothesis worth testing, not an observed requirement to replace the current runtime. A supported extensible implementation remains an equally serious candidate.

Scope: benign versioned document review and local artifact processing. No provider/model calls, paid execution, target operations, new runtime, tracker changes or broad framework survey. Source and existing test bodies were inspected; **no tests were executed**. Assertions below describe what pinned tests check, not independently reproduced passing results.

## Source identity and confidence

| Source | Exact inspected boundary | Confidence and limit |
| --- | --- | --- |
| OpenAI Agents Python SDK | `f1f35031d364f9f0d8e94dda0853c92abefdccff`, commit 2026-09-05 01:01:56 UTC | High confidence in inspected Python control flow and test assertions; no provider or deployment verification. Selected files/ranges only. |
| Claude Agent SDK Python | `b1b838b1c5730a7a0b270915a79b15861a8ca716`, commit 2026-09-04 19:58:48 UTC; source declares SDK `0.2.152`, bundled CLI `2.1.261` | High confidence in wrapper/parser contracts. The bundled binary's internal implementation and ordinary emissions were not audited. |
| Posthorse extension | `8d45703e5e4cb1fd52cba956ca024f3892219220`, commit 2026-09-05 01:20:57 UTC | README, relevant source and integration assertions inspected. Tests use a faux provider. |
| Required Pi fork | `f9b06177e565f70cd243a785d088d1c491830dbd`, commit 2026-09-04 11:40:05 UTC | Selected native context-window implementation and projection tests inspected; no disk-crash or provider test. |
| DeepSeek Harness | `d347e703908d0406b7a7ef80e3a0e594d86b2215` | Prior architecture/invariant inspection reused for candidate fairness, without expanding this investigation. Developer preview and documented recovery gaps. |
| Current repository | `6a47b64264b6bf8f1edf8923847cfc9952cd1ab8` in the isolated engineering checkout | Prior bounded driver/adapter inspection reused. No ordinary-session acceptance test. |

UTC dates above avoid confusing September 5 UTC commits with September 4 local dates. Live Claude documentation was read September 5 and is secondary to pinned code for the wrapper's actual accepted fields.

## Gap 1 — Which request does the record actually describe?

**Implementation observation.** OpenAI's `call_model_input_filter` receives a copied input list and instructions, validates the returned `ModelInputData`, and supports synchronous or asynchronous callbacks. In the inspected streamed path, the runner then deduplicates returned items, updates server-continuation tracking, invokes `on_llm_start`, and eventually passes the normalized input and other configuration to the model adapter. Therefore a receipt recorded *inside the filter* can differ from the later SDK dispatch. The later hook exposes normalized instructions/items, but not all dispatch arguments; model settings, tools, output schema and continuation identifiers are separate arguments. Neither observation point is automatically a durable receipt or provider acceptance. [O1][O1] [O2][O2]

**Test evidence inspected.** `test_call_model_input_filter_sync_non_streamed` and its streamed counterpart assert that a `ScriptedModel` receives changed instructions/items. Duplicate-output tests assert that the later duplicate wins; ordering tests preserve a call before its result. These are meaningful transport-independent checks of context shaping. They do not prove an exact HTTP request, provider processing or model understanding. [O3][O3]

With client-managed history, the pending-input test expects initial request, tool call, tool result and late correction in order. With server-managed continuation it instead expects only the unsent tool result and correction plus `previous_response_id`. A delta is not the full effective history. Another test deliberately raises during a model request after local input admission: pending input may already be empty while the admitted item remains recoverable. Thus “admitted locally,” “adapter called,” and “provider accepted” must stay distinct. [O4][O4] [O5][O5]

**Implication.** Changing history selection is supported and does not justify a custom loop by itself. For an offline comparison, use an explicitly declared client-managed context and a scripted model that records its received arguments. If the requirement is full provider-effective-history reconstruction, these tests cannot establish it; that requirement may need a different continuation mode or remain unverifiable. Do not silently upgrade a local dispatch record into proof of model comprehension.

## Gap 2 — Pause, cancellation, termination and durable recovery differ

**OpenAI implementation/test observation.** `cancel(mode="after_turn")` requests completion of the current turn, including pending tools, before stopping. Immediate cancellation cancels tasks and clears queues. The documented API requires continued stream consumption to finish cancellation. Tests assert that soft cancellation executes both tools in a batch, stops before another model request, preserves result state, and admits a late correction exactly once after the previous tool output on resume. Their “exactly once” assertions concern the tested local input/tool sequence, not arbitrary external side effects. [O6][O6] [O7][O7] [O4][O4]

`RunState.to_json()` returns a serializable dictionary; `to_string()` returns JSON. Those calls do not themselves atomically store a checkpoint with an artifact write. Restoring requires an initial agent definition; some custom context types require a deserializer or override. The current schema is `1.17`. Historical compatibility tests inspect durable fields and idempotent rewrites. The corpus explicitly distinguishes genuine historical-writer fixtures from relabeled canonical-compatibility fixtures; these must not all be called historical outputs. [O8][O8] [O9][O9] [O10][O10]

**Claude implementation/test observation.** The Python SDK locates a bundled CLI or other configured executable and launches a subprocess. Its cleanup gives the process time to flush before termination, and shields cleanup from AnyIO-scope cancellation. The source explicitly documents a remaining limitation for raw asyncio cancellation, which can interrupt escalation; a remaining child is retained for exit-time handling. Existing fake-CLI tests assert reaping under AnyIO cancellation. They do not establish arbitrary parent/host-loss containment or the binary's complete persistence behavior. [C1][C1] [C2][C2] [C3][C3]

The result parser preserves `subtype`, `is_error`, `stop_reason`, `terminal_reason`, error details and usage separately. One test supplies `subtype="success"` with `is_error=True` and `api_error_status=529`; another supplies success with `terminal_reason="aborted_tools"`. **This establishes the SDK parser's accepted combinations and the tests' contract, not how often the bundled runtime emits them.** A success subtype alone is therefore an inadequate completion predicate. [C4][C4] [C5][C5] [C6][C6]

Cost is another partial account. Parser tests preserve `modelUsage` and allow absent optional fields. The live loop documentation says crash-result cost may be zeroed and `usage` covers the main loop while `modelUsage` covers the tree. That runtime accounting claim was not independently reproduced. OpenAI's soft-cancel usage test asserts a positive request count, not complete token or dollar attribution. Neither SDK total includes human repair or infrastructure automatically. Missing usage remains unknown, not zero. [C7][C7] [C8][C8] [O7][O7]

**Implication.** Specify cooperative pause and arbitrary process loss separately. For an offline artifact written before its receipt/checkpoint, require a truthful uncertain outcome and reconciliation rule; do not demand or claim exactly-once effects from a saved conversation alone. If a required cancellation mode cannot reach a recoverable boundary through supported controls, that is a concrete reason to compare a wrapper fix, another runtime, a narrow fork and an owned loop.

## Gap 3 — A host-level context boundary can be a real missing contract

Posthorse is a precise example, not a general endorsement of forks. Its extension checks for fork-only native context methods. The host records `context_window` entries, and its context projection starts at the newest such entry on the selected branch. Host tests assert that old messages are excluded, branch context remains separate, and model/thinking settings survive. [P1][P1] [P2][P2] [P5][P5] [P6][P6]

The extension integration test loads Posthorse in the real fork's harness with a faux provider. It requests rollover alongside a failing sibling tool, asserts no boundary for that failed batch, then requests a successful rollover and reopens the saved session to assert the new window's context. Another test carries bounded text from a recorded but unconsumed result, retaining an ID to retrieve the rest; stale checkpoint material is subordinate to current inputs/results. [P3][P3] [P4][P4]

**Limits.** This tests orderly batch and reopen semantics. It is not evidence of atomic disk durability under power loss, restoration of in-flight processes, or lower operator effort. Unpatched Pi is unsupported by this extension; that does not prove every other runtime lacks an equivalent supported interface. Recovery size and reminders are bounded/best-effort. [P1][P1]

**Specific deeper-ownership trigger.** If the required behavior is a persisted no-summary context boundary that commits only after the current batch reaches its defined successful boundary and is honored on reopen, and the chosen host cannot express it through supported interfaces, a host change becomes a legitimate candidate. The comparison should include another extensible runtime before concluding that a full owned loop is necessary.

## Fair candidate comparison

| Candidate | Supported or inspected capability | Unproved boundary / next question |
| --- | --- | --- |
| Current supervisor + native session | Outer repetition and ledger-derived completion; limited-content adapter metadata | Can record-derived recovery supply the required offline account without inner conversation reconstruction? Current code intentionally does not retain everything. |
| Supported SDK | OpenAI has prepared-input shaping and explicit paused state; Claude exposes wrapper events, outcomes and cleanup controls | These SDKs expose different boundaries. Neither test set here proves arbitrary crash recovery or complete effective history. |
| Extensible internals | DeepSeek supplies replaceable components and a check over selected loop-built request fields | Its journal check is not provider-internal reconstruction. Hard loss before stream settlement leaves no durable attempt stream; interrupted-turn repair remains a consumer responsibility. [D1][D1] [D2][D2] |
| Narrow fork | Posthorse/Pi demonstrates one concrete missing host boundary with faux-provider integration assertions | Maintain both extension and host pins; measure divergence and recovery behavior rather than assuming a small diff is cheap forever. |
| Owned model loop | Could unify the specific request/context/unfinished-work contract and make experiments easier to instrument | Hypothesis only. It must replace existing obligations, not merely move them into new code. No winner or implementation size established. |

Current baseline sources: [driver](/Users/matheusvsky/Documents/trab/llm-redteam-harness-engineering/tools/work_queue_driver.py:619), [adapter](/Users/matheusvsky/Documents/trab/llm-redteam-harness-engineering/tools/claude_work_session.py:1). Storage backend, provider and billing remain separate choices from loop ownership.

## One discriminating benign comparison, proposed only

Use synthetic document v1, a correction producing v2, and an offline artifact derived from one named revision. A deterministic scripted model supplies identical responses; no real provider, network tool or engagement data is needed. Keep the grader outside the worker's records.

Compare only the claimed interfaces, with these checkpoints: (1) prepared input normalized before adapter invocation; (2) v2 result recorded but not yet supplied; (3) cooperative pause after the tool batch; (4) simulated process loss after an artifact write but before its receipt; (5) optional no-summary rollover and clean reopen. The last case tests a separate requirement; a candidate must not be penalized for lacking it unless that requirement was selected beforehand.

For each checkpoint, require an account of source revision, locally admitted input, actual scripted-adapter arguments, recorded result, unfinished work, terminal/error flags and unknown effects. Record observed usage separately from absent usage. Check duplicate input and artifact work, lost corrections, false completion, restart consistency, and human repair steps. Count adapter code, compatibility commitments and machinery removed as engineering burden. Compare the current baseline with a supported extensible candidate; include the fork/owned-loop candidates where an actual unsupported contract remains.

This proposed comparison can resolve interface fit and deterministic accounting. It cannot establish model quality, provider-effective context, paid cost, production reliability or rare-event rates. Existing source tests are evidence for choosing checkpoints, not results of this comparison.

## Next specification boundary and unsupported assumptions

The next spec must choose: the exact observation point constituting a request receipt; client-managed versus server-managed context; cooperative pause versus process-loss semantics; whether no-summary persisted rollover is required; and what data may be retained. It should not choose a framework first.

Still unsupported: that ordinary sessions match these source versions; that hooks cannot mutate later inputs; that a local call reached or was accepted by a provider; that serialization is durably committed; that custom context/agent code can be restored without a pinned definition; that SDK outcomes prove document correctness; that SDK usage includes missing failed requests, external tools or labor; that any candidate reduces total maintenance. Retention of complete requests would also change the current limited-content policy and is not authorized by this note.

Stop condition reached: three consequential gaps identified, bounded source/test evidence collected, and the next comparison/spec boundary is explicit. No runtime was implemented and no candidate was declared the winner.

## Pinned references

[O1]: https://github.com/openai/openai-agents-python/blob/f1f35031d364f9f0d8e94dda0853c92abefdccff/src/agents/run_internal/turn_preparation.py#L51 "OpenAI input preparation"
[O2]: https://github.com/openai/openai-agents-python/blob/f1f35031d364f9f0d8e94dda0853c92abefdccff/src/agents/run_internal/run_loop.py#L2169 "OpenAI streamed filter, normalization, hooks and dispatch"
[O3]: https://github.com/openai/openai-agents-python/blob/f1f35031d364f9f0d8e94dda0853c92abefdccff/tests/test_call_model_input_filter.py#L17 "OpenAI filter tests"
[O4]: https://github.com/openai/openai-agents-python/blob/f1f35031d364f9f0d8e94dda0853c92abefdccff/tests/test_run_state_pending_input.py#L136 "OpenAI pending-input tests"
[O5]: https://github.com/openai/openai-agents-python/blob/f1f35031d364f9f0d8e94dda0853c92abefdccff/tests/test_run_state_pending_input.py#L522 "OpenAI failed-request admission tests"
[O6]: https://github.com/openai/openai-agents-python/blob/f1f35031d364f9f0d8e94dda0853c92abefdccff/src/agents/result.py#L819 "OpenAI cancellation implementation"
[O7]: https://github.com/openai/openai-agents-python/blob/f1f35031d364f9f0d8e94dda0853c92abefdccff/tests/test_soft_cancel.py#L73 "OpenAI soft-cancel tests"
[O8]: https://github.com/openai/openai-agents-python/blob/f1f35031d364f9f0d8e94dda0853c92abefdccff/src/agents/run_state.py#L1774 "OpenAI RunState serialization"
[O9]: https://github.com/openai/openai-agents-python/blob/f1f35031d364f9f0d8e94dda0853c92abefdccff/tests/fixtures/run_state/README.md "OpenAI compatibility corpus provenance"
[O10]: https://github.com/openai/openai-agents-python/blob/f1f35031d364f9f0d8e94dda0853c92abefdccff/tests/test_run_state_compatibility_corpus.py#L165 "OpenAI compatibility assertions"
[C1]: https://github.com/anthropics/claude-agent-sdk-python/blob/b1b838b1c5730a7a0b270915a79b15861a8ca716/src/claude_agent_sdk/_internal/transport/subprocess_cli.py#L788 "Claude subprocess launch"
[C2]: https://github.com/anthropics/claude-agent-sdk-python/blob/b1b838b1c5730a7a0b270915a79b15861a8ca716/src/claude_agent_sdk/_internal/transport/subprocess_cli.py#L943 "Claude cleanup contract and limitation"
[C3]: https://github.com/anthropics/claude-agent-sdk-python/blob/b1b838b1c5730a7a0b270915a79b15861a8ca716/tests/test_close_cancellation.py#L101 "Claude cleanup tests"
[C4]: https://github.com/anthropics/claude-agent-sdk-python/blob/b1b838b1c5730a7a0b270915a79b15861a8ca716/src/claude_agent_sdk/_internal/message_parser.py#L308 "Claude result parser"
[C5]: https://github.com/anthropics/claude-agent-sdk-python/blob/b1b838b1c5730a7a0b270915a79b15861a8ca716/tests/test_message_parser.py#L1259 "Claude success-subtype/error-flag test"
[C6]: https://github.com/anthropics/claude-agent-sdk-python/blob/b1b838b1c5730a7a0b270915a79b15861a8ca716/tests/test_message_parser.py#L866 "Claude terminal-reason test"
[C7]: https://github.com/anthropics/claude-agent-sdk-python/blob/b1b838b1c5730a7a0b270915a79b15861a8ca716/tests/test_message_parser.py#L1150 "Claude usage and absent-field tests"
[C8]: https://code.claude.com/docs/en/agent-sdk/agent-loop "Claude SDK loop documentation"
[P1]: https://github.com/fitchmultz/pi-posthorse/blob/8d45703e5e4cb1fd52cba956ca024f3892219220/README.md "Posthorse pinned requirements and limits"
[P2]: https://github.com/fitchmultz/pi-posthorse/blob/8d45703e5e4cb1fd52cba956ca024f3892219220/index.ts#L107 "Posthorse native-host guard"
[P3]: https://github.com/fitchmultz/pi-posthorse/blob/8d45703e5e4cb1fd52cba956ca024f3892219220/test/integration/posthorse-in-pi.test.ts#L271 "Posthorse rollover and reopen integration test"
[P4]: https://github.com/fitchmultz/pi-posthorse/blob/8d45703e5e4cb1fd52cba956ca024f3892219220/test/integration/posthorse-in-pi.test.ts#L79 "Posthorse unconsumed-result integration test"
[P5]: https://github.com/fitchmultz/pi/blob/f9b06177e565f70cd243a785d088d1c491830dbd/packages/coding-agent/src/core/session-manager.ts#L438 "Pi host context-window projection"
[P6]: https://github.com/fitchmultz/pi/blob/f9b06177e565f70cd243a785d088d1c491830dbd/packages/coding-agent/test/session-manager/build-context.test.ts#L223 "Pi host context-window tests"
[D1]: https://github.com/deepseek-ai/deepseek-harness/blob/d347e703908d0406b7a7ef80e3a0e594d86b2215/docs/architecture.md "DeepSeek prior inspected architecture"
[D2]: https://github.com/deepseek-ai/deepseek-harness/blob/d347e703908d0406b7a7ef80e3a0e594d86b2215/packages/core/agent-loop/src/invariant.ts "DeepSeek prior inspected request invariant"
