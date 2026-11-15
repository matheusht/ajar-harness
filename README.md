# llm-redteam-harness

A **domain-neutral, portable** harness for **authorized** security research. A researcher works
inside an explicit authority and evidence boundary; LLM application security is one supported
domain whose retained cards are a domain pack, not the product boundary. The repository name is
historical.

> **Prime directive.** The product is **rigor, not findings**. A claim is confirmed only with an
> execution observation, a relevant control, and a clean replay. A narrative, report match, or model
> agreement cannot supply missing execution evidence.

**Agent entrypoint:** [`AGENTS.md`](AGENTS.md) routes repository work, legacy queue/record work,
lifecycle records, the candidate native route and qualification claims. `CLAUDE.md` is kept
byte-identical to it.

## Current scope

The Decision 0005/0006 record kernel and [research lifecycle](docs/research-lifecycle.md)
remain for existing contracts. New research enters the candidate Codex/OMP v2
workflow. [Decision 0015](docs/decisions/0015-initial-scope-autonomy.md) adopts its
explicit initial-scope authority policy and default caller routing. Runtime
qualification, sustained operation and the operator's fresh-target study remain
separate from that policy decision; the candidate branch is not a release.

## Scope fence (read first)

The fence is generic. Each route and domain supplies its own benign objective set and safe-signal
cards.

| Boundary | What | Gate |
| --- | --- | --- |
| ✅ **Authorized local research** | a benign objective set declared in the signed target-local scope, run only inside the declared local environment | signed scope **+** a benign `safe_signal` for every used card **+** the declared effect, containment and cleanup ceiling |
| ⚠️ **Authorized impact-escalation** | a real PoC artifact to prove blast radius (e.g. a contained worm or exfiltration chain) | signed scope **+** containment **+** recorded cleanup; v2 `initial-scope-v1` preauthorizes in-scope artifacts, other routes require fresh human confirmation |
| ❌ **Never** | real-harm uplift as the product · a library of working harmful jailbreaks · HarmBench-style harm-elicitation as a metric · wholesale ingestion of harm corpora | — |

**Authorization is mandatory.** No filled and signed `scope.md` → the legacy loop refuses to run.

LLM-domain examples are disclosed in [LLM domain scope](docs/agents/llm-domain-scope.md): benign
system-prompt disclosure, refusal flip on a harmless target, indirect-injection canaries,
excessive agency / unsafe rendering, and cross-user canary propagation. The never-boundary holds
across domains.

## Route quickstart

| Work | Start at |
| --- | --- |
| Repository engineering, research, docs or planning | [`AGENTS.md`](AGENTS.md), then [the layout](#layout) and [decision index](docs/decisions/README.md) |
| Existing queue/record engagement | [legacy queue and record entry](docs/agents/legacy-local-research.md) |
| Attempts, bounded negatives, evidence bundles | [research lifecycle](docs/research-lifecycle.md) |
| New source, binary, application or combined research | [v2 engagement guide](docs/agents/engagement.md) and [initial-scope autonomy](docs/decisions/0015-initial-scope-autonomy.md); runtime qualification remains separate |
| Explicit v1 native inputs or existing v1 run | [v1 compatibility guide](docs/agents/native-local-research.md) |
| Capability, readiness or qualification claim | [engineering wiki](docs/wiki/index.md), then its source evidence |

## Layout

```
skills/         PLANE 1 — methodology (read-only): vulns/ · techniques/ · oracles/ · patterns/
engine/         PLANE 2 — orchestration: loop · persistence · routing · roster · gates · lifecycle
schemas/        the contracts: attempt · finding · pattern · technique-card · lifecycle records
fixtures/       sanitized oracle-calibration + routing-activation ground truth
casebooks/      PLANE 1 — scrubbed prior-engagement memory (routing + false-positive discipline)
engagements/    PLANE 3 — _TEMPLATE copied OUT into each target's own project repo (append-only)
tools/          record kernel, research lifecycle, work queue, conformance
docs/           architecture + decisions + agents + research + wiki
```

**Plane rule:** Plane 1 is read-only knowledge; Plane 3 is write-only memory. The portable harness
(Plane 1+2) travels; each engagement's Plane 3 records live with its target.

## Conformance

```sh
python3 tools/check-conformance.py     # stdlib only; exit 0 = clean
```

Structural gate: front matter, pattern `activation` tiers, vuln `safe_signal`, `routes_to`
resolution plus `stub:` quoting, casebook pattern-refs, and a casebook secret scan. A green run is
required before a pattern/vuln/casebook change is promoted (also enforced in CI). It is structural,
not a full schema validator, and it does not prove a research result.

## Naming & anonymization

- **Casebooks are strictly anonymized** — no client or marketing name beyond an abstract
  `target_class`, no live ids/tokens/URLs. Enforced by the schema rule and the conformance scan.
- **Plane-1 methodology files** may keep an operator-internal engagement label as *provenance*,
  but never a secret. Keep internal labels internal; repository visibility is not a redaction
  control.
- **Before external sharing**, replace engagement labels with abstract handles. Until then they
  stay internal.

## Links

- [Decision index](docs/decisions/README.md) — accepted and superseded architecture decisions.
- [Engineering wiki](docs/wiki/index.md) — maintained engineering synthesis and its dated state.
- [Architecture](docs/architecture.md) and [harness flow](docs/harness-flow.md).
- [Benchmark results and comparison](docs/research/benchmark-results-and-comparison.md) — earlier
  calibrations, not a fresh execution result or authorization.
- [Docker work-queue contract](docs/agents/docker-work-queue.md) and
  [session-end backstop](docs/agents/session-end-backstop.md).
- [LLM domain scope](docs/agents/llm-domain-scope.md) and
  [legacy queue and record entry](docs/agents/legacy-local-research.md).

## Status

Dated pointer, 2026-10-23: the [engineering wiki](docs/wiki/index.md) holds the maintained
engineering synthesis and its dated delivery state; recheck the source commit and issue state
before acting. The wiki's own status is an observation, not a live tracker. The candidate native
route is present in this checkout; #165 adoption, #171 integrated qualification and #172
unfamiliar-target study remain open. It must not be described as qualified or adopted. Earlier
benchmark records retain their original scope.
