# Deep-research + oracle plan: Project Zero + ZDI root-cause chain corpus

> Status: research plan, ready for operator review. This document does not itself authorize a run.

Same discipline and document shape as the CVSS severity-precedent, GHSA fix-diff, REJECTED/DISPUTED
CVE, and HackerOne disposition plans: mine real disclosed artifacts that carry their own verdict,
re-verify each at a primary authority, land them as calibration anchors + a backing corpus with
"Contested"/"Dropped" sections. This is proposal **#5** of the deep-research-corpus agenda. The axis
is the **disclosed multi-stage exploit chain** and its **published root-cause analysis** — Google
Project Zero's 90-day tracker + deep-dive writeups, and Zero Day Initiative advisories.

The distinguishing property versus the sibling passes: those mine web-application / package
ecosystems. This one mines **memory-safety, sandbox-escape, and OS/kernel** chains — the exact
cross-domain evidence `engine/chainability.md` says it lacks, and the exact place where "the sink
executed but the claimed impact was narrower" (pocinator `claim_mismatch`) is documented in detail by
a hostile third party rather than the finder.

---

## 1. ROLE and the gap it closes

**What it is.** For each disclosed item, fetch the primary record — a P0 issue
(`issuetracker.google.com`, ex-`bugs.chromium.org/p/project-zero`) + its linked patch and any
"In-the-Wild" / deep-dive blog post, or a ZDI advisory (`zerodayinitiative.com/advisories/ZDI-…`) —
and extract a structured tuple: the **chain stages** (each primitive → boundary crossed → resulting
capability), the **published root-cause**, the **CVE + CVSS vector + affected version**, the **patch
reference**, and — where the writeup states it — the **reported-impact-vs-real-impact delta**. P0's
tracker and blog carry the *mechanism and the chain linkage* in depth; ZDI carries *structured
CVSS/CVE/affected-product* with a terser root-cause. Both are primary disclosures with a built-in,
third-party-adjudicated verdict (the vendor patched it; the researcher published the mechanism), not a
researcher self-claim.

**The gap, grounded in the readers.**
- **`engine/chainability.md` §3b openly rests on a single-domain basis.** Verbatim (line 116): "The
  six angles above were generalized from a single Cosmos `iavl` finding"; §0/§3 promote canonical
  angles "only on repeated cross-instance evidence." PR #28 seeded §3b with 32 **HackerOne web-app**
  chains — but those are almost all request→state web shapes. There is **no** memory-corruption,
  sandbox-escape, or kernel-LPE chain in the corpus, so the angle-shapes are still untested against the
  domain where chaining is most load-bearing. P0/ZDI is that missing cross-domain evidence.
- **`engine/regrade.md` §3/§4 has thin worked examples for root-cause / severity re-derivation.**
  `confirmed_with_correction` (real, but severity/scope framing corrected — §3) leans on one
  prototype-pollution and one filter-chain example; `refuted` got its only worked instance
  (CVE-2019-9193) from proposal #3. P0/ZDI writeups are dense **published root-cause re-derivations by
  a hostile analyst** — precisely the "re-derive from primary sources, trust nothing" (§4) evidence
  regrade is built on, including real severity corrections (reported critical → real high once a
  precondition is traced).
- **`engine/pocinator.md` §5 lens 4/6 (mechanism fidelity, `claim_mismatch`) is under-anchored.**
  Lens 4 ("mechanism fidelity via the negative control") and lens 6's `claim_mismatch` scope both
  concern "the PoC is real but proves something narrower/different than claimed." P0's tracker
  repeatedly documents exactly this — a primitive that "technically executed" but reached a narrower
  boundary than first reported, or an impact re-attributed to a different root cause after analysis.
  These are real `claim_mismatch` / mechanism-fidelity exemplars from a primary source.

**Why this is the same template as the sibling passes.** Terse consumption anchors keyed by axis + a
backing corpus where every row is re-verified verbatim at a primary authority, with explicit
"Contested"/"Dropped". Proven four times now (severity 314 vectors, GHSA 127 diffs, rejected/disputed
41 anchors, HackerOne dispositions 80 rows), each with the grep-vs-corpus + independent-re-fetch
anti-hallucination gate.

**What it is NOT.**
- **Not a severity-precedent pass.** ZDI/P0 CVSS grounds `regrade.md`'s *root-cause-driven severity
  re-derivation* (why the reported number was wrong once the mechanism is traced), NOT the
  `severity-precedent-oracle` methodology corpus — regrade §5 draws that boundary explicitly; respect it.
- **Not a live-bug or exploit-primitive pass.** Every item is disclosed and patched. The corpus is
  chain **structure** + published root-cause, never a weaponized reproduction or a usable primitive.
- **Not an angle-promotion.** Chains land in chainability **§3b as candidates**; the canonical six
  angles change only on repeated cross-instance evidence per the card's own §0 rule. This pass never
  rewrites §3.

---

## 2. HARD RULES

1. **Primary disclosure only — the finder/vendor record, never an aggregator.** Admissible sources:
   the P0 issue tracker entry, the P0 blog post, or the ZDI advisory page (and the linked vendor
   patch/CVE). A news summary, a "top 10 exploits" roundup, or a writeup-index entry is never the
   cited source (the explicit anti-#17 rule).
2. **A "chain" means ≥2 distinct disclosed stages.** IN only if the writeup shows genuine multi-stage
   linkage — at least two distinct primitives or trust boundaries crossed in sequence (e.g.
   info-leak → UAF → sandbox escape → LPE). A single-primitive bug relabeled "chain" is OUT. Record
   each stage as `primitive → boundary → capability`.
3. **Root-cause, CVSS, CVE, affected version, and any impact-delta quote are copied from the primary
   record, not reconstructed.** If P0 prose states the root cause, quote/paraphrase it faithfully with
   the source anchor; never infer a root cause the writeup doesn't give.
4. **Respect chainability's promotion rule.** New chains are §3b **candidates**. Do not add to or
   rewrite the canonical six angles (§3) from this corpus. Promotion is a separate, evidence-gated,
   operator step.
5. **P0-prose extraction is quote-bounded.** P0 is narrative (full-text-trap risk, flagged in the
   proposals audit). Extract only linkage/mechanism the post actually states; mark inferred connective
   tissue as inference, never as disclosed fact. ZDI root-cause summaries are often one sentence —
   record them as-is and flag `thin_rootcause` rather than padding.
6. **Cross-domain diversity is the acceptance criterion, not volume.** The whole point is breadth the
   HackerOne web corpus lacks. Cap any single class (e.g. browser-renderer UAF) so the corpus spans
   memory-corruption, sandbox/VM escape, OS-kernel LPE, mobile baseband/driver, and logic chains.
7. **Defensive artifact only** — chain structure, root-cause, severity, patch reference. Never a
   reproduction, exploit primitive, or step-by-step weaponization.

---

## 3. SOURCES

- **Google Project Zero issue tracker (primary).** `issuetracker.google.com` (P0 component; formerly
  `bugs.chromium.org/p/project-zero/issues`). Each disclosed issue: root-cause description, PoC
  reference, linked fix, disclosure timeline (the 90-day deadline is the built-in disclosure oracle).
  Filter to `Status: Fixed` / disclosed. Best for **chain mechanism + root cause**.
- **Project Zero blog (primary, narrative).** `googleprojectzero.blogspot.com` — deep dives and the
  "In-the-Wild" 0-day series, which document full real-world chains stage-by-stage. Best for **A-axis
  multi-stage chains**; highest full-text-trap risk (rule 5).
- **Zero Day Initiative advisories (primary, structured).** `zerodayinitiative.com/advisories/` — each
  carries a `ZDI-CAN`/`ZDI-<year>-<n>` id, CVE, CVSS vector, affected products/versions, a (terse)
  root-cause summary, and the disclosure timeline. Best for **structured CVSS/CVE/version anchors**;
  root cause is often thin (rule 5).
- **Vendor patch / CVE cross-ref (secondary).** The linked commit/bulletin + the NVD record — used to
  confirm CVE + CVSS + affected range, joining to the severity-precedent corpus by CVE id. Not the
  source for the chain or root cause.

**Structured/clean:** ZDI advisories (machine-parseable fields) and P0 tracker metadata. **Traps:**
(a) P0 blog is prose — mechanism must be extracted, not fabricated (rule 5); (b) ZDI root-cause
summaries are frequently one sentence — real but thin; (c) the P0 tracker migrated hosts
(`bugs.chromium.org` → `issuetracker.google.com`) — resolve the live URL; (d) some P0/ZDI items are
single-bug, not chains — those are OUT for the A-axis (may still serve B/C).

---

## 4. METHOD

1. **Bucket by the consumer axis, not by product.** Three destinations:
   **(A) cross-domain chains** (≥2 disclosed stages) → `chainability.md` §3b candidate list;
   **(B) root-cause / severity re-derivations** (published analysis corrects or grounds the reported
   severity/scope) → `regrade.md` §3/§4 worked examples;
   **(C) mechanism-fidelity / impact-delta** (sink executed but real impact narrower/re-attributed) →
   `pocinator.md` §5 lens 4/6 (`claim_mismatch`) worked examples.
   One item may serve more than one axis (a P0 in-the-wild chain often serves A + B).
2. **Collect ZDI first (structured), P0 second (narrative).** ZDI advisories give the CVE/CVSS/version
   spine cheaply; P0 issues+blog supply the chain-stage and root-cause depth. Chunk ZDI across
   collectors by product-family/year; chunk P0 by the in-the-wild series + tracker Fixed set.
3. **Extract the tuple** — `{ source id (P0 #/ZDI-id) · CVE · product/version · CVSS vector · chain
   stages [primitive→boundary→capability] · root-cause (quoted/anchored) · reported-vs-real impact
   delta · patch ref · axis · disclosure date }`.
4. **Dedup structurally.** Diversity of domain × chain-shape × boundary-crossed, not repeats (rule 6).
   Target roughly 8–15 per axis, hard-capping any single vuln class.
5. **The disclosure is the oracle.** For A, the writeup's shown stage linkage is the ground truth; for
   B, the published root-cause + vendor CVSS is the severity ground truth; for C, the writeup's own
   statement that the real impact differed from the first-reported one is the calibration signal.

---

## 5. ORACLE GATE — IN / CONTESTED / OUT

- **IN:** the P0 issue / P0 post / ZDI advisory still resolves and carries the cited fields; the item
  maps to an axis. For A, a genuinely ≥2-stage disclosed chain with the linkage shown; for B, a
  published root-cause + a real severity/scope correction (or a clean severity anchor); for C, a
  writeup-stated impact/mechanism delta.
- **CONTESTED:** the chain is real but the root-cause is a one-line ZDI summary (`thin_rootcause`); or
  the stage linkage is partly inferred rather than fully disclosed (record with the inference flagged,
  rule 5); or CVSS is vendor-assigned but disputed. Record and label; do not assert the missing detail.
- **OUT:** an aggregator/summary is the only available source; the item is a single-primitive bug (no
  chain) for the A-axis; the P0 URL no longer resolves and no archived primary exists; or a duplicate
  chain-shape/domain already covered (rule 6). Every drop logged with reason.

---

## 6. OUTPUT — where it lands

- **A backing corpus — `skills/oracles/references/project-zero-zdi-chain-corpus.md`.** Sibling to the
  GHSA/CVE/HackerOne reference corpora, per-axis structure with "Contested"/"Dropped". Columns:
  `Source (P0 #/ZDI-id) | CVE | Product/version | CVSS | Chain stages (primitive→boundary→capability) | Root-cause (quoted) | Reported-vs-real impact delta | Axis | Disclosed | Source URL`.
  Per-row provenance flag ("re-fetched this session" vs "second-hand — re-verify").
- **Consumption anchors:**
  - `engine/chainability.md` **§3b** — extend the candidate list with N cross-domain P0/ZDI chains,
    explicitly labeled candidates under the existing promote-per-§0 rule (never touch §3's six angles).
  - `engine/regrade.md` **§3/§4** — add real root-cause / severity re-derivation worked examples
    (`confirmed_with_correction` where a traced precondition capped severity; a `refuted`/`blocked`
    where the reported impact didn't re-derive), grounded in P0/ZDI analysis.
  - `engine/pocinator.md` **§5** — add a mechanism-fidelity / `claim_mismatch` worked example: a
    disclosed case where the primitive executed but reached a narrower boundary than reported.
- **No new oracle id** — like the rejected/disputed and disposition passes, it enriches existing
  engine doctrine + a reference corpus; it is calibration data, not a mechanically-matchable target
  property.

---

## 7. Build shape (workflow) and acceptance gates

**Run shape.** Sonnet-5 collectors (≤11/bulk step): ~6 chunk the ZDI advisory feed (by
product-family/year) + fetch each advisory; ~3 fetch P0 tracker Fixed issues + the in-the-wild blog
chains. Opus adjudication applies §5 and assigns the axis (adjudicator-set field, not regex-derived —
the #4 lesson that avoided the #3 section-overlap bug). Sonnet re-fetch verifier samples cited ids.
**Corpus assembled deterministically in-script from adjudicated rows — never synth-authored** (standing
lesson: synth agents placeholder big tables).

**Anti-hallucination gate (reused).** (1) grep every cited `ZDI-…`/P0-`#` against collector returns;
(2) independent re-fetch of each cited advisory/issue confirming CVE + CVSS + the chain claim; (3)
adjudicators watch specifically for fabricated stage-linkage (rule 5) and single-bugs-as-chains
(rule 2). Plus operator hand re-fetch of a sample against the primary pages (verify-the-verifier — a
0-drop result is "too clean" and must be spot-checked).

**Acceptance gates.** Every corpus row re-fetch-verified or flagged second-hand; **cross-domain
diversity enforced** (no single class dominates — the #6 rule is the point of the pass); chainability
rows land as §3b candidates, not §3 promotions; P0-prose linkage quote-bounded; `check-conformance.py`
introduces no new failures. **Effort:** Med — ZDI is structured but P0 requires careful prose
extraction and host-migration URL resolution; no Zone-2 surface (public disclosed advisories, not a
PoC).
