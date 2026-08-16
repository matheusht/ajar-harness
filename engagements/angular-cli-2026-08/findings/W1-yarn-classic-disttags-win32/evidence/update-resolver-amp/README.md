# W1 ng-update amplifier — evidence note (source-verified, E1-R2/X3 kill-pair)

The ng-update entry amplifier (3 additional dist-tags call sites) is SOURCE-VERIFIED at the pin
d827ba9005: `packages/angular/cli/src/commands/update/update-resolver.ts` `_buildPackageInfo`
(:495-527), `resolvePackageVersion` (:604-627), `_addPackageGroup` (:630-668) → `getRegistryManifest`
specifier construction (`package-managers/package-manager.ts:515-523`) → yarn-classic
`getManifestCommand` → quote-wrap → win32 `shell:true` spawn (identical chain to the ng add case).

Order proof: the resolve loop (:947-992, with the `_addPackageGroup` spawn at :967 / packageGroup
members at :662) executes BEFORE `packageInfoEntries` (:997-1008, whose `semver.lte` throw at :527
fires post-injection) — the injection fires first; the abort only masks it. No confirmation gate in
the update flow (verified: no inquirer/confirm in update/cli.ts).

Physical cmd.exe execution remains environment-blocked (no Windows host) — same as the base W1.
