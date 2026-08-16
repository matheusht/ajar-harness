# P9 PoC — is_valid_merkle_proof vacuously satisfiable

Run (one command, from the pinned ocore tree):

```
cd /Users/matheusvsky/Documents/trab/obyte-ocore-2026-08-ocore
node lab-obyte.js /Users/matheusvsky/Documents/trab/llm-redteam-harness/engagements/obyte-ocore-2026-08/evidence/lab/p9/p9-poc.js
```

Read the `P9-RESULTS` block:

- **vacuous:* rows → `res: true`** for arbitrary elements with NO tree membership. This is the flaw:
  `is_valid_merkle_proof(X, "0-" + sha256_base64(X))` accepts any X because the proof root is
  attacker-chosen and never bound to a committed merkle tree.
- **positive-control-real-tree-proof → `true`** — the engine works for legitimate proofs (not broken).
- **negative-control-wrong-root → `false`** — it checks self-consistency only, not always-true.
- **sixty-siblings-above-fix → `false`**, **sixty-siblings-below-fix → `true`** — the sibling cap
  (e01ba3e) is position-gated without the S1 disjunct: units attached below `pemCurvesFixMci` skip
  the cap and a crafted 60-sibling proof with an attacker-computed root passes.
- **in-merkle-* → `false`** — the DEFINITION-language `in merkle` predicate requires the proof root to
  equal an on-chain posted data-feed value; the same vacuous proof fails there. That is the sound
  pattern; the formula construct lacks the commitment step.

Interpretation: any AA that uses `is_valid_merkle_proof` for a membership/whitelist/authorization gate
without separately pinning the root is bypassable — the predicate is vacuously satisfiable.
