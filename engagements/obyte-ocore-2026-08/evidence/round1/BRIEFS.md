# Round 1 briefs — obyte-ocore-2026-08 (PoC + adversarial refutation)

Launched 2026-08-11. Directed allocation from round-0 adjudication (rounds.md Tier A/B). Builders
produce runnable maximum-impact PoCs in the local lab; refuters (fresh context) attack every
surviving candidate. **Every PoC gets an independent fresh-context run by a reviewer in round 2 —
builders must make their PoC fully runnable + documented (one-command) so an independent party can
execute it and read RAW output.**

## Lab harness

- `evidence/lab/lab.js` — in-process ocore boot (scratch SQLite; symlinked as `lab-obyte.js` in the
  ocore tree). Usage: `cd <ocore> && node lab-obyte.js <abs path to script>`; script signature:
  `module.exports = async function(db, storage, network, validation, objectHash, signature, composer, mutex, constants)`.
- Real-path discipline: **no mocks, no fake clients, no reimplementations** — compose/validate
  through the real library entry points (composer, validation.validate, network handlers). A PoC
  that reproduces a sink without the real path is a reward-hack (goal prompt Part 8).
- Upgrade MCIs are zeroed in the lab (all rules apply from genesis) unless a candidate SPECIFICALLY
  needs old-DAG gating — then the builder must set `constants.X` to a nonzero value and attach the
  unit below it (see each brief).

## PoC briefs

### P1 — crash: private-payment doublespend → uncaught throw → full-node process death (validation.js:1662)
- Claim: attacker (sender of a private payment, retaining the spend proof as bearer secret) authors
  unit A spending the victim's private output X with `spend_proofs:[{address: <victim_addr>,
  spend_proof: P}]` (P = hash of output fields + blinding, recomputable by the sender). When any
  node holding the victim's spend_proofs row validates A: `checkForDoublespends`
  (validation.js:1655-1662) → `arrAuthorAddresses.indexOf(conflict.address) === -1` → **unconditional
  throw** → `network.js:4367` uncaughtException handler → re-throw → process crash. Also hits light
  wallets (throw precedes `conf.bLight`).
- Lab: two keypairs (sender, recipient). Real path: composer composes private divisible payment to
  recipient (output X with blinding); node validates + saves chain (spend_proofs row stored);
  recipient spends X (row updated); attacker composes A re-spending X with address=victim;
  validate A through the real validation entry → expect process death.
- Negative control: same flow, public asset → clean rejection, no crash. Also: A with address=attacker
  (not victim) → accepted as forked doublespend (no crash) — document both.
- Deliverable: `evidence/lab/p1/` runnable script + README with the claim tuple; observed crash
  (raw stderr/exit code).

### P2 — crash-family reachability: sites 2289 and 1678
- Claim (2289): input-level `checkInputDoubleSpend` `onDone` (validation.js:2289) throws for
  private assets on full nodes when a conflict error propagates — reachable when the unit-level
  `validateSpendProofs` (validation.js:1640) did NOT reject first: (a) private-elements chain flow
  (`validateDivisiblePrivatePayment` — no message-level uniqueness check), (b) concurrent-validation
  race, (c) missing `spend_proofs` message. Determine EMPIRICALLY which of (a)-(c) is reachable with
  the real path, or refute all three.
- Claim (1678): `throw Error("unreachable code, conflicting ...")` (validation.js:1678) when a
  conflicting record's unit is `temp-bad` — spend of an output whose unit is temp-bad. Determine if
  a temp-bad unit's output can be spent (does an earlier check block it?) or if this crashes.
- Deliverable: `evidence/lab/p2/` — one script per reachable site (or a documented refutation with
  the decisive control for each).

### P4 — SQL: `+competitor_units.sequence='good'` unary-plus coercion divergence (main_chain.js:1391-1416)
- Claim: on Oracle MySQL 8, `+'good'` → 0 and `0='good'` → TRUE (string→number coercion), so the
  predicate matches ALL sequences; sqlite/MariaDB (tested) match only 'good'. Divergent
  `final-bad` resolution → divergent ball hashes → consensus divergence between DB backends.
- Verify with the tools available (sqlite + any installed MySQL-family server; document Oracle
  MySQL 8 coercion precisely with references — MySQL manual / bug reports). If MariaDB is installed,
  re-run the exact query and record the result. Produce the exact SQL test + expected Oracle result.
- Also: check whether Obyte deployments realistically mix DB backends (does the program/docs specify
  sqlite-only for full nodes? conf.storage supports mysql) — the production-mix question decides
  severity.
- Deliverable: `evidence/lab/p4/` — SQL test scripts + a written severity determination.

### P6 — economics: tps-fee `exp()` blow-up → author balance poisoning (storage.js:1228-1234)
- Claim: `getFinalTpsFee = round(base_tps_fee * (exp(tps) - 1))` with `elapsed = (timestamp diff) || 1`
  (storage.js:1174): equal-second timestamps → elapsed=1 → tps=count; count≥30 → fee ≥10% of total
  supply; count≥709 → Infinity → `tps_fees_balance` (storage.js:1261-1270) plunges negative →
  author permanently frozen (validation.js:1087 min-fee gate).
- Lab: drive `getFinalTps`/`getFinalTpsFee`/`updateTpsFees` through the real storage path with
  synthetic unit props (equal timestamps, N units in window) — measure the balance delta; test
  sqlite's handling of Infinity/NaN in the BIGINT column (does the INSERT fail, coerce, or store?).
- Also measure the attacker-economics: does the spamming author's own last unit get rejected by the
  min-acceptable fee gate (self-limiting)? Answer the 200%-expense feasibility question.
- Deliverable: `evidence/lab/p6/` — runnable script + measured numbers + the self-limiting verdict.

### P8 — S1 in formula eval: `is_valid_signed_package` complexity/count budget bypass (formula/evaluation.js ~1652-1655)
- Claim: evaluation-side gates are bare-`mci` (`max_complexity = mci >= pemCurvesFixMci ? 10 : 0`;
  3-package cap skipped below the gate) WITHOUT the disjunct. Old-DAG-attached AA → max_complexity=0
  (falsy → budget skipped) → up to ~100 signed-package calls × full definition validation + DB
  queries per AA trigger on every full node (valid unit, auto-propagating).
- Lab: real formula evaluation with `pemCurvesFixMci` set nonzero: (a) confirm the max_complexity
  divergence (mci below vs above); (b) measure CPU/DB amplification for N calls; (c) determine
  whether old-DAG attachment passes full unit validation (S1 prerequisite).
- Deliverable: `evidence/lab/p8/` — script + measurements + reachability verdict.

### P9 — engine semantics: `is_valid_merkle_proof` vacuously satisfiable (formula/evaluation.js:1763-1810, merkle.js:84-101)
- Claim: the proof root is attacker-supplied and never bound to a committed tree; `proof="0-" +
  base64(hash(X))` (single-element "tree", no siblings, index 0) passes for ANY X. Contrast
  `in merkle` (definition.js:1006-1031) which binds the root to an on-chain feed.
- Lab: pure formula-evaluation test (no DB needed): `is_valid_merkle_proof("X", "0-" + b64(hash(X)))`
  → true for arbitrary X not in any real tree; show `in merkle` equivalent FAILS without a posted
  root. Document impact: any AA using the construct without separately pinning the root is
  bypassable (engine-level footgun).
- Deliverable: `evidence/lab/p9/` — script + outputs + impact statement.

## Refuter briefs (fresh context, briefed to REFUTE — never told a flaw is expected)

### R1 — refute the private-payment crash family (P1: validation.js:1662; P2: 2289/1678)
Read `evidence/round0/f1.md`, `f7.md`, `f8.md`, `f13.md`, then the P1/P2 briefs above. Attack every
link: (1) is the 1662 throw really reachable with a unit that passes all PRIOR validation (does the
unit even reach checkForDoublespends? does `spend_proofs` need to be in the message? is there an
earlier address/ownership check that rejects A first?); (2) does the process really die (is there a
try/catch between the throw and the uncaughtException handler; is the handler re-throw confirmed?);
(3) the bearer-secret premise (does the sender really retain the blinding; can the victim's node be
forced to process A — delivery path); (4) 2289 race feasibility; (5) 1678 temp-bad reachability.
For each link name the decisive control that would block it, or concede the link with the exact
file:line that makes it pass. Concede only where the code forces you to.

### R2 — refute P4 (MySQL divergence) and P6 (tps-fee balance poisoning)
Read `evidence/round0/f2.md` (T-f2-01) and `f16.md` (T1), then the P4/P6 briefs. P4: (1) is the
`+sequence='good'` predicate really evaluated as `(+sequence)='good'` and does MySQL coerce the
string comparison to a number (cite the semantics precisely); (2) do Obyte full nodes realistically
run Oracle MySQL (is the mysql backend maintained/tested; what does conf.storage default to); (3)
does the divergence actually change ball hashes (is sequence part of getBallHash for these units;
does final-bad resolution differ meaningfully). P6: (1) can an attacker reach count≥30 with
elapsed=1 (are equal timestamps actually valid; is the min-acceptable-fee gate self-limiting); (2)
does sqlite store/coerce Infinity or reject the UPDATE; (3) is the "permanent freeze" real (any
recovery path — updateMissingTpsFees, restart, other authors in the window); (4) the 200%-expense
feasibility rule. Name the decisive control per link or concede.

## Output contract (all agents)

Write your full report to `evidence/round1/<id>.md` and RETURN a compact JSON:
`{id, claim: "<one line>", verdict: "confirmed_signal | refuted | needs_more_work | blocked",
decisive_control: "<the exact control or mechanism, file:line>", raw_evidence: "<file paths>"}`.
Builders: keep every script runnable + documented (a reviewer will RUN it independently in round 2).
Do NOT modify the ocore clone beyond the lab symlink. No live network contact. No secrets.
