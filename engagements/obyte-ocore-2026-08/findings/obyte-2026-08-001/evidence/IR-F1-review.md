# IR-F1 — independent review of the P9 merkle PoC (`is_valid_merkle_proof` vacuously satisfiable)

**Reviewer:** independent (fresh context). **PoC under review:** `evidence/p9-poc.js`
(builder report `evidence/p9-builder.md`). **Date:** 2026-08-11.

## Execution

```
cd /Users/matheusvsky/Documents/trab/obyte-ocore-2026-08-ocore
node lab-obyte.js /Users/matheusvsky/Documents/trab/llm-redteam-harness/engagements/obyte-ocore-2026-08/evidence/lab/p9/p9-poc.js
```

Environment pre-checks:
- Tree at pinned commit `a7eb776afc68ed4bed05ba554f7f1e95f5d49b44` (`git log -1`), clean except the
  untracked lab symlink `lab-obyte.js` (pre-existing, points at `evidence/lab/lab.js`). No local
  modifications to `merkle.js`, `formula/*`, or `definition.js`.
- Lab harness (`evidence/lab/lab.js`) boots the real ocore modules in-process, redirects
  `desktop_app.getAppDataDir` to a fresh scratch dir, zeroes the upgrade MCIs, and hands the script
  the real `db/storage/validation/objectHash/signature/composer/mutex/constants`. It patches no
  formula/merkle/definition code.
- PoC script restores `constants.pemCurvesFixMci = 12155000` (mainnet value, constants.js:101) after
  the lab zeroes it, so the S1 boundary test uses the real mainnet boundary. Documented in the script.

## Raw output (verbatim, from the run)

`P9-RESULTS` block (abridged to the load-bearing fields):

| row | raw result |
|---|---|
| vacuous:"not-in-any-tree-1" | `{"err":null,"res":true}` |
| vacuous:"hello world" | `{"err":null,"res":true}` |
| vacuous:"h9jB+6N0vn11s7b2DMVTng==" (random base64) | `{"err":null,"res":true}` |
| vacuous:"user-supplied element 42" | `{"err":null,"res":true}` |
| positive-control-real-tree-proof | `{"err":null,"res":true}` |
| negative-control-wrong-root | `{"err":null,"res":false}` |
| sixty-siblings-above-fix (mci=15,000,000) | `{"err":null,"res":false}` |
| sixty-siblings-below-fix (mci=1,000,000) | `{"err":null,"res":true}` |
| in-merkle-vacuous-proof-no-feed | `{"err":null,"res":false}` |
| in-merkle-real-tree-root-no-feed | `{"err":"bad merkle proof at path r.1"}` |

The `in merkle` rows also produced the real-DB feed log
`data feed by 3Y24IXW57546PQAPQ2SXYEPEDNX4KC6Y merkle_feed=<root>: false, 0 / 0 records inspected`
and `null, df took 2ms` — the definition predicate ran a real `dataFeedExists` query against the
fresh scratch SQLite (no feed posted → false).

## Required verifications (per BRIEFS.md)

1. **All 4 vacuous rows true — PASS.** 4/4 rows `res:true` with arbitrary elements
   (`not-in-any-tree-1`, `hello world`, random base64, `user-supplied element 42`), proof
   `"0-" + base64(sha256(X))`, no tree membership anywhere.
2. **Positive control true — PASS.** A real 5-element tree proof for `"c"`
   (`merkle.getMerkleProof(["a".."e"], 2)` serialized) evaluates `true` — engine not broken.
3. **Negative control false — PASS.** Root ≠ hash(element) → `false` (self-consistency check only).
4. **60-sibling above-fix false / below-fix true — PASS.** Crafted 60-sibling proof with
   attacker-computed root: `false` at mci=15,000,000 (≥ 12,155,000), `true` at mci=1,000,000
   (< 12,155,000).
5. **`in merkle` contrast false — PASS.** The same vacuous proof rejected by the definition
   predicate (row 9 `res:false`; row 10 rejected with fatal error). The contrast claim — the
   construct that binds the root to an on-chain posted feed rejects the self-consistent proof —
   holds.

## Reward-hacking audit

- **No mocks / no fake clients / no reimplementations.** The script requires the real
  `formula/index.js` (whose `evaluate` is the exact export used by `aa_composer.js` at
  602/631/674/716/754/780/812/1446 and by `definition.js:14`), the real `merkle.js`, the real
  `definition.js` `validateAuthentifiers`, and real `secp256k1` for the signature branch. The
  `in merkle` branch executed a real `dataFeeds.dataFeedExists` SQL query against the lab's scratch
  SQLite (visible in the log).
- **No hardcoded expectations.** The script prints raw engine callbacks; there is no assertion table,
  no post-hoc boolean rewriting, no comparison against expected values.
- **Only environment mutation:** restoring `pemCurvesFixMci` to its mainnet value (the lab zeroes it);
  necessary and sufficient to test the S1 boundary. No monkey-patching of engine code (verified via
  clean `git status` at the pin).
- **Independent cross-check (fresh construction, not PoC code):** I built my own element/proofs and
  drove the same real engine directly:
  - vacuous self-consistency proof (my element `independent-reviewer-element-2026`) → `true`
  - 60-sibling crafted proof above fix (mci=15M) → `false`
  - 60-sibling crafted proof below fix (mci=1M) → `true`
  - wrong-root negative control → `false`

## Source verification (file:line)

- `formula/evaluation.js:79` — `var mci = objValidationState.last_ball_mci;` (evaluation mci comes
  from the validation state).
- `formula/evaluation.js:1763` — `case 'is_valid_merkle_proof':`; `:1781` proof length cap 1024;
  `:1787-1791` — the sibling cap:
  `if (mci >= constants.pemCurvesFixMci) { if (!Array.isArray(objProof.siblings) || !objProof.siblings.every(ValidationUtils.isNonemptyString)) return cb(false); if (objProof.siblings.length > 50) return cb(false); }`.
  No `!hasBall && getMinRetrievableMci()` disjunct: `getMinRetrievableMci` occurs **0 times** in
  `evaluation.js` (grep-verified). The gate is bare-mci, as the builder claims.
- `merkle.js:84-98` — `verifyMerkleProof`: with `index=0`, `siblings=[]` (the vacuous proof),
  `:97` reduces to `hash(element) === proof.root` — root is attacker-chosen from the proof itself.
  `merkle.js:75-78` `deserializeMerkleProof` splits on `-`, so the "0-" prefix yields `index="0"`.
- `definition.js:1004` — `case 'in merkle':`; `:1020` —
  `dataFeeds.dataFeedExists(arrAddresses, feed_name, '=', proof.root, ...)` — the sound pattern binds
  the root to an on-chain posted feed value; absent a feed, the predicate is false. Contrast confirmed
  empirically.
- `constants.js:101` — mainnet `pemCurvesFixMci = 12155000` (matches the PoC's restored value and the
  FIX/BELOW test MCI choices).

## Verdict

**CONFIRMED.** The PoC's raw output reproduces the builder's table exactly; my independent
fresh-context cross-check reproduces the mechanism. No reward hacking found. Verdict JSON:

```json
{
  "id": "IR-F1",
  "verdict": "confirmed",
  "evidence": "P9-RESULTS raw block: 4/4 vacuous rows res:true; positive-control real tree proof res:true; negative-control wrong-root res:false; 60-sibling above-fix(15M) res:false / below-fix(1M) res:true; in-merkle vacuous-proof res:false with real dataFeedExists '0 / 0 records inspected'. Independent cross-check reproduced vacuous=true, 60-above=false, 60-below=true, wrong-root=false with independently constructed proofs on the real engine.",
  "raw_output_ref": "engagements/obyte-ocore-2026-08/evidence/round2/IR-F1.md §Raw output (run: cd obyte-ocore-2026-08-ocore && node lab-obyte.js <abs>/evidence/lab/p9/p9-poc.js)"
}
```

## Residual risks / notes

- **S1 reachability is NOT settled by this PoC.** The below-fix row simulates a node whose
  `last_ball_mci` is 1,000,000. Whether an old-DAG-attached unit's evaluation actually runs with
  `last_ball_mci < 12155000` on a synced node (or only on behind/fresh nodes / a no-ball window) is
  the S1-link question owned by `KP-F2-link` (main_chain.js / aa_composer trigger path). The builder's
  gloss "Old-DAG-attached units skip the cap" overstates what the eval-side measurement alone proves;
  the measurement proves the gate is bare-mci, not the live-node reachability.
- **Impact conditional.** The footgun matters only if an AA formula uses `is_valid_merkle_proof` as a
  membership/authorization gate without pinning the root. Individual AA logic is out of scope; the
  engine-level defect is what is confirmed (in-scope SF-9/SF-10 engine). Severity stays
  info/medium, usage-capped.
- **PoC drives the engine directly** with a synthesized `objValidationState` of the same shape the AA
  path builds (aa_composer.js:442+); no end-to-end AA unit was executed. Appropriate level for an
  opcode-semantics finding; full-chain proof would be an AA-usage demonstration, out of this brief.
- **Row 10 nuance:** `in-merkle-real-tree-root-no-feed` fails at `verifyMerkleProof` (element
  `merkled-element-1` is not a leaf of the `["a".."e"]` tree), i.e. a different failure mode than the
  builder's prose implies ("real tree root, still no feed"). The observable rejection is real and the
  required contrast row 9 is clean; flagging only for precision.
- **Side effect:** my bare `node -e` cross-check (outside the lab harness) caused the library boot to
  create an empty local sqlite at `~/Library/Application Support/ocore/` (default desktop_app dir —
  the harness normally redirects to the scratch dir). Local-only, empty, no secrets. Flagged for the
  engagement cleanup ledger.
