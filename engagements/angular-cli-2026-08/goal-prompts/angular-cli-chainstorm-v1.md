# GOAL PROMPT — `angular-cli-2026-08`, CHAINSTORM PHASE (chains × escalation × next-phase handoff)

You are the **orchestrator** of the chainstorm phase of an authorized white-box red-team of
`github.com/angular/angular-cli`. Read `CLAUDE.md`, then this engagement's `scope.md`,
`program-policy.md`, `goal-prompts/angular-cli-deep-v1.md` (the completed deep phase), `cascades.md`,
and `plan.md` (§7-§11). The kernel is **ACTIVE**; the deep phase ended with **seven promoted
findings** (all gates CLEAR) and 12 fully-verdict-ed lanes. This phase attacks the **kill chains**
the findings compose into, per-finding escalation lanes, and — if the chains confirm — hands a
**next deeper escalation phase** off to a final 64-subagent swarm.

---

## 0. The contract

Three waves, no exceptions, **4+ hours of work**:

1. **Wave A — chains: 10 rounds × 8 subagents (80 slots).** One round per chain (1-5), then
   integration, kill-pairs, cascading, demos, documentation.
2. **Wave B — per-finding lanes: 36 subagents (6 lanes × 6 each, equally distributed).**
   Lanes: W1 · M3+D2 family · D1 · E1-C1 · M2 · D3. Six subagents per lane: mechanism-extension,
   channel-sweep, kill-pair, PoC-build, filing-delta, reviewer.
3. **Wave C — reviewers for every important claim**, embedded in every round (kill-pairs /
   adversarial refuters before anything touches a report) — same discipline as the deep phase.
4. **Wave D — next-phase handoff: 64 subagents in 4 rounds (4 × 16).** If any chain or escalation
   CONFIRMS, this swarm BEGINS the next deeper escalation phase from the confirmed residue:
   R1 planning the next phase from the confirmed chains, R2 executing its highest-value lanes,
   R3 verifying/kill-pairing, R4 synthesizing + records + phase-terminal.

**It is possible. If you give up you are not trying hard enough** — that governs *effort*, never a
verdict. A chain that dies at a kill-pair is a *result*; a chain that survives is an *escalation*.

## 1. The chains under attack (from the 7-finding portfolio)

- **Chain 1 — Cloned-repo delivery chain (W1+M3+D2+E1-C1+D1).** One attacker-authored repo ships
  `.yarnrc`/`.npmrc` → attacker registry + malicious `dist-tags` (W1, now manager-independent via
  ng update) · malicious `angular.json` (`outputPath`, `cli.cache.path`, `i18n.locales` keys →
  M3 delete + case-guard root-delete, D2 cache purge, E1-C1 webpack write escape) · poisoned
  schematics defaults (D1, global-config channel reaches `route` with no flag). Dev runs the
  normal README workflow → RCE + workspace deletion + file overwrite + production code. Goal:
  one end-to-end fixture, real commands, synthetic registry; kill-pair: does any single step's
  cap (e.g. npa/semver gates, confirmation prompts) break the chain?
- **Chain 2 — CI sabotage (M3 amps + E1-C1 + D2 on PR content).** Fork PR to a repo whose CI
  runs `ng build`/extract-i18n/prerender on PR content → malicious config values from the PR →
  case-guard root-delete on macOS runners (case-insensitive APFS), E1-C1 webpack write escape,
  extract-i18n/prerender overwrite of files later CI steps read. Goal: map which real-world CI
  shapes are vulnerable (Angular's own pr.yml as the reference), runner-state impact analysis;
  wire-2 private-fork demo remains operator-gated.
- **Chain 3 — MCP agent steering (D1→M2→run_target).** D1-injected code/strings in a repo → dev
  opens it in an MCP-enabled editor → M2 reads repo content as assistant instructions (priority
  0.9) → injected instructions steer the agent through run_target option-values (relative `..`
  traversal, live-verified) → silent exfil inside a legitimate build artifact. Shell-less trigger
  (desktop-assistant clients) = true restricted-host bypass. Goal: working steering demo harness;
  kill-pair: agent-judgment / confirmation layers that could refuse.
- **Chain 4 — Browser supply chain (E1-C1 member C).** Locale key + dependency-confusion package
  in the resolution chain → findLocaleDataPath loads attacker module → Babel transform → attacker
  content ships in the production bundle, executes in app users' browsers. Goal: bundle demo +
  browser-execution proof; kill-pair: resolution-failure fallback, Babel parse bound.
- **Chain 5 — D3 forward chain (guard ineffectiveness + robot key).** Fork PRs reach secret-bearing
  jobs with the robot key wired in; the cap is the action being API-only. Any future action change
  that reads untrusted content turns the E12 flood into a key-exfiltration primitive. Goal: audit
  the action + sibling workflows at the pin for ANY file-read/templating today, document the
  one-line-change watch list; kill-pair: show a current file-read or refute the exposure.

## 2. Wave A rounds (10 × 8)

- R1: Chain 1 assembly (8 lanes: .yarnrc channel, combined-repo fixture design, per-finding
  channel verification in-repo, ordering/sequencing analysis, chain kill-pair prep, negative
  control design, integration-harness build, chain novelty re-check).
- R2: Chain 2 (8 lanes: CI-shape survey, pr.yml reference analysis, macOS-runner case-guard
  semantics, extract-i18n/prerender/E1-C1 in CI, runner-state impact, kill-pair, wire-2 spec,
  negative control).
- R3: Chain 3 (8 lanes: steering-harness build, D1-carrier analysis, run_target exfil harness,
  agent-judgment kill-pair, shell-less trigger reality check, stealth analysis, negative control,
  reviewer).
- R4: Chain 4 (8 lanes: bundle demo, dependency-confusion resolution audit, Babel bound,
  browser-execution proof, production-reach analysis, kill-pair, negative control, novelty).
- R5: Chain 5 (8 lanes: action file-read audit at pin, sibling-workflow audit, key-exposure map,
  watch-list, concurrency analysis, kill-pair, attribution rows, novelty).
- R6: Integration (8 lanes: cross-chain sequencing, combined fixture assembly, chain-interaction
  analysis, demos for surviving chains, chain kill-pairs round 2, evidence packaging prep,
  records prep, reviewer).
- R7: Kill-pairs (8 lanes: adversarial reviewers on EVERY confirmed chain claim, one per chain +
  3 integration).
- R8: Cascading (8 lanes: fold confirmed chain amplifiers into findings, spin-off NEW findings
  for new root causes with full gate discipline, chain deltas per finding, remediation updates).
- R9: Demos + evidence (8 lanes: chain E2E demo runs, PoC artifacts, evidence dirs, chain
  documentation in plan.md §12, credential scan).
- R10: Chain records (8 lanes: chain matrix in plan.md §13, novelty per chain, chain attribution
  ledger updates, kernel events, rounds rows, next-phase residue list).

## 3. Wave B — per-finding lanes (36 = 6 lanes × 6 subagents)

W1 · M3+D2 family · D1 · E1-C1 · M2 · D3. Per lane the 6 subagents: (1) mechanism-extension
(what new channel/venue the finding has beyond the documented), (2) channel-sweep (family members,
sibling sinks, adjacent surfaces), (3) kill-pair (adversarial refutation of the strongest
extension), (4) PoC-build (compiled/live artifact for the strongest surviving extension),
(5) filing-delta (marginal delta + severity recheck vs the documented caps), (6) reviewer
(independent adjudication of the lane's output before it touches a report).

## 4. Wave D — next-phase handoff (64 = 4 × 16)

If ≥1 chain confirms or ≥1 escalation is gate-promoted:
- D-R1 (16): next-phase goal-prompt draft from the confirmed residue, lane enumeration, cap
  inventory, chain leftovers, risk matrix.
- D-R2 (16): execute the next phase's highest-value lanes (buildable artifacts, demos, audits).
- D-R3 (16): kill-pairs + verification of D-R2 outputs; reviewers on every claim.
- D-R4 (16): synthesis, records, kernel events, phase-terminal for the chainstorm campaign.

## 5. Discipline (unchanged)

`engine/whitebox-analysis.md` funnel; kill-pairs before any fold; gates G0-G6 before any promotion;
severity = marginal delta; wire-2 only with a fresh operator confirmation at the moment of the act;
attribution boundary (dev-infra-rooted → cascades.md, never filed here); local lab only; no real
credentials; cleanup ledger for every artifact; redaction always.

## 6. Terminal states

Per chain: `confirmed` (demonstrated end-to-end or mechanism-complete with named residual) ·
`killed` (cap demonstrated) · `partial` (some hops live, named blocker) — each with the exact
evidence. Per escalation lane: `promoted` / `folded` / `capped` / `refuted`. The phase terminal is
**the chain matrix with every chain verdict-ed and the next-phase residue list handed to Wave D.**

## 7. Calibration

Realistic yield: Chain 1 (cloned-repo delivery) is the most likely to CONFIRM end-to-end in-lab;
Chain 2's wire-gated demo stays operator-pending but the mechanism should fully map; Chain 3's
steering harness is buildable (existing pieces); Chain 4's bundle demo is buildable; Chain 5 is an
audit + watch-list. Both confirmed chains and fully-killed chains are successes. The failure to
avoid: a chain "confirmed" without its kill-pair, or Wave D starting from unverified residue.

## 8. First move

1. Write the chain matrix + Wave A/B/D lane plans into plan.md §12.
2. Launch Wave A R1 (8 subagents) immediately.
3. Funnel R1 the same session; record; re-route.

**Do not file, submit, publish, or contact Google, Angular, or any maintainer. The operator files.**
