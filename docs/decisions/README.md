# Decisions

Product and architecture decisions that should survive individual engagements.

Before changing architecture, read [AGENTS.md](AGENTS.md) for current founder intent,
native-runtime reuse and questions that warrant founder input. The
[November plan](../research/oslit-engineering-plan-2026-11-14.md) is the endorsed
direction with Codex/OMP and duration corrections; the operator has now
[assigned implementation](../research/oslit-implementation-2026-11-14.md).
The [Q30 rationale](../research/oslit-harness-grilling-2026-11-13.md#q30--scored-search-within-a-task-minimal-native-tool-integration)
records why scored search stays within tasks and native reuse requires a minimal,
enforced controller interface. This planning direction does not amend runtime gates.

Use this folder for choices that are more specific than `docs/architecture.md`, but more durable
than a one-off field note. Decision docs should explain:

- what was decided;
- why it matters;
- how future agents should act on it;
- what remains deliberately flexible.

For the maintained engineering synthesis and implementation evidence, start with the [engineering wiki](../wiki/index.md). These decision records remain canonical; the wiki links to them and preserves their approval and supersession status.

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
- [0010 — Promotion gates: default-reject, computable where possible, and the fail-open lesson](0010-promotion-gates-and-fail-open.md) — **historical G0–G6 failure evidence; filing-boundary replacement remains incomplete in draft 0013**; doctrine at [`engine/finding-lifecycle.md`](../../engine/finding-lifecycle.md)
- [0011 — Depth over provability: partials, primitives, external calibration, and the authorization ceiling](0011-depth-external-calibration-ceiling.md) — **two audits measuring excess rigor, the 12-promotions/0-blocks result, and why the ceiling is scope not judgement**; ledger at [`tools/disposition_ledger.py`](../../tools/disposition_ledger.py)
- [0012 — Full autonomy as the north star: scope is the only human decision](0012-full-autonomy-north-star.md) — **RECORDED DIRECTION, not accepted**: the intended end state, the six preconditions none of which is met today, and the reframe that a hard gate is removed by BOUNDING the capability rather than by trusting supervision more

- [0013 — One versioned signed finding activation](0013-canonical-filing-contract.md) — **interim fail-closed draft; new positive filings unavailable because original G3/G6 producer is missing; #85 incomplete**
- [0014 — One durable engagement controller with native research runtimes](0014-native-engagement-team.md) — **accepted implementation direction; capability enforcement required before v2 activation; old routes unchanged**

The [native local research source route](../agents/native-local-research.md) is implemented as a
candidate for new local source research; the [legacy entry](../agents/legacy-local-research.md)
remains for supported existing queue/record work. This source implementation does not revise
accepted decisions or historical records. #165 adoption, #171 integrated qualification and #172
unfamiliar-target study remain open.
