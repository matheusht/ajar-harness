# Goal prompt — REVISIT / REDO / RE-RUN an engagement (standard format)

Follow the harness [entry/resume procedure]([HARNESS_CHECKOUT]/skills/source-engagement-bootstrap/references/goal-template.md#entry-and-resume-procedure) for signed-scope/init ordering, inspector reconstruction, list/next/gate queue reads and supported runner readiness.


> **This is the standard goal-prompt format for REVISITING / REDOING / RE-RUNNING an already-closed
> engagement when the operator wants escalation vectors, exhaustion checks, or a fresh pass** ("was it
> exhausted?", "find the critical escalation, but no reward-hacking", "the report was rejected / judged
> not innovative"). Copy it into `engagements/<id>/goal-prompts/<id>-goal-prompt-<round>.md` and fill
> every `<...>` with verified facts from the prior engagement + this round. For a brand-new engagement,
> use `goal-prompt-START.md` instead. The LLM adapts structure and detail to the engagement's domain;
> the section skeleton below is the constant. Binding gates (CLAUDE.md, scope.md, engine/*) always
> override this template.

GOAL: white-box EXHAUSTION + ESCALATION-AS-THE-PRODUCT re-run of the <TARGET> — <PROGRAM>
(program: <PROGRAM NAME, PLATFORM, CONTACT; if no formal program, note the disclosure reality — prior
report feedback, e.g. "not innovative enough", is the trigger and the re-run's job is to find what the
prior pass missed or prove the ceiling is structural>). Prior engagement <PRIOR_ID> is CLOSED; its
findings are STARTING PRIORS, not re-hunt targets (re-derive each from real source/bytecode
fresh-context, never inherit the draft's conclusions). The prior independent review
(<REVIEW_FILE>) and the escalation ledger (<LEDGER_FILE>, CLOSED <N>/<N> lanes) are the binding prior
state. Audit baseline = the LIVE DEPLOYED / PINNED source (mainnet block snapshots or exact commit — see
the admitted source/environment records for the frozen block / source freeze <SHA256>). <RPCS/TOOLING: endpoints, toolchain, the
tooling gaps that blocked the prior pass — re-verify reachability, the blocked surface is the highest-
value unexplored lane>. IN: every surface below; the operator will provide <SECRETS/CREDENTIALS for any
API/web/testing> separately, and <API/WEB TESTING> is IN once they arrive.

TARGETS: <EXACT TARGETS: contracts/addresses/impls, repos/commits, APIs, web, domains, all surfaces,
each with its identity and prior coverage status — explicitly flag which surfaces were NEVER examined
in the prior pass (the never-audited surface is the flagship lane, because a cap-breaking path there
re-rates the whole stack)>.

OUT/KILL before deep work (prior-audit exclusions + prior-pass conclusions + scope constraints): the
<N> already-fixed items VERIFIED DEPLOYED/CLOSED (<LIST: check for INCOMPLETE fixes only, never
re-report>); <PRIOR FINDINGS WITH FINAL SEVERITIES: re-derive, don't re-grade — F2-001 etc. stay at
their adjudicated severity unless a NEW mechanism escalates>; the <PRIOR NEGATIVES> (re-verify with the
enumeration probe — a negative is only as good as its enumeration); the <PRIOR CEILING / cap> (re-attack
— a change in the capped dimension IS a new finding); any live transaction that <MOVES FUNDS / MUTATES
STATE> on ANY real <NETWORK> (Zone-2 ceiling, never waived). <REVIEW-GATE FLAGS from the prior close-out:
killed-then-shipped findings, hedges stripped, stale numbers, unfounded claims — discipline the
packaging layer, nothing enters a submission that contradicts a verdict in findings/>.

BUILD A CARD FIRST if a lead needs one: <VULN CLASSES WITHOUT A DEDICATED CARD>. Author a
skills/{vulns,patterns} card for the trigger class BEFORE deep grading — a card-less lead has no oracle.
Oracle-grade it. Log a pattern-candidate.

PIPELINE: narrow->classify->triples->reachability->confirm->faithfulness-verify->chainability->Post
(engine/whitebox-analysis.md; jump back freely). Grading agents manage the pipeline themselves and do
not stop until every lead is exhausted and adjudicated. Full persistence mode (engine/persistence.md) —
explicit effort budgets and material new evidence control the re-run. Revisit a held vector when new
evidence changes its bounded search; preserve refutation and independently reviewed exhaustion.

CASCADING (second-order discovery — every discovery is a tree branch, not an endpoint): when a finding,
escalation, or significant research discovery survives, INTERROGATE IT WITH TWO QUESTIONS. Q1: "how can
I detect similar behavior elsewhere?" — the same shape in a sibling contract/module/input surface
(<SEED: one function guards, its sibling doesn't → which OTHER asymmetric pairs exist; one function has
replay protection, its sibling doesn't → which OTHER untrusted-role functions lack the guard the
siblings have>). Q2: "does the ORIGIN of that behavior enable other attacks?" — the root mechanism as a
primitive (<SEED: reversible-but-detectable → detection-latency is the exposure; inflate-the-denominator
→ masks the real state; no-idempotency-key → production double-settlement; delegation-executes-on-
incoming-only → outgoing-tx keys are bare>). Seed cascades from the confirmed + prior state
(<LIST THE PRIOR FINDINGS' CASCADE SEEDS, each with its Q1/Q2 target>). LOG EVERY CASCADE in
cascades.md (append-only): parent discovery id → Q1 answer → Q2 answer → cascade leads (target:fn,
hypothesis, why real/fake, confidence) → disposition. Every cascade lead enters the pipeline like any
other hypothesis, gets multi-round graded, and can itself cascade — the positive feedback loop is the
whole point. It will get messy; the ledger is what keeps the mess productive.

CHAINABILITY (per confirmed/real finding, run fresh across the six angles of engine/chainability.md —
persistence, repeatability, composition, population/reach, fan-out, sibling-recurrence — checked
against REAL <BYTECODE/SOURCE>): verdicts `bounded` / `amplifier_found` / `new_finding_spun_off` /
`needs_more_evidence` / `blocked`. THE PRIOR PASS ESTABLISHED <N> KILL CONDITIONS / CEILINGS; the
re-run's escalation job is to attack each one: (a) <KILL CONDITION 1: e.g. "no exit path" — but the
<NEVER-AUDITED SIBLING> DOES have the exit; if any path reaches it, the ceiling breaks — THE highest-
value chain candidate>; (b) <CEILING 2: e.g. "no liquidity/venue" — re-enumerate ALL venues exhaustively
by <ENUMERATION METHOD> — one venue change = a NEW finding; the prior "$0 measured" error was measuring
ONE dead instance of N>; (c) <CEILING 3: e.g. "the primitive destroys, not transfers" — verify cheaply,
then look for a NEW redirect/hook>. Additional headroom per the prior review: <REVERSIBILITY — the
exposure is DETECTION LATENCY, no rate-limit/cooldown; is there a way to make it undetectable or the
recovery fail?>, <CONCENTRATED PRIVILEGE — the one thing that could have forced High; re-verify the path
end-to-end on a fresh env, then look for the adjacent asymmetry>, <THE INERT-REMEDY TRAP — the intuitive
incident response destroys collateral / does nothing — a Medium-trap worth sharpening, not re-grading>,
<UNAUDITABLE COMPONENT — unresolved-to-a-reachable-chain domain; is there an off-chain attack or a
completion gap?>.

OPERATING MODEL: one bounded worker by default, with independent cold review in distinct sessions.
Extra concurrency needs explicit authorization and a concrete independent assignment. The orchestrator
checks direction-changing claims against source evidence and an independent reviewer before changing
any verdict; agreement is not an oracle. Preserve real pinned-path controls and faithfulness checks.
Use the requested available models and finite budgets. Evidence-grounded persistence can return
refuted, bounded or blocked outcomes; neither a prior nor elapsed effort establishes a finding.

KEY ROUTING (the ceiling = a NEW <Critical/High> mechanism, or a PROVEN structural cap per surface; do
NOT re-grade the prior severities): (1) <THE NEVER-AUDITED SURFACE — the flagship lane>: <mechanism
family to probe — first-depositor, rounding, exit-path, permit, donation, standard-divergence,
upgrade-admin>. If yes → the ceiling breaks; this is the round's flagship lane. (2) <ROLE GRAPH /
CUSTODY> — every role × every contract (now including <NEW/NEVER-CHECKED components>), getRoleAdmin on
ALL roles (never-granted ≠ can-never-be-granted — the single highest-value check), delegation targets
(are ALL <N> delegated keys behind a dead/configured policy?), bootstrap-authority tracing, upgrade-key
equivalence (<X>/<Y> upgrade keys ≡ <Z>). If a role reaches unbounded <MINT/BURN/EXIT> without a
multisig → High governance (only the novel delta counts). (3) <CROSS-COMPONENT COMPOSITION> — can value
move from the capped side to the redeemable/exit side; can a <BRIDGE/MESSAGE> argument create or consume
state across domains; can a stranded/unauditable gap be exploited; is there a completion gap an attacker
can race. If yes → funds-loss Critical class. (4) <OFF-CHAIN / API / WEBHOOK> (once the operator shares
secrets) — <ENDPOINT COUNT + surface list>: <prior-clean class> was clean prior but business-logic
(<AUTHORIZATION FOR MONEY-PATHS>), <SIGNATURE-FORGERY class>, <JWT/algorithm confusion>, mass-assignment,
and any path where off-chain state reaches on-chain <MINT/BURN/EXIT>. If yes → an authorization break.
(5) <ASYMMETRIC-PAIR SWEEP> — every function whose sibling has a guard it lacks (the "every sibling
bounds itself, this one doesn't" shape is the strongest oversight evidence and the prior review's own
rubric). (6) <VENUE/LIQUIDITY> — exhaustive re-enumeration of every venue for <ASSETS> on all reachable
chains (<ENUMERATION METHOD: Initialize-log filter + state-read + 2026-DEX set>); the <CEILING> is the
cap on EVERY finding's realizable severity — breaking it re-rates the whole stack. Each sub-surface:
what the invariant should be, how this code breaks it, in one sentence.

AUTHORIZATION (scope.md signed <DATE> — <ZONE-2 CEILING>): the real <NETWORK> is READ-ONLY forever —
<eth_call/getCode/getStorageAt/getLogs/getTransactionCount/getBalance ONLY> / <source-only>. NO
transaction on any real <NETWORK>, ever — no signed payload, no <sendRawTransaction>, nothing that
<moves funds/mints/changes ownership>. ALL state-changing proofs run on a LOCAL <FORK/REPRO> of the real
chain pinned to a frozen state, verified clean against live values before use (unique high port +
explicit --fork-block-number + verify a known live value + generate fresh keypairs and assert
<eth_getCode == 0x> on the <FORK> before use — <DEFAULT ACCOUNTS ARE NOT CLEAN IN THE PRIOR PASS'S
DOMAIN>). Escalate each confirmed bug to MAXIMAL demonstrated impact inside the fork (a forked-state
delta, a fork-wide exit path, an unbounded <MINT>) then stop — never expand the surface. Obtain explicit human confirmation before every Zone-2 PoC artifact under root policy. Retain the other
human gates for: any real-network transaction, any real user/funds/key, any
publication/disclosure step. The fresh-confirm gate is NOT waived. Do NOT fabricate / reward-hack /
overclaim (escalation.md §1 marginal-contribution: severity = the delta the bug adds vs the world
without it, never the total nearby; and a chain whose preconditions include <A PRIVILEGED CAPABILITY>
must state its marginal over calling <THE DIRECT FUNCTION> directly). Every material number in every
finding carries its block/commit number and its measurement method ("N=<count> found by <method>, the
one tested was dead" is the correct shape; "measured <$0>" without enumeration is not). Emit attempt
always, finding only on oracle-confirmed; operator re-authors + files; cleanup.md logged.

FIRST MOVE: (1) follow the shared entry/resume procedure, preparing the complete scope/goal/readiness draft before signature and admitting records only after required authority; verify existing pinned identities and acquire only missing explicitly scoped <NEVER-FETCHED SOURCE>; (2) after signed scope, authorized init and execution readiness, verify the authorized <TOOLCHAIN> and <RPC/ENV> availability; record unavailable requirements as blockers in canonical environment records; (3) re-derive the prior-priority findings fresh
(<LIST: F2-001 etc.>) — one sentence "why it's real (or not)" per survivor, log the disposition in
cascades.md; (4) formal recon: complete the activation-signals table in recon-signals.md — confirm every
role × getRoleAdmin across ALL components, map the delegation graph, enumerate ALL asymmetric guard
pairs, inventory the <BRIDGE> domains and the stranded gap, and run the exhaustive venue enumeration
for both <ASSETS> on all reachable chains; (5) oracle calibration vs the prior review's severity
precedent + the severity-precedent-corpus (note: the corpus has NO <DOMAIN> bucket and NO
reversible-DoS exemplar — flag this gap, do not force-fit a different class onto a <DOMAIN> finding);
(6) select one bounded next assignment from the computed queue, prioritizing <NEVER-AUDITED-SURFACE>;
record missing authorized environment access as blocked rather than starting an unavailable lane.
