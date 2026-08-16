# W1 Filing-Viability Operator Note (Lane OP-W1-viability, deep phase E1-R11)

**Finding:** `findings/W1-yarn-classic-disttags-win32/REPORT.md` — yarn-classic/ng-update win32 command injection via unvalidated registry `dist-tags` values (Low-Medium; finding #6; all 7 gates CLEAR).

---

## (a) The delta-first framing (what a filing must open with — NOT the mechanism)

W1 is not a first report: the sink class was triaged by the maintainers as **#32509 (2026-03, `severity6: security`, same injection shape)**, the full fix PR **#32892 was REJECTED**, and a **won't-fix doctrine was documented 2026-03-27** (package-manager specifier handling under config-trust). A triager who has seen that doctrine will reject a mechanism-first writeup. The filing's load-bearing opening must be the *narrow delta* the doctrine did not cover:

1. **Registry-controlled VALUE channel, not specifier construction.** The doctrine covered the specifier-construction class; W1's channel is the unvalidated `dist-tags` VALUE (`metadata['dist-tags'][versionSpec]`, package-manager.ts:572-590 / update-resolver.ts:604-627) — no semver/charset validation anywhere (`isReleaseAgeSatisfied` passes everything; default `minReleaseAge = 0`). This specific channel is **undisclosed** (searched; no issue/PR/advisory).
2. **Pre-gate invisible execution.** The injection fires during the metadata fetch (`loadPackageInfoTask`, add/cli.ts:520-531) BEFORE the confirmation task (:570) and the install task; the non-TTY abort does not prevent the already-executed fetch+injection. In `ng update` there is **no confirmation gate at all**, and the `semver.lte` throw (update-resolver.ts:527) fires AFTER the spawn — post-injection masking, not a preventive gate (kill-pair order proof, E1-R2/X3).
3. **Manager-independent update entry (E1-R8/FS-W1 widening).** The `ng update` dist-tags entry resolves for EVERY package manager (npm default included) via `getRegistryManifest` (update-resolver.ts:50-55, :662/:727/:534) → the same quote-wrap (package-manager.ts:515-523) → win32 `shell:true` spawn (host.ts:161-164). The yarn-classic-only cap applies to the `ng add` metadata-fetch path only.
4. **PackageGroup multi-spawn.** Group members inherit the malicious version → additional `getRegistryManifest` spawns per member.
5. **Automated/bot reach.** `ng update` runs in pipelines — no human confirmation between fetch and spawn.

Supporting citations (mandatory): #32509, #32892 (rejected), #32678 (git-executor-only fix), `85e3ce2e0` (quote-wrap, the bypass vehicle), `d8b76e93d` (dist-tag lookup). Co-credit risk: same-day same-reporter cluster **#33074-77 (foxllb, 2026-04-28)** on adjacent injection surfaces — disclose it.

## (b) Doctrine risk assessment

- **Precedent weighs against acceptance as a "new" report.** The maintainers triaged the class severity6, then rejected the full fix and documented config-trust doctrine. Expect the first response to be "covered by #32509/#32892 decision" unless the delta framing lands in the first paragraph.
- **The delta is real but narrow.** The registry-VALUE channel + pre-gate timing + update-resolver multi-call-site reach are genuinely outside the rejected fix's scope (the rejected fix addressed specifier quoting/escaping, not unvalidated value interpolation at the source). Novelty of the exact channel is confirmed undisclosed.
- **An active independent researcher is on this surface** (foxllb cluster) — novelty of adjacent channels may erode quickly; timing matters.
- **Verdict impact:** the doctrine makes acceptance probabilistic rather than certain; it does NOT make the finding wrong (mechanism source-verified at the pin; the won't-fix doctrine is a triage posture, and the delta falls outside its stated scope).

## (c) Filing options

| Option | When | What it requires |
|---|---|---|
| **File-with-delta** | Now (static-only) | The delta-first writeup (a) + all five citations + the foxllb disclosure; accepts that the first response may cite the doctrine. `FILING-COVER.md` row: "file-with-Windows-rung OR hold" — static is defensible because every hop is source-verified and the fixture documents the exact commands. |
| **Hold-until-Windows-rung** | Until a Windows host is available | Run `WINDOWS-E2E-FIXTURE.md` (local synthetic registry, method-2, no wires) to close the single evidence-grade gap (physical cmd.exe execution). Strongest posture against a doctrine-dismissal. Cost: indefinite delay — no Windows layer exists in-lab (Darwin/arm64; no wine/qemu/VM; Docker Linux-only), and the foxllb co-discovery risk grows while waiting. |
| **Don't-file** | Only if the operator concludes the doctrine makes filing value-negative | The delta (registry-value channel, undisclosed, pre-gate, manager-independent) is real and documented in the report; choosing not to file leaves an unpatched injection in the default `ng update` flow on win32. |

**Recommended:** file-with-delta now (static argument), with the Windows E2E offered as the follow-up rung if the maintainers request execution evidence. The delta is strong enough that holding until an indefinite Windows run is the worse option on balance (doctrine-dismissal risk is equal either way; co-discovery risk grows with delay).

## (d) What a Windows run would add

The single evidence-grade gap: **observed cmd.exe execution**. A run of the fixture on any Windows host would add:
- The physical marker-execution output (`calc`/marker command running under `cmd.exe /c yarn info --json --verbose "pkg@1.0.0" & <marker> & ""`) — turning "source-verified chain" into "execution-observed chain".
- Negative-control confirmation on the same host (benign dist-tags value → no injection; POSIX array-spawn control).
- Pre-gate timing observation (injection fires before the confirmation prompt; the non-TTY abort does not prevent it).
- Nothing else changes: severity, vector (CVSS 3.1/AV:N/AC:H/PR:N/UI:R/S:U/C:H/I:H/A:H), caps (win32 + registry-control + yarn-classic-for-add / manager-independent-for-update), and the doctrine framing are all unaffected by the rung.

---

```acceptance-report
{
  "criteriaSatisfied": [
    {
      "id": "criterion-1",
      "status": "satisfied",
      "evidence": "Returned the W1 filing-viability operator note with concrete file paths and severities: findings/W1-yarn-classic-disttags-win32/REPORT.md (Low-Medium; doctrine section, X3 amplifier with order proof at update-resolver.ts:527/:947-992, FS-W1 manager-independent widening at update-resolver.ts:50-55/:662/:727/:534, static-only argument with exact line anchors package-manager.ts:572-590 / host.ts:157-164 / add/cli.ts:520-531), payload-proposals/FILING-COVER.md row 11 (file-with-Windows-rung OR hold), L9c verdict facts (#32509 severity6, #32892 rejected, won't-fix 2026-03-27, foxllb cluster #33074-77). All four requested parts (delta framing, doctrine risk, filing options, Windows-rung delta) returned as markdown with a recommendation."
    }
  ],
  "changedFiles": [],
  "testsAddedOrUpdated": [],
  "commandsRun": [
    {
      "command": "grep -n 'DOCTRINE|AMPLIFIER|FILING|viability' findings/W1-*/REPORT.md + grep W1 payload-proposals/FILING-COVER.md",
      "result": "passed",
      "summary": "located doctrine/amplifier/static-argument sections and the FILING-COVER W1 row"
    },
    {
      "command": "sed -n 30,80p findings/W1-yarn-classic-disttags-win32/REPORT.md",
      "result": "passed",
      "summary": "read the full doctrine, amplifier, reachability-cap, and static-argument text for the note"
    }
  ],
  "validationOutput": [
    "Note grounded exclusively in the REPORT doctrine/amplifier sections, the L9c verdict facts, and FILING-COVER.md; delta-first framing preserved verbatim from the report's own filing-viability note; recommendation (file-with-delta now, Windows E2E as follow-up) is an operator input, not a claim change."
  ],
  "residualRisks": [
    "Physical cmd.exe execution remains environment-blocked (no Windows host in-lab) — the note's recommendation depends on the static-only argument being accepted by the triager, which the doctrine makes probabilistic",
    "foxllb same-reporter cluster (#33074-77) may independently disclose the registry-value channel before filing — co-discovery risk grows with any delay",
    "Severity/vector unchanged by this lane; operator re-verifies line numbers and CVSS against finding.json before any submission"
  ],
  "noStagedFiles": true,
  "diffSummary": "Read-only lane; no files modified; operator note returned inline only",
  "reviewFindings": [
    "no blockers",
    "info: the FILING-COVER.md row already carries the doctrine warning and the file-with-Windows-rung OR hold options — the note adds the per-option analysis and a concrete recommendation",
    "info: the delta (undisclosed registry-VALUE channel + pre-gate timing + manager-independent update reach) is the only counter to the documented won't-fix doctrine; any filing must open with it"
  ],
  "manualNotes": "Operator decision point (HIGH): choose file-with-delta-now vs hold-until-Windows-rung. If filing, the delta-first opening, the five citations (#32509/#32892/#32678/85e3ce2e0/d8b76e93d), and the foxllb disclosure are mandatory. The Windows E2E fixture (WINDOWS-E2E-FIXTURE.md) is ready for any future Windows host; running it closes the only evidence-grade gap."
}
```
