Title: Angular CLI executes commands from registry metadata on Windows before any confirmation; on CI the injected command inherits the job's tokens

**Report as (Google OSS VRP vulnerability type):** Command injection leading to remote code execution (Windows shell spawn with unvalidated registry value; CI-token venue = zero-interaction RCE) — form category: **Command Injection** (fallback: RCE).

Hi Angular CLI team,

I found that `ng add` and `ng update` take the `dist-tags` value from package metadata and use it as a version inside a shell string on Windows, with quotes that do not escape embedded quotes. A registry you do not control can make the CLI run an arbitrary command, and the fetch happens before the install confirmation. On a CI runner the same command inherits the job tokens. I'm including a one-command Windows repro kit with this report.

## Product and version

- @angular/cli, pinned commit d827ba9005 (2026-08-13). Checked current main on 2026-08-15; unchanged.

## Severity

- Dev machine: Low-Medium (CVSS:3.1/AV:N/AC:H/PR:N/UI:R/S:U/C:H/I:H/A:H, 7.5), filed Low-Medium because the value needs an attacker-controlled registry and a Windows host.
- CI venue: CVSS:3.1/AV:N/AC:H/PR:N/UI:N/S:U/C:H/I:H/A:H (8.1). Fork PR on a windows CI runner, no user interaction.

## Summary

For yarn-classic projects, `ng add <pkg>` fetches metadata and uses `dist-tags[latest]` as the version inside a double-quoted specifier. The quoting wraps but never escapes. A registry serving `"latest": "1.0.0\" & <cmd> & \""` produces a cmd.exe line where `<cmd>` runs as its own command. The fetch happens before the install confirmation, so nothing prompts the developer first. `ng update` has no confirmation gate at all, is manager-independent (npm default included), and its version-check fetch fires before everything else.

On CI, the spawn inherits the runner job env. That means `GITHUB_TOKEN` (read-scoped by default on PR events), `ACTIONS_RUNTIME_TOKEN`/`ACTIONS_RUNTIME_URL`, and the OIDC ID-token when the job grants `id-token: write`.

## Steps to reproduce

The repro kit ships with this report (`w1-repro-triager.ps1`). On any Windows machine with Node:

```powershell
powershell -ExecutionPolicy Bypass -File w1-repro-triager.ps1
```

It starts a local registry stub that serves `dist-tags.latest = 1.0.0" & echo W1-MARKER > %TEMP%\w1-poc & "`, points a fixture's `.yarnrc`/`.npmrc` at it (no registry flag is passed; the redirect comes from the repo config), and runs `ng add` (or `ng update` when yarn 1 is absent). Expected result: `RESULT: EXECUTION-OBSERVED` with the marker file present. The mechanism is also verified at the pin with the compiled modules (the spawn string construction is in the report evidence).

## Impact

What I proved: the full command-construction chain at the pin, the ordering (metadata fetch before confirmation), the env inheritance on CI, and the exact cmd.exe string. What I did not prove here: I have no Windows host in my lab, so physical cmd.exe execution is the one rung the kit closes on your side. The sink shape is present in the stable CLI; the fix history is relevant.

## Prior art and the delta

- #32509 (2026-03) was triaged severity6 for this sink class. The full fix PR #32892 was rejected. #32678 fixed the git executor only.
- The delta I'm filing: the registry-controlled VALUE channel (dist-tags, unvalidated), the pre-gate timing, the manager-independent update path, and the CI token reach. Those are not covered by the earlier discussion.

## Remediation

1. Validate `dist-tags` values with `semver.valid()` before building any specifier, in both `getManifest` and `getRegistryManifest` (covers add, update, and the version-check path).
2. Do not join args into a shell string on win32; spawn array-form with `shell: false`.
3. Validate before the `updateDependency` package.json write (the poisoned value persists there).

Happy to retest once the kit has run on your side, and to adjust the severity framing to what the triage policy prefers.
