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

Work from first principles by reading the code. Reading Node.js or dependency source is fine. Reading
the Obyte developer documentation and the Autonomous Agents guide is encouraged.

### The history sweep — do it once, at the start, and record shapes only

**Read the recent commit history. It is the strongest routing signal available.** An earlier version
of this prompt forbade it. That was a rule borrowed from capability benchmarks, where the goal is to
prove a model can find a bug unaided. This is a bounty, where the goal is impact. The rule cost
signal and bought nothing.

`ocore` is being actively hardened. Verified 2026-08-11 against the public history:

| commit | date | subject |
|---|---|---|
| `991c5d65d` | 2026-08-03 | fix: V-001 security vulnerability (#305) |
| `16ddd6a41` | 2026-08-03 | pre-validate asset in aa composer |
| `f3b253ebf` | 2026-08-02 | check allowed charset in isValidAddress |
| `f503efc9f` | 2026-07-28 | move stability point by 1 after validation found that a later MC unit is stable in parents |
| `c368211fc` | 2026-07-26 | validateAATriggerObject: no early success if no non-base assets |
| `d7d6a8256` | 2026-06-02 | try/catch getBase64Hash in spend proofs |
| `403e96b93` | 2025-05-20 | delay parenting AA responses to mitigate partitioning on OP doublespend |
| `05f291d8d` | 2025-02-19 | uniqueness of spend proof is not verified in light |

`V-001` reads like an audit finding id, so assume a recent third-party audit and assume its findings
are already fixed and already reported.

**What the sweep is for: a fixed bug marks a family, not a target.** Where one instance was wrong,
siblings live. A validation that needed hardening in one path is worth checking in every sibling path.

**Three binding rules on the sweep:**

1. **Record abstract shapes in `recon-signals.md`, not fixes.** Write "asset pre-validation was
   missing at one AA composer entry point" — a shape you then hunt for elsewhere. Do not copy the
   diff into the engagement.
2. **Never report a fix as a find.** Any candidate that maps to a swept shape must be checked against
   the actual fix before it can be promoted. If the fix covers it, it is `covered-dry`, not a
   finding. Stage 5.25 novelty already enforces this; the sweep does not bypass it.
3. **One sweep, at the start.** Do not return to the history to steer the loop. It seeds routing; it
   does not run it.

**And know why code is defended.** Without the sweep, a hunter meets hardened code and cannot tell
whether it was always careful or was fixed last month. That wastes rounds.

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

**The two $50k lanes need a PROOF STRATEGY, not a feasibility verdict.** Do not answer "is there a
path?" early — that question invites a premature "no" on the hardest and most valuable lane, and Q-B
lives in the subtlest code in the repository (signature verification, authentifier parsing, the
definition language, private spend proofs). Answer these instead, and revisit as recon proceeds:

- **What would count as proof?** What evidence would convince a reviewer that a transaction executed
  from another user's account without their key, or that the whole network stopped unrecoverably?
- **What does the condition decompose into?** Does "total network shutdown" mean every order provider
  down, a consensus-rule violation that partitions permanently, or a state no valid unit can extend?
  Name the sub-conditions. Each is then a lane.
- **What would the local lab have to show?** Write the experiment before you can run it.

A lane with a written proof strategy and no path yet stays open. A lane with neither is not closed —
it is unexamined, and saying so is the honest record.

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

**Author 3–4 DAG cards during recon, BEFORE round 0.** `skills/` has EVM and Cosmos cards and nothing
DAG-shaped, so every DAG lead would otherwise pay a card tax at grading time — hours per lead on a
codebase class we have never audited. Pay it once, up front. Candidates, adjust after recon:

- unit/joint acceptance desync — validated in one pass, acted on in another
- JS numeric semantics on value arithmetic — `Number` is a double
- spend-proof uniqueness and the full-versus-light verification asymmetry
- witness / main-chain mutation and stability advancement

These are **oracles**, not hypotheses. They describe how to grade a shape, not where to look, so they
do not compromise a blind round 0. A lead that needs a card the recon did not anticipate still builds
one before deep grading; log a pattern-candidate either way.

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

## Part 13 — Calibration

`ocore` is a nine-year-old production consensus library, and the history sweep shows it is under
active hardening. **The honest prior is: mostly solid, with a scattering of Medium and High bugs and
a long-shot Critical.**

That is calibration for reading the result, not a licence to work less. The persistence contract in
Part 11 is unchanged.

**What success looks like here.** "Covered-dry on both $50k lanes, with the proof strategies written
and the sub-conditions enumerated, plus two confirmed Mediums with runnable PoCs" is a **good
engagement**. Report it as one. Obyte's historically severe issues lived in the wallet layer — out of
scope here — so a DLT-core run that produces Mediums and Highs has hit the realistic distribution.

The failure to avoid is not a low finding count. It is six hours spent chasing a $50k shutdown
because it was worth the most, while the High and Medium surface went unexamined.

## Part 14 — First move

1. **Pin.** Clone `ocore`, pick the latest commit whose test suite runs, and record that identity in
   `progress.md`. Note if you had to move off `HEAD` and why.
2. **Sweep the history once** (Part 1). Record abstract shapes in `recon-signals.md`. No diffs.
3. **Build the lab once and persist it.** A local multi-node Obyte network — synthetic genesis, a
   generated key set, node config — checked in as a reusable artifact with a one-command bring-up.
   Every severity needs a runnable PoC, so this is the most-used tool in the engagement. Per-candidate
   bring-up must be minutes, not hours.
4. **Environment preflight:** Node version, install, run the existing test suite. Record any blocker
   verbatim — a blocked environment is a real result, not a delay.
5. **Recon:** complete the activation-signals table in `recon-signals.md`. Capture **baseline
   controls** — what the node refuses with no attack at all.
6. **Write the proof strategies** for both $50k conditions (Part 3). Decompose each into
   sub-conditions. Do not answer "is it feasible".
7. **Settle the DoS coordination question** for the availability surface.
8. **Author the DAG cards** (Part 5).
9. Seed the family registry, everything `unexplored`. Launch Round 0 blind, one family per hunter.
