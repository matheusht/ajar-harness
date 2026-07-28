# Deep-research + oracle plan: HackerOne disposition / severity / state-history corpus

> Status: research plan, ready for operator review. This document does not itself authorize a run.

Same discipline and document shape as the CVSS severity-precedent, GHSA fix-diff, and REJECTED/DISPUTED
CVE plans: mine real disclosed artifacts that carry their own verdict, re-verify each at a primary
authority, land them as calibration anchors + a backing corpus with "Contested"/"Dropped" sections.
The difference is the axis. The [[hackerone-humanization]] pass already mined this exact 74-report
corpus for **prose voice only** (`skills/reporting/research/hackerone-genuine-human-corpus.md` +
`hackerone-humanization-ruleset.md`). This pass mines the **non-prose ground truth** of the same
reports — the **program's own disposition** (`Resolved`/`Duplicate`/`Informative`/`N-A`/`Spam`), the
**assigned severity/CVSS**, and the **state-transition history** — plus a targeted widening for the
negative dispositions the disclosed set under-represents.

---

## 1. ROLE and the gap it closes

**What it is.** For each report, fetch the public per-report detail JSON
(`hackerone.com/reports/<id>.json`) and extract a structured tuple: the **disposition** (`state` +
`substate` = `resolved`/`duplicate`/`informative`/`not-applicable`/`spam`), the **assigned severity**
(`severity.rating` + CVSS score/vector when present), the **bounty** (`formatted_bounty`), the
**weakness/CWE** (`weakness.name`), the **disclosure date**, and — where the disclosed activity feed
carries it — the **state-transition history** (e.g. a report closed `Informative` then re-opened and
confirmed as a CVE). The program's own disposition is a built-in, timestamped, third-party-adjudicated
ground truth: it is the platform's verdict on the report, not the researcher's self-claim.

**The gap, grounded in the readers.**
- **`skills/oracles/adjudication-oracle.md` has a `## What does NOT count (write these into
  rejections)` section that is authored from priors, not exemplars.** Its whole job is to hold the
  "this is not a finding" bar — but it has no real `Informative`/`Duplicate`/`N-A` disclosed reports
  behind it. A disposition corpus is exactly the negative-exemplar set that section lacks.
- **`engine/chainability.md` openly derives its six angle-shapes from a single finding** — verbatim
  header: "generalized from *one* Cosmos finding (the `iavl` negative-`Version` state-sync crash)…
  promote only on repeated cross-instance evidence." The 74-corpus already contains real disclosed
  multi-stage chains across domains (SSRF→GCP-metadata→k8s-RCE #341876; traversal→Marshal-cookie-RCE
  #827052; upload→ImageMagick-RCE #403417; IDOR→ATO #1685970) — real cross-domain chains to replace
  the single-example basis.
- **`severity_rubric` numbers across `skills/vulns/*` are textbook re-derivations.** The assigned
  severity + bounty on a real disposed report is an independent precedent to cross-check them against
  (complementary to the CVSS-vector corpus, which mines NVD/GHSA vectors, not program-assigned ratings
  + real money).
- **`engine/routing.md` / pattern-card `activation` blocks are authored from memory.** Real reporter
  recon narratives (how the finder actually reached the sink) are disclosed-report ground truth for
  rewriting them — the same reports, read for method rather than voice.

**Why this is the same template as the sibling passes.** Terse consumption anchors keyed by axis + a
backing corpus where every row is re-verified verbatim at a primary authority, with explicit
"Contested"/"Dropped". Proven three times now (severity 314 vectors, GHSA 127 diffs, rejected/disputed
41 anchors), each with the grep-vs-corpus + independent-re-fetch anti-hallucination gate.

**What it is NOT.**
- **Not the prose pass.** Voice/humanization is done ([[hackerone-humanization]]); this pass never
  touches the ruleset — it reads the same reports for disposition/severity/chain structure.
- **Not a live-bug claim.** Every report is disposed and disclosed. The corpus is a taxonomy of how
  real triage adjudicated real reports, not a claim any target is exploitable.
- **Not the CVSS-vector pass.** It mines the *program-assigned* rating + bounty (a different oracle
  than NVD/GHSA CVSS vectors); it cross-checks the severity corpus, does not replace it.

---

## 2. HARD RULES

1. **The program's disposition is the oracle — never the researcher's self-claim.** `substate` from
   the report JSON (`resolved`/`duplicate`/`informative`/`not-applicable`/`spam`) is the ground truth.
   A researcher writing "critical RCE" in the body is a *claim*; if the program disposed it
   `Informative`, the corpus records `Informative`. Never invert this.
2. **Re-fetchable primary record only.** An anchor is admissible only if `hackerone.com/reports/<id>.json`
   still resolves and carries the `substate`/`severity` fields cited. An aggregator/blog summary is
   never the cited source.
3. **No fabrication.** Disposition, severity rating, bounty, CWE, and any state-transition quote are
   copied from the fetched JSON, not reconstructed from the prose corpus or memory.
4. **State the disclosed-set bias explicitly.** Disclosed reports skew toward `resolved`/bountied
   (that is *why* they got disclosed). The 74-seed will therefore be positive-heavy; negative
   dispositions (`Informative`/`Duplicate`/`N-A`) must come from a **targeted widening hunt** and be
   labeled as such. Do not present a resolved-heavy sample as a representative disposition distribution.
5. **Redacted / private disposition rationale → CONTESTED, not dropped.** Many disclosed reports show
   the disposition but redact the *why* (`███` blocks). Record the disposition (it is real) and flag
   that the rationale is unavailable; do not invent the reasoning.
6. **State-history requires the activity feed, not the closing state alone.** A "closed Informative
   then confirmed as CVE" transition is only IN if the disclosed activity/timeline actually shows both
   states; otherwise record only the final disposition.
7. **Never present a disposed report as a live finding**, and keep the mined artifact defensive
   (disposition + severity + chain *structure*, never a weaponized reproduction).

---

## 3. SOURCES

- **`hackerone.com/reports/<id>.json` (primary).** Public per-report detail JSON. Verified live to
  carry `state`, `substate`, `severity.rating` (+ CVSS score/vector when set), `formatted_bounty`,
  `weakness.name`, `disclosed_at`, and (variably) an activity/timeline feed. This is the disposition
  and severity ground truth and the join key back to the prose corpus (same id).
- **The existing 92-id seed** (`skills/reporting/research/hackerone-genuine-human-corpus.md`). Re-mine
  these first for the non-prose axes — the ids are already vetted-genuine, so this reuses prior
  selection work.
- **HackerOne Hacktivity disclosed listing (for the widening hunt).** Filter disclosed reports for
  `Informative`/`Duplicate`/`Not Applicable` substates to populate the negative-exemplar axis the seed
  under-represents. Each hit is still re-fetched at its `.json` endpoint.
- **NVD/CVE cross-ref (secondary).** For the CVE-linked reports, join the H1 severity to the
  severity-precedent corpus by CVE id — not a source for the disposition.

**Structured/clean:** the `.json` endpoint (best — machine-readable disposition + severity). **Traps:**
(a) no bulk API without a researcher account — this is per-id fetch + Hacktivity scraping, rate-limited;
(b) disposition rationale often redacted (rule 5); (c) self-claim contamination in the prose body
(rule 1); (d) a handful of the 92 ids are secondary references (PayPal #739737 is content-redacted) —
those yield disposition-only or drop.

---

## 4. METHOD

1. **Bucket by the consumer axis, not by vuln class.** Four destinations:
   **(A) negative exemplars** (`Informative`/`Duplicate`/`N-A`/`Spam`) → `adjudication-oracle` "what
   does NOT count"; **(B) disclosed chains** → `chainability.md` angle-shapes; **(C) severity
   precedents** (disposition `resolved` + rating + bounty + CVSS) → `severity_rubric` cross-check;
   **(D) routing-recon narratives** → `routing.md`/pattern `activation`.
2. **Re-mine the 92 seed ids first** (chunked across collectors): fetch each `.json`, extract the
   tuple, and tag which axis/axes it serves. Most will land in B/C/D (resolved-heavy).
3. **Targeted widening for bucket A** (2–3 collectors): hunt disclosed `Informative`/`Duplicate`/`N-A`
   reports via Hacktivity, re-fetch each `.json`. This is where the "what does NOT count" grounding
   actually comes from — the seed alone can't supply it (rule 4).
4. **Extract the tuple** — `{ report id · disposition (state+substate) · severity rating (+CVSS) ·
   bounty · weakness/CWE · disclosed_at · chain-structure (for B) · state-transitions (if in the feed)
   · self-claim-vs-disposition delta }`.
5. **Dedup structurally.** Diversity of disposition × class × chain-shape, not repeats. Target roughly
   8–15 per axis.
6. **The disposition is the oracle.** For A, the `substate` IS the negative-verdict ground truth; for
   C, the assigned rating + bounty is the severity ground truth; the self-claim-vs-disposition delta
   (rule 1) is itself a calibration signal (over-claimed body, downgraded by triage).

---

## 5. ORACLE GATE — IN / CONTESTED / OUT

- **IN:** `.json` re-fetches and carries the cited `substate` + `severity`; the row maps cleanly to
  one of the four axes. For A, a real non-`resolved` disposition; for B, a genuinely multi-stage
  disclosed chain (not a single-step bug); for C, `resolved` + a rating (+ bounty); for D, a disclosed
  recon narrative.
- **CONTESTED:** disposition is visible but the rationale is redacted/private (rule 5); or a
  self-claim-vs-disposition conflict that is itself unresolved (body says critical, program severity
  blank/disputed). Record and label; do not assert the missing reasoning.
- **OUT:** `.json` no longer resolves or lacks the fields (content-redacted reports); disposition is
  only inferable from prose, not the record; or a duplicate row (same chain shape already covered).
  Every drop logged with reason.

---

## 6. OUTPUT — where it lands

- **A backing corpus — `skills/reporting/research/hackerone-disposition-corpus.md`.** Sibling to the
  genuine-human-corpus, per-axis structure with "Contested"/"Dropped". Columns:
  `Report | Disposition (state/substate) | Severity (rating/CVSS) | Bounty | CWE | Axis | Self-claim→disposition delta | Chain structure | Disclosed | Source`.
  Per-row provenance flag ("re-fetched this session" vs "second-hand — re-verify").
- **Consumption anchors:**
  - `skills/oracles/adjudication-oracle.md` `## What does NOT count` — add 3–5 real
    `Informative`/`Duplicate`/`N-A` exemplars (the negative-exemplar set it lacks).
  - `engine/chainability.md` — add real disclosed chains as angle-shape exemplars, replacing the
    single-Cosmos-finding basis (kept as candidates until repeated cross-instance evidence, per the
    card's own promotion rule).
  - A severity cross-check note tying program-assigned ratings/bounties to `severity-precedent-corpus.md`.
- **No new oracle id** — like the rejected/disputed pass, it enriches existing oracles + engine
  doctrine + the reporting corpus; it is calibration data, not a mechanically-matchable target property.

---

## 7. Build shape (workflow) and acceptance gates

**Run shape.** Sonnet-5 collectors (≤11/bulk step): ~8 chunk the 92 seed ids + re-fetch each `.json`;
2–3 run the Hacktivity widening hunt for negative dispositions. Opus adjudication applies §5. Sonnet
re-fetch verifier samples cited ids (anti-hallucination gate 2). **Corpus assembled deterministically
in-script from adjudicated rows — never synth-authored** (standing lesson).

**Anti-hallucination gate (reused).** (1) grep every cited report id against collector returns; (2)
independent re-fetch of each cited `.json` confirming `substate` + `severity` verbatim; (3)
adjudicators watch specifically for self-claim-recorded-as-disposition (rule 1) and redacted-rationale
invention (rule 5).

**Acceptance gates.** Every corpus row re-fetch-verified or flagged second-hand; bucket A populated
from the widening hunt (not faked from the resolved seed); disclosed-set bias stated in the header;
`check-conformance.py` introduces no new failures. **Effort:** Med — per-id fetch + a widening hunt,
rate-limited but structured; no Zone-2 surface (public disposition metadata, not a PoC).
