I have the scope/policy context. Producing the wire-2 spec:

## WIRE-2 SPEC — Chain 2 CI sabotage: private-fork Actions demo (operator-gated)

### 0. Wire declaration (per `scope.md` §9)

This act trips **wire 2** ("Reaches a third party — any GitHub Actions run, even in the operator's own private fork"). It requires **one fresh operator confirmation at the moment of the act**, naming the fork, the workflow, and the cleanup path. Nothing in this spec authorizes the run; it defines what a granted confirm would cover. `zone2_containment` permits "a private throwaway fork the operator controls… a private-fork Actions run requires a fresh operator confirm at the wire" — the fork, the workflow, and the payload below all sit inside that stated envelope. The run is **not** needed to establish the base findings (all seven are gate-CLEAR on in-lab PoCs); it closes the Chain-2 *runner-semantics* rung and gives the filing bundle a full-build E2E.

### 1. Test repo layout (private, operator-owned, throwaway)

`<operator>/chain2-cisabot/` (private — never public; never under the angular org):

```
chain2-cisabot/
├── .github/workflows/ci-sabot.yml     # the demo workflow
├── angular.json                        # benign base config (the PR will not modify it)
├── package.json                        # deps: @angular/cli@18.2.20 pinned (or the engagement pin d827ba9005-equivalent release)
├── src/                                # minimal app: index.html, main.ts, styles.css
│   ├── index.html
│   └── main.ts
├── marker/                             # benign target: a directory the payload deletes
│   └── canary.txt
└── dist/                               # (generated)
```

**`ci-sabot.yml`** (the vulnerable-shape reference, mirroring the real-world pattern from Angular's own `pr.yml`: PR-triggered, checkout PR content, install, build):

```yaml
name: ci-sabot
on:
  pull_request:                      # fork PRs reach the job (the D3-shaped trigger class)
    branches: [main]
permissions:
  contents: read                     # NO secrets on this job; no GITHUB_TOKEN writes
jobs:
  build:
    runs-on: ${{ matrix.os }}
    strategy:
      matrix:
        os: [ubuntu-latest, macos-latest]   # macos arm64 = APFS; ubuntu = ext4 reference
    steps:
      - uses: actions/checkout@v4     # PR HEAD (attacker-controlled angular.json from a fork)
      - uses: actions/setup-node@v4
        with: { node-version: 20 }
      - run: npm ci
      - run: npx ng build             # reads the PR's angular.json — the untrusted value
        env: { NG_CLI_ANALYTICS: "false" }
      - run: test ! -f marker/canary.txt && echo "MARKER-DELETED" || echo "MARKER-INTACT"
```

**Payload variants tested across three workflows or three PRs (benign, marker-only):**

| PR | `angular.json` mutation | Expected chain hop | Benign observable |
|---|---|---|---|
| P1 | `outputPath: "<case-variant of the workspace root>"` (e.g. `/home/runner/work/CHAIN2-CISABOT` vs real `chain2-cisabot`) | M3 case-guard bypass → `deleteOutputDir` rm of the checkout contents | `marker/` gone (deleted with the workspace) + build failure/empty dist |
| P2 | `outputPath: "/home/runner/work/chain2-cisabot/../../../marker"`-style `..` escape (ubuntu) | M3 base delete / E1-C1 webpack write escape | marker/canary.txt deleted or overwritten; build log normal |
| P3 | `i18n.locales: { "<deep-dot key>": ... }` + webpack builder | E1-C1 write escape | file lands outside the output base (verify with a find after build) |

All three are **availability/data-integrity only, scoped to the disposable fork's own runner workspace** — nothing outside the checkout that a real attacker could value, nothing persistent.

### 2. Runner choice + cost

- **macos-latest (arm64)** — required for the **case-guard hop**: proves `readdir(<case-variant>)` resolves to the real workspace dir on the actual GitHub macOS image (APFS, case-insensitive by default) — the one fs-semantics question in-lab cannot settle authoritatively.
- **ubuntu-latest** — control + the write-escape hops (ext4 is case-sensitive; expected NEGATIVE for the case-guard hop, positive for `..`-escape writes) — a built-in cross-platform negative control.
- **Cost:** private-repo Actions quota: 2,000 min/month; `macos` counts 10× → one ~8-min build ≈ 80 quota-minutes; `ubuntu` ≈ 8. Total ≈ **90 quota-minutes, well within a free/Pro private-repo budget, charged to the operator's own GitHub account** (no third party). If quota is a concern, run the macos job only (the case-guard is the marginal hop) ≈ 80 min.

### 3. Safety envelope (what a fresh confirm covers)

- **No secrets anywhere**: no GITHUB_TOKEN writes (read-only default), no repository secrets, no env with credentials, no npm auth. The workflow uses only public `actions/checkout`/`setup-node` + `npm ci` against the public registry with a pinned benign CLI version.
- **Benign payload only**: marker-directory deletion/overwrite inside the throwaway fork's own runner workspace; no exfiltration, no persistence, no third-party reach beyond the runner itself.
- **Fork cleanup path (stated at the confirm):** after the runs, operator deletes the fork (`gh repo delete chain2-cisabot --yes`) and removes any local clone; run logs screenshotted/archived under `findings/` evidence first (the only artifacts kept are the benign log excerpts + fs probes).
- **At-the-wire confirm text (the operator must re-affirm verbatim):** "I confirm the private-fork Actions run: repo `<fork>/chain2-cisabot`, workflows `ci-sabot.yml` (P1/P2/P3 branches), no secrets, marker-only payload, cleanup = `gh repo delete` + local clone removal, logs to engagement evidence."
- **Containment ceiling:** the fork is the operator's own; the angular org, real repos, real runners' other tenants, the real npm registry, and any credentials are never touched (per `zone2_containment`).

### 4. What the demo proves that in-lab cannot

| Question | In-lab state | Wire-2 answer |
|---|---|---|
| Full-build E2E of the DELETE/write hops | compiled-module PoCs only (option-normalization + resolver + write functions); full `ng build` webpack infra never spun up | real `npx ng build` on a real runner, real npm install of the CLI, full pipeline |
| GitHub-hosted macOS runner workspace fs semantics | lab APFS is case-insensitive (proven) — but the runner image's volume layout is runner-infrastructure behavior | `_work`/`work/<repo>` layout + case behavior on the actual macos-latest image (is the checkout volume case-insensitive?) |
| Checkout-action path layout interplay | not exercised | actions/checkout's exact path (`/home/runner/work/<repo>/<repo>`) interacting with the guard's `resolve(root, outputPath) === root` compare |
| Runner image + CLI version combination | lab node 24/bazel builds | real image node + pinned CLI behavior |
| Cross-platform negative control | ext4 case-sensitivity reasoned, not run | ubuntu runner confirms the case-guard hop is macOS-only in a real environment |

**The marginal claim only wire-2 settles:** "the M3 case-guard bypass fires on GitHub-hosted macOS runners" — everything else is in-lab-proven; the demo is the last honesty rung for the CI-sabotage reach claim.

### 5. Alternatives if wire-2 is refused (strongest in-lab approximation)

1. **Local APFS case-insensitivity proof (already executed in the deep phase):** the lab's own volume is case-insensitive APFS; `readdir(CASEV)` resolves to the real workspace root and the compiled `deleteOutputDir` deletes it (control throws). This settles the fs-semantics question *for APFS in general* — what it cannot settle is the *runner image's specific volume* behavior and the full-build E2E.
2. **`act` (nektos) local workflow harness:** run `ci-sabot.yml` locally against the malrepo — proves the workflow wiring + command chain end-to-end on the host fs; approximation boundary: act executes on the host's fs (case-insensitive here), not the runner image.
3. **Full `ng build` E2E on the lab** (no wire): spin up the webpack build infra in the lab (the deep-phase residual: "full build E2E not run (webpack infra not spun up)") — closes the build-pipeline rung; the runner-volume question stays reasoned-not-run.
4. **Documented honesty stance:** the case-guard hop is source-verified + lab-APFS-executed; the runner-specific residue is stated in the M3 report as "macOS-hosted runners: mechanism verified on case-insensitive APFS; runner-image confirmation pending wire-2 (operator-gated)."

**Recommendation:** run (3) in-lab now (zero-wire), keep this spec ready for a one-shot wire-2 confirm if the operator wants the runner rung closed before filing M3's CI-sabotage framing.

---

```acceptance-report
{
  "criteriaSatisfied": [
    {
      "id": "criterion-1",
      "status": "satisfied",
      "evidence": "Wire-2 spec produced per the task contract: (a) test repo layout + ci-sabot.yml with three benign payload PRs (P1 macos case-guard root-delete, P2 ubuntu ..-escape, P3 E1-C1 webpack write escape); (b) runner choice macos-latest (APFS, 10x multiplier, ~80 quota-min) + ubuntu-latest control (~8 min); (c) safety envelope: no secrets (contents: read, no repo secrets), marker-only impact, fork cleanup via gh repo delete, verbatim at-the-wire confirm text; (d) marginal proof table: full-build E2E + runner workspace fs semantics + checkout layout + cross-platform negative control, all grounded in scope.md §9 wires/zone2_containment and the Chain-2 goal text; (e) four in-lab alternatives ranked with their approximation boundaries."
    }
  ],
  "changedFiles": [],
  "testsAddedOrUpdated": [],
  "commandsRun": [
    {
      "command": "grep scope.md section 9 wires + zone2_containment + program-policy wire mentions",
      "result": "passed",
      "summary": "Wire-2 trip confirmed (third-party reach); zone2_containment explicitly allows a private throwaway operator-controlled fork with fresh at-the-wire confirm"
    },
    {
      "command": "grep goal-prompts/angular-cli-chainstorm-v1.md Chain 2 + rounds.md E2-R2 lane list",
      "result": "passed",
      "summary": "Chain 2 scope confirmed: M3 case-guard on macOS runners, E1-C1 webpack write escape, extract-i18n/prerender overwrite, D2 purge; wire-2 spec is lane C2F"
    },
    {
      "command": "grep upstream/angular-cli/.github/workflows/pr.yml build steps",
      "result": "passed",
      "summary": "Reference vulnerable shape confirmed: PR-triggered checkout + install + build on PR content (pr.yml runs pnpm ng-dev release build on pull_request)"
    }
  ],
  "validationOutput": [
    "Spec grounded entirely in the engagement's own scope (zone2_containment) and the Chain-2 lane definition; no new attack surface invented — the demo is the honesty rung for the CI-sabotage reach claim",
    "Cost quantified against the operator's private-repo Actions quota (approx 90 quota-min total; 80 if macos-only)"
  ],
  "residualRisks": [
    "Wire-2 requires the operator's fresh confirm at the moment of the act; without it the runner-fs question stays reasoned-not-run (documented in M3 report)",
    "GitHub could change runner image fs layout between confirm and run — the demo result would reflect the image at run time; if the macos workspace ever becomes case-sensitive, the case-guard hop is expected negative (the claim self-documents that condition)",
    "Actions quota charge is real funds on the operator's account (wire 4 adjacent) — included in the confirm text"
  ],
  "noStagedFiles": true,
  "diffSummary": "Read-only planning lane; no files modified (spec returned inline as the task result)",
  "reviewFindings": [
    "no blockers: spec is self-contained, operator-gated, and honest about the marginal proof value",
    "note: the strongest in-lab alternative (full ng build E2E on the lab, zero-wire) is recommended first — it closes the build-pipeline rung without spending quota or tripping wire 2"
  ],
  "manualNotes": "The parent orchestrator should hold this spec as the wire-2 ask payload: if the operator confirms, the run is mechanical (create fork from the layout, push three PR branches, capture logs, gh repo delete). Recommend sequencing after the in-lab full-build E2E alternative."
}
```
