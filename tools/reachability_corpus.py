#!/usr/bin/env python3
"""Phase 7 step 1 — build the reachability corpus, and report the denominator.

`docs/research/static-analysis-and-knowledge-base-plan.md` A.2 specifies the experiment: express
each adjudicated finding as a source-to-sink claim, run it through a dataflow engine, and compute
three numbers -- confirm rate, miss rate, contradiction rate.

Its own ground rule 1 is "measure before we build", and ground rule 4 is "report the denominator".
This does both, BEFORE anyone installs a multi-gigabyte engine. It answers: how many adjudicated
cases actually exist, in what language, and how many are even dataflow-shaped?

Three exclusions, each of which would otherwise inflate the corpus:

  QUARANTINED   a target-local marker makes the entire engagement inadmissible. The marker is
                checked dynamically and no command-line override can make its rows authoritative.
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
  python3 tools/reachability_corpus.py [--json]
"""

import argparse
import glob
import json
import os
import re
import stat
import sys
from pathlib import Path

from engagement_records import RecordError
from engagement_quarantine import is_quarantined
from engagement_state import (
    _relative_regular_files,
    bound_engagement_source,
    read_governed_file,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

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


def _bound_child_directories(root: Path, name: str) -> list[str]:
    parts = root.parts
    if not (len(parts) == 4 and parts[1:3] == ("dev", "fd") and parts[3].isdigit()):
        raise RecordError("bound_engagement_required", "scanner source is not bound")
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        directory_fd = os.open(name, flags, dir_fd=int(parts[3]))
    except FileNotFoundError:
        return []
    try:
        result = []
        for child_name in sorted(os.listdir(directory_fd)):
            try:
                child = os.stat(child_name, dir_fd=directory_fd, follow_symlinks=False)
            except OSError:
                continue
            if stat.S_ISDIR(child.st_mode) and not stat.S_ISLNK(child.st_mode):
                result.append(child_name)
        return result
    finally:
        os.close(directory_fd)


def scan(root=ROOT):
    rows = []
    for eng_dir in sorted(glob.glob(os.path.join(root, "engagements", "*/"))):
        engagement_path = Path(eng_dir)
        try:
            with bound_engagement_source(
                engagement_path, allow_ungoverned=True
            ) as bound:
                # Retained as an explicit hook for the quarantine race regression; the authoritative
                # checks in the context manager are also bound to this same directory inode.
                if is_quarantined(bound):
                    raise RecordError(
                        "engagement_quarantined", "engagement evidence is quarantined"
                    )
                engagement_rows = []
                regular_files = _relative_regular_files(bound)
                eng = engagement_path.name
                for verdict, sub in (("confirmed", "findings"), ("adjudicated-negative", "unproven")):
                    for name in _bound_child_directories(bound, sub):
                        if sub == "unproven" and not re.search(r"REFUT|DEMOT", name, re.I):
                            continue        # an open partial is not an adjudicated negative
                        prefix = f"{sub}/{name}/"
                        fj = prefix + "finding.json"
                        blob = ""
                        doc = {}
                        if fj in regular_files:
                            try:
                                doc = json.loads(read_governed_file(bound / fj).decode("utf-8"))
                                blob = json.dumps(doc).lower()
                            except Exception:
                                pass
                        if not blob:
                            for md in sorted(
                                value for value in regular_files
                                if value.startswith(prefix)
                                and len(Path(value[len(prefix):]).parts) == 1
                                and value.endswith(".md")
                            ):
                                blob += read_governed_file(bound / md).decode(
                                    "utf-8", errors="ignore"
                                ).lower()[:8000]
                        usable, why = True, None
                        src, snk = extract_tuple(doc)
                        if usable and not (src or snk):
                            usable, why = False, ("NO-TUPLE: the package records no source and no sink -- "
                                                  "schemas/finding.schema.json has no field for either")
                        engagement_rows.append({"engagement": eng, "package": name, "verdict": verdict,
                                                "language": classify_language(blob), "usable": usable,
                                                "excluded_because": why, "shape_hint": shape_hint(blob),
                                                "source": src, "sink": snk, "fields": sorted(doc)[:20]})
                if is_quarantined(bound):
                    raise RecordError(
                        "engagement_quarantined", "engagement evidence is quarantined"
                    )
            # Context exit is the admission point: it rechecks the public path identity and GQ.
            rows.extend(engagement_rows)
        except (RecordError, OSError):
            continue
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    rows = scan()

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
    for k, v in Counter(r["shape_hint"] for r in rows).most_common():
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
