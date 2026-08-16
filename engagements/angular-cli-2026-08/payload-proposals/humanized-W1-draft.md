# humanized-W1-draft.md

**DRAFT — operator re-authors before filing. Source pin `d827ba9005b86b23d05ee7c62c0823367aa245c1` (2026-08-13). Date: 2026-08-15.**

## W1 — Windows: registry `dist-tags` metadata executes commands during `ng add`/`ng update`

**One-line summary**
On Windows, in yarn-classic projects, `ng add <pkg>` and `ng update` interpolate the registry's `dist-tags` value into a shell command without validating or escaping it, so a malicious registry entry runs an arbitrary command on the developer machine before any confirmation gate.

**What the user sees**
You run `ng add` in a project whose `.npmrc`/`.yarnrc` points at an attacker-controlled registry (or a compromised mirror). The metadata fetch happens before the confirmation prompt, and the injected command runs in your shell at that moment. Nothing is shown about the injected value.

**Why it matters**
The value is registry-controlled package metadata, not the developer's own input. The quoting added in the earlier fix wraps the specifier but does not escape embedded quotes, so `"latest": "1.0.0\" & calc & \""` closes the wrapper and chains on cmd.exe. The same sink class was reported before (#32509, triaged severity6) and the full fix PR (#32892) was rejected under the project's config-trust doctrine, so any filing has to open with the delta: the registry-controlled value channel plus the pre-gate timing, not the mechanism. I verified every hop in source at the pinned commit; a live Windows run is still blocked in this environment (no Windows runner available), and the fixture for one is written up.

**Reproduction sketch**

