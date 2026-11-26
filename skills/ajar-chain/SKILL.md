---
name: ajar-chain
description: Compose multi-hop exploit chains in Ajar v3.6 using chain_weaver.py 12-type EffectType ontology, CarrierKind compatibility, backward WISH abduction, and end-to-end C3 verification.
---

# Ajar Chain (`v3.6-Balanced`)

Use this skill to compose partial primitives and blocked Crown-Jewel sinks into end-to-end multi-hop candidates via `src/ajar/chain_weaver.py` and `.ajar/WHITEBOARD.md`.

## 1. The 12-Type `EffectType` & 6-Type `CarrierKind` Ontology

Record every partial primitive as an `effect` event and every blocked Crown-Jewel sink as a `wish` event in `.ajar/events.jsonl` (`whiteboard.py`) using the exact `chain_weaver.py` enums:

**`EffectType` (12 types):**
- `parser_offset_disagreement`, `buffer_geometry_mismatch`, `lifetime_escape`
- `residual_error_state`, `uninitialized_or_sentinel_propagation`, `policy_alias_divergence`
- `cross_session_key_reuse`, `reentrant_callback_window`, `accounting_rounding_delta`
- `stale_cache_or_oracle_read`, `privilege_or_capability_smuggling`, `schema_or_encoding_malleability`

**`CarrierKind` (6 carriers):**
- `call_arg_return`, `shared_struct_field`, `persistent_or_cache_store`
- `wire_or_container_frame`, `callback_or_async_yield`, `cross_contract_or_ipc_call`

Consult `skills/references/project-zero-zdi-chain-corpus.md` and `skills/references/defi-exploit-chain-corpus.md` for verified multi-hop handoff shapes.

## 2. Backward `WISH` Abduction & Deterministic Join (`chain_weaver.py`)

1. **Post Forward Effects (`post_effect`):** Whenever a worker finds a low/medium quirk, state nudge, offset drift, or callback window that does not reach a Crown Jewel alone, post an `effect` with its `EffectType`, `CarrierKind`, and observed `span`.
2. **Post Backward Wishes (`post_wish`):** Whenever a worker finds a high-impact sink blocked by an upstream invariant, post a `wish` with the `desired_effect` (`EffectType`), `CarrierKind`, `sink_span`, and `impact`.
3. **Deterministic Join (`join_effects_and_wishes`):** `chain_weaver.py` automatically joins posted `effect` and `wish` records whose types and carriers match `EFFECT_COMPAT` and `CARRIER_COMPAT` without burning LLM tokens on incompatible pairs.
4. **LLM Chain Weaving (`weave_candidates`):** When compatible joins appear (and `--disable-chain-weaver` is not set), the `weaver` role synthesizes concrete multi-hop `Candidate` objects populating `chain_hops` (`[hop1_span, hop2_span, ...]`), end-to-end `repro_cmd`, `failure_oracle`, and root-cause `patch_diff`.

## 3. Six High-Yield Chain Shapes

1. **Parser Offset / Schema Malleability -> Policy Alias or Buffer Mismatch:** Desynchronize validation vs execution parsing across wire frames or container layers.
2. **Reentrant Callback -> Stale Cache/Oracle or Accounting Delta:** Re-enter before state settlement so a downstream check reads stale balances or exchange ratios.
3. **Residual Error / Sentinel Propagation -> Capability Smuggling:** Trigger a partial-failure path that leaves a stale flag, zero handle, or default role active on retry.
4. **Cross-Session Key Reuse -> Stale Oracle or Auth Bypass:** Replay or collide cached tickets/nonces across virtual hosts or tenants.
5. **Peer-Route Asymmetry:** Enter state through a permissive sibling route or callback that skips an invariant enforced on the primary path.
6. **Shared-Chokepoint Widening:** Trace a flawed helper or deserializer to its highest-impact caller instead of stopping at a low-severity symptom.

## 4. End-to-End `C3` Proof Rule

Never inflate severity on hypothetical chaining. A multi-hop chain is valid only when:
- Every hop in `chain_hops` is causally necessary and grounded in observed spans (`SpanTracker`).
- One self-contained `repro_cmd` executes the entire chain end-to-end against the real target.
- A minimal `patch_diff` breaking the root invariant eliminates the end-to-end failure across all 5 stages of `ajar verify <repo> --candidate-id <id> --runs 3`.
