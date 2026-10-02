#!/usr/bin/env python3
"""Micro-inspiration fragmenter and a deterministic novelty mapper.

Two jobs, and the second is the load-bearing one.

Why
---
The harness has no ideation step. Stage 0 is "candidate sink-function narrowing", which filters a
space that already presumes the bug class is known, and card selection is deterministic-by-id
against a fixed corpus of 45 vuln cards. Everything it has found is an instance of a known class.

Kettle's method inverts that: fragment a primary source into 1-3 sentence units, generate 1-5
hypotheses per unit, and let a cheap evaluator sort them. He fed 138 RFCs, got 15,000 fragments and
30,000 vectors. His measured warning is that supplying even one inspiration example collapsed his
own rediscovery rate from 5% to 0% ("context-contamination"), so fragments stay small on purpose.

For a white-box source audit the analogue of an RFC is the host-to-contract interface: the hook
surface IS the protocol specification an attacker programs against.

The mapper is the part that makes the experiment answerable
-----------------------------------------------------------
Generating hypotheses is easy and needs a model. Deciding whether a hypothesis is NEW is the hard
part, and it is the same question Stage 5.25 (novelty) asks with one doctrine paragraph and no tool.

This mapper is deterministic on purpose. It scores a hypothesis against every existing card by token
overlap and reports the nearest match with its score. Above the threshold the hypothesis restates a
card the harness already has (rediscovery). Below it, the hypothesis is a NOVELTY CANDIDATE - not a
finding, not proof of novelty, only "no existing card covers this, so a human should look".

It cannot prove novelty. Nothing can: absence from 45 cards is not absence from the field. It can
cheaply remove the ~90% that are restatements, which is what makes a generated pile reviewable.

Usage
-----
  ideation.py fragment --source DIR [--limit N]
  ideation.py map --hypotheses FILE [--threshold F]
  ideation.py selftest
"""

import argparse
import json
import os
import re
import sys
from collections import Counter

from regular_file_io import read_regular_text

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

STOP = set("""a an the and or of to in for with on at by is are be as it its this that from
which when where what how any all not no if then than so such may can will would could should
must each other into over under via using use used than then there their they them we our you your
value values return returns given gives set sets get gets new old same different""".split())


def tokens(text):
    return {w for w in re.findall(r"[a-z][a-z0-9]{2,}", text.lower()) if w not in STOP}


# --- fragmenting --------------------------------------------------------------

HOOK_RE = re.compile(
    r"(?:^|\n)((?://[^\n]*\n)*)func \(context \*VMHooksImpl\) ([A-Za-z0-9_]+)\(([^)]*)\)")


def fragment_hooks(source_dir):
    """Each hook is one micro-inspiration unit: its name, signature and doc comment.

    Deliberately small. Kettle's finding is that extra context anchors the model onto the example
    and suppresses novelty, so a unit carries the interface and nothing else - no call sites, no
    prior findings, no card names."""
    out = []
    hooks_dir = os.path.join(source_dir, "kvm", "vmhost", "vmhooks")
    if not os.path.isdir(hooks_dir):
        return out
    for fn in sorted(os.listdir(hooks_dir)):
        if not fn.endswith(".go") or fn.endswith("_test.go"):
            continue
        text = read_regular_text(os.path.join(hooks_dir, fn), errors="replace")
        for m in HOOK_RE.finditer(text):
            doc = " ".join(l.strip("/ ").strip() for l in m.group(1).splitlines() if l.strip())
            out.append({
                "unit_id": f"{fn}:{m.group(2)}",
                "name": m.group(2),
                "signature": re.sub(r"\s+", " ", m.group(3)).strip(),
                "doc": doc[:300],
            })
    return out


# --- mapping ------------------------------------------------------------------

def load_cards():
    cards = []
    for family in ("vulns", "patterns", "techniques"):
        base = os.path.join(ROOT, "skills", family)
        if not os.path.isdir(base):
            continue
        for name in sorted(os.listdir(base)):
            p = os.path.join(base, name, "SKILL.md")
            if not os.path.isfile(p):
                continue
            text = open(p, errors="replace").read()
            fm = text.split("\n---", 2)[0] if text.startswith("---") else text[:2000]
            cards.append({"family": family, "dir": name,
                          "id": (re.search(r"^id:\s*(.+)$", fm, re.M) or [None, name])[1].strip(),
                          "tokens": tokens(fm)})
    return cards


def idf_table(cards):
    """Inverse document frequency across the card corpus.

    A plain overlap ratio over-scores short text: a sentence with nine tokens that accidentally
    shares three generic words with a card scores 0.33 and reads as a rediscovery. The selftest
    caught this by classifying a sentence about sourdough starter as a rediscovery. Weighting by
    rarity fixes it, because a token appearing in most cards carries no signal about which card."""
    n = len(cards) or 1
    df = Counter()
    for c in cards:
        df.update(c["tokens"])
    import math
    return {t: math.log(n / (1 + d)) + 0.01 for t, d in df.items()}, math.log(n / 1) + 0.01


def nearest(hyp_text, cards, idf=None, default_idf=None):
    """Rarity-weighted containment. Returns (card, score) for the best match.

    Score is the share of the hypothesis's DISCRIMINATIVE weight that a card already covers. A term
    the corpus has never seen contributes full weight and can never be "already covered", which is
    what lets a genuinely new idea score low."""
    ht = tokens(hyp_text)
    if not ht:
        return None, 0.0
    if idf is None:
        idf, default_idf = idf_table(cards)
    total = sum(idf.get(t, default_idf) for t in ht)
    if total <= 0:
        return None, 0.0
    best, best_score = None, 0.0
    for c in cards:
        if not c["tokens"]:
            continue
        shared = ht & c["tokens"]
        # An absolute floor as well as a ratio: one rare word in common is coincidence, not cover.
        if len(shared) < 2:
            continue
        score = sum(idf.get(t, default_idf) for t in shared) / total
        if score > best_score:
            best, best_score = c, score
    return best, round(best_score, 3)


# Calibrated 2026-08-09 against both extremes of the corpus:
#   unrelated prose (5 samples, unrelated domains) tops out at 0.195
#   a card's own token set scores 1.000 against itself
# 0.60 sits in that gap.
#
# MIDDLE RANGE CALIBRATED 2026-08-09 (the caveat below is now discharged). Five hypotheses written as
# analyst restatements of real cards scored 0.61 / 0.70 / 0.74 / 0.95 / 0.74 and all classified
# rediscovery; an unrelated control scored 0.10. The threshold separates them cleanly, so a
# 0-rediscovery result on real hypotheses means the corpus genuinely lacks a card, not that the bar
# is unreachable. Known residual: the nearest-card ATTRIBUTION can be wrong while the verdict is
# right (an object-ownership restatement matched a proof-verification card). Read the card as a hint,
# never as a citation.
#
# Superseded caveat, kept for the record: the upper point is an identity match, not a realistic
# restatement, so the middle of the range is UNCALIBRATED. Re-calibrate against real generated
# hypotheses before reading any rediscovery rate as a measurement.


def classify(score, threshold):
    if score >= threshold:
        return "rediscovery"
    if score >= threshold / 2:
        return "adjacent"
    return "novelty-candidate"


def cmd_fragment(args):
    units = fragment_hooks(args.source)
    if args.limit:
        units = units[:args.limit]
    json.dump({"source": args.source, "unit_kind": "vm-hook-interface",
               "count": len(units), "units": units}, sys.stdout, indent=2)
    sys.stdout.write("\n")
    print(f"\n{len(units)} micro-inspiration units", file=sys.stderr)
    return 0


def cmd_map(args):
    cards = load_cards()
    idf, dflt = idf_table(cards)
    doc = json.loads(read_regular_text(args.hypotheses))
    hyps = doc if isinstance(doc, list) else doc.get("hypotheses", [])
    rows, counts = [], Counter()
    unreadable = []
    for i, h in enumerate(hyps):
        text = h if isinstance(h, str) else f"{h.get('title','')} {h.get('text','')}"
        # Fail CLOSED on a schema we cannot read. Scoring unreadable text gives 0.00, which
        # classifies as novelty-candidate — the tool would silently manufacture novelty from a typo'd
        # field name. Found 2026-08-09 while testing a hypothesis file that used `statement`.
        if not tokens(text):
            unreadable.append(h.get("id", f"#{i}") if isinstance(h, dict) else f"#{i}")
            continue
        card, score = nearest(text, cards, idf, dflt)
        verdict = classify(score, args.threshold)
        counts[verdict] += 1
        rows.append({"hypothesis": text[:110], "verdict": verdict, "score": score,
                     "nearest_card": card["id"] if card else None})
    total = len(rows) or 1
    for r in rows:
        print(f"  {r['verdict']:18s} {r['score']:.2f}  {r['nearest_card'] or '-':38s} {r['hypothesis']}")
    print(f"\n{len(rows)} hypotheses against {len(cards)} cards (threshold {args.threshold})")
    for v, n in counts.most_common():
        print(f"  {n:4d}  {100.0*n/total:5.1f}%  {v}")
    print("\nnovelty-candidate means no existing card covers it. That is a review queue, not a")
    print("novelty claim: absence from this corpus is not absence from the field.")
    if unreadable:
        print(f"\nREFUSED {len(unreadable)} hypothesis/es with no readable text: "
              f"{', '.join(str(u) for u in unreadable[:8])}")
        print("Each hypothesis needs a 'title' and/or 'text' field. These were NOT scored — a "
              "hypothesis the mapper cannot read is not a novelty candidate.")
        return 1
    return 0


def cmd_selftest(args):
    """The mapper must call a card's own description a rediscovery, and unrelated text a candidate.

    Without this the threshold is a guess. A mapper that calls everything novel is as useless as one
    that calls everything known."""
    cards = load_cards()
    idf, dflt = idf_table(cards)
    if not cards:
        print("no cards found")
        return 1
    ok = True

    # 1. Each card's own front matter must map back to itself as a rediscovery.
    hits, selfmatch = 0, 0
    for c in cards:
        text = " ".join(sorted(c["tokens"]))
        best, score = nearest(text, cards, idf, dflt)
        if score >= args.threshold:
            hits += 1
        if best and best["id"] == c["id"]:
            selfmatch += 1
    print(f"  card text scores as rediscovery : {hits}/{len(cards)}")
    print(f"  nearest card is itself          : {selfmatch}/{len(cards)}")
    ok &= hits == len(cards) and selfmatch == len(cards)

    # 2. Text from a wholly unrelated domain must not map.
    unrelated = [
        "the sourdough starter must be fed twice daily with equal parts flour and water",
        "migratory geese navigate using the earth magnetic field during autumn",
        "concrete cures more slowly at low ambient temperature and retains moisture",
        "the violin bow is strung with horsehair and rosin is applied before playing",
        "tidal patterns follow the lunar cycle and vary with coastal shelf geometry",
    ]
    bad = 0
    for u in unrelated:
        _, score = nearest(u, cards, idf, dflt)
        v = classify(score, args.threshold)
        flag = "ok  " if v == "novelty-candidate" else "FAIL"
        bad += v != "novelty-candidate"
        print(f"  {flag} unrelated text -> {v} ({score})")
    ok &= bad == 0

    print(f"\nmapper selftest: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("fragment")
    p.add_argument("--source", required=True)
    p.add_argument("--limit", type=int, default=0)
    p.set_defaults(func=cmd_fragment)
    p = sub.add_parser("map")
    p.add_argument("--hypotheses", required=True)
    p.add_argument("--threshold", type=float, default=0.60)
    p.set_defaults(func=cmd_map)
    p = sub.add_parser("selftest")
    p.add_argument("--threshold", type=float, default=0.60)
    p.set_defaults(func=cmd_selftest)
    args = ap.parse_args()
    try:
        return args.func(args)
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
