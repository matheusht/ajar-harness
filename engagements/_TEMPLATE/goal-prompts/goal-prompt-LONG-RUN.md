# Goal prompt — LONG-RUN single-asset deep hunt (standard format)

> **This is the standard goal-prompt format for a LONG-RUN (6+ hour, multi-round, one-asset) deep hunt.**
> Copy it into `engagements/<id>/goal-prompts/<id>-goal-prompt-longrun-<asset>.md` and fill every `<...>`
> with verified facts. The section skeleton is the constant; the LLM adapts depth to the domain.
>
> **Pick the right template.** `goal-prompt-START.md` opens an engagement across many surfaces.
> `goal-prompt-REVISIT-ESCALATION.md` re-runs a closed engagement for escalation. **This one** points a
> multi-round agent portfolio at ONE asset and runs until a terminal verdict — use it when the asset is
> big enough to hold several independent mechanism families, and the operator will not be available to
> steer for hours.
>
> Binding gates (`CLAUDE.md`, `scope.md`, `engine/*`) always override this template. The engine doc that
> governs the round loop is `engine/multi-round-orchestration.md`; read it before filling this in.
>
> **Provenance and what we changed.** The multi-agent search heuristics derive from Kues (Searchlight
> Cyber, 2026-07-20), who adapted them from OpenAI's CDC conjecture-search prompt. That method was
> reproduced once independently, on a different language and stack, by swapping the target. Two published
> successes with an unknown denominator — nobody blogs the runs that found nothing. Treat it as a
> promising method, not a measured one. **Three of its instructions are inverted here**: the asserted
> vulnerability (Part 1), the fixed six-hour floor (Part 11), and the missing reportability gate
> (Part 12). Part 0 explains why.

---

## Part 0 — The anti-bias construction (read before filling anything in)

The source method opens with *"the source in this repository has a vulnerability that can be exploited
from pre-authentication to RCE."* That single sentence is what makes the method persistent, and it is
the one thing that must not be copied.

It works by making "I found nothing" an unacceptable answer. It makes it unacceptable by making it
**false by construction**. Point that at a clean codebase and the run cannot terminate honestly: the only
reachable exit is the one it was told to expect, so it manufactures one. Our targets are frequently
clean, and `covered-dry` is a correct and valuable product for us. It is not for a vendor blog.

We keep the persistence and drop the bias with three moves.

**1. Symmetric exit obligation — replaces the asserted bug.** Both exits cost the same, so neither is
the lazy one:

> Exactly one of two statements about this surface is true. Either a reachable flaw exists on it, or
> every mechanism family on it is bounded by a control you can name and demonstrate. Proving either takes
> the same work. You may not return until you have proven one. **"I did not find anything" proves
> neither and is not a terminal state.**

`covered-dry` carries a payload (Part 12). A model cannot reach it by getting tired.

**2. Bias placement by lane — the prior is allowed where it is cheap.**

| Lane | Optimistic prior | Cost if the prior is wrong |
|---|---|---|
| Hunter | **allowed and encouraged** — "assume the developer made a mistake here; find it" | wasted compute, extra candidates |
| Refuter / oracle / adjudicator | **forbidden — never told a flaw is expected** | a false report to a vendor |

A hunter cannot emit `confirmed` (`CLAUDE.md` §2), so its bias is contained. The orchestrator's standing
duty is to stop the hunter's prior from leaking into a refuter's brief. A refuter brief that says
"confirm this bug" has already failed.

**3. Effort framing, never verdict framing.** *"It's possible; if you give up you're not trying hard
enough"* and *"be more stubborn than the developer was careful"* are correct instructions about **how
long to work** and false instructions about **what to conclude**. Use them in Part 11 only, scoped to
effort. Never let them reach Part 12.

---

## Part 1 — Current task statement

GOAL: long-run white-box exhaustion of **<ASSET>** — <ONE-LINE DESCRIPTION OF WHAT IT DOES AND WHO
TALKS TO IT>. Program: <PROGRAM NAME / PLATFORM / reward basis; or "no formal program — <DISCLOSURE
REALITY>">. Audit baseline pinned at <TAG / COMMIT / ARTIFACT SHA256>, mirrored at <LOCAL_PATH>
(identity recorded in `progress.md`).

<STATE THE SURFACE. DO NOT STATE THAT A FLAW EXISTS.> The attacker-reachable surface of this asset is
<SURFACE: entry points, parsers, routes, RPCs, message types, config loaders>. The impact classes that
would matter are <IMPACT CLASSES, ranked>.

Exactly one of two statements about that surface is true: a reachable flaw exists on it, or every
mechanism family on it is bounded by a control you can name and demonstrate. Both cost the same to
prove. Return only when one is proven. **"I did not find anything" is not a terminal state.**

Work from first principles by reading the code. **Do not diff against a patched version, read
changelogs, read release notes, read git history, or search the web for known issues in this asset** —
those routes rediscover an n-day and present it as a find, and they short-circuit the mechanism
understanding that the later stages depend on. <IF THE MIRROR HAS `.git` REMOVED, SAY SO HERE.>
Carve-outs where the internet IS allowed: <e.g. reading dependency source, language/runtime semantics,
protocol RFCs — never this asset's own issue tracker, advisories, or commit log>.

A `third_party/` scratch directory is provided at <PATH>. Clone any dependency you want to audit into
it and **read its source rather than searching the web for its documented behaviour**. A chain may need
a link inside a dependency, a runtime, or the language itself.

Binding: `CLAUDE.md`, `scope.md` (signed <DATE> — <ZONE-2 LEVEL>), `program-policy.md`,
`engine/{multi-round-orchestration,whitebox-analysis,persistence,regrade,pocinator,chainability,escalation}.md`.
Read `recon-signals.md` and `progress.md` FIRST.

---

## Part 2 — Binding scope and safety gates

IN: <EXACT DIRS, FILES, MODULES, ENTRY POINTS, SINKS>.

OUT / KILL BEFORE DEEP WORK: <GENERATED CODE; VENDORED DEPS THAT ARE NOT THE TARGET; ALREADY-FIXED
HARDENING — POSITIVE CONTROLS ONLY, CHECK FOR INCOMPLETE FIXES, NEVER RE-HUNT; DEPENDENCY CVEs WITHOUT
AN ASSET-SPECIFIC PoC; PREVIOUSLY-DISCLOSED ITEMS; ANY LIVE NETWORK OR PRODUCTION SYSTEM>.

**Naming the allowed target is not a fence.** State the prohibition as a rule. If a lane discovers an
adjacent host, service, or repository that looks in reach, it is OUT unless `scope.md` names it — and
evidence gathered against it is quarantined, not used, **even when it is the run's best result**.

Zone-2: <CEILING FROM scope.md>. Every state-changing proof runs on <THE DISPOSABLE OWNED LOCAL
ENVIRONMENT: local instance, private fork, loopback sim>.

**Escalate to maximum impact without asking.** `scope.md` carries a standing impact-maximization
mandate. Push every confirmed bug to its maximal demonstrated impact inside the authorized surface,
and compose confirmed primitives freely — chaining is escalation, not a new act. Do not ask for what
the mandate already grants.

**Stop for a fresh human confirm when an act trips one of five wires.** These are properties of the
act, not of its severity:

1. **irreversible by the actor** — the identity performing it cannot undo it with the access it used
2. **reaches a third party** — outside the operator's own accounts and the named target
3. **outlives the engagement** — survives the cleanup ledger, or removal needs access you do not hold
4. **real funds, real keys, real users, or production**
5. **submission, disclosure, or outbound vendor contact**

Name the wire, state the cleanup path, then ask. **A grant covers what was on the table when it was
given** — an act invented later is not covered by an earlier "yes", however broad that yes was. This
gate is never waived and never batched.

---

## Part 3 — Version, attribution, and eligibility gates

- Pinned identity: <TAG / COMMIT / ARTIFACT SHA256>. Every finding cites it.
- Attribution: is the flaw in <ASSET> itself, or in an application's use of it, or in a dependency?
  Only <ASSET>-attributable flaws are reportable here. State the attribution per candidate.
- Eligibility: <PROGRAM EXCLUSIONS THAT KILL A FINDING REGARDLESS OF TRUTH>.
- Novelty: a flaw already public, already fixed upstream, already on a published roadmap, or already
  reachable by a running fuzzer is **real but not reportable**. Check this at Stage 5.25, not before —
  novelty never kills a candidate early, it only gates reporting.

---

## Part 4 — Attacker model and realism bar

- Attacker position: <PRE-AUTH REMOTE / AUTHENTICATED LOW-PRIV / CO-TENANT / LOCAL>.
- Attacker input: <EXACTLY WHAT THEY CONTROL, AND WHERE IT ENTERS>.
- Configuration: **default**. A finding that needs a non-default option, a raised limit, or an unusual
  deployment is `real-but-capped` until you demonstrate a realistic deployment that has it. Name the
  deployment.
- The consumer must be real. A differential nothing consumes is not a finding.
- Severity is the **marginal** contribution (`engine/escalation.md` §1): the delta this flaw adds versus
  the world without it, never the total impact sitting nearby. A chain whose preconditions include a
  privileged capability must state its margin over just using that capability directly.

---

## Part 5 — Asset-specific approach portfolio (seed families)

Seed the family registry with genuinely independent mechanism families. These are starting points, not a
fixed assignment — a family the recon discovers is as valid as one listed here.

<LIST 8–14 FAMILIES, EACH WITH: id, the mechanism in one line, the source slice, the attacker input,
the sink or boundary it would cross. Draw from — and extend beyond — this general roster:>

- input parsing and decoder state
- charset, encoding, unicode, normalization
- type confusion and loose-typing gaps (a validator that handles the expected shape and silently no-ops
  on another shape)
- **validate-here / execute-there desync** (one pass validates, a second pass acts on a different index,
  buffer, or representation)
- **path/route normalization divergence** (a security filter and a dispatcher disagree on what a path is
  — trailing slash, case, encoding, double segment)
- **trust transitivity between a verified and an unverified input** (an endpoint takes a checked secret
  and an unchecked blob in the same call, then trusts the blob's contents)
- serialization, deserialization, gadget reachability
- **configuration-as-code write primitives** (a logging, template, or plugin config that can write or
  execute a file the next layer treats as live)
- file upload, extraction, path handling
- caching, cache identity, and cache poisoning
- races and TOCTOU
- error handling and fail-open behaviour
- **flag interaction** (an admin or feature parameter that sidesteps an unrelated gate as a side effect)
- mass assignment and property-level authorization
- resource limits, amplification, unbounded allocation
- state machines and protocol sequencing
- privilege, role graph, and delegation

**BUILD A CARD FIRST** if a lead needs one: <CLASSES WITH NO DEDICATED CARD>. A card-less lead has no
oracle. Author the `skills/{vulns,patterns}` card before deep grading, oracle-grade it like the existing
cards, and log a pattern-candidate.

---

## Part 6 — Multi-agent search management

Run `engine/multi-round-orchestration.md`. Maintain its three live artifacts: the **approach-family
registry**, the **primitive registry**, and the **round ledger**.

Concurrency: up to **<N>** agents at once (source audit parallelises; a live or browser target
serialises toward 1 per `CLAUDE.md`). Never exceed the runtime cap.

- **Round 0 is blind.** Independent hunters, each seeded a distinct family. **Withhold what you already
  suspect.** Telling every agent the favoured hypothesis buys you that hypothesis's blind spots.
- Group agents by the **research idea**, not by wording. Two agents phrasing the same mechanism
  differently are one family.
- No family takes more than about half a round's concurrency. Every round spends at least one agent on
  an `untouched` family until all are touched.
- Every agent gets a bounded brief: family, source slice, attacker boundary, required concrete output,
  excluded claims, budget. Require source→sink→path triples with `file:line`, byte-level input
  constructions, or **the exact mechanism that blocks the route**. Reject status reports and vague
  suspicion.
- **`blocked` records the specific missing mechanism.** Reopen only on a materially new construction —
  a different bypass, a new pairing, a new reachable path, a new sink. Rewording does not reopen a route.
- `held` is not `exhausted`. One failed construction does not close a mechanism.
- Keep at least **two incompatible routes** alive across at least two rounds before cross-pollinating.
- **Adversarial throughout.** Every concrete candidate gets an independent refuter from round 1 — not
  only at the confirm stage. The refuter is briefed to **REFUTE**, and is never told a flaw is expected
  (Part 0, move 2).
- **Kill-pair for framing-ambiguous candidates only** (`multi-round-orchestration.md` §4a): one reviewer
  assigned to kill, one assigned to establish, run concurrently and blind to each other; the
  orchestrator adjudicates rather than averaging. Fire it when the verdict turns on *framing* ("is this
  a bug or the function's purpose?"), when two lanes disagree, or when a candidate survives only because
  nobody attacked it. Do not fire it for anything one measurement settles.
- **The orchestrator participates.** Never let a single subagent's word move the ledger. If a subagent
  makes a claim that would severely change direction — a new Critical, a broken cap, a new reachable
  path — spawn an independent reviewer on that exact claim from fresh context and reconcile both before
  any verdict changes. Agent consensus is not an oracle.
- Between every round: synthesise, challenge, redirect, launch. Update all three artifacts.

Route statuses: `unexplored` · `active` · `candidate` · `held` · `blocked` · `exhausted` · `confirmed` ·
`real-but-capped` · `refuted`.

---

## Part 7 — Required staged funnel

Per `engine/whitebox-analysis.md`, run inside each route; jump back freely:

`narrow → classify → triples → reachability → confirm → faithfulness-verify → chainability → Post`

Rules that do not bend:

- **Rules are a Stage-1 pre-filter only.** They misclassify, they overmatch, and they miss what a model
  finds. Never let one rule kill a candidate.
- **Never one-pass kill or bless.** Multiple genuinely independent keep-biased grading rounds, each
  adding **new** signal. Log every kill with its reason. The grading agents manage the pipeline
  themselves and do not stop until every enumerated lead has a disposition.
- **The job is filtering, not finding.** Sinks are cheap; the work is filtering thousands of fake ones
  for the real one. Understand the **whole** exploit before verifying — know what is real and what is
  fake *before* you run it, and give a one-sentence "why it's real" per survivor.

---

## Part 8 — Controls and evidence requirements

- **Faithfulness pass runs in FRESH context.** The PoC must exercise the **real pinned code path that
  the real control flow executes** — real build, real runtime, real network where applicable.
- **A harness that reproduces a sink without the real path is a reward-hack**, and it is the most common
  way a real bug gets closed as invalid. A fuzzer, an emulator, a mock, a fake client, or a
  reimplementation of the target proves nothing. Fakes skip the validation the real system performs, so
  they confirm claims the real system would reject. Source-first regrade any claim that rests on one.
- **Confirm from RAW output, never a wrapper's summary.** Tooling that summarises test results, diffs,
  or match counts has been observed to report the wrong outcome. Verify every such verdict with a second
  independent tool.
- **Every finding carries a negative control.** Show the benign case that does NOT trigger it. A uniform
  error response makes "it errors now" meaningless — aim the probe at a target whose success state is
  observable.
- **Re-validate an oracle inside every namespace you use it in.** Calibrating once at the root proves it
  works only where you calibrated it. Run a random-garbage negative control in each new scope.
- Quantify impact. State the measured number, the method that produced it, and the pinned
  version/block/commit it was measured at. "N=<count> found by <method>" is the correct shape;
  a bare number without its enumeration is not.

---

## Part 9 — Adjudication and independent audits

- Only the orchestrator or the oracle emits `confirmed`. A hunter may propose `suspected_success`.
- Every surviving candidate passes: fresh-context regrade (`engine/regrade.md`), reward-hack check
  (`engine/pocinator.md`), chainability across the six angles (`engine/chainability.md`), then novelty,
  attribution and reportability (Stage 5.25).
- **The adjudicating lane is never told that a flaw was expected.** A reviewer who read the
  orchestrator's own prior conclusions is producing circular support, not independent review — discount
  its precedent arguments and keep only its factual verifications.
- A reviewer that corrects the orchestrator **downward** is the mechanism working, not a bad result.

---

## Part 10 — Recording and checkpoints

Append-only, updated at every synthesis point, never rewritten to match a later belief:

- `rounds.md` — the three registries and each round's ledger entry
- `hypotheses.md` — every hypothesis with its disposition
- `cascades.md` — see below
- `attempts.jsonl` — an `attempt` for every result; a `finding` only on oracle-`confirmed`
- `progress.md` — pinned identities, environment, blockers recorded verbatim
- `cleanup.md` — every artifact created, and its disposition

**CASCADING** (second-order discovery; every discovery is a branch, not an endpoint). When a finding or
a significant research discovery survives, interrogate it with two questions and record an answer for
each, even when the answer is "nothing":

- **Q1 — how do I detect this same behaviour elsewhere?** The same shape in a sibling module, processor,
  route, or input surface. <SEED EXAMPLES FROM THIS DOMAIN.>
- **Q2 — does the ORIGIN of that behaviour enable a different attack?** The root mechanism treated as a
  primitive. <SEED EXAMPLES FROM THIS DOMAIN.>

Q1 mostly yields siblings. **Q2 is where a new class comes from.** Log every cascade: parent discovery
id → Q1 answer → Q2 answer → leads (`file:line`, hypothesis, why real or fake, confidence) →
disposition. Every cascade lead re-enters the funnel like any other hypothesis and may cascade again.
Every capped primitive stays in the primitive registry as a **fragment awaiting composition** — a cap is
not terminal. It will get messy; the ledger is what keeps the mess productive.

---

## Part 11 — Persistence contract (effort, never verdict)

Target at least **<DURATION: 6+ hours>** of active research. Do not sleep to consume time. Keep reading
source, constructing inputs, measuring controls, rotating agents, and opening untouched families.

**It is possible; if you give up you are not trying hard enough. Be more stubborn than the developer was
careful.** That applies to **effort**. It does not license a conclusion, and it never reaches Part 12.

Do not return merely because:

- the first wave produced nothing;
- several agents agreed the code looks robust;
- the most promising route turned out to be bounded;
- a construction was hard to build;
- a lane was unfamiliar;
- a candidate came in lower than hoped;
- the tree was bigger than expected.

A held vector is a **wrong turn to revisit with fresh recon**, not a dry verdict. When a sub-area stalls,
zoom out: re-bound the surface, look for missed entry points, redirect agents. When a candidate is live,
zoom in: complete the real path, the controls, the measurement, the chain.

**Persistence is evidence-licensed, not claim-licensed.** It raises effort; it must never raise
confidence. A confirmed primitive, a `strong` routing signal, a fix-diff anchor, or an operator prior
**raises** the round bound and forbids an early dry verdict. Absent such evidence, the floor applies.
Fishing is not persistence. Several bounded families do not prove the asset safe, and several suspicious
shapes do not make a finding.

Stop early **only** when a safety or authorization gate blocks all meaningful in-scope progress and
needs the operator. Otherwise launch another round.

If a candidate survives early, do **not** stop. Spend the remaining time attacking it: disprove its
reachability, attack its cap, measure its scaling, sweep for sibling instances, look for alternate
constructions, replay it from a clean environment, and complete the regrade / pocinator / chainability /
novelty / cleanup passes.

---

## Part 12 — Terminal verdicts and final response

Allowed terminal verdicts — nothing else:

- **`confirmed`** — the exact claim survives every oracle and independent review, at default
  configuration, executed against the real code path with a negative control.
- **`confirmed_with_correction`** — the mechanism is real; the honest claim is narrower than first
  stated.
- **`chained`** — a multi-step impact chain with every edge verified and a named realistic consumer.
- **`real-but-capped`** — the primitive is real and its limiting control is **demonstrated**, not
  assumed.
- **`covered-dry`** — the surface is bounded, enumerated, and every material route is exhausted or
  closed by evidence.
- **`blocked`** — an external gate or unavailable environment prevents completion; name the exact
  missing condition.

Never terminal: "it finally crashed", "probably exploitable", "likely a DoS", "the model finally
complied", or agent consensus.

**If a finding survives**, return an internal research package:

1. one sentence on why it is real; 2. pinned version and artifact identity; 3. attacker model and
realistic entry point; 4. input construction, source→sink→path, full chain; 5. default-configuration
evidence; 6. quantitative impact with its negative control; 7. reproduction command and expected raw
output; 8. independent review results; 9. novelty, attribution, and reachability status; 10. strongest
honest severity and the demonstrated cap; 11. cleanup disposition; 12. unresolved caveats.

**If the result is `covered-dry`**, return — this is a deliverable, not a surrender:

1. the bounded surface and sink inventory, with counts; 2. the family registry with terminal
dispositions; 3. all strong and negative activation signals; 4. the most credible refuted candidates
and the **decisive control** that killed each; 5. any real-but-capped hardening issues; 6. gaps not
covered, and why; 7. evidence of the active-research time spent; 8. cleanup and memory disposition.

**Do not file, submit, publish, email, open an issue, open a pull request, or contact the vendor.**
Filing is operator-only; the operator personally reviews and re-authors any submission.

**The product of this run is rigor, not a finding count.** A conservative, reproducible `covered-dry`
beats a dramatic result that needs a raised limit, a non-default option, a hand-built input that skips
the real parser, or a differential no real system relies on.

---

## Part 13 — Models and first move

MODELS: <PLANNING MODEL, top tier> = orchestration, triage, verdicts, gates, cascade seeding,
cross-agent reconciliation. <HUNTER MODEL, mid tier> = one bounded brief each. <EXECUTION MODEL> = the
long-horizon grunt work — PoC harnesses, fuzzers, instrumentation, private-net sims, tens of thousands
of lines where the work genuinely needs it. **Do not invert these.**

FIRST MOVE:

1. Pin and record: clone <ASSET> at <TAG>, remove `.git` if the no-diff rule is in force, record the
   identity and any artifact sha256 in `progress.md`; create `third_party/`.
2. Environment preflight: <TOOLCHAIN>. Build the pinned source, then the targeted test subset. Record
   any blocker verbatim.
3. Recon on the mirror: complete the activation-signals table in `recon-signals.md` —
   <DOMAIN-SPECIFIC RECON QUESTIONS>. Capture the **baseline controls**: what the asset refuses with no
   attack at all.
4. Seed the family registry from Part 5 plus whatever recon surfaced. Mark every family `unexplored`.
5. Calibrate the oracle against <FIXTURES / SOURCE / THE SEVERITY-PRECEDENT CORPUS>, and run a
   random-garbage negative control in each namespace you will use it in.
6. Launch Round 0 blind, one distinct family per hunter, withholding any suspicion you already hold.
