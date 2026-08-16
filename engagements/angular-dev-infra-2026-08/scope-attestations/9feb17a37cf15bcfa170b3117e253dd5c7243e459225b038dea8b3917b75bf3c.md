# scope.md — engagement authorization gate

**OPERATOR-APPROVED — CANONICAL KERNEL ATTESTATION PENDING.** Matheus instructed the orchestrator on
2026-08-12 to scaffold this engagement and run it at maximum impact for at least six hours, with the
stopping contract recorded in the goal prompt. `Signed: [x]` records that in-session approval. The
loop stays inactive until the operator signs the canonical initialization challenge over these exact
bytes.

## Engagement
- **id:** `angular-dev-infra-2026-08`
- **target:** `https://github.com/angular/dev-infra` — Angular's shared development, CI, and release
  infrastructure. Publishes `@angular/ng-dev`, `rules_angular`, `rules_browsers`, `rules_sass`.
  Supplies 21 composite Actions and one reusable release workflow to three other OT0 repositories.
- **tier:** **OT0** (primary-verified; see `program-policy.md` §1)
- **environment:** local, disposable, operator-owned. **No live Angular or Google system is a target.**
- **box:** white-box — full public source.
- **program:** Google OSS VRP, category **Supply-Chain Compromise**, OT0 ceiling **$31,337**.

## Pinned identity
- Repository HEAD at scoping: `04230133d395dfb032d782b8e63b4fcbbd406aa5` (2026-08-07T14:06:09Z)
- Default branch: `main`
- The run re-pins at Round 0 and records the pin in `progress.md`. Every attempt, finding and PoC
  cites the exact pinned commit. Stale-version-only findings are rejected by the program.

## Surfaces in scope

- [x] `.github/workflows/` — 14 workflows, including the two `pull_request_target` workflows and the
  `workflow_call` reusable release workflow
- [x] `.github/local-actions/` — 5 composite actions
- [x] `github-actions/` — 16 composite actions, incl. `release/publish`, `post-approval-changes`,
  `branch-manager`, `labeling/issue`, `labeling/pull-request`, `bazel/{setup,configure-remote}`,
  `npm/checkout-and-setup-node`, `previews/*`, `org-file-sync`, `unified-status-check`
- [x] `ng-dev/` — 351 files: `release/` (publish, versioning, stamping, npm-dist-tag,
  snapshot-publish, recover-ci-publish, precheck, notes), `auth/`, `utils/git/`, `caretaker/`
- [x] `bazel/` — 404 files of shared Bazel rules shipped as `rules_angular`, `rules_browsers`,
  `rules_sass`
- [x] `apps/`, `lint-rules/`, `tools/`
- [x] `.ng-dev/release.mjs`, `renovate.json`, `renovate-presets/`, `.github/ng-renovate/`
- [x] `pnpm-lock.yaml`, `pnpm-workspace.yaml`, and the committed `*_token.data` files
- [x] The **interface** dev-infra exposes to consuming repositories: action inputs, outputs, and the
  reusable workflow contract. Reasoning about a consumer is in scope; **hunting inside a consumer
  repository is not** (see attribution below).

## Explicitly out of scope

- [ ] **Any live system.** The real `angular/*` repositories, their Actions runners, the Angular
  Robot and Lock Bot GitHub Apps, the real npm registry, the real Renovate runner, BrowserStack,
  SauceLabs, Firebase, and Google RBE. **No probe, no test PR, no test issue, no triggered workflow.**
- [ ] Hunting for flaws **inside** `angular/angular`, `angular/angular-cli`, or `angular/components`.
  A dev-infra flaw whose impact lands in a consumer is in scope; a consumer's own wiring bug is that
  repository's finding and belongs to a different engagement.
- [ ] Any adjacent host, service, or repository discovered mid-run. **Naming the allowed target is
  not a fence.** Evidence gathered against anything not named above is quarantined and unused, **even
  when it is the run's best result.**
- [ ] Stale-version-only issues; previously disclosed items; already-fixed hardening (positive
  controls only — check for an incomplete fix, never re-hunt).
- [ ] Third-party dependency flaws without an upstream report first, and without a
  dev-infra-specific trigger.
- [ ] Memory corruption. There is none here; do not manufacture a claim that would enter the
  OSS-Fuzz gate this engagement currently sits outside of.

## Active vulnerability and technique families

Workflow and pipeline injection; privileged-trigger abuse; secret and token exfiltration from CI;
indirect prompt injection into an LLM-driven bot holding privileged credentials; improper handling of
model output that drives a privileged API call; excessive agency in an automated bot; artifact and
cache poisoning; release and publish-path integrity failure; review and approval-gate bypass;
dependency and lockfile integrity non-enforcement; unpinned or mutable reference resolution; path
traversal and archive handling in artifact packing; command construction in release tooling;
confused-deputy and delegated-capability over-grant.

**Capability gate (`CLAUDE.md` §1 gate 2, non-waivable).** No card fires until its `SKILL.md` exists
and declares a benign `safe_signal`. Cards that already exist and apply: `workflow-step-injection`,
`indirect-prompt-injection`, `llm05-improper-output-handling`, `llm06-excessive-agency`,
`registry-lockfile-integrity-nonenforcement`, `path-traversal-lfi`, `arbitrary-file-upload`,
`injection`, `os-command-injection`, `ssrf-server-side-fetch`, `information-disclosure`, plus the
`verification-root-not-anchored`, `transitive-sanitizer-reliance`, `delegated-capability-attenuation`
and `unsafe-default-authz-helper` patterns. Any lead outside these needs a card authored first.

## Benign safe-objective set (allowlisted win-conditions)

Every signal is produced locally, against a local replica or a private throwaway fork. No signal is
ever produced by touching the real Angular organization.

- [x] **`secret_reaches_attacker_controlled_sink`** — a locally planted **synthetic** canary secret,
  placed where the real workflow places a real secret, is observably readable by, or emitted to, a
  sink an attacker controls. The canary is a distinctive random string with no real value.
- [x] **`unreviewed_code_lands`** — a locally replicated approval or merge gate accepts a change it
  was designed to reject. The negative control is the same gate correctly rejecting the benign case.
- [x] **`artifact_substituted`** — a build, pack, or publish path accepts an artifact that does not
  match the value it was supposed to be bound to, with no hard failure.
- [x] **`injected_step_executes`** — attacker-influenced text reaches a shell, an expression
  interpolation, or a step definition and executes a benign marker command.
- [x] **`bot_performs_unintended_privileged_action`** — a locally driven bot, fed attacker-shaped
  input, issues a privileged call outside its intended vocabulary. Demonstrated against a local mock
  API that records calls, never against the real GitHub API.
- [x] **`integrity_check_silent_accept`** — a modified input passes a hash, signature, or pin check
  that should hard-fail.

A crash, a hang, an agent's confidence, a narrative, or a wrapper tool's summary is **never**
confirmation. Confirm from raw output and a second independent tool — the local `rtk` shell hook has
been observed reporting wrong test outcomes, wrong diff equality and wrong grep counts.

## Adversarial-input transforms
- **scope_allows_adversarial_input_transforms:** `yes`
- Authorized only inside the local disposable environment, to construct or analyze candidate inputs
  (issue and PR bodies, commit messages, branch names, label payloads, model prompts, archive
  entries). They stay sensor and converter output. They never become an oracle or an authorization
  source.

## Payload generation
- **scope_allows_payload_generation:** `yes`
- Proposal-only generation is authorized for candidate workflow files, action inputs, prompt strings,
  archive fixtures, and local harnesses. A proposal cannot execute, grade, or authorize itself. Live
  creation and execution stay under the Zone-2 gate and the runtime confirm.

## Escalation ceiling

- Ceiling: **the maximum honestly demonstrable supply-chain impact inside a local replica or a
  private throwaway fork the operator controls** — up to and including a synthetic canary secret
  reaching an attacker-controlled local sink, an unreviewed change landing in a local replica of the
  gate, and a substituted artifact passing a local replica of the publish path.
- Continue from a confirmed rung to the next while budget remains and the next action stays inside
  containment. Never substitute narrative inference for an unobserved rung.
- **Not authorized at any severity:** any action against the real Angular organization, its runners,
  its bots, its Apps, or the real npm registry; use of any real credential; publication of any
  package; persistence; or any effect on a person or a third-party system.

## Impact-demo authorization (Zone-2)
- **impact_demo_authorized:** `yes`
- **zone2_authorized_categories:** `zone2_artifact_creation`
- **zone2_escalation_ceiling:** `artifact_creation`
- **zone2_containment:** `only the operator-owned disposable local machine and a private throwaway fork the operator controls; workflow proofs run locally through act or a replicated harness; a private-fork Actions run requires a fresh operator confirm at the wire; forged local tokens and synthetic canary secrets only; never the real angular org repositories runners bots apps or the npm registry; never a real GitHub App key or publish credential; artifacts stay under the engagement evidence path with an open cleanup obligation`

## Workflow-proof method — decided, and where the line sits

Proving a workflow flaw needs a workflow to run. Three methods, with different authorization:

1. **Static reasoning + source reading** — autonomous, no gate. Always the first pass.
2. **Local replication** — `act`, a replicated harness, or a direct driver for the action's own
   JavaScript or TypeScript entry point, run on the operator's machine against a local mock API.
   **Autonomous under the standing Zone-2 grant.** This is the intended normal working method.
3. **A private throwaway fork the operator controls, running real GitHub Actions** — this **trips
   wire 2**. It requires one fresh operator confirm at the moment of the act, naming the fork, the
   workflow, the synthetic secrets, and the teardown path. It is never batched and never assumed.

**Method 2 is not automatically proof.** A local replica that "confirms" a flaw the real Actions
control flow would not execute is a reward-hack, and it is the single most expensive failure mode
available here. See the goal prompt, Part 8.

## Impact-maximization mandate
- **standing_impact_maximization_mandate:** `yes` — the operator's standing answer, reaffirmed in
  session on 2026-08-12.

Push every confirmed bug to its maximal demonstrated impact **inside the authorized surface**, and
compose confirmed primitives freely — chaining is escalation, not a new act, and needs no fresh
confirmation. **Never under-demonstrate.** The gap between a $3,133.70 SCC report and a $31,337 one
is demonstrated blast radius, not discovery. "Maximum" never expands the environment, the target set,
or the operational effect.

### The five wires — a fresh human confirm at each, regardless of severity

1. **Irreversible by the actor** — the identity performing the act cannot undo it with the access used.
2. **Reaches a third party** — outside the operator's own machines and the pinned source tree.
   **Any GitHub Actions run, even in the operator's own private fork, is here.**
3. **Outlives the engagement** — survives the cleanup ledger, or removal needs access the run lacks.
4. **Real funds, real keys, real users, or production.**
5. **Submission, disclosure, or any outbound contact with Google or the Angular team.**

Name the wire, state the cleanup path, then ask. A grant covers what was on the table when it was
given. If the act trips no wire, proceed to maximum impact without asking.

**Do not restate general methodology here.** Binding doctrine is read from the engine:
`engine/persistence.md`, `engine/whitebox-analysis.md` §3 and §4, `engine/escalation.md` §1,
`engine/regrade.md` §4a, `engine/pocinator.md`, `engine/multi-round-orchestration.md`.

## Accounts / fixtures
- accounts: **none against the real target.** A private throwaway GitHub fork under the operator's
  own account may be created for method 3, subject to the wire-2 confirm.
- fixtures: local Node and pnpm workspace, `act`, a local mock GitHub API that records calls, locally
  generated throwaway keys, and synthetic canary secrets. Never a real key or credential.
- **live target concurrency:** `0` — there is no live target.
- **source-analysis concurrency:** up to **128** agents across the engagement, per the operator's
  in-session budget. Source audit parallelises. Never exceed the runtime cap.
- external network: allowed to clone the pinned repository, the three consuming repositories for
  interface reading only, dependency source into `third_party/`, and language and Actions
  documentation. **Never** to probe, trigger, or interact with any live Angular or Google service.
- retention: minimized PoCs, raw tool output, local transcripts, build identity, redacted logs. Never
  store credentials, authorization headers, signed URLs, or private signing keys.

## Independent reviewer identity
- Reviewer identity: `angular-dev-infra-reviewer`
- Reviewer public-key fingerprint: `SHA256:sHU2fkOGl7d3lav22M/XmhDibvAAAKkZmNATsSfp/uE`
- Reviewer allowed signers file: `engagements/angular-dev-infra-2026-08/signers/reviewer.allowed_signers`
- Reviewer allowed signers SHA256: sha256:033a98535251c5022936619d0018118e887d775c9a2973c9ebf3b25cc39d4d32
- Reviewer signatures use namespace: `llm-redteam-harness-review-v1`
- The reviewer private half is operator-controlled and lives outside this repository. It never enters
  the engagement or any agent context.
- The reviewer must run in a genuinely fresh context, must not be a hunter that touched the candidate
  under review, and must never be told that a flaw is expected.

## Authority lanes
- Notebook work may continue inside this signed scope while an exact dependent action is
  `pending_authority`.
- Approval is digest-, lane-, environment-, executor/session-, and expiry-bound; one-use; never
  retrospective.
- Zone-2 creation always requires a fresh live confirmation immediately before bytes or effects.
- Finding filing, report acceptance, memory promotion, external publication, and closure remain
  separate operator-owned transitions. **This scope authorizes no external submission.**

## Cleanup and retention
- Open a cleanup obligation before creating each Zone-2 artifact.
- Delete any private throwaway fork, revoke any synthetic canary, and remove local caches and node
  modules at closure. Record what was removed.
- Preserve only the redacted evidence needed to reproduce a finding.
- Unresolved cleanup blocks pattern promotion and closure.

## Authorization
- Operator public-key fingerprint: `SHA256:RjRZNewHUOzH3Gg6IyrklJwuYID7IE8UWm+Ir/yWvHI`
- Operator allowed signers file: `engagements/angular-dev-infra-2026-08/signers/operator.allowed_signers`
- Operator allowed signers SHA256: sha256:ccd13b84d23e9f64b1cb96458b49cb0219ee6115453652e2fbc5e7bf0944b9cc
- Operator signatures use namespace: `llm-redteam-harness-operator-v1`
- Operator: matheusht
- Date: 2026-08-12
- Signed: [x]
- In-session authorization: the operator directed a six-hour-minimum exhaustion run at maximum
  impact, with the termination contract recorded in the goal prompt.
- Record kernel: `decision-0006-v1`

Canonical activation still requires the operator to review these exact bytes and sign the generated
initialization challenge with the private half of the `matheusht` key. The private key must never
enter the engagement or agent context.
