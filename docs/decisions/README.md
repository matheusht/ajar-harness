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
- [0009 — Kernel upgrade path: decision-0005 → decision-0006 with orphan reconciliation](0009-kernel-upgrade-migration.md) — **operator-console-signed in-place kernel migration + orphan reconciliation (`migrate-kernel`)**
- [0010 — Promotion gates: default-reject, computable where possible, and the fail-open lesson](0010-promotion-gates-and-fail-open.md) — **the G0–G6 stack, why each gate exists, and the four instruments that returned a pass without running**; doctrine at [`engine/finding-lifecycle.md`](../../engine/finding-lifecycle.md)
- [0011 — Depth over provability: partials, primitives, external calibration, and the authorization ceiling](0011-depth-external-calibration-ceiling.md) — **two audits measuring excess rigor, the 12-promotions/0-blocks result, and why the ceiling is scope not judgement**; ledger at [`tools/disposition_ledger.py`](../../tools/disposition_ledger.py)
