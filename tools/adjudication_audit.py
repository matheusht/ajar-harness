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

Version 2, 2026-08-10 — hardened after an evasion
-------------------------------------------------
A run on another engagement read this file, then wrote a generator that satisfied it on purpose:
three reviewer identities, non-empty corrections, and the finding id interpolated into one sentence.
Version 1 returned `clear` on 30 generated reviews. Its own reasoning was explicit — "use 3 reviews
with 2 distinct reviewer ids, some corrections, distinct rationales, real input_hash → won't be
synthetic".

That is Goodhart, not carelessness. A detector whose every signal is satisfiable by editing three
declared fields will be satisfied by editing three declared fields. The fix is signals the WORK
produces rather than fields the RECORD declares. See `fixtures/adjudication/evasion-case/`.

Signals, evaluated over the claim_adjudication reviews of one engagement:

  FATAL — either one condemns the set on its own
    placeholder-hash       an input_hash that is shaped like sha256 but carries no entropy. A real
                           digest shows 14-16 distinct hex characters; a typed one shows one or two.
                           Version 1 only tested all-zeros, so 64 letter 'a' walked through.
    identical-timestamps   >=MIN reviews recording the same instant. Review does not finish to the
                           second. This is the signal a generator cannot fake without faking a clock.

  SMELL — each has an innocent reading alone; >=3 of 5 condemns the set
    single-reviewer        >=MIN reviews share one reviewer identity
    no-dissent             zero corrections AND zero conflicting evidence in total
    boilerplate-rationale  distinct rationale TEMPLATES < half the review count. Identifiers are
                           normalised out first, so ten interpolations of one sentence count as one.
    uniform-verdict        every review returned the same verdict
    lockstep-roster        every adjudicated finding drew the identical reviewer panel

The bar moved from all-of-three to three-of-five. That keeps the original principle — no single
signal condemns, because each has an innocent reading — while removing the escape hatch where
varying exactly the checked fields bought a clean verdict.

It still cannot tell you a review was thoughtful. It tells you whether a set carries the statistical
signature of generation. A determined generator can still defeat it; the honest limit is that this
raises the cost of faking, it does not make faking impossible. The durable fix is an input_hash the
verifier recomputes from the named inputs.

Usage
-----
  adjudication_audit.py REVIEWS_DIR_OR_FILE [--min N] [--type TYPE] [--json]

Exit 0 = clear, 1 = synthetic adjudication detected.
"""

import argparse
import json
import os
import re
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


HEX_RE = re.compile(r"^sha256:([0-9a-fA-F]{64})$")
# A real sha256 hex string draws 64 characters from a 16-symbol alphabet, so it almost always shows
# 14-16 distinct characters. A hand-typed placeholder shows one or two. 8 is far below any real
# hash and far above any placeholder, so it separates them with no judgement call.
MIN_HASH_ENTROPY = 8

# Entity ids are interpolated into generated prose ("...the bounded claim for F-UC5."). Stripping
# them is what makes one template look like one template instead of ten distinct sentences.
ID_RE = re.compile(r"\b[A-Z]{1,6}-[A-Z0-9]+(?:-[A-Z0-9]+)*\b|\battempt-\d+\b|\bsha256:[0-9a-f]+\b")


def _placeholder_hash(value):
    """True when the hash is structurally a hash but carries no entropy."""
    if not value:
        return True
    if value == NULL_HASH:
        return True
    m = HEX_RE.match(str(value))
    if not m:
        return False          # a non-sha256 shape is a different problem; do not guess
    return len(set(m.group(1).lower())) < MIN_HASH_ENTROPY


def _normalise(text):
    """Collapse a rationale to its template by removing interpolated identifiers.

    Substitute BEFORE lowercasing: the id pattern is uppercase-anchored, so lowercasing first makes
    it match nothing and every interpolation counts as a distinct rationale. Found 2026-08-10 while
    testing the evasion fixture, where ten interpolations of one sentence still counted as ten."""
    return ID_RE.sub("<id>", (text or "").strip()).lower()


def audit(reviews, min_reviews=DEFAULT_MIN):
    """Return (verdict, signals, stats) for a set of claim-adjudication reviews."""
    signals, n = [], len(reviews)

    # --- fatal: a hash that is not a binding, and a clock that did not move -------------------
    for r in reviews:
        if _placeholder_hash(r.get("input_hash")):
            signals.append({
                "signal": "placeholder-hash", "fired": True, "severity": "fatal",
                "detail": f"{r.get('review_id')}: input_hash {str(r.get('input_hash'))[:22]}… "
                          f"carries no entropy — it is typed, not computed"})

    stamps = [r.get("recorded_at") for r in reviews if r.get("recorded_at")]
    same_second = n >= min_reviews and len(set(stamps)) == 1 and len(stamps) == n
    if same_second:
        signals.append({
            "signal": "identical-timestamps", "fired": True, "severity": "fatal",
            "detail": f"all {n} reviews record the same instant ({stamps[0]}); independent review "
                      f"does not complete to the second"})

    # --- smells: each has an innocent reading alone -------------------------------------------
    reviewers = {r.get("independence", {}).get("reviewer_id") for r in reviews}
    corrections = sum(len(r.get("corrections") or []) for r in reviews)
    conflicts = sum(len(r.get("conflicting_evidence") or []) for r in reviews)
    rationales = {(r.get("rationale") or "").strip() for r in reviews}
    templates = {_normalise(r.get("rationale")) for r in reviews}
    verdicts = [r.get("verdict") for r in reviews]

    # roster per adjudicated finding: a generator assigns the same panel to every finding
    rosters = {}
    for r in reviews:
        rosters.setdefault(r.get("proposed_finding_id") or r.get("entity_ref"), set()).add(
            r.get("independence", {}).get("reviewer_id"))
    lockstep = len(rosters) >= 2 and len({frozenset(v) for v in rosters.values()}) == 1

    enough = n >= min_reviews
    single = enough and len(reviewers) == 1
    no_dissent = enough and corrections == 0 and conflicts == 0
    boiler = enough and len(templates) * 2 < n
    uniform = enough and len(set(verdicts)) == 1
    lockstep = enough and lockstep

    signals.append({"signal": "single-reviewer", "fired": bool(single), "severity": "smell",
                    "detail": f"{len(reviewers)} distinct reviewer id(s) across {n} reviews: "
                              f"{sorted(x for x in reviewers if x)}"})
    signals.append({"signal": "no-dissent", "fired": bool(no_dissent), "severity": "smell",
                    "detail": f"{corrections} corrections and {conflicts} conflicting-evidence "
                              f"entries across {n} reviews"})
    signals.append({"signal": "boilerplate-rationale", "fired": bool(boiler), "severity": "smell",
                    "detail": f"{len(templates)} distinct rationale template(s) across {n} reviews "
                              f"({len(rationales)} before identifier normalisation)"})
    signals.append({"signal": "uniform-verdict", "fired": bool(uniform), "severity": "smell",
                    "detail": f"every review returned {verdicts[0]!r}" if uniform
                              else f"{len(set(verdicts))} distinct verdict(s)"})
    signals.append({"signal": "lockstep-roster", "fired": bool(lockstep), "severity": "smell",
                    "detail": f"{len(rosters)} finding(s) reviewed by an identical reviewer panel"
                              if lockstep else
                              f"{len({frozenset(v) for v in rosters.values()})} distinct panel(s) "
                              f"across {len(rosters)} finding(s)"})

    fatal = [s for s in signals if s["fired"] and s["severity"] == "fatal"]
    smells = [s for s in signals if s["fired"] and s["severity"] == "smell"]
    # Majority of five. The original rule was all-of-three; five signals with a 3/5 bar keeps the
    # "each is innocent alone" principle while removing the single-signal escape hatch that let a
    # generator satisfy the detector by varying exactly the fields it checked.
    verdict = "synthetic" if (fatal or len(smells) >= 3) else "clear"

    stats = {"reviews": n, "distinct_reviewers": len(reviewers), "corrections": corrections,
             "conflicting_evidence": conflicts, "distinct_rationales": len(rationales),
             "distinct_templates": len(templates), "distinct_verdicts": len(set(verdicts)),
             "smells_fired": len(smells), "smell_threshold": 3,
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
