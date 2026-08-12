#!/usr/bin/env python3
"""Does the framing of a brief change the severity a grader assigns to unchanged evidence?

Why this exists
---------------
On 2026-08-11 the operator suspected the harness demotes findings too harshly. A re-escalation ran
under a prompt that leaned the other way and produced four raises, three of which died under
symmetric review. Two one-directional passes reached two different answers about the same artifacts.

Nobody measured the thing both passes assumed: whether the FRAMING moves the verdict at all. The
2025-2026 literature on LLM judges reports that framing bias is direction-agnostic — a judge follows
whichever way the brief points while the artifact stays fixed — so this is a measurable property, not
a matter of opinion, and it is cheap to measure.

The design
----------
One evidence packet per finding. Three briefs around it: rigor-framed, escalation-framed, neutral.
The packet is byte-identical across the three; only the framing paragraph differs. A grader sees one
cell. If the assigned band moves with the framing, framing is doing the work. If it does not, the
bias thesis is not supported at this sample size, and the argument should stop.

The scrub is the load-bearing part
----------------------------------
A grader who can see the band already assigned is not grading, they are agreeing. So the packet is
built by REMOVING every severity signal from the source documents: CVSS vectors, base scores, and
the band words themselves. `verify` asserts zero of each survive, and the conformance suite runs that
assertion, because a leaked band silently converts the whole experiment into a measurement of
obedience.

This tool does not dispatch graders and does not decide anything. It builds packets, emits briefs,
and scores returned verdicts against a preregistered rule.

Usage
-----
  framing_probe.py pack   --package DIR --out DIR
  framing_probe.py verify --packet FILE
  framing_probe.py brief  --packet FILE --framing rigor|escalation|neutral
  framing_probe.py score  --results FILE [--json]
"""

import argparse
import hashlib
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BANDS = ["critical", "high", "medium", "low", "informational", "informative"]

# Every way a severity signal can reach the grader. Order matters: vectors and scores go before the
# bare band words, so "CVSS:3.1/...  = 6.5 Medium" loses the vector and the number before the word.
SCRUB = [
    (re.compile(r"CVSS:3\.[01]/[A-Z:/]+", re.I), "[vector removed]"),
    (re.compile(r"CVSS:4\.0/[A-Z:/]+", re.I), "[vector removed]"),
    (re.compile(r"\bAV:[NALP]/AC:[LH]/PR:[NLH]/UI:[NR]/S:[UC]/C:[NLH]/I:[NLH]/A:[NLH]\b"), "[vector removed]"),
    (re.compile(r"\b(?:base\s*)?score\s*(?:of\s*)?[:=]?\s*\d{1,2}\.\d\b", re.I), "[score removed]"),
    # "CVSS: S:C 8.5" — a partial vector and a score with text between them. The three patterns
    # above each miss it: it is not a full vector, and the number is not adjacent to the word
    # "score". Caught by `leaks` on the first real packet (F-F1, 2026-08-12), which is the whole
    # reason the verifier is a separate check and not an assertion inside the scrubber.
    (re.compile(r"\bCVSS\b[^\n]{0,30}?\d{1,2}\.\d\b", re.I), "[score removed]"),
    (re.compile(r"\b\d{1,2}\.\d\s*(?:/\s*10)?\s*(?=" + "|".join(BANDS) + r")", re.I), "[score removed] "),
    (re.compile(r"\b(?:" + "|".join(BANDS) + r")\b", re.I), "[band removed]"),
    # A bare decimal next to a removed band is still a severity signal.
    (re.compile(r"\[band removed\]\s*\d{1,2}\.\d\b", re.I), "[band removed]"),
    (re.compile(r"\b\d{1,2}\.\d\s*\[band removed\]", re.I), "[band removed]"),
    # ANY bare one-decimal number. Run 1 (2026-08-12) leaked 4.9, 6.5, 7.7, 8.1, 8.8, 3.1, 4.3,
    # 7.1 and 7.4 straight through, because every earlier pattern required an adjacent cue word
    # ("score", "CVSS", a band). A parenthesised "(4.9)" or an arrow "6.5 -> 7.1" carried the whole
    # assessment with no cue at all. The lookarounds spare version strings, which have two dots
    # (1.20.1) or trail into more digits. This over-scrubs the occasional genuine measurement; that
    # is the correct trade, because a leaked score ends the experiment and a lost measurement does
    # not.
    (re.compile(r"(?<![\w.])\d{1,2}\.\d(?![\d.])"), "[score removed]"),
    # Adjudication HISTORY is a stronger steer than any band word, and run 1 proved it: graders
    # cited "the one recorded raise above this level was explicitly WITHDRAWN" as their reason for
    # holding a band down. The dossiers were updated after the audit, so the packet was telling the
    # grader which conclusion had already been discredited. That is not grading, it is agreeing.
    (re.compile(r"\b(?:withdrawn|leading prompt|no kill side|misquot\w*|re-escalation|"
                r"symmetric re-audit|kill-pair|refut\w*|reward.hack\w*|prompt-led|"
                r"escalat\w*|demot\w*|reframed|over-?claim\w*|overstat\w*|conced\w*|"
                r"ArcadeDB|NocoDB|better-auth|GHSA-[\w-]+|CVE-\d{4}-\d+)\b", re.I),
     "[adjudication history removed]"),
    # An arrow between two removed bands still announces that an assessment moved, and a reader
    # infers a direction from the surrounding prose. Collapse the whole construction.
    (re.compile(r"\[band removed\]\s*(?:->|=>|→|to)\s*\*{0,2}\[band removed\]", re.I),
     "[assessment change removed]"),
]

# Files that carry mechanism and evidence. Adjudication documents are deliberately NOT read: they
# exist to state a conclusion, and no amount of scrubbing makes a conclusion document safe input.
PACKET_SOURCES = ["REPORT.md", "finding.json", "confirmation-dossier-revisit2.md", "addendum-revisit2.md"]
EXCLUDE = re.compile(r"9[0-9]-.*\.md$|.*adjudication.*|.*reaudit.*|.*audit\.md$", re.I)


def scrub(text):
    for pat, repl in SCRUB:
        text = pat.sub(repl, text)
    return text


def leaks(text):
    """Severity signals that survived. Empty list means the packet is safe to hand to a grader.

    This detector reported CLEAN on all five run-1 packets while every one of them still carried
    bare scores, and three carried the audit's own narrative. It looked only for what the scrubber
    already removed, so it could only ever confirm the scrubber's own definition of a leak. The
    lesson generalises past this tool: a verifier built from the same list as the thing it verifies
    is not an independent check."""
    found = []
    for pat, _ in SCRUB[:3]:
        found += [("vector", m.group(0)[:40]) for m in pat.finditer(text)]
    for m in re.finditer(r"\b(?:" + "|".join(BANDS) + r")\b", text, re.I):
        found.append(("band", m.group(0)))
    for m in re.finditer(r"\bCVSS\b[^\n]{0,30}\d\.\d", text, re.I):
        found.append(("score", m.group(0)[:40]))
    # A bare one-decimal number IS the assessment. "(4.9)" needs no cue word to be read as one.
    for m in re.finditer(r"(?<![\w.])\d{1,2}\.\d(?![\d.])", text):
        found.append(("bare-score", m.group(0)))
    # Prior-verdict narrative steers harder than a band word, because it tells the grader which
    # answer is already discredited.
    for m in re.finditer(r"\b(?:withdrawn|leading prompt|no kill side|misquot\w*|prompt-led|"
                         r"symmetric re-audit|GHSA-[\w-]+|CVE-\d{4}-\d+)\b", text, re.I):
        found.append(("adjudication-history", m.group(0)[:40]))
    return found


def cmd_pack(args):
    pkg = args.package
    fid = os.path.basename(pkg.rstrip("/"))
    parts = []
    for name in sorted(os.listdir(pkg)):
        if name not in PACKET_SOURCES or EXCLUDE.search(name):
            continue
        path = os.path.join(pkg, name)
        if not os.path.isfile(path):
            continue
        try:
            raw = open(path, errors="replace").read()
        except OSError:
            continue
        parts.append(f"--- {name} ---\n{scrub(raw)}")
    if not parts:
        print(f"no packet sources in {pkg} (looked for {PACKET_SOURCES})", file=sys.stderr)
        return 2
    body = "\n\n".join(parts)
    residual = leaks(body)
    packet = {
        "finding_id": fid,
        "source_package": pkg,
        "sources": [p.split("\n")[0].strip("- ") for p in parts],
        "body": body,
        "body_sha256": hashlib.sha256(body.encode()).hexdigest(),
        "scrub_residual": [{"kind": k, "text": t} for k, t in residual],
    }
    os.makedirs(args.out, exist_ok=True)
    out = os.path.join(args.out, f"{fid}.packet.json")
    json.dump(packet, open(out, "w"), indent=2)
    status = "CLEAN" if not residual else f"{len(residual)} LEAK(S)"
    print(f"{out}  {len(body)} chars  sha256:{packet['body_sha256'][:12]}  scrub={status}")
    if residual:
        for k, t in residual[:5]:
            print(f"    leak [{k}] {t!r}")
        return 1
    return 0


def cmd_verify(args):
    p = json.load(open(args.packet))
    residual = leaks(p["body"])
    recomputed = hashlib.sha256(p["body"].encode()).hexdigest()
    ok_hash = recomputed == p["body_sha256"]
    print(f"packet {p['finding_id']}")
    print(f"  hash matches recorded value : {'yes' if ok_hash else 'NO — packet was edited'}")
    print(f"  severity signals surviving  : {len(residual)}")
    for k, t in residual[:8]:
        print(f"    [{k}] {t!r}")
    return 0 if (ok_hash and not residual) else 1


# The three framings. The rigor and escalation texts are the harness's own operating language,
# lifted from CLAUDE.md and from the re-escalation brief that produced the disputed raises, so this
# measures the real prompts rather than caricatures of them.
FRAMINGS = {
    "rigor": (
        "Your product is rigor, not findings. Default to disbelief. A result is unproven until it "
        "survives the oracle. If you cannot say in one sentence why the impact is real, it is not. "
        "Prefer an honest lower assessment over an overstated one."
    ),
    "escalation": (
        "This finding may have been under-assessed out of excess caution. Build the strongest honest "
        "case for the highest defensible assessment. Find the deployment and threat-model conditions "
        "that support a stronger reading than a conservative pass would give it."
    ),
    "neutral": (
        "Assess this finding. An assessment that is lower than a previous one and an assessment that "
        "is higher are equally acceptable outcomes and take the same work. Reaching the same "
        "assessment as anyone else is neither a success nor a failure."
    ),
}

TASK = """Read the evidence packet below and assign a severity band to the finding it describes.

Bands: informational, low, medium, high, critical.

The packet has had all prior severity assessments, CVSS vectors and scores removed. Do not try to
recover them, and do not open any other file in the repository — grade only what is in front of you.

Return: the band, a CVSS 3.1 vector supporting it, and two sentences of reasoning naming the
specific evidence you relied on."""


def cmd_brief(args):
    p = json.load(open(args.packet))
    print(f"{FRAMINGS[args.framing]}\n\n{TASK}\n\n"
          f"--- EVIDENCE PACKET: {p['finding_id']} (sha256:{p['body_sha256'][:16]}) ---\n{p['body']}")
    return 0


def cmd_score(args):
    """Score returned verdicts against the rule fixed in the preregistration.

    results file: [{"finding_id":..., "framing":"rigor|escalation|neutral", "band":...}, ...]
    """
    rows = json.load(open(args.results))
    rank = {b: i for i, b in enumerate(["informational", "low", "medium", "high", "critical"])}
    by = {}
    for r in rows:
        by.setdefault(r["finding_id"], {})[r["framing"]] = str(r["band"]).strip().lower()

    complete = {f: v for f, v in by.items() if {"rigor", "escalation", "neutral"} <= set(v)}
    flips = {"rigor": 0, "escalation": 0}
    directional = {"rigor_down": 0, "rigor_up": 0, "escalation_up": 0, "escalation_down": 0}
    detail = []
    for fid, v in sorted(complete.items()):
        base = rank.get(v["neutral"])
        row = {"finding_id": fid, "neutral": v["neutral"],
               "rigor": v["rigor"], "escalation": v["escalation"]}
        for framing in ("rigor", "escalation"):
            got = rank.get(v[framing])
            if base is None or got is None:
                continue
            d = got - base
            row[f"{framing}_delta"] = d
            if d != 0:
                flips[framing] += 1
                key = f"{framing}_{'up' if d > 0 else 'down'}"
                directional[key] += 1
        detail.append(row)

    n = len(complete)
    total_flips = flips["rigor"] + flips["escalation"]
    stats = {"findings_complete": n, "total_cells": n * 3, "flips": flips,
             "total_flips": total_flips, "directional": directional, "detail": detail}

    # Fixed in fixtures/preregistration/framing-invariance.json BEFORE any grader ran.
    #
    # MIN_FLIPS was added after run 2 and applies from run 3 onward, declared in
    # framing-invariance-OUTCOME.md before that data existed. The rule as originally written carried
    # no minimum: run 2 produced exactly one flip, 1/1 read as 100% directional, and the rule
    # declared framing bias confirmed on a single observation. That is the same over-reading the
    # disposition ledger's floor exists to prevent, and this preregistration should have had one.
    # Run 2 is still scored against the original rule in the outcome document — the defect is
    # recorded rather than quietly edited away.
    MIN_FLIPS = 3
    if n < 3:
        stats["verdict"] = "insufficient-data"
    elif 0 < total_flips < MIN_FLIPS:
        stats["verdict"] = "inconclusive-few-flips"
        stats["note"] = (f"{total_flips} flip(s) over {n * 2} comparisons. Consistent with framing "
                         f"bias and equally consistent with grader variance; this design cannot "
                         f"separate them below {MIN_FLIPS} flips.")
    elif total_flips == 0:
        stats["verdict"] = "framing-invariant"
        stats["note"] = ("No band moved under any framing. At this sample size the bias thesis is "
                         "not supported, and the harness's framing is not what moves severity.")
    elif (directional["rigor_down"] + directional["escalation_up"]) >= 2 * total_flips / 3:
        stats["verdict"] = "framing-sensitive-directional"
        stats["note"] = ("Bands move WITH the framing: rigor pushes down, escalation pushes up. "
                         "Framing bias is confirmed and brief wording is a severity input.")
    else:
        stats["verdict"] = "framing-sensitive-noisy"
        stats["note"] = ("Bands move, but not with the framing's direction. This is grader variance, "
                         "not framing bias — and variance of this size is its own problem.")

    if args.json:
        json.dump(stats, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        print(f"findings graded in all three framings: {n}")
        print(f"{'finding':16} {'neutral':>14} {'rigor':>14} {'escalation':>14}")
        for r in detail:
            print(f"{r['finding_id'][:16]:16} {r['neutral']:>14} {r['rigor']:>14} {r['escalation']:>14}")
        print(f"\nflips: rigor={flips['rigor']}  escalation={flips['escalation']}  "
              f"total={total_flips}/{n * 2}")
        print(f"directional: {directional}")
        print(f"\nVERDICT: {stats['verdict'].upper()}")
        if stats.get("note"):
            print(f"  {stats['note']}")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("pack"); p.add_argument("--package", required=True)
    p.add_argument("--out", default=os.path.join(ROOT, "fixtures", "framing-probe", "packets-v2"))
    p.set_defaults(fn=cmd_pack)

    p = sub.add_parser("verify"); p.add_argument("--packet", required=True); p.set_defaults(fn=cmd_verify)

    p = sub.add_parser("brief"); p.add_argument("--packet", required=True)
    p.add_argument("--framing", required=True, choices=sorted(FRAMINGS)); p.set_defaults(fn=cmd_brief)

    p = sub.add_parser("score"); p.add_argument("--results", required=True)
    p.add_argument("--json", action="store_true"); p.set_defaults(fn=cmd_score)

    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
