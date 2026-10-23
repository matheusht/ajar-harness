# Legacy queue and record engagements

Use this route for a supported existing engagement that depends on the Decision 0005/0006 queue,
record kernel or historical ledger, and for work explicitly assigned to that runtime. New local
source research is not this route: the candidate native route is external
[PR #192](https://github.com/matheusht/redteam-harness/pull/192) and is **not on `main`**. Do not
infer its behavior here, and do not convert, rewrite or re-grade a historical engagement.

The root [entrypoint](../../AGENTS.md) gates and the signed target-local scope still control every
action. See the [harness flow](../harness-flow.md) for the stage overview, the
[research lifecycle](../research-lifecycle.md) for attempt and bounded-negative records, the
[Docker work-queue contract](docker-work-queue.md) for the full host/image boundary, and the
[session-end backstop](session-end-backstop.md) for the computed-queue Stop check.

## 2. Roles (put cognition where the leverage is)

- **Orchestrator (you, top model):** plan, select cards, validate vs oracle, score, adapt, triage,
  enforce gates. **Never touches the target except to establish a session.**
- **Hunter (mid model):** drive the target, run ONE card with a bounded brief, return a structured
  `attempt`. May propose `suspected_success`; **only the orchestrator/oracle emits `confirmed`.**
- **Helper (cheap model):** offline only — DOM scrape, transcript diff, dedup. Never touches target.

Single agent first. The shared browser serializes live work anyway; parallelism is a config knob
(concurrency 1→N) gated on `scope.md`, not an architecture.

## 3. How skills are loaded (decision: portable + deterministic)

Cards live as plain `SKILL.md` under `skills/{vulns,techniques,oracles,patterns}/`. The orchestrator loads
the **exact** card for the current objective by id (Read the file) — deterministic, not fuzzy
description-matching, which suits a rigor-first harness. Context stays lean because only the one
card being fired is opened. (Rationale: engine-portable — any runtime
reads markdown; deterministic — the orchestrator, not the model, picks the card.)

## 4. The runbook (legacy engagement)

0. **Bootstrap** — copy `engagements/_TEMPLATE/` into the **target's own** project repo as
   `engagements/<id>/` (Plane 3 lives with the target, never in this portable repo). **Then start
   the record kernel, before any recon or attempt**, and prove it:
   `./.venv/bin/python tools/finding_lifecycle.py preflight --engagement engagements/<id>`.
   A kernel started mid-run is retroactively fatal: work done before it cannot cite a ledger row, so
   it can never clear G1 or G2. `exodus-2026-08` initialized on day 3 of a three-day run and
   stranded 16 of 19 packages that way — real work, controls named with `file:line`, permanently
   unpromotable. Gate `GK` re-checks this at promotion, which is far too late to help.
1. **Ground & scope** — read prior intel; fill + sign `scope.md`; pick the active OWASP subset (LLM07
   ships as a full vuln card; the rest of OWASP-LLM are planned/stub — scope selects from what exists).
   *Scope varies per project — be prepared for all.*
2. **Establish the oracle** — load `skills/oracles/`; calibrate against `fixtures/` or source.
3. **Recon → routing** — authenticate, snapshot surfaces/tools/flows, capture **baseline controls**
   (what the target refuses with no attack). Then **emit activation signals**: for each observation,
   name which `skills/patterns/` (and vuln) cards it lights up (`strong/weak/negative`) per
   `engine/routing.md`. Those signals select the cards for the loop. The orchestrator may use, ignore,
   or override an activated card, but records one line on why for a **strong** signal on a high-impact
   path. `negative` signals (a control that looks correctly enforced) are recorded as likely-held +
   positive-control candidates, not findings. **After activation — never before — run the
   cross-engagement KB pass** (`tools/kb.py query` / `route`): it reorders and annotates the
   activated set with what previous engagements proved, and never removes a card (`D-09`). At close,
   promote winners and losers back with `tools/kb.py add`; a loss must name the control that held,
   and an entry that changes no routing decision is not promoted.
4. **Loop** (`engine/loop.md`) — ladder + winners, bounded chunks, oracle every result,
   loop-until-coverage-or-dry. A refusal is an input to the next rung; the terminal verdict is
   "coverage/dry", never "the model finally complied". When evidence (a confirmed finding, a `strong`
   signal, or an operator prior) says a vuln is *present*, switch to **persistence mode**
   (`engine/persistence.md`): bound the space, treat a held vector as a wrong turn not a dry verdict,
   grade leads top-to-bottom through the funnel, backtrack / redo recon rather than tunnel-vision, and
   keep the rigor bar and gates unchanged.
5. **Record the lifecycle** — before target contact, start the attempt with `attempt-start`; after the
   oracle, finish it with `attempt-finish` and a `cost_status`; an exhausted lane gets
   `record-negative`, never an implied finding. These are notebook records: they grant no authority
   and change no coverage or closure verdict. See [research lifecycle](../research-lifecycle.md).
6. **Adjudicate & record** — after `attempt-finish`, write a finding package only when it warrants a
   promotion attempt; `pattern` only on manual scrubbed promotion. **A finding is written to
   `unproven/` and has no status field; it reaches `findings/` only by passing the promotion gates**
   (`engine/finding-lifecycle.md`). Hunters write there and move nothing; only the orchestrator
   promotes; any role may demote. Every gate can say no, and a partial package stays in `unproven/`
   with its proven stages and its `what_would_close_it` stated.
7. **Review, triage, clean up** — operator review; run the cleanup ledger; redact secrets always.

## 5. Records & memory

- `attempt` (many, append-only) → `finding` (few, immutable revisions; starts in `unproven/`) →
  `pattern` (very few, manual scrubbed promotion). Schemas in `schemas/`.
- Memory is **append-only evidence, never self-edited belief**. `memory/winners.md` holds scrubbed,
  abstract, benign-objective patterns only. No self-rewriting memory.
- **Cross-engagement memory** is `memory/kb.jsonl`, driven by `tools/kb.py` (Phase 8). One format,
  two entry kinds (winner / loser). It **reorders routing and annotates it — it never removes a
  route, kills a candidate, or lowers a verdict**. Per-engagement `winners.md` is unchanged and does
  not cross engagement boundaries; this is the only thing that does. See `engine/routing.md`.

## Legacy Decision 0005/0006 record kernel

Decision 0006 keeps Decision 0005's evidence and authority boundaries while allowing the local
broker to maintain truthful Notebook records non-interactively. Consequential transitions use
lane-local digest-bound authority requests; Zone-2 still requires a fresh human confirmation before
creation (see [LLM domain scope](llm-domain-scope.md) for the LLM-domain examples).

Legacy version-3 engagements use `python3 tools/run-engagement.py <subcommand> ...` as their public
Plane-3 authority. Append-only ledgers are authoritative; snapshots and Markdown are derived. See
[the implementation architecture](../decision-0005-implementation-architecture.md), its
[implementation report](../decision-0005-implementation-report.md), and
[Decision 0006](../decision-0006-agent-autonomous-record-kernel.md) for commands, trust boundaries,
migration, telemetry, and the distinction between conformance, regression parity, and efficacy.

Queue draining uses `tools/run-work-queue.py run` with canonical target/engagement paths and
explicit session, wall and timeout bounds. The public CLI requires `--session-backend docker` and
every Docker resource limit. Before a `budget_bounded` ending, freeze and register the coverage
corpus and pass its `--corpus-enumeration-ref`; a missing denominator returns `operator_required`.
`max_wall_seconds` bounds admission, not an already-admitted record transaction, and status reports
both total wall time and any overrun. The full host/image, broker/Stop, storage, mount and CLI
contract is in the [Docker work-queue doc](docker-work-queue.md) and the
[session-end backstop](session-end-backstop.md). Retrospective and A/B tools are offline only.

## 7. Not yet built (Phase 2+)

- Autoresearch keep-if-better ratchet + anti-cheat gate (immutable evaluator, holdouts,
  replay-before-accept) — rides a frozen eval slice that Phase-1 produces.
- UCB selection — only once cross-engagement stats exist. For now: ladder + winners.
- Pack mode / multi-account concurrency — only when a concrete throughput wall appears.
