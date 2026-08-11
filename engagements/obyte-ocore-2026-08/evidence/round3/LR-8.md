# LR-8 — Formula language completeness (round-3 terminal audit)

Pinned `a7eb776afc68ed4bed05ba554f7f1e95f5d49b44`. Scope: the ops skimmed in round 0 — func_call /
func_declaration recursion, foreach/map/filter/reduce, json_parse/json_stringify edge cases
(prototype pollution, __proto__ keys, huge nesting), search_param_list, selectSubobject /
filterBySearchCriteria / assignByPath. Question: any op whose attacker-shaped input produces
cross-node divergence, crash, or state corruption; any op bypassing the complexity/ops accounting.

## Terminal verdict

**No new vulnerability class found.** All six audited op families are bounded and fail-closed.
One S1-family hardening note (eval-side bare-mci caps — dead by the KP-F2-link stabilization
verdict, recorded for the migration). The recursion vector is structurally impossible and
empirically rejected. No crash, divergence, or state-corruption path was found in any of these ops.

## Op-by-op findings (all HELD)

### 1. func_call / func_declaration recursion — HELD (structurally impossible + empirically rejected)
- Functions are registered into `locals` only AFTER their body is parsed
  (`validation.js:621-641`: `parseFunctionDeclaration(...)` returns props, then
  `assignField(locals, var_name, {props, type:'func'})`). A body referencing its own name fails
  `func_call` validation (`validation.js:1146-1148`: `if (!hasOwnProperty(locals, func_name))
  return cb("no such function name")`).
- Mutual recursion is impossible by declaration order (a body can only reference functions declared
  earlier; later names are not in scope during its parse).
- `callFunction` (evaluation.js:3045) has no runtime depth counter, but no reachable recursion
  exists. The `"function called after a return"` throw (3046) is unreachable (the top-of-`evaluate`
  guard, f5-R1). The `"neither local nor remote"` throw (evaluation.js:2420) is defensive —
  `evaluateFunctionExpression` (3095-3106) only produces `{local}` or `{remote}` shapes.
- **Empirical (real engine):** the codebase's own test `test/formula.test.js:3183` asserts
  `$f = ($a) => {$a+$f(1)}; $f(3)` → `null` (rejected); my independent probe reproduced
  (`LR8B self-recursion | err + res: null`).

### 2. foreach / map / filter / reduce — HELD (bounded)
- `readCount` (validation.js:1452-1470) caps count at **100**; complexity charged as
  `count * funcProps.complexity` (or 1 for zero-complexity) and ops as `count * funcProps.count_ops`
  (validation.js:1021-1024).
- Eval-side re-check: `arrElements.length > count → fatal error` (evaluation.js:2361-2363).
  **Empirical:** `reduce([1,2,3,4,5], 3, $f, 0)` → error ("found 5 elements in object, only up to 3
  allowed"); `map([10,20,30], 3, $f)` → ok; `reduce([1,2,3], 3, $f, 0)` → 6.
- Accumulator (reduce) and map result are `isTooBigObj`-checked after each/at end
  (evaluation.js:2424-2427, 2454-2457). Filter's retValue is bounded by the source collection size.
- Count expression restricted to literals or already-assigned local vars (validation.js:1455-1466).

### 3. json_parse / json_stringify — HELD (bounded, canonical, pollution-safe)
- **String-length caps:** every string path is capped at `MAX_AA_STRING_LENGTH` (4096): the
  top-level `evaluate` string branch (evaluation.js:144), `replace` (2133), `join` (2188),
  `json_stringify` (1973), string values (2956). `json_parse` input is therefore ≤4096 chars; the
  parsed object is bounded; the post-parse `isTooBigObj` check (1926-1927) is belt-and-suspenders.
- **Prototype pollution:** `assignField` uses `Object.defineProperty` (formula/common.js:69-77) —
  bypasses the `__proto__` setter (own data property semantics). `JSON.parse` creates an own
  `__proto__` data property (no setter invocation). Object spread (`{...obj0, ...obj1}`,
  evaluation.js:2771) uses CreateDataProperty. Selector reads use `hasOwnProperty` guards
  (evaluation.js:2933). **Empirical (real engine):** parsing `'{"__proto__":{"p":1},"a":5}'`
  leaves `Object.prototype` **CLEAN** (probe `Object.prototype.polluted_test_probe === undefined`).
- **Canonicalization:** `json_stringify` uses `getJsonSourceString` (sorted keys — canonical);
  `replaceNegativeZero` applied post-parse; `containsNonFiniteNumber` rejects non-finite values
  (1928-1930); Decimal config pinned (precision 15, ROUND_HALF_EVEN). No cross-node divergence.
- **Semantic quirk (not a bug):** `json_parse` of a wrappedObject input converts the input to
  `true` (evaluation.js:1919-1921, the commented-out "json_parse of object" error) — deterministic
  across nodes, not consensus-relevant.

### 4. search_param_list — HELD (capped); one S1-family accounting note
- Caps: ≤5 criteria pairs and ≤5 fields per pair (validation.js:491-497, 509-514) — with the
  `getMinRetrievableMci()` disjunct (migration complete on the validation side here).
- **S1-family note:** the ops-accounting line `count_ops += arrPairs.length` (validation.js:519) is
  bare-`mci` gated — below the fix MCI the ops cost is not charged. Max 5 ops; negligible; dead by
  KP-F2-link (no below-fix evaluation executes). Hardening note only.

### 5. selectSubobject / filterBySearchCriteria / assignByPath — HELD (pre-guarded or wrapped)
- `assignByPath` throws (`"not an object"`, `"scalar ... treated as object"`,
  evaluation.js:2866-2888) are wrapped by the caller's `try/catch → setFatalError`
  (evaluation.js:1281-1288) — clean fatal error, no crash.
- `selectSubobject` routes all errors through `cb2/cb` (evaluation.js:2908-2940).
- `filterBySearchCriteria` leading throws (`'search params is not an array'`, evaluation.js:2975)
  are unreachable through a validated `search_param_list` (validation.js:490-520 guarantees
  structure). The eval-side array-length/criteria caps (2985-2989) are bare-`mci` — S1-family
  hardening note (dead by KP-F2-link).

## S1 eval-side family members enumerated this pass (hardening notes only — dead by KP-F2-link)

| site | gate | skipped below fix MCI |
|---|---|---|
| evaluation.js:2553 | `func_call` args > 30 | arg-count cap (validation side has the disjunct) |
| evaluation.js:2985-2989 | filterBySearchCriteria array length / criteria count | caps (validation side has the disjunct) |
| validation.js:519 | search_param_list ops accounting | `count_ops += arrPairs.length` |
| evaluation.js:327 | min/max/hypot args > 30 | (previously enumerated by CHAIN-1) |

## No divergence / crash / state-corruption found

- **Cross-node divergence:** no — json_parse/json_stringify use deterministic parsers and the
  canonical serializer; Decimal config is process-global and pinned; no op's output depends on
  runtime state beyond the (deterministic) validation state.
- **Crash:** no new throw site reachable from attacker input (all throws pre-guarded or wrapped —
  the f5-R1 "evaluate guard" precedent extends to every site found).
- **State corruption:** no — these ops do not write state directly; state writes flow through the
  composer's `executeStateUpdateFormula`/`saveStateVars` (held by f5-R6: types/sizes validated
  before write; `+=`/`-=` require Decimal current values → error → bounce, no partial write).

## Real-path verification performed

Commands (all against the pinned tree, scratch sqlite, no network):
- `node lab-obyte.js /tmp/lr8b.js` → map-bounded ok; reduce-bounded = 6; reduce-exceed-count error;
  self-recursion error; stringify `{"a":1,"b":[1,2]}` (sorted keys)
- `node lab-obyte.js /tmp/lr8c.js` → Object.prototype CLEAN after `__proto__` JSON; nested-read ok;
  plain-read = 1
- `node lab-obyte.js /tmp/lr8-test.js` → json_parse-proto ok; json-roundtrip ok

## Files

- This report: `evidence/round3/LR-8.md`
- Probes (throwaway, in /tmp — not committed): lr8-test.js, lr8b.js, lr8c.js
- No changes to the pinned ocore tree (verified `git status` clean apart from the pre-existing
  lab-obyte.js symlink).

## Residual risks

- The `json_parse`-of-object-input → `true` quirk is deterministic but undocumented; could surprise
  AA authors (a logic bug in their formulas, not a consensus issue).
- The S1 eval-side bare-mci caps remain latent if a future path introduces below-fix evaluation
  (hardening item per KP-F2-link §residual-3).
- Deep-nesting JSON within 4096 chars: V8's JSON.parse is iterative (no stack overflow); the
  post-parse isTooBigObj bounds the object. Not exercised for pathological nesting depth within the
  cap; low residual.
