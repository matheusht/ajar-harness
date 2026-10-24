# LLM application domain scope

This page holds the concrete benign-proxy and impact examples for the LLM-application domain. It is
a domain pack, not the generic authority fence: the [root README](../../README.md#scope-fence-read-first)
owns the route-neutral boundaries. Use this page when the selected route targets an LLM application.

| Boundary | What | Gate |
| --- | --- | --- |
| ✅ **Benign proxy** | system-prompt disclosure, refusal-flip on a *harmless* target, indirect-injection canary, excessive-agency / unsafe-render, cross-user canary propagation | signed scope and a benign `safe_signal` for every used vulnerability card |
| ⚠️ **Authorized impact-escalation** | a real PoC artifact to prove blast radius (e.g. a contained worm or exfiltration chain) | signed `scope.md` **+** fresh human confirmation **+** containment **+** cleanup obligation recorded at creation |
| ❌ **Never** | real-harm uplift as the product · a library of working harmful jailbreaks · HarmBench-style harm-elicitation as a metric · wholesale ingestion of harm corpora | No exceptions |

The legacy loop refuses to run without a filled and signed `scope.md`. Its cards use the
`skills/vulns/` `safe_signal` front matter. A target-specific exception belongs in that target's
signed scope; this domain page is not a portable grant.
