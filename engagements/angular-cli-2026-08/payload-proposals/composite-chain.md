# COMPOSITE CHAIN — the operator-facing document (chainstorm phase, E2)

**Scope:** the final composite statement for the operator — what the five chains compose into,
across deployment shapes; what may and may not be claimed; and what is wire-2-gated.
**Sources:** INT6 independent composite review (E2-R6), KP-INT adversarial composite kill-pair
(E2-R7), INT4 composite matrix, C2F wire-2 spec, plan.md §12 (chain matrix), E1-C1 venue
corrections (E2-R4/C4F + E2-B2/ECKP severity 6.3).

---

## 1. The final composite statement (INT6 5-bullet framing, with the mandatory label set)

**One attacker-authored Angular repo is the single delivery vehicle** that composes, across
deployment shapes:

1. **Win32 RCE via unvalidated registry values** (W1 — **execution-pending**; the marginal vs
   install-scripts is pre-gate/pre-confirmation timing + manager-independent `ng update` entry,
   NOT new code-exec capability where scripts run).
2. **Cross-platform data loss via uncontained config paths** (M3 delete + case-guard root-delete
   on case-insensitive fs; D2 purge; E1-C1 member A write; extract-i18n/prerender writes) — the
   hops that fire under `--ignore-scripts` and in no-install config-as-data CIs: **this is the
   chain's unique capability** (install-script-mitigation bypass). *Shape note required:* the
   config-as-data CI shape excludes install-dependent hops.
3. **Product-code persistence** (D1 route codegen → the dev's app → production SSR; E1-C1 member
   C → deployed client bundles AND legacy SSR server processes — severity settled at Medium 6.3
   for the legacy-SSR venue per E2-B2/ECKP; doctrine risk carried). *Venue separation required:*
   E1-C1's write side (member A) belongs to bullet 2 (C1), its read side (member C) belongs here
   (C4) — one finding, two venues; do not double-count.
4. **MCP agent steering mechanics** (repo content → priority-0.9 instructions → run_target
   option-values → out-of-roots read → build-artifact exfil) — **live mechanics**; **agent-follow
   (H2) SIMULATED/estimated (MEDIUM-HIGH)**; capability delta only for the real-but-undemonstrated
   shell-less client class.
5. **An enabling condition for future robot-key exposure** (D3 guard defect, publicly
   co-discovered #33632) — **future-conditional watch-list**, not a live hop.

Caps compound: every hop shares the config-trust / attacker-delivered-repo precondition; the RCE
hops are win32 + execution-pending; the agent-follow hop is simulated; the CI shape excludes
install-running CIs; C5 is future-conditional; the config-trust doctrine
(#33074/#33076/#32873/#32892) applies to most hops. The composite's filing counterweights are:
**(a) the install-script-mitigation bypass, (b) production-persistent code, (c) the
mis-keyed-guard discriminator** (ensureValidSubPath guards explicit subPath but not keys — the
"fix exists but is keyed wrongly" pattern), (d) W1's severity6-disclosed-class delta framing.

## 2. Per-shape capability table (KP-INT: the only valid reading)

**Composite-as-SINGLE-SCENARIO (X4 "one artifact, five impact planes" on one machine) is
KILLED** — shape conflation (the dev shape runs install; the config-as-data CI shape excludes
attacker-scripted install — mutually exclusive for install-dependent hops) + the probability
product for targeted claims. **Composite-as-CAPABILITY-CONJUNCTION SURVIVES** — one repo = the
blast radius it can reach across deployment shapes.

| Composite | Composition | New delta | Verdict |
|---|---|---|---|
| X1 = C1 × C3 | repo → steered agent (MCP) | no-friction execution (agent triggers the destructive hops silently) — stealth/automation, NOT new capability for shell clients (R7); H2 agent-follow SIMULATED | narrow-real |
| X2 = C1 × C4 | repo ships the locale KEY **and** the module (4-dot variant, check4dot.mjs live) | **precondition removal** (no separate dependency-confusion step) + **production persistence** (deployed client bundles AND legacy-SSR server processes) | **REAL — strongest** |
| X3 = C2 × C4 | maintainer-browser targeting via a preview-deploy step | mechanism-complete; requires the preview-deploy step + a maintainer click; inherits C2's shape restriction | fragile-real (**wire-gated**) |
| X4 = C1×C2×C3×C4 | "one artifact, five impact planes" | single-deployment-scenario reading | **KILLED as single-scenario** |
| X5 = C3 × C5 | — | no shared event surface | correctly NO |

**FINAL-FRAMING (one sentence per shape):**

> One attacker-authored Angular repo is the single delivery vehicle that composes: **(dev shape)**
> pre-gate win32 RCE (W1, execution-pending) + cross-platform data loss under install-script
> hardening (M3/D2/E1-C1 member A) + product-code persistence to production SSR (D1) and — with a
> `--localize` build — to deployed client bundles AND legacy SSR server processes (E1-C1 member C,
> the X2 composite: repo ships the key AND the module) + MCP-agent steering mechanics (live; H2
> agent-follow pending); **(config-as-data CI shape)** the same repo's config values drive
> delete/write sabotage without any attacker code executing (M3/D2/E1-C1), and a preview-deploy
> step would serve the poisoned bundle to the reviewing maintainer (X3, wire-gated).

**Mandatory label set** (the framing is defensible only if carried): execution-pending ×2
(W1 dev, C2D CI-token) · simulated H2 (C3) · future-conditional C5 · per-shape split (dev vs
config-as-data CI) · E1-C1 venue separation (member A = write/C1 vs member C = read/C4) ·
wire-gated X3 · E1-C1 legacy-SSR severity = Medium 6.3 (E2-B2/ECKP).

## 3. Must-NOT-be-claimed list (until wire-2 / further evidence)

1. Any "in real GitHub Actions CI" statement — no live run; the macOS-runner root-delete is
   verified on local APFS; runner semantics are documented, not demonstrated.
2. **CI-token theft** ("GITHUB_TOKEN/ACTIONS_RUNTIME_TOKEN/OIDC inherited") — source-verified env
   inheritance only, zero execution (W1 CHAINSTORM AMPLIFIER carries the exact token inventory
   and the read-scoped-GITHUB_TOKEN default).
3. **"Deployed production" impact** — the bundle demos are synthetic local builds; production
   reach is source-reasoned.
4. **"Agents in the wild follow the steering"** — H2 simulated; the honest label is
   ARMED-WITH-ESTIMATED-FOLLOW (self-assessment limitation declared by the blind-test lane).
5. **"Angular's own CI is vulnerable"** — C2A/S6: structurally not reachable; keep as the
   negative reference, never as a victim.
6. A composite sentence that sums all five findings across BOTH shapes ("one repo achieves RCE +
   deletion in dev and CI") — false in both directions (shape conflation; the C2 config-as-data
   shape covers only the delete/write hops).

## 4. Wire-2 gated items (operator-confirmed at the moment of the act — none authorized here)

| # | Act | Closes | Spec |
|---|---|---|---|
| W-1 | Private-fork Actions run: `chain2-cisabot` workflow building a PR-shipped malicious angular.json on a macOS runner (case-guard root-delete) | Chain 2 runner-semantics rung + full-build E2E for the filing bundle | `payload-proposals/chain2-wire2-spec.md` (private throwaway fork; no secrets; cleanup path declared) |
| W-2 | Windows-host run of `WINDOWS-E2E-FIXTURE.md` (local, method-2 — a Windows host is required, not GitHub) | W1's single evidence-grade gap (cmd.exe execution) | `findings/W1-yarn-classic-disttags-win32/WINDOWS-E2E-FIXTURE.md` |
| W-3 | Real desktop-assistant MCP client test of the steering chain (Claude Desktop / ChatGPT Desktop with the built CLI server) | C3 H2 agent-follow hop + the M2 shell-less promotion trigger | steering-demo evidence (`findings/M2/evidence/steering-demo/`) + INT2 verdict |

W-2 is method-2-local on an operator-owned Windows machine (no wire); W-1 and W-3 trip wires 2/3
respectively per `scope.md` §9 and require a fresh operator confirmation naming the target, the
payload, and the cleanup path at the moment of the act.

## 5. Chain-matrix cross-reference (plan.md §12)

C1 CONFIRMED (fixture 9/9 both modes) · C2 NARROWED-SURVIVES (config-as-data demonstrated in-lab;
wire-2 = W-1) · C3 ARMED-WITH-ESTIMATED-FOLLOW (steering live; H2 pending = W-3) · C4 CONFIRMED
venue-restricted (browser + legacy-SSR Medium 6.3; X2 evidence = the Chain-4 filing centerpiece) ·
C5 FUTURE-CONDITIONAL (watch-list; #33632 co-discovery). Composite verdict: single-scenario
KILLED, capability-conjunction SURVIVES with X2 (C1×C4) strongest.
