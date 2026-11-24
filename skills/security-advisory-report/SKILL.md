---
name: security-advisory-report
description: Draft maintainer-grade security advisories, GHSAs, bug-bounty reports, plain-text mailing-list disclosures, Immunefi disclosures, and commissioned customer security reviews with complexity-proportional brevity, causal code precision, upfront trust-boundary honesty, portable defensive verification, idiomatic fixes, and zero AI slop or internal harness jargon.
---

# Security Advisory & Report Skill (v2)

Write outbound vulnerability advisories and commissioned security review deliverables so an upstream maintainer, triage lead, or engineering buyer grasps the exact defect, trust boundary, verification check, and fix on the **first read**.

Assume the reader wrote the target subsystem. Never waste maintainer attention on throat-clearing preambles, multi-pass restatement, severity inflation, Goodharted filler, or leaked internal engine telemetry.

**Engine Handoff Boundary:** Internal closeout skills (`ajar-report`) own SQL gates, `report.json` telemetry, and `DEC-0113` SHA-256 preimage ledger sealing. This skill owns **every word of human-facing prose** across external disclosures and customer deliverables.

## Workflow

1. **Run the 5-Point Pre-Flight Check** (Section 1).
2. **Pick the Complexity Tier & Channel** (`S`, `M`, `C`, `low`, `dry`, or `audit` across `ghsa`, `mailing-list`, `h1`, `immunefi`, or `customer`, Section 2).
3. **Load the Channel Spine** from `references/channel-formats-and-rubric.md`.
4. **Draft Using the 7 Core Proof & Craft Rules** (Section 3) and **Voice & Jargon Discipline** (Section 4).
5. **Pass `scripts/report_voice_lint.py --strict`** with `0` errors and `0` warnings before finalizing (Section 5).

---

## 1. Five-Point Pre-Flight & Deduplication Gate

Before drafting prose, verify five fail-closed conditions:

1. **Currentness on `HEAD` and Latest Release Tag:** Confirm the defect reproduces on both the latest release tag and current `main`/`master`.
2. **Silent-Fix, PR, & Advisory Deduplication:** Check open and recently closed PRs, recent commits, changelogs, and published GHSAs/CVEs. **Never invent, guess, or cite unassigned/synthetic CVE or GHSA IDs**; cite only verified public advisories (`CVE-2023-38545`, `CVE-2024-32002`) or exact upstream commit SHAs.
3. **Documented Security Boundary & Capability Delta:**
   - Check explicit target boundary policies and `Known Issues` (`SECURITY.md`, `gitsecurityboundary(7)`, `curl` `vuln-disclosure.html`, OpenSSL Security Policy, CPython/Linux policies, Immunefi `Resources`).
   - Prove a concrete **capability delta**: what an attacker achieves *with* the bug that their required starting privilege could not already do *without* it. Frame non-boundary invariant bugs honestly as defensive hardening.
4. **Root-Cause Grouping vs. Per-Subsystem Splitting:**
   - **Group** sibling entrypoints sharing one root-cause fix into a single advisory scored at the highest reachable impact.
   - **Split** independent subsystems and separate fixes into separate advisories. Never send a multi-subsystem monolithic dump in one external advisory.
5. **Attribution, Ledger Preimage, & AI Policy:** Commit any required `DEC-0113` preimage hash before authorized external transmission. Obey target AI/clean-room patch rules. Keep org names out of technical prose; use at most **one** native footer trailer (`Reported-by: Name <email> (Ajar Labs)` or `Credits:`) or customer cover header.

---

## 2. Complexity-Proportional Budgets ("Simple Where It Needs to Be")

Scale length strictly with **causal complexity**. Never pad a crisp 100-word single-branch bug to hit an arbitrary word quota, and never force 10 headings onto a 1-line fix:

| Tier (`--tier`) | When to Use | Prose Word Band *(Hard Cap)* | `h2`/`h3` Sections | Tables | Reproducer / Diff |
| :--- | :--- | :---: | :---: | :---: | :--- |
| **`low`** | Customer audit Low / Informational hardening or config hygiene | **`50–180w`** *(`<= 220w`)* | `2–3` (`Target`, `Description`, `Recommendation`) | **`0`** | Optional (`<= 4`-line diff); omit `Impact` & `Scenario` |
| **`dry`** | Zero-finding Verified Boundaries or `DEC-0099` buyer-safe summary | **`80–380w`** *(`<= 500w`)* | `3–5` | `<= 1` | Optional; cite verified `file:line` guards |
| **`S`** | Single-branch missing check, NULL/bounds/reset flaw (`CVE-2024-2004`) | **`90–350w`** *(`<= 420w`)* | **`3–4` compact** or `5–6` full GHSA | `<= 1` | **Required** (`< 35`-line check + diff) |
| **`M`** | Stateful protocol/parser interaction, client/server gate split (`CVE-2023-38545`) | **`180–650w`** *(`<= 780w`)* | `4–6` (`h4 <= 2`) | `<= 1` | **Required** (`< 60`-line check + diff) |
| **`C`** | Multi-step state/aliasing composition (`CVE-2023-23946`, `CVE-2024-32002`) | **`350–1,000w`** *(`<= 1,200w`)* | `5–7` (`h4 <= 4`) | `<= 1` | **Required** (`< 65`-line check + diff) |
| **`audit`** | Full multi-finding customer review (`--channel customer`) | Per-finding bands above | Executive split + findings | Per section | Per finding (`High/Med` required; `Low` optional) |

**Compact `Tier S` Rule:** When a single-branch defect takes 4 sentences to explain, use 4 sections (`Summary`, `Details`, `PoC`, `Suggested fix`) unless submitting to a GHSA form that maps `### Impact` and `### Workarounds` directly (`<= 6` sections supported). Cut every sentence that repeats `Summary`.

---

## 3. Seven Core Proof, Triage, & Customer Deliverable Rules

### Rule 1: Channel-Native Causal Lead
- **`ghsa`, `mailing-list`, `h1`, `customer` findings (`1–2` sentences, `25–55w`, cap `80w`):** Pack four anchors into the opening sentences: *(1)* version range or tested commit SHA, *(2)* backticked `function()` and `path/file.c:line`, *(3)* concrete trigger/precondition, and *(4)* proven boundary outcome.
- **`immunefi` (`1–5` sentences, `<= 105w`):** Open `### Quantified Summary & Activation Status` with contract/module address + chain/block, broken invariant, **bounded on-chain exposure ceiling** in native units (isolating unaffected pools; never `minted * spot_price` hyperbole), and live deployment status.
- Ban all throat-clearing (`"During a security review..."`, `"Code review identified..."`, `"This advisory describes..."`).

### Rule 2: Direct Code Entry, Natural Sibling Contrast, & `git bisect` Provenance
- **Zero repetition:** `Summary` states *what happens*; `Details` enters caller-to-callee control flow immediately. Never repeat `Overview -> Description -> Impact -> Scenario` or `Expected / Observed / Defensive Fix` triads.
- **Natural sibling-path contrast:** Contrast the unguarded path against a compliant peer in one natural clause (*"`Curl_socks4a()` rejects hostnames over 255 bytes upfront, whereas `do_SOCKS()` falls back to local resolution without re-checking length"*) rather than stiff twin-sentence symmetry.
- **Archaeological provenance:** Cite `Introduced in commit <12-char-sha> ("<subject>", YYYY-MM-DD)` via `git bisect` plus any incomplete prior fix (`CVE-2023-23946`) so maintainers can scope backports immediately.
- **Zero prompt-schema artifacts:** Never open paragraphs with rubric-echo bold labels (`**Trust boundary and precondition:**`, `**Root cause:**`), never emit `- Intended:` / `- Bypass:` bullet pairs, and never label bug steps as `Hop 1` / `Hop 2`. Name the subsystem mechanics directly.

### Rule 3: Upfront Negative Scope, Boundary Ceilings, & CVSS Discipline
- **Foreground what is NOT affected:** State default vs. non-default config, OS/filesystem, and server-vs-client gates up front (*"Hosting servers with `receive.fsckObjects=true` reject this object on push; exposure is confined to clients cloning with default `transfer.fsckObjects=false`"*).
- **Sandbox & blast-radius ceiling:** Ground claims in the target's boundary doc (`gitsecurityboundary(7)`, sandbox/privilege model) and state what downstream guards prevent (read-only probing vs. file write, ASan crash vs. `-O2` error return).
- **CVSS calibration:** Include a 1-sentence rationale whenever an integrity/UI/AC vector depends on a follow-up subcommand or local ingestion (`UI:R`, `AV:L`). Omit CVSS entirely on projects that reject it (`curl`, `OpenSSL`), and omit redundant top metadata bullets when pasting into structured GHSA web fields.

### Rule 4: Portable, Hermetic, Defensive Verification (`PoC` / `Verification`)
- **Strictly harmless & hermetic:** Use `mktemp -d` + `trap 'rm -rf "$work"' EXIT` or native test harnesses (`test_expect_success`, `pytest`, `cargo test`, `forge test --fork-block-number`). Assert harmless exit codes, diagnostics, or inert marker files inside `$work`.
- **macOS / BSD / Linux portability:** Construct multiline files with **POSIX `cat <<'EOF' >file` heredocs**—never GNU-only `sed -i` or multiline `sed` insertions that fail on macOS. Prefer native plumbing (`git mktree`, `printf`) over external `python3` scripts or hardcoded hash sizes (`SHA-1` vs. `SHA-256`) unless explicitly noted in setup.
- **Positive + Benign Control:** Show both the failing check (**Expected** vs. **Observed**) and a brief benign control confirming normal input succeeds.

### Rule 5: Subsystem-Clean `Suggested Fix`
- **Native idioms & header layering:** Respect subsystem header boundaries (do not pull internal cache headers into unrelated config units when a public `path.h` helper exists), use native string/memory helpers (`strbuf_tolower()`, `Curl_safecmp()`), hoist guards before state-mutating calls, and keep parallel validation helpers in sync.
- **Backport clarity & full sentences:** Note when a multi-hunk patch separates the root state fix from defense-in-depth checks. Write complete sentences with grammatical subjects when citing test runs (*"With this patch applied, `test700` and `test728` pass"*—never clipped *"Passed `test700`"*).

### Rule 6: Dedicated `### Workarounds`
Place concrete no-upgrade CLI/config mitigations in a dedicated **`### Workarounds`** section (mapping 1:1 to the GHSA form field) rather than burying a `Workaround:` sentence inside `Impact`. State plainly if a workaround is partial or if none exists.

### Rule 7: Customer Engagement Split, `DEC-0099` Summary, & Honest Dry Closure
In `--channel customer` deliverables:
1. **Mandatory Executive Split:** Always separate **(a) Unprivileged Live Entrypoint Findings** from **(b) Config/Operator-Gated, Component-Isolated, or Pre-Activation Findings** so buyers never confuse gated defense-in-depth bugs with live unauthenticated exposure.
2. **Buyer-Safe `DEC-0099` Security Review Summary:** Accompany technical reports with a concise, exploit-free summary stating: *(i)* exact repository and commit SHA reviewed, *(ii)* bounded outcome summary, *(iii)* remediation and retest verification status, *(iv)* **material limitations, blocked test paths, and remaining uncertainty**, *(v)* explicit notice that the summary is **not** a certification, warranty of absence, or launch authorization, and *(vi)* concrete **next-review triggers** (architecture changes, new integrations, governance activation).
3. **Zero-Finding ("Dry") Discipline (`--tier dry`):** Never pad a clean scope with Low/Info filler. Report the exact invariant questions tested, `file:line` guards verified, **blocked or unresolved paths**, and remaining assumptions.

---

## 4. Researcher Voice & Zero-Jargon Hygiene

### 4.1 Humanistic Technical Style (`technical-writing` + `unslop`)
1. **Put code in the subject slot:** Default to functions, structs, and callers as subjects (`do_SOCKS() copies...`). Plain `"We verified on Linux and macOS"` is fine; ban self-congratulatory audit narration (*"During our thorough investigation..."*).
2. **Natural rhythm without metric gaming:** One thought per sentence. Mix crisp 6–10 word boundary statements (*"Stock Linux builds are unaffected."*) with 20–30 word causal traces; split sentences above ~35 words (`0` over `50`). Never manufacture artificial 3-word dramatic fragments.
3. **Concrete referents:** Make every `"this"` or `"that"` modify a noun (*"That length truncation..."*). Eliminate trailing `", which allows..."` clauses and tacked-on `-ing` participial tails (*"...overflowing the buffer, causing..."* -> use a main verb).
4. **Zero AI tells or punctuation crutches:** Zero em-dashes (`—`), spaced en-dashes (` – `), or prose double-hyphens (` -- `; POSIX CLI `--` flags are fine). Zero emojis, zero GitHub alert boxes (`> [!IMPORTANT]`) in external advisories, zero `"Orthogonally to"`, zero `"simply/easily/trivially"`, and zero AI puffery (`delve`, `crucial`, `robust`, `leverage`, `utilize`, `comprehensive`, `pivotal`, `catastrophic`, `threat actor`).
5. **One line per paragraph in Markdown (`ghsa`, `h1`, `immunefi`, `customer`) — never hard-wrap prose at 72/80 columns (GFM turns single `\n` into `<br>`); reserve 72-column hard wrapping strictly for `--channel mailing-list` plain text.** Keep every Markdown paragraph and every bullet item on a single unwrapped line.
6. **Precision escape valve:** When any stylistic rule makes a technical statement less accurate or harder to read, rewrite cleanly for accuracy first.

### 4.2 Internal Engine -> External Engineering Translation Map

| Banned Internal / Scanner Token | Maintainer-Facing Translation |
| :--- | :--- |
| `4-arm`, `9-arm`, `Arm 1..9`, `verified_local`, `survived_falsify` | Present directly as `PoC` + `Benign control` + `Suggested fix` + test suite results |
| `micropatched`, `maintainer_patched` *(pre-merge)* | *"Unpatched on `master` at `<sha>`; candidate patch verified locally against `<suite>`"* |
| `clm-*`, `fnd-*`, `cor-*`, `pvf-*`, `chn-*`, `surf-*`, `Hop 1..N` | Omit IDs completely; name subsystem steps directly (*"mode-less copy step"*, *"second patch"*) |
| `locus`, `dry_control_locus`, `primitive`, `sink`, `trust_gadget`, `open door` | Name exact `file.c:line` and concrete behavior (*"cryptographic primitives"* / *"log sink"* are fine) |
| `Workspace Steers`, `epistemic_hooks`, `hook H6`, `gate G3`, `peer_symmetry`, `native_ffi`, `outside_in`, `inside_out`, `Confidence: 8.5` | Omit completely (`HTTP/1..3` `H1`–`H3` and `BLS12-381` / `JVM` `G1`–`G2` are fine) |
| `/home/<user>`, `/Users/<user>`, `/opt/<dir>`, `file:///<path>`, `*@*.invalid` | Hermetic `$work` (`mktemp -d`) paths; real or omitted git trailers |

---

## 5. Mandatory Mechanical Gate (`report_voice_lint.py` v2)

Run the bundled stdlib linter (`ajar-report-voice-lint/2`) in `--strict` mode before finishing any deliverable:

```bash
python3 <path-to-skill>/scripts/report_voice_lint.py <draft_file> \
  --tier <S|M|C|low|dry|audit> \
  --channel <ghsa|mailing-list|h1|immunefi|customer> \
  --strict
```

The gate must exit `0` (`PASS`, `0` errors, `0` warnings, `0` hard-wrapped Markdown lines, and `0` leaks across the entire file including post-diff lines). For channel templates and the full `0–10` per-axis evaluation rubric, load `references/channel-formats-and-rubric.md`.
