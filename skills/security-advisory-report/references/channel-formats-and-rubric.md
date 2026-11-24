# Channel Format Spines & 100-Point Evaluation Rubric (v2)

This reference accompanies `SKILL.md` and `scripts/report_voice_lint.py` (`ajar-report-voice-lint/2`). Every template and example uses strictly defensive verification checks and historical public CVEs (`CVE-2023-23946`, `CVE-2024-32002`, `CVE-2025-48385`, `CVE-2023-38545`, `CVE-2024-2004`).

---

## 1. Channel Format Templates

### 1.1 GitHub Security Advisory (`--channel ghsa`)

Use clean GitHub Flavored Markdown with zero alert banners (`> [!IMPORTANT]`), zero em-dashes, zero rubric-echo bold subheads (`**Trust boundary:**`), zero `Hop 1..N` labels, and zero unassigned/synthetic CVE IDs.

- **One line per paragraph in Markdown (`ghsa`, `h1`, `immunefi`, `customer`) — never hard-wrap prose at 72/80 columns (GFM turns single `\n` into `<br>`); reserve 72-column hard wrapping strictly for `--channel mailing-list` plain text.** Put every paragraph and every list bullet on a single unwrapped line.
- **Top metadata strip is optional** when pasting into GitHub's structured web fields, and **omit CVSS entirely** for projects that reject CVSS (`curl`, `OpenSSL`).
- **Compact `Tier S` option (`4` sections):** For a 1-branch defect explainable in `90–160` words, use `### Summary`, `### Details` (folding 1-sentence impact/workaround scope), `### PoC`, and `### Suggested fix`.
- **Full `6`-section GHSA spine (`Tier S/M/C`):** Maps 1:1 to GHSA form sections (`max_sections=6` supported in `Tier S/M`, `7` in `Tier C`):

```markdown
# <subsystem>: <root defect> in `<function>()` allows <outcome> when <condition>

- **Severity:** <Critical | High | Medium | Low>
- **CVSS v3.1:** `CVSS:3.1/AV:.../AC:.../PR:.../UI:.../S:.../C:.../I:.../A:...` (<score>) — <1-clause rationale for UI/AC/I vector>
- **CWE:** <CWE-ID> (<Official Name>)
- **Affected versions:** `< latest_patched` (introduced in `<tag/sha>`, verified on `master` at `<12-char-sha>`)

### Summary

<1-2 sentences, 25-55 words. Cite version/SHA, backticked `func()` + `path/file.c:line`, concrete trigger/precondition, and proven boundary outcome. Never repeat in Details.>

### Details

<Enter caller -> callee flow immediately. Contrast against compliant sibling paths in one natural clause. Cite `Introduced in commit <12-char-sha> ("<subject>", YYYY-MM-DD)` and any prior public CVE lineage (e.g., `CVE-2023-23946`). State default vs. non-default config/OS/server gates up front before impact.>

### PoC

<1-sentence build/OS note (`-O2` vs. `-fsanitize=address`). Use portable POSIX `cat <<'EOF'` heredocs (never GNU-only multiline `sed`) inside `mktemp -d` + `trap`, asserting harmless state plus a benign control.>

```sh
#!/bin/sh
set -eu
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
cat <<'EOF' >"$work/input.cfg"
# minimal harmless input
EOF
# Positive check (Expected vs. Observed) + 1-line benign control
```

### Impact

<1 concise paragraph (+ at most 1 compact OS/config matrix in Tier M/C when >= 3 environments differ). Ground in documented policy (`gitsecurityboundary(7)`, `curl` security policy) and state explicit blast-radius ceilings.>

### Suggested fix

<1-3 complete grammatical sentences naming the enforced invariant, clean header/helper choices, synced sibling callers, root-cause vs. defense-in-depth hunks, and passing upstream test suites (`With this patch applied, tXXXX passes.`).>

```diff
--- a/path/to/file.c
+++ b/path/to/file.c
@@ -120,6 +120,8 @@
```

### Workarounds

<Dedicated section for no-upgrade CLI/config mitigations (`git config --global ...`). State plainly if partial or if no config workaround exists.>

Reported-by: <Researcher Name> <<email>> (Ajar Labs)
```

---

### 1.2 Plain-Text Mailing List & `git format-patch` (`--channel mailing-list`)

**Strict plain-text rules:**
1. Wrap prose at **72 columns** (`<= 78` hard ceiling).
2. **Zero Markdown syntax:** no `###` headings, no ```` ``` ```` fences, no `` `backticks` ``, no `**bold**`, no `[label](<url>)`, and no `| pipe |` tables.
3. Support standard RFC 5322 headers (`From:`, `To:`, `Date:`, `Subject:`) or `git format-patch -1` single-commit advisories (where the commit message contains the causal trace + regression test).
4. Use `========` or `--------` Setext underlines, 4-space indented POSIX `sh` / C reproducer blocks, and unfenced `--- a/` / `+++ b/` unified diffs.

```text
From: <Researcher Name> <<email>>
To: <security-list@project.org>
Date: <RFC 2822 date>
Subject: [SECURITY] <subsystem>: <concise defect and boundary outcome>

In <Project> <version_range> (commit <12-char-sha>), <func>() in
<path/file.c>:<line> <action without guard>, allowing <trigger> to
<concrete boundary outcome> when <condition>.

Affected versions: <earliest_tag> .. <latest_tag>
Introduced in:     <12-char-sha> ("<subject>", YYYY-MM-DD)
Affected configs:  <default vs. non-default flags, OS scope>

Analysis
--------
<func>() <direct trace>. Sibling <peer_func>() enforces <guard>,
whereas <func>() skips it when <state>. Stock <OS/config> builds are
unaffected.

Verification
------------
Tested on <OS/arch> with -O2 and -fsanitize=address.

    #!/bin/sh
    set -eu
    work=$(mktemp -d)
    trap 'rm -rf "$work"' EXIT
    # portable POSIX check + benign control

Suggested Fix
-------------
<Complete sentence noting synced callers and passing test suites.>

--- a/path/to/file.c
+++ b/path/to/file.c
@@ -120,6 +120,8 @@

Reported-by: <Researcher Name> <<email>> (Ajar Labs)
```

---

### 1.3 HackerOne Systems & Web Submissions (`--channel h1`)

- **Title:** `<Component>: <Defect> in <func/route> leads to <verified outcome> [<config gate>]`
- **`### Summary` (`<= 55w`, `1–2` sentences):** Violated API/RFC/manpage contract, version/SHA tested, trigger, and proven outcome. Omit CVSS on programs that forbid it (`curl`, `OpenSSL`).
- **`### Steps To Reproduce`:** Hermetic `mktemp -d` or local container script + **Benign Control** + trimmed observable output (`6–12` lines).
- **`### Impact` & `### Workarounds`:** Exact buffer/config thresholds (`CVE-2023-38545`), starting privilege, blast-radius ceiling, and config mitigation. Never extrapolate an OOB read or crash into RCE.
- **`### Suggested fix`:** Minimal diff + sibling-caller check.

---

### 1.4 Immunefi Smart-Contract & Consensus Submissions (`--channel immunefi`)

Zero textbook intros (*"What is a Flash Loan?"*). Use five tight blocks:
1. **`### Quantified Summary & Activation Status` (`1–5` sentences, `<= 105w`):** Live contract/module address + chain/block + commit, broken invariant, **exact bounded exposure ceiling** in protocol units (explicitly noting isolated/unaffected pools), and mainnet pause/activation state.
2. **`### Trust Boundary & Broken Invariant`:** `6–15` line contract/validator excerpt contrasting compliant peer check vs. unguarded path in plain prose (zero `- Intended:` / `- Bypass:` bullets).
3. **`### State Walkthrough`:** Numbered `1..N` atomic call/block sequence with concrete actors, amounts, and gas/capital cost.
4. **`### Verification`:** Pinned-block `forge test` / `cargo test` asserting pre-fix failure and post-fix invariant preservation.
5. **`### Remediation`:** Two-stage split: *(a)* immediate operational containment (pause/cap) and *(b)* minimal diff + test suite.

---

### 1.5 Commissioned Customer Deliverables (`--channel customer`)

#### A. Multi-Finding Engagement Executive Split (`--tier audit`)
Every technical engagement report MUST separate findings at the top into two distinct tables so leadership never conflates gated hardening with live exposure:
1. **Unprivileged Live Entrypoint Findings:** Reachable in production configuration without operator privilege or pre-existing compromise.
2. **Config/Operator-Gated, Component-Isolated, or Pre-Activation Findings:** Require non-default flags, trusted admin roles, off-default build modes, or unreleased features.

#### B. Buyer-Safe `DEC-0099` Security Review Summary (`--tier dry`)
Deliver a short, exploit-free companion record containing:
- **Reviewed Scope & Revision:** Exact repository URL(s), commit SHA(s), and covered modules.
- **Bounded Outcome & Remediation Status:** Validated finding counts split by Live vs. Config/Operator-Gated, plus commit SHAs where fixes were re-verified.
- **Verified Boundaries (when dry or partially dry):** Specific invariant questions tested and `file:line` guards verified as holding.
- **Limitations & Unresolved Paths (`OPINIONS.md`):** Out-of-scope services, blocked dynamic environments, timeboxed surfaces, and remaining uncertainty.
- **Reliance Boundary & Next-Review Trigger:** Explicit statement that the summary records bounded engineering evidence on the named commit—**not** a certification, warranty of defect absence, compliance opinion, or launch authorization—followed by concrete events requiring re-review (e.g., modifying settlement math, changing trust assumptions, or activating governance modules).

#### C. Proportional Individual Finding Spines
- **High / Medium (`--tier S|M|C`):** Metadata strip (`Severity`, `Preconditions`, `Target`) + `### Summary` (`<= 55w`) + `### Description` + `### Verification` + `### Recommendations` (Short-term fix + Long-term invariant).
- **Low / Informational (`--tier low`, `50–180w`, `0` tables, optional diff):** **Three blocks only:** `Target`, `### Description` (`3–5` sentences including explicit blast-radius ceiling: *"Impact is confined to..."*), and `### Recommendation` (`1–2` sentences). Omit standalone `Impact` and `PoC` ceremony.

---

## 2. The 10-Axis 100-Point Blind Evaluation Rubric

### 2.1 Full-Range Scoring Calibration (`0–10` per Axis, `100` Total)

Judges MUST use the **full `0–10` scale** on every axis:
- **`9–10` (Top-1% Maintainer Grade — Calif / Project Zero / AISLE / Core Maintainer bar):** Crisp, unpadded, immediately actionable, subsystem-idiomatic, honest about negative scope and ceilings, portable PoC, natural researcher cadence. **Award `9` or `10` whenever a candidate genuinely hits this bar!**
- **`7–8` (Strong Senior Security Engineer):** Technically accurate, reproducible, zero jargon/slop leaks; minor tightening or style polish possible.
- **`5–6` (Acceptable / Mixed):** Real bug communicated, but noticeable padding, stiff phrasing, minor missing boundary/portability nuance, or mild template friction.
- **`3–4` (Deficient):** Leaks internal scanner IDs/arms, repeats 3-pass invariant triads, omits PoC/diff/workarounds, or inflates severity.
- **`0–2` (Unusable):** Inaccurate root cause, destructive PoC, wrong channel format, or heavy AI slop.

> **Important Calibration Note for Blind Judges:** There is **NO default `6`-point ceiling**! The "Mechanical Hard Ceilings" column below applies **only when the named defect actually occurs in the candidate** (either observed directly in the text or reported by `report_voice_lint.py --json`). Never cap a clean candidate at `6` when no ceiling condition triggered.

---

### 2.2 Anchored Scoring Matrix (`0–10` per Axis)

| Axis | `3–4` (Deficient) | `5–6` (Acceptable / Mixed) | `7–8` (Strong Senior Engineer) | `9–10` (Top-1% Maintainer Grade) | Defect-Triggered Ceilings *(apply ONLY if defect is present)* |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **1. Causal Lead Clarity** | Metadata dump, generic audit preamble, `> 80w`, or omits symbol/outcome. | Names bug in `56–80w` or `3` sents (`> 105w` on Immunefi), or omits version/trigger. | `1–2` sents (`<= 55w`; `1–5` sents on Immunefi) naming `func()`, `file`, trigger, and outcome. | Razor-sharp opening (`25–55w`) with exact version/SHA, `func()`/`file:line`, precondition, and proven outcome on first read. | **`<= 4`** if metadata-bullet lead, `> 80w` (`> 135w` Immunefi), or no code anchor. **`<= 7`** if throat-clearing opener. |
| **2. Proportional Brevity** |Pads simple bugs with filler, repeats 3x (`Expected/Observed/Fix`), or blows tier cap. | Slightly wordy (`10–20%` trimmable), `1` filler heading, or mild summary restatement. | Fits complexity tier naturally (`90–350w` `S`, `180–650w` `M`, `350–1000w` `C`); zero filler headings. | Every sentence does work; simple 1-branch bugs stay compact (`90–220w`); `Details` enters code immediately with zero repetition. | **`<= 4`** if `Expected/Observed/Defensive Fix` triad or breaches hard word cap. |
| **3. Causal Code Precision** | Vague file mention without control-flow/state trace, or wrong symbols. | Names vulnerable function, but omits caller state, stage preconditions, or sibling check. | Accurate caller-to-callee trace, struct/mode state, and `file:line` references. | Exact state transition, natural 1-clause sibling-path contrast, `git bisect` `Introduced in:` SHA + date, and zero synthetic CVE IDs. | **`<= 4`** if hallucinated/unassigned CVE ID cited as fact or zero code symbols in `Details`. |
| **4. Trust-Boundary & Scope Honesty** | Inflates crash/OOB to RCE, ignores boundary doc, or hides non-default config gates. | Right bug class, but buries OS/config/fsck defaults or omits ASan vs. `-O2` delta. | Upfront OS/FS/build/config prerequisites and realistic CVSS vector. | Foregrounded negative scope (*"Stock X builds are unaffected"*), anchored in target boundary doc (`gitsecurityboundary(7)`), explicit blast-radius ceiling + 1-line CVSS rationale. | **`<= 4`** if self-declares `"Confirmed Critical"` or extrapolates unproven RCE. |
| **5. Portable Defensive Verification** | Missing PoC on standalone advisory, opaque blob, or unsafe/host-mutating commands. | Prose-only steps, unstated external deps, or non-portable GNU `sed` breaking macOS/BSD. | Self-contained `mktemp -d` + `trap` or native test harness with build flags and output. | Minimal (`< 35` lines `S`, `< 65` `M/C`), portable POSIX `cat <<'EOF'` heredocs + native plumbing, positive + benign control, harmless assertions. | **`<= 2`** if standalone advisory (`S/M/C`) lacks a reproducer block. |
| **6. Suggested Fix Quality** | Hand-wavy prose advice or uncompiled `// SECURITY-TODO` pseudo-diff. | Fixes one call site while breaking header layering, duplicating loops, or missing sibling helper. | Clean, minimal unified diff matching project style + verified test suite named. | Subsystem-clean header layering, native helpers (`strbuf_tolower()`), hoisted guards, synced sibling callers, backport hunk note, and full-sentence test citation. | **`<= 3`** if `SECURITY-TODO` marker; **`<= 6`** *only* if local code fix is omitted without architectural rationale. |
| **7. Zero Tool / Scanner Jargon** | `>= 3` leaked harness IDs (`fnd-*`, `clm-*`), `4-arm`/`9-arm`, `Steers`, or local `/Users/` paths. | `1–2` leaked scanner labels (`Hop 1`, `verified_local`, `micropatched`, `@*.invalid`). | `0` ID, path, or enum leaks; at most `1` slightly abstract noun. | **`0` internal engine tokens, `0` `Hop 1..N` labels, and `0` local path leaks** anywhere in the file (including post-diff). | **`<= 3`** if `>= 3` leaks; **`<= 5`** if `1–2` leaks (`clm-*`, `4-arm`, `Hop 1`, `/home/<user>`). |
| **8. Zero AI Slop & Prompt Echoes** | `>= 4` AI vocab/puffery hits, `>= 3` em-dashes, lecturing prose, or chatbot pleasantries. | `1–3` slop hits, rubric-echo bold subhead (`**Trust boundary:**`), `- Intended:`/`- Bypass:` pair, or `"Orthogonally to"`. | `0` AI vocab/puffery and `0` prompt-schema echoes; clean punctuation. | **`0` AI slop, `0` rubric-echo subheads, `0` dashes-as-punctuation, `0` callout boxes, `0` minimizing adverbs (`simply/trivially`).** | **`<= 5`** if `>= 2` slop/LLM-tell hits or `>= 3` em-dashes. |
| **9. Humanistic Researcher Voice** | Monotonous robotic cadence (`SD < 3.5w`) OR legalese (`> 50w` run-ons, `> 35%` true passive). | Understandable but stiff (`1` `> 50w` sentence, clipped subjectless fragments, or twin-sentence symmetry). | Active code-subject sentences (`<= 20%` true passive), `0` `> 50w` run-ons, natural sentence mix. | Reads unmistakably like a seasoned subsystem contributor: concrete nouns after `"this"`/`"that"`, crisp boundary pivots mixed with clear causal traces. | **`<= 4`** if `>= 2` run-ons `> 50w` or true `passive_ratio > 0.35`. |
| **10. Triage Frictionlessness** | Wrong channel shape (Markdown in plain-text email, hard-wrapped `<br>` prose in Markdown, monolithic dump, missing GHSA sections). | Minor channel friction (workarounds buried in `Impact`, version range ambiguous, or redundant metadata). | Clean match for target channel (`GHSA`, `72`-col email, `H1`, `Immunefi`, or `Customer`); minor touch-up at most. | Drop-in publishable / `git am`-ready (`< 15`-min maintainer confirmation, single-line Markdown paragraphs, dedicated `### Workarounds`, zero clarification round-trips). | **`<= 4`** if raw Markdown appears in `mailing-list` plain text, Markdown prose hard-wraps mid-paragraph, or unrelated subsystems are bundled. |
