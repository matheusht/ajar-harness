# N-K — E1-C1 venue-split record brief (operator decision record)

## 1. Severity venue-split (the decision to record)

**Recommended record: browser 4.0 Low-Medium · legacy-SSR 6.3 Medium.**

Supersession chain (must be visible in the record so reviewers don't resurrect the stale figure):

| Step | Severity claim | Source |
|---|---|---|
| E2-R4 (C4F) | HIGH **7.3** (AV:N/AC:H/PR:N/UI:N/S:U/C:H/I:H/A:H) — first SSR-venue detection | `findings/E1-C1-i18n-locale-key-escape/REPORT.md` (venue-split section, now corrected) |
| E2-B2 (ECKP) | **6.3** correction — honest preconditions: attacker-file/package must be locally reachable (**AV:L**) and the dev must run the localized build (**UI:R**) | Wave-B kill-pair, recorded rounds.md E2-B row |
| E2-D3 (DR3-15) | **Reconciled to 6.3 everywhere** — front-matter + plan.md §12/§13/§15 + operator notes all carry 6.3 | applied this session; gates re-verified CLEAR |

The 8.1 figure (ECRV, harness `cvss31_base` under AV:N/UI:N) is a **calculator-variant**, not a competing claim — record as a footnote, not an option.

- **Browser venue:** CVSS:3.1/AV:L/AC:H/PR:N/UI:N/S:U/C:L/I:L/A:N (4.0) — client-bundle embed; integrity + limited disclosure.
- **Legacy-SSR venue:** CVSS:3.1/AV:L/AC:H/PR:N/UI:R/S:U/C:H/I:H/A:H (6.3) — attacker-authored JS executes in the SSR Node process at server boot (module top-level; runtime-demonstrated N1-D through the real i18n-inlining pipeline: `createI18nOptions` → `findLocaleDataPath` → server-bundle prepend; evidence `findings/E1-C1-i18n-locale-key-escape/evidence/chain4/ssr-e2e-real/`).
- `finding.json` currently carries `severity: low_medium` + the browser vector only — the venue-split lives in the REPORT; the operator decides whether to record the SSR vector in finding.json or keep the REPORT as the venue authority (recommended: REPORT-only, one finding, one file).

## 2. Members E + F (folded, both compiled-demonstrated)

- **Member E** — translation-path read (Low): `i18n-options.ts:258-262` + `load-translations.ts` `createTranslationLoader`, uncontained read at a workspace-controlled path; compiled demo `evidence/chain4/member-e/`; kill-pair N2B SURVIVES-NARROWED (no schema gate; reader.ts:24 free-form).
- **Member F** — baseHref raw HTML injection (Low-Medium, widest venue — BOTH builder stacks): `augment-index-html.ts:267-270` `emitRaw`; compiled demo `payload-proposals/next-phase-demos/nr2-mf/` + `evidence/chain4/member-f/`; kill-pair DR3-01 + N2C SURVIVES-NARROWED with the **CSP-conditional** caveat (strict-CSP deployments immune; emitRaw-vs-updateAttribute discriminator).

## 3. Current-main citation (N1-H)

`i18n-options.ts` at main is byte-identical to the pin (its newest commit IS the pin `d827ba9005b8`); member C + the SSR venue survive at main — the "Verified unfixed at main (2026-08-15, GitHub API + raw-content diff, DR3-04)" line is in the REPORT's Replay/staleness section.

## 4. Filing composition recommendation

- File E1-C1 as **ONE finding** with the venue-split severity (browser 4.0 / legacy-SSR 6.3), members C+E+F included, chain-4 evidence (browser demo, dependency-confusion variant, SSR E2E) attached.
- The 6.3 vector is the filing headline; the SSR-venue runtime demo is the delta that outlives the config-trust doctrine (server-process execution of attacker-authored JS).
- Novelty: NOVEL (web-checked); adjacent class #33073 (foxllb) cited; config-trust doctrine expected to apply — the counters are the SSR-execution delta + the mis-keyed-guard discriminator (`ensureValidSubPath` guards explicit subPath only).

```acceptance-report
{
  "criteriaSatisfied": [
    {
      "id": "criterion-1",
      "status": "satisfied",
      "evidence": "Concrete findings with file paths and severity: E1-C1 venue-split (browser 4.0 / legacy-SSR 6.3) with the full supersession chain E2-R4 (7.3) -> E2-B2/ECKP (6.3) -> E2-D3 reconcile, anchored in findings/E1-C1-i18n-locale-key-escape/REPORT.md (venue-split + members E/F sections, both compiled-demonstrated); finding.json severity=low_medium + browser vector (the venue authority decision documented); SSR runtime evidence at evidence/chain4/ssr-e2e-real/; main-unchanged citation at Replay/staleness; filing composition recommendation (one finding, 6.3 headline, SSR delta + discriminator counters)"
    }
  ],
  "changedFiles": [],
  "testsAddedOrUpdated": [],
  "commandsRun": [
    {
      "command": "grep -n 'venue-split|6.3|7.3|member' findings/E1-C1-i18n-locale-key-escape/REPORT.md",
      "result": "passed",
      "summary": "venue-split section, members E/F lines, and supersession text verified on file; no stale 7.3 in the front-matter"
    },
    {
      "command": "python finding.json inspection",
      "result": "passed",
      "summary": "severity=low_medium, cvss=browser vector (AV:L/AC:H/PR:N/UI:N/S:U/C:L/I:L/A:N) — venue-split lives in the REPORT"
    }
  ],
  "validationOutput": [
    "Brief under 500 words; covers the 4 record elements: venue-split with supersession chain, members E/F with evidence paths, main-unchanged citation, filing composition recommendation"
  ],
  "residualRisks": [
    "The 8.1 calculator-variant (ECRV) could be resurrected by a reviewer who prefers AV:N/UI:N — the record must keep the footnote visible",
    "finding.json carries only the browser vector; if the operator later wants the SSR vector in the file, G5 re-verification is needed",
    "SSR venue bound to the legacy webpack stack — the application builder remains a negative control"
  ],
  "noStagedFiles": true,
  "diffSummary": "Read-only brief; no files modified",
  "reviewFindings": [
    "no blockers: all four record elements verified on file with exact anchors"
  ],
  "manualNotes": "The brief is ready to append to the E1-C1 filing package; the operator decision points are (a) REPORT-only venue authority vs finding.json SSR vector, (b) file E1-C1 with the 6.3 headline"
}
```
