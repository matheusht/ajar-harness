# scope.md — engagement authorization gate

**Status: SIGNED 2026-08-11** by the operator, in session.
**Impact-demo (Zone-2): AUTHORIZED at maximum, bounded by the five trip-wires in §7.**

## Engagement
- **id:** `obyte-ocore-2026-08`
- **target:** `https://github.com/byteball/ocore` — Obyte core library. Obyte is a DAG-based
  distributed ledger, not a blockchain. Node.js / JavaScript.
- **program:** Immunefi — Obyte Foundation. Rules in `program-policy.md`. **Primacy of Rules.**
- **environment:** local only. No mainnet, no public testnet (see §5).
- **box:** white-box source audit + local-fork dynamic proof.
- **asset class:** **Blockchain/DLT only.**

## Surfaces in scope

| # | Surface | In scope |
|---|---|---|
| SF-1 | DAG validation and unit/joint acceptance (`validation.js`, `joint_storage.js`) | yes |
| SF-2 | Consensus: main-chain selection, stability, witnessing (`main_chain.js`, `witness_proof.js`) | yes |
| SF-3 | Signature and authentifier verification, address derivation (`signature.js`, `definition.js`) | yes |
| SF-4 | Definition language / smart-address predicate evaluation (`definition.js`) | yes |
| SF-5 | Network / peer protocol, gossip, request handling (`network.js`) | yes |
| SF-6 | Storage, catchup, hash-tree proofs (`storage.js`, `catchup.js`) | yes |
| SF-7 | Payment/output handling, divisible + indivisible assets (`divisible_asset.js`, `indivisible_asset.js`) | yes |
| SF-8 | Private payments and spend-proof handling (`private_payment.js`) | yes |
| SF-9 | Autonomous Agent execution engine as it sits **inside ocore** (`aa_validation.js`, `aa_composer.js`) | yes — as DLT surface |
| SF-10 | Formula/oscript evaluation reachable from AA execution | yes — as DLT surface |

**OUT for this engagement — deferred, not excluded by the program.** The nine Autonomous Agent
repositories (`coop-aa`, `counterstake-bridge`, `obyte-cascading-donations`, `prediction-markets-aa`,
`perpetual-aa`, `oswap-token-aa`, `city-aa`, `friend-aa`) are a **separate scope**. The operator's
instruction is blockchain-only first. If that scope opens later, prioritise by most-recently-updated
repository. Do not audit them in this engagement. A finding in `ocore`'s AA *engine* is in scope; a
finding in an individual AA's *own* logic is not.

## Reward ladder — the routing driver

| Tier | Amount | Condition |
|---|---|---|
| **Critical, full** | **up to $50,000** | ONLY: unrecoverable **total network shutdown of the entire Obyte network**, OR **unpermitted execution of transactions from other users' accounts without their private keys**. 10% of funds directly affected, capped at $50k, floor $2,500. |
| Critical, capped | **$2,500 flat** | every other Critical |
| High | **$1,700 flat** | temporary freezing of funds ≥ 1 year |
| Medium | **$1,000 flat** | contract unable to operate for lack of token funds; temporary freezing of funds |

**Read the ladder before choosing a lane.** The reward is nearly flat except for two named
mechanisms. A Critical that is not total-shutdown or key-free-spend pays the same as another
Critical, so effort belongs on those two conditions and on High/Medium coverage — not on
manufacturing a third Critical class.

## Impacts in scope
- **Critical** — direct theft of user funds, at-rest or in-motion, other than unclaimed yield.
- **Critical** — permanent freezing of funds.
- **Critical** — protocol insolvency.
- **High** — temporary freezing of funds for at least 1 year.
- **Medium** — unable to operate due to lack of token funds; temporary freezing of funds.

## Out of scope — kill before deep work
- **Minimum impact USD 1,000** for anything involving funds lost or frozen. Below that is out.
- Direct financial damage **≤ 200% of the attacker's own expense**.
- **Temporary network disruption that a fix resolves WITHOUT network coordination** (node crashes,
  DoS). If resolving it **requires network coordination**, it IS in scope, graded as temporary
  freezing of network transactions. This distinction decides many DoS candidates — settle it early.
- 51% attacks and basic economic/governance attacks. Sybil. Liquidity. Centralization risk.
- Third-party oracle data (oracle manipulation and flash-loan attacks are NOT excluded by this).
- Anything needing leaked keys, credentials, or privileged addresses.
- Secrets in GitHub without proof of production use.
- Best-practice recommendations, feature requests, test and configuration files.
- Phishing or social engineering.

## Feasibility rules the program applies
Chain rollbacks, pre-impact bug monitoring, attack investment amount, attacks carrying financial risk
to the attacker, and the griefing-downgrade rule. Read `program-policy.md` before arguing severity.

## 5. Hard wall — the environment
**All testing runs against a LOCAL fork or local instance.** The program prohibits any testing on
mainnet or public testnet deployed code. It also prohibits testing with pricing oracles, third-party
contracts, third-party systems, DoS against project assets, and high-traffic automated testing.

No contact with any live Obyte node, hub, explorer, or public testnet. Ever. Local only.

## 6. Escalation ceiling
- self → stored/persistent → cross-user: ceiling = **cross-node, local fork only**.

## 7. Impact-demo authorization (Zone-2)
- **impact_demo_authorized:** `yes`
- **zone2_authorized_categories:** `zone2_artifact_creation`
- **zone2_escalation_ceiling:** `artifact_creation`
- **zone2_containment:** `local multi-node Obyte network on loopback, synthetic genesis, locally
  generated keys and assets, torn down per cleanup.md`
- **standing_impact_maximization_mandate:** `yes`

**Escalate to maximum demonstrated impact inside the local network without asking.** Compose
confirmed primitives freely — chaining is escalation, not a new act.

**Stop for a fresh human confirm only when an act trips a wire** (properties of the act, not of its
severity):

1. **irreversible by the actor** — the identity performing it cannot undo it with the access it used
2. **reaches a third party** — outside the local environment and the named target
3. **outlives the engagement** — survives the cleanup ledger, or removal needs access you do not hold
4. **real funds, real keys, real users, or production** — including any live Obyte node or testnet
5. **submission, disclosure, or outbound contact with the Obyte Foundation or Immunefi**

Name the wire, state the cleanup path, then ask. A grant covers what was on the table when it was
given.

## 8. Accounts and assets
- No program accounts. No KYC required by the program.
- All keys, addresses, and assets are locally generated for this engagement. None are real.

## 9. Proof requirement
**The program requires a PoC for every severity, always.** A source-only finding is not submittable.
Every candidate needs a runnable local proof before it can be considered complete.

## 10. Disclosure
**Responsible publication Category 3 — approval required.** No publication of anything, patched or
not, without Obyte Foundation approval. The operator handles all submission. **AI is barred from
filing.**

## 11. Redaction
No credentials, tokens, or private keys in any file in this engagement, even locally generated ones
that look real. Redact always.

## Binding doctrine — read from the engine, do not restate here
- `CLAUDE.md` — gates, roles, records.
- `engine/finding-lifecycle.md` — findings start in `unproven/`; promotion runs six gates.
- `engine/persistence.md` — a held vector is a wrong turn, not a dry verdict.
- `engine/whitebox-analysis.md` §3 — keep-biased multi-round grading; never one-pass kill.
- `engine/escalation.md` §1 — marginal-contribution severity.
- `engine/multi-round-orchestration.md` — family registry, blind round 0, adversarial throughout.
- `engine/chainability.md` — the six angles.

## Signature
- **signed:** [x] — authorized in session by the operator, 2026-08-11: *"this is the target/scope,
  I sign off. For blockchain that's the scope."*
- **operator:** matheusht
- **date:** 2026-08-11
