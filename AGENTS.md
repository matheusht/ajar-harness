# Ajar Agent Instructions

Ajar is a verification-backed security engine for `Code`, `Fixes`, `Security reviews`, and `Supply chain`.
Your product is causal proof, not plausible prose. A claim becomes a confirmed finding only when all four reproduction arms pass (`ajar claim reproduce`).

## Route Selection

- **Security run (`source`, `binary`, or `live`):** Follow the canonical workflow below and load the step skill under `skills/ajar-*/SKILL.md`.
- **Repository engineering on Ajar itself:** Read `docs/engineering/AGENTS.md`, `docs/architecture.md`, and `docs/decisions/0017-ajar-v3-dual-mode-architecture.md`.

## Canonical Workflow (`investigate -> falsify -> reproduce -> fix`)

1. **Initialize or inspect state:** Store all run data outside the target repository in `~/.ajar/runs/<run_id>/run.db` (`ajar init`, `ajar status`, `ajar doctor`).
2. **Map surfaces (`skills/ajar-map/SKILL.md`):** Run `ajar map --budget-tokens 1500`, query `ajar ref query --kind intent|reachability`, register entrypoints (`ajar surface add`, `ajar driver add`), and enqueue `investigate` tasks (`ajar task add`).
3. **Investigate (`skills/ajar-investigate/SKILL.md`):** Lease work (`ajar task lease --worker <id> --recover`) and load `ajar context --task <id>`.
   - When `skill_mode=zero_skill`, analyze target code from first principles and do **not** open `skills/domains/*`.
   - When `skill_mode=domain`, open only the matching pack in `skills/domains/{evm-solidity,consensus-vm,rust-systems,web-api,auth-crypto}/SKILL.md` and exit immediately with `ajar task dry` when a concrete upstream guard holds.
   - Persist verified constants (`ajar binding set`), unexpected behaviors (`ajar anomaly add`), and composable capabilities (`ajar primitive add`).
   - Propose claims (`ajar claim propose`) only with concrete state reachability, `--falsification-prediction`, and `--falsification-test`.
4. **Falsify (`skills/ajar-falsify/SKILL.md`):** Challenge every proposed claim from an independent worker identity (`falsifier != proposer`) against upstream guards and `skills/references/{false-positive-controls-corpus,rejected-disputed-cve-corpus}.md` (`ajar claim falsify` or `ajar claim survive`).
5. **Reproduce (`skills/ajar-reproduce/SKILL.md`):** Run `ajar claim reproduce` across all four arms (Arm 1: clean + PoC fires; Arm 2: clean + control passes; Arm 3: minimal root-cause fix + PoC blocks; Arm 4: minimal fix + control passes). After two unchanged reproduction failures, stop guessing and instrument the target (`needs_instrumentation`).
6. **Chain and Fix (`skills/ajar-chain/SKILL.md`, `skills/ajar-patch/SKILL.md`):** Compose multi-step exploit paths (`ajar chain propose`) and upgrade verified micro-patches into idiom-preserving remediations tested against `>= 3` bypass variants.
7. **Close Out (`skills/ajar-report/SKILL.md`):** Verify deterministic SQL gates `G1–G5` (`ajar gate check`), seal the run (`ajar finish`), and emit calibrated deliverables (`ajar report`).

## Non-Negotiable Boundaries

1. **Scope gate:** Never issue live network requests or mutations unless `scope_rules` explicitly authorizes the target host (`--allow-live-requests`, `--allow-host`).
2. **Secret redaction:** Never write credentials, API keys, JWTs, session cookies, private keys, or signed URLs to files, logs, or commits.
3. **Target cleanliness:** Never commit `.ajar/` artifacts into a target repository; keep run state in `~/.ajar/runs/<run_id>/`.
4. **External action gate:** Filing advisories, contacting vendors, deploying patches, or publishing reports requires explicit operator authorization.
