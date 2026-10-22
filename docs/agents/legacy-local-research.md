# Existing queue and record engagements

Use this route for a supported existing engagement that depends on the
Decision 0005/0006 queue, record kernel, or historical ledger, and for work
explicitly assigned to that legacy runtime. New local source research is
prepared through the [native entry](native-local-research.md), with execution
subject to the signed scope, plan-bound approval and supported runtime. #165
qualification/adoption remains open; this source route does not claim it.
Root `AGENTS.md` / `CLAUDE.md` gates and the signed target-local scope still
control every action. Keep historical records and active engagements intact.

For a legacy source bootstrap, use the
[existing-engagement bootstrap procedure](../../skills/source-engagement-bootstrap/references/legacy-bootstrap.md)
and its [entry/resume reference](../../skills/source-engagement-bootstrap/references/goal-template.md#entry-and-resume-procedure).

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
5. **Adjudicate & record** — emit `attempt` always. Keep incomplete proposals in `unproven/`.
   Canonical finding revisions are immutable and carry the exact independently reviewed claim
   state (`supported`, `confirmed`, `contaminated`, or `refuted`); filing does not imply oracle
   confirmation. Use the admitted `request-authority` → `resolve-authority` →
   `settle-approved-revision` (or `revise-finding`) path in `tools/run-engagement.py`.
   Only a committed activation establishes active membership. The old `promote` route is not a
   substitute for this signed revision path; patterns still need manual scrubbing.
   Issue #85 remains incomplete: without an independently qualified producer of original target
   privilege and impact-state origin/reachability, the interim draft refuses new `supported` or
   `confirmed` filings with `filing_original_observation_unavailable`. Signed negative filing
   and historical replay remain available. This hold is not retained-gate equivalence or adoption.
6. **Review, triage, clean up** — operator review; run the cleanup ledger; redact secrets always.

## 5. Records & memory

- `attempt` (many, append-only) → `finding` (few, immutable canonical revisions) → `pattern`
  (very few, manual scrubbed promotion). Schemas in `schemas/`; the committed activation and
  reviewed claim state control current finding membership.
- Memory is **append-only evidence, never self-edited belief**. `memory/winners.md` holds scrubbed,
  abstract, benign-objective patterns only. No self-rewriting memory.
- **Cross-engagement memory** is `memory/kb.jsonl`, driven by `tools/kb.py` (Phase 8). One format,
  two entry kinds (winner / loser). It **reorders routing and annotates it — it never removes a
  route, kills a candidate, or lowers a verdict**. Per-engagement `winners.md` is unchanged and does
  not cross engagement boundaries; this is the only thing that does. See `engine/routing.md`.

## Legacy Decision 0005/0006 record kernel

Decision 0006 keeps Decision 0005's evidence and authority boundaries while allowing the local
broker to maintain truthful Notebook records non-interactively. Consequential transitions use
lane-local digest-bound authority requests; Zone-2 follows the impact-artifact gate above.

Legacy version-3 engagements use `python3 tools/run-engagement.py <subcommand> ...` as their public
Plane-3 authority. Append-only ledgers are authoritative; snapshots and Markdown are derived. See
`docs/decision-0005-implementation-architecture.md`,
`docs/decision-0005-implementation-report.md`, and
`docs/decision-0006-agent-autonomous-record-kernel.md` for commands, trust boundaries, migration, telemetry,
and the precise distinction between conformance, regression parity, and efficacy.

To drain the reducer-owned queue, use `tools/run-work-queue.py run` with absolute canonical paths to
one target repository and its own `engagements/<id>` directory, plus explicit session-count,
wall-admission, and per-session timeout bounds. The public CLI requires `--session-backend docker`
and every Docker resource limit; there is no implicit host-process fallback. Supply an ordered
reviewer pool by repeating `--reviewer-model`; the driver selects the first model distinct from the
exact subject origin and required prior reviewer lineage, or pauses once as
`reviewer_model_unavailable` without launching or retry-spinning.

Before a run may end as `budget_bounded`, freeze the coverage corpus and put the manifest bytes'
`sha256:...` digest on the exact `Frozen corpus enumeration SHA256` line in `scope.md` before the
initial scope is signed. A later scope re-attestation cannot introduce or replace this genesis pin.
After kernel initialization and before the run, register that exact manifest and
its linked enumeration as engagement artifacts. Pass the registered manifest artifact ID to the
driver as `--corpus-enumeration-ref <artifact-id>`. The digest in scope binds the permitted bytes;
the CLI value names the registered artifact carrying those bytes. The option may be omitted for a
run that will not declare a budget boundary, but if a session or wall ceiling is reached without it
the driver returns `operator_required` and does not record `budget_bounded`.

The Docker backend currently accepts only non-root Apple Silicon macOS with a local Docker Desktop
Linux/arm64 engine that exposes the required cgroup-v2, seccomp, memory, swap, and PID controls.
Unsupported hosts fail before the model starts. The runtime accepts only an already-cached immutable
`repository@sha256` image and uses `--pull never`; the image must contain the operator-named absolute
Claude and Python executables.

`max_wall_seconds` is the deadline for admitting another action, not permission to cancel a trusted
record transaction halfway through. An action admitted before that deadline must quiesce; terminal
reducer state then takes precedence. The result always reports both total `wall_seconds` and any
`wall_deadline_overrun_seconds`, so a completed in-flight action cannot hide cleanup or commit time.

The driver mounts the exact target directly at `/workspace`, this harness at `/harness`, and only
repeated operator-declared regular files at deterministic `/inputs/NNN` paths, all read-only. It
rejects optional directories and special files and never discovers or mounts target workspaces
centrally. A PID-1 supervisor owns every descendant, retains
the per-session broker HMAC key behind a local semantic relay, and installs the authenticated Stop
backstop. `/scratch` and `/dev/shm` are tmpfs filesystems with separate hard byte and inode limits;
PID 1 traces the descendant tree and brokers scalar writes through an inherited seccomp listener.
It uses the exact writer TID plus a thread-scoped pidfd to duplicate one stable descriptor, snapshots
at most 16 MiB of write data, and never uses notification `CONTINUE`. Only bounded tmpfs regular-file
`ENOSPC`/`EDQUOT` or a positive short result latches storage failure; ordinary pipe/socket partial
writes retain their result. The Docker profile names `SYS_PTRACE` only to admit the required broker
syscalls through the built-in seccomp policy; non-root PID 1 and the model both prove all usable
capability sets are zero under `no-new-privileges`. Reserved exit 73 maps only to
`driver_session_storage_exceeded`; broker/setup failure maps to sanitized internal failure.
Timeout, interrupt, parent death, and normal completion clean the exact container and network IDs,
not same-uid processes.

The session bridge permits provider egress. Its removal ends the container's credential and network
authority, but it cannot undo disclosure that occurred before teardown or revoke an upstream token.
Use scoped, short-lived model credentials. See
[Docker work queue](docker-work-queue.md) for the full host/image
contract, CLI template, broker/Stop flow, resource limits, and the distinction between real-Docker
fake-Claude containment evidence and credentialed live-Claude qualification.

The retrospective and A/B tools are offline evaluators only. They do not contact targets, authorize
Zone-2 work, file reports, promote memory/cards, or prove efficacy.

## 7. Not yet built (Phase 2+)

- Autoresearch keep-if-better ratchet + anti-cheat gate (immutable evaluator, holdouts,
  replay-before-accept) — rides a frozen eval slice that Phase-1 produces.
- UCB selection — only once cross-engagement stats exist. For now: ladder + winners.
- Pack mode / multi-account concurrency — only when a concrete throughput wall appears.

