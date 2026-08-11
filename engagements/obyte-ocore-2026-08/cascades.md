# cascades.md — Q1/Q2 interrogation records (append-only)

## Cascade 1 — the S1 old-DAG family (opened from the disjunct-migration finding)
- **Q1 (siblings):** enumerated — validation.js:741 (non-AA parent), 986-992 (outer AA-trigger gate),
  1025-1028 (multi-trigger), formula/evaluation.js 10+ bare-mci eval gates (min/max/hypot, array/dict
  literals, signed-package cap, merkle sibling cap, search-param caps, isTooBigObj).
- **Q2 (root mechanism):** the root is "position-gated rules without the network-height disjunct".
  As a primitive: old-DAG attachment → validation-layer rule skip. **RESOLVED: the primitive is
  capped at the validation layer** — old-DAG-attached units cannot stabilize (witnessed level is
  ancestry-derived; best-parent sorts by it; MC walk starts from the tip; KP-F2-link Q1-Q4), so
  every EXECUTION-bearing effect (AA triggers, getters, dry-run) runs at a current position. The
  validation-layer skips affect only never-stabilizing junk units → no consensus or availability
  impact. **Q2 answer: the mechanism is not a primitive for anything beyond junk-DAG pollution.**

## Cascade 2 — the uncaught-throw pattern (opened from the crash family)
- **Q1 (siblings):** 4 sites found (1667/1686/2292/2451) — all refuted as reachable
  (address-binding; state machine; flow ordering). No sibling survives.
- **Q2 (root mechanism):** "throws in async completion callbacks escape to uncaughtException".
  As a primitive: any future reachable throw in these paths = network-wide crash-loop. **Q2 answer:
  a latent hardening class** — the 05f291d8 fix converted the light-path throw to a clean rejection;
  the full-node sites remain throw-based. Not exploitable today (states unreachable); the pattern
  should be converted to cb(err) as defense-in-depth. Recorded as a hardening note.

## Cascade 3 — private-payment double-spend protection (opened from F3)
- **Q1 (siblings):** the address-scoped uniqueness key is the only gap; the input-layer check
  exists but cannot run network-wide for private payloads (bPrivate only in the payload flow) —
  this is the defect's core. Payload-level binding (divisible_asset.js:159) is per-node.
- **Q2 (root mechanism):** "the unit-level check keys on a party-chosen string instead of the
  committed owner". As a primitive: any private-payment sender can place a permanent, undetected,
  unresolved duplicate-spend record. **Q2 answer: this IS the finding (F3)** — the root mechanism
  enables the race + ledger-integrity effects.

## Cascade 4 — tps-fee settlement (opened from F4)
- **Q1 (siblings):** getLocalTpsFee (estimation) uses the same exp() curve with a 10x multiplier —
  estimation can also explode, but it's bounded by the same funding gate (self-DoS only).
- **Q2 (root mechanism):** "settlement fee unbounded relative to author balance". As a primitive:
  any rate spike (attack or NATURAL — a natural 30-unit burst would freeze honest authors too!)
  poisons every author in the window. **Q2 answer: the natural-burst case is the strongest form** —
  the attack framing requires ~10.7% supply, but a NATURAL burst (e.g., a popular AA launch or
  exchange sweep) hitting count>=30 in a second would freeze every author settling in that window
  with NO attacker at all. The fee formula has no cap. This raises F4's honest severity framing:
  real-but-capped as an attack; a latent economic hazard as a natural occurrence.
