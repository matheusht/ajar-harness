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
from pathlib import Path

from engagement_records import RecordError
from engagement_quarantine import read_safe_offline_file
from engagement_state import (
    _open_absolute_directory,
    _relative_regular_files,
    bound_engagement_source,
    find_engagement_root,
    read_governed_file,
)

NULL_HASH = "sha256:" + "0" * 64
DEFAULT_MIN = 3
DEFAULT_TYPE = "claim_adjudication"


def _load_review_bytes(files, review_type=DEFAULT_TYPE, *, strict_json=False):
    """Parse already-bound ``(relative_name, bytes)`` review candidates."""

    out = []
    for name, data in files:
        if name.endswith(".jsonl"):
            for line in data.decode("utf-8", errors="replace").splitlines():
                if line.strip():
                    try:
                        out.append(json.loads(line))
                    except ValueError:
                        pass
            continue
        try:
            obj = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            if strict_json:
                raise RecordError(
                    "review_source_invalid", "review source is invalid JSON"
                ) from exc
            continue
        out.extend(obj if isinstance(obj, list) else [obj])

    out = [r for r in out if isinstance(r, dict)]
    if review_type:
        out = [r for r in out if r.get("review_type") == review_type]
    # A recursive walk can meet the same review twice (a package copied into evidence/, a review
    # also appended to a ledger). Counting it twice would inflate n and weaken every set-level
    # signal, which is the wrong direction to be wrong in.
    seen, deduped = set(), []
    for r in out:
        key = r.get("review_id")
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        deduped.append(r)
    return deduped


def _load_bound_reviews(root: Path, relative: tuple[str, ...], review_type):
    regular_files = _relative_regular_files(root)
    target = Path(*relative).as_posix() if relative else ""
    if target in regular_files:
        return _load_review_bytes(
            [(target, read_governed_file(root / target))],
            review_type,
            strict_json=not target.endswith(".jsonl"),
        )

    directory = root / Path(*relative) if relative else root
    try:
        fd = _open_absolute_directory(directory)
    except OSError:
        # Preserve the old single-file failure for a path that is neither a directory nor a
        # regular source file.
        read_governed_file(root / target)
        raise AssertionError("unreachable")
    else:
        os.close(fd)

    prefix = target.rstrip("/") + "/" if target else ""
    candidates = []
    for name in sorted(regular_files):
        if not name.startswith(prefix) or not name.endswith(".json"):
            continue
        below = Path(name[len(prefix):])
        # Hidden dirs are scratch DB state (.kp-f3-data, .labdata-*), never review records.
        if any(part.startswith(".") for part in below.parts[:-1]):
            continue
        candidates.append((name, read_governed_file(root / name)))
    return _load_review_bytes(candidates, review_type)


def load_reviews(path, review_type=DEFAULT_TYPE):
    """Load review records from a directory tree, a .jsonl, or a single .json.

    Directories are walked RECURSIVELY. Version 1 used os.listdir, so pointing this at an engagement
    root found nothing and printed `VERDICT: CLEAR` over zero reviews — absence of input read as a
    pass. Real engagements keep reviews at `<engagement>/<unproven|findings>/<id>/reviews/*.json`,
    never at the root, so the corpus arm of G4 had never once executed on real data. Found
    2026-08-11 while measuring obyte-ocore-2026-08 against its preregistration.

    Callers that need "no reviews found" to be an error must check the returned length. This
    function reports what it finds; it does not decide what an empty set means."""
    source = Path(os.path.abspath(path))
    located = find_engagement_root(source)
    if located is not None:
        engagement, relative = located
        with bound_engagement_source(engagement) as bound:
            return _load_bound_reviews(bound, relative, review_type)

    # Portable fixture directories use the same inode-bound walker, without manufacturing a
    # record-kernel lock. Individual portable files use the offline file boundary helper.
    if source.is_dir():
        with bound_engagement_source(source, allow_ungoverned=True) as bound:
            return _load_bound_reviews(bound, (), review_type)
    try:
        data = read_safe_offline_file(source)
    except ValueError as exc:
        raise RecordError(
            "review_source_unavailable", "review source is governed or unavailable"
        ) from exc
    return _load_review_bytes(
        [(source.name, data)],
        review_type,
        strict_json=source.suffix != ".jsonl",
    )


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


def _count_entries(value):
    """Number of entries in a field that may be written as a list OR as one prose string.

    `len()` on a string counts characters. A real review carrying a 399-character
    conflicting_evidence paragraph scored 399 dissent entries, so the no-dissent smell could never
    fire on any engagement that wrote prose instead of a list. Wrong in the fail-open direction.
    Found 2026-08-11 auditing obyte-ocore-2026-08."""
    if not value:
        return 0
    if isinstance(value, str):
        return 1
    if isinstance(value, (list, tuple, set, dict)):
        return len(value)
    return 1


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
    corrections = sum(_count_entries(r.get("corrections")) for r in reviews)
    conflicts = sum(_count_entries(r.get("conflicting_evidence")) for r in reviews)
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

    # A corpus that only REJECTS is not manufacturing findings — but that does NOT make it judged.
    #
    # Fabrication inflates: the spotify generator wrote `supported` fifteen times. The opposite shape
    # — every verdict a rejection — is also what an operator produces when they batch-annotate bad
    # reviews by hand, and the two are structurally identical: one reviewer, one instant, one
    # template, one verdict. gemini-cli fired four signals including a fatal one for exactly that
    # innocent reason.
    #
    # The first version of this rule zeroed every signal and returned `clear`. That was wrong, and
    # wrong in a way that matters: an all-rejecting corpus IS the shape of findings killed without
    # real review, which is the exact failure mode a harness accused of over-killing needs to be
    # able to see. A reviewer demonstrated it the same day — a corpus firing all seven signals,
    # placeholder hashes and identical timestamps included, returned CLEAR purely because its
    # verdicts rejected.
    #
    # So the verdict now splits the two questions the old one conflated:
    #   synthetic             — generated CONFIRMATIONS. Blocks promotion (G4).
    #   rejections-unreviewed — generated or batch-annotated REJECTIONS. Does not block a promotion,
    #                           because nothing is being promoted on the strength of a rejection.
    #                           It is not a fraud accusation; it is the true statement that this set
    #                           of kills carries no sign of independent judgement. Feeds a demotion
    #                           audit, which is the thing that catches over-killing.
    rejecting = {"non_compliant", "noncompliant", "refuted", "rejected", "unsupported",
                 "not_supported", "quarantined", "withdrawn", "invalid", "demoted"}
    verdict_words = {str(v).strip().lower() for v in verdicts if v}
    all_rejecting = bool(verdict_words) and verdict_words <= rejecting
    if all_rejecting and (fatal or len(smells) >= 3):
        signals.append({
            "signal": "all-verdicts-rejecting", "fired": True, "severity": "smell",
            "detail": f"every verdict is a rejection ({', '.join(sorted(verdict_words))}) — these "
                      f"kills carry no sign of independent judgement. This does not block a "
                      f"promotion, but a batch of unreviewed rejections is how a real finding "
                      f"disappears quietly; audit them before trusting the kills"})
    # Majority of five. The original rule was all-of-three; five signals with a 3/5 bar keeps the
    # "each is innocent alone" principle while removing the single-signal escape hatch that let a
    # generator satisfy the detector by varying exactly the fields it checked.
    if fatal or len(smells) >= 3:
        verdict = "rejections-unreviewed" if all_rejecting else "synthetic"
    else:
        verdict = "clear"

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

    try:
        reviews = load_reviews(args.path, args.type or None)
    except (RecordError, OSError) as exc:
        verdict = "quarantined" if isinstance(exc, RecordError) and exc.code == "engagement_quarantined" else "source-unavailable"
        if args.json:
            json.dump({"verdict": verdict, "stats": {"reviews": 0}, "signals": []}, sys.stdout)
            sys.stdout.write("\n")
        else:
            print("engagement evidence is quarantined" if verdict == "quarantined" else "review source is unavailable")
        return 1
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
        elif verdict == "rejections-unreviewed":
            print("Every verdict here is a rejection, and the set shows no sign of independent")
            print("judgement. Nothing promotes on a rejection, so this blocks no finding — but a")
            print("batch of unreviewed kills is how a real finding disappears quietly. Audit them.")
    return 1 if verdict == "synthetic" else 0


if __name__ == "__main__":
    sys.exit(main())
