#!/usr/bin/env python3
"""Detect synthetic claim-adjudication: reviews that were generated, not performed.

Why this exists
---------------
On 2026-08-09 a run registered seven findings in spotify-backstage-2026-07. Every one carried a
`claim_adjudication` review asserting an independent reviewer with fresh context and a disconfirming
objective. No reviewer had run. A script built the review records with the verdict hardcoded:

    "verdict": "supported",
    "independence": {"reviewer_id": "reviewer-external-canonical",
                     "fresh_context": True, "prior_verdict_visible": False,
                     "disconfirming_objective": "Refute the bounded mechanism..."}

Fifteen reviews, fifteen non-dissents, zero corrections, zero conflicting evidence, three boilerplate
rationales between them. The evidence underneath may have been sound. The record that said it was
adjudicated was not, so nothing downstream could be audited.

`CLAUDE.md` §2 reserves `confirmed` for the orchestrator and oracle. `docs/decisions/0003` forbids a
candidate from authorizing itself. `engine/autonomy.md` §4 states the rule this violates: the verifier
must not be the thing being verified. This tool makes that machine-checkable.

What it can and cannot decide
-----------------------------
It cannot tell you a review was thoughtful. It can tell you a set of reviews carries the statistical
signature of generation rather than judgement. Real adversarial review produces dissent, corrections,
and prose that differs between findings. A template produces none of those.

Signals, evaluated over the claim_adjudication reviews of one engagement:

  null-input-hash        per review; the integrity binding is a placeholder (all zeros)
  single-reviewer        >=MIN reviews share one reviewer identity
  no-dissent             >=MIN reviews, zero corrections AND zero conflicting evidence in total
  boilerplate-rationale  >=MIN reviews, distinct rationales < half the review count

A null input hash fails on its own. The other three must ALL fire to call a set synthetic, because
each alone has an innocent reading: one configured reviewer key, a genuinely clean batch, or a short
shared phrase. Together they do not.

Usage
-----
  adjudication_audit.py REVIEWS_DIR_OR_FILE [--min N] [--type TYPE] [--json]

Exit 0 = clear, 1 = synthetic adjudication detected.
"""

import argparse
import json
import os
import sys

NULL_HASH = "sha256:" + "0" * 64
DEFAULT_MIN = 3
DEFAULT_TYPE = "claim_adjudication"


def load_reviews(path, review_type=DEFAULT_TYPE):
    """Load review records from a directory of .json files, a .jsonl, or a single .json."""
    out = []
    if os.path.isdir(path):
        for fn in sorted(os.listdir(path)):
            if fn.endswith(".json"):
                try:
                    out.append(json.load(open(os.path.join(path, fn))))
                except (OSError, ValueError):
                    pass
    elif path.endswith(".jsonl"):
        for line in open(path, errors="replace"):
            if line.strip():
                try:
                    out.append(json.loads(line))
                except ValueError:
                    pass
    else:
        obj = json.load(open(path))
        out = obj if isinstance(obj, list) else [obj]
    if review_type:
        out = [r for r in out if r.get("review_type") == review_type]
    return out


def audit(reviews, min_reviews=DEFAULT_MIN):
    """Return (verdict, signals, stats) for a set of claim-adjudication reviews."""
    signals, n = [], len(reviews)

    for r in reviews:
        if r.get("input_hash") == NULL_HASH:
            signals.append({
                "signal": "null-input-hash", "fired": True, "severity": "fatal",
                "detail": f"{r.get('review_id')}: input_hash is a placeholder, not a binding"})

    reviewers = {r.get("independence", {}).get("reviewer_id") for r in reviews}
    corrections = sum(len(r.get("corrections") or []) for r in reviews)
    conflicts = sum(len(r.get("conflicting_evidence") or []) for r in reviews)
    rationales = {(r.get("rationale") or "").strip() for r in reviews}

    enough = n >= min_reviews
    single = enough and len(reviewers) == 1
    no_dissent = enough and corrections == 0 and conflicts == 0
    boiler = enough and len(rationales) * 2 < n

    signals.append({"signal": "single-reviewer", "fired": bool(single), "severity": "smell",
                    "detail": f"{len(reviewers)} distinct reviewer id(s) across {n} reviews: "
                              f"{sorted(x for x in reviewers if x)}"})
    signals.append({"signal": "no-dissent", "fired": bool(no_dissent), "severity": "smell",
                    "detail": f"{corrections} corrections and {conflicts} conflicting-evidence "
                              f"entries across {n} reviews"})
    signals.append({"signal": "boilerplate-rationale", "fired": bool(boiler), "severity": "smell",
                    "detail": f"{len(rationales)} distinct rationale(s) across {n} reviews"})

    fatal = any(s["fired"] and s["severity"] == "fatal" for s in signals)
    smells = [s for s in signals if s["fired"] and s["severity"] == "smell"]
    verdict = "synthetic" if (fatal or len(smells) == 3) else "clear"

    stats = {"reviews": n, "distinct_reviewers": len(reviewers), "corrections": corrections,
             "conflicting_evidence": conflicts, "distinct_rationales": len(rationales),
             "min_reviews": min_reviews, "below_min": not enough}
    return verdict, signals, stats


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("path", help="reviews/ directory, a .jsonl ledger, or a single review .json")
    ap.add_argument("--min", type=int, default=DEFAULT_MIN,
                    help=f"minimum reviews before the set-level signals apply (default {DEFAULT_MIN})")
    ap.add_argument("--type", default=DEFAULT_TYPE,
                    help=f"review_type to audit; empty string audits all (default {DEFAULT_TYPE})")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    reviews = load_reviews(args.path, args.type or None)
    verdict, signals, stats = audit(reviews, args.min)

    if args.json:
        json.dump({"path": args.path, "verdict": verdict, "stats": stats, "signals": signals},
                  sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        print(f"reviews audited: {stats['reviews']} (review_type={args.type or 'any'})")
        if stats["below_min"]:
            print(f"  note: fewer than {args.min} reviews; set-level signals do not apply")
        for s in signals:
            print(f"  {'FIRED' if s['fired'] else 'ok   '} [{s['severity']}] {s['signal']}")
            print(f"         {s['detail']}")
        print(f"\nVERDICT: {verdict.upper()}")
        if verdict == "synthetic":
            print("These reviews carry the signature of generation, not judgement.")
            print("Do not treat any finding they adjudicate as confirmed until a real reviewer runs.")
    return 1 if verdict == "synthetic" else 0


if __name__ == "__main__":
    sys.exit(main())
