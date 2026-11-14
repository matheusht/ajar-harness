# Blind triage rubric

Use this to compare two reports for the same finding without knowing which skill produced which.
Score the exact submitted text and package, not the internal working file.

## Protocol

1. Randomize A/B per reviewer. Reviewer 1 scores A then B; reviewer 2 scores B then A.
2. Strip author, tool, date, and skill provenance. Do not reward formatting polish.
3. Answer the gate first. If any answer is NO, the report is not triage-ready regardless of score.
4. Score each criterion 0/1/2 from the anchors, with one evidence sentence per score.
5. Apply penalty caps before totaling. Do not double-count.
6. Compare only after both are scored. If reviewers differ by more than one point on a criterion,
   a third reviewer adjudicates that criterion, not the whole report.

## The gate

Answer from the package alone:

| # | Question | Passes when |
|---|---|---|
| G1 | What is affected and what class of bug is this? | Product, artifact/version/commit, component, and class are explicit in the first screen. |
| G2 | Can I run the fast path and know what to observe? | Package inventory, pinned target, prerequisites, command, expected output. |
| G3 | Is the headline demonstrated with a control or differential? | Raw output or code quote, plus the obvious alternative ruled out. |
| G4 | Is every load-bearing claim checkable from the package? | Versions, commands, outputs, severity arithmetic, absence claims, and scope claims are evidenced or bounded. |
| G5 | Are observation and inference separated, with no contradictory caveat? | Confirmed vs inferred is explicit; limits do not undermine the headline. |
| G6 | Is the chain closed to the claimed stage? | Every stage is `proven` with an evidence cell or `argued` with a named blocker and what would close it; title and summary claim no stage past the last `proven` one; severity is the floor link, not the end state. |

G6 is `N/A` (pass) for a single-stage finding. A chain with no stage table, no per-stage state,
or a headline past the last proven stage fails G6.

A polite "please confirm this number" is a G4 failure when the number is load-bearing.

## Ten criteria

| # | Criterion | Weight | 2 | 1 | 0 |
|---|---|---:|---|---|---|
| C1 | Orientation: title, summary, affected artifact | 6 | Component + mechanism + consequence in title; 2–4 sentence summary with product, precondition, primitive, impact; exact version before first scroll. | Accurate but generic; version buried; impact needs next section. | Label or sales pitch; process lead; no impact/version. |
| C2 | Structural clarity and sequencing | 10 | Canonical order; each section answers one question; fast/full paths separated; chain traceable without jumping; for a chain, a chain overview table and diagram (or self-sufficient table) precede the walkthrough and use the same stage IDs. | Sections exist but one does double duty; chain exists only as prose, or the table/diagram disagrees with the body. | No stable order; mechanism scattered; command dump. |
| C3 | Human voice and plain register | 10 | Accountable first person where earned; concrete nouns; varied sentence length; calibrated confidence; no marketing or template. | Correct but institutional/impersonal; hedged until blurry. | Marketing, tool promotion, process grievance, manufactured affect, jargon wall. |
| C4 | Root-cause specificity | 16 | Exact file/function/line; quoted guard; input-to-sink; why the guard fails; every link pinned; each link classified root/consequence; each edge has its own anchor and output→precondition statement; each link's state shown. | Component and general mechanism, but one link hand-waved; edges implicit; no root/consequence split. | Bug-class label with no function, line, flow, or guard analysis. |
| C5 | Concrete, bounded impact | 12 | Primitive → technical consequence → real-world consequence; named actor, asset, precondition; demonstrated vs theoretical; for a chain, entry actor to terminal asset and the link that carries the score. | Correct but generic; asset/actor missing; consequence asserted. | Copy-paste impact; no named asset/actor; severity asserted. |
| C6 | Reproducibility from the package alone | 16 | All artifacts; target pinned; exact prerequisites; one-command fast path; full walkthrough; literal expected output; no author-machine dependency; patches/deltas explicit; for a chain, per-stage commands, markers, abort/restore, and `n/N`. | Complete but environment-heavy; fast path missing; output described not shown; only a terminal marker. | PoC on request; missing artifacts; private setup; no expected output. |
| C7 | Evidence and controls | 12 | Every claim maps to raw output/code/artifact; negative control or differential; replay stated; absent slots labeled; contradictions addressed; for a chain, one evidence row per stage and at least one stage-local control. | Strong observation, no control; screenshot without transcript; one claim rests on “it worked”; terminal control only. | Screenshot-only; claim/evidence mismatch; control does not isolate. |
| C8 | Honest boundaries | 8 | Confirmed vs inferred; pinned environment; preconditions; untested scope; conditional ceiling; fix labeled suggestion; for a chain, per-stage assumptions with `confirmed`/`inferred`/`assumed`, weakest link, and last proven stage. | Main prerequisite named; negative space missing; caveat buried. | “All versions”; no preconditions; hides simulation; limit contradicts headline. |
| C9 | Novelty and duplicate delta | 6 | Search trail (advisories, CVEs, GHSAs, issues), date, result; adjacent art gets root-cause delta. | Asserts novelty; one source; delta implicit. | “First ever” with no search; ignores adjacent prior art. |
| C10 | Signal density | 4 | Every paragraph carries mechanism, evidence, boundary, or decision; no form scaffolding, tool marketing, process narrative, repeated disclaimers. | Some scaffolding/repetition; body readable. | Opens with or dominated by meta; reader must skip blocks. |

## Penalty caps

| Defect | Trigger | Cap |
|---|---|---|
| Jargon | Five or more undefined internal terms/acronyms in first screen, or a mechanism that needs a glossary | C2 ≤1; C2 = 0 if unreadable |
| Meta | Submission instructions, tool marketing, process grievance, report-about-the-report | C3 ≤1 and C10 ≤1; C10 = 0 if it leads or exceeds 10% |
| Generic impact | Impact survives a product-name swap; no named asset/actor/precondition | C5 ≤1; C5 = 0 if no named asset |
| Unverifiable claim | Load-bearing version, command, output, “no warning”, severity arithmetic, or “all users” not shown | C7 ≤1; G4 fails if headline |
| Unquantified reliability | “Reliable”, “most runs”, “zero crashes”, or `AC:L` without `n/N` and environment | C6 ≤1; C8 ≤1 if it changes the ceiling |
| Fabrication/contradiction | Quoted source says something else; output contradicts text; invented evidence | Automatic reject |

## Chain supplement

Use this only when the finding has more than one stage. It does not change the weights; it
sharpens the gate and the anchors.

A chain report must contain:

1. A chain overview table with one row per capability transition, a `path:line` anchor, a literal
   proof marker, and a `root`/`consequence` class.
2. A per-stage state (`proven`, `argued`, `refuted`), and a `Closed at` value equal to the last
   `proven` stage.
3. One edge anchor per link: the line where the producer's output becomes the consumer's input.
4. A stage-local control for at least one intermediate stage, not only the terminal one.
5. Per-stage `n/N`, the failure signature, and an abort/restore path.
6. A per-stage assumption table with `confirmed`, `inferred`, or `assumed`.
7. A build-keyed table for every literal offset or address, if the PoC contains one.

A chain with a stage table but no stage-local control scores C7 ≤1. A chain with `n/N` only at
the end scores C6 ≤1. A chain whose title names stage 5 while stage 3 is `argued` fails G6, not
C8.

## Decision

| Total | Decision |
|---|---|
| 90–100, gate pass | Send; minor copyedit only |
| 80–89, gate pass | Send; one weak area, no load-bearing gap |
| 65–79 or gate fail | Revise; follow-up question or weak criteria become the fix list |
| <65 or C4/C5/C6/C7 = 0 or C8 = 0 with overclaim | Reject/rewrite |

Hard floor: gate 5/5 (6/6 for a chain; G6 may be `N/A` only for a single-stage finding);
total ≥80; C4, C5, C6, C7 each ≥1; C8 ≥1; no fabrication.

Tie-break within 5 points: higher C4 + C6 (root cause + reproducibility), then higher C10
(signal density). Never tie-break on confidence, formatting, or reviewer taste.

## Scoring sheet

```text
BLIND A/B — Reviewer: ______   Report: A / B

GATE
G1 Y/N  G2 Y/N  G3 Y/N  G4 Y/N  G5 Y/N  G6 Y/N/N/A
First follow-up question: _________________________________

CRITERIA                        Weight  Score  Points  Evidence
C1 Orientation                     6      ___     ___    __________
C2 Structure                      10      ___     ___    __________
C3 Voice                          10      ___     ___    __________
C4 Root cause                     16      ___     ___    __________
C5 Impact                         12      ___     ___    __________
C6 Reproducibility                16      ___     ___    __________
C7 Evidence/controls              12      ___     ___    __________
C8 Boundaries                      8      ___     ___    __________
C9 Novelty                         6      ___     ___    __________
C10 Density                        4      ___     ___    __________
                                          TOTAL ___ / 100

Caps: jargon __ meta __ generic __ unverifiable __ reliability __ fabrication __
Floor: C4 __ C5 __ C6 __ C7 __ C8 __
Decision: SEND / REVISE / REJECT
One-line reason: ___________________________________________
```
