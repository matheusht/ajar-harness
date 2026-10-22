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

Both local routes use the same scope fence. The legacy kernel enforces its
record gates; the native entry must check the signed scope and card safe signal
before a run:

| Zone | What | Gate |
| --- | --- | --- |
| ✅ **Default — benign proxy** | system-prompt disclosure, refusal-flip on a *harmless* target, indirect-injection canary, excessive-agency / unsafe-render, cross-user canary propagation | signed scope and a benign `safe_signal` for every used vulnerability card |
| ⚠️ **Authorized impact-escalation** | a real PoC artifact to prove blast radius (e.g. contained worm/exfil chain) | signed `scope.md` **+** fresh human confirmation or kernel-enforced standing local-PoC grant **+** containment **+** cleanup obligation recorded at creation |
| ❌ **Never** | real-harm uplift as the product · a library of working harmful jailbreaks · HarmBench-style harm-elicitation as a metric · wholesale ingestion of harm corpora | — |

**Authorization is mandatory.** The legacy loop refuses to run without a filled and
signed `scope.md`. The native runner binds scope bytes to its plan approval, but
its entry procedure must verify the signature and each used card's benign
`safe_signal`; the runner does not check either one itself.

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
engagements/    PLANE 3 — legacy _TEMPLATE copied OUT into each target's own project repo
tools/          conformance checker — the first mechanical gate
docs/           architecture + decisions + field-notes (cross-engagement methodology log)
```

**Plane rule:** Plane 1 is read-only knowledge; Plane 3 is write-only memory. The portable harness
(Plane 1+2) travels; each engagement's Plane 3 wiki lives with its target.

## New local source research — candidate native default

The [native entry](docs/agents/native-local-research.md) is the source route for
new local source research in this candidate branch: prepare a signed target-local
scope, brief and allowance, then use its persistent run root, review and internal
result. The [bootstrap skill](skills/source-engagement-bootstrap/SKILL.md) ranks
source targets and prepares that handoff. Issues #166–170 implement the source
change; #165 remains open, so this is neither live qualification nor a scoped
adoption decision. An actual run still needs its signed scope, plan-bound
approval and supported runtime. The [cutover contract](docs/agents/native-cutover-contract.md)
records the remaining checks.

## Existing queue and record engagements

The [legacy entry](docs/agents/legacy-local-research.md) retains Decision
0005/0006, the governed queue, canonical records and historical readers for
supported existing work. Its [Docker work-queue contract](docs/agents/docker-work-queue.md)
and [source bootstrap branch](skills/source-engagement-bootstrap/references/legacy-bootstrap.md)
remain available. New local source research uses the native entry above; this
source change does not convert, rewrite or grade historical engagements.

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

The repository retains the Decision 0005/0006 record kernel for existing work and now
contains the candidate native source default for new local source research. #165
qualification/adoption and the final E2E remain open. Start with the
[decision index](docs/decisions/README.md) for accepted and superseded architecture decisions,
and the [engineering wiki](docs/wiki/index.md) for the current offline engineering delivery state
and its verification limits. The benchmark table above records earlier calibrations, not a fresh
execution result or authorization.
