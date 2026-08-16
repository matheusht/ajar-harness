# W1 Windows repro kit — TRIAGER-READY

What this is: a self-contained reproduction kit for the win32 command-injection finding.
It ships WITH the VRP report so a triager can run it on any Windows machine. One command,
no lab artifacts, no internal builds. The only network traffic is the public npm registry
(for the `npx @angular/cli` download) and localhost.

## One command

```powershell
powershell -ExecutionPolicy Bypass -File w1-repro-triager.ps1
```

Prerequisites: Node 18+ with npm on PATH. For the yarn-classic `ng add` path, yarn 1.x
(`npm i -g yarn@1`); without it the script uses the `ng update` path, which is
manager-independent (npm default) and reaches the same sink.

## What it does

1. Starts a zero-dependency registry stub on `http://127.0.0.1:4873` that serves the
   packument for `w1-poc-pkg` with `dist-tags.latest = 1.0.0" & echo W1-MARKER > %TEMP%\w1-poc & "`.
2. Runs `ng add w1-poc-pkg` (yarn-classic path) or `ng update w1-poc-pkg` (npm-default path)
   from a fixture whose `.yarnrc`/`.npmrc` points at the stub. No registry flag is passed:
   the redirect comes from the repo config alone.
3. The CLI builds the specifier with a quote-wrap that does not escape embedded quotes and
   spawns it via `shell:true` on win32. cmd.exe parses the `&` operators: it runs the yarn/npm
   metadata fetch, then the injected `echo W1-MARKER > %TEMP%\w1-poc`, then an empty command.
4. The script prints `RESULT: EXECUTION-OBSERVED` and the marker content if the marker file
   exists, or `RESULT: MARKER ABSENT` with the triage list if not.

## Expected output (the pass condition)

```
RESULT: EXECUTION-OBSERVED - marker created at C:\Users\<user>\AppData\Local\Temp\w1-poc (content: W1-MARKER)
The injected command ran via cmd.exe (shell:true) BEFORE any install/confirmation gate.
```

The marker is created during the metadata fetch, which precedes the install confirmation
gate (`loadPackageInfoTask` before `confirmInstallationTask` in the add flow; the update
flow has no gate at all and the version-check fetch fires first).

## Files

| File | Role |
|---|---|
| `w1-repro-triager.ps1` | the one-command driver |
| `registry-server.cjs` | malicious registry stub (zero deps; `node registry-server.cjs <port> benign` = negative control) |
| `run-e2e.ps1` + `RUN-BUNDLE.md` | the operator-run version (uses a locally built CLI, for the internal run) |
| `expected-markers.md`, `result-report-template.md` | recording templates |

## Honest notes

- The stable public CLI (`@angular/cli@latest`) carries the same sink shape as the pinned
  commit (the quote-wrap dates to 2026-02; the pin is 2026-08-13). The finding was verified
  against the pin and re-verified unfixed at main on 2026-08-15.
- The negative control: run the same script with `node registry-server.cjs 4873 benign`
  (serves `dist-tags.latest = 1.0.0`) - no marker is expected.
- This kit proves the dev-machine venue. The CI-token venue (fork PR on a windows CI runner,
  injected command inheriting GITHUB_TOKEN / ACTIONS_RUNTIME_TOKEN / OIDC) uses the same
  mechanism with the same commands inside a CI step; the report describes that venue
  separately (CVSS 8.1).
