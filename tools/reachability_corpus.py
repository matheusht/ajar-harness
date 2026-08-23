#!/usr/bin/env python3
"""Phase 7 step 1 — build the reachability corpus, and report the denominator.

`docs/research/static-analysis-and-knowledge-base-plan.md` A.2 specifies the experiment: express
each adjudicated finding as a source-to-sink claim, run it through a dataflow engine, and compute
three numbers -- confirm rate, miss rate, contradiction rate.

Its own ground rule 1 is "measure before we build", and ground rule 4 is "report the denominator".
This does both, BEFORE anyone installs a multi-gigabyte engine. It answers: how many adjudicated
cases actually exist, in what language, and how many are even dataflow-shaped?

Three exclusions, each of which would otherwise inflate the corpus:

  QUARANTINED   spotify-backstage-2026-07's adjudications were produced by a script with the
                verdict already decided (see its QUARANTINE-synthetic-adjudication.md). Measuring
                an engine's agreement with a fabrication measures nothing. This is the single
                largest exclusion and dropping it is not optional.
  NO-TUPLE      the package records no source and no sink, so no query can be written from it.
                This is currently EVERY non-quarantined package, and the cause is structural:
                `schemas/finding.schema.json` has no `source` or `sink` field. The claim exists in
                prose inside `proof` and `objective`; nothing carries it in machine-readable form.
                That is the concrete Phase 7 blocker, and it is fixable in the schema.

A shape hint (CI config, credential-at-rest, supply-chain, dataflow) is reported per case and is
NEVER used to exclude one. An earlier version of this tool excluded on that regex and threw out 11
of 13 cases, including `D1-route-codegen-injection` -- an injection finding, labelled "authorization
configuration" because its prose mentions permissions. A classifier that decides the corpus has to
be better than the thing it is measuring.

Usage:
  python3 tools/reachability_corpus.py [--json] [--include-quarantined]
"""

import argparse
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Engagements whose adjudications cannot serve as ground truth, with the reason.
QUARANTINED = {
    "spotify-backstage-2026-07":
        "adjudication was script-generated with the verdict pre-decided "
        "(QUARANTINE-synthetic-adjudication.md)",
}

LANG_PATTERNS = [
    ("typescript", [r"\.ts\b", r"\.mts\b", r"typescript"]),
    ("javascript", [r"\.js\b", r"\.mjs\b", r"\.cjs\b", r"javascript"]),
    ("go",         [r"\.go\b", r"golang"]),
    ("python",     [r"\.py\b", r"\bpython\b"]),
    ("java",       [r"\.java\b"]),
    ("solidity",   [r"\.sol\b"]),
]
# Shape HINTS only. These are regexes over the package text, and text is a weak instrument for
# "is this a dataflow question" -- an injection finding whose prose happens to say "permission" hits
# the authorization pattern. They are reported as hints and NEVER used to exclude a case. Getting
# this wrong in the other direction would let a bad classifier decide the corpus.
SHAPE_HINTS = [
    (r"\.ya?ml\b|workflow|github actions|pull_request_target", "CI/workflow configuration"),
    (r"credential|secret|token|private key|passphrase", "credential handling / secret at rest"),
    (r"lockfile|dist-tag|registry|integrity hash|publish", "supply-chain / package integrity"),
    (r"permission|acl|rbac|approver|review gate", "authorization configuration"),
]


def classify_language(blob):
    for name, pats in LANG_PATTERNS:
        if any(re.search(p, blob) for p in pats):
            return name
    return "unknown"


def shape_hint(blob):
    for pat, label in SHAPE_HINTS:
        if re.search(pat, blob):
            return label
    return "possibly dataflow-shaped"


def extract_tuple(doc):
    """Pull a source->sink claim if the package states one. Never invent it."""
    src = doc.get("source") or doc.get("entrypoint") or (doc.get("claim") or {}).get("source")
    snk = doc.get("sink") or (doc.get("claim") or {}).get("sink")
    return (src, snk) if (src or snk) else (None, None)


def scan(include_quarantined=False):
    rows = []
    for eng_dir in sorted(glob.glob(os.path.join(ROOT, "engagements", "*/"))):
        eng = os.path.basename(eng_dir.rstrip("/"))
        for verdict, sub in (("confirmed", "findings"), ("adjudicated-negative", "unproven")):
            for pkg in sorted(glob.glob(os.path.join(eng_dir, sub, "*/"))):
                name = os.path.basename(pkg.rstrip("/"))
                if sub == "unproven" and not re.search(r"REFUT|DEMOT", name, re.I):
                    continue        # an open partial is not an adjudicated negative
                fj = os.path.join(pkg, "finding.json")
                blob = ""
                doc = {}
                if os.path.isfile(fj):
                    try:
                        doc = json.load(open(fj))
                        blob = json.dumps(doc).lower()
                    except Exception:
                        pass
                if not blob:
                    for md in glob.glob(os.path.join(pkg, "*.md")):
                        blob += open(md, errors="ignore").read().lower()[:8000]
                usable, why = True, None
                if eng in QUARANTINED and not include_quarantined:
                    usable, why = False, "QUARANTINED: " + QUARANTINED[eng]
                src, snk = extract_tuple(doc)
                if usable and not (src or snk):
                    usable, why = False, ("NO-TUPLE: the package records no source and no sink -- "
                                          "schemas/finding.schema.json has no field for either")
                rows.append({"engagement": eng, "package": name, "verdict": verdict,
                             "language": classify_language(blob), "usable": usable,
                             "excluded_because": why, "shape_hint": shape_hint(blob),
                             "source": src, "sink": snk, "fields": sorted(doc)[:20]})
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--include-quarantined", action="store_true")
    args = ap.parse_args()
    rows = scan(args.include_quarantined)

    if args.json:
        print(json.dumps(rows, indent=2, sort_keys=True))
        return 0

    total = len(rows)
    usable = [r for r in rows if r["usable"]]
    pos = [r for r in usable if r["verdict"] == "confirmed"]
    neg = [r for r in usable if r["verdict"] == "adjudicated-negative"]

    print(f"adjudicated packages found          : {total}")
    print(f"usable as reachability ground truth : {len(usable)}")
    print(f"  confirmed (positives)             : {len(pos)}")
    print(f"  adjudicated negatives             : {len(neg)}")

    from collections import Counter
    print("\nexclusions")
    for reason, n in Counter(r["excluded_because"].split(":")[0]
                             for r in rows if not r["usable"]).most_common():
        print(f"  {reason:14s} {n}")
    print("\nshape hints (reported, never used to exclude)")
    for k, v in Counter(r["shape_hint"] for r in rows
                        if r["engagement"] not in QUARANTINED).most_common():
        print(f"  {v:3d}  {k}")

    print("\nusable positives by language")
    for k, v in Counter(r["language"] for r in pos).most_common():
        print(f"  {k:12s} {v}")

    print("\nverdict on runnability")
    if len(neg) < 5:
        print(f"  BLOCKED: {len(neg)} adjudicated negative(s). The plan states a confirm-only")
        print("  corpus cannot measure a false positive, so CONTRADICTION RATE is uncomputable.")
    if len(pos) < 20:
        print(f"  BLOCKED: {len(pos)} positives. MISS RATE on this n cannot separate the plan's own")
        print("  decision bands (under 20% / 20-50% / over 50%) -- one case moves the rate by "
              f"{100/max(len(pos),1):.0f} points.")
    if len(pos) >= 20 and len(neg) >= 5:
        print("  RUNNABLE.")
    print("\n  No outcome here is a failure. The plan fixed that in advance, and a measured")
    print("  'not yet' costs one command instead of a month of engine integration.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
