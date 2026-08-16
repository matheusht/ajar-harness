# Orchestrator verifications during round E1 (2026-08-11)

Independent source traces + adjudication aids for the E1 escalation lanes.

## OV-1 — E1-1 fee-accounting: REFUTED (conservation + recipient override)
- The declared tps_fee is part of the balance closure: `total_input === total_output + hc +
  payload_commission + oversize_fee + tps_fee + burn_fee + vote_count_fee`
  (validation.js:2654-2656) — the declared fee is consumed from the inputs (burned at save).
- Settlement applies only the delta `(declared - final)` to the RECIPIENTS' tps_fees_balances
  (storage.js:1246-1261).
- `getTpsFeeRecipients` (storage.js:1458-1465) OVERRIDES the recipient set to the author (100%)
  whenever any named recipient is not an author ("non-authors won't pay for our tps fee") — a
  named-victim drain is structurally blocked.
- Conservation: author pays declared (burned) + absorbs (final - declared) via the balance delta →
  net cost = final. No money creation, no double-credit, no targeting. F4 stays per-author scatter.

## OV-2 — E1-15 reorg corner: CLOSED (state machine holds under reorgs)
- `goDownAndUpdateMainChainIndex` sets `main_chain_index=NULL` for all units above the retreat
  point (SQL + in-memory) — a temp-bad unit loses its index on retreat.
- The re-advance re-indexes from the retreat point upward (new indices > the balled retreat index);
  stabilization (which resolves temp-bad → good/final-bad) is atomic with ball creation.
- A temp-bad unit can therefore never hold `main_chain_index <= last_ball_mci` at a balled MCI,
  even across reorgs → the 1686/2451 throws stay unreachable. The crash family remains dead.

## OV-3 — E1-13 ghost-in-fee-window: edge is REAL but marginal contribution ≈ 0
- F3's ghost units are 'good' MC-path units (LR-2: MC indices 1 and 2) — they DO count in
  getFinalTps's window count (stable MC units between last_ball_mci and mci, storage.js:1178-1218).
  CHAIN-1's "fork units are off-MC" bound was wrong for the descendant-ghost construction.
- BUT the attacker pays the same escalating fees on ghost units as on normal flood units — the
  F3→F4 composition adds no economic leverage over F4 alone (same self-limiting funding bound).
  The composition is real (F3's units can drive F4's window) but the marginal contribution is ~0.

## OV-4 — E1-5 parent_composer throw: reachable via HN-5 inflation (new chain)
- `filterParentsByTpsFeeAndReplace` (parent_composer.js:~461) throws "all potential parents underpay
  the tps fee" when every candidate parent's paid fee is below `min_parentable_tps_fee`.
- HN-5's future-timestamp units inflate `getRecentTps` → `min_acceptable_tps_fee_multiplier` → the
  local fee estimate → `min_parentable_tps_fee` rises above historical parents' paid fees → the
  victim wallet's composition path throws.
- Impact: wallet composition crash (client DoS) + the HN-5 fee inflation. Whether the throw is
  caught upstream (failed composition vs crash) is E1-5's question. Wallet-layer, below the
  program floor likely — record as a hardening/chain note.

## OV-5 — E1-13/E1-3 note: the F1→AA-funds chain is the strongest composition
- F1's vacuous merkle proof + any AA gating on it = fund movement (E1-3 demonstrates). The engine
  defect is the root; the AA is the payload. Cap: individual AA logic out of scope; the engine
  finding (F1) already captures the root.
