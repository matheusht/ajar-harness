# lessons.md — portable lessons (routing + false-positive discipline)

Newest first. No client verbatim; abstract shapes only.

## L-1 — A PoC that seeds ledger state must prove the state is REACHABLE, not just that the code crashes on it
The engagement confirmed a crash on a seeded state (a temp-bad unit at a balled MCI) — and the
refuter proved the state machine forbids it (temp-bad resolution is atomic with ball creation).
The same error class later bit our OWN finding: a fee-poisoning drive seeded the honest unit with
the attacker's equal timestamps, and the real settlement ordering made the window count 1.
**Portable rule:** every synthesized-state PoC carries the burden of a state-reachability argument;
a real-network (or real-path-with-documented-state) corroboration is the tie-breaker. "The code
crashes on this state" and "an attacker can create this state" are different claims.

## L-2 — The escalation phase can refute the finding it escalates; that is the process working
The adversarial escalation round refuted the engagement's own fee-poisoning finding (real-path +
real-network evidence), and the demotion went through the normal lifecycle. **Portable rule:** an
escalation pass must attack the finding's caps AND its reachability with equal rigor; a demotion on
real evidence is a first-class outcome, not a failure of the phase.

## L-3 — Verify WHERE a settlement/reconciliation runs relative to state transitions before believing a window-count claim
The fee formula is exponential in a window rate; the apparent window (all units between the last
ball and the tip) collapses to 1 because each unit settles after its own MCI is balled. **Portable
rule:** for any rate/ratio computed over a "window," trace the state transition that closes the
window (ball creation, stabilization, commit) and measure the window at the settlement instant, not
at the tip.

## L-4 — SQL-engine semantic claims must be executed, not assumed from documentation
A "documented coercion" (unary plus on a TEXT column) that seemed certain was empirically false on
all 4 engines (it coerces only pure-integer strings). **Portable rule:** any claim about a specific
engine's behavior gets executed on that engine (or the nearest available one) before it becomes a
finding; documented behavior + no execution = needs_review.

## L-5 — Defense-commit subjects are the best routing seed; they name the attack class being hardened
The vendor's own commits ("enforce new rules for all new units, even if attached to an old part of
the DAG"; "uniqueness of spend proof is not verified in light") named the exact attack classes and
surfaced the S1 rule-gating family and the spend-proof uniqueness family before any deep analysis.
**Portable rule:** read the recent security-relevant commit history first; a fixed bug marks a
family, not a target — then check the migration is COMPLETE (both sides of a rule boundary:
validation side had the disjunct, evaluation side did not).

## L-6 — A blind terminal round can find what N directed families miss
Sixteen directed families covered validation, consensus, signatures, formulas, assets, private
payments, network, storage, AA, encoding, races, fail-open, composer, economics — and a single
prior-free sweep found the one genuinely new crash class (an adjacent-surface wallet crash via the
device-message decryption path). **Portable rule:** schedule a blind no-new-family sweep before
declaring coverage; it is the cheapest insurance against family-blindness.

## L-7 — Bearer-token uniqueness keys must bind the committed value, not a party-chosen identity
A uniqueness registry for a bearer secret (gift codes, payment proofs, capability tokens) keyed on
a claimable identity (the unit's own author) is dodgeable by any party who can choose the key. The
fix pattern: resolve the token's committed value at the registry, or store the committed owner and
key on it. The sound sibling in the same codebase (root bound to an on-chain value) is the contrast
to teach from.

## L-8 — Uncaught-throw patterns: throws in async COMPLETION callbacks escape, throws in async
ITERATORS do not
All four crash candidates were throws inside `conn.query` completion callbacks (escaped to
`uncaughtException` → process death); the harness's own earlier crash (parent selection) confirmed
the mechanism incidentally. **Portable rule:** in callback-heavy services, grep for `throw` inside
completion callbacks — the async-library boundary (iterator vs completion) determines whether a
throw kills the process; convert to `cb(err)` as defense-in-depth even when the state is currently
unreachable.
