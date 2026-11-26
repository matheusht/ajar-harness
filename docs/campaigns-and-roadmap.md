# Ajar Campaigns, Rent Rule, & Roadmap (`v3.6-Balanced`)

This document explains why **Ajar v3.6-Balanced** replaced the legacy `v3.4` orchestration stack, defines the **Earned-Mass Rent Rule** used to keep or evict Ring-1 modules, and outlines the active campaign workflow and roadmap.

See [architecture.md](architecture.md) for the Three-Ring module map and [decisions/README.md](decisions/README.md) for archived `v3.4` decision records (`archive/v3.4-legacy`).

---

## 1. Why `v3.6-Balanced` Replaced `v3.4`

The legacy `v3.4` harness (`~45k` LoC, preserved at git tag `archive/v3.4-legacy`) accumulated heavy orchestration middleware that added worker friction without proportional `C3` yield. `v3.6-Balanced` applies two strict design rules:

1. **Zero Bureaucracy in the Inner Loop:** Workers read code, run commands, and iterate freely through `WorkspaceTools` (`agent.py`). Coordination happens via lock-free `.ajar/events.jsonl` -> `.ajar/WHITEBOARD.md`, never blocking state-machine locks.
2. **Earned-Mass Governance:** Ring 0 stays strictly `<= 1,800` SLOC (`cli.py`, `llm.py`, `agent.py`, `verify.py`). Every Ring-1 capability must justify its SLOC via local ablation (`--disable-<module>`) under the empirical rent rule in `src/ajar/bench.py`.

---

## 2. Local Phase-0 Probes & Empirical Rent Rule (`ajar bench`)

Paid benchmark runs never gate CI. Every commit runs `$0` deterministic checks (`pytest`, `extra/sz_ajar.py`, `tools/arch_lint.py`), and operators run local on-demand probes before spending inference budget:

```bash
python3 extra/sz_ajar.py .
ajar bench --phase0
```

### Phase-0 Deterministic Probes (`P0-A` .. `P0-D`)

- **`P0-A` (Polyglot Indexer):** Verifies `repomap.py` indexes Solidity sinks (`.call{`, `delegatecall`) and emits `.ajar/REALITY.md`.
- **`P0-B` (Sanitizer Autobuild):** Verifies `autobuild.py` synthesizes an executable `.ajar/build.sh` with ASan/UBSan flags and parallel build settings.
- **`P0-C` (5-Stage `C3` Anti-Stale Gate):** Compiles a real C target, proves `verify.py` rejects a stale/comment-only patch after mandatory post-patch rebuild, and mints `C3` for a genuine bounds fix.
- **`P0-D` (Effect/Wish Chain Join):** Verifies `chain_weaver.py` joins compatible `EffectType` + `CarrierKind` events posted to `.ajar/events.jsonl` while ignoring incompatible wishes.

### Leave-One-Out Rent Rule (`evaluate_rent_rule`)

A Ring-1 module earns `KEEP` (otherwise `EVICT`) via `ajar bench --disable-<module>` when:
- It delivers **at least one** measurable gain: `recall >= +5%`, `FP reduction >= +5%` (non-regressing recall), `chain_hops >= +0.5` (non-regressing recall), or `cost <= -15%` (non-regressing recall); **and**
- It satisfies all safety caps: `recall regression <= 1%`, `worker friction <= 5%`, and `loc_added <= 600` SLOC.

---

## 3. Campaign Tier Ladder & Operator Workflow

Validate every harness change bottom-up before running long multi-worker campaigns:

| Tier | Scope | Budget / Wall-Clock | Exit Criteria |
| --- | --- | --- | --- |
| **Tier 0: Local Structural & Phase-0** | Synthetic fixtures + unit suite | `$0` / `< 30s` | `scripts/verify-repo.sh --fast` + `ajar bench --phase0` green |
| **Tier 1: Focused Calibration** | Single parser, verifier, or contract (`5K–45K` LoC) | `$5–$15` / `< 90m` | `C3` reproduction in clean `git worktree` + positive Leave-One-Out rent lift |
| **Tier 2: Multi-Subsystem Targets** | State machines, gateways, storage engines (`50K–300K` LoC) | `$25–$50` / `2h–6h` | Full forward/backward pincer in `.ajar/REALITY.md`, clean `45m` pivot, `92%` drain to `C3` |
| **Tier 3: Deep Multi-Hop Campaigns** | Toolchains, runtimes, monorepos (`300K+` LoC) | `$50+` / `6h+` | Multi-hop `EffectType`/`WISH` chains verified end-to-end to `C3` and `100/100` voice-linted advisories |

### Canonical Operator Flow

```bash
# 1. Confirm harness integrity and Phase-0 deterministic probes
python3 extra/sz_ajar.py .
ajar bench --phase0

# 2. Run the 8-worker autonomous swarm (45m pivot, 65%/70% relay, 92% drain)
ajar run <repo> --workers 8 --budget-usd 50 --hours 6 --profile upstream

# 3. Re-run or inspect 5-stage mechanical C3 verification for candidates
ajar verify <repo> --runs 3 --profile upstream

# 4. Export voice-linted C3 advisories and hardening notes
ajar report <repo> --out ./reports
```

---

## 4. Active Engineering Roadmap (`v3.6+`)

1. **Empirical Ring-1 Ablation Sweeps:** Measure Leave-One-Out lift across all 7 `--disable-*` flags on Tier 1 and Tier 2 benchmarks and evict or simplify any muscle that fails `evaluate_rent_rule`.
2. **Deeper Polyglot Build Profiles:** Expand `autobuild.py` recipes and Build Doctor heuristics across C/C++ (`CMake`, `Meson`, `Autotools`), Rust (`cargo`), Go, Foundry, and OSS-Fuzz targets while keeping `.ajar/build.sh` fast and hermetic.
3. **End-to-End Multi-Hop Chain Synthesis:** Improve `chain_weaver.py` `EffectType` / `CarrierKind` joins and `Input Encoder` payload generation so multi-step chains consistently clear 5-stage `C3` verification.
4. **Zero-Friction Maintainer Deliverables:** Keep `ajar report` + `skills/security-advisory-report/scripts/report_voice_lint.py` locked at `100/100` mechanical voice hygiene with zero internal jargon or host paths.
