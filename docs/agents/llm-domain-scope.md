# LLM application domain scope

This page preserves the concrete benign-proxy and impact examples for the
LLM-application domain. It is a domain pack, not the generic harness authority
fence. The [root README](../../README.md#scope-fence-read-first) owns the
route-neutral boundaries; use this page when the selected route is an LLM
application.

| Boundary | What | Gate |
| --- | --- | --- |
| ✅ **Benign proxy** | system-prompt disclosure, refusal-flip on a *harmless* target, indirect-injection canary, excessive-agency / unsafe-render, cross-user canary propagation | signed scope and a benign `safe_signal` for every used vulnerability card |
| ⚠️ **Authorized impact-escalation** | a real PoC artifact to prove blast radius (e.g. contained worm/exfil chain) | signed `scope.md` **+** fresh human confirmation or a target-local standing local-PoC grant recorded in that signed scope **+** containment **+** cleanup obligation recorded at creation |
| ❌ **Never** | real-harm uplift as the product · a library of working harmful jailbreaks · HarmBench-style harm-elicitation as a metric · wholesale ingestion of harm corpora | — |

The legacy loop refuses to run without a filled and signed `scope.md`. The native
entry must verify the signed scope and every used card's benign `safe_signal`; the
runner does not check either one itself. Target-specific standing grants belong
in the target's signed scope, not in this domain page.
