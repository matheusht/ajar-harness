## Research resolution

The next comparison must name the required observation/recovery contract before selecting a runtime. The inspected sources support selected input shaping and cooperative pause/resume, but do not establish arbitrary-loss recovery, complete provider-effective history or full cost accounting.

Three boundaries discriminate candidates: the request actually received at an adapter after normalization; interruption/termination versus artifact effects and receipts; and a persisted context boundary honored on reopen. The strongest deeper-ownership case is a missing compound contract across those facts. A supported extensible runtime remains a serious rival to a narrow fork or owned loop.

Pinned sources: OpenAI Agents Python `f1f35031d364f9f0d8e94dda0853c92abefdccff`; Claude Agent SDK Python `b1b838b1c5730a7a0b270915a79b15861a8ca716`; Posthorse `8d45703e5e4cb1fd52cba956ca024f3892219220` and its required Pi host `f9b06177e565f70cd243a785d088d1c491830dbd`. Selected tests and control flow were inspected, not executed. [Normalized dispatch](https://github.com/openai/openai-agents-python/blob/f1f35031d364f9f0d8e94dda0853c92abefdccff/src/agents/run_internal/run_loop.py#L2169-L2259), [outcome parser contract test](https://github.com/anthropics/claude-agent-sdk-python/blob/b1b838b1c5730a7a0b270915a79b15861a8ca716/tests/test_message_parser.py#L1259-L1281), [orderly rollover/reopen test](https://github.com/fitchmultz/pi-posthorse/blob/8d45703e5e4cb1fd52cba956ca024f3892219220/test/integration/posthorse-in-pi.test.ts#L271-L305).

Prepare a benign document/correction packet with client-managed scripted-adapter observations, late results, cooperative pause and explicit uncertainty after an artifact write without a receipt. Rollover remains optional unless selected as a required behavior. A protocol or synthetic trace cannot award execution proof to a candidate.

No runtime, adapter, provider call or paid comparison was implemented. No winner was selected. Source inspection reached the intended decision boundary; actual interface-fit and maintenance benefits await a later run with fixed configuration and complete accounting.

Local context: research commit `d150f8d0`, branch `codex/research-harness-engineering-2026-09-05`, note `docs/research/harness-engineering-2026-09-05/foundations.md`. Local only; not pushed. The proposed preparation ticket is reviewable with the rest of the specification and does not authorize runtime execution.
