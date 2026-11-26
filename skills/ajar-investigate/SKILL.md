---
name: ajar-investigate
description: Execute focused code investigation inside Ajar v3.6 WorkspaceTools, SpanTracker, EpistemicGuard, and stigmergic whiteboard coordination to produce falsifiable candidates.
---

# Ajar Investigate (`v3.6-Balanced`)

Use this skill to audit mapped surfaces and sinks, coordinate with parallel swarm workers through `.ajar/WHITEBOARD.md`, obey `EpistemicGuard` provenance checks, and emit falsifiable `Candidate` records into `.ajar/candidates.jsonl`.

## 1. Coordinate Through `.ajar/WHITEBOARD.md` (`whiteboard.py`)

1. Read `.ajar/REALITY.md` and `.ajar/WHITEBOARD.md` before opening files.
2. Post a `claim` event (`20m` TTL evaporation) for the target seam so parallel workers (`surface_scout`, `deep_auditor`, `bounty_resolver`, `downstream_prover`) do not duplicate effort.
3. Post durable discoveries as append-only events into `.ajar/events.jsonl`:
   - **`insight`:** Concrete code behavior or reachability path with exact `file:start-end` span.
   - **`invariant`:** Proven compensating guard with the exact `file:line` where it executes.
   - **`effect`:** Observed partial primitive tagged with `EffectType` and `CarrierKind` for `chain_weaver.py`.
   - **`wish`:** Blocked Crown-Jewel sink describing the upstream `EffectType` and `CarrierKind` needed to unlock it.
   - **`dead_end`:** Closed path with verified guard locus so no worker re-audits it.

## 2. Work Inside `EpistemicGuard` (`epistemic.py`)

`EpistemicGuard` never blocks bash or reads proactively, but enforces four mechanical hygiene checks:

1. **Observed-Span Provenance (`SpanTracker`):** Read every `entry_span` and guard callee directly via `read_file` before citing it. Never hypothesize line numbers or claim a guard holds without reading its body.
2. **Sink Counterfactual Closure (`check_sink_counterfactual`):** Before closing a sink as safe (`dead_end`), open every guard helper called along the path. Unopened guard callees trigger a reopen warning.
3. **Rut Detection (`check_rut`):** Five consecutive read/search steps with Jaccard overlap `>= 0.80` (and no `exec_cmd` run) trigger a rut alert. Pivot to a new seam or run a concrete `exec_cmd` experiment immediately.
4. **Pre-Prove Gate (`on_pre_prove`):** Every candidate submitted for verification must have:
   - an observed `entry_span` (`path:start-end`) recorded in `SpanTracker`,
   - a concrete, executable `repro_cmd` (never `todo`, `placeholder`, `echo`, or `<angle_bracket>` stubs), and
   - a concrete `failure_oracle` referencing a real sanitizer, assertion, panic, revert, invariant, or differential mismatch.

## 3. Respect Swarm Pacing & Context Relays (`swarm.py`, `agent.py`)

- **Context Relay (`65%` / `70%`):** Summarize open hypotheses, observed spans, and next probes onto `.ajar/WHITEBOARD.md` before context recycle so the next worker resumes cleanly.
- **45-Minute Stagnation Pivot:** If a seam yields zero new effects, wishes, or candidates for `45m`, post a `dead_end` or `wish` and pivot to an unaudited `bounty`.
- **92% Budget Drain:** Once `CostMeter` hits `92%` of `--budget-usd`, stop new exploration and drain remaining budget into `ajar verify` for queued candidates.
- **Domain Packs:** Consult `skills/domains/<domain>/SKILL.md` only when matching the target domain; otherwise derive invariants from first principles in target code.

## 4. Emit Structured Candidates (`.ajar/candidates.jsonl`)

Append each concrete finding to `.ajar/candidates.jsonl` matching `cli.Candidate`:
- `id`, `title`, `severity`, `category` (`advisory` or `hardening`)
- `entry_span` (`rel/path:start-end`) and `sink_symbol`
- `repro_cmd` and concrete `failure_oracle`
- minimal `patch_diff`, concise `root_cause`, and proven `impact`
- `chain_hops` (for multi-step chains) and `build_profile` (`upstream`, `debian`, or `al2023`)

Keep prose strictly structural (entrypoint -> missing guard -> broken invariant -> concrete outcome). Never fabricate command output or stack traces.
