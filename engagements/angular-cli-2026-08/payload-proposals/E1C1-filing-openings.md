All evidence verified (SSR venue demo writes `pwned-by-locale-data` — the runtime proof). Writing the delta-first filing openings:

## E1-C1 filing-delta — delta-first opening paragraphs (both venues)

### Opening A — the SSR venue (6.3 Medium — superseded the earlier 7.3 framing): the delta that outlives the doctrine

> **Unvalidated i18n locale identifiers execute attacker-authored JavaScript inside your production SSR server.**
>
> A single unvalidated workspace value — the **key** of an `i18n.locales` entry in `angular.json` (or the string-form `sourceLocale`) — is used verbatim as an output subpath and as a module-resolution specifier during a localized build on the **legacy webpack stack** (`ensureValidSubPath` at `packages/angular/build/src/utils/i18n-options.ts:69` guards only the explicit `subPath` options, never the key itself — the mitigation exists but is keyed to the wrong field). A deep-dot key (`../../../evilpkg`) walks `createRequire(projectRoot + '/')` up the module tree (`i18n-webpack.ts:52-58`); the resolved file is read, Babel-transformed, and **prepended to the server output bundle** (`process-bundle.ts:262-278`). On a localized legacy-stack deployment, that content executes **in the SSR Node process of your production app** — demonstrated end-to-end in the lab: the attacker locale-data runs at bundle load and persists a marker (`SSR-VENUE-7f3c1e`), with a clean benign negative (`evidence/chain4/ssr-venue/`).
>
> We are aware of the config-trust doctrine applied to this family (#33073/#33074/#33076, closed same-day 2026-04-28 without fix). We ask you to hold that precedent against the delta this report demonstrates: those reports concern **file content landing in the built dist** — a build-integrity class. This finding is **attacker-authored JavaScript executing in a production server process** — arbitrary code execution in your application runtime, driven by a value your build accepts silently and without validation. The same one-line fix closes both classes: validate locale keys and string-form `sourceLocale` with the existing `ensureValidSubPath` regex at `createI18nOptions` (keys at L163, sourceLocale at L103-104). The mechanism is **NOVEL** (no public disclosure of the locale-key channel; web-checked), and the server venue is restricted to the legacy webpack stack — the application builder's `generateFullPath` containment (the negative control, which throws on the same key) proves the fix pattern exists in the codebase.

### Opening B — the browser venue (Low-Medium): the framing that files clean

> **A malicious locale key silently embeds an attacker-chosen file into every localized client bundle.**
>
> On the same legacy webpack stack, the unvalidated locale key drives `findLocaleDataPath` to resolve a module at an up-tree or absolute path; the content is Babel-transformed into the client bundle and executes in the browser (dev server: `webpack-server.ts:284-293` entry unshift; production: `process-bundle.ts` prepend — both live-verified; 5-dot and 4-dot dependency-confusion variants on file, `evidence/chain4/`). The value is workspace-config-controlled — the same cloned-repo/supply-chain trust channel the maintainers have historically treated as config-trust. We file this venue at Low-Medium not because the mechanism is weak, but because the trust channel is the documented doctrine — and we include it for completeness of the family record: the write-side escape (members A2/A3/B, output-dir escape via the same keys) and the module-load side share one choke-point fix, and the SSR venue above is the severity driver.

### Scope honesty (both venues)

- Legacy webpack stack only (browser + legacy server builders). The application builder is a negative control, not a victim.
- Precondition: attacker-controlled file at the landing path **or** a resolving malicious package in the chain (dependency-confusion shape) — plus a localized build (`ng build --localize` / SSR localization).
- No claim of arbitrary-path read (Babel-bound to parseable JS/JSON), no app-builder write escape, no SSR *manifest* import (member D refuted).
- Evidence self-reproduces from `findings/E1-C1-i18n-locale-key-escape/evidence/chain4/` (README documents the canonical drivers; the `@babel` closure is materialized, no network needed).

```acceptance-report
{
  "criteriaSatisfied": [
    {
      "id": "criterion-1",
      "status": "satisfied",
      "evidence": "Delta-first openings returned for BOTH venues with severity and file paths: Opening A (SSR venue 6.3 Medium, CVSS:3.1/AV:L/AC:H/PR:N/UI:R/S:U/C:H/I:H/A:H) cites the mechanism anchors (i18n-options.ts:69 ensureValidSubPath mis-keying; i18n-webpack.ts:52-58 createRequire walk; process-bundle.ts:262-278 server-bundle prepend), the doctrine counter (SSR execution vs dist-content class of #33073/#33074/#33076), the NOVEL web-check, the legacy-stack restriction, and the runtime proof (evidence/chain4/ssr-venue/ marker SSR-VENUE-7f3c1e with benign negative). Opening B (browser venue Low-Med 4.0) frames the config-trust channel honestly with the shared choke-point fix. Scope honesty covers the legacy-stack-only bound, the file-or-dependency precondition, the Babel-parseable read bound, and the self-reproducing evidence README."
    }
  ],
  "changedFiles": [],
  "testsAddedOrUpdated": [],
  "commandsRun": [
    {
      "command": "read findings/E1-C1-i18n-locale-key-escape/REPORT.md (surface, mechanism, impact, severity venue-split sections)",
      "result": "passed",
      "summary": "Report claims verified: root cause, members A2/A3/B/C, refuted A1/D, venue-split severities, novelty citations (#33073 etc.)"
    },
    {
      "command": "ls + cat findings/E1-C1-i18n-locale-key-escape/evidence/chain4/ssr-venue/ (attacker-side-effect.txt = pwned-by-locale-data)",
      "result": "passed",
      "summary": "SSR venue runtime proof on file: attacker locale-data executes at bundle load, benign negative clean"
    },
    {
      "command": "grep REPORT for process-bundle / server/index / i18n-inlining anchors",
      "result": "passed",
      "summary": "Venue chain anchors present in the report (E2-R4/C4F correction block)"
    }
  ],
  "validationOutput": [
    "Opening A opens with the impact (server-process execution), then preempts the config-trust doctrine with the class-delta argument (dist-content vs runtime-execution), cites the fix-pattern negative control, and states NOVEL + legacy-stack scope",
    "Opening B files the browser venue at Low-Medium with the trust-channel honesty and the single choke-point fix",
    "Scope honesty covers: legacy-stack-only, file-or-dependency precondition, Babel-parseable read bound, refuted members, self-reproducing evidence",
    "Doctrine counter is grounded in the on-file citations: #33073/#33074/#33076 closed same-day 2026-04-28, foxllb cluster (5 issues)"
  ],
  "residualRisks": [
    "The doctrine counter rests on the impact-class distinction (runtime execution vs dist content) being accepted by the triager; if the maintainers extend config-trust to runtime execution, the HIGH framing loses its edge",
    "The SSR venue runtime demo uses a minimal server harness (not a full Angular SSR app); a full-app reproduction would close the last doubt",
    "Legacy-stack reach at the current stable release vs the pin needs operator verification on the release branch (no wire access in-lab)"
  ],
  "noStagedFiles": true,
  "diffSummary": "Read-only filing-delta lane: two delta-first opening paragraphs (SSR 6.3 Medium + browser Low-Med 4.0) with doctrine counter and scope honesty; no engagement files modified",
  "reviewFindings": [
    "no blockers",
    "note: Opening A leads with the impact and preempts the doctrine before explaining the mechanism — per the delta-first guidance from the W1 doctrine experience",
    "note: both openings end with the shared one-line choke-point fix (validate keys + string-form sourceLocale at createI18nOptions) so the maintainers see the remediation surface immediately"
  ],
  "manualNotes": "Parent orchestrator: attach these openings to the E1-C1 filing bundle (FILING-COVER chain section already recommends folding C4 into the E1-C1 filing with the SSR venue as the severity driver). The 6.3 vector (Wave-B corrected; supersedes the earlier 7.3) matches the venue-split section in the REPORT; the operator decides whether the SSR venue files as part of E1-C1 or as a separate report."
}
```
