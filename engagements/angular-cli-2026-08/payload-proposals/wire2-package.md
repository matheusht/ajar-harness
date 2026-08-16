# WIRE-2 OPERATOR PACKAGE — Chain 2 CI-sabotage private-fork Actions demo

> Supersedes/extends `payload-proposals/chain2-wire2-spec.md` (the base spec this package is built on).
> Owner: operator. Gate: fresh at-the-wire confirmation (scope.md §9 wire 2). NOT agent-executable.
> Prepared by Wave D D-R1 (DR1-12, 2026-08-15) — read-only planning output, no files were modified by the planner.

## WIRE-2 OPERATOR PACKAGE — Chain 2 CI-sabotage private-fork demo

**What this is.** One operator-gated GitHub Actions run on a private throwaway fork to close the *runner-semantics* rung of Chain 2 (CI sabotage): whether the M3 case-guard bypass fires on a real GitHub-hosted macOS runner, and the full-build E2E of the delete/write hops. Everything else in the chain is in-lab-proven; this is the last honesty rung before filing M3's CI-sabotage framing. Built on `payload-proposals/chain2-wire2-spec.md`; grounded in `scope.md` §9 (wire 2: "Any GitHub Actions run, even in the operator's own private fork") and `zone2_containment` (private throwaway fork, fresh at-the-wire confirm, artifacts under the engagement evidence path with an open cleanup obligation).

---

### 1. THE CONFIRMATION QUESTION (copy-paste, ask exactly this)

> **Wire-2 confirmation request — Chain 2 CI-sabotage private-fork Actions demo.**
> I confirm one private-fork GitHub Actions run, to be executed now:
> - **Fork:** `<operator>/chain2-cisabot` (private, throwaway, operator-owned; never public, never under the angular org)
> - **Workflow:** `.github/workflows/ci-sabot.yml` in that fork (PR-triggered build; `contents: read` only; **no repository secrets, no GITHUB_TOKEN writes, no npm auth**)
> - **Payload branches:** `pr/p1-caseguard` (macOS case-variant root-delete), `pr/p2-escape` (ubuntu `..`-escape), `pr/p3-locales` (E1-C1 webpack write escape) — marker-directory deletion/overwrite inside the fork's own runner workspace only; no exfiltration, no persistence, no third-party reach beyond the runner
> - **Runner:** `macos-latest` (arm64, APFS — the case-guard hop) + `ubuntu-latest` (ext4 control)
> - **Cost:** ≈90 quota-minutes charged to my own GitHub account (macOS 10×: ~80; ubuntu ~8) — real funds on my account, accepted
> - **Cleanup:** after capture, `gh repo delete chain2-cisabot --yes`, remove the local clone, keep only the benign log excerpts + fs probes archived under `findings/` evidence with a cleanup.md ledger entry
> - **Confirmation:** I reaffirm the fork, the workflow, and the cleanup path above; this run trips wire 2 and I authorize it for this act only.

If the operator answers with anything other than a verbatim-or-substantive "confirmed" naming those four elements (fork/workflow/payload/cleanup), **do not run**.

### 2. Test repo layout (private, throwaway)

```
chain2-cisabot/
├── .github/workflows/ci-sabot.yml
├── angular.json          # benign base config (never modified by the PRs' base)
├── package.json          # @angular/cli@18.2.20 pinned (engagement-pin-equivalent stable release)
├── src/{index.html, main.ts, styles.css}
├── marker/canary.txt     # benign canary the payloads delete/overwrite
└── dist/                 # (generated)
```

### 3. `ci-sabot.yml` (ready to paste)

```yaml
name: ci-sabot
on:
  pull_request:
    branches: [main]
permissions:
  contents: read
jobs:
  build:
    runs-on: ${{ matrix.os }}
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, macos-latest]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: 20 }
      - run: npm ci
      - run: npx ng build
        env: { NG_CLI_ANALYTICS: "false" }
      - run: |
          test ! -f marker/canary.txt && echo "MARKER-DELETED" || echo "MARKER-INTACT"
          find . -name 'messages.xlf' -o -name 'index.html' | head -20
```

**Payload branches** (each opens a PR against `main`; base `angular.json` stays benign, only the PR's copy mutates):

| PR branch | `angular.json` mutation | Expected hop | Benign observable |
|---|---|---|---|
| `pr/p1-caseguard` | `outputPath: "/home/runner/work/CHAIN2-CISABOT"` (case-variant of the runner's real checkout dir) | M3 case-guard bypass → `deleteOutputDir` wipes the checkout (macOS APFS) | `marker/` gone; build fails / empty dist on macOS; **ubuntu expected MARKER-INTACT (ext4 case-sensitive — the built-in negative control)** |
| `pr/p2-escape` | `outputPath: "/home/runner/work/chain2-cisabot/../../../marker"` | M3 base delete / E1-C1 webpack write escape (both OSes) | `marker/canary.txt` deleted or overwritten; build log normal |
| `pr/p3-locales` | `i18n.locales: { "<deep-dot key>": { "translation": "src/i18n/messages.fr.xlf", "baseHref": "" } }` + legacy webpack builder | E1-C1 write escape | file lands outside the output base (visible in the `find` step) |

### 4. Safety envelope (explicit checklist, all must hold at confirm time)

- [ ] Fork is private and operator-owned; never public, never under the angular org
- [ ] `permissions: contents: read` — no token writes; zero repository secrets; no npm auth; no env credentials
- [ ] Payload is marker-only (delete/overwrite a canary file inside the fork's own runner workspace)
- [ ] No exfiltration, no persistence, no contact with real angular repos/orgs/runners/apps/keys
- [ ] `npm ci` hits the public registry for a pinned benign CLI — this is a wire-adjacent fetch the confirm already covers (the spec's cost line states it); if the operator objects to ANY public-registry fetch, fall back to a committed offline tarball + `npm i ./tarball` (zero registry wire) — state which in the confirm
- [ ] Quota check: private-repo Actions minutes available on the operator's account (≥100 to be safe)

### 5. Execution checklist (mechanical, after confirm)

1. `gh repo create <operator>/chain2-cisabot --private` (or reuse a pre-made empty private repo)
2. Push `main` (benign base), then push `pr/p1-caseguard`, `pr/p2-escape`, `pr/p3-locales`
3. Open the three PRs; wait for both matrix legs to finish
4. Capture: run logs (workflow runs page → raw log), the `MARKER-DELETED/INTACT` lines, `find` output, and the macOS checkout path probe (`pwd` at step 1 + `df -T`/`diskutil info` if reachable in a step)
5. Archive captures under `engagements/angular-cli-2026-08/findings/M3-legacy-builder-outputpath-delete/evidence/wire2-ci-demo/` (benign excerpts only — no tokens, no fork content beyond the logs)

### 6. Cleanup path (must run even on failure)

```bash
gh repo delete <operator>/chain2-cisabot --yes
rm -rf <local clone>          # and any temp copies
# ledger entry (cleanup.md):
# | <operator>/chain2-cisabot (private fork + local clone) | wire-2 demo (chainstorm) | <date> | delete (closure); completed | closed |
```

### 7. Contingencies

| Event | Expected | Handling |
|---|---|---|
| macOS checkout volume is case-sensitive (GitHub changes image layout) | case-guard hop NEGATIVE | Record it; the M3 claim self-documents that condition ("macOS-hosted runners: mechanism verified on case-insensitive APFS; runner-image confirmation pending"); the ubuntu `..`-escape + p3 hops still prove the write/delete E2E |
| Build fails before the delete hop (CLI version incompat) | Hops not reached | Fix the pinned CLI version in `package.json` and rerun (within the same confirm — same fork/workflow/payload scope) |
| Quota exhausted mid-run | Partial results | Keep whatever captured; the missing leg is re-run only under a fresh confirm |
| npm registry fetch refused by the operator | No registry wire | Switch to a committed offline CLI tarball + `npm i ./tarball` (still the same confirm if stated at ask time) |

### 8. What the demo proves vs not

- **Proves:** full-build E2E of the delete/write hops on real runners; the case-guard bypass firing (or not) on the actual macos-latest image; actions/checkout path layout interacting with the `resolve(root, outputPath) === root` guard; cross-platform negative control (ext4).
- **Does not prove:** anything beyond the operator's own disposable fork — no angular-org impact, no persistence, no secrets. The marginal claim it settles is exactly: *"the M3 case-guard bypass fires on GitHub-hosted macOS runners."*
- **If refused:** the strongest in-lab alternative stands (full `ng build` E2E on the lab, zero-wire) + the existing lab-APFS execution + the documented runner-residue sentence in the M3 report.

---
