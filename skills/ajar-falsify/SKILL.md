---
name: ajar-falsify
description: Challenge candidate findings using EpistemicGuard provenance checks, false-positive corpora, and verify.py cross-family critique before spending verification or reporting effort.
---

# Ajar Falsify (`v3.6-Balanced`)

Use this skill as the kill-biased disconfirmation filter on candidates in `.ajar/candidates.jsonl`. A finding is never accepted on prose agreement; it must survive adversarial code falsification and mechanical `C3` verification in `verify.py`.

## 1. Five Disconfirmation Checks

Before promoting a candidate to `ajar verify`, test all five failure modes against `skills/references/false-positive-controls-corpus.md` and `skills/references/rejected-disputed-cve-corpus.md`:

1. **Upstream Guard & Caller Check:** Read every caller and guard helper between `entry_span` and `sink_symbol` (satisfying `EpistemicGuard.check_sink_counterfactual`). Confirm middleware, parser bounds, type invariants, or modifiers do not already reject or normalize the payload.
2. **Principal & Trust-Boundary Check:** Confirm the required attacker precondition does not already grant the claimed capability (for example, local admin running commands, database superuser, or operator-only CLI flags). Never conflate unprivileged external callers with permissioned operators.
3. **False-Positive Trap Check:** Reject claims backed only by echoed input, HTTP `200` without unauthorized state change, inert text inside escaped sinks, or non-exploitable debug assertions that disappear in release builds.
4. **Tautology & Anti-Cheat Check (`verify.py`):** Confirm `repro_cmd` executes the real target binary or library API and triggers `sink_symbol` + `failure_oracle` organically—never `exit 1`, `false`, synthetic `stub.c` bypasses, or source-text `grep`/`rg` checks (mechanically rejected by `_is_tautological_repro`).
5. **State & Configuration Realism:** Confirm the vulnerable path is reachable under default or documented production settings, and check sibling implementations or downstream callers to ensure an outer boundary does not neutralize the effect.

## 2. Cross-Family Critic Gate (`verify.py` / `llm.py`)

During `ajar verify <repo> --runs 3`, `verify.py` automatically invokes a **Cross-Family Critic** (`resolve_role_model("critic")`, rejecting `zhipu-glm` self-critique) on candidates that pass pre-patch/post-patch mechanical checks:

- **`APPROVE`:** Mints `Verdict(status="VERIFIED", truth_level="C3")`.
- **`REJECT`:** Marks `Verdict(status="REJECTED", truth_level="C2")`, blocking advisory export.
- **`--offline` mode:** Skips the critic and caps truth at `C2` (exported only to `hardening-notes/`, never `advisories/`).

## 3. Record Falsification Outcomes Cleanly

- **Completely refuted:** Set `"withdrawn": true` on the candidate in `.ajar/candidates.jsonl` and post a `dead_end` event with the verified guard `file:line` to `.ajar/whiteboard.sqlite` (primary SQLite WAL + FTS5 store; `.ajar/events.jsonl` audit mirror; withdrawn drafts are omitted from `ajar report` per `DEC-0139`).
- **Defense-in-depth / non-security gap:** Reclassify as `"category": "hardening"` and `"severity": "informational"` so `ajar report` routes it to `hardening-notes/` instead of `advisories/`.
- **Shifted root cause or partial primitive:** Update `entry_span`, `sink_symbol`, `root_cause`, and `patch_diff` to the true locus, or post the surviving partial capability as an `effect` on `.ajar/WHITEBOARD.md` for `chain_weaver.py`.
- **Survived disconfirmation:** Proceed immediately to `ajar verify <repo> --candidate-id <id> --runs 3`.
