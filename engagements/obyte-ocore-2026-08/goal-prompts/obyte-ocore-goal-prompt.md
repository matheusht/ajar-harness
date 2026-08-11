# Goal prompt — obyte-ocore-2026-08

## Part 1 — Task

GOAL: white-box exhaustion of **`github.com/byteball/ocore`** — the Obyte core library. Obyte is a
**DAG-based distributed ledger, not a blockchain**. Node.js / JavaScript. Program: Immunefi / Obyte
Foundation, **Primacy of Rules** — an impact that is real but not on the list does not qualify.

Read `scope.md` and `program-policy.md` first. They are binding and they are specific.

Pin the audit baseline: clone `ocore` at a tag or commit, record the identity in `progress.md`, and
cite that identity in every finding.

**State the surface, not a conclusion.** Exactly one of two statements about this asset is true:
either a reachable flaw exists on it, or every mechanism family on it is bounded by a control you can
name and demonstrate. Both cost the same to prove. Return only when one is proven. **"I did not find
anything" is not a terminal state.**

Work from first principles by reading the code. Do not diff against a patched version, read
changelogs, or search for known issues in this asset — that rediscovers an n-day and presents it as a
find. Reading Node.js or dependency source is fine. Reading the Obyte developer documentation and the
Autonomous Agents guide is fine and encouraged.

## Part 2 — The hard wall

**All testing runs on a LOCAL fork or local instance.** `program-policy.md` prohibits any testing on
mainnet or public testnet deployed code. **No contact with any live Obyte node, hub, explorer, or
public testnet. Ever.** Also prohibited: pricing oracles, third-party contracts, third-party systems,
DoS against project assets, high-traffic automated testing.

**Naming the allowed target is not a fence.** If you discover an adjacent host or service, it is OUT
unless `scope.md` names it, and evidence gathered against it is quarantined — even when it is the
run's best result.

**Escalate to maximum impact without asking.** `scope.md` carries a standing impact-maximization
mandate. Push every confirmed bug to its maximal demonstrated impact inside the local network, and
compose confirmed primitives freely — chaining is escalation, not a new act.

**Stop for a fresh human confirm only when an act trips a wire.** These are properties of the act,
not of its severity:

1. **irreversible by the actor** — you cannot undo it with the access you used
2. **reaches a third party** — outside the local environment and the named target
3. **outlives the engagement** — removal needs access you do not hold
4. **real funds, keys, users, or production** — including any live Obyte node or testnet
5. **submission, disclosure, or outbound contact** with the Foundation or Immunefi

Name the wire, state the cleanup path, then ask.

## Part 3 — The reward ladder decides where effort goes

| Tier | Amount | Condition |
|---|---|---|
| **Critical, full** | **up to $50,000** | ONLY unrecoverable **total network shutdown of the entire Obyte network**, OR **unpermitted execution of transactions from other users' accounts without their private keys** |
| Critical, capped | $2,500 | every other Critical |
| High | $1,700 | temporary freezing of funds ≥ 1 year |
| Medium | $1,000 | unable to operate for lack of token funds; temporary freezing of funds |

**Read this before choosing a lane.** The ladder is nearly flat except for two named mechanisms. A
third Critical class pays what a Medium-plus pays. So effort belongs on those two conditions, and on
honest High/Medium coverage — not on manufacturing another Critical.

**Settle the DoS question early, because it decides many candidates.** A temporary network disruption
is **out of scope** when a fix resolves it **without network coordination**. It is **in scope** when
resolution **requires network coordination**, graded as temporary freezing of network transactions.
For any availability candidate, answer that question first and record the answer.

**Minimum impact is USD 1,000** for anything involving funds lost or frozen. Damage ≤ 200% of the
attacker's own expense is out of scope.

## Part 4 — Attacker model

- Position: a network participant who can craft and broadcast units, run a node, and act as a peer.
  Some paths also allow an ordinary wallet user or an AA caller.
- Input: unit and joint structures, network messages, definition/oscript payloads, AA trigger data,
  asset definitions, spend proofs.
- Configuration: **default**. A finding needing a non-default option is `real-but-capped` until you
  name a realistic deployment that has it.
- Severity is the **marginal** contribution (`engine/escalation.md` §1) — the delta this flaw adds
  over the world without it, never the total nearby.

## Part 5 — Seed families

Independent mechanism families. These are starting points, not an allocation. A family recon
discovers is as valid as one listed here.

- **DAG validation** — unit and joint acceptance, parent selection, structural checks, size limits
- **Main-chain selection and stability** — the ordering rule, stability point advancement
- **Witness handling** — witness list mutation, witnessed level, the mutation distance rule
- **Signature and authentifier verification** — including multi-sig and nested definitions
- **Definition language** — smart-address predicate evaluation, `sig`, `hash`, `cosigned by`, `in
  data feed`, `has`, nested boolean structure, and the definition-change path
- **Formula / oscript evaluation** — the AA engine inside ocore: numeric handling, string handling,
  state variable read and write, bounce conditions, response chains, recursion and depth limits
- **Asset handling** — divisible versus indivisible, private assets, transfer conditions, caps
- **Private payments and spend proofs** — double-spend detection on the private path
- **Catchup and proof chains** — hash-tree proofs, catchup chain validation
- **Network protocol** — gossip, request handling, peer message parsing, subscription handling
- **Storage and reorg handling** — what happens when the main chain moves
- **Numeric and encoding** — JS number precision on value arithmetic, integer overflow, JSON parsing,
  base64/base32 handling, unicode in text messages
- **Races and TOCTOU** — validation versus write, concurrent unit handling
- **Fail-open error handling** — a caught exception that returns "valid"

**Two seams worth naming, because both have produced findings in comparable ledgers.** First, a
**validate-here / act-there desync**: one pass validates a structure and a later pass acts on a
different representation of it. Second, **JavaScript numeric semantics on money** — `Number` is a
double; any value arithmetic that leaves integer-safe range, or any comparison that coerces, is worth
a hard look.

**BUILD A CARD FIRST** if a lead needs one. A card-less lead has no oracle. `skills/vulns/` and
`skills/patterns/` have EVM and Cosmos cards but nothing DAG-specific. Author the card before deep
grading, oracle-grade it, and log a pattern-candidate.

## Part 6 — Search management

Run `engine/multi-round-orchestration.md`. Keep its three artifacts: the approach-family registry,
the primitive registry, and the round ledger.

- **Round 0 is blind.** Independent hunters, one distinct family each. Withhold what you already
  suspect.
- Group by research idea, not wording. No family takes more than half a round.
- Every brief requires source→sink→path triples with `file:line`, a concrete input construction, or
  the exact mechanism that blocks the route. Reject status reports.
- `blocked` records the specific missing mechanism. Reopen only on a materially new construction.
- `held` is not `exhausted`.
- **Adversarial throughout.** Every concrete candidate gets an independent refuter from round 1,
  briefed to REFUTE, and never told a flaw is expected.
- **Kill-pair** for framing-ambiguous candidates only (`multi-round-orchestration.md` §4a).
- **The orchestrator participates.** No single subagent's word moves the ledger. A claim that would
  change direction gets an independent second reviewer from fresh context.

## Part 7 — Funnel

`narrow → classify → triples → reachability → confirm → faithfulness-verify → chainability → Post`
(`engine/whitebox-analysis.md`; jump back freely).

- Rules are a Stage-1 pre-filter only. Never let one rule kill a candidate.
- **Never one-pass kill or bless.** Multiple independent keep-biased rounds, each adding new signal.
  Log every kill with its reason.
- The job is filtering, not finding. Understand the whole exploit before verifying.

## Part 8 — Evidence

**The program requires a PoC for every severity, always.** A source-only finding is not submittable.

- The faithfulness pass runs in **fresh context** against the **real pinned code path**.
- **A harness that reproduces a sink without the real path is a reward-hack.** A mock, a fake client,
  or a reimplementation proves nothing. Run a real local Obyte network.
- **Confirm from RAW output, never a wrapper's summary.**
- **Every finding carries a negative control** — the benign case that does not trigger it.
- Quantify impact with the method that produced the number and the pinned commit it was measured at.

## Part 9 — Findings

`engine/finding-lifecycle.md` governs this. **Findings are written to `unproven/<FINDING_ID>/` and
have no status field.** A package is:

```
unproven/<FINDING_ID>/
  finding.json    the record, including privilege_context {claimed, proven}
  attest.json     the attestations the attestable gates need
  REPORT.md       the writeup
  reviews/*.json  claim_adjudication reviews
```

Check any package without moving it:

```
./.venv/bin/python tools/finding_lifecycle.py gates <PKG> --engagement <ENG>
```

Promotion to `findings/` runs six gates and is the **orchestrator's** act. Hunters write and move
nothing. Any role may demote with a reason.

**On adjudication reviews.** A review records that a reviewer ran. If no reviewer ran, do not write
the record — an unwritten review is an honest gap, and a written one that describes nothing is not.
If you cannot obtain independent review, say so and leave the finding unpromoted.

## Part 10 — Recording

Append-only, never rewritten to match a later belief: `rounds.md`, `hypotheses.md`, `cascades.md`,
`attempts.jsonl` (an attempt for every result), `progress.md` (pinned identities, blockers verbatim),
`cleanup.md` (every artifact and its disposition).

**CASCADING.** When a finding or a significant discovery survives, interrogate it and record an
answer even when the answer is nothing:

- **Q1 — how do I detect this same behaviour elsewhere?** The same shape in a sibling validator,
  message handler, or asset path.
- **Q2 — does the ORIGIN of that behaviour enable a different attack?** The root mechanism as a
  primitive.

Q1 mostly yields siblings. **Q2 is where a new class comes from.** Expect Q2 to over-report on first
pass; review every Q2 answer before recording it as a new kind.

## Part 11 — Persistence

Target at least **6 hours** of active research. Do not sleep to consume time.

**It is possible; if you give up you are not trying hard enough. Be more stubborn than the developer
was careful.** That governs **effort**. It does not license a conclusion.

Do not return because the first wave produced nothing, because several agents agreed the code looks
robust, because the best route turned out bounded, or because the tree was bigger than expected. A
held vector is a wrong turn to revisit with fresh recon.

**Persistence is evidence-licensed.** A confirmed primitive or a strong signal raises the bound and
forbids an early dry verdict. Absent that, the floor applies. Fishing is not persistence.

If a candidate survives early, do not stop — attack its cap, sweep for siblings, replay it clean, and
complete the regrade, pocinator, chainability and novelty passes.

## Part 12 — Terminal verdicts

Allowed: `confirmed` · `confirmed_with_correction` · `chained` · `real-but-capped` (cap
demonstrated) · `covered-dry` (bounded, enumerated, every route exhausted or closed by evidence) ·
`blocked` (name the exact missing condition).

Never terminal: "probably exploitable", "likely a DoS", "it finally crashed", or agent consensus.

**A `covered-dry` result is a deliverable**, not a surrender. Return the bounded surface inventory
with counts, the family registry with terminal dispositions, all strong and negative signals, the
most credible refuted candidates with the decisive control that killed each, gaps not covered and
why, and the cleanup disposition.

**Do not file, submit, publish, or contact the Obyte Foundation or Immunefi.** Filing is
operator-only. Publication is Category 3 — approval required.

**The product of this run is rigor, not a finding count.**

## Part 13 — First move

1. Clone `ocore`, pin the commit, record it in `progress.md`. Set up a local multi-node Obyte network
   with synthetic genesis and locally generated keys.
2. Environment preflight: Node version, install, run the existing test suite. Record any blocker
   verbatim — a blocked environment is a real result, not a delay.
3. Recon: complete the activation-signals table in `recon-signals.md`. Capture **baseline controls** —
   what the node refuses with no attack at all.
4. Answer the two ladder questions early: what would total unrecoverable network shutdown require,
   and what would spending from another account without its key require? Write the answer even if it
   is "no path found yet".
5. Settle the DoS coordination question: for the availability surface, what resolves without network
   coordination and what does not?
6. Seed the family registry. Mark every family `unexplored`.
7. Launch Round 0 blind, one family per hunter.
