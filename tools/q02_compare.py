#!/usr/bin/env python3
"""Q-02 prompt-ablation adjudicator (Phase 5).

Roadmap Q-02: does the hand-authored per-target goal prompt earn what it costs? One target, two
arms, one variable. This computes the comparison from two arm directories and applies the
PREREGISTERED decision rule.

The design rule here is the one this repository keeps re-learning: **do not let a tool assert what
it cannot compute.**

  computable from the ledgers   M1 findings, M2 candidates, M5 cost
  partly computable             M3 severity profile, M4 family coverage
  JUDGED, never computed        M6 overlap (needs the same-finding root-cause rule)
                                M7 waste (needs a human reading rounds)

M6 and M7 are the two that decide the verdict, and neither can be derived from a file listing. The
tool emits a worksheet for them and REFUSES to issue a verdict until a blinded adjudicator fills it
in. A tool that guessed M6 would be the harness grading its own homework, which is the failure mode
the whole preregistration exists to prevent.

The threshold is read out of the frozen preregistration, never hardcoded here, so this tool cannot
drift away from the rule that was fixed before the data existed.

Commands:
  measure   compute what is computable; emit the judged-metric worksheet
  verdict   apply the preregistered rule to measurements + a filled worksheet
  --self-test
"""

import argparse
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PREREG = os.path.join(ROOT, "fixtures", "preregistration", "phase5-q02-prompt-ablation.json")


def read_threshold(prereg_path=PREREG):
    """Pull the >=N finding gap out of the frozen rule. Never hardcode it here."""
    with open(prereg_path) as fh:
        doc = json.load(fh)
    rule = doc["decision_rule"]["prompt_earns_its_keep_if"]
    m = re.search(r"M1\(A\)\s*-\s*M1\(B\)\s*>=\s*(\d+)", rule)
    if not m:
        raise SystemExit(f"cannot read the threshold out of {prereg_path}; refusing to guess it")
    return int(m.group(1)), doc


def count_packages(arm, sub):
    d = os.path.join(arm, sub)
    if not os.path.isdir(d):
        return []
    return sorted(
        os.path.basename(p.rstrip("/"))
        for p in glob.glob(os.path.join(d, "*/"))
    )


def jsonl_rows(path):
    if not os.path.isfile(path):
        return []
    return [json.loads(l) for l in open(path) if l.strip()]


def severity_profile(arm):
    prof = {}
    for pkg in glob.glob(os.path.join(arm, "findings", "*/")):
        fj = os.path.join(pkg, "finding.json")
        if not os.path.isfile(fj):
            continue
        try:
            band = (json.load(open(fj)).get("severity") or {})
            band = band.get("band") if isinstance(band, dict) else band
        except Exception:
            band = None
        prof[band or "unstated"] = prof.get(band or "unstated", 0) + 1
    return prof


def subagent_spend(arm):
    """Read the per-round spend the brief required in progress.md. Absent is reported, not zeroed."""
    p = os.path.join(arm, "progress.md")
    if not os.path.isfile(p):
        return None
    nums = [int(n) for n in re.findall(r"(?:subagents?|agents?)[^0-9\n]{0,20}(\d{1,3})",
                                       open(p).read(), re.I)]
    return sum(nums) if nums else None


def measure_arm(arm):
    return {
        "path": os.path.relpath(arm, ROOT),
        "M1_findings": count_packages(arm, "findings"),
        "M2_candidates": count_packages(arm, "unproven"),
        "M3_severity": severity_profile(arm),
        "M5_attempts": len(jsonl_rows(os.path.join(arm, "attempts.jsonl"))),
        "M5_events": len(jsonl_rows(os.path.join(arm, "events.jsonl"))),
        "M5_subagents": subagent_spend(arm),
    }


WORKSHEET = {
    "_instructions": "Filled by an adjudicator who ran NEITHER arm, judging packages with arm "
                     "labels, paths and timestamps stripped. See the preregistration's "
                     "same_finding_rule: two findings are the same only if they share a root cause "
                     "-- the same defective decision in the same function or config key.",
    "adjudicator": None,
    "blinding_held": None,
    "run_record": {
        "ran_concurrently": None,
        "sequence_order_if_sequential": None,
        "cross_arm_read_occurred": None,
        "limit_truncated_an_arm": None
    },
    "M6_overlap": {"both_arms": None, "arm_a_only": None, "arm_b_only": None},
    "M7_waste": {"arm_a_wasted_rounds": None, "arm_b_wasted_rounds": None,
                 "waste_class_a_avoided_that_b_hit": None},
    "M4_families": {"arm_a": None, "arm_b": None}
}


def cmd_measure(args):
    a, b = os.path.join(args.engagement, "arm-a"), os.path.join(args.engagement, "arm-b")
    for p in (a, b):
        if not os.path.isdir(p):
            raise SystemExit(f"missing arm directory: {p}")
    out = {"engagement": os.path.relpath(args.engagement, ROOT),
           "arm_a": measure_arm(a), "arm_b": measure_arm(b),
           "computed_only": "M6 and M7 are judged, not computed. Fill the worksheet."}
    print(json.dumps(out, indent=2, sort_keys=True))
    if args.worksheet:
        if os.path.exists(args.worksheet) and not args.force:
            raise SystemExit(f"{args.worksheet} exists; pass --force to overwrite")
        with open(args.worksheet, "w") as fh:
            json.dump(WORKSHEET, fh, indent=2)
            fh.write("\n")
        sys.stderr.write(f"\nworksheet written to {args.worksheet}\n")
    return 0


def decide(m, w, threshold):
    """Apply the preregistered rule. Returns (verdict, reasons, blockers)."""
    blockers = []
    if w.get("blinding_held") is False:
        blockers.append("blinding failed: the M6 split is unreliable and must be reported as such")
    rr = w.get("run_record") or {}
    if rr.get("limit_truncated_an_arm"):
        blockers.append("an account/rate limit truncated one arm: the equal-budget rule broke, so "
                        "a full arm would be compared against a cut-short one")
    if rr.get("cross_arm_read_occurred"):
        blockers.append("a cross-arm read occurred: the arms are not independent")
    for k in ("both_arms", "arm_a_only", "arm_b_only"):
        if (w.get("M6_overlap") or {}).get(k) is None:
            blockers.append(f"M6_overlap.{k} is unfilled -- it is judged, and the tool will not guess it")
    if blockers:
        return "inconclusive", ["preregistration guard tripped"], blockers

    a, b = len(m["arm_a"]["M1_findings"]), len(m["arm_b"]["M1_findings"])
    gap = a - b
    reasons = [f"M1(A)={a}, M1(B)={b}, gap={gap:+d}, preregistered threshold >= {threshold}"]

    if a == 0 and b == 0:
        reasons.append("both arms found nothing; a two-arm null says nothing about prompts")
        return "inconclusive", reasons, []

    waste = (w.get("M7_waste") or {}).get("waste_class_a_avoided_that_b_hit")
    if gap >= threshold:
        reasons.append("the finding gap meets the preregistered threshold")
        return "prompt_earns_its_keep", reasons, []
    if waste:
        reasons.append(f"arm A avoided a documented waste class arm B hit: {waste}")
        return "prompt_earns_its_keep", reasons, []
    if b >= a:
        reasons.append("arm B matched or beat arm A")
        return "prompt_does_not_earn_its_keep", reasons, []

    sa, sb = m["arm_a"].get("M5_subagents"), m["arm_b"].get("M5_subagents")
    if abs(gap) <= 1:
        if sa is not None and sb is not None and sa > sb:
            reasons.append(f"gap <= 1 while arm A cost more (subagents {sa} vs {sb})")
            return "prompt_does_not_earn_its_keep", reasons, []
        reasons.append("gap <= 1 and cost is not recorded on both arms, so the cost clause cannot "
                       "be evaluated; a gap of one was preregistered as noise")
        return "inconclusive", reasons, []
    return "inconclusive", reasons + ["no preregistered branch matched"], []


def cmd_verdict(args):
    threshold, doc = read_threshold(args.prereg)
    m = json.load(open(args.measurements))
    w = json.load(open(args.worksheet))
    verdict, reasons, blockers = decide(m, w, threshold)
    print(f"preregistration: {doc['preregistration_id']}")
    print(f"VERDICT: {verdict}\n")
    for r in reasons:
        print("  -", r)
    if blockers:
        print("\nblocked by:")
        for b in blockers:
            print("  !", b)
    print("\nlicenses: " + doc["decision_rule"]["what_this_can_and_cannot_license"][:220] + "...")
    return 0


# ---------------------------------------------------------------- self-test

def _m(a, b, sa=None, sb=None):
    return {"arm_a": {"M1_findings": ["f"] * a, "M5_subagents": sa},
            "arm_b": {"M1_findings": ["f"] * b, "M5_subagents": sb}}


def _w(**kw):
    w = json.loads(json.dumps(WORKSHEET))
    w["blinding_held"] = True
    w["run_record"] = {"ran_concurrently": True, "cross_arm_read_occurred": False,
                       "limit_truncated_an_arm": False}
    w["M6_overlap"] = {"both_arms": 0, "arm_a_only": 0, "arm_b_only": 0}
    w.update(kw)
    return w


def self_test():
    ok = True
    th, _ = read_threshold()

    def check(name, cond, detail=""):
        nonlocal ok
        ok &= bool(cond)
        print(f"  {'ok  ' if cond else 'FAIL'} {name}" + (f"  -> {detail}" if not cond else ""))

    print(f"[self-test] threshold is read from the frozen preregistration (got {th})")
    check("threshold is 2", th == 2)

    print("[self-test] the three preregistered outcomes")
    v, _, _ = decide(_m(5, 2), _w(), th)
    check("gap >= 2 earns its keep", v == "prompt_earns_its_keep", v)
    v, _, _ = decide(_m(0, 0), _w(), th)
    check("both zero is inconclusive", v == "inconclusive", v)
    v, _, _ = decide(_m(2, 4), _w(), th)
    check("arm B ahead does not earn its keep", v == "prompt_does_not_earn_its_keep", v)

    print("[self-test] a gap of one is NOT a result")
    v, _, _ = decide(_m(3, 2, sa=60, sb=12), _w(), th)
    check("gap 1 + A costs more -> does not earn its keep", v == "prompt_does_not_earn_its_keep", v)
    v, _, _ = decide(_m(3, 2), _w(), th)
    check("gap 1 + no cost data -> inconclusive, never a win", v == "inconclusive", v)

    print("[self-test] the waste clause")
    v, _, _ = decide(_m(1, 1), _w(M7_waste={"waste_class_a_avoided_that_b_hit": "misattribution"}), th)
    check("a documented waste class A avoided earns its keep", v == "prompt_earns_its_keep", v)

    print("[self-test] guards refuse a verdict rather than issuing a wrong one")
    v, _, bl = decide(_m(9, 0), _w(blinding_held=False), th)
    check("blinding failure blocks even a landslide", v == "inconclusive" and bl, v)
    w = _w(); w["run_record"]["limit_truncated_an_arm"] = True
    v, _, bl = decide(_m(9, 0), w, th)
    check("a truncated arm blocks", v == "inconclusive" and bl, v)
    w = _w(); w["run_record"]["cross_arm_read_occurred"] = True
    v, _, bl = decide(_m(9, 0), w, th)
    check("a cross-arm read blocks", v == "inconclusive" and bl, v)
    w = _w(); w["M6_overlap"]["arm_b_only"] = None
    v, _, bl = decide(_m(9, 0), w, th)
    check("an unfilled judged metric blocks (never guessed)", v == "inconclusive" and bl, v)

    print("\nSELF-TEST:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--self-test", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    m = sub.add_parser("measure")
    m.add_argument("--engagement", required=True)
    m.add_argument("--worksheet"); m.add_argument("--force", action="store_true")
    m.set_defaults(fn=cmd_measure)
    v = sub.add_parser("verdict")
    v.add_argument("--measurements", required=True); v.add_argument("--worksheet", required=True)
    v.add_argument("--prereg", default=PREREG); v.set_defaults(fn=cmd_verdict)
    args = ap.parse_args()
    if args.self_test:
        return self_test()
    if not getattr(args, "fn", None):
        ap.print_help(); return 2
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
