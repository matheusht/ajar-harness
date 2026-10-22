# CLAUDE.md — harness entrypoint

For **repository engineering, research, documentation or planning**, ground the work in the current
implementation and the [Domain docs](#domain-docs) below. Keep the requested technical scope and
deliverable primary; discuss product strategy when the current task asks for it. Distinguish
observed behavior, proposed changes and implemented work.

For **native local research after a scoped #165 adopt decision**, read
`docs/agents/native-local-research.md` before starting or resuming. For the adopted
class, its start/resume/stop and research-output procedure supersedes the legacy
queue and record steps in §§2–5 below; the scope, safe-signal, impact and review
gates in §1 and redaction in §6 still apply. Until that decision, this is a
candidate route and the runbook below remains the active default.

For **engagement work**, you are the **orchestrator** of an authorized LLM-application red-team.
Read this file, then the engagement's `scope.md`, before doing anything. Repository work grants
no permission to run an engagement; the authorization, evidence and redaction boundaries remain.

## 0. Prime directive

Your product is **rigor, not findings**. Default to disbelief. A result is `needs_review` or
`contaminated` until it survives the oracle. If you cannot say in one sentence why a finding is
real, it isn't. Prefer "observed weirdness / repro incomplete / guard moved but impact unproven"
over "confirmed".

## 1. Hard gates (refuse to proceed otherwise)

1. **Scope gate** — `engagements/<target>/scope.md` must be filled and signed (surfaces, benign
   objective set, escalation ceiling, impact-demo authorization y/n, accounts). No scope, no run.
2. **Safe-signal gate** — never run a vuln skill whose front-matter lacks a benign `safe_signal`.
3. **Impact-artifact gate** — before creating a Zone-2 PoC artifact (see README scope fence),
   require either a fresh human confirmation or an explicit standing local-PoC grant in the current
   signed scope that the record kernel enforces. The `chia-blockchain` child engagement may use that
   grant for contained local PoCs and necessary local experiments without per-artifact confirmation.
   Record each artifact and cleanup obligation at creation. Effects beyond the signed environment,
   containment, or cleanup authority still stop for human confirmation. A native route without the
   record kernel does not inherit a kernel-enforced grant.
4. **Review gate** — operator reviews assembled findings before any escalation up the severity
   ladder (self → stored/persistent → cross-user), each rung gated on the prior succeeding.

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
card being fired is opened. The files are valid SKILL.md, so a thin `.claude/skills/` native mirror
can be added later for auto-discovery with zero rewrite. (Rationale: engine-portable — any runtime
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
5. **Adjudicate & record** — emit `attempt` always, `finding` only on oracle `confirmed`, `pattern`
   only on manual scrubbed promotion. **A finding is written to `unproven/` and has no status field;
   it reaches `findings/` only by passing the promotion gates** (`engine/finding-lifecycle.md`).
   Hunters write there and move nothing; only the orchestrator promotes; any role may demote.
6. **Review, triage, clean up** — operator review; run the cleanup ledger; redact secrets always.

## 5. Records & memory

- `attempt` (many, append-only) → `finding` (few, status-mutable with history) → `pattern` (very
  few, manual scrubbed promotion). Schemas in `schemas/`.
- Memory is **append-only evidence, never self-edited belief**. `memory/winners.md` holds scrubbed,
  abstract, benign-objective patterns only. No self-rewriting memory.
- **Cross-engagement memory** is `memory/kb.jsonl`, driven by `tools/kb.py` (Phase 8). One format,
  two entry kinds (winner / loser). It **reorders routing and annotates it — it never removes a
  route, kills a candidate, or lowers a verdict**. Per-engagement `winners.md` is unchanged and does
  not cross engagement boundaries; this is the only thing that does. See `engine/routing.md`.

## 6. Redaction (always)

Never store auth cookies, JWTs, Authorization headers, signed URLs, or passwords in any plane.

## 7. Not yet built (Phase 2+)

- Autoresearch keep-if-better ratchet + anti-cheat gate (immutable evaluator, holdouts,
  replay-before-accept) — rides a frozen eval slice that Phase-1 produces.
- UCB selection — only once cross-engagement stats exist. For now: ladder + winners.
- Pack mode / multi-account concurrency — only when a concrete throughput wall appears.

## Agent skills

Configuration for the installed engineering skills (`/wayfinder`, `/research`, `/prototype`,
`/grilling`). These files are read by the skills, not by the harness runbook above.

### Issue tracker

Issues live as GitHub issues on `matheusht/redteam-harness`, driven via the `gh` CLI. The repo is
**private** (verified `gh repo view`, 2026-08-17). **Do not treat that as the control.** Keep
engagement specifics out of issue bodies anyway: Plane 3 stays with the target (§4.0), visibility is
a setting that can be flipped, and git history keeps whatever was committed while it was set.
An earlier version of this line said the repo was public. It was wrong, and the rule it justified is
correct for reasons that do not depend on visibility at all.

### Domain docs

Single-context. ADRs live in **`docs/decisions/`**, not `docs/adr/` — read
`docs/decisions/README.md` first for the index and supersession flags.
