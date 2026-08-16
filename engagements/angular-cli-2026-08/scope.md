# scope.md — engagement authorization gate

**OPERATOR-APPROVED — CANONICAL KERNEL ATTESTATION PENDING.** Matheus instructed the orchestrator on
2026-08-14 to scaffold this engagement, signed off in session, and directed the **same
authorizations already granted on `angular-dev-infra-2026-08`**, designed for a long-running run at
maximum impact for **at least six hours**, with the stopping contract recorded in the goal prompt.
`Signed: [x]` in the Authorization section records that in-session approval. The loop stays inactive until the operator
signs the canonical initialization challenge over these exact bytes.

## Engagement

- **id:** `angular-cli-2026-08`
- **target:** `https://github.com/angular/angular-cli` — the Angular CLI monorepo. Publishes 15 npm
  packages including `@angular/cli`, `@angular/build`, `@angular/ssr`, `@schematics/angular` and
  `@angular-devkit/*`.
- **tier:** **OT0** (flagship). Primary-verified — see `program-policy.md` §1.
- **program:** Google OSS VRP. Categories: **Supply-Chain Compromise** (OT0 ceiling **$31,337**) and
  **Product Vulnerability** (OT0 **$500–$7,500**).
- **environment:** local, disposable, operator-owned. **No live Angular, Google or npm system is a
  target.** Recon is source reading against the public repository.
- **box:** white-box — full public source.

## Pinned identity

- HEAD at scoping: `d827ba9005b86b23d05ee7c62c0823367aa245c1` (2026-08-14T16:05:57Z, `main`)
- The run **re-pins at Round 0** and records the pin in `progress.md`. Every attempt, finding and PoC
  cites the exact pinned commit.
- **Stale-version-only findings are rejected by the program.** Confirm each candidate is still
  unfixed at the current released tag before any deep work.

## Surfaces in scope

| # | Surface | Notes |
|---|---|---|
| SF-1 | `packages/angular/cli` | the `ng` command surface, argv parsing, command resolution |
| SF-2 | `packages/angular/build` | `@angular/build` — the current build pipeline |
| SF-3 | `packages/angular/ssr` | server-side rendering; request-path handling |
| SF-4 | `packages/angular_devkit/core` | path/virtual-fs primitives, JSON schema, workspace parsing |
| SF-5 | `packages/angular_devkit/schematics` | the schematic engine, `Tree`, sinks, task execution |
| SF-6 | `packages/angular_devkit/architect` | builder resolution and invocation |
| SF-7 | `packages/angular_devkit/build_angular`, `build_webpack` | legacy build path |
| SF-8 | `packages/schematics/angular` | `@schematics/angular` — `ng new`, `ng generate`, `ng update` |
| SF-9 | `packages/ngtools/webpack` | the AOT webpack plugin |
| SF-10 | `.github/workflows/` | 7 workflows: `ci.yml`, `pr.yml`, `dev-infra.yml`, `codeql.yml`, `perf.yml`, `scorecard.yml`, `assistant-to-the-branch-manager.yml` |
| SF-11 | `.ng-dev/`, `MODULE.bazel`, `MODULE.bazel.lock`, `constants.bzl`, `BUILD.bazel` | release config and build graph |
| SF-12 | `goldens/`, `.monorepo.json` | package manifest and public-API goldens |

**Highest expected value first.** The SCC band is roughly 4× the top PV band, so the release,
publish and CI surfaces (SF-10, SF-11) outrank library logic on expected value. `ng update` and
`ng add` (SF-8) are the two commands that fetch and execute third-party code, so they carry the
supply-chain weight on the client side.

## THE ATTRIBUTION BOUNDARY — read before filing anything

`angular/angular-cli` **consumes** `angular/dev-infra` through `.ng-dev/` and `dev-infra.yml`. We
audited dev-infra last week and promoted two findings there (`F13`, `R8`).

**A defect in dev-infra's own code is dev-infra's finding, not this engagement's.** Filing it here
duplicates a report we already hold and burns credibility with the same triage team.

Three rules:
1. When a candidate's root cause resolves into a dev-infra action, workflow or `ng-dev` module,
   **stop and attribute it to `angular-dev-infra-2026-08`.** Record it in `cascades.md`; do not open
   a finding here.
2. A **consumer-side** defect is in scope: angular-cli calling a dev-infra interface unsafely, or
   granting it more privilege than it needs. The defect must be in *this* repo's wiring.
3. If attribution is genuinely ambiguous, that is an operator decision, not an orchestrator one.

## Out of scope — kill before deep work

- **Schematics execute code by design.** `ng add` and `ng update` run third-party package code
  on purpose; that is documented behaviour, not a vulnerability. Reporting it wastes a round. A
  finding must show a *boundary crossed that the design does not intend*.
- **Memory-corruption reports** pay only with an exact OSS-Fuzz reproduction via an existing fuzz
  target, or a merged upstream patch (post-March-2026 gate). This is a TypeScript repo, so the class
  is mostly inapplicable — do not pivot a logic candidate onto it.
- Anything already fixed at the current released tag.
- Third-party dependency defects whose root cause is upstream — those go upstream first, not to
  OSS VRP, unless the vulnerability is in *how this repo uses* the dependency.
- Denial of service against a developer's own local machine by their own configuration.
- Best-practice recommendations, missing hardening, feature requests.

## Benign safe-objective set (allowlisted win-conditions)

Win-conditions for this white-box engagement, all demonstrable inside the local lab (see the
Escalation ceiling and Impact-demo authorization sections):

- [x] synthetic canary secret reaching an attacker-controlled local sink through a local replica of a
      fetch-and-execute or publish path
- [x] unreviewed change landing in a local replica of a review gate (CI / PullApprove / merge queue)
- [x] substituted or downgraded package passing a local replica of the install / publish path
- [x] attacker-controlled code executing through a local replica of `ng add` / `ng update`
- [x] logic-defect PoC reaching an unauthorized file-system or network effect inside the local lab

## Escalation ceiling

- Ceiling: **the maximum honestly demonstrable supply-chain impact inside a local replica or a
  private throwaway fork the operator controls** — up to and including a synthetic canary secret
  reaching an attacker-controlled local sink, an unreviewed change landing in a local replica of a
  gate, a substituted package passing a local replica of the publish path, and attacker-controlled
  code executing through a local replica of `ng add` / `ng update`.
- Continue from a confirmed rung to the next while budget remains and the next action stays inside
  containment. **Never substitute narrative inference for an unobserved rung.**
- **Not authorized at any severity:** any action against the real Angular organization, its runners,
  its bots, its Apps, the real npm registry, or any Google system; use of any real credential;
  publication of any package; persistence; or any effect on a person or a third-party system.

## Impact-demo authorization (Zone-2)

- **impact_demo_authorized:** `yes`
- **zone2_authorized_categories:** `zone2_artifact_creation`
- **zone2_escalation_ceiling:** `artifact_creation`
- **zone2_containment:** `only the operator-owned disposable local machine and a private throwaway fork the operator controls; workflow proofs run locally through act or a replicated harness; a private-fork Actions run requires a fresh operator confirm at the wire; registry interaction goes to a local registry stub or a recording HTTP fixture; forged local tokens and synthetic canary secrets only; never the real angular org repositories runners bots apps or the npm registry; never a real GitHub App key or publish credential; artifacts stay under the engagement evidence path with an open cleanup obligation`

## Workflow- and publish-proof method — decided, and where the line sits

1. **Source reading against the pinned tree** — always authorized.
2. **A local replica**: workflows through `act` or a replicated harness; the publish path against a
   local registry stub or recording fixture; `ng add` / `ng update` against synthetic packages.
   **Autonomous under the standing Zone-2 grant. This is the intended normal working method.**
3. **A private throwaway fork the operator controls, running real GitHub Actions** — this **trips
   wire 2**. It requires one fresh operator confirm at the moment of the act, naming the fork, the
   workflow, and the cleanup path.

**Method 2 is not automatically proof.** A local replica that "confirms" a flaw the real runner would
reject proves nothing — the replica's fidelity to the real path is part of the claim, and G6 applies
to it. State what the replica reproduces faithfully and what it approximates.

## Impact-maximization mandate

- **standing_impact_maximization_mandate:** `yes` — the operator's standing answer, reaffirmed in
  session on 2026-08-14, granting the same authorizations as `angular-dev-infra-2026-08`.

Push every confirmed bug to its maximal demonstrated impact **inside the authorized surface**, and
compose confirmed primitives freely — chaining is escalation, not a new act, and needs no fresh
confirmation. **Never under-demonstrate.** The gap between a $3,133.70 SCC report and a $31,337 one
is demonstrated blast radius, not discovery. "Maximum" never expands the environment, the target
set, or the operational effect.

### The five wires — a fresh human confirm at each, regardless of severity

1. **Irreversible by the actor** — the identity performing the act cannot undo it with the access used.
2. **Reaches a third party** — outside the operator's own machines and the pinned source tree.
   **Any GitHub Actions run, even in the operator's own private fork, is here. So is any request to
   the real npm registry.**
3. **Outlives the engagement** — survives the cleanup ledger, or removal needs access the run lacks.
4. **Real funds, real keys, real users, or production.**
5. **Submission, disclosure, or any outbound contact** with Google, the Angular team, or any
   maintainer.

Name the wire, state the cleanup path, then ask. A grant covers what was on the table when it was
given. **If the act trips no wire, proceed to maximum impact without asking.**

## Proof requirement

Every finding ships a runnable PoC against the pinned commit, plus a negative control that fails for
the stated reason. `G6` applies: the impact-bearing state must be **reached** through the real path,
not written into place.

## Accounts / fixtures

- accounts: none (no program accounts)
- concurrency: `1` (raising past 1 requires explicit authorization here)
- No real npm tokens, no real GitHub tokens, no real Google credentials — ever, including in a local
  test. All fixtures are synthetic.

## Disclosure

The operator files. **AI is barred from filing, contacting maintainers, or opening any issue or PR.**

## Redaction

No credentials, tokens, or private keys in any file in this engagement, even locally generated ones
that look real.

## Authorization

- Operator public-key fingerprint: `SHA256:RjRZNewHUOzH3Gg6IyrklJwuYID7IE8UWm+Ir/yWvHI`
- Operator allowed signers file: `engagements/angular-cli-2026-08/signers/operator.allowed_signers`
- Operator allowed signers SHA256: sha256:ccd13b84d23e9f64b1cb96458b49cb0219ee6115453652e2fbc5e7bf0944b9cc
- Operator signatures use namespace: `llm-redteam-harness-operator-v1`
- Operator: matheusht
- Date: 2026-08-14
- Signed: [x]
- In-session authorization: the operator signed off on 2026-08-14 and directed **the same
  authorizations already granted on `angular-dev-infra-2026-08`**, designed for a long-running run —
  a six-hour-minimum exhaustion run at maximum impact, with the termination contract recorded in the
  goal prompt.
- Record kernel: `decision-0006-v1`

**The initialization challenge was NOT carried over from `angular-dev-infra-2026-08`.** A challenge
signature covers one engagement's exact bytes; reusing it here would assert an attestation the
operator never made over this scope. The allowed-signers files are copied because the key is the
same. Canonical activation requires the operator to review these exact bytes and sign a **freshly
generated** initialization challenge with the private half of the `matheusht` key. The private key
must never enter the engagement or agent context.

## Binding doctrine — read from the engine, do not restate here

- `CLAUDE.md` — gates, roles, records
- `engine/finding-lifecycle.md` — findings start in `unproven/`; promotion runs seven gates
- `engine/persistence.md` — a held vector is a wrong turn, not a dry verdict
- `engine/whitebox-analysis.md` §3 — keep-biased multi-round grading; never one-pass kill
- `engine/escalation.md` §1 — marginal-contribution severity
- `engine/multi-round-orchestration.md` — family registry, blind round 0, adversarial throughout
- `engine/chainability.md` — the six angles
