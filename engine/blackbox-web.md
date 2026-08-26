# engine/blackbox-web.md — black-box web / API systems (no source)

The specialization of the harness for a **running system you cannot see inside**: domains, endpoints,
APIs, no source. This is the harness's *native* mode — it was built for authorized LLM-application
red-team, which is black-box. `engine/whitebox-analysis.md` is the *other* specialization (source
available, the Decision-0005 stage numbers). Both share the same skeleton — recon → activation signals
→ loop → oracle → adjudicate (`engine/routing.md`, `engine/loop.md`) — and the same doctrine. Black-box
does not change the doctrine; it changes what each stage operates on.

First engagement profile: **Shopify** (multi-tenant, API-first, app ecosystem) — grounding example at
the bottom. Start vertical (one target, quality locked), expand horizontally with the same bar.

## What black-box changes — and what it does NOT
- **Unchanged (all of `AGENTS.md §1`, `loop.md`, `gates.md`):** rules/scanners NARROW only, never kill
  or confirm; keep-biased multi-round grading; verification-of-verification before `confirmed`;
  persistence licensed; roles (`engine/roster.md`); the gates; rigor over findings.
- **Changed:** the corpus is not given — you **manufacture the attack-surface graph** by recon. The
  "sink" is not a code location you can name; it is a **behavior inferred from response deltas**.
  Reachability is **empirical** (an auth-context differential you observe), not a call graph you read.
- **Scanners are the black-box "rules," and they are worse than source-rules** — false-positive
  (a 500 is not SQLi) *and* false-negative (they cannot see IDOR, function-level authz, or multi-step
  business logic, which are the high-bounty classes). So a scanner's "confirmed" is a *lead*; a
  scanner's "clean" never retires a surface an LLM would reason about.

## Stage list (black-box web) — mapped from the white-box funnel
- **Recon (−1) — surface-graph construction.** The web analog of "the source tree exists." Build it.
- **0 — surface narrowing.** Which endpoints/params/flows are security-relevant *by shape*.
- **1 — primitive probe.** Cheap differential probes; bucket responses (reflected? id-guessable?
  error-leak? timing? role-gated?).
- **2 — triples.** `(attacker INPUT → observable EFFECT / oracle-signal → AUTH-CONTEXT)`. The "path" is
  the observed causal link, not a code path.
- **3 — reachability.** Auth-context differential: can role/tenant/user X trigger it, and does the
  effect **cross a privilege / tenant / data boundary**.
- **3.5 / 5 — chain.** Observed output→precondition edges (open-redirect→OAuth theft; IDOR→enum→ATO;
  SSRF→metadata→creds). Same rule as white-box: a chain edge is *verified*, never "these combine."
- **4 — confirmation.** The differential oracle + a negative control, on the **real target**.
- **4.25 — verify-of-verify.** The reward-hack protocol below. A separate pass.
- **5.25 — novelty.** Dedup vs the program's disclosed dupes + CVEs for the fingerprinted stack.
- **5.5 — dossier.** The repro package (requests, roles, controls, blast radius).
- **/goal, Post** — unchanged (`engine/regrade.md`, `engine/pocinator.md`).

## Recon → surface-graph (corpus construction for web)
Emit activation signals from what recon *observes* (`engine/routing.md`), the same as any engagement.
Build the graph from: subdomain enum + service/tech fingerprint; crawl; **JS-bundle analysis**
(hidden endpoints, API routes, keys leaked in JS); API-spec / **GraphQL introspection**; SPA/mobile
traffic capture; wayback/historical; parameter mining. Output: `hosts → endpoints → params/inputs →
auth-contexts/roles → observable data flows`. Bound it up front so "dry" means *enumerated-and-
adjudicated*, not "I stopped."

## The differential oracle (black-box confirmation)
**The oracle is a difference, not a value.** Two axes, and a confirm needs the relevant one plus its
controls:
- **baseline vs probe (same context):** the probe changes an observable the baseline did not.
- **cross-context:** principal A's request reads or affects principal B's state.

Mechanically this rides the existing two layers: **`signal-oracle`** (did the *predeclared, distinctive*
planted canary/marker appear — mechanical, no judgment) → **`adjudication-oracle`** (does that mean a
boundary failed — judgment). Every confirm carries:
- a **negative control** (selector absent / = self / lower-role-via-intended-path must DECLINE), and
- where a validating sibling exists, a **differential positive control** (the sibling 403s the same call).

**Canary discipline:** the signal is a benign marker YOU planted in a SECOND owned context — never real
third-party data. A bare 200/302/204 is `needs_review` until the *foreign* canary is what came back.

## Reward-hack / verify-of-verify protocol (the whole point)
The black-box fakes are nameable. Before any `confirmed`, a separate pass rules out EACH — an unruled
one keeps the finding at `needs_review`:
- **OWN-STATE** — you read a canary you planted under your own control / same account. → reproduce
  cross-context with a marker only the OTHER principal set.
- **CACHE / CDN** — an edge artifact, not the origin. → use a just-created resource the attacker never
  touched; require dynamic per-request fields in the response.
- **WAF / DECOY** — a 500/403 that is a WAF block, not the app. → separate the WAF signature from real
  app behavior before calling anything "injection."
- **PUBLIC / SHARED DATA** — the "victim" object is public. → an unauthenticated request to it must be
  DENIED, or it is not a leak.
- **CLIENT-SIDE** — a browser fetch mistaken for server SSRF. → prove the SERVER made the request (an
  out-of-band callback the client cannot reach).
- **OUT-OF-SCOPE** — the effect lands on a third-party host. → `scope.md`, not a finding.
- **DUPLICATE** — already disclosed. → novelty dedup.

Then **reproduce from a clean, second, independent context** (fresh account / session / IP). "Understand
the whole exploit" = trace request → effect → impact end to end; **a status code is not a finding.**
This is the exact analog of white-box "the forged object must enter via the real pipeline, not
DB-injected": here, the effect must be produced by the real server against a real *other* context, not
by your own state, a cache, the client, or a WAF.

## Sharpened gates (the target is LIVE PRODUCTION)
- **Scope is safety-critical, not tidy.** Only in-scope hosts. A *discovered* subdomain is NOT in scope
  until `scope.md` says so; recon that touches an out-of-scope host is a violation, not a lead.
- **Safe-signal:** benign probes + planted canaries only. No real user data read/stored/exfiltrated; no
  destructive, persistent, or business-impacting mutation.
- **Impact-escalation confirm fires at the CROSS-USER / PERSISTENT / DESTRUCTIVE line** — cross-tenant
  read, stored XSS that fires on real users, mass-assignment on real data, ATO of a real account. STOP,
  get an explicit operator confirm, contain (owned/synthetic canaries only), log in `cleanup.md` with a
  revert. Never autonomous, even if `scope.md` authorizes the category.
- **Review gate up the ladder** (self → same-tenant-other-user → cross-tenant), each rung gated on the
  prior succeeding.

## Shopify profile (first engagement — grounding)
Multi-tenant (a **shop is the tenant**); API-first (Admin REST + **GraphQL**, Storefront API, Partner
API); an **app ecosystem** (OAuth, app proxies, webhooks, granular scopes); **staff accounts** with
per-permission gating. The classes weighted for this vertical — high-bounty, scanner-blind,
LLM-decisive — and the cards they route to:
- **Cross-shop / cross-object access** → `bola.broken-object-level-authz` (cross-tenant = critical).
- **Staff-permission / function-level bypass** → `bfla.broken-function-level-authz` (new sibling card).
- **Business logic** (checkout, discount stacking, refund/payout, inventory, subscription invariants)
  → `business-logic-abuse`.
- **GraphQL field / mutation authz, aliasing/batching, nested-query DoS** → `graphql-abuse`.
- **App OAuth scope escalation, app-proxy HMAC, webhook signature, SSRF via fetchers** → patterns
  `oauth-client-binding`, `delegated-capability-attenuation`, `ssrf-server-side-fetch`,
  `bopla-property-authz`.
- **Deprioritized this vertical** (partly scanner-covered, operator call): injection/XSS classes.

Substrate: two or more **owned test shops** + **staff accounts of differing privilege** are the canary
plane (plant markers in shop/staff B, attack from A). The per-engagement `engagements/shopify-<date>/
scope.md` + `recon-signals.md` ground which shop objects, roles, and apps are the actual test surface,
and set the impact-demo ceiling. No LLM-class cards this vertical.

## Roadmap (deferred — captured so the operation is not lost)
- **`engine/blackbox-binary.md`** (deferred): native/binary black-box — RE-lift corpus construction
  (decompile/type-recover/symbolize), fuzz + symbex reachability, **crash-triage as the fake-filter**,
  **harness-divergence** verify-of-verify (the crash must fire through the real program's entry + control
  flow, not a scaffold that hands the sink the bug), and a **determinism/reliability + environment-fidelity
  ledger** (exact binary hash, libc, OS, ASLR/NX/PIE/CFG/canary state; reliability rate over N runs).
