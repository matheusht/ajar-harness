---
id: pattern.dag-js-numeric-value-arithmetic
name: JS Number on Money — double-precision value arithmetic in the ledger
description: >
  Value arithmetic runs on JS `Number` (IEEE-754 double) instead of a fixed-precision type. Amounts
  that leave the integer-safe range (2^53) or that are computed with division, multiplication of
  large values, fee percentages, or asset-cap arithmetic lose precision silently; comparisons
  coerce; two nodes can compute different results for the same formula. In a value ledger, any
  `Number` arithmetic on amounts is a candidate: rounding, precision loss, overflow, and
  cross-node divergence.
type: pattern
owasp: "—"
also: "DAG/DLT value arithmetic — precision/rounding"
atlas: "—"
routes_to: ["stub:dag-dlt-vuln-cards"]

activation:
  strong:
    - "an amount, fee, cap, or balance is computed with plain `*`, `/`, `+`, `-` on `Number` where the operands can exceed 2^53 or produce non-integer results"
    - "a formula (AA) evaluates money math in JS doubles (Decimal used inconsistently — some paths Decimal, some plain Number)"
    - "recent commits touch numeric canonicalization: `-0` expunge, Decimal.isDecimal checks, `isFiniteDecimal`, exponent forms"
    - "a value is compared for equality after arithmetic (rounding makes `a*b === c` fragile)"
  weak:
    - "integer division or percentage math on fees/shares (earned_headers_commission_share, tps fees)"
    - "asset caps, issue amounts, or balances stored as JS numbers"
    - "parseInt/parseFloat/Number() on user-supplied amount strings"
    - "exponent or scientific-notation amounts (`1e21`)"
  negative:
    - "all value arithmetic is Decimal (decimal.js) or BigInt end-to-end, including fee and share math"
    - "conversion to Number happens only for display, never for consensus-bearing math"
    - "equality comparisons of computed values are avoided or done with explicit rounding tolerance"
---

# JS Number on money

> **The two failure modes.**
> 1. **Precision loss:** amounts beyond `Number.MAX_SAFE_INTEGER` (2^53−1 ≈ 9.007e15) lose integer
>    precision — two large values that differ by 1 can be equal after arithmetic; `a + b - b !== a`.
>    In units of 10^-9 (Obyte base), 9e15 base units ≈ 9e6 full units — reachable for whale assets.
> 2. **Non-integer division:** fee shares, commissions, caps with fractions round; rounding direction
>    (floor vs round) that differs across nodes or across a boundary is a consensus split or a
>    value-theft (round-down-theft / round-up-inflation).

**Where it bites in a DAG ledger.**
- **Formula evaluation** — AA code computes values in JS; a formula that multiplies a large balance
  by a rate loses precision; the same formula on two nodes with different float rounding is a split.
- **Fees/commissions** — `earned_headers_commission_share`, tps fees, oversize fees: percentage
  math on amounts.
- **Asset caps / issue amounts** — cap arithmetic that overflows 2^53.
- **Equality gates** — "if (sum === total)" after arithmetic; a rounding difference silently fails
  or passes a check.

## Suggested probes (benign, local-fork only)
- **Enumerate amount arithmetic.** Grep `*`, `/`, `+`, `-` on balance/fee/cap/amount variables in
  `indivisible_asset.js`, `divisible_asset.js`, `headers_commission.js`, `formula/evaluation.js`,
  `aa_*.js`. Identify which use Decimal vs Number. The mixed paths are the candidates.
- **Boundary math.** Construct amounts at 2^53±1, compute fee/cap/division, and compare against
  Decimal results. Any divergence is a lead.
- **Formula precision.** Write a formula doing `balance * rate` with a large balance; check storage
  value against Decimal reference.
- **Cross-node determinism.** The same transaction processed on two nodes must produce identical
  state. Any float divergence is Critical-shaped (split).

## Negative controls
- Reference Decimal/BigInt computation matches the ledger's result.
- Two nodes produce identical state for the same input.
- Equality checks hold under rounding.

## Counterexample (held)
- Value math is Decimal end-to-end; Number appears only in display/JSON transport; no
  consensus-bearing arithmetic on doubles.
