---
id: pattern.dag-canonicalization-split
name: DAG Canonicalization Divergence — values hashed/compared inconsistently across nodes
description: >
  Money-bearing or consensus-bearing values (unit hashes, sorted lists, formula results, asset
  fields) are canonicalized inconsistently: `-0` vs `0`, `NaN`, array-vs-object equality, sort
  order that depends on runtime type coercion, JSON serialization order. Two honest nodes compute
  different hashes or different comparison results for the same logical unit → permanent consensus
  split. The signature is a recent commit *changing* the canonicalization (sortObject descent,
  expunge -0, isEqual replacement).
type: pattern
owasp: "—"
also: "DAG/DLT consensus split — hash canonicalization"
atlas: "—"
routes_to: ["stub:dag-dlt-vuln-cards"]

activation:
  strong:
    - "recent commits touch canonicalization/serialization: `-0` handling, `sortObject` array descent, `lodash.isEqual` replacement, `expunge` helpers"
    - "the same logical value can be serialized in two orders (object key order, array vs object, number formatting) before hashing"
    - "a hash or sort feeds consensus: unit hash, ball hash, definition hash, sorted address lists, formula result equality"
    - "string_utils.js / object_hash.js contain hand-rolled comparison or serialization logic"
  weak:
    - "Decimal / big-number handling with sign-zero or exponent forms (`1e-9` vs `0.000000001`)"
    - "comparison operators (`<`, `<=`) applied to values that may be numbers, strings, or objects"
    - "JSON.stringify used as a hashing input anywhere"
  negative:
    - "a single canonical serializer is used everywhere a value is hashed, and it is total (handles -0, NaN, key order, arrays)"
    - "formula results are normalized to a canonical form before any equality or storage"
    - "node tests cover cross-serialization equality (same value, two encodings → same hash)"
---

# DAG canonicalization divergence

> **Why this is a Critical-shaped bug.** A consensus ledger only needs *one* value that two honest
> nodes serialize differently to split forever — each side believes the other's units are invalid.
> The hash is the boundary. Any code path that hashes or compares a value without a single total
> canonical form is a candidate.

**JS gotchas that bite here.**
- **`-0` vs `0`:** `JSON.stringify(-0)` → `"0"` but `Object.is(-0, 0)` is false and `1/-0` is
  `-Infinity`. Formula arithmetic can produce `-0` (`x * -1` of 0); if one node stores `-0` and
  another `0`, hash inputs differ.
- **Key order:** `JSON.stringify({a:1,b:2}) !== JSON.stringify({b:2,a:1})`. Any object built by
  iteration order (DB rows, response parsing) must be sorted before hashing.
- **Array vs object:** `sortObject` historically did not descend into arrays — array contents
  sorted differently from object keys.
- **Type coercion in comparisons:** `"2" <= "10"` is false (string), `2 <= 10` is true (number).
  A sort that mixes types produces node-dependent order.
- **Decimal/exponent forms:** `1e-7` vs `0.0000001` — different strings, same value. If hashed
  before normalization → split.

## Suggested probes (benign, local-fork only)
- **Find every hash input.** Grep `getUnitHash`, `getBallHash`, `getObjHash`, `object_hash`, and
  `JSON.stringify` feeds. For each input object, ask: can this object be built in two key orders?
  Can any field be `-0`/`NaN`/exponent-form? Who sorts it, and with what comparator?
- **Formula-result divergence.** Formula (AA) computed values that feed state or unit content:
  produce `-0`, `NaN`, `Infinity`, or exponent forms via arithmetic, then check storage/hash.
  `formula/evaluation.js` — is the result normalized before hashing?
- **Sort comparators.** Find every `.sort()` on address/recipient/attestor arrays — the comparator
  must be total and type-stable. Test with mixed-type input (numbers-as-strings).
- **Cross-node differential in the lab.** Two-node local network; node A and B each serialize the
  same logical unit (constructed to have two encodings); show hashes diverge and MC/stability
  disagree. This is the decisive proof — a static divergence is `needs_review`.

## Negative controls
- The same value in two encodings produces the same hash (control run).
- Sorting is stable under mixed types.
- Formula results with `-0`/exponent inputs are stored canonically.

## Counterexample (held)
- A single total canonicalizer (e.g., a `sortObject` that descends into arrays + `-0` expunge +
  Decimal normalization) is used on every hash input, verified by cross-encoding tests.
