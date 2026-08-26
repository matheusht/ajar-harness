# scope.md — engagement authorization gate

**The loop refuses to run until this is filled and signed.** Copy this `_TEMPLATE/` into the
target's own project repo (Plane 3) per engagement.

## Engagement
- **id:** `<client-YYYY-MM>`
- **target:** `<url / app / surface>`
- **environment:** `<staging | prod | sandbox>`
- **box:** `<black-box | gray-box (+ source location)>`

## Surfaces in scope
- [ ] chat UI
- [ ] document / RAG ingest
- [ ] tools / connectors (list): ___
- [ ] shared / cross-user surfaces: ___

## Active OWASP subset (harness ships all 10; select per engagement)
- [ ] LLM01 prompt injection  [ ] LLM02 sensitive-info  [ ] LLM05 output-handling
- [ ] LLM06 excessive-agency  [ ] LLM07 system-prompt-leak  [ ] other: ___

## Benign safe-objective set (allowlisted win-conditions)
- [ ] system-prompt / instruction disclosure (distinctive token)
- [ ] refusal-flip on a HARMLESS restricted target
- [ ] indirect-injection canary propagation
- [ ] excessive-agency / unsafe render on owned tooling
- [ ] other (must define a benign signal): ___

## Adversarial-input transforms (E-track capabilities)
- **scope_allows_adversarial_input_transforms:** `no`  ← default. If `yes`, the orchestrator may use the
  external encoding/obfuscation/stego/covert-channel capabilities in `capabilities/registry.yaml`
  (sensor-only, benign-canary objectives; the oracle stays authoritative). Each capability is also
  `default: disabled` per card; this flag is the engagement-level enable. GLOSSOPETRAE channels
  additionally require operator review.

## Payload generation (E-track `payload_generator` class)
- **scope_allows_payload_generation:** `no`  ← default. If `yes`, the harness may use `payload_generator`
  capabilities (`capabilities/classes.yaml`) to *propose* candidate artifacts for an approved benign
  objective — **proposal only**: they never execute on a live target, never judge success, never emit a
  verdict; the broker/oracle stay authoritative. Each proposal must carry a declared payload class,
  containment plan, cleanup plan, and a non-authority attestation. Any Zone-2 artifact or live execution
  still requires the impact-demo authorization above + a runtime human-confirm.

## Escalation ceiling
- self → stored/persistent → cross-user: ceiling = `<rung>`

## Impact-demo authorization (Zone-2)
- **impact_demo_authorized:** `no`  ← default. If `yes`, fill every field below; otherwise Zone-2 fails closed.
- **zone2_authorized_categories:** `none`
- **zone2_escalation_ceiling:** `none`
- **zone2_containment:** `none`

Categories are comma-separated exact identifiers (currently `zone2_artifact_creation`); the ceiling
must be exactly `artifact_creation`; containment must be specific and non-placeholder. Duplicate or
unbackticked authorization fields fail closed. Even when all fields authorize the exact category, a live human-confirm displays the digest-bound
action, scope, environment, expiry, and cleanup binding before any artifact is created.

## Impact-maximization mandate (standard — the operator's standing answer is `yes`)
- **standing_impact_maximization_mandate:** `yes`  ← this operator's standing answer, recorded
  2026-08-10. Requires `impact_demo_authorized: yes`. **The scope is still inert until signed** —
  the signature is the gate, not this field. A different operator must set it back to `no`.

The operator dictated this mandate by hand on six engagements (cosmos, google-oss-vrp, klever, tron,
zeom, mercadobitcoin) before it was templated, and confirmed it as standing on 2026-08-10: *"i always
give permission for maximum impact PoC, and escalation of findings to whatever necessary."* Do not
ask again for what this paragraph already grants.

When the field is `yes`, the following applies for this engagement:

- Build any PoC the surface allows and **escalate each confirmed bug to its maximal demonstrated
  impact inside the authorized environment.** Use a loopback or multi-node simulation to show blast
  radius. Demonstrate fund-integrity classes on synthetic assets only. Demonstrate key-exposure or
  RCE classes against locally generated keys only.
- **Never under-demonstrate a bug.** Demonstrated-severity fidelity is the goal. Push *inside* the
  authorized surface. Never expand the surface.
- **Compose freely.** Chaining confirmed primitives into a composed proof is escalation, not a new
  act. It needs no fresh confirmation.

### What this grant does NOT cover — the trip-wires

The mandate is broad on purpose, so the boundary must be crisp. **A grant covers escalation within
the authorized surface. It does not cover an act that trips any wire below.** Each one needs a fresh
human confirmation at the moment of the act, and each is a property of the act, not of its severity:

1. **Irreversible by the actor.** The identity performing the act cannot undo it with the access it
   used. If cleanup needs a console, an admin, or another account, the wire is tripped.
2. **Reaches a third party.** Anything outside the operator's own accounts and the named target.
3. **Outlives the engagement.** The artifact survives the cleanup ledger, or its removal depends on
   access the run does not hold.
4. **Real funds, real keys, real users, or production.**
5. **Submission, disclosure, or any outbound contact with the vendor.**

**Why these five and not a list of acts.** On 2026-08-10 an engagement received a blanket grant that
named six acts. Four more acts followed it, and the two that left the least removable artifacts —
poisoned files written into a second account's namespace, deletable only from the cloud console —
were the least authorized. A grant reads as covering what was on the table when it was given. Naming
the *properties* that require a fresh confirm scales; naming the acts does not.

**Ask once, at the wire.** If an act trips a wire, say which wire, state the cleanup path before
acting, and get the confirmation. If it trips no wire, proceed to maximum impact without asking.

**Do not restate general methodology in this file.** The binding operating doctrine lives in the
engine and must be read from there, so that a later edit to the engine does not leave a stale copy in
an engagement file:

- `engine/persistence.md` — a held vector is a wrong turn, not a dry verdict.
- `engine/whitebox-analysis.md` §3 — keep-biased multi-round grading; never one-pass kill.
- `engine/escalation.md` §1 — marginal-contribution severity.
- `engine/regrade.md` §4a — the unbounded-negative discipline.
- `engine/pocinator.md` — verification of the verification; do not reward-hack.

## Accounts / fixtures
- accounts (owned, same-org if cross-user): ___
- concurrency: `1`  (raising past 1 requires explicit authorization here)

## Independent reviewer identity
- Reviewer allowed signers file: `<engagement-relative or operator-controlled path>`
- Reviewer allowed signers SHA256: `<sha256:...>`
- Reviewer signatures use namespace: `llm-redteam-harness-review-v1`

## Authority lanes
- Notebook work may continue inside the signed scope while an exact dependent action is `pending_authority`.
- Approval is digest-, lane-, environment-, executor/session-, and expiry-bound; it is never retrospective.
- Real-world / Zone-2 creation still requires a fresh live confirmation immediately before bytes/effects.

## Authorization
- Operator allowed signers file: `<operator-controlled path; private key stays outside agent access>`
- Operator allowed signers SHA256: `<sha256:...>`
- Operator signatures use namespace: `llm-redteam-harness-operator-v1`
- Operator: [name]
- Date: [date]
- Signed: [ ]
- Record kernel: `decision-0006-v1`
