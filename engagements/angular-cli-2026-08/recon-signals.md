# recon-signals.md — angular-cli-2026-08

Recon output. Each observation names the cards it lights up and at what strength
(`strong` / `weak` / `negative`), per `engine/routing.md`. A `negative` signal is a control that
looks correctly enforced — it is recorded as likely-held and as a **positive-control candidate**,
never as a finding.

**Empty until Round 0 runs.** The tables below are the shape to fill, plus the priors carried in
from scoping. Do not treat a prior as an observation.

---

## 1. Activation table

| # | Observation (file:line) | Cards lit | Strength | Note |
|---|---|---|---|---|
| | | | | |

The orchestrator may use, ignore, or override any activated card, but records **one line on why**
for a `strong` signal on a high-impact path.

---

## 2. Baseline controls — what the code refuses with no attack

Capture these before attacking anything. Without them a later "it rejected" means nothing.

| Control | Where enforced (file:line) | Observed refusal | Positive control? |
|---|---|---|---|
| | | | |

---

## 3. History sweep — shapes only, never diffs

Recorded **once**, at the start. It seeds routing and does not steer the loop.

**A fixed bug marks a FAMILY, not a target.** Where one instance was wrong, siblings live. Any
candidate that maps to a swept shape is checked against the actual fix before promotion, and
**a fix is never reported as a find**.

| Shape | Where the family lives | Sibling sites to check |
|---|---|---|
| | | |

---

## 4. Proof strategies — the two Supply-Chain lanes

The SCC band tops out at **$31,337**, roughly 4× the best Product-Vulnerability outcome. Each lane
gets a **proof strategy, not a feasibility verdict**. "No path found" is not an answer — it closes
the highest-value lane early. A lane with a strategy and no path stays **OPEN**.

### Lane A — the release and publish path

*What would count as proof to a Google triager?* — write it before hunting.
*What sub-conditions does "attacker code reaches a published artifact" decompose into?*
*What must the lab show?*

- [ ] sub-conditions enumerated
- [ ] what a reviewer would accept as proof, stated
- [ ] lab requirement stated
- **status:** OPEN

### Lane B — CI and workflow compromise

Seven workflows. The questions that decide this lane: does any workflow run untrusted PR content
with secrets in scope; can a fork poison a cache the trusted path consumes; is there a
`pull_request_target` with a checkout of the PR head.

- [ ] sub-conditions enumerated
- [ ] what a reviewer would accept as proof, stated
- [ ] lab requirement stated
- **status:** OPEN

---

## 5. Priors carried from scoping — NOT observations

These are reasons to look, not evidence of anything. Delete or convert each one as Round 0 settles it.

- `ng add` / `ng update` fetch and execute third-party code **by design**. The design intent is the
  baseline; a finding must show a boundary the design does not intend — wrong package resolved,
  integrity check skipped, a downgrade silently accepted.
- `@angular/ssr` is the only surface that faces a network request at runtime.
- `@angular-devkit/core` holds the path and virtual-fs primitives — the natural home for traversal
  and normalization defects.
- Builder resolution in `architect` reads workspace files; whether a workspace file can redirect a
  builder to arbitrary code is a question, not a claim.
- `.ng-dev/` and `dev-infra.yml` bind this repo to `angular/dev-infra`. **Root causes that resolve
  into dev-infra are attributed there** (`scope.md` §4) and recorded in `cascades.md`.

---

## 6. Negative signals — controls that look correctly enforced

Recorded as likely-held and as positive-control candidates. Not findings.

| Control | Why it looks held | Where it would be a positive control |
|---|---|---|
| | | |
