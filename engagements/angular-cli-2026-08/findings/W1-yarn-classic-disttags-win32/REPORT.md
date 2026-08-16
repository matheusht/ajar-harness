# W1 — Windows command injection via unvalidated registry `dist-tags` values (yarn-classic metadata path)

- **Engagement:** angular-cli-2026-08 · **Pinned commit:** `d827ba9005b86b23d05ee7c62c0823367aa245c1`
- **Origin:** cascading-phase E0-R1 cell E3 (`new_finding_spun_off`) — first cap-removal of the phase: the held "developer-invoked input" cap on the win32 shell-string surface is removed for yarn-classic projects.
- **Surface:** `packages/angular/cli/src/package-managers/package-manager.ts:572-590` (`getManifest` tag case) → `:520-523` (`getRegistryManifest`) → `packages/angular/cli/src/package-managers/host.ts:157-164` (win32 `spawn(..., {shell:true})`)
- **Status:** PROMOTED (2026-08-15, finding #6) — cascading spin-off; deep-phase amplifiers folded (ng-update entry; doctrine; sibling note; manager-independent widening).

## One sentence on why it is real

For yarn-classic projects, `ng add <pkg>` / `ng update <pkg>@latest` fetch registry metadata and use the **registry-controlled, unvalidated** `dist-tags[latest]` value as the version inside a win32 shell-string specifier wrapped in double quotes that do **not** escape embedded quotes — a malicious registry (cloned repo's `.npmrc`/`.yarnrc`, or a compromised mirror) serves `"latest": "1.0.0\" & calc & \""` and cmd.exe executes the attacker command **from metadata alone, before the install confirmation gate and before any `--ignore-scripts`-gated script run**.

## Mechanism (source-verified)

1. `getManifest` tag case (`package-manager.ts:572-590`): `versionSpec = fetchSpec ?? 'latest'`; for `requiresManifestVersionLookup` descriptors: `versionSpec = metadata['dist-tags'][versionSpec]` — **no semver/charset validation** of the dist-tag value.
2. `getRegistryManifest` (`:520-523`): `specifier = this.host.requiresQuoting ? `"${packageName}@${version}"` : ...` — the `85e3ce2e0` quoting fix wraps but does **not escape embedded `"`**.
3. `host.ts:157-164` (win32): `spawn(`${command} ${args.join(' ')}`, {shell: true})` — the wrapped specifier with an embedded quote closes the wrapper; `&`/`|`/`;` after it execute on cmd.exe.
4. The descriptor is yarn-classic (`requiresManifestVersionLookup: true`, `package-manager-descriptor.ts:246` — the npm descriptor has `getRegistryMetadata` and does not take this path; yarn classic needs the `yarn info` manifest lookup). The CLI auto-selects yarn-classic for `yarn.lock` projects with Yarn < 2 (`factory.ts:99-107`).
5. Trigger: `ng add <pkg>` (bare specifier → `getManifest('pkg@latest')`) or `ng update <pkg>@latest` — the metadata fetch runs **before** the Listr confirmation task and before any install.

## Trust boundary crossed

Registry response `dist-tags` (attacker-influenceable via cloned-repo `.npmrc`/`.yarnrc` registry line or a compromised mirror — the dev runs `ng add` on a project whose config points at the attacker registry) → unvalidated string → win32 shell command → **arbitrary command execution on the developer machine, ungated and unconfirmed**.

## Marginal-contribution delta (per escalation §1)

Without the bug, an attacker registry can still serve a malicious tarball — but its install scripts are gated by `--ignore-scripts` (when enabled) plus the interactive confirmation. With the bug: arbitrary command execution **from metadata alone** — the fetch happens before both gates, and the injected command runs in the developer's shell context at metadata time.

## Caps that held (empirically tested by E3)

- `npa.resolve` throws on the malicious version in `ng add`'s version re-resolution path (kills that route).
- ~~`semver.lte` throws in the update-resolver path (kills that route)~~ — **SUPERSEDED by the E1-R2/X3 kill-pair order proof:** the `semver.lte` throw in `update-resolver.ts:527` fires AFTER the injection spawn (resolve loop :947-992 executes before `packageInfoEntries` :997-1008) — it is post-injection masking, not a preventive gate. See the DEEP-PHASE AMPLIFIER section (ng update entry). The `getManifest` tag path retains the no-check shape.
- `.npmrc` → `--registry` CLI-arg plumbing does not exist (config is only copied to temp dirs) — the registry value must come from the project config's registry line, which package managers read themselves.
- Workspace schematics defaults never reach package-manager args.

## Reachability caps

- **Windows only** (POSIX is array-spawn — safe).
- **yarn-classic only FOR THE `ng add` METADATA-FETCH PATH** (npm/yarn-modern descriptors skip the `requiresManifestVersionLookup` lookup — KP-W1 verified). **E1-R8/FS-W1 WIDENING: the `ng update` entry is MANAGER-INDEPENDENT** — `update-resolver.ts` resolves dist-tags values unvalidated for EVERY manager (npm default included) and reaches the same quote-wrap + win32 shell:true sink via `getRegistryManifest` (update-resolver.ts:50-55, :662/:727/:534). The yarn-classic-only cap applies to the add path; the update entry (X3 amplifier) is not manager-bounded.
- The attacker controls the registry the dev's project points at (or compromises a mirror) — the same precondition class as registry-supply-chain generally, but the *execution* here bypasses the script gates.

## Replay / staleness

- Mechanism re-verified at the pin (source). Live E2E on Windows is **blocked in this environment** (no Windows runner; wires forbid third-party systems) — the PoC fixture shape (recording registry serving the malicious `dist-tags`, run `ng add` under wine/CI Windows) is specified in WINDOWS-E2E-FIXTURE.md (fixture ready). `d8b76e93d` (2025-12) added the dist-tag lookup without validation; `85e3ce2e0` (2026-02) added the quoting this bypasses. Not stale.


## DEEP-PHASE AMPLIFIER (E1-R2/X3, kill-pair SURVIVES): ng update entry — 3 additional dist-tags call sites, injection fires BEFORE the abort

- **New claim (entry delta):** the ng update flow reaches the SAME win32 shell:string sink with unvalidated registry-controlled dist-tags values at THREE more call sites in `update-resolver.ts`: `_buildPackageInfo` (:495-527), `resolvePackageVersion` (:604-627), `_addPackageGroup` (:630-668) → `getRegistryManifest` specifier construction (`package-managers/package-manager.ts:515-523`) → the project manager generic `getManifestCommand` (npm default: `view --json` at package-manager-descriptor.ts:188; yarn-classic: `info --json --verbose`) → quote-wrap → win32 `shell:true` spawn (identical chain to the ng add case; manager-independent per FS-W1/E2-R7).
- **Order proof (kill-pair-verified):** the resolve loop (:947-992, containing the `_addPackageGroup` spawn at :967 (packageGroup members at :662)) executes BEFORE `packageInfoEntries` (:997-1008, whose `semver.lte` check at :527 throws "Invalid Version") — **the injection fires first; the abort only masks it**.
- **No confirmation gate:** the update flow has no prompt between metadata fetch and install (verified: no inquirer/confirm in update/cli.ts).
- **Validation audit:** `isReleaseAgeSatisfied` passes everything (RegistryClient default `minReleaseAge = 0` → returns true; with a configured age, `metadata.time[malicious-version]` is undefined → returns true). No semver validation of the dist-tag value anywhere.
- **Amplifier:** `packageGroup` spread — group members inherit the malicious version → additional `getRegistryManifest` spawns per member.
- **Entry delta vs base W1:** automated bot/CI reach (`ng update` in pipelines), no confirmation prompt, packageGroup multi-spawn, post-injection abort masking, and — FS-W1 (E1-R8) — MANAGER-INDEPENDENT reach (npm default included; the yarn-classic-only bound applies to the ng add path). Severity calculus for the DEV-MACHINE venue unchanged (same trust boundary: registry-controlled value, win32; AC:H reachability holds); the CI-token venue is a separate framing (E2-R7/KP-W1 — filing-time operator decision on Medium for the CI variant).
- **Remediation extension:** validate dist-tags values with `semver.valid()` at the SOURCE in BOTH `getManifest` and `getRegistryManifest` (update-resolver feeds the latter).


## DEEP-PHASE SIBLING NOTE (E1-R4/L6b): terminal escape-sequence injection — same registry precondition

- Verified (source): raw registry-controlled `homepage`/error text reaches `process.stdout` unchanged in `ng add` (display-only; modern terminal emulators execute no code from escape sequences — output spoofing / OSC 52 clipboard / prompt-spoofing classes only). Error-path variants embed registry error text too (logger.error(e.message)).
- Same trust precondition as W1 (attacker-controlled registry metadata); the SAME attacker controls both the shell-injection value and the terminal-escape value. Not a standalone finding (display-only, no exec); recorded here as the W1-family sibling note.
- Remediation line: sanitize control characters from registry-derived display strings (strip C0/C1 + OSC sequences) before terminal output.

## CHAINSTORM AMPLIFIER (E2-R2/C2D, source-verified): fork PR on Windows CI = RCE inheriting CI tokens

- **New reach (marginal delta, mechanism-complete):** a fork PR to a repo whose CI runs `ng add`/`ng update` (or e2e jobs that scaffold apps) on `windows-latest`, with the PR checkout carrying the malicious `.yarnrc`/`.npmrc` (C1A: silent registry redirect, no validation) — the metadata fetch fires the injection BEFORE any confirmation (add/cli.ts:221 precedes :227; ng update has no gate and is manager-independent).
- **Secret reach (verified at source; kill-pair precision E2-R7/KP-W1):** the injected cmd.exe runs under the ng CLI process env (`host.ts:150-165` — `{...process.env, ...options.env}` + win32 joined-string `shell:true`). Exact token inventory on a fork-PR-triggered `pull_request` job: **read-scoped `GITHUB_TOKEN` by default** (repo default permissions), `ACTIONS_RUNTIME_TOKEN`/`ACTIONS_RUNTIME_URL` (always present — artifacts/caches), `ACTIONS_ID_TOKEN_REQUEST_TOKEN`/`URL` only when `permissions: id-token: write` (OIDC); arbitrary repo secrets (incl. the robot key) are NOT in the step env unless explicitly mapped — the robot key stays in-process in the action (C5A). Exfil path: the attacker registry server (outbound HTTP default-allowed).
- **Shape framing (E2-R7/KP-W1):** the CI shape is per-repo conditional — the primary attacker-triggered venue is e2e/scaffolding CI jobs that run `ng new`/`ng add` on PR content (real in boilerplate/sample repos and framework e2e suites); general app repos running `ng update` on PR checkouts are rarer; dependency-update BOT runs are a DIFFERENT attacker model (bot token, not fork-triggered) and are excluded. The yarn-classic-only cap applies to the `ng add` metadata-fetch path; the `ng update` path is manager-independent (npm default — `getRegistryManifest` is the generic method, `npm view --json` on win32).
- **Caps (declared):** execution rung still environment-blocked (no Windows host in-lab); the env channel (`YARN_NPM_REGISTRY_SERVER`) is flag-only and NOT config-driven (C2H bounded); Angular's own CI is structurally not reachable (S6: no ng add/update, sandboxed registry).
- **Delta vs base W1:** dev-machine RCE → CI-token theft on attacker-triggered events (fork PR), when the CI shape exists. Severity framing for filing: the mechanism hops are all source-verified; the physical run is the single gap (WINDOWS-E2E-FIXTURE.md + a wire-2 private-repo demo would close it — operator-gated).

## WAVE-B PRECISION ADDITIONS (E2-B1): version-check venue + package.json poisoning + CI-venue severity split

- **Version-check venue (W1-ME + N2D kill-pair, verified at pin):** `cli-version.ts:63` runs on EVERY `ng update` WITH packages — `checkCLIVersion` fires FIRST (update/cli.ts:168-171), BEFORE the update-resolver loop and any confirmation: **an EARLIER entry point than the X3 amplifier**. The version-check fetch uses the same tag-case + quote-wrap + win32 `shell:true` chain; the package.json-poisoning write (`applyUpdatePlan` -> `updateDependency`, update-resolver.ts:1189+) is reachable in the SAME invocation. Bounds (N2D): yarn-classic-only (getManifest `requiresManifestVersionLookup`), numeric runnerVersion paths semver-bounded (`maxSatisfying`), POSIX array-spawn safe, `ng update` without packages does not fire.
- **Package.json poisoning (W1-CS, V3):** on the update path the unvalidated dist-tags value is ALSO written into the dev's package.json dependencies (`updateDependencies`) — persistence + a second-stage vector (the poisoned version string survives the run; a later install re-fetches it).
- **CI-venue severity split (W1-FD, derived):** dev-machine venue unchanged (CVSS 7.5, filed Low-Medium under the doctrine). Fork-PR CI venue: `AV:N/AC:H/PR:N/UI:N/S:U/C:H/I:H/A:H` (no user interaction — attacker-triggered via PR; 8.1 base by the UI:N delta, conditional High with the ID-token/OIDC branch) — filing-time operator decision (part of W1 or separate entry); the humanized opening must keep the #32509/#32892 doctrine citation visible while leading with the zero-interaction delta.

## DEEP-PHASE DOCTRINE SECTION (E1-R2/L9c): maintainer posture — disclosed class, rejected full fix

- The sink class was previously triaged by the maintainers: **#32509** (2026-03) carries `severity6: security` with the SAME injection shape; the full fix PR **#32892 was REJECTED**; the maintainers documented a **won't-fix doctrine (2026-03-27)** treating package-manager specifier handling under config-trust. **#32678** fixed the git executor only. The pin postdates all of these (85e3ce2e0a quote-wrap, 598a690a0 git-quoting both ancestors).
- **Filing-viability note (operator decision input):** under the documented doctrine, W1's filing viability is LOW as a first report — the ONLY counter is the narrow delta: the registry-controlled VALUE channel (not the specifier-construction class) + the pre-gate/pre-confirmation invisible-execution timing + the update-resolver multi-call-site reach. Any filing must open with the delta vs #32509/#32892, not the mechanism.
- Novelty of the exact channel (registry dist-tags value, ungated) remains undisclosed (searched; no issue/PR/advisory).

## DEEP-PHASE UPDATES (E1-R1): upstream framing, novelty, and the static-only filing argument

**Upstream fix-bypass framing (verified at the pin, deep phase):** the sink line was previously the subject of a security fix — GH issue **#32509** (2026-03) touched `host.ts` + the package-manager executor, and the pin's code POSTDATES that fix. The bypass vehicle is the quote-wrap added by `85e3ce2e0` (2026-02-23, "quote complex range specifiers", ~1 month BEFORE #32509): `requiresQuoting` wraps the specifier in double quotes WITHOUT escaping embedded quotes — `1.0.0" & calc & "` closes the quote and chains via `&`. PR **#32678** fixed the git executor only (a different spawn site); the yarn-classic metadata-fetch path at host.ts:157-164 retains the unescaped-wrap + `shell:true` shape at the pin. **Filing framing: regression/fix-bypass of #32509, not a first-report.** Any filing must cite #32509, #32678, and `85e3ce2e0` or credibility is lost.

**Novelty (E1-R1, L9):** NEAR-MISS / fix-bypass as above — no public disclosure of the dist-tag value channel itself. Same-day same-reporter cluster **#33074/#33075/#33076/#33077** (2026-04-28, reporter `foxllb`) reports adjacent package-manager/codegen injection issues — an active independent researcher on this surface; disclose the cluster in the filing (co-credit risk).

**Windows E2E blocker (exact, verified):** host is Darwin/arm64 with no Windows execution layer — no wine/wine64, no qemu, no Windows virtualization apps (Parallels/UTM/VirtualBox/VMware absent), no cross/zig toolchain, and Docker Desktop is Linux-containers-only (`OSType: linux`, linux/arm64 — macOS Docker cannot run Windows containers). Procuring a Windows host or remote runner would require third-party systems, which scope.md §9 wires forbid. The E2E fixture (`WINDOWS-E2E-FIXTURE.md`) is ready to run on any Windows host (local, method-2, no wires).

**Static-only filing argument (what a triager should accept without the live E2E):**
1. The injection value trace is a closed loop of source-verified hops: `dist-tags.latest = '1.0.0" & calc & "'` (registry-controlled, unvalidated at package-manager.ts:572-590) → `versionSpec` (no semver/charset check) → quote-wrap `'"pkg@1.0.0" & calc & ""'` (host.ts:110 `requiresQuoting`, no escaping) → win32 `spawn(string, {shell:true})` (host.ts:157-164) → `cmd.exe /c yarn info --json --verbose "pkg@1.0.0" & calc & ""` — executes yarn, then `calc`, then an empty command.
2. Trigger ordering is verified in the Listr flow: the metadata fetch (`loadPackageInfoTask`, add/cli.ts:520-531) executes BEFORE the confirmation task (line 570) and the install task; the non-TTY abort at confirmation does not prevent the already-executed fetch+injection. Two additional triggers at add/cli.ts:363 and :458.
3. The single evidence-grade gap is physical cmd.exe execution on Windows (environment-blocked); every hop is source-verified at the pin and the mechanism is not contested — the fixture documents the exact commands a Windows run would execute as the confirmation rung.

## Severity / category

- **Low-Medium** (Windows + yarn-classic + attacker-registry preconditions; arbitrary command exec on the dev machine; ungated). CVSS:3.1/AV:N/AC:H/PR:N/UI:R/S:U/C:H/I:H/A:H — see finding.json. Category: Product Vulnerability (package-manager plumbing). Operator re-review.

## Remediation

1. Validate `versionSpec` from `dist-tags` with `semver.valid` before building any specifier.
2. Never join args into a shell string on win32 — spawn array-form with `shell: false` (Node passes args to CreateProcess without cmd.exe interpretation), or properly escape embedded quotes.
3. Apply the same validation in the npm/pnpm descriptors' metadata paths (audit `getRegistryMetadata` for parallel unvalidated values).
4. Validate dist-tags values BEFORE the `updateDependency` write (the version-check venue + package.json-poisoning share the same unvalidated value; N2D).
