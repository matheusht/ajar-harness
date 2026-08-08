---
id: vulns.tvm-energy-accounting
name: TVM Energy/Opcode Accounting — custom schedule under/overcharge
description: >
  Prove that a TVM energy-accounting path (opcode cost table, call-path energy math,
  refund/stipend/63-64 handling, dynamic energy factor, or the #6613 BigInteger rewrite)
  undercharges an operation relative to its real CPU/work cost, or charges divergently from the
  intended semantics, so an attacker obtains effectively free or cheaper-than-intended execution
  (energy DoS on nodes, economic abuse of undercosted opcodes/precompiles). Confirmed only by
  measuring the delta on a real private-net node with real TVM execution.
type: vuln
owasp: "no single CWE — CWE-770 (allocation without limits) / CWE-682 (incorrect calculation) /
CWE-400 (uncontrolled resource consumption)"
atlas: "—"
patterns: []

activation:
  strong:
    - "call-path energy math where a penalty/charge term is computed as `energyCost * factor /
      DECIMAL - energyCost` with `factor` (context contract factor) potentially unbounded, and an
      overflow is clamped to zero instead of failing closed (undercharge shape)"
    - "63/64 rule (caller energy reserve) applied ONLY when `allowTvmCompatibleEvm &&
      contractVersion == 1` — otherwise a sub-call can forward ALL remaining energy, leaving the
      caller at 0, with only MAX_DEPTH=64 bounding recursion"
    - "a custom (pre-EIP-2929) opcode energy table where any opcode's cost is below its real CPU
      cost on the pinned implementation, or where a post-2929 opcode (TSTORE/MCOPY/CLZ/MODEXP,
      PUSH0, warm/cold storage) was added with the wrong price"
    - "the #6613 BigInteger/StrictMath rewrite (addExact/multiplyExact/floorDiv) — any site where
      an ArithmeticException during gas math lands in a catch that undercharges instead of
      fail-closing (spendAllEnergy)"
  weak:
    - "refund/stipend ordering divergences from Ethereum semantics (EIP-3529 refunds, CALL
      stipend 2300) with no exploitable delta measured"
    - "dynamic energy factor (DYNAMIC_ENERGY_FACTOR_DECIMAL, updateContextContractFactor) paths
      whose factor bounds are not audited"
  negative:
    - "every opcode cost verified ≥ CPU cost with real execution measurements on the pinned tag,
      and call-path math fail-closes on overflow → likely held"
    - "cost table byte-identical to the upstream audited schedule (EIP-2929/EIP-2565 etc.) with no
      local modifications → positive control, do not re-report"

safe_signal:
  proxy: >
    a predeclared measurable delta in an OWNED disposable private network: locally-minted test
    TRX, a contract deployed by us that executes the undercosted operation N times (or a crafted
    transaction driving the call-path math), measure energy charged vs wall-clock CPU and vs the
    intended charge (Ethereum-equivalent schedule / exact-math control). The proof is the delta
    between what the audit schedule charges and what the real path charges or costs. Never a real
    network (mainnet/Shasta/Nile) or real TRX.
  never: >
    do not touch a live TRON network, real TRX, or third-party contracts; do not exceed the
    minimal local demonstration of the undercharge; revert any local state change and log it in
    cleanup.md.

impact_escalation:
  enabled_by: scope.md#impact_demo_authorized (tron-2026-08 signed MAX Zone-2, 2026-08-06)
  requires: human_confirm_only_for_submission
  containment: "disposable local private net, locally-minted test TRX; any escalation (energy DoS
    flooding, block-time stall) stays inside the local validator set"

oracle: [signal-oracle, adjudication-oracle, ghsa-fix-diff-oracle]
severity_rubric: >
  undercosted_opcode_energy_dos (an opcode/precompile/call path runs with measurably less energy
  than its real CPU cost, enabling cheap node-crippling loops): high — $25k ceiling per
  goal-prompt routing (economics-break would argue critical, ceiling at high unless combined with
  fund theft); call_path_undercharge_via_overflow (penalty forced to 0 by long overflow, or
  charge computed on unbounded factor): high; energy_double_charge_or_refund_ordering (users
  overcharged or refund mismatch): medium; semantics_divergence_only (differs from Ethereum but
  no measured delta): low.

procedure:
  - "MAP THE CHARGE: enumerate the cost table (EnergyCost/OperationRegistry), the call-path math
    (getCalculateCallCost, getCallEnergy, penalty, adjustedCallEnergy, 63/64 gating, stipend,
    refund ordering) and the dynamic-energy-factor path; record file:line and formula."
  - "DIFFERENTIAL vs UPSTREAM: compare each cost/rule to the Ethereum schedule the code claims to
    implement (EIP-2929 post-fork opcodes, EIP-198/2565 modexp, EIP-3529 refunds). A deviation is
    a lead only if it undercharges."
  - "CHECK OVERFLOW SEMANTICS: for every long multiply/divide in energy math, verify the
    fail-closed direction — overflow must cost MORE (or fail), never zero/negative."
  - "NEGATIVE CONTROL: measure the same opcode loop under the reference schedule (or exact
    BigInteger math) — the delta between charged energy and real CPU is the exploit surface."
  - "NAME THE BROKEN INVARIANT: 'N executions of opcode X cost E energy but consume C CPU,
    enabling ~M× amplification of the node's work per unit energy' — not 'energy math has
    overflow'."
  - "FAITHFULNESS: reproduce on the REAL pinned code (GreatVoyage-v4.8.2.1) on a disposable
    single-node private net with locally-minted TRX; real TVM, real transaction execution. A
    standalone math snippet that never runs the real VM path is a reward-hack, not evidence."
  - "DIFFERENTIAL (lens 11): where a flag gates the new math (allowTvmCompatibleEvm,
    allowEnergyAdjustment, allowDynamicEnergy, allowTvmOsaka/Shanghai/Cancun), run the PoC with
    the flag OFF and ON — the maintainers' own upgrade as the pre/post boundary."
  - "Default to needs_review unless the broken invariant, the exact site, and the measured delta
    are all stated; energy findings overclaim easily when the real CPU cost is not measured."
  - "CASCADE (Q1/Q2): every surviving site is a branch — Q1: which sibling opcode/precompile/call
    path shares the charge shape? Q2: does the undercharge primitive compose (cheap execution →
    flood → node DoS; or undercosted op → economic abuse in a DeFi-style contract)?"

emits: [attempt, finding]
---

## What "confirmed" looks like here

A named invariant (opcode/precompile/call path charged ≥ its real CPU cost; call-path math
fail-closes on overflow; 63/64 reserve or equivalent depth bound) is broken, proven on the real
pinned node by a measured energy-vs-CPU delta (or an overflow→zero charge) with the reference
schedule as negative control.

## Known recon grounding (pinned GreatVoyage-v4.8.2.1, recon 2026-08-06)

- EnergyCost.java keeps a custom pre-EIP-2929 schedule with a dynamic-energy multiplier;
  v4.8.2 rewrote cost math to BigInteger/StrictMath (#6613 — a regression surface; addExact/
  multiplyExact throw ArithmeticException, so gas-math throws must fail closed, never undercharge).
- Call-path lead: `getCalculateCallCost` computes `penalty = energyCost * factor /
  DYNAMIC_ENERGY_FACTOR_DECIMAL - energyCost` (long multiply on unbounded `factor` —
  getContextContractFactor bound UNRESOLVED; overflow is clamped to penalty=0 → undercharge
  shape, EnergyCost.java ~516-521); energyCost + adjustedCallEnergy is bounded by energyLimitLeft
  (no overflow there).
- 63/64 rule gated on `allowTvmCompatibleEvm && getContractVersion()==1` — otherwise a sub-call
  can forward ALL remaining energy (caller left at 0), recursion bounded only by MAX_DEPTH=64;
  undercharge per se not established, efficiency divergence noted.
- modexp pre-Osaka matches EIP-198 (multComplexity quadratic, min(expLen,32) bit-length,
  modLen=0 → 0 gas with trivial work — Ethereum-equivalent, NOT a divergence).
- TIP-7883 (Osaka) modexp adds caps + higher pricing — differential control (lens 11).
- Open questions for the hunter: context-contract-factor bounds, Maths.min/max boolean overload
  semantics (VMConfig.disableJavaLangMath), RepositoryImpl:931 averageLastUsage round/decay
  (resource-accounting floor — that lane's surface), opcode table vs EIP-2929 deltas,
  refund/stipend ordering.

## Not this card

- Resource/Stake-2.0 float→long accounting → `vulns.resource-precision-loss`.
- Precompile CPU-vs-energy mismatches (BN128/modExp/blake2f calldata edges) → the tvM-precompiles
  lane (coordinates via cascades.md).
- Generic integer overflow elsewhere (no energy/charging semantics) → unchecked-arithmetic.

## Do not overclaim

- "Custom schedule differs from Ethereum" is not a finding — the direction (undercost) and a
  real measured CPU-vs-energy delta are required.
- Do not claim energy DoS without running the loop on the real node and measuring node impact
  (block-time stall, CPU) — not computed in isolation.
- If a flag's on-chain activation state is unverifiable from source, say so and scope the claim
  (default-config exposure vs flag-activated).
