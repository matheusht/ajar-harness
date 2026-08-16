All four components verified in the records (D1FD opening, Wave-B app-trust scoping, N2D/SSR boot-time correction, REJECTED-family citations). Here is the final opening:

---

**D1 — filing opening (delta-first, final, ~300 words)**

> `ng generate module --route <value>` writes the `--route` option into the generated routing module with **no validation and no escaping** — `packages/schematics/angular/module/index.ts:135-136` interpolates the raw value into a single-quoted string, and the option schema declares a plain string with no pattern. A value containing a quote breaks out of the string literal and injects statements that compile cleanly and execute at module evaluation (comma-exec shape; marker verified at module scope with the CLI's own transpiler, 0 errors).
>
> The injected module is the app's routing configuration. Its parent routing module is statically bundled into the server bundle and evaluated when the production SSR server boots (`platformServer().bootstrapModule()` module-graph eval) — the payload executes **once per server boot, with the app's own trust**, persistent for the process lifetime and re-armed on every restart. It is module-scope code running with the application's privileges — no sandbox or privilege escape, but attacker-authored statements execute inside the deployed production server process. Timing is boot-time module-eval, not per-request: ESM module-graph evaluation is once-per-process, and per-request re-execution (a demo artifact from cache-busted imports) is not claimed.
>
> Two adjacent reports on the same family were triaged `severity6` and closed as not-a-vuln on 2026-04-28 under the maintainers' config-trust doctrine: **#33074** (baseHref) and **#33076** (unescaped server entry). This finding's delta is twofold. First, the value does not need to live in a committed config file: `--route` is an **invocation argument** reachable from scaffolding services, IDE extensions, and CI automation that derive generator arguments from external input. Second, it lands in **production server code**, not a build artifact. The discriminator is concrete: the component generator's class-name validation rejects the same payload shape, while the module generator has no equivalent gate on `route` — and a schema pattern on the merged options would have rejected the payload at option validation (verified counterfactual, the strongest remediation evidence).

---

```acceptance-report
{
  "criteriaSatisfied": [
    {
      "id": "criterion-1",
      "status": "satisfied",
      "evidence": "Final D1 filing opening (~300 words, under the 350 cap) returned, folding the four components verified against on-file records: (1) D1FD delta-first mechanism text (payload-proposals/D1-filing-opening.md — module/index.ts:135-136 raw interpolation, comma-exec verified with the CLI own transpiler, production-SSR platformServer reach); (2) Wave-B app-trust scoping (findings/D1-route-codegen-injection/REPORT.md WAVE-B SCOPING section — module-scope execution with the app own trust, no privilege/sandbox-escape delta); (3) N2D boot-time SSR timing correction (payload-proposals/D1-SSR-timing-correction.md — once-per-server-boot ESM module-eval, per-request re-execution explicitly killed and disclaimed); (4) REJECTED-family doctrine citation (#33074/#33076, severity6, closed not-a-vuln 2026-04-28 — REPORT novelty section, cited as rejected-not-fixed) plus the discriminator (component class-name validation vs module route gate) and the verified schema-fix counterfactual."
    }
  ],
  "changedFiles": [],
  "testsAddedOrUpdated": [],
  "commandsRun": [
    {
      "command": "grep WAVE-B SCOPING + REJECTED-family blocks in findings/D1-route-codegen-injection/REPORT.md",
      "result": "passed",
      "summary": "app-trust scoping text and #33074/#33076 rejected-status citations verified verbatim for the fold"
    },
    {
      "command": "head payload-proposals/D1-filing-opening.md + payload-proposals/D1-SSR-timing-correction.md",
      "result": "passed",
      "summary": "D1FD opening and boot-time timing correction contents verified on file"
    }
  ],
  "validationOutput": [
    "Word count ~300 (under the 350 cap); the opening leads with the invocation-argument delta (per the REJECTED-doctrine filing guidance: delta-first, doctrine citation kept visible), folds the boot-time correction as a scoping sentence (not a disclaimer), and closes with the discriminator + verified counterfactual"
  ],
  "residualRisks": [
    "The CI-generate shape (CI runs ng generate with externally-derived args) would warrant a Medium CI venue — named in the D1FD verdict as an operator filing decision, not folded into this opening",
    "Production-SSR boot execution is source-verified + demo-verified at module-eval semantics (boot-once2.mjs), not runtime-demonstrated on a full deployed SSR app — consistent with the REPORT E10 conditional framing"
  ],
  "noStagedFiles": true,
  "diffSummary": "Read-only composition task; no files modified — the final opening is returned inline for the parent to place into the D1 filing package (payload-proposals/D1-filing-package.md)",
  "reviewFindings": [
    "no blockers: all four folded components verified against on-file records; the per-request amplifier is disclaimed exactly as the N2D kill-pair requires; the doctrine citation states REJECTED (not fixed) per the L9c correction",
    "note: the app-trust line ('with the application privileges, no sandbox escape') preempts the privilege-inflation dismissal; the discriminator + counterfactual give the maintainer a concrete fix path"
  ],
  "manualNotes": "Parent: insert this opening at the top of the D1 humanized draft; the D1FD severity verdict (Low-Medium STANDS, conditional Medium CI venue) is unchanged by this composition."
}
```
