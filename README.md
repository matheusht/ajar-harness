# llm-redteam-harness

The harness is being developed as a **domain-neutral, portable** system for
**authorized security research**. A capable researcher uses source, tools,
experiments and runtime feedback inside an explicit authority and evidence
boundary. LLM application security is one domain; the retained LLM cards are a
domain pack, not the whole product. The repository name is historical.

> **Prime directive.** A red-team harness's product is **rigor, not findings**. It is engineered to
> **default to disbelief** when confirming a claim. A claim stays unconfirmed until it has an
> execution observation, a relevant control, and a clean replay. A narrative, report match, or
> model agreement cannot supply missing execution evidence. Discovery preserves plausible leads;
> reporting stays within supported conditions. A supported effect and unfinished deeper work can
> coexist.

Read [product and engineering direction](docs/wiki/product-and-engineering-direction.md)
for the north stars and design choices, and [native research status](docs/wiki/native-research-status.md)
for the dated implementation and qualification boundary. The product is intended to
be model/provider independent; the current native integration supports a narrower,
explicit set of runtimes and model routes.

## Scope fence (read first)

Both local routes use the same three authority boundaries. Each route and domain
supplies its own benign objective set and safe-signal cards. The LLM-application
examples are in [LLM domain scope](docs/agents/llm-domain-scope.md); source
research uses the [source engagement bootstrap](skills/source-engagement-bootstrap/SKILL.md).

| Boundary | What | Gate |
| --- | --- | --- |
| ✅ **Authorized local research** | a benign objective set declared in the signed target-local scope, run only inside the declared local environment | signed scope + the route's benign `safe_signal` for every used card + effect, containment and cleanup ceiling |
| ⚠️ **Authorized impact-escalation** | a real PoC artifact to prove blast radius (e.g. contained worm/exfil chain) | signed `scope.md` **+** fresh human confirmation or a target-local standing local-PoC grant recorded in that signed scope (kernel-enforced where the route uses the kernel) **+** containment **+** cleanup obligation recorded at creation |
| ❌ **Never** | real-harm uplift as the product · a library of working harmful jailbreaks · HarmBench-style harm-elicitation as a metric · wholesale ingestion of harm corpora | — |

**Authorization is mandatory.** The legacy loop refuses to run without a filled and
signed `scope.md`. The native runner binds scope bytes to its plan approval, but
its entry procedure must verify the signature and each used card's benign
`safe_signal`; the runner does not check either one itself.

## Research model

A research workflow combines reusable cards, tools, oracles, patterns and scrubbed
casebooks. The researcher chooses and revises the investigation; the harness
preserves authority, evidence, continuity and review obligations.

## Layout

```
skills/         PLANE 1 — methodology (read-only): LLM-domain cards + source bootstrap; shared patterns/oracles
engine/         PLANE 2 — native research method + retained legacy orchestration
schemas/        the contracts: attempt · finding · pattern · technique-card
fixtures/       sanitized oracle-calibration + routing-activation ground truth
casebooks/      PLANE 1 — scrubbed prior-engagement memory (routing + false-positive discipline)
engagements/    PLANE 3 — legacy _TEMPLATE copied OUT into each target's own project repo
tools/          native runner + candidate continuation · retained legacy tools · conformance
docs/           architecture + decisions + field-notes (cross-engagement methodology log)
```

The portable methodology/runtime travels; target state and evidence stay with the
target. Legacy records retain their append-only and immutable-history rules.
Native research uses ordinary working files in its persistent run root and keeps
protected host evidence separate. Use the selected route's actual record contract.

## New local source research — candidate native default

The [native entry](docs/agents/native-local-research.md) is the candidate source
route for new local source research: prepare a signed target-local scope, brief
and allowance, then use its persistent run root, review and internal result. The [bootstrap skill](skills/source-engagement-bootstrap/SKILL.md) ranks
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

The record lifecycle layer (attempt start/finish, bounded negative results and
evidence-bundle manifests) is recorded in
[research lifecycle](docs/research-lifecycle.md).

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
  rule still applies. Keep internal labels internal; repository visibility is not a redaction control.
- **Before any external sharing**, run a pre-publish pass that replaces engagement labels with abstract
  handles. Until then, labels stay internal.

## Earlier benchmark calibrations

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
the [engineering wiki](docs/wiki/index.md) for topic navigation, and
[native research status](docs/wiki/native-research-status.md) for the dated capability
assessment. September delivery and earlier benchmark records retain their original
scope; they are not fresh execution results or authorization.
