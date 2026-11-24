# Ajar Agent Instructions (v3.5)

Ajar (built by Ajar Labs) is a first-principles autonomous security engine (`< 1,500` LoC stdlib implementation; `<= 1,800` LoC permanent ceiling).
Your product is causal proof in a clean worktree, not plausible prose. Every finding must survive clean-room Red/Green reproduction, Wrong-Bug Trace Guard, and the `4x3` Diagonal Kill Matrix.

## Core 8-Verb Workflow (`reality -> microfuzz / explore -> chain -> prove -> critique -> report`)

1. **Adaptive Reality (`ajar reality <repo> --profiles upstream,debian`):** Synthesize `<repo>/.ajar/REALITY.md` (with or without `SECURITY.md`), map comment-stripped entrypoints and Crown-Jewel sinks (`D6`), and load the 5 Cross-Seam Lenses (`L1_PARSER_DIFFERENTIAL`, `L2_POLICY_ALIAS_GAP`, `L3_WRAPPER_ENGINE_SEAM`, `L4_MID_OP_RESIDUE`, `L5_LIFETIME_ARENA_SEAM`).
2. **Unshackled Exploration & Micro-Fuzzing (`ajar microfuzz <repo> --entrypoint ...`):** Explore directly with `bash`/`rg` and run in-slot boundary + stateful `microfuzz`; promote ONLY crashes that replay through the real public entrypoint in a clean worktree.
3. **Stigmergic Chaining (`ajar chain <repo>`):** Post `CAN` and `WISH` primitives to `.ajar/primitives.jsonl`, bridge them via normal product features, and prove single-script end-to-end chains in a clean worktree.
4. **Deterministic Proof (`ajar prove <repo> --finding-json <path> [--test-cmd ...] [--concurrency-mode deterministic|statistical]`):** Verify Red repro on clean `HEAD`, claimed sink symbol match (Wrong-Bug Trap), minimal patch Green replay, and `D5` concurrency gates.
5. **Adversarial Critique (`ajar critique <repo> --finding-json <path> [--critic-cmd ...]`):** Enforce the `4x3` Diagonal Kill Matrix (`reachability:static_code`, `controllability:clean_replay`, `boundary_validity:shipped_profile`, `impact_and_patch:clean_replay`) and Cross-Family Critic disproof.
6. **Campaign Sentinel (`ajar campaign <repo> --workers 8 --budget-usd 100`):** Coordinate up to 8 flat-file workers with `45m` physical-signal pivots (`D3`), `65%/70%` compaction relays (`D4`), and `< 35%` COGS guard.
7. **Reports & Local Bench (`ajar report <repo> --out <dir>`, `ajar bench --check-loc`):** Split `advisories/` vs. `hardening-notes/` (`D7`), omit withdrawn drafts (`DEC-0139`), enforce 100/100 engineering voice lint, and run `ajar bench` locally on demand (`0` CI gates).

## Non-Negotiable Boundaries

1. **Zero-LLM Core & LoC Ceiling:** `src/ajar/` stays pure Python stdlib (`<= 1,800` LoC). Legacy v3.4 code is preserved at tag `archive/v3.4-legacy`.
2. **Hermetic Clean-Room Isolation:** All verification runs inside disposable git worktrees with fail-closed network isolation (`D6`) and locked build profiles (`D2`: `upstream`, `debian`, `al2023`).
3. **Secret & Path Hygiene:** Never commit credentials, tokens, PII, `.ajar/` run artifacts, or developer home paths.
4. **External Action Gate:** Never submit external advisories, contact vendors, or publish findings without explicit operator approval.
