# program-policy.md — Google OSS VRP rules for `angular/angular-cli` (captured 2026-08-14)

> **Source-quality warning, stated once and binding.** `bughunters.google.com` is a JS SPA and
> returns an empty shell to a fetcher; the Wayback captures are the same shell. **The tier
> assignment below is primary-verified from a machine-readable file. The reward amounts are
> corroborated from secondary sources and are NOT primary-fetch-verified.** Re-verify at
> `bughunters.google.com/open-source-security` before the operator files.

## 1. Tier — primary-verified

`https://github.com/angular/angular-cli` → **`TIER_OT0`**, `product_vuln_scope: SCOPE_OSS_VRP`.

Source: `github.com/google/bughunters` → `oss-repository-tier/external_repositories.txtpb`, fetched
**2026-08-14**. That file now holds **73 tiered repositories (26 OT0, 47 OT1)**.

**Freshness note:** the same file held 71 (26 OT0, 45 OT1) when `angular-dev-infra-2026-08` fetched
it on 2026-08-12. Two OT1 repositories were added in two days. The roster is live — re-fetch it at
Round 0 rather than trusting this line, and record any change.

Four Angular repositories are OT0: `angular/angular`, `angular/angular-cli`, `angular/components`,
`angular/dev-infra`. OT0 is the flagship tier.

Full roster and portfolio coverage: `docs/research/oss-vrp-tier-coverage.md`.

## 2. Reward categories

| Category | OT0 band | What it covers |
|---|---|---|
| **Supply-Chain Compromise** | up to **$31,337** | compromise of the build, release, publish or distribution path — anything that lets an attacker place code into a shipped artifact |
| **Product Vulnerability** | **$500 – $7,500** | design or implementation logic defects in the software itself |
| Other | varies | reported at Google's discretion |

**The SCC ceiling is roughly 4× the top PV band.** Route accordingly: the release and CI surfaces are
worth more than library logic, per identical effort.

## 3. The post-March-2026 memory-safety gate

For OT0 and OT1, a memory-corruption report pays only with **an exact OSS-Fuzz reproduction via an
existing fuzz target, or a merged upstream patch.** This repository is TypeScript, so the class is
largely inapplicable — the operative consequence is: **do not pivot a logic candidate onto a
memory-safety framing** hoping for a higher band. It will be rejected at intake.

## 4. Scope rules that decide candidates

- **Current-version requirement.** A finding must be unfixed at the current released tag.
  Stale-version-only findings are rejected. Pin, then confirm, before deep work.
- **Third-party root cause goes upstream first.** If the defect lives in a dependency, it is that
  project's report, not an OSS VRP one — unless the vulnerability is in *how this repository uses*
  the dependency.
- **Designed behaviour is not a vulnerability.** `ng add` and `ng update` execute third-party package
  code by design. A report must show a boundary crossed that the design does not intend.

## 5. Process

- Reports are filed by the operator at `bughunters.google.com/report`.
- **AI is barred from filing, from contacting maintainers, and from opening any issue or PR.**
- Google runs its own triage and assigns the final category and amount. Our severity is an input,
  not a verdict — record what we claimed and what they assigned in
  `engagements/angular-cli-2026-08/dispositions.jsonl` when it comes back.

## 6. Prohibited

- Any testing against live Google, Angular, or npm infrastructure.
- Any interaction with the real npm registry or the real GitHub API using this engagement's work.
- Social engineering of maintainers.
- Public disclosure ahead of Google's process.
