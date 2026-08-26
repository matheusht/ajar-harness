#!/usr/bin/env python3
"""Operator-intervention ledger.

Records one entry per correction that an operator or an independent check makes to harness output.

Why this exists
---------------
OSLit `CLM-0001` states the promotion requirement for autonomy: "Instrument comparable engagements
and demonstrate that founder interventions decline without lower external acceptance, higher false
confirmation, or weaker evidence." No instrument existed. Answering "where does the operator spend
attention?" required a manual read of 15 engagements' prose. This makes it a query.

It also feeds two other things:
  * `tools/score-finding.py` takes its regression corpus from entries where machine_checkable=true.
  * The pattern-promotion path has never had a structured input. This is it.

Design notes
------------
Append-only. `add` refuses to overwrite an existing id. Corrections to a record are new records,
never edits, matching the append-only evidence rule in CLAUDE.md section 5.

`provenance` separates `live` entries from `backfilled` ones. A backfilled entry is reconstructed
from writing after the fact and is weaker evidence. `report` never mixes them in one figure without
labelling both.

Usage
-----
  intervention_ledger.py validate [PATH ...]      validate files against the schema
  intervention_ledger.py add --file F --json '{}' append one entry
  intervention_ledger.py report [PATH ...]        counts by stage, class, latency, root cause
  intervention_ledger.py corpus [PATH ...]        emit the machine-checkable subset for score-finding
"""

import argparse
import collections
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA_PATH = os.path.join(ROOT, "schemas", "intervention.schema.json")
DEFAULT_GLOB = os.path.join(ROOT, "fixtures", "interventions", "*.json")


def load_schema():
    with open(SCHEMA_PATH) as fh:
        return json.load(fh)


def load_files(paths):
    """Return (path, document) pairs. Expand globs and directories."""
    out = []
    if not paths:
        paths = sorted(glob.glob(DEFAULT_GLOB))
    for p in paths:
        if os.path.isdir(p):
            out.extend(load_files(sorted(glob.glob(os.path.join(p, "*.json")))))
            continue
        for hit in sorted(glob.glob(p)) or [p]:
            with open(hit) as fh:
                out.append((hit, json.load(fh)))
    return out


def entries_of(doc):
    return doc.get("entries", []) if isinstance(doc, dict) else list(doc)


# --- validation ---------------------------------------------------------------

def validate_entry(entry, schema, jsonschema):
    """Return a list of error strings. Empty means valid."""
    errors = []
    if jsonschema is not None:
        validator = jsonschema.Draft202012Validator(schema)
        for err in sorted(validator.iter_errors(entry), key=lambda e: list(e.path)):
            loc = ".".join(str(x) for x in err.path) or "(root)"
            errors.append(f"{loc}: {err.message}")
        return errors

    # Fallback when jsonschema is absent: check the contract this tool actually depends on.
    for field in schema["required"]:
        if field not in entry:
            errors.append(f"(root): missing required field {field!r}")
    for field, spec in schema["properties"].items():
        if field not in entry or "enum" not in spec:
            continue
        if entry[field] not in spec["enum"]:
            errors.append(f"{field}: {entry[field]!r} is not one of {spec['enum']}")
    return errors


def cmd_validate(args):
    schema = load_schema()
    try:
        import jsonschema
    except ImportError:
        jsonschema = None
        print("note: jsonschema is absent; running the reduced structural check")

    total, bad, no_quote = 0, 0, 0
    seen_ids = {}
    for path, doc in load_files(args.paths):
        for entry in entries_of(doc):
            total += 1
            eid = entry.get("intervention_id", "(no id)")
            errs = validate_entry(entry, schema, jsonschema)

            if eid in seen_ids:
                errs.append(f"intervention_id: duplicate, first seen in {seen_ids[eid]}")
            else:
                seen_ids[eid] = path

            # A record with no quote cannot be audited. The schema allows it; this tool does not.
            refs = entry.get("source_refs") or []
            if not any(r.get("quote") for r in refs):
                no_quote += 1
                errs.append("source_refs: no ref carries a quote; the record cannot be audited")

            if errs:
                bad += 1
                print(f"FAIL {path} :: {eid}")
                for e in errs:
                    print(f"       {e}")

    print(f"\n{total} entries, {bad} failing ({no_quote} without a quote)")
    return 1 if bad else 0


# --- append -------------------------------------------------------------------

def cmd_add(args):
    schema = load_schema()
    try:
        import jsonschema
    except ImportError:
        jsonschema = None

    entry = json.loads(args.json)
    errs = validate_entry(entry, schema, jsonschema)
    if errs:
        print("refusing to add: the entry does not validate")
        for e in errs:
            print(f"  {e}")
        return 1

    path = args.file
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.isfile(path):
        with open(path) as fh:
            doc = json.load(fh)
    else:
        doc = {"schema_version": 1, "method": "live capture", "entries": []}

    existing = {e.get("intervention_id") for e in doc.get("entries", [])}
    if entry["intervention_id"] in existing:
        print(f"refusing to add: {entry['intervention_id']} already exists. The ledger is append-only;")
        print("record a correction as a new entry rather than editing this one.")
        return 1

    doc.setdefault("entries", []).append(entry)
    with open(path, "w") as fh:
        json.dump(doc, fh, indent=2)
        fh.write("\n")
    print(f"added {entry['intervention_id']} to {path}")
    return 0


# --- report -------------------------------------------------------------------

def _table(title, counter, total):
    print(f"\n{title}")
    for key, n in counter.most_common():
        share = (100.0 * n / total) if total else 0.0
        print(f"  {n:4d}  {share:5.1f}%  {key}")


def cmd_report(args):
    rows = [e for _, doc in load_files(args.paths) for e in entries_of(doc)]
    if not rows:
        print("no entries found")
        return 0

    live = [e for e in rows if e.get("provenance") == "live"]
    back = [e for e in rows if e.get("provenance") == "backfilled"]

    print(f"{len(rows)} entries: {len(live)} live, {len(back)} backfilled")
    if back and live:
        print("Report these two groups apart. A backfilled entry is reconstructed from writing and is")
        print("weaker evidence than one captured when the correction happened.")

    groups = [("live", live), ("backfilled", back)] if (live and back) else [("all", rows)]
    for label, group in groups:
        if not group:
            continue
        n = len(group)
        print(f"\n{'=' * 62}\n{label}: {n} entries\n{'=' * 62}")
        _table("by stage (the stage that produced the wrong claim)",
               collections.Counter(e.get("stage", "?") for e in group), n)
        _table("by judgement class (what the operator supplied)",
               collections.Counter(e.get("judgement_class", "?") for e in group), n)
        _table("by root cause",
               collections.Counter(e.get("root_cause", "?") for e in group), n)
        _table("by latency (how long the wrong claim survived)",
               collections.Counter(e.get("latency", "?") for e in group), n)
        _table("by engagement",
               collections.Counter(e.get("engagement_id", "?") for e in group), n)

        early = sum(1 for e in group if e.get("latency") == "same-round")
        print(f"\nearly-catch rate: {early}/{n} = {100.0 * early / n:.1f}%")

        # Report by reusable family, not by machine_checkable. A corpus of N unique check shapes
        # gives a tool N special cases; only recurring families scope a general grader.
        fams = collections.Counter(e.get("check_family") for e in group if e.get("check_family"))
        reusable = sum(v for k, v in fams.items() if k and k != "one-off")
        flagged = sum(1 for e in group if e.get("machine_checkable"))
        if fams:
            _table("by check family (a family is a reusable check; one-off is not)", fams, n)
            print(f"\nflagged machine_checkable : {flagged}/{n} = {100.0 * flagged / n:.1f}%")
            print(f"in a reusable family      : {reusable}/{n} = {100.0 * reusable / n:.1f}%")
            print("  -> the SECOND number scopes tools/score_finding.py. The first counts claims a")
            print("     program could check one at a time, which does not generalise into a tool.")
            modes = collections.Counter(e.get("check_mode") for e in group
                                        if e.get("check_family") not in (None, "one-off"))
            for mode, cnt in modes.most_common():
                note = ("decided from the artifacts" if mode == "computable"
                        else "cannot be judged, but a missing reference can be refused")
                print(f"     {mode:11s} {cnt:3d}  {note}")
        else:
            print(f"machine-checkable flagged: {flagged}/{n} = {100.0 * flagged / n:.1f}%")
            print("  -> no check_family assigned yet; do not scope a tool from this number.")
    return 0


# --- corpus -------------------------------------------------------------------

def cmd_corpus(args):
    """Emit the machine-checkable subset. This is the regression corpus for score-finding.py."""
    rows = [e for _, doc in load_files(args.paths) for e in entries_of(doc)]
    picked = [e for e in rows if e.get("machine_checkable")]
    shapes = collections.Counter(e.get("check_shape", "(unnamed)") for e in picked)
    out = {
        "schema_version": 1,
        "derived_from": "fixtures/interventions/",
        "note": ("Entries a deterministic check could have caught. This measures the catch rate for "
                 "error shapes that already happened. It does not measure the rate for new shapes. "
                 "Do not report it as a false-negative rate."),
        "check_shapes": dict(shapes.most_common()),
        "entries": picked,
    }
    json.dump(out, sys.stdout, indent=2)
    sys.stdout.write("\n")
    print(f"\n{len(picked)} of {len(rows)} entries are machine-checkable", file=sys.stderr)
    return 0


def cmd_live(args):
    """Capture one intervention AS IT HAPPENS during a standby run.

    Live capture is the point. The 62 backfilled entries were reconstructed from prose written
    afterwards, which loses the ones nobody thought worth writing down, and it cannot be produced
    during a run. `provenance` stays separate so the two never merge into one figure.

    The id uses today's date and the next free sequence number, so an operator mid-run does not have
    to invent one."""
    import datetime
    today = datetime.date.today().strftime("%Y%m%d")
    path = args.outfile or os.path.join(
        ROOT, "fixtures", "interventions", f"live-{args.engagement}.json")

    existing = []
    if os.path.isfile(path):
        existing = json.load(open(path)).get("entries", [])
    seq = 1 + max([int(e["intervention_id"][-3:]) for e in existing
                   if e.get("intervention_id", "").startswith(f"INT-{today}")] or [0])

    src, _, line = args.source.partition(":")
    ref = {"path": src, "quote": args.quote}
    if line.isdigit():
        ref["line"] = int(line)

    entry = {
        "schema_version": 1,
        "intervention_id": f"INT-{today}-{seq:03d}",
        "engagement_id": args.engagement,
        "provenance": "live",
        "stage": args.stage,
        "judgement_class": args.jclass,
        "detected_by": args.detected_by,
        "latency": args.latency,
        "claim_before": args.before,
        "claim_after": args.after,
        "root_cause": args.root_cause,
        "source_refs": [ref],
    }
    if args.machine_checkable:
        entry["machine_checkable"] = True
        if not args.check_shape:
            print("refusing: --machine-checkable requires --check-shape")
            print("an unnamed check cannot become a regression case")
            return 1
        entry["check_shape"] = args.check_shape

    ns = argparse.Namespace(file=path, json=json.dumps(entry))
    return cmd_add(ns)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("validate", help="validate entries against the schema")
    p.add_argument("paths", nargs="*")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("add", help="append one entry")
    p.add_argument("--file", required=True)
    p.add_argument("--json", required=True)
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("live", help="capture one live intervention during a run")
    p.add_argument("--engagement", required=True)
    p.add_argument("--stage", required=True)
    p.add_argument("--class", dest="jclass", required=True)
    p.add_argument("--before", required=True)
    p.add_argument("--after", required=True)
    p.add_argument("--root-cause", required=True)
    p.add_argument("--source", required=True,
                   help="path[:line] where the wrong claim appeared")
    p.add_argument("--quote", required=True,
                   help="the wrong claim, verbatim. A record with no quote cannot be audited.")
    p.add_argument("--detected-by", default="operator")
    p.add_argument("--latency", default="same-round")
    p.add_argument("--machine-checkable", action="store_true")
    p.add_argument("--check-shape", default=None)
    p.add_argument("--file", dest="outfile", default=None)
    p.set_defaults(func=cmd_live)

    p = sub.add_parser("report", help="counts by stage, class, latency, root cause")
    p.add_argument("paths", nargs="*")
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("corpus", help="emit the machine-checkable subset")
    p.add_argument("paths", nargs="*")
    p.set_defaults(func=cmd_corpus)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
