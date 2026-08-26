# engine/escalation.md — drive a confirmed finding to its MAXIMUM *honest* impact

> Companion to `engine/chainability.md` (the analysis method: "does this finding compound?") and a
> sibling of `engine/regrade.md` / `engine/pocinator.md` in the Post-stage family. Chainability asks
> whether scope is complete; **escalation asks how hard to push a *confirmed* finding toward its true
> ceiling, and — the harder half — how to do it without reward-hacking the severity upward.** Pair this
> with `engine/persistence.md` (exhaust leads, held vector = wrong turn not a stop) and the prime
> directive in `CLAUDE.md` §0 (rigor, not findings; if you can't say in one sentence why it's real, it
> isn't). This doc is the reference an agent loads for full escalation context, and it ends (§6) with a
> **parametrized goal-prompt blueprint** the operator swaps per engagement.

## 0. The two-sided goal — and the tension that defines it

The mandate is **maximum-impact fidelity**: never under-demonstrate a real bug into a lower tier, and
never over-sell it into one it can't honestly reach. Both failures cost you. Under-demonstrating leaves
severity (and bounty) on the table and gets a real bug rated below its truth. Over-selling gets the
report closed as invalid, burns program Signal, and is a form of reward-hacking yourself.

So every escalation move in §2 is paired with a **keep-reason guardrail**. The target is "target HIGH,
but if it isn't, BE SURE of that" — a proven `real-but-capped` with the cap *demonstrated* is a
first-class success, identical in value to a confirmed escalation. Giving up early and honest-capping
are opposites: one is untested surrender, the other is a proven ceiling.

## 1. The keystone anti-reward-hack: the marginal-contribution critique

**Before crediting any escalation, ask: what does the world look like WITHOUT this bug? The severity is
only the DELTA the bug adds — never the total bad outcome it happens to sit near.**

This is the single highest-leverage discipline in the whole doc and it is *not* one of chainability's
six angles. Worked example (Cosmos Hermes, 2026-07-19): the "client-expiry → funds-stranded" escalation
looked like a fund-loss HIGH. The critique: *if Hermes's sole node is malicious and Hermes is the sole
relayer, the client expires anyway — no valid headers means no updates, bug or no bug.* So the bug's
**marginal** harm collapsed to (a) turning a *visible* ongoing-retry failure into a *silent* permanent
death (operator can't notice and switch nodes), and (b) an instant panic under a non-default flag. Real,
but a conditional appendix — not "creates the fund loss." That honest-down-scoping is what made the
whole pass credible when the *other* chain (whole-chain blackout) genuinely was HIGH.

Apply it to every escalation lead: subtract the precondition. If the bad outcome already happens once
the precondition is met, the bug is only the delta on top, and you rate *that*.

## 2. The escalation move-set (each with its keep-reason guardrail)

Proven on real Cosmos escalations (Hermes Medium→HIGH; the `iavl` state-sync crash chainability passes;
the eureka PC-10 honest cap). Several independently corroborated on a separate web-app engagement — the
moves generalize across domains; instantiate each concretely, never reason about it in the abstract.

1. **Attack your own caps first.** Your most confident caps — especially ones you "empirically proved"
   with a single input shape — are the prime escalation targets. An empirical proof of a cap only tests
   the inputs you tried; it's an assumption until adversarially tested with inputs *designed to break
   it*. Point a hunter explicitly at each cap you wrote.
   *Guardrail:* the break must be a real input against real code, reproduced — not a hypothesized one.

2. **"What is the worst honest version," not "is it real."** A confirmed finding is the START of
   escalation. Re-open its original disposition and treat every cap baked into it (same-user, needs-a-
   config, needs-a-policy) as an untested assumption to remove or prove.
   *Guardrail:* removing a cap requires showing the real path that removes it, with file:line — not
   asserting it's removable.

3. **Find the shared chokepoint (blast-radius widening: local → systemic).** A per-instance bug often
   funnels through a single shared resource that widens its reach. Hermes: one crafted event → the
   *single per-chain event-source thread* → the WHOLE chain's relaying dies, not one channel. Look for
   the shared mutex/thread/cache/registry the local effect propagates through.
   *Guardrail:* trace the actual topology in source (who shares what, who respawns whom) — a widened
   blast radius is a claim about real wiring, not p2p/architecture intuition.

4. **"Defeats its own mitigations" is a severity multiplier — and rebuts the exclusion.** If the bug
   stays invisible to the very controls that would otherwise cap it (health-check passes, systemd
   `Restart=always` inert, `dump-state` lies, log-alerting sees nothing), that is what lifts it a tier
   AND what rebuts the boilerplate "DoS mitigated by operational controls" exclusion. Demonstrate the
   defeat of each named control explicitly.
   *Guardrail:* prove each control is actually defeated (process stays up under unwind-not-abort; the
   disconnect is silently swallowed) — don't assert "monitoring won't catch it."

5. **Default/shipped-config reachability gate.** An escalation only counts at the tier its *default,
   shipped* configuration reaches. Hermes's whole-chain blackout mattered because it fires in the
   DEFAULT Push/WebSocket mode via the `Tx` branch — not only a niche mode. A finding gated behind a
   non-default flag (Hermes's `trusted_node=true` instant-kill) is a real but *conditional* escalator,
   labeled as such.
   *Guardrail:* confirm the default config from shipped templates/docs and trace that the default path
   reaches the sink; label every precondition (default vs opt-in vs sole-relayer) honestly.

6. **Chains = verified output→precondition edges, each with a file:line.** Build a chain as a graph:
   for each finding pair, does A's concrete OUTPUT satisfy B's concrete PRECONDITION, checked in source?
   The surviving Cosmos/Backstage chains all came from one real edge; the broken ones broke at a
   specific named control. "These probably combine" is not a chain.
   *Guardrail:* every edge gets a file:line; every break gets the named blocking control that stops it.

7. **Sweep sibling instances after one confirmation (one-off → class).** Once a parser/logic bug is
   confirmed in one place, sweep every sibling with the same code shape — the root cause usually recurs,
   and "systemic across N of M instances" is a materially bigger finding than a one-off.
   *Guardrail:* read each sibling's actual guarding logic; a sibling that IS guarded is an honest
   negative that strengthens the finding, not something to omit.

8. **Lens diversity, not vote redundancy.** Escalate with hunters asking DIFFERENT questions (one:
   "push this finding's own ceiling"; one: "what larger chain is this a link in"; one cross-finding
   graph pass), plus an independent skeptic and an independent severity judge. N identical "is this
   real" votes surface nothing new; three different lenses surface three different things.
   *Guardrail:* see §3 — a hunter's "this escalates" is a hypothesis, not a confirmation.

## 3. Keeping reason — the confirmation discipline for escalations (anti-reward-hack)

Escalation multiplies the reward-hack surface, because a bigger claim is a bigger temptation. The
filtering problem is unchanged from `whitebox-analysis.md`: the hard part isn't finding a bigger story,
it's confirming the ONE real one and confirming that the *verification itself* is real, not a harness
that replays a control flow the real code would never take.

- **Hunters generate; the orchestrator confirms against ground truth.** Never promote a hunter's "this
  escalates" to `confirmed` on its word. Re-read every decisive code hop yourself, or re-run the check
  against the real pinned deps. (`CLAUDE.md` §2: only the orchestrator/oracle emits `confirmed`.)
- **Re-run PoCs in your own hand; a builder's "PASS" is not ground truth.** Builders stall, summarize
  optimistically, or paste output they didn't produce. Read pass/fail from the raw log yourself
  (`memory/rtk-test-summary-unreliable`).
- **Faithful harness vs faked decisive hop — name which every mock is.** An acceptable harness boundary
  injects an *external* dependency the real code then consumes (and that the project's own tests mock
  the same way). A faked hop mocks the thing under test. The decisive hop must run REAL code. This is
  the difference between a PoC that proves the claim and one that lies (`engine/pocinator.md`;
  `memory/fake-client-poc-invariant-check`).
- **Verify-of-verify cuts BOTH ways.** The same discipline that caps an over-claim also rescues an
  under-claim: in practice it has bounded an inflated chain down AND resurrected a real escalation a
  first-pass refutation wrongly killed. Run it in both directions — don't only look for reasons to
  shrink.
- **Independent skeptic (mechanism) + independent judge (severity), fresh context.** The skeptic
  re-verifies every hop and stress-tests the marginal-contribution critique; the judge rates severity
  cold. Both catch citation drift (Hermes: the skeptic caught a `header.rs:50` vs `foreign_client.rs`
  trigger-site mix-up).

## 4. Name the honest ceiling — and floor a chain by its strongest link

Every escalation pass ends by stating the ceiling AND why it can't go higher, in one line, tied to the
capping metric. Hermes: "HIGH availability — off-chain relayer, funds *frozen* not stolen, `S:U` caps
pure-availability below Critical; no theft/halt/consensus break." That sentence is the deliverable as
much as the escalation is.

For a multi-finding chain, the chained severity is **floored by the strongest independently-reachable
link**, then adjusted only if a weaker link *provably* raises it. Hermes chain = HIGH, floored by the
whole-chain blackout (A); the conditional funds-stranded link (B) did not lift it to Critical, and
saying so plainly is what kept the chain honest.

## 5. Terminal states for an escalation pass

Mirror `engine/persistence.md`'s "dry is real only if bounded." An escalation pass closes in exactly
one of:

- **`escalated-confirmed`** — a real, source-verified, default-config-reachable higher tier, confirmed
  by skeptic + judge. Updates the finding's severity + Impact (chainability's `amplifier_found` folds in
  here).
- **`real-but-capped`** — the ceiling is proven, with the capping metric named and the marginal-
  contribution critique applied. A first-class success, NOT a failure.
- **`bounded`** — angles close cleanly; scope is exactly what was already claimed.
- **`new_finding_spun_off`** — a genuinely distinct vuln surfaced; log it separately, do not stretch the
  current finding's narrative to cover it.
- **`no-escalation-found-and-SURE`** — every lead exhausted per persistence mode (bounded space, all-N
  adjudicated), not "the model gave up." This is only legitimate if you can name the leads you closed
  and how. "I could not escalate this because X (file:line)" is a result; "I didn't find more" is not.

Never silently close. `escalated-confirmed`/`real-but-capped` rewrite the report; `no-escalation` is
stated with its exhaustion trail.

## 6. Parametrized escalation/chainability goal-prompt blueprint

Fill the `<...>` slots per engagement/finding; keep the fixed doctrine. This is the reusable prompt to
hand an escalation pass. (Companion to the per-asset exhaustion goal-prompts — this one runs AFTER a
finding is confirmed.)

```
GOAL: ESCALATION + CHAINABILITY pass on <FINDING-ID(s)> in <asset @ pinned tag>. From a FRESH
perspective, drive each to its MAXIMUM *honest* impact and see if they chain into something bigger.
Target <HIGH/Critical> but if it isn't there, BE SURE of that. Baseline: <one-line current
severity/claim + its current caps>. Binding: CLAUDE.md, scope.md, engine/{escalation,chainability,
regrade,pocinator,persistence}.md. Read <coverage-matrix + prior phase verdicts + pattern-candidates>
FIRST. PoC = real runnable code exercising the REAL decisive hop; max-impact, not more/less.

ANTI-REWARD-HACK (keystone): apply the MARGINAL-CONTRIBUTION critique to every escalation — subtract the
precondition; the severity is only the DELTA the bug adds vs the world without it, never the total bad
outcome nearby. Do NOT fabricate, do NOT reframe onto a higher-tier class the code doesn't support, do
NOT build a harness that replays a control flow the real code wouldn't take. Hunters PROPOSE; only the
orchestrator/oracle emits confirmed — re-read every decisive hop in source + re-run every PoC yourself
from RAW output. Name which every mock is (acceptable-external-dep vs faked-hop-under-test).

MOVES (instantiate concretely, check in source): (1) attack MY OWN caps first — <list the caps to
break> — an empirical cap only tests inputs I tried. (2) "worst honest version," not "is it real." (3)
find the SHARED CHOKEPOINT a per-instance effect funnels through -> blast-radius widening (local ->
systemic). (4) does it DEFEAT its own mitigations (health-check/restart/monitoring/<controls>)? = tier
multiplier + rebuts the ops-mitigation exclusion. (5) DEFAULT-config reachability gate — only counts at
the tier the shipped config reaches; label every precondition (default/opt-in/sole-X). (6) CHAINS =
verified output->precondition edges, each file:line; every break gets its named blocking control. (7)
sweep SIBLING instances after one confirmation (one-off -> class); a guarded sibling is an honest
negative. (8) LENS DIVERSITY not vote redundancy — one ceiling-pusher, one chain-linker, one
cross-finding graph, + independent SKEPTIC (mechanism, every hop) + independent JUDGE (severity, cold).

PERSISTENCE: exhaust all leads (engine/persistence.md) — a held vector is a wrong turn to revisit, not a
stop; bound the space so "no escalation" = all-N-adjudicated, never "gave up." It's possible; if you
give up you're not trying hard enough — but if it genuinely caps, prove the cap.

CEILING: end by naming the honest ceiling + the capping metric (why it can't go higher), and floor any
chain by its strongest independently-reachable link (adjust up only if a weaker link PROVABLY raises
it). TERMINAL STATE (exactly one): escalated-confirmed / real-but-capped (cap PROVEN) / bounded /
new_finding_spun_off / no-escalation-and-SURE (with the exhaustion trail). Emit attempt always, finding
update only on oracle-confirmed; operator re-authors + files; cleanup.md logged.
```

## 7. Model tiers

Same split as the sibling docs (`CLAUDE.md` §2). The escalation *judgment* — is this a real amplifier
or a clean cap, does the marginal-contribution critique hold, what's the honest ceiling — is
planning/orchestration-tier (Opus). The mechanical legwork under a move (trace a call graph, grep
siblings, re-run a check) is Hunter/Helper-tier feeding the planning-tier verdict. The independent
skeptic and judge run fresh-context, on the reasoning tier, because both are severity/mechanism
judgment calls. Long-horizon exploit-engineering under an escalation (the tens-of-thousands-of-lines,
days-of-work kind) is Codex grunt work — Opus plans and adjudicates, Codex builds; don't invert.

---

**Provenance:** distilled from Cosmos (`hermes-phase/chainability.md` Medium→HIGH; the `iavl`
state-sync chainability passes; the eureka PC-10 honest cap) at operator request 2026-07-20. Moves 1–2
and 6–8 were independently corroborated on a separate web-app engagement whose own retrospective is
still pending-close, so their authoritative examples here are Cosmos-based and target-agnostic; promote
the cross-engagement version into memory only after that engagement closes and the moves are re-scrubbed
(see that engagement's `PENDING-AFTER-CLOSE.md`). The marginal-contribution critique (§1) is the
escalation-specific companion to chainability's six angles — kept here rather than jammed into
`chainability.md`'s canonical list, which promotes angles only on repeated cross-instance evidence.
