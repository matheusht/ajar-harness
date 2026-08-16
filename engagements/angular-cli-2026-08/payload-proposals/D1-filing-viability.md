# D1 FILING-VIABILITY NOTE (operator decision input, E1-R11)

**Finding:** D1 — `--route` codegen injection · **Severity:** Low-Medium (CVSS:3.1/AV:L/AC:H/PR:N/UI:N/S:U/C:N/I:L/A:N ≈ 3.7) · **Gates:** 7/7 CLEAR · **Source:** `findings/D1-route-codegen-injection/REPORT.md`, `payload-proposals/FILING-COVER.md` row 12

## (a) The delta vs the rejected #33074/#33076 family

The family (option/config string → generated code) was disclosed and **REJECTED** (closed not-a-vuln 2026-04-28, `severity6: security` triage labels) under the maintainers' config-trust doctrine. D1's counter is a *four-part delta*, each part verified:

1. **Exact sink novel.** Neither #33074 (SSR manifest `baseHref`) nor #33076 (unescaped `server` entry path) covers the schematics `--route` option. The sink shape is unpatched at the pin (module/index.ts:129-136, schema no pattern; the #33076 sink at application-code-bundle.ts:345-366 is also unchanged — the family was rejected, not fixed).
2. **CLI-flag reach (not config-only).** `--route` is a direct CLI flag on `ng generate module --route <value>` — the value is attacker-supplied at the command line, not a committed config file. This is the sharpest part of the delta: it does NOT depend on the config-trust premise the doctrine was built on. (The config-default channel is also live but is the weak flank — see (b).)
3. **Production-SSR execution.** The injected top-level code executes at module import in the SSR/prerender production server (E10: `extractRoutesAndCreateRouteTree` → `platformServer` bootstrap, ng-routes.ts:621-640; eager case at build/startup, lazy at server-side render of the injected route) — payload ships in the SSR bundle. Confidentiality impact conditional on the deployed SSR bundle, but the execution venue is beyond "dev machine only".
4. **Comma-exec payload empirically verified.** KP-E10 correction: the original demo payload was invalid TS; the comma-exec shape (routes-array context) is 0-error, survives the tree's own esbuild 0.28.2 transpile, and executes at module import (marker empirically confirmed; QA-D1 independently re-verified). A triager cannot dismiss it as "won't compile".

## (b) The config-trust doctrine risk (honest)

- The doctrine's core premise: options/config the developer runs against are trusted (attacker-authored project = dev already executing its content). #33076 was rejected on this basis.
- D1's flag-channel argument **is untested against the doctrine** — no record shows the maintainers adjudicating a *CLI-flag-supplied* injection vs a config-supplied one. The doctrine text (2026-03-27 won't-fix) is written around config-trust; a flag value supplied by an attacker who *also* controls the project is arguably within the same trust sphere (dev runs the command inside the attacker's project).
- **Highest rejection risk:** a reviewer maps D1 onto the family precedent and closes with "same class, same rationale" without engaging the flag-vs-config distinction. The filing MUST open with the delta (flags 2+4 above), never the mechanism.
- **Compounding risk:** the same-day reporter cluster (#33074-77, `foxllb`, 2026-04-28) shows an active independent researcher on this exact surface; co-credit/duplicate-review friction is real.

## (c) Filing options

| Option | When | Notes |
|---|---|---|
| **File-with-delta (delta-first)** | Default | Strongest on the flag-reach + verified-payload combination; frame as sibling-miss in a rejected family with a NEW channel, not a re-litigation. Cite #33074/#33076 WITH rejection status (never "fixed"). |
| **Hold (until evidence strengthens)** | If the operator wants lower rejection odds | The SSR-execution half would be materially stronger with a live SSR-render PoC (production bundle with the injected route rendered — currently the execution is source+transpile-verified, not E2E-rendered). A wait also de-risks the doctrine ambiguity only if public posture changes — not guaranteed. |
| **Don't file** | If the operator weighs the doctrine as determinative | Justified only if the flag-vs-config distinction is judged inoperative; the mechanism evidence (comma-exec, SSR reach) argues against this. |

## (d) What strengthens the case

1. **Maintainer response history (favorable signal):** the family was triaged as `severity6: security` — they *treated* the class as security-relevant before rejecting on trust grounds; a novel channel is a fair re-open. PR #3746/#3761 (dev-infra fork-origin hardening) and the #32892 rejection (W1 family) show maintainers DO act on delta arguments when the channel differs — cite the #33074/#33076 closure comments to show exactly what was rejected, then show the flag channel was not among it.
2. **A live SSR-render PoC** (deployed-style bundle, injected route rendered, marker in server output) would close the last evidence gap and answer the "won't compile / doesn't run in prod" dismissal class pre-emptively.
3. **Operator-side novelty double-check** on the exact `--route` sink (GitHub issues/advisories search for "ng generate module route injection") — L9 checked the family, not this exact string; cheap insurance.

**Bottom line:** file-with-delta is viable and defensible; the delta is real and verified. The doctrine risk is material but not determinative because the flag channel is outside the rejected family's stated rationale. The operator's call should hinge on (a) whether the live-SSR PoC gap is acceptable and (b) the filing venue's tolerance for sibling-miss reports in rejected families.

```acceptance-report
{
  "criteriaSatisfied": [
    {
      "id": "criterion-1",
      "status": "satisfied",
      "evidence": "Operator note returned with concrete file paths and severity: delta vs rejected family (module/index.ts:129-136 sink; #33074/#33076 closed not-a-vuln 2026-04-28; application-code-bundle.ts:345-366 unchanged), comma-exec payload verified with the tree's own esbuild 0.28.2 (REPORT.md KP-E10 section), production-SSR execution venue (ng-routes.ts:621-640), severity Low-Medium CVSS 3.7, gates 7/7 CLEAR, FILING-COVER.md row 12 options table (file-as-is / hold / don't-file)"
    }
  ],
  "changedFiles": [],
  "testsAddedOrUpdated": [],
  "commandsRun": [
    {
      "command": "read findings/D1-route-codegen-injection/REPORT.md (novelty + KP-E10 PoC + SSR reach sections)",
      "result": "passed",
      "summary": "delta components, rejection status, and filing requirement extracted verbatim"
    },
    {
      "command": "grep payload-proposals/FILING-COVER.md D1 row",
      "result": "passed",
      "summary": "cover row confirms file-as-is-or-hold posture and doctrine pushback expectation"
    }
  ],
  "validationOutput": [
    "Four-part delta verified against the report (novel sink, CLI-flag reach, SSR production execution, comma-exec payload empirically confirmed); doctrine risk characterized (config-trust premise, flag-channel untested, family-rejection mapping risk, foxllb cluster); three filing options with decision criteria; strengthening factors (severity6 triage history, #3746/#3761 delta-response precedent, live-SSR PoC gap, exact-string novelty double-check)"
  ],
  "residualRisks": [
    "The config-default channel remains the weak flank of the filing (inside the doctrine premise); the filing should lead with the flag channel",
    "No live SSR-render E2E PoC exists yet — the execution claim is source+transpile-verified; a reviewer demanding a rendered-proof could stall the report",
    "Doctrine ambiguity (flag vs config trust) has no public resolution; rejection remains possible even with the delta",
    "foxllb cluster co-credit/duplicate-review friction"
  ],
  "noStagedFiles": true,
  "diffSummary": "Read-only lane; no files modified",
  "reviewFindings": [
    "no blockers: the delta is source-verified and the operator note is complete",
    "info: the note deliberately avoids the mechanism-first framing (the report's own filing requirement); the flag-vs-config distinction is the load-bearing argument",
    "info: FILING-COVER.md row 12 already carries the file-as-is-OR-hold posture — this note is the reasoning behind it, not a change"
  ],
  "manualNotes": "Parent orchestrator: this is operator decision input, not a claim change. If the operator chooses file-with-delta, the recommended next step is the live SSR-render PoC (payload in a deployed-style bundle, marker in server output) plus the exact-string novelty search before submission."
}
```
