# M3D2-filing-package.md — ONE family report: "Uncontained destructive filesystem operations from workspace-config path values in the Angular CLI build family"

Prepared for the operator's re-authoring (next-phase records, Wave D). Read-only assembly grounded in:
`findings/M3-legacy-builder-outputpath-delete/REPORT.md`, `findings/D2-cache-clean-deletion/REPORT.md`,
`payload-proposals/WB-M3D2-filing-package.md` (Wave B), `payload-proposals/kp-m3d2-verdict.md` (Wave B
kill-pair), `payload-proposals/chain1-fixture-spec.md` + `chain-demos/` (Chain 1 fixture 9/9),
`payload-proposals/chain2-wire2-spec.md` (Chain 2 config-as-data), `FILING-COVER.md` rows 9/10/20.

---

## 1. The one-report structure (shared chokepoint framing)

**Headline claim:** two workspace-config path values drive uncontained recursive deletion in the
Angular CLI build family. One value (`cli.cache.path`, D2) fires on EVERY default build with no
containment anywhere; the other (`outputPath`, M3) carries a root-guard that is bypassable on
case-insensitive filesystems and whose write-path sibling was fixed twice upstream without touching
the delete path.

**Shared root-cause class:** unvalidated workspace-config path value -> uncontained destructive fs
operation at build time.

| Member | Config value | Chokepoint | Operation | Guard | Severity |
|---|---|---|---|---|---|
| **D2** (family-strongest) | `cli.cache.path` | `getCacheBasePath` (2 byte-identical copies: `packages/angular/cli/src/commands/cache/utilities.ts:27`, `packages/angular/build/src/utils/normalize-cache.ts:43`) | `purgeStaleBuildCache` force-recursive rm, 9 builder entrypoints, fires on every default build | **NONE (never guarded)** | Medium (hold) |
| **M3** | `outputPath` (application + legacy browser/server) | `deleteOutputDir` (`packages/angular/build/src/utils/delete-output-dir.ts`) — exactly 3 callers | recursive contents-delete of the resolved dir, plus write-variant siblings (extract-i18n, prerender) | `resolvedOutputPath === root` string compare, **case-bypassable** | Medium (hold) |

**Family remediation (one ask):** containment at option-normalization time in both paths +
case-folded canonical guard inside `deleteOutputDir` + the shared-helper chokepoint fix for the
cache path. The two fixes land in different files but are one remediation family.

## 2. Case-guard section (M3 sub-claim ONLY)

- The ONLY containment in `deleteOutputDir` is `resolvedOutputPath === root`, a case-sensitive
  string compare. On case-insensitive filesystems (macOS default APFS, Windows NTFS, GitHub Actions
  macOS runners) an `outputPath` set to a case-variant of the workspace root bypasses the guard and
  the workspace root's own contents are deleted (compiled-module PoC: exact-root control throws;
  case-variant deletes; readdir -> []).
- **Kill-pair strengthening (kp-m3d2-verdict):** the variant does not need an absolute path — a
  RELATIVE case-variant (`outputPath: '../PROJ'` for a workspace named `proj`) works; ANY case
  mismatch on case-insensitive fs passes the guard. A naive `realpathSync(out) === realpathSync(root)`
  remediation FAILS on APFS (`realpathSync` preserves input case; `/tmp/kp-m3/PROJ` stays
  `/private/tmp/kp-m3/PROJ`) — the fix must explicitly case-fold (M3 remediation item 2's
  "case-folded/canonicalized" wording is load-bearing).
- **Must NOT be claimed for D2:** D2 has no root guard to bypass (its discriminator is the mirror
  image — it never had protection, which is precisely why it is the unconditional member). File D2
  with the "never guarded" framing, not "guard bypassed".

## 3. CI-wipe section (the Chain-2 outcome)

- **D2 primary, cross-platform:** in the config-as-data CI shape (a trusted CI that builds the PR
  checkout without running install-scripts), the purge wipes the checkout — verified on
  case-sensitive filesystems (ubuntu, the dominant GH-hosted shape). **Precision condition
  (kp-m3d2-verdict):** in CI the default `cli.cache.environment` is 'local' which DISABLES the
  purge; the malicious angular.json must also set `cli.cache.environment: 'ci'` — one extra field
  in the same config file, same trust channel. With both keys set the purge destroys the workspace
  root outright (live compiled-module control).
- **M3 in CI:** non-root outputPath deletes work on any fs; the ROOT-delete (case-guard) needs a
  case-insensitive runner (macOS GH-hosted, the S2 shape); extract-i18n/prerender write variants
  work anywhere.
- **Coverage:** the family covers every GH-hosted OS (ubuntu: D2 wipe; macOS: M3 root-delete;
  windows: both).
- **Honest cap:** GH-hosted runners are ephemeral (failed PR + Actions-minute burn); the persistent
  damage shape is self-hosted (already scoped in the chain records).

## 4. Novelty citations (both verified in the M3 report)

- **#32873**: a delete-path guard was PROPOSED but NEVER MERGED — the delete variant is
  disclosed-but-unfixed. Filing must state this explicitly: the maintainers considered the delete
  guard and did not ship it.
- **#33312 / bd413b0eb** (2026-06-04, main-only): extends the application-builder WRITE containment
  (the 8358805d3 family) to the browser-dir escape. The DELETE path and the case-guard are
  unaffected (likely still live on main — the next-phase current-main re-verification will confirm).
- **D2**: NOVEL — no disclosure of `cli.cache.path`/purge deletion anywhere in the searched corpus.
- Framing: "sibling-miss in a twice-fixed family" for M3; "unconditional member, never guarded" for
  D2. Together they defeat the "individual guard exists" defenses on both sides.

## 5. Openings (delta-first, filing voice — operator re-authors and re-verifies line numbers)

**Opening A (family, for a combined report):**
"Two workspace-config path values (`outputPath`, `cli.cache.path`) drive uncontained recursive
deletion in the Angular CLI build family. One of them (`cli.cache.path`) deletes whatever directory
it names on every default build, with no containment anywhere in the chain, on every platform. The
other (`outputPath`) deletes the contents of the resolved directory through a path that carries a
root-guard, and that guard falls to a case-variant on macOS and Windows. The write-path sibling of
the second value was fixed twice upstream; the delete path was proposed for a fix and never
merged."

**Opening B (D2 standalone, if the operator splits):**
"`ng cache clean` and the automatic build-time cache purge delete any directory the workspace
config names, with no validation and no prompt. The value comes from a cloned repo or a supply
chain, and the deletion fires on every default build even when nothing malicious is ever run. This
one never had a guard."

**Opening C (M3 standalone, if the operator splits):**
"`outputPath` deletes the contents of any directory the config names, and the only protection, a
guard that refuses to delete the project root, is bypassable by a case-variant of the root's name
on macOS and Windows. The delete path was proposed for a fix upstream and never merged."

## 6. Evidence inventory (filing-ready)

- M3: `findings/M3/evidence-caseguard/` (compiled `delete-output-dir.mjs` + `poc.mjs` + README —
  the case-guard PoC), `evidence-x1-extract-i18n/` (poc.mjs, neg.mjs, messages-sample.xlf),
  `evidence/poc.mjs` + `poc2.mjs` (base delete), chain-role note in the REPORT.
- D2: `findings/D2/evidence/poc.mjs` (real-command), `cache-utilities.ts` + `cache-clean-cli.ts`
  pin copies, the 9-entrypoint purge map, chain-role keystone note in the REPORT.
- Chain 1: `payload-proposals/chain-demos/` (fixture 9/9 both modes; the family hops H2/H3/H6).
- Chain 2: `payload-proposals/chain-demos/c2shape/` (config-as-data 3/3) + `chain2-wire2-spec.md`.
- Credential scan over the evidence: CLEAN (verified E2-R9).

## 7. Severity (both Medium, hold)

CVSS:3.1/AV:L/AC:H/PR:N/UI:N/S:U/C:N/I:N/A:H for both. The CI delivery frame does not shift the
vector (the destructive op runs in a local build process; AV:L is the runner-local scope). The
write-variant amplifiers (extract-i18n Low, prerender Low) do not raise the headline.

## 8. Sequence recommendation

File the family after the W1 CI-token entry in the operator's sequence (W1 CI-token RCE > M3+D2
family > E1-C1 SSR venue > D1 > M2 > D3), per the FILING-SEQUENCE.md rationale — the higher-severity
findings benefit from fresh filing while D3's window is the longest-lived.
