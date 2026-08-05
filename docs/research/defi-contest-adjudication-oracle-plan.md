# Deep-research + oracle plan: DeFi contest-adjudication (Code4rena / Sherlock / Immunefi) corpus

> Status: research plan, ready for operator review. This document does not itself authorize a run.

Same discipline and document shape as the CVSS severity-precedent, GHSA fix-diff, REJECTED/DISPUTED
CVE, HackerOne disposition, and Project Zero + ZDI chain plans: mine real disclosed artifacts that
carry their own verdict, re-verify each at a primary authority, land them as calibration anchors + a
backing corpus with "Contested"/"Dropped" sections. This is proposal **#6** of the deep-research-corpus
agenda (the first blockchain-domain pass) and the grounding half of the crypto/fintech capability
investment. The axis is the **judged smart-contract audit-contest finding** and its **public
adjudication** — Code4rena and Sherlock final judged reports and Immunefi disclosed reports + the
Immunefi Vulnerability Severity Classification System.

The distinguishing property versus the sibling passes: those mine web-application bug-bounty triage
(HackerOne) and CVSS/CWE precedent (NVD) — the **web/infra** severity and disposition world. This one
mines the **DeFi / smart-contract** world, whose severity model is categorically different: not CVSS,
but **impact × likelihood denominated in funds at risk** ("attacker gains X, protocol loses Y"), and
whose dedup ground truth is the harshest that exists publicly — contests literally merge hundreds of
duplicate submissions into one canonical finding and publish the grouping. It is the missing
blockchain analog of both the HackerOne-disposition and severity-precedent siblings, in one corpus.

---

## 1. ROLE and the gap it closes

**What it is.** For each judged finding, fetch the primary record — a Code4rena final report
(`code4rena.com/reports/<contest>`) backed by its `code-423n4/<contest>-findings` issue (severity
label, `duplicate-of`, `sponsor confirmed`/`sponsor disputed`, `unsatisfactory`/`nullified`), a
Sherlock judged issue (`audits.sherlock.xyz/contests/<n>` + `sherlock-audit/<contest>-judging`
escalation resolutions), or an Immunefi disclosed report + the ISVCS severity tier — and extract a
structured tuple: the **finding class** (reentrancy, oracle/price manipulation, access control,
rounding/precision, signature replay, donation/first-depositor, etc.), the **judged validity**
(valid / invalid / known-issue / out-of-scope / duplicate), the **judged final severity** (High /
Medium / Low / QA / Gas, with the impact×likelihood rationale), any **severity re-classification**
(reported vs judged), the **duplicate-merge group** it belongs to, and the **judge/head-of-judging
rationale**. Code4rena and Sherlock carry the *adjudication verdict + dedup grouping* explicitly;
Immunefi carries the *canonical severity taxonomy* and disclosed real-loss reports. All are primary
disclosures with a built-in, third-party-adjudicated verdict (the judge ruled; the sponsor
confirmed/disputed), not a researcher self-claim.

**The gap, grounded in the readers.**
- **`skills/oracles/adjudication-oracle.md` "What does NOT count" (§42) + its calibration block (§48)
  rest entirely on HackerOne web dispositions.** Verbatim, the only "real disposed non-findings"
  calibration is "(calibration — HackerOne dispositions)". There is **no** smart-contract disposition
  evidence: no "requires the admin to be malicious → invalid", no "known-issue already in the
  automated-findings report", no "user-error / griefing-only", no "external requirement not
  satisfied" — the exact invalid-classes that dominate DeFi contest triage and that the harness will
  face the moment it audits a contract. Contest judging is the densest public "what does NOT count"
  corpus for this domain.
- **`skills/oracles/severity-precedent-oracle.md` is CVSS/CWE-shaped and web/infra-only.** Its
  reference table (§80) is keyed by CWE (SSRF, IDOR, XSS, SQLi…) and its cross-check (§44) is
  "program-assigned severity + bounty (HackerOne)". DeFi severity is **not** CVSS — it is
  impact×likelihood over funds at risk, and a "High" often requires *no* CWE at all (a rounding
  direction, a missing slippage bound). The oracle has no DeFi-native severity precedent; this pass
  adds it as a parallel cross-check section, never touching the CWE table.
- **`engine/regrade.md` §3/§4 has thin worked examples, and its DeFi disposition/severity
  re-derivation is absent.** `confirmed_with_correction` and `refuted` leaned on web/PP and the P0/ZDI
  anchor (line 93). Contest judging supplies dense, published **downgrades** (reported High → judged
  Medium because likelihood is bounded) and **invalidations** (reported vuln → judged known-issue /
  user-error) by a hostile adjudicator — precisely the "re-derive, trust nothing" evidence §4 is built
  on, in the blockchain domain.
- **`engine/chainability.md` dedup + §3b has no DeFi basis.** Contest duplicate-merge groups are
  literal ground truth for "these N reports are the same finding" — the exact dedup discipline the
  chainability/adjudication layers assert but cannot currently calibrate against real clusters; and
  DeFi's canonical *composed* Highs (flash-loan → oracle manipulation → drain; donation → share-price
  inflation → theft) are multi-step chain shapes absent from the web-shaped §3b.

**Why this is the same template as the sibling passes.** Terse consumption anchors keyed by axis + a
backing corpus where every row is re-verified verbatim at a primary authority, with explicit
"Contested"/"Dropped". Proven five times now (severity 314 vectors, GHSA 127 diffs, rejected/disputed
41 anchors, HackerOne dispositions 80 rows, P0/ZDI 36 chains), each with the grep-vs-corpus +
independent-re-fetch anti-hallucination gate.

**What it is NOT.**
- **Not a smart-contract vuln-card pass.** This grounds the **judgment layer** (validity, severity,
  dedup) for the DeFi domain; it does not author Solidity/Move vuln cards or contract-audit tooling.
  Those are a separate capability build the corpus will later anchor. Respect that boundary.
- **Not a live-bug or exploit pass.** Every item is a disclosed, judged, closed finding. The corpus is
  the finding **class + adjudication + severity rationale**, never a weaponized reproduction, an
  exploit primitive, or a step-by-step drain against a live protocol.
- **Not a CVSS re-scoring.** DeFi contest severity is impact×likelihood, not a CVSS vector. It lands as
  a *parallel* precedent cross-check; it never rewrites the CWE-keyed severity table or claims a CVSS
  number the judge didn't assign.

---

## 2. HARD RULES

1. **Primary adjudicated disclosure only — the judge's record, never an aggregator.** Admissible
   sources: the Code4rena final report + its `code-423n4` findings issue; the Sherlock contest report +
   `sherlock-audit` judging/escalation repo; an Immunefi disclosed report or the ISVCS document. A
   "top DeFi hacks" roundup, a solodit/aggregator entry used as the *only* source, or a researcher's
   own blog claiming a bug is never the cited source (the explicit anti-#17 rule). Solodit may be used
   to *locate* a finding, but the cited source must be the judge's primary record.
2. **The judged verdict is the ground truth, not the submitter's claim.** IN only with the *final*
   adjudication: the severity the judge assigned (post-escalation for Sherlock), the validity the judge
   ruled, and the dedup group the judge merged into. A submitter's self-asserted "High" that the judge
   downgraded is recorded as the *downgrade*, never as a High.
3. **Validity, severity, dedup grouping, and the judge rationale are copied from the primary record,
   not reconstructed.** Quote/paraphrase the judge's stated reason faithfully with the source anchor;
   never infer a rationale the report doesn't give. If the report gives only a label with no rationale,
   record it and flag `thin_rationale`.
4. **Respect the judgment-layer boundary.** Findings ground the adjudication/severity/dedup oracles as
   **calibration anchors**. This pass does not create DeFi vuln cards, does not add a CVSS vector to the
   severity table, and does not promote any chain shape into chainability §3's canonical angles (§3b
   candidates only, per that card's promotion rule).
5. **Disposition extraction is quote-bounded.** Contest reports mix judge prose, sponsor comments, and
   submitter text. Extract only the *judge's* verdict and stated reason; mark sponsor/submitter claims
   as such, never as the adjudicated fact. Where a severity is disputed and escalated, record the
   *final* head-of-judging resolution and flag the reclassification.
6. **Class + disposition diversity is the acceptance criterion, not volume.** Cap any single finding
   class (e.g. reentrancy) and any single contest so the corpus spans the real DeFi class space
   (reentrancy, oracle/price manipulation, access control, arithmetic/rounding, first-depositor/share
   inflation, signature/replay, slippage/MEV, governance, upgrade/init, accounting) **and** the full
   disposition space (valid-High/Med/Low, invalid, known-issue, OOS, duplicate, downgraded).
7. **Defensive artifact only** — finding class, judged disposition, severity rationale, dedup grouping.
   Never a reproduction, an exploit primitive, an address of a currently-vulnerable contract, or a
   step-by-step weaponization.

---

## 3. SOURCES

- **Code4rena (primary, structured + adjudicated).** `code4rena.com/reports/<contest>` — the final
  report groups findings by judged severity (High/Medium/QA/Gas) with the judge's summary; the backing
  `github.com/code-423n4/<contest>-findings` issues carry per-issue labels
  (`2 (Med Risk)`/`3 (High Risk)`, `duplicate-of`, `sponsor confirmed`/`sponsor disputed`,
  `unsatisfactory`, `nullified`, `withdrawn`). Best for **disposition + dedup-group + severity**
  ground truth at volume. The label taxonomy is the built-in oracle.
- **Sherlock (primary, adjudicated + escalation trail).** `audits.sherlock.xyz/contests/<n>` reports +
  `github.com/sherlock-audit/<contest>-judging` — head-of-judging decisions and *escalation
  resolutions* (a submitter contests a severity; the resolution is the final verdict). Sherlock's
  published **judging criteria** (the "will/would happen", "external conditions", Medium-vs-High
  definitions) is itself a canonical disposition rubric. Best for **severity-reclassification worked
  examples** and the adjudication-bar rubric.
- **Immunefi (primary — taxonomy + disclosed real-loss).** The **Immunefi Vulnerability Severity
  Classification System (ISVCS)** — a public, structured smart-contract/blockchain/web severity
  taxonomy (Critical/High/Medium/Low with impact definitions) — is the canonical severity spine. Plus
  Immunefi's disclosed bug reports / whitehat writeups where an adjudicated payout tier is stated. Best
  for the **severity-model backbone** (impact×likelihood → tier) and real fund-loss anchors.
- **Contest judging-criteria docs (primary rubric).** Code4rena's severity categorization docs and
  Sherlock's judging docs — the published rules for what counts and how severity is assigned. Used to
  ground the *rubric*, joined to concrete findings by class.

**Structured/clean:** Code4rena issue labels and the ISVCS tiers (machine-parseable). **Traps:**
(a) submitter self-claim vs judge verdict must be separated (rule 2/5); (b) severities differ across
platforms — a Sherlock "Medium" and a C4 "Medium" have different bars, so record the platform with
every severity; (c) escalations mean the *first* label is not final — resolve the post-escalation
verdict (rule 5); (d) some "findings" are Gas/QA/informational, not vulns — those serve the
disposition axis (as the low end / invalid boundary), not the severity-High precedent set.

---

## 4. METHOD

1. **Bucket by the consumer axis, not by platform.** Three destinations:
   **(A) validity / disposition** (valid vs invalid / known-issue / OOS / user-error / duplicate) →
   `adjudication-oracle.md` "What does NOT count" + `regrade.md` `refuted`/known-issue worked examples;
   **(B) DeFi-native severity precedent** (judged H/M/L with impact×likelihood rationale, and
   reported→judged reclassifications) → `severity-precedent-oracle.md` new DeFi cross-check +
   `regrade.md` §3/§4 downgrade/upgrade examples;
   **(C) duplicate-merge groups + composed-chain shapes** (dup clusters as dedup ground truth; DeFi
   multi-step Highs) → `chainability.md` dedup discipline + §3b DeFi candidate shapes.
   One item may serve more than one axis (a downgraded-on-likelihood High serves A + B; a merged dup of
   a flash-loan chain serves B + C).
2. **Collect the rubric first (structured), findings second (adjudicated).** ISVCS + C4/Sherlock
   judging criteria give the severity/validity spine cheaply; then chunk concrete findings across
   collectors by platform × contest × class. Prefer well-known judged contests with published reports
   over obscure ones (verifiability).
3. **Extract the tuple** — `{ source (C4 report+issue# / Sherlock contest+issue / Immunefi) · protocol
   type (lending/AMM/vault/bridge/staking) · finding class · judged validity · judged severity
   (platform-tagged) · reported→judged reclassification · dedup-group size · judge rationale (quoted)
   · axis · disclosed date · source URL }`.
4. **Dedup structurally.** Diversity of finding-class × disposition × protocol-type, not repeats
   (rule 6). Target roughly 10–18 per axis, hard-capping any single class and any single contest.
5. **The judge is the oracle.** For A, the judge's validity ruling + stated reason is ground truth;
   for B, the judged final severity + impact×likelihood rationale is the severity ground truth; for C,
   the contest's own duplicate-merge grouping is the dedup ground truth and the composed-High is the
   chain shape.

---

## 5. ORACLE GATE — IN / CONTESTED / OUT

- **IN:** the C4 report / Sherlock contest / Immunefi record still resolves and carries the cited
  fields; the item maps to an axis. For A, a clear judged validity ruling with a stated reason; for B,
  a judged final severity with the impact×likelihood rationale (or a clean reported→judged
  reclassification); for C, an explicit duplicate-merge group or a judge-recognized composed-chain High.
- **CONTESTED:** the verdict is real but the rationale is a bare label with no reasoning
  (`thin_rationale`); or the severity is mid-escalation / the resolution is ambiguous; or the platform
  bar makes the severity hard to compare cross-platform (record with the platform flagged); or
  submitter and judge disagree and the final resolution is unclear. Record and label; do not assert the
  missing detail.
- **OUT:** an aggregator/roundup or a submitter's self-claim is the only available source; the finding
  is Gas/informational with no disposition value; the report URL no longer resolves and no archived
  primary exists; or a duplicate class×disposition×protocol already covered (rule 6). Every drop logged
  with reason.

---

## 6. OUTPUT — where it lands

- **A backing corpus — `skills/oracles/references/defi-contest-adjudication-corpus.md`.** Sibling to
  the GHSA/CVE/HackerOne/P0-ZDI reference corpora, per-axis structure with "Contested"/"Dropped".
  Columns: `Source (C4 report+#/Sherlock/Immunefi) | Protocol type | Finding class | Judged validity |
  Judged severity (platform) | Reported→judged | Dedup-group | Judge rationale (quoted) | Axis |
  Disclosed | Source URL`. Per-row provenance flag ("re-fetched this session" vs "second-hand —
  re-verify").
- **Consumption anchors:**
  - `skills/oracles/adjudication-oracle.md` — extend "What does NOT count" (§42) with a sibling
    calibration block: "Real disposed non-findings (calibration — DeFi contest invalid / known-issue /
    OOS / user-error dispositions)", pointing at the corpus axis A.
  - `skills/oracles/severity-precedent-oracle.md` — add a parallel cross-check section (sibling to the
    HackerOne one, §44): "Cross-check: DeFi contest-judged severity — impact×likelihood (Code4rena /
    Sherlock / Immunefi ISVCS)", explaining the model is *not* CVSS and pointing at corpus axis B. The
    CWE-keyed table (§80) is untouched.
  - `engine/regrade.md` §3/§4 — add DeFi worked examples: a `confirmed_with_correction` **downgrade**
    (reported High → judged Medium once likelihood/precondition is traced) and a `refuted`/known-issue
    (reported vuln → judged user-error / already-known), grounded in a named contest ruling.
  - `engine/chainability.md` §3b — add DeFi composed-chain candidate shapes (flash-loan → oracle
    manipulation → drain; donation → share-price inflation → theft) as candidates under the
    promote-per-§0 rule, plus a one-line dedup-discipline note citing contest duplicate-merge groups as
    real "same-finding" ground truth (never touch §3's canonical angles).
- **No new oracle id** — like the rejected/disputed, disposition, and P0/ZDI passes, it enriches
  existing oracle/engine doctrine + a reference corpus; it is calibration data, not a
  mechanically-matchable target property.

---

## 7. Build shape (workflow) and acceptance gates

**Run shape.** Sonnet-5 collectors (≤11/bulk step): ~3 fetch the rubric spine (ISVCS, C4 severity
categorization, Sherlock judging criteria); ~5 chunk concrete judged findings across platform × class
(C4 High/Med findings by contest; Sherlock escalation resolutions; Immunefi disclosed reports). Opus
adjudication applies §5 and assigns the axis + separates judge-verdict from submitter-claim
(adjudicator-set field, not regex-derived — the #4 lesson that avoided the #3 section-overlap bug).
Sonnet re-fetch verifier samples cited reports/issues. **Corpus assembled deterministically in-script
from adjudicated rows — never synth-authored** (standing lesson: synth agents placeholder big tables).

**Anti-hallucination gate (reused).** (1) grep every cited C4 report slug / issue # / Sherlock contest
/ ISVCS tier against collector returns; (2) independent re-fetch of each cited finding confirming the
judged validity + severity + dedup group; (3) adjudicators watch specifically for submitter-claim
masquerading as judged-verdict (rule 2/5) and first-label-vs-post-escalation confusion. Plus operator
hand re-fetch of a sample against the primary pages (verify-the-verifier — a 0-drop result is "too
clean" and must be spot-checked).

**Acceptance gates.** Every corpus row re-fetch-verified or flagged second-hand; **class + disposition
diversity enforced** (no single class or contest dominates — the #6 rule is the point of the pass);
severity lands as a *parallel* DeFi cross-check, never as a CVSS number or a CWE-table rewrite; chain
rows land as §3b candidates, not §3 promotions; judge rationale quote-bounded; `check-conformance.py`
introduces no new failures. **Effort:** Med — C4/Sherlock are structured but the judge-vs-submitter
separation and post-escalation resolution require care; no Zone-2 surface (public disclosed judged
reports, not a live PoC).
