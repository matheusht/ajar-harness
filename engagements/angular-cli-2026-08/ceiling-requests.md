# ceiling-requests.md — ceilings that only AUTHORIZATION is holding down

Operator standing instruction (2026-08-16): **scope will always widen if more authorization is what
it takes to prove a ceiling. Always.**

That does not authorize anyone to widen it. The five wires in `scope.md` are unchanged. What it
changes is that a ceiling blocked only by scope is a **REQUEST**, not a silent cap.

Before this ledger existed, the highest-value result in `angular-dev-infra-2026-08` — the GCP
service-account key to RBE cache-poisoning chain, the Supply-Chain top band — was written out in
full and marked "hypothesis, not claimed" because probing it trips wires 2 and 4. Correct about the
act. Wrong about the record: it capped instead of asking.

**The orchestrator does not perform the act.** It states the request precisely enough that the
operator can answer yes or no in one reading.

| # | The ceiling | Band it reaches | Exact act required | Wire tripped | What is irreversible | Cleanup path | Operator |
|---|---|---|---|---|---|---|---|
|   |             |                 |                    |              |                      |              | pending  |

Rules:
- One row per blocked ceiling. Never batch several acts into one request.
- "Exact act" means the specific command or probe, not a category.
- If nothing is irreversible and no wire is tripped, it is not a ceiling request — just do it.
- An empty table at close means either nothing was scope-blocked, or nobody asked. Say which in
  `progress.md`.
