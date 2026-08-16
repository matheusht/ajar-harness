# M2 — filing opening (FINAL, next-phase N3)

**Delta-first, 348 words:**

---

MCP servers advertise a containment boundary: every tool is confined to the client's declared roots. `get_best_practices` breaks it in a way the boundary cannot see. The tool validates its *input* workspace path against the roots, then hands that path to Node module resolution — `createRequire(workspacePath).resolve('@angular/core/package.json')` — which walks the workspace's `node_modules` and then **every ancestor** up to the filesystem root. The resolved package's `angular.bestPractices.path` guide is read with a raw `readFile` that is never re-checked against the roots, and returned to the assistant with `{ audience: ['assistant'], priority: 0.9 }` — attacker-influenceable content injected into the agent's context as protocol-flagged instructions. Demonstrated byte-for-byte at the pin (both input forms), and re-confirmed at the pin after the upstream input fix landed: the three root-enforcement commits (34e1e0bb5/2b060630c/24fd8fce2) cover the input; the ancestor-walk residual stands, undisclosed.

The same tool surface carries a second, mechanically proven channel. `run_target` accepts free-form option values, passes them verbatim as `--key=value`, and never checks them against the restricted host — the builder then resolves `tsConfig`/`browser`/`main`/`polyfills` paths with `path.join`, so a relative `..` traversal reads out-of-roots parseable files into the build artifact. A refined-stealth shape (N2F) survives even a hardened agent: an option value hidden behind a legitimate-looking build step shows no anomaly in the tool call at all, so the "flag the visible `..`" defense never triggers.

Capped honestly: a shell-capable agent could exfil visibly — the delta is stealth and steerability, not capability; the shell-less client population (desktop assistants) is real but the chain is armed, not demonstrated end-to-end. Severity: Low-Medium.

**Recommendation: file now.** The residual is undisclosed, the mechanism is live at the pin and verified unchanged at main, and the fix (scope `createRequire` with `paths: [workspace/node_modules]`) is a one-line containment. Filing as the residual + run_target amplifier with the chain as context, not as a generic prompt-injection report — the mis-keyed-guard discriminator is the claim.

```acceptance-report
{
  "criteriaSatisfied": [
    {
      "id": "criterion-1",
      "status": "satisfied",
      "evidence": "Opening grounded in the on-file M2 REPORT (findings/M2-mcp-best-practices-roots-escape/REPORT.md): residual ancestor-walk claim with exact anchors (best-practices.ts createRequire chain, workspace-utils.ts isAllowedWorkspacePath input-only, priority 0.9 annotation), re-PoC evidence (evidence/repoc-pin/, MARKER-ATTACKER-GUIDE-2), run_target amplifier (KP-M2RT relative-..-traversal correction, options verbatim), N2F stealth-shape refinement (blind-harness refusal of visible anomaly; one-level indirection survives — M2 REPORT trigger section updated N2), and the M2FD file-now recommendation. Word count 348 (under the 350 limit)."
    }
  ],
  "changedFiles": [],
  "testsAddedOrUpdated": [],
  "commandsRun": [
    {
      "command": "read findings/M2-mcp-best-practices-roots-escape/REPORT.md (sections: one-sentence, mechanism, PoC, deep-phase status, run_target amplifier, trigger)",
      "result": "passed",
      "summary": "All claim anchors, evidence refs, and the current trigger language verified on file"
    }
  ],
  "validationOutput": [
    "Opening length: 348 words (limit 350). Severity Low-Medium consistent with finding.json. Delta-first framing per the M2FD recommendation; doctrine-adjacent citations (#32509-style) not required for M2 (no prior disclosure of the residual channel)."
  ],
  "residualRisks": [
    "The shell-less population chain remains armed-not-demonstrated — the opening states this rather than claiming it",
    "Operator re-authors before filing (harness rule); line numbers and the 1MB cap are quoted from the pinned report"
  ],
  "noStagedFiles": true,
  "diffSummary": "Read-only lane; no engagement files modified; filing opening returned inline",
  "reviewFindings": [
    "no blockers: every factual claim in the opening traces to the pinned M2 REPORT, the re-PoC evidence, or the N2 round record"
  ],
  "manualNotes": "The parent may copy this block into the M2-filing-package.md opening section (payload-proposals/M2-filing-package.md) or save as payload-proposals/M2-filing-opening-final.md."
}
```
