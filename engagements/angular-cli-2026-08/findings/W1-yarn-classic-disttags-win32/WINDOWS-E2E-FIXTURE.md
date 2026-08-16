# W1 — Windows E2E fixture specification (E0-R5 deliverable)

The W1 mechanism is source-verified at the pin; a live Windows E2E is blocked in this environment
(no Windows runner; wires forbid third-party systems). This spec lets the operator (or a future
Windows-capable run) reproduce end-to-end. All artifacts are synthetic; no real registry.

## Fixture components

1. **Recording/malicious registry stub** (local, e.g. `verdaccio` or a tiny http server):
   - Serves `GET /<package>` returning metadata with
     `{"dist-tags": {"latest": "1.0.0\" & calc & \""}, "versions": {...}}` (or a benign marker
     command like `" & echo PWNED > %TEMP%\\w1-poc & "`).
   - Serves the manifest for `name@1.0.0` (any valid manifest).
2. **Project**: `yarn.lock` present + the project manifest with a dependency on the test package.
   **Yarn-1 `.yarnrc` syntax** (not bare `registry http://…`): `--registry http://127.0.0.1:<port>`
   (Yarn 1 config semantics). The fixture commands MUST run from the fixture project directory
   (the yarn subprocess inherits `process.cwd()` — host.ts:164 — and reads the project `.yarnrc`
   from it). Yarn 1.x must be on PATH and the version-detection subprocess (`yarn --version`,
   factory.ts:99-107) must resolve major < 2 — a yarn 2+ binary silently falls through to
   yarn-modern (no injection).
3. **Environment**: Windows 10/11, cmd.exe default shell, Node 24, Yarn 1.x, `@angular/cli` at the
   pin (`d827ba9005b86b23d05ee7c62c0823367aa245c1`).
4. **Invocation**:
   ```
   ng add <test-package>            # bare specifier -> getManifest('pkg@latest') metadata fetch
   # or
   ng update <test-package>@latest  # update/cli.ts:466 second trigger
   ```
   Both fetch metadata BEFORE the confirmation gate and before any install.

## Expected observation

- The injected command executes (use an echo-marker, e.g.
  `" & echo PWNED > %TEMP%\w1-poc & "` — `calc` opens a GUI window, fine interactively but
  awkward in CI; state the marker path explicitly and clean it up) (marker file created / calc window) **before** any install
  confirmation prompt appears and **before** `node_modules` is touched (no package install trail).
- Negative control: same fixture with the registry serving a VALID dist-tag value
  (`"latest": "1.0.0"`) — no injection; with npm/pnpm descriptors — no injection (value path skipped).
- POSIX control: same fixture on Linux/macOS — array-spawn, no injection.

## Verification notes

- `requiresQuoting = platform() === 'win32'` (host.ts:110); win32 spawn is
  `spawn(`${command} ${args.join(' ')}`, {shell: true})` (host.ts:157-164).
- The `confirmInstallationTask` displays `packageIdentifier.toString()` (the tag name, `pkg@latest`)
  — the injected value is not revealed to the user.
- Non-TTY control: `ng add` without TTY aborts at the confirmation ("No terminal detected") for the
  install path — but the injection fires during the preceding metadata fetch.

## Cleanup

- All artifacts are local/synthetic; no real credentials; nothing persists outside the fixture dir.
