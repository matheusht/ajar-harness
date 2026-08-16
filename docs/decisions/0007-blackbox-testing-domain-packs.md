# Decision 0007 — Black-box testing domain packs (web first, binary deferred)

**Status:** accepted as product direction; implementation incremental (web pack v1 begun)\
**Date:** 2026-07-16\
**Effect:** extends Decision 0005 by applying its reasoning-directed, evidence-constrained posture to
targets with **no source**; adds the black-box **web/API** domain pack and records a roadmap for a
deferred **binary** pack. Supersedes nothing. Decision 0004 (autonomy + complexity) and 0005 (live
research + evidence state) remain canonical and govern this work.\
**Related:** `engine/blackbox-web.md`, `engine/routing.md`, `engine/loop.md`, `engine/gates.md`,
`skills/oracles/signal-oracle.md`, `skills/oracles/adjudication-oracle.md`,
`skills/vulns/broken-object-level-authz/`, `skills/vulns/broken-function-level-authz/`,
`skills/vulns/business-logic-abuse/`, `skills/vulns/graphql-abuse/`, `AGENTS.md`

## Context

The harness is **black-box at its core**: it was built for authorized LLM-application red-team, where
the target is a running system you cannot see inside. Decision 0005's white-box stage numbers
(sink-narrowing → triples → reachability, `engine/whitebox-analysis.md`) were a *specialization* for
source-available work (the Backstage/Spotify engagement). 0005 already states the intended shape: "LLM
application security is one domain pack among web, API, source audit, binary, supply-chain, blockchain,
consensus, and future domains."

This decision formalizes the **other** specialization — general black-box web/API systems with no
source — and sets the order in which it and its siblings are built. The doctrine does not change. What
changes per domain is only what each stage operates on:

- the corpus is not given; you **manufacture the attack-surface graph** by recon;
- the "sink" is not a code location but a **behavior inferred from response deltas**;
- reachability is **empirical** (an observed auth-context differential), not a call graph you read;
- the black-box "rules" are scanners, which are worse than source-rules — false-positive *and*
  blind to the high-bounty classes (access-control, function-level authz, business logic).

## Decision

### 1. Black-box is a first-class specialization, not a fork

Black-box and white-box share the same skeleton — recon → activation signals → loop → oracle →
adjudicate (`engine/routing.md`, `engine/loop.md`) — and the same hard shell. `engine/blackbox-web.md`
is the web profile; `engine/whitebox-analysis.md` is its source-available sibling. New domain packs are
profiles over the shared skeleton, never parallel harnesses.

### 2. Rollout is vertical-first, then horizontal — and the bar never moves

This is the load-bearing operating principle for the rollout:

> Go **deep on one target until the quality bar is demonstrably met**, then expand **wide at the same
> bar** — never trade the bar for breadth.

- **Vertical (now):** pick ONE target, lock the quality bar on it (differential oracle + matched
  negative controls + the verify-of-verify/reward-hack protocol + the sharpened live-production gates),
  and prove the pipeline end-to-end — including at least one reproduced-cross-context finding *and* at
  least one well-evidenced negative.
- **Horizontal (after):** only once the vertical has shown the bar holds, expand to more targets and
  more vuln classes, carrying the identical bar. Breadth is earned by demonstrated depth, not assumed.

**Why:** the product is rigor, not findings (`AGENTS.md §0`). A shallow-broad sweep manufactures the
9,999 fakes; it does not find the 1 real, and it burns program trust with closed-as-informational
reports. Consistency at the bar across many targets is the actual deliverable, so horizontal expansion
is gated on the vertical proving the bar is reproducible, not on time elapsed.

### 3. First vertical: Shopify

Multi-tenant (a shop is the tenant), API-first (Admin REST + GraphQL, Storefront API, Partner API), an
app ecosystem (OAuth, app proxies, webhooks, granular scopes), staff accounts with per-permission
gating. Class weighting for this vertical — high-bounty, scanner-blind, LLM-decisive:

- cross-shop / cross-object access → `bola.broken-object-level-authz`;
- staff-permission / function-level bypass → `bfla.broken-function-level-authz` (added by this decision);
- business logic (checkout, discount, refund/payout, inventory, subscription invariants) →
  `business-logic-abuse`;
- GraphQL field/mutation authz, aliasing/batching, nested-query DoS → `graphql-abuse`;
- app OAuth scope, app-proxy HMAC, webhook signature, SSRF via fetchers → the `oauth-*`,
  `delegated-capability-attenuation`, `ssrf-server-side-fetch`, `bopla-property-authz` patterns.

Injection/XSS classes are **deprioritized** this vertical (partly scanner-covered; operator call). **No
LLM-class cards** this vertical. The per-engagement `engagements/shopify-<date>/scope.md` +
`recon-signals.md` ground the actual test surface (which shop objects, roles, apps) and set the
impact-demo ceiling. Two or more owned test shops plus staff accounts of differing privilege are the
canary substrate.

### 4. What is mechanized vs kept flexible (Decision 0005's boundary, applied to no-source targets)

| Surface | Posture |
| --- | --- |
| Scope on a **live production** target (in-scope hosts only; a discovered subdomain is not in scope until `scope.md` says so), safe-signal (benign probes + planted canaries only), the **cross-user / persistent / destructive** impact-escalation confirm, canary-only substrate, differential oracle + matched negative controls before `confirmed`, cleanup ledger | Enforce mechanically |
| Recon / surface-graph construction, hypothesis generation, chaining, business-logic invariant reasoning, the verify-of-verify judgment | Keep reasoning-directed and flexible |
| Surface narrowing, stage transitions, candidate rejection, severity, coverage/dry, novelty interpretation | Model judgment with structured rationale, evidence references, independent challenge, and operator authority where consequential |

The reward-hack surface is domain-specific and enumerated in `engine/blackbox-web.md` (own-state,
cache/CDN, WAF/decoy, public-data, client-side, out-of-scope, duplicate). Each must be ruled out before
`confirmed`; an unruled one keeps the finding at `needs_review`.

### 5. Cards and skills: reuse, then fill gaps

Reuse the existing black-box-web vocabulary (`broken-object-level-authz`, `business-logic-abuse`,
`graphql-abuse`; patterns `client-supplied-selector-authz`, `ui-only-policy-enforcement`,
`legacy-route-differential`, `unsafe-default-authz-helper`, `oauth-client-binding`,
`ssrf-server-side-fetch`, `bopla-property-authz`). Cards stay domain-neutral; the engagement's
`scope.md` + `recon-signals.md` bind them to the target. Gaps are filled one at a time at the vertical's
quality bar — this decision adds `bfla.broken-function-level-authz` (the sibling the BOLA card explicitly
deferred). Do not batch shallow cards for coverage; add a card when a real surface needs it.

### 6. Roadmap

- **Now — web pack v1:** `engine/blackbox-web.md` + `bfla.broken-function-level-authz` written. Next:
  stand up `engagements/shopify-<date>/` from the template, fill + sign `scope.md`, run recon → the
  surface-graph, and drive the vertical to the bar in §2.
- **Near — earned by the vertical:** promote worked Shopify recon→activation examples into a
  `casebooks/<id>/recon-signals.yml` after the engagement (scrubbed); add tenant-isolation / OAuth-app
  cards only if the vertical surfaces a real gap they fill.
- **Deferred — `engine/blackbox-binary.md`:** native/binary black-box (RE-lift corpus construction,
  fuzz + symbex reachability, crash-triage as the fake-filter, **harness-divergence** verify-of-verify,
  and a **determinism/reliability + environment-fidelity ledger**). Captured so the operation is not
  lost; not built. Its stub lives at the bottom of `engine/blackbox-web.md`.

### 7. Success criterion (unchanged from 0005)

Not report volume. A vertical succeeds when it produces at least one finding **reproduced from a clean
second context with matched negative controls and the verify-of-verify pass complete**, and at least one
**well-evidenced negative** where controls and bounded coverage held. A proven cap or a documented
refutation is a success, not a failure.

## What remains deliberately flexible

- The exact order of vuln classes within the Shopify vertical (routing decides from recon signals).
- **When** the vertical is judged "bar met" and horizontal expansion is licensed — an operator call,
  gated on the bar being demonstrably reproducible (§2), never on time elapsed.
- Which second target opens the horizontal phase, and which domain pack (further web verticals vs the
  deferred binary pack) comes after.
