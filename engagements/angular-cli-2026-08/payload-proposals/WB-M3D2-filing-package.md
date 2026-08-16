# WB-M3D2-FD — M3+D2 filing-delta verdict (Wave B per-finding swarm, lane M3+D2, subagent 5: filing-delta)

Read-only. Grounded in: findings/M3-legacy-builder-outputpath-delete/REPORT.md, findings/D2-cache-clean-deletion/REPORT.md, payload-proposals/FILING-COVER.md (rows 9/10/20), rounds.md E2-R8 chain-role notes, C2E/C2H Chain-2 verdicts, E1-R1 case-guard verdicts.

## 1. Package recommendation: ONE family report

**RECOMMENDATION: file M3 + D2 as ONE family report** ("Uncontained destructive filesystem operations from workspace-config path values in the Angular CLI build family"), with D2 as the unconditional member and M3 as the flagship-DELETE-path + guard-bypass member. Supporting evidence:

- Both reports already frame the sibling relationship: D2's Severity section states "Sibling of M3 — operator may want to file M3 + D2 together as one family report"; FILING-COVER row 20 records the shared root class.
- Same root-cause class: unvalidated workspace-config path value → uncontained destructive fs op at build time (M3: `outputPath` → `deleteOutputDir`; D2: `cli.cache.path` → `getCacheBasePath` → `purgeStaleBuildCache`).
- Same trust boundary (config-trust; cloned-repo / supply-chain precondition), same CVSS shape (AV:L/AC:H/PR:N/UI:N/S:U/C:N/I:N/A:H), same severity (Medium ×2), same remediation family (containment at option normalization + shared-chokepoint helpers).
- Chain 1/2 unification: ONE malicious repo fires both hops (fixture 9/9); the CI-wipe outcome is shared. A single report tells the complete story with one remediation ask.
- Filing-value asymmetry STRENGTHENS the family: D2 = NOVEL + unconditional (fires on every default build, no malicious command); M3 = NOVEL + the flagship application-builder DELETE path (the reference fix 8358805d3 covered writes only) + the case-guard + write-variant amplifiers. Together they defeat the "individual guard exists" defenses on both sides.
- Evidence on file per finding: M3 (evidence-caseguard/, evidence-x1-extract-i18n/, compiled deleteOutputDir PoCs), D2 (poc.mjs real-command, cache-utilities.ts + cache-clean-cli.ts pin copies, 9-entrypoint purge map).

**Counter considered (rejected):** separate reports would isolate D2 as the cleaner unconditional case and separate the fix PRs (options.ts vs cache/utilities.ts). But the shared class + shared remediation + unified chain narrative dominates for the operator's bar (fewer, stronger reports). If the operator prefers two, the cross-reference MUST state the family relation and the shared remediation.

## 2. Case-guard delta paragraph (M3-specific — must NOT be claimed for D2)

- M3: the ONLY containment in `deleteOutputDir` is `resolvedOutputPath === root`, a case-sensitive string compare. On case-insensitive filesystems (macOS default APFS, Windows NTFS, GitHub Actions macOS runners) an `outputPath` set to a case-variant of the workspace root bypasses the guard and the workspace root's own contents are deleted (compiled-module PoC: control throws; case-variant deletes; readdir → []). The "cannot delete the project root" protection is thereby defeated on CI filesystems — a material escalation of the contained case.
- D2: NO root guard exists — `getCacheBasePath` returns the absolute configured path and `purgeStaleBuildCache` deletes it without any equality/containment check. The case-guard bypass does NOT extend to D2 (there is no guard to bypass); D2's discriminator is the mirror image — it never had protection, which is precisely its severity driver (unconditional).
- Filing text requirement: state the case-guard as an M3 sub-claim ONLY; for D2, use the "never guarded" framing, not "guard bypassed".

## 3. CI-wipe delta paragraph (the Chain-2 outcome)

- D2 purge: CROSS-PLATFORM full-checkout wipe candidate in the config-as-data CI shape — verified on case-sensitive filesystems; fires UNCONDITIONALLY on every default build (`ng build`/`ng serve`/`ng test` on PR content) with no malicious command beyond the PR-shipped angular.json. This is the primary Chain-2 wipe primitive (works on ubuntu runners — the dominant GH-hosted shape).
- M3 in CI: the outputPath delete works on any fs for non-root paths; the ROOT-delete (case-guard) requires a case-insensitive runner (macOS GH-hosted — the S2 shape); the extract-i18n/prerender write variants work anywhere.
- Delta framing: D2 = the cross-platform, unconditional wipe (highest CI reliability); M3 = the macOS root-delete amplifier + the flagship-DELETE-path (the twice-fixed-family sibling miss). Together the family covers every GH-hosted OS.

## 4. Severity recheck: BOTH STAY MEDIUM (hold)

- D2: unconditional firing (every default build), arbitrary-dir recursive rm, NOVEL, real-command PoC → Medium holds; it is the family's strongest member.
- M3: config-gated per-invocation delete + case-guard root-delete + flagship-builder DELETE path → Medium holds. The case-guard could suggest lower AC (trivial variant string), but the config-trust precondition (attacker-controlled value must be processed by a build) keeps AC:H. Write-variant amplifiers (extract-i18n Low, prerender Low) do NOT raise the headline.
- CVSS unchanged for both: CVSS:3.1/AV:L/AC:H/PR:N/UI:N/S:U/C:N/I:N/A:H. The CI delivery frame does not shift the vector (the destructive op runs in a local build process; AV:L is the runner-local scope).

## 5. Filing checklist deltas (from the E2 additions)

- M3 must cite #32873 (delete-guard proposed, never merged — disclosed-but-unfixed) and #33312/bd413b0eb (2026-06-04 main-only write-path follow-up fix) — the sibling-miss-in-a-twice-fixed-family framing.
- M3 chain-role note (E2-R8) + case-guard evidence (evidence-caseguard/ with README) are filing-ready.
- D2 chain-role note + real-command PoC + 9-entrypoint purge map are filing-ready.
- Family report opening (recommended): "Two workspace-config path values (outputPath, cli.cache.path) drive uncontained recursive deletion in the Angular CLI build family. One value (D2) fires on every default build with no containment anywhere; the other (M3) carries a root-guard that is bypassable on case-insensitive filesystems and whose write-path sibling was fixed twice upstream without touching the delete path."
