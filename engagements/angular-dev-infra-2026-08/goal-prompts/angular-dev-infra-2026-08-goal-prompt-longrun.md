# Goal prompt — LONG-RUN exhaustion: `angular/dev-infra` (Google OSS VRP, OT0)

> Engagement `angular-dev-infra-2026-08`. Format: `engagements/_TEMPLATE/goal-prompts/goal-prompt-LONG-RUN.md`.
> Round loop: `engine/multi-round-orchestration.md`. Read it before acting on this.
>
> **Blockers open** (`progress.md` §2): B1 disk (1.5 GiB free, need ≥ 30 GB), B2 toolchain, B3
> reviewer keypair. Clear B1 and B2 before Round 0. B3 blocks committing a review, not hunting.
>
> `CLAUDE.md`, `scope.md`, `program-policy.md` and `engine/*` override this file everywhere.

---

## Part 0 — The anti-bias construction (read before anything else)

The method this format derives from opens by asserting the repository contains a vulnerability. That
sentence is what makes the method persistent, and it is the one thing that must not be copied. It
works by making "I found nothing" **false by construction**. Point that at a clean surface and the
run cannot terminate honestly — the only reachable exit is the one it was told to expect, so it
manufactures one. Manufacturing one here means a fabricated report to Google, which is precisely what
the OSS VRP tightened its rules in 2026 to stop.

The operator's own words hold both halves of this and neither cancels the other:

> *"Do not reward hack yourself to cheat into a way you need to work less, but if it ends up not
> having anything there, it's okay, just BE SURE of it."*

Three moves keep the persistence and drop the bias.

**1. Symmetric exit obligation.**

> Exactly one of two statements about this surface is true. Either a reachable flaw exists on it, or
> every mechanism family on it is bounded by a control you can name and demonstrate. Proving either
> takes the same work. You may not return until you have proven one. **"I did not find anything"
> proves neither and is not a terminal state.**

**2. Bias placement by lane. This is the rule that makes an unbiased run possible.**

| Lane | Optimistic prior | Cost if the prior is wrong |
|---|---|---|
| **Hunter** | **allowed and encouraged** — "assume the developer made a mistake here; find it" | wasted compute, extra candidates |
| **Refuter / oracle / adjudicator / reviewer** | **forbidden — never told a flaw is expected, never shown the orchestrator's conclusions** | a false report to Google |

A hunter cannot emit `confirmed` (`CLAUDE.md` §2), so its bias is contained. **The orchestrator's
standing duty is to stop the hunter's prior from leaking into a refuter's brief.** A refuter brief
that says "confirm this bug" has already failed. A reviewer that read your prior reasoning is
producing circular support, not independent review.

**3. Effort framing, never verdict framing.** *"It is possible; if you give up you are not trying
hard enough."* *"Be more stubborn than the developer was careful."* These are correct instructions
about **how long to work** and false instructions about **what to conclude**. They govern Part 11.
They never reach Part 12.

---

## Part 1 — Current task statement

GOAL: long-run white-box exhaustion of **`angular/dev-infra`** — Angular's shared development, CI and
release infrastructure. It publishes four npm packages (`@angular/ng-dev`, `rules_angular`,
`rules_browsers`, `rules_sass`) and supplies 21 composite Actions plus one reusable release workflow
that **three other OT0 repositories** run inside their own CI.

Program: **Google OSS VRP, tier OT0** (primary-verified). Target category **Supply-Chain
Compromise**, ceiling **$31,337**. Product Vulnerability is the fallback category at $500–$7,500.
Full rules and the source-quality caveat: `program-policy.md`.

Audit baseline pinned at `04230133d395dfb032d782b8e63b4fcbbd406aa5` (2026-08-07), re-derived and
re-pinned at Round 0 start. 1,023 files.

**The surface.** Attacker input is: issue titles, bodies and labels; pull-request titles, bodies,
branch names, author identity, commit messages and diffs; artifact contents from PR builds; upstream
registry content reaching Renovate; and `workflow_call` inputs from a consuming repository. That
input reaches 14 workflows, 21 composite actions, the `ng-dev` release toolchain (351 files), and 404
files of shared Bazel rules.

The impact classes that matter, ranked, and what each is worth:

1. **Exfiltrate `ANGULAR_ROBOT_PRIVATE_KEY`** — a GitHub App private key with org-wide write. Reaches
   every Angular repository directly. Top of the SCC band.
2. **Publish-path compromise** — attacker content in `@angular/ng-dev` or a `rules_*` package. This
   is verbatim OSS VRP SCC language: "packages distributed via package managers."
3. **Unreviewed code lands** — defeat `post-approval-changes` or `branch-manager` and a change
   reaches three OT0 repositories without the review that was supposed to gate it. Source compromise.
4. **CI code execution** in dev-infra's own pipeline, or in a consumer through a shared action.
5. Product Vulnerability in `ng-dev` as a tool — real, lower band.

**Do not state that a flaw exists.** Exactly one of two statements about that surface is true: a
reachable flaw exists, or every family is bounded by a control you can name and demonstrate. Both
cost the same to prove. Return only when one is proven.

Work from first principles by reading the code. **Do not read git history, changelogs, release notes,
the issue tracker, advisories, or search the web for known dev-infra issues during the hunt.** Those
routes rediscover an n-day and short-circuit the mechanism understanding the later stages need.
Carve-outs: GitHub Actions documentation, `@actions/*` toolkit source read from `third_party/`, Node
and TypeScript semantics, Bazel documentation. Never this asset's own history.

Binding: `CLAUDE.md`, `scope.md` (signed 2026-08-12), `program-policy.md`,
`engine/{multi-round-orchestration,whitebox-analysis,persistence,regrade,pocinator,chainability,escalation}.md`.
**Read `recon-signals.md`, `rounds.md` and `progress.md` FIRST** — real recon is already seeded there,
including one measured negative result.

---

## Part 2 — Binding scope and safety gates

**IN:** the pinned tree — `.github/workflows/`, `.github/local-actions/`, `github-actions/`,
`ng-dev/`, `bazel/`, `apps/`, `lint-rules/`, `tools/`, `.ng-dev/`, `renovate*`, `pnpm-lock.yaml`, the
committed `*_token.data` blobs, and the interface dev-infra exposes to consumers.

**OUT — kill before deep work:**

- **Every live system.** The real `angular/*` repositories, their runners, the Angular Robot and Lock
  Bot Apps, the real npm registry, Renovate, BrowserStack, SauceLabs, Firebase, Google RBE. **No
  probe. No test PR. No test issue. No triggered workflow. Not once, at any severity.**
- Hunting **inside** `angular/angular`, `angular/angular-cli`, `angular/components`. Reasoning about a
  consumer's exposure to a dev-infra flaw is in scope; a consumer's own wiring bug is not our finding.
- Stale-version-only issues, previously disclosed items, already-fixed hardening (positive controls
  only — check for an incomplete fix, never re-hunt).
- Memory corruption. There is none here. Do not manufacture a claim that would push the finding into
  the OSS-Fuzz gate this engagement currently sits outside.

**Naming the allowed target is not a fence.** If a lane finds an adjacent host, service or repository
in reach, it is OUT unless `scope.md` names it — and evidence gathered against it is quarantined and
unused, **even when it is the run's best result.**

**Zone-2:** ceiling `artifact_creation`. Proof methods and their authorization:

| Method | Authorization |
|---|---|
| Static reasoning and source reading | autonomous |
| **Local replication** — `act`, a direct action driver, the local mock API, synthetic canaries | **autonomous** — the intended normal working method |
| A private throwaway fork running real GitHub Actions | **trips wire 2. One fresh operator confirm at the moment of the act.** Never batched, never assumed |

**Escalate to maximum impact without asking** inside the authorized surface. Compose confirmed
primitives freely — chaining is escalation, not a new act. **Never under-demonstrate:** the gap
between a $3,133.70 SCC report and a $31,337 one is demonstrated blast radius, not discovery.

**Stop for a fresh human confirm at five wires** — properties of the act, not of its severity:

1. **irreversible by the actor** · 2. **reaches a third party** (*any* GitHub Actions run, including
in the operator's own private fork) · 3. **outlives the engagement** · 4. **real funds, keys, users,
or production** · 5. **submission, disclosure, or outbound contact with Google or the Angular team**

Name the wire, state the cleanup path, then ask. If no wire is tripped, proceed without asking.

---

## Part 3 — Version, attribution, and eligibility gates

- **Pinned identity** cited by every finding. Re-pin at Round 0; stale-version-only findings are
  rejected by the program.
- **Attribution, per candidate, stated explicitly.** Is the flaw in dev-infra itself, in a consuming
  repository's wiring, in GitHub Actions as a platform, or in a third-party dependency? **Only
  dev-infra-attributable flaws are reportable here.** This gate killed candidates in
  `google-oss-vrp-2026-07`. It will bite here, and the most attractive candidates are the most likely
  to fail it — a bug that needs a consumer to have wired something a particular way is that
  consumer's bug.
- **Third-party dependency flaws** need an upstream report first, and a dev-infra-specific trigger.
- **Category discipline.** Grade against the category the report would actually file under. Do not
  inflate a Product Vulnerability into an SCC claim to reach the higher band. The adjudication oracle
  checks this and a reviewer will catch it.
- **Novelty is checked LATE, and it never kills a candidate early.** Already public, already fixed, on
  a roadmap — those make a flaw **real but not reportable**. Record truth and reportability as two
  separate facts, never collapsed into `refuted`.

---

## Part 4 — Attacker model and realism bar

- **Attacker position:** an unprivileged, unaffiliated GitHub user. They can open an issue, open a
  pull request from a fork, push to their own fork's branch, choose a branch name, write a commit
  message, and control the contents of files in their PR. **They have no write access, no
  maintainer role, and no approval right.** Any candidate needing more is capped until you demonstrate
  a realistic path to that position.
- **Configuration: default.** As the workflows are actually written in the pinned tree.
- **The consumer must be real.** A flaw nothing consumes is not a finding.
- **Severity is the marginal contribution** (`engine/escalation.md` §1) — the delta this flaw adds
  versus the world without it, never the total impact sitting nearby. A chain whose preconditions
  already include maintainer access has a margin near zero. Say so.

---

## Part 5 — Approach portfolio

**The family registry is `rounds.md` §A — F1 through F16, already seeded with real recon.** That is
the live artifact. Read it. A family recon discovers is as valid as one listed.

Top seeds and why:

- **F1 / F2 — the LLM bot next to the App key.** `dev-infra.yml` fires on `pull_request_target` and
  `issues`, and hands attacker-authored issue text to Gemini in a job holding
  `ANGULAR_ROBOT_PRIVATE_KEY`. Their `zizmor` suppression argues the trigger is safe *because the
  workflow does not checkout untrusted code* — which is true about checkout and does not by itself
  address what the job does with untrusted **text**. The decisive question is what constrains the
  model's output: a fixed label vocabulary, or something that can steer a privileged call. **Read the
  action's source before forming the hypothesis.** This is the harness's native domain and the cards
  already exist.
- **F3 — `post-approval-changes`.** Its entire purpose is catching commits pushed after approval. All
  three consuming OT0 repos run it. Defeating it is direct source-integrity compromise.
- **F5 / F6 / F7 — the publish path.** Four packages, an `id-token: write` OIDC grant, and a
  `directory-hash` integrity step whose enforcement must be read, not assumed.
- **F10 — the pin-bump path.** Recon measured 208/208 consumer references SHA-pinned, which closes
  automatic propagation. What it does not close is who reviews a SHA bump, and against what.
- **F12 — `bazel/`, 404 files.** The largest slice nobody has looked at, shipped as three packages.

**BUILD A CARD FIRST** if a lead needs one. Cards that exist and apply are listed in `scope.md`.
A card-less lead has no oracle and cannot be graded (`CLAUDE.md` §1 gate 2, non-waivable). Author it,
oracle-grade it like the existing cards, log a pattern-candidate, then hunt.

---

## Part 6 — Multi-agent search management

Run `engine/multi-round-orchestration.md`. Maintain all three artifacts in `rounds.md` and
`hypotheses.md`, every round.

**Agent budget: up to 128 across the engagement.** Model roles (`engine/whitebox-analysis.md` §5,
and the operator's standing roster):

| Tier | Model | Job |
|---|---|---|
| Orchestrator / triage | **deepseek-v4-pro** | plan, select families, triage candidates, author and debug the pipeline and drivers, decide what earns deep verification, adjudicate |
| Hunter | **deepseek-v4-pro** | bounded family hunts, source reading, candidate generation |
| Grunt execution | **deepseek-v4-flash** | the long-horizon build: drivers, harnesses, minimization, the exploit chain. **This is the tier licensed — explicitly and repeatedly — to not give up.** Left to its own judgment it will call "infeasible" well before the budget the operator is willing to spend |
| Helper | cheap/offline | diffing, dedup, log scraping. **Never trusted with a kill/keep or confirm/refute verdict** |

**Do not invert this.** Asking the triage tier to grind for hours wastes its comparative advantage.
Letting the grunt tier self-select what is "worth" pursuing skips the judgment step it is not suited
for.

Round discipline:

- **Round 0 is blind.** Independent hunters, each seeded a distinct family. **Withhold what you
  suspect.** Telling every agent the favoured hypothesis buys you that hypothesis's blind spots.
- Group agents by the **research idea**, not by wording. Two agents phrasing one mechanism
  differently are one family.
- No family takes more than about half a round's concurrency. Every round spends at least one agent
  on an `unexplored` family until all sixteen are touched.
- Every agent gets a bounded brief: family, source slice, attacker boundary, required concrete
  output, excluded claims, budget. Require **source → sink → path triples with `file:line`**, a
  concrete input construction, or **the exact mechanism that blocks the route**. Reject status
  reports and vague suspicion.
- **`blocked` names the specific missing mechanism.** Reopen only on a materially new construction.
  Rewording does not reopen a route. **`held` is not `exhausted`.**
- Keep **two incompatible routes** alive across at least two rounds before cross-pollinating.
- **Adversarial throughout.** Every concrete candidate gets an independent refuter from round 1 — not
  only at confirm. The refuter is briefed to **REFUTE** and is never told a flaw is expected.
- **Kill-pair for framing-ambiguous candidates only.** One reviewer assigned to kill, one to
  establish, concurrent and blind to each other; you adjudicate rather than average. Fire it when the
  verdict turns on framing — here that most often means *"is this a bug or is this what the bot is
  for?"* and *"is this dev-infra's flaw or the consumer's?"* Do not fire it for anything one
  measurement settles.
- **You participate.** Never let a single subagent's word move the ledger. A claim that would change
  direction — a new High, a broken cap, a new reachable path — gets an independent reviewer on that
  exact claim from fresh context before any verdict changes. **Agent consensus is not an oracle.**
  Agents have caught orchestrator errors on past runs and the reverse; both are normal.
- Between every round: synthesise, challenge, redirect, launch. Update every artifact.

---

## Part 7 — The staged funnel, and who drives it

`narrow → classify → triples → reachability → confirm → faithfulness-verify → chainability → Post -> redo entire pipeline with cascading`

**The stage names show a development progression, not a protocol to walk once.** They are where the
rigor gates sit. A candidate can and routinely should jump back to narrowing (the corpus was not
covered), to triples (the shape was wrong), or to classification (the vocabulary missed a variant)
from any later stage. **The grading agents manage the pipeline themselves and do not stop until every
enumerated lead has a disposition.**

Rules that do not bend:

- **Rules are a Stage-1 pre-filter only.** A grep, a `zizmor` run, a taint query — all useful to
  *narrow*, none of them decide. They misclassify, they overmatch, and they miss what a model finds.
  Every unfamiliar target is a black box to a hand-written rule even when the source is fully visible.
  **Never let one rule kill a candidate.** This repo already runs zizmor; anything zizmor alone finds
  is almost certainly already known.
- **Never one-pass kill or bless.** Killing a candidate requires **multiple genuinely independent
  grading rounds that each add new signal**. "A second agent agreed" is not new signal. Log every
  kill in `hypotheses.md` with what new signal that round added. Letting one source kill a real
  finding is terrible ROI; a false positive surviving one extra round costs a few dollars.
- **Bias every grading round toward keep-if-uncertain.** This is the inverse of the adversarial-verify
  bias, deliberately: adversarial verify exists to refute a *claim*; the grading panel exists to not
  lose a *candidate*.
- **The job is filtering, not finding.** Sinks are cheap. This repo will produce hundreds of
  suspicious-looking sites. The work is filtering the fakes without losing the real one.
  **Understand the whole mechanism before verifying** — know what is real and what is fake *before*
  you run it — and give a one-sentence "why it is real" per survivor.

---

## Part 8 — Controls, evidence, and the reward-hack that will happen here

**The faithfulness pass runs in FRESH context**, by an agent that did not build the harness.

**The specific failure mode for this target**, stated plainly because it is not hypothetical:

> An agent builds a local driver for a composite action, feeds it a crafted event payload, watches
> the marker fire, and reports `confirmed` — while the **real GitHub Actions control flow would never
> have reached that code with that input**, because a trigger filter, an `if:` condition, a
> `permissions:` block, a GitHub-side event-shape constraint, or an earlier step would have stopped
> it first.

That report gets closed as not-reproducible, burns credibility with the program, and is exactly what
the OSS VRP tightened its rules against. **A local driver is a tool to FIND the path. It is never the
proof that the path is real.** Before any `confirmed`, a fresh-context pass answers in writing:

1. Which real trigger delivers this event, and does the workflow's `on:` filter accept it?
2. Does every `if:` between trigger and sink evaluate true with **attacker-controllable** values?
3. Does the job's `permissions:` block actually grant what the impact claims?
4. Is the input field attacker-controlled **on GitHub**, or only in our synthetic payload?
5. Would GitHub itself reject this event shape?

**Any answer of "not checked" means the verdict is not `confirmed`.** A mock, an emulator, a
reimplementation, or a fake client skips the validation the real system performs, and therefore
confirms claims the real system would reject.

Further non-negotiables:

- **Confirm from RAW output, never a wrapper's summary.** The local `rtk` hook has been observed
  reporting wrong test outcomes, wrong diff equality **and** wrong grep counts. Verify every such
  verdict with a second independent tool. Tooling is itself a reward-hack vector.
- **Every finding carries a negative control** on the byte-identical harness. Show the gate correctly
  rejecting the benign case before you claim it accepted the malicious one. **A detector that fires
  on both is useless; one that fires on nothing has not been shown to work.**
- **Re-validate each oracle inside every namespace.** Calibrating on `labeling/issue` proves nothing
  about `post-approval-changes`.
- **Quantify with the enumeration.** `N=<count> found by <method>` is the correct shape. A bare number
  without the enumeration that produced it is how a perfectly executed measurement of the wrong
  sample reads as the most rigorous result in the pass.
- **Synthetic canaries only.** Never a real key, token, or credential, in any harness, at any time.

---

## Part 9 — Adjudication and independent review

- Only the orchestrator or the oracle emits `confirmed`. A hunter may propose `suspected_success`.
- Every surviving candidate passes, in order: fresh-context regrade (`engine/regrade.md`),
  reward-hack check (`engine/pocinator.md`), chainability across the six angles
  (`engine/chainability.md`), then novelty, attribution and reportability.
- **The adjudicating lane is never told a flaw was expected and never shown your conclusions.**
  Discount a reviewer's precedent arguments if it read them; keep only its factual verifications.
- **A reviewer that corrects you downward is the mechanism working**, not a bad result.
- When a finding sits at `needs_review` or `needs_poc`, spawn the review lane. Committing a review
  needs the reviewer keypair (B3); an uncommitted review is not a gate that passed — record it as
  such rather than treating it as one.

---

## Part 10 — Recording and cascading

Append-only, updated at every synthesis point, never rewritten to match a later belief:
`rounds.md` · `hypotheses.md` (every kill, with the new signal that killed it) · `cascades.md` ·
`attempts.jsonl` (an attempt for every result; a finding to `unproven/` only on oracle-confirmed) ·
`progress.md` · `cleanup.md`.

**CASCADING is mandatory on every survivor.** Two questions, an answer recorded for each, even when
the answer is "nothing". Seeds are in `cascades.md`.

- **Q1 — how do I detect this same behaviour elsewhere?** Every action sharing that helper or idiom;
  the other `pull_request_target` workflow; `labeling/pull-request` if the flaw was in
  `labeling/issue`; the sibling Bazel rules.
- **Q2 — does the ORIGIN of that behaviour enable a different attack?** Environment read becomes
  secret disclosure. App-key disclosure becomes org-wide write. Org-wide write becomes source
  compromise in three OT0 repos. Label influence becomes merge-gate influence. Merge-gate influence
  becomes unreviewed code. Package write becomes execution in every consumer's CI.

**Q1 mostly yields siblings. Q2 is where a new class comes from.** Every cascade lead re-enters the
funnel and may cascade again. Every capped primitive stays in the primitive registry as a **fragment
awaiting composition** — a cap is not terminal.

---

## Part 11 — Persistence contract (effort, never verdict)

**Minimum eight hours of active research. Eight hours is a floor, not a target.** Do not sleep to consume
time. Keep reading source, building drivers, constructing inputs, measuring controls, rotating
agents, and opening untouched families.

**It is possible; if you give up you are not trying hard enough. Be more stubborn than the developer
was careful.** That governs **effort**. It licenses no conclusion and it never reaches Part 12.

Do not return because:

- the first wave produced nothing;
- several agents agreed the code looks robust;
- the most promising route turned out to be bounded;
- a driver was hard to build, or a chain was long;
- a lane was unfamiliar;
- a candidate came in lower than hoped;
- the tree was bigger than expected;
- *"this repo is well maintained, everything is SHA-pinned, there is probably nothing here"* — good
  hygiene on one axis is not a proof about sixteen families, and recon already found that same repo
  running an LLM on attacker text next to an org-wide App key.

A held vector is a **wrong turn to revisit with fresh recon**, not a dry verdict. When a sub-area
stalls, zoom out: re-bound the surface, look for missed entry points, redirect agents. When a
candidate is live, zoom in: complete the real path, the controls, the measurement, the chain.

**Persistence is evidence-licensed, not claim-licensed.** It raises effort; it must never raise
confidence. A confirmed primitive, a `strong` signal, or an operator prior **raises** the round bound
and forbids an early dry verdict. Absent such evidence, the floor applies. **Fishing is not
persistence.** Several bounded families do not prove the repo safe, and several suspicious shapes do
not make a finding.

**Do not reward-hack yourself into working less.** Shortcuts that look like progress and are not:
declaring a family exhausted after one pass; accepting a rule's verdict as a decision; calling a
local driver run a confirmation; grading a candidate with an agent that read your conclusions;
counting "no agent found anything" as enumeration; writing `covered-dry` without the Part 12 payload.

---

## Part 12 — TERMINATION CONTRACT

**This section is the operator's explicit instruction. It overrides any inclination to wrap up.**

### The run ends in exactly three ways. There is no fourth.

**T1 — a Critical or High finding, confirmed, escalated, cascaded, reproducible and reviewed.**
Every oracle passed, fresh-context regrade clean, pocinator clean, negative control present,
faithfulness questions all answered, attribution stated, novelty checked, cascade ledger complete,
and the impact demonstrated at its maximum inside the authorized surface.

**T2 — `covered-dry`, proven to the enumeration bar in the payload below.**
Not asserted. Not "the agents did not find anything." Proven. Exhaustion of 100% of the repo, re-done multiple times through the funnel stages on uncertainty or lack of direction. Sometimes take a step back and try to see the bigger picture in it all. Then direct hunter agents in parallel for each lane to hunt.

**T3 — `blocked`.** A safety or authorization gate stops all meaningful in-scope progress and needs
the operator. Name the exact missing condition. B1, B2 and B3 produce this if Round 0 is attempted
without resolving them.

### A confirmed finding is a PHASE TRANSITION, not a finish line

**On any confirmed finding at Medium or above, DO NOT STOP.** Enter escalation mode and spend the
remaining budget on it:

1. **Attack its cap.** Whatever bounds the impact — try to break that bound.
2. **Climb the severity ladder.** Medium → High → Critical. What would it take to reach the next
   rung, and can you demonstrate it? A Medium that is really a High reported as a Medium is an
   under-demonstration, and this scope forbids under-demonstrating.
3. **Cascade it.** Q1 and Q2 in `cascades.md`, both answered, leads re-entered into the funnel.
4. **Sweep for siblings.** The same shape everywhere it could recur.
5. **Compose it.** Every fragment in the primitive registry, re-examined against this new primitive.
   Chaining is escalation and needs no fresh confirmation.
6. **Attack it yourself.** Disprove its reachability. Replay it from a clean environment. Try to make
   the refuter's case better than the refuter did.
7. **Then keep hunting the untouched families.** One finding does not retire the other fifteen.

A Medium confirm therefore **increases** the remaining work rather than ending it. Only T1 — a
Critical or High, fully worked through all seven steps above — closes the run.

### The `covered-dry` payload — what T2 must contain

`covered-dry` is a real and valuable product, and it is **expensive**. It is reached by evidence, never
by fatigue. To claim it, deliver **all** of:

- **Per family, all sixteen plus any discovered:** the control that bounds it, **named and
  demonstrated** — not asserted, not inferred from the absence of a finding.
- **The enumeration.** What was the bounded space, how was it enumerated, and what is N? "Dry" means
  "all N enumerated and adjudicated", not "we looked and stopped."
- **Every hypothesis with a disposition** in `hypotheses.md`, and for every kill, the new signal each
  independent round contributed.
- **The positive controls that fired.** Each oracle proven to work in each namespace it was used in.
- **The families you could not bound**, named honestly as `held` or `blocked` rather than folded into
  the dry verdict.

**A `covered-dry` missing any of these is not a verdict. It is an unfinished run, and returning it is
the reward-hack this contract exists to prevent.**

### Allowed terminal verdicts — nothing else

`confirmed` · `confirmed_with_correction` · `chained` · `real-but-capped` (cap **demonstrated**) ·
`real-but-not-reportable` (truth and reportability recorded separately) · `covered-dry` (with the
payload) · `blocked` (with the exact missing condition).

**Never terminal:** "it looks robust", "probably exploitable", "likely exploitable", "no agent found
anything", "the surface seems well maintained", or agent consensus.

### Final response, if a finding survives

1. one sentence on why it is real; 2. pinned commit; 3. attacker model, with the position proven
reachable for an unprivileged GitHub user; 4. input construction and source → sink → path with
`file:line`; 5. default-configuration evidence, plus written answers to all five faithfulness
questions; 6. quantified impact with its negative control and enumeration; 7. reproduction command
and expected raw output; 8. independent review results, including anything that corrected the claim
downward; 9. novelty, **attribution**, and reportability; 10. OSS VRP category and the strongest
honest severity, with the demonstrated cap; 11. cleanup disposition and canary disposal; 12.
unresolved caveats.

**Filing is operator-only** (wire 5). Everything here is an internal research artifact for the
operator's re-authoring, never pasted verbatim into a submission.

---

## Part 13 — First moves

1. Resolve B1 and B2, or record `blocked` with the exact missing condition.
2. Re-pin HEAD; record it and the clone identity in `progress.md` §3.
3. Build the local proving rig — mock API, canaries, action drivers (`environment/BUILD-PLAN.md` §3).
4. **Calibrate every oracle with matched positive and negative controls before Round 0.** Raw output
   to `evidence/oracle-calibration/`.
5. Settle F13 (the committed `*_token.data` blobs) — it is cheap; settle it and move on.
6. Read `github-actions/labeling/issue/` source **before** forming the F1 hypothesis.
7. Launch Round 0 blind: independent deepseek-v4-pro hunters, one distinct family each, no shared priors.
