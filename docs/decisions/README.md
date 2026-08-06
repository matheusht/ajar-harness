# Decisions

Product and architecture decisions that should survive individual engagements.

Use this folder for choices that are more specific than `docs/architecture.md`, but more durable
than a one-off field note. Decision docs should explain:

- what was decided;
- why it matters;
- how future agents should act on it;
- what remains deliberately flexible.

## Index

- [0001 — Casebooks, pattern cards, and recon routing](0001-casebooks-patterns-routing.md)
- [0002 — GEPA autoresearch scope, DSPy posture, and capability ladder](0002-gepa-autoresearch-scope.md)
- [0003 — Autonomy envelopes](0003-autonomy-envelopes.md) — _superseded by 0004_
- [0004 — Epistemic autonomy and complexity budget](0004-epistemic-autonomy-complexity-budget.md) — **canonical autonomy + complexity policy**
- [0005 — Reasoning-directed, evidence-constrained research](0005-reasoning-directed-evidence-constrained-research.md) — **canonical live-research + evidence-state policy**; [implementation/evidence report](../decision-0005-implementation-report.md)
- [0006 — Agent-autonomous record kernel](../decision-0006-agent-autonomous-record-kernel.md) — **Notebook autonomy with authority-preserving async gates and advisory flow telemetry**
- [0007 — Black-box testing domain packs (web first, binary deferred)](0007-blackbox-testing-domain-packs.md) — **black-box web/API pack + vertical-first-then-horizontal rollout**; engine profile at [`engine/blackbox-web.md`](../../engine/blackbox-web.md)
- [0008 — Smart-contract (Solidity/EVM) audit capability](0008-smart-contract-audit-capability.md) — **EVM-first contract-audit capability: Foundry+Slither tool-family, thin-slice-first rollout, on-fork-PoC=Zone-2 fence, B1/B2-grounded severity**; build plan at [`docs/research/smart-contract-audit-capability-build-plan.md`](../research/smart-contract-audit-capability-build-plan.md)
