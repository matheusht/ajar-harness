# llm-redteam-harness

A **target-agnostic, portable** harness for **authorized** red-teaming of LLM / agentic
applications. It drives a target through a validated, OWASP-LLM-aligned checklist of
application-layer weaknesses, proves each finding against a ground-truth **oracle**, and
accumulates what it learns as reusable methodology.

> **Prime directive.** A red-team harness's product is **rigor, not findings**. It is engineered to
> **default to disbelief** and to **disprove itself before it is allowed to believe**. Success is not
> "found lots of issues" — it is being *more conservative than the operator's own intuition* about
> what counts as real.

## Scope fence (read first)

Three zones, enforced structurally (not just documented):

| Zone | What | Gate |
| --- | --- | --- |
| ✅ **Default — benign proxy** | system-prompt disclosure, refusal-flip on a *harmless* target, indirect-injection canary, excessive-agency / unsafe-render, cross-user canary propagation | a skill with no benign `safe_signal` **will not load** |
| ⚠️ **Authorized impact-escalation** | a real PoC artifact to prove blast radius (e.g. contained worm/exfil chain) | `scope.md` authorizes **+** runtime human-confirm **+** contained **+** cleanup-logged |
| ❌ **Never** | real-harm uplift as the product · a library of working harmful jailbreaks · HarmBench-style harm-elicitation as a metric · wholesale ingestion of harm corpora | — |

**Authorization is mandatory.** No `scope.md` filled and signed → the loop refuses to run.

## What it is / isn't

- It **is** a knowledge base of composable cards (vulns × techniques × oracles, plus **patterns** that
  route recon to the right cards) + one adaptive loop that reads them, driven by a single orchestrator
  with on-demand hunters, and **casebooks** of scrubbed prior engagements it learns from.
- It **isn't** a universal jailbreak generator, a payload arsenal, or a self-rewriting memory.

## Layout

```
skills/         PLANE 1 — methodology (read-only): vulns/ · techniques/ · oracles/ · patterns/
engine/         PLANE 2 — orchestration: loop · persistence · routing · roster · gates
schemas/        the contracts: attempt · finding · pattern · technique-card
fixtures/       sanitized oracle-calibration + routing-activation ground truth
casebooks/      PLANE 1 — scrubbed prior-engagement memory (routing + false-positive discipline)
engagements/    PLANE 3 — _TEMPLATE copied OUT into each target's own project repo (append-only)
tools/          conformance checker — the first mechanical gate
docs/           architecture + decisions + field-notes (cross-engagement methodology log)
```

**Plane rule:** Plane 1 is read-only knowledge; Plane 3 is write-only memory. The portable harness
(Plane 1+2) travels; each engagement's Plane 3 wiki lives with its target.

## Decision 0005/0006 record kernel

Decision 0006 keeps Decision 0005's evidence and authority boundaries while allowing the local
broker to maintain truthful Notebook records non-interactively. Consequential transitions use
lane-local digest-bound authority requests; Zone-2 creation requires either fresh confirmation or
a versioned local-only standing grant in the current signed scope, plus an open cleanup obligation.

New version-3 engagements use `python3 tools/run-engagement.py <subcommand> ...` as the sole public
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
[`docs/agents/docker-work-queue.md`](docs/agents/docker-work-queue.md) for the full host/image
contract, CLI template, broker/Stop flow, resource limits, and the distinction between real-Docker
fake-Claude containment evidence and credentialed live-Claude qualification.

The retrospective and A/B tools are offline evaluators only. They do not contact targets, authorize
Zone-2 work, file reports, promote memory/cards, or prove efficacy.

## Conformance (run before promoting any card / casebook change)

```
python3 tools/check-conformance.py     # stdlib only; exit 0 = clean
```

Structural gate (Phase 2.5A): front matter, pattern `activation` tiers, vuln `safe_signal`,
`routes_to` resolution + `stub:` quoting, casebook pattern-refs, and a casebook secret scan. **A green
run is required before a pattern/vuln/casebook change is promoted** (also enforced in CI —
`.github/workflows/conformance.yml`). It is structural, not a full schema validator; that's Phase 2.5.

## Naming & anonymization

- **Casebooks are strictly anonymized** — no client/marketing name beyond an abstract `target_class`,
  no live ids/tokens/URLs. Enforced by the schema rule + the conformance secret scan.
- **Plane-1 methodology files** (field-notes, fixtures, vuln-card lessons) MAY keep an operator-internal
  engagement label as *provenance* (it makes a lesson credible), but **never a secret** — the redaction
  rule still applies. This repo is private / operator-internal.
- **Before any external sharing**, run a pre-publish pass that replaces engagement labels with abstract
  handles. Until then, labels stay internal.

## Benchmark calibrations

The harness has been calibrated against public security/CTF benchmarks as a **capability + rigor
signal** (its own records are published under `engagements/`; the vendored third-party challenge
corpora and raw attempt logs are not redistributed). Every solve is **oracle-gated** (exact
flag-match → adjudication), driven by a single orchestrator with **fresh, never-contaminated Hunter
agents** and gray-box ground truth held only by the orchestrator.

| Benchmark | Scope run | Attempted | Confirmed (oracle-gated) | Result |
| --- | --- | --- | --- | --- |
| **XBOW / XBEN** (104 web CTF challenges) | all 104, all 25 tag categories | 104 / 104 | ~100 (99 distinct records) | ~96%, 0 dry |
| **Cybench** (40 pro CTF tasks) | Phase-1 = 18 Web+Crypto | 18 / 18 | 17 | ~94%, 0 dry; Phase-2 (13 Pwn/Rev/Forensics/Misc) deferred |
| **CVE-Bench** zero-day (40 real-world web CVEs) | all 40 proposed | 0 / 40 | 0 | **queued — authorized but not yet run** |

## Status

As of 2026-09-05, the repository includes the Decision 0005/0006 record kernel described above;
the original scaffold label no longer describes the whole implementation. Start with the
[decision index](docs/decisions/README.md) for accepted and superseded architecture decisions,
and the [engineering wiki](docs/wiki/index.md) for the current offline engineering delivery state
and its verification limits. The benchmark table above records earlier calibrations, not a fresh
execution result or authorization.
