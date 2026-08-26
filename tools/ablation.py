#!/usr/bin/env python3
"""Ablation gate for promoted lessons.

The problem this solves
-----------------------
Across ~25 engagements exactly one memory disposition reached `promote`
(engagements/kiwicom-15-07/memory/memory-disposition-r4.json). It was valid, sanitized, reviewed,
and passed every schema gate. Its `winners.md` still reads `(none yet)`, and the lesson appears
nowhere in `skills/` or `engine/`. The mechanism fired exactly as designed and the loop did not
close, because `promote` has no next step.

Separately, of 65+ pattern candidates none has ever reached `promoted`, while doctrine that DID
become machinery got there by someone hand-editing an engine file outside the ledger entirely.

The rule this enforces
----------------------
A lesson is load-bearing only when a decision changes because of it. So a promotion must ship a
fixture that shows the change: run the decision with the lesson applied and with it removed, and the
two outcomes must differ. If removing the lesson changes nothing, it was never load-bearing and the
promotion is prose.

This inverts an ablation the harness already writes for the sensor side
(`docs/post-phase14-capability-fit-review.md`: "disabling retrieval must change no verdict").

No source found in the agent-memory literature measures promotion this way. Voyager, Reflexion,
ExpeL and Constitutional AI all close their loop with a scored benchmark or a weight update; skill
libraries that rely on description-matching triggers publish no trigger-accuracy metric at all. This
is original engineering, so record what it does and does not prove.

Two fixture modes
-----------------
  executable  The lesson is a predicate in a rule module. The tool runs the case with the rule and
              without it and compares. This is a real measurement.
  documented  The lesson landed in prose. The tool can only assert that the named anchor text
              exists in the named file and that the fixture claims a verdict change. Weaker: it
              proves the lesson landed, not that it decides anything. Prefer `executable`.

Usage
-----
  ablation.py run [FIXTURE_DIR ...]     run every fixture, non-zero exit if any fails
  ablation.py check-dispositions        every `promote` disposition must name an ablation fixture
"""

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path

from engagement_records import RecordError
from engagement_state import (
    _relative_regular_files,
    bound_engagement_source,
    read_governed_file,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE_ROOT = os.path.join(ROOT, "fixtures", "ablation")


def _load_rule(path):
    spec = importlib.util.spec_from_file_location("ablation_rule", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_fixture(d):
    """Return (ok, lines). A fixture passes when the lesson demonstrably changes an outcome."""
    lines = []
    fx_path = os.path.join(d, "fixture.json")
    if not os.path.isfile(fx_path):
        return False, [f"{d}: no fixture.json"]
    fx = json.load(open(fx_path))
    name = fx.get("disposition_id", os.path.basename(d))
    mode = fx.get("mode")

    if mode == "executable":
        rule_path = os.path.join(d, fx["rule_module"])
        if not os.path.isfile(rule_path):
            return False, [f"{name}: rule_module {fx['rule_module']} not found"]
        rule = _load_rule(rule_path)
        if not hasattr(rule, "decide"):
            return False, [f"{name}: rule module has no decide(case, lesson_applied) function"]
        # A fixture passes on two conditions, not one:
        #   1. every case decides exactly as declared, and
        #   2. at least one case changes when the lesson is removed.
        # Condition 2 is the load-bearing test. Cases that do NOT change are controls, and they are
        # required: a rule that flips every verdict is a blanket reopen, not a lesson.
        ok = True
        changed = 0
        for case in fx["cases"]:
            with_l = rule.decide(case["input"], lesson_applied=True)
            without_l = rule.decide(case["input"], lesson_applied=False)
            want_w, want_o = case["with_lesson"], case["without_lesson"]
            good = (with_l == want_w and without_l == want_o)
            ok &= good
            differs = with_l != without_l
            changed += differs
            mark = "ok  " if good else "FAIL"
            role = "load-bearing" if differs else "control"
            lines.append(f"  {mark} {name}/{case['id']} [{role}]: "
                         f"with={with_l!r} without={without_l!r} "
                         f"(expected {want_w!r} / {want_o!r})")
        lines.append(f"  {'ok  ' if changed else 'FAIL'} {name}: the lesson changes at least one "
                     f"verdict ({changed}/{len(fx['cases'])} cases)")
        if not changed:
            lines.append("       removing the lesson changed nothing. It is not load-bearing, so "
                         "this promotion is prose. Do not promote it.")
        controls = len(fx["cases"]) - changed
        if not controls:
            lines.append(f"  FAIL {name}: no control case")
            lines.append("       every case flipped. Add a case the lesson must NOT change, or the "
                         "rule is a blanket verdict rather than a discriminating one.")
            ok = False
        return (ok and changed > 0), lines

    if mode == "documented":
        anchor_file = os.path.join(ROOT, fx["landed_in"])
        if not os.path.isfile(anchor_file):
            return False, [f"{name}: landed_in {fx['landed_in']} does not exist"]
        text = open(anchor_file, errors="replace").read()
        found = fx["anchor"] in text
        differ = fx["claimed_with"] != fx["claimed_without"]
        lines.append(f"  {'ok  ' if found else 'FAIL'} {name}: anchor present in {fx['landed_in']}")
        lines.append(f"  {'ok  ' if differ else 'FAIL'} {name}: claims a verdict change")
        lines.append("       mode=documented proves the lesson landed, not that it decides "
                     "anything. Convert to mode=executable when a predicate exists.")
        return (found and differ), lines

    return False, [f"{name}: unknown mode {mode!r} (use executable or documented)"]


def cmd_run(args):
    dirs = args.fixtures or (
        [os.path.join(FIXTURE_ROOT, n) for n in sorted(os.listdir(FIXTURE_ROOT))]
        if os.path.isdir(FIXTURE_ROOT) else [])
    dirs = [d for d in dirs if os.path.isdir(d)]
    if not dirs:
        print("no ablation fixtures found")
        return 0
    bad = 0
    for d in dirs:
        ok, lines = run_fixture(d)
        print("\n".join(lines))
        bad += not ok
    print(f"\n{len(dirs)} fixtures, {bad} failing")
    return 1 if bad else 0


def fixture_index():
    """Map disposition_id -> fixture directory.

    The lookup runs this way round on purpose. Requiring the disposition record to name its fixture
    would mean editing a record after the fact, and CLAUDE.md section 5 makes records append-only
    ("append-only evidence, never self-edited belief"). The fixture points at the disposition, so
    nothing already recorded is touched."""
    idx = {}
    if not os.path.isdir(FIXTURE_ROOT):
        return idx
    for name in sorted(os.listdir(FIXTURE_ROOT)):
        fx = os.path.join(FIXTURE_ROOT, name, "fixture.json")
        if os.path.isfile(fx):
            did = json.load(open(fx)).get("disposition_id")
            if did:
                idx[did] = os.path.join(FIXTURE_ROOT, name)
    return idx


def promote_dispositions(root=ROOT):
    out = []
    engagement_root = Path(root) / "engagements"
    if not engagement_root.is_dir():
        return out
    for engagement in sorted(path for path in engagement_root.iterdir() if path.is_dir() and path.name != "_TEMPLATE"):
        try:
            with bound_engagement_source(
                engagement, allow_ungoverned=True
            ) as bound:
                engagement_rows = []
                for relative in sorted(_relative_regular_files(bound)):
                    name = Path(relative).name
                    if not (
                        name.startswith("memory-disposition")
                        and name.endswith(".json")
                    ):
                        continue
                    try:
                        doc = json.loads(
                            read_governed_file(bound / relative).decode("utf-8")
                        )
                    except (UnicodeDecodeError, json.JSONDecodeError, OSError):
                        continue
                    if doc.get("disposition") == "promote":
                        engagement_rows.append(
                            (
                                os.path.relpath(engagement / relative, root),
                                doc,
                            )
                        )
            # Nothing is admitted until the bound scanner rechecks identity and quarantine.
            out.extend(engagement_rows)
        except (RecordError, OSError):
            continue
    return sorted(out)


def cmd_check_dispositions(args):
    """Every `promote` must have an ablation fixture, and that fixture must pass."""
    idx = fixture_index()
    rows = promote_dispositions()
    bad = 0
    for rel, doc in rows:
        did = doc.get("disposition_id", "(no id)")
        d = idx.get(did)
        if not d:
            print(f"  FAIL {rel}: promote with no ablation fixture for {did!r}")
            print("       a promotion without a demonstrated verdict change is prose")
            bad += 1
            continue
        ok, _ = run_fixture(d)
        print(f"  {'ok  ' if ok else 'FAIL'} {rel}: ablation {os.path.relpath(d, ROOT)}")
        bad += not ok
    print(f"\n{len(rows)} promote dispositions, {bad} without a passing ablation fixture")
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("run")
    p.add_argument("fixtures", nargs="*")
    p.set_defaults(func=cmd_run)
    p = sub.add_parser("check-dispositions")
    p.set_defaults(func=cmd_check_dispositions)
    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
