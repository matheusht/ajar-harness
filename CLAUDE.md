# Ajar Agent Instructions

Ajar (built by Ajar Labs) is a verification-backed security engine for `Platform`, `Code`, `Fixes`, `Security reviews`, and `Supply chain`.
Your product is causal proof, not plausible prose. A claim becomes a confirmed finding only when all reproduction arms and causal locus alignment pass (`ajar claim reproduce`).

## Route Selection

- **Security run (`source`, `binary`, or `live`):** Follow the canonical workflow below and load the step skill under `skills/ajar-*/SKILL.md`.
- **Repository engineering on Ajar itself:** Read `docs/engineering/AGENTS.md`, `docs/architecture.md`, and `docs/decisions/README.md`.

## Canonical Workflow (`map -> investigate -> falsify -> reproduce -> converge -> fix`)

1. **Quote and initialize:** Preview scope and the `35%` COGS cap (`ajar quote`), then initialize `~/.ajar/runs/<run_id>/run.db` (`ajar init [--stopping exhaustive-high|first-high|crown-jewel] [--phase hunt|remediate] [--diff <base..head>] [--brief-file <md>] [--uncapped]`, `ajar door jewel-add`, `ajar steer add`, `ajar status`).
2. **Map and threat-model (`skills/ajar-map/SKILL.md`):** Run `ajar map --budget-tokens 1500 --slice-cap 15000`, query `ajar ref query --kind intent|reachability`, synthesize the adaptive threat model (`ajar threat-model set`, `assumption-add`), register surfaces (`--requires-tags`), and enqueue `investigate` tasks across `outside_in`, `inside_out`, `native_ffi`, and `peer_symmetry`.
3. **Investigate (`skills/ajar-investigate/SKILL.md`):** Lease work (`ajar task lease --worker <id> --recover`) and load prefix-stable context (`ajar context --task <id>`).
   - Obey `Active Workspace Steers` and any triggered `Active Epistemic Hooks` (including each hook's `Kill Rule`). When `skill_mode=zero_skill`, derive invariants from target code and do **not** open `skills/domains/*`.
   - When `skill_mode=domain`, open only the matching pack in `skills/domains/{evm-solidity,consensus-vm,rust-systems,web-api,auth-crypto}/SKILL.md`.
   - Persist bindings (`ajar binding set`), coverage (`ajar coverage record`), anomalies (`ajar anomaly add`), capabilities/gadgets (`ajar primitive add --role capability|trust_gadget --guarded-by <locus> --provides-tags <tags>`, `ajar primitive dry`), and suspended Open Doors (`ajar door park`). Never close `dry` while an inner primitive remains guarded by an untested assumption.
   - Propose claims (`ajar claim propose`) with concrete state reachability, `--falsification-prediction`, and `--falsification-test`.
4. **Falsify or Rescope (`skills/ajar-falsify/SKILL.md`):** Challenge every claim from an independent worker (`falsifier != proposer`) via `ajar claim falsify [--config-gate <pred>]`, `ajar claim rescope`, or `ajar claim survive`.
5. **Reproduce (`skills/ajar-reproduce/SKILL.md`):** Smoke-test strike-free via `ajar repro try`, then prove causal path and impact via `ajar claim reproduce` (`--build-cmd`, `--save-post-state`, 4 arms + `claim.locus` overlap + `--release-cmd` when `H6` fires). After two unchanged target negatives, run `ajar claim instrument`.
6. **Converge and Fix (`skills/ajar-chain/SKILL.md`, `skills/ajar-patch/SKILL.md`):** Inspect percolated paths and 1-link gaps (`ajar chain frontier`, `ajar door list`), probe post-states (`ajar chain probe --from-snapshot`), prove ablated multi-hop chains (`ajar chain propose`), calibrate realism (`ajar finding calibrate`), and advance to `remediate` (`ajar phase advance --to remediate`) before 9-arm `Fixes` (`ajar patch verify`).
7. **Close Out (`skills/ajar-report/SKILL.md`):** Verify SQL gates `G1–G5` (`ajar gate check`), export the `Platform` graph (`ajar export-graph`), seal the run (`ajar finish`), and emit reports (`ajar report`).

## Non-Negotiable Boundaries

1. **Scope gate:** Never issue live network requests or mutations unless `scope_rules` explicitly authorizes the target host (`--allow-live-requests`, `--allow-host`).
2. **Secret redaction:** Never write credentials, API keys, JWTs, session cookies, private keys, or signed URLs to files, logs, or commits.
3. **Target cleanliness:** Never commit `.ajar/` artifacts into a target repository; keep run state in `~/.ajar/runs/<run_id>/`.
4. **External action gate:** Filing advisories, contacting vendors, deploying patches, or publishing reports requires explicit operator authorization.
