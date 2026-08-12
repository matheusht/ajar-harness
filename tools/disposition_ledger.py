#!/usr/bin/env python3
"""External verdicts on filed findings. The only ground truth this harness has.

Why this exists
---------------
On 2026-08-12 an audit asked whether the harness assigns severity too harshly. Four independent
reviewers read every engagement record and concluded that essentially nothing had ever been filed,
so the question could not be answered. The operator then said that findings HAD been filed and
adjudicated across four programs.

Both were right. Reports were filed; the repository did not know. The single most valuable data the
harness can hold — what an external triager actually decided — lived only in an inbox. Every
argument in that audit was the harness grading itself.

What this measures
------------------
One number: the SEVERITY DELTA, our band minus theirs, over every disposition where both graded.

    delta < 0   we called it LOWER than the program did   -> under-calling (excess rigor)
    delta = 0   we agreed
    delta > 0   we called it HIGHER than the program did   -> over-calling

A distribution centred below zero is the excess-rigor thesis confirmed with outside evidence. One
centred above zero is the opposite. This is the measurement that no amount of internal re-review can
substitute for, because every internal pass shares the priors of the thing being measured.

What it deliberately does NOT do
--------------------------------
It does not rewrite `our_severity` to match the vendor. That field is the record of what we believed
BEFORE we knew, and back-editing it would erase the only signal in the file. It does not average, and
it does not score an engagement. It counts.

Records live at `engagements/<id>/dispositions.jsonl`, append-only, one JSON object per line,
matching `schemas/disposition.schema.json`.

Usage
-----
  disposition_ledger.py record   --engagement DIR --finding ID --program P --our SEV --outcome O [...]
  disposition_ledger.py table    [--root engagements] [--json]
  disposition_ledger.py calibrate [--root engagements] [--json]
  disposition_ledger.py todo     [--root engagements]

Exit 0 always for `table`/`todo`. `calibrate` exits 1 when the delta distribution is lopsided enough
to be a finding about the harness, so CI can surface it.
"""

import argparse
import glob
import json
import os
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEDGER = "dispositions.jsonl"

# Ordered so subtraction is meaningful. `not-assigned` is deliberately absent: a party that closed a
# report without grading it contributes an OUTCOME but no delta, and folding it in as a zero would
# quietly claim agreement that never happened.
BANDS = ["informational", "low", "medium", "high", "critical"]
RANK = {b: i for i, b in enumerate(BANDS)}

# Outcomes that mean the finding was real to the external party, whatever they called it. Used only
# for reporting acceptance rate — never for the delta, which needs both sides to have graded.
ACCEPTING = {"accepted", "accepted_lower_severity", "accepted_higher_severity",
             "credited_via_vendor_advisory"}


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def load_all(root):
    """Every disposition under root, tagged with the file it came from."""
    out = []
    for path in sorted(glob.glob(os.path.join(root, "*", LEDGER))):
        for n, line in enumerate(open(path, errors="replace"), 1):
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                print(f"  ! {path}:{n} is not valid JSON — skipped", file=sys.stderr)
                continue
            rec["_path"] = f"{path}:{n}"
            out.append(rec)
    return out


def delta(rec):
    """our band minus theirs, or None when either side did not grade."""
    ours, theirs = rec.get("our_severity"), rec.get("their_severity")
    if ours not in RANK or theirs not in RANK:
        return None
    return RANK[ours] - RANK[theirs]


# --- commands -----------------------------------------------------------------

def cmd_record(args):
    eng = args.engagement
    if not os.path.isdir(eng):
        print(f"no such engagement directory: {eng}", file=sys.stderr)
        return 2
    rec = {
        "schema_version": 1,
        "engagement": os.path.basename(eng.rstrip("/")),
        "finding_ref": args.finding,
        "program": args.program,
        "recorded_at": now(),
        "our_severity": args.our,
        "outcome": args.outcome,
        "source": {"kind": args.source_kind, "ref": args.source_ref or ""},
        "confidence": args.confidence,
    }
    for key, val in (("report_id", args.report_id), ("their_severity", args.theirs),
                     ("our_vector", args.our_vector), ("their_vector", args.their_vector),
                     ("decided_at", args.decided_at), ("notes", args.notes)):
        if val:
            rec[key] = val
    if args.bounty is not None:
        rec["bounty_usd"] = args.bounty

    path = os.path.join(eng, LEDGER)
    with open(path, "a") as fh:
        fh.write(json.dumps(rec, sort_keys=True) + "\n")
    d = delta(rec)
    print(f"recorded -> {path}")
    print(f"  {rec['finding_ref']}: we said {rec['our_severity']}, "
          f"they said {rec.get('their_severity', '(not graded)')}, outcome {rec['outcome']}"
          + (f", delta {d:+d}" if d is not None else ""))
    return 0


def cmd_table(args):
    recs = load_all(args.root)
    if args.json:
        json.dump(recs, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0
    if not recs:
        print("no dispositions recorded yet.")
        print("Every severity claim in this repo is currently unvalidated against any outside party.")
        return 0
    print(f"{'engagement':26} {'finding':22} {'ours':>9} {'theirs':>11} {'delta':>6}  outcome")
    print("-" * 104)
    for r in recs:
        d = delta(r)
        print(f"{r.get('engagement', '?')[:26]:26} {str(r.get('finding_ref', '?'))[:22]:22} "
              f"{r.get('our_severity', '?'):>9} {str(r.get('their_severity', '-')):>11} "
              f"{(f'{d:+d}' if d is not None else '-'):>6}  {r.get('outcome', '?')}")
    print(f"\n{len(recs)} disposition(s)")
    return 0


def cmd_calibrate(args):
    recs = load_all(args.root)
    graded = [r for r in recs if delta(r) is not None]
    deltas = [delta(r) for r in graded]

    stats = {
        "dispositions": len(recs),
        "both_graded": len(graded),
        "under_called": sum(1 for d in deltas if d < 0),
        "agreed": sum(1 for d in deltas if d == 0),
        "over_called": sum(1 for d in deltas if d > 0),
        "mean_delta": round(sum(deltas) / len(deltas), 3) if deltas else None,
        "accepted": sum(1 for r in recs if r.get("outcome") in ACCEPTING),
        "verified_basis": sum(1 for r in recs if r.get("confidence") == "verified"),
        "operator_recall_basis": sum(1 for r in recs if r.get("confidence") == "operator_recall"),
    }

    # A verdict needs enough records to mean anything. Below the floor this reports and stays quiet:
    # a two-record ledger leaning one way is noise, and treating it as a finding would be the same
    # error the harness keeps catching elsewhere.
    floor = args.min
    if len(graded) < floor:
        stats["verdict"] = "insufficient-data"
        stats["note"] = (f"{len(graded)} graded disposition(s); {floor} needed before the "
                         f"distribution says anything. This is not evidence of calibration.")
    elif stats["under_called"] > stats["over_called"] + stats["agreed"]:
        stats["verdict"] = "under-calling"
        stats["note"] = "we assign lower bands than programs do. The excess-rigor thesis is supported."
    elif stats["over_called"] > stats["under_called"] + stats["agreed"]:
        stats["verdict"] = "over-calling"
        stats["note"] = "we assign higher bands than programs do."
    else:
        stats["verdict"] = "calibrated"
        stats["note"] = "no lopsided direction in the recorded dispositions."

    if args.json:
        json.dump(stats, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        print("Calibration against external verdicts")
        print("-" * 60)
        for k in ("dispositions", "both_graded", "under_called", "agreed", "over_called",
                  "mean_delta", "accepted"):
            print(f"  {k:22} {stats[k]}")
        if stats["operator_recall_basis"]:
            print(f"  {'operator_recall_basis':22} {stats['operator_recall_basis']}  "
                  f"<- unverified; re-check against the program before citing this")
        print(f"\nVERDICT: {stats['verdict'].upper()}")
        print(f"  {stats['note']}")
    return 1 if stats["verdict"] in ("under-calling", "over-calling") else 0


def cmd_todo(args):
    """Filed findings with no disposition recorded. The gap between what we know and what we wrote."""
    recs = load_all(args.root)
    have = {(r.get("engagement"), str(r.get("finding_ref"))) for r in recs}
    print("Engagements with report drafts but no recorded external disposition:")
    print("(each is ground truth the harness cannot currently use)\n")
    n = 0
    for eng_dir in sorted(glob.glob(os.path.join(args.root, "*"))):
        if not os.path.isdir(eng_dir):
            continue
        eng = os.path.basename(eng_dir)
        drafts = (glob.glob(os.path.join(eng_dir, "reports", "*.md"))
                  + glob.glob(os.path.join(eng_dir, "submissions", "*")))
        if not drafts:
            continue
        recorded = sum(1 for e, _ in have if e == eng)
        if recorded == 0:
            n += 1
            print(f"  {eng:34} {len(drafts):>3} report artifact(s), 0 dispositions")
    print(f"\n{n} engagement(s) with unrecorded outcomes.")
    print("Record each with: disposition_ledger.py record --engagement engagements/<id> ...")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("record", help="append one external verdict")
    r.add_argument("--engagement", required=True)
    r.add_argument("--finding", required=True)
    r.add_argument("--program", required=True)
    r.add_argument("--our", required=True, choices=BANDS)
    r.add_argument("--theirs", choices=BANDS + ["not-assigned"])
    r.add_argument("--outcome", required=True,
                   choices=["accepted", "accepted_lower_severity", "accepted_higher_severity",
                            "credited_via_vendor_advisory", "duplicate", "informative",
                            "not_accepted", "out_of_scope", "pending", "withdrawn_by_us"])
    r.add_argument("--report-id", dest="report_id")
    r.add_argument("--our-vector", dest="our_vector")
    r.add_argument("--their-vector", dest="their_vector")
    r.add_argument("--decided-at", dest="decided_at")
    r.add_argument("--bounty", type=float)
    r.add_argument("--notes")
    r.add_argument("--source-kind", dest="source_kind", default="operator_report",
                   choices=["repo_record", "operator_report", "external_url", "vendor_advisory"])
    r.add_argument("--source-ref", dest="source_ref")
    r.add_argument("--confidence", default="operator_recall",
                   choices=["verified", "operator_recall", "provisional"])
    r.set_defaults(fn=cmd_record)

    for name, fn, helptext in (("table", cmd_table, "list every recorded disposition"),
                               ("calibrate", cmd_calibrate, "our bands vs theirs"),
                               ("todo", cmd_todo, "report drafts with no disposition")):
        p = sub.add_parser(name, help=helptext)
        p.add_argument("--root", default=os.path.join(ROOT, "engagements"))
        if name != "todo":
            p.add_argument("--json", action="store_true")
        if name == "calibrate":
            p.add_argument("--min", type=int, default=5,
                           help="graded dispositions needed before a verdict is issued (default 5)")
        p.set_defaults(fn=fn)

    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
