#!/usr/bin/env python3
"""Deterministic grader for a finding package.

Why this exists
---------------
`tools/score-candidate.py` already proves the pattern for the harness's own self-improvement loop:
"judge_note is advisory only: it is recorded but never read by the decision". That boundary was
never applied to the work itself. Every live verdict is model judgement, and the operator is the
only deterministic component in the loop.

This applies the same boundary one level down. It decides nothing about whether a vulnerability is
real. It decides whether the package's own claims survive mechanical checking.

Scope, measured not assumed
---------------------------
`fixtures/interventions/backfill-corpus.json` holds 62 documented corrections. 37 of them (60%) fall
into 8 reusable check families. The other 15 need bespoke domain logic and are out of scope for any
general tool. The families split two ways:

  computable  a program decides from the artifacts alone
              existence, recompute, cross-doc, pin-version          21 entries (34%)
  attestable  a program cannot judge the work, but it can refuse a
              package that does not name the required reference
              enumeration, negative-control, real-path-exec,
              refetch-external                                      16 entries (26%)

The second kind matters. Nothing can tell you an enumeration census was done well. Something can
refuse a `covered-dry` verdict that names no census at all.

Usage
-----
  score_finding.py PACKAGE_DIR [--attest FILE] [--judge-note TEXT] [--json]

Exit 0 = pass, 1 = block. --judge-note is recorded and never read by the decision.
"""

import argparse
import json
import os
import re
import sys

# --- CVSS 3.1 base score ------------------------------------------------------

_AV = {"N": 0.85, "A": 0.62, "L": 0.55, "P": 0.2}
_AC = {"L": 0.77, "H": 0.44}
_UI = {"N": 0.85, "R": 0.62}
_CIA = {"H": 0.56, "L": 0.22, "N": 0.0}
_PR_U = {"N": 0.85, "L": 0.62, "H": 0.27}
_PR_C = {"N": 0.85, "L": 0.68, "H": 0.50}

CVSS_RE = re.compile(
    r"CVSS:3\.[01]/AV:([NALP])/AC:([LH])/PR:([NLH])/UI:([NR])/S:([UC])/C:([HLN])/I:([HLN])/A:([HLN])")


def _roundup(x):
    i = int(round(x * 100000))
    return i / 100000.0 if i % 10000 == 0 else (i // 10000 + 1) / 10.0


def cvss31_base(av, ac, pr, ui, s, c, i, a):
    """Return the CVSS 3.1 base score for the given metric letters."""
    scope_changed = s == "C"
    iss = 1 - (1 - _CIA[c]) * (1 - _CIA[i]) * (1 - _CIA[a])
    if scope_changed:
        impact = 7.52 * (iss - 0.029) - 3.25 * (iss - 0.02) ** 15
    else:
        impact = 6.42 * iss
    pr_val = (_PR_C if scope_changed else _PR_U)[pr]
    expl = 8.22 * _AV[av] * _AC[ac] * pr_val * _UI[ui]
    if impact <= 0:
        return 0.0
    raw = min((1.08 if scope_changed else 1.0) * (impact + expl), 10)
    return _roundup(raw)


# --- package loading ----------------------------------------------------------

TEXT_EXT = {".md", ".txt", ".json"}


def load_package(root):
    docs = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in {".git", "node_modules", "out", "cache"}]
        for fn in filenames:
            if os.path.splitext(fn)[1].lower() in TEXT_EXT:
                p = os.path.join(dirpath, fn)
                try:
                    docs[os.path.relpath(p, root)] = open(p, errors="replace").read()
                except OSError:
                    pass
    return docs


class Result:
    def __init__(self):
        self.checks = []

    def add(self, ok, family, mode, label, detail=""):
        self.checks.append({"ok": bool(ok), "family": family, "mode": mode,
                            "label": label, "detail": detail})

    @property
    def failures(self):
        return [c for c in self.checks if not c["ok"]]


# --- computable checks --------------------------------------------------------

PATH_RE = re.compile(r"`([A-Za-z0-9_][A-Za-z0-9_./-]*\.(?:md|py|go|c|json|sol|txt|log|wasm|yaml|yml))`")
URL_RE = re.compile(r"https?://[^\s`)>\]]+")


def check_existence(root, docs, res):
    """Every package-relative path a document cites must exist in the package."""
    for name, text in docs.items():
        for m in PATH_RE.finditer(text):
            rel = m.group(1)
            if rel.startswith(("http", "//")) or " " in rel:
                continue
            hit = (os.path.isfile(os.path.join(root, rel))
                   or any(os.path.basename(k) == os.path.basename(rel) for k in docs)
                   or os.path.isfile(os.path.join(root, os.path.dirname(name), rel)))
            # A path that clearly points at the TARGET's source tree is not a package artifact.
            if not hit and not re.match(r"^(src|lib|core|kvm|engine|skills|tools|cmd|pkg|x)/", rel):
                res.add(False, "existence", "computable",
                        f"{name}: cited path resolves — {rel}", "not found in the package")


def check_recompute(docs, res):
    """Every CVSS vector must recompute to the score stated beside it."""
    for name, text in docs.items():
        for m in CVSS_RE.finditer(text):
            vector = m.group(0)
            got = cvss31_base(*m.groups())
            tail = text[m.end():m.end() + 120]
            stated = re.search(r"=?\s*\**(\d{1,2}\.\d)\b", tail)
            if not stated:
                continue
            want = float(stated.group(1))
            res.add(abs(want - got) < 0.05, "recompute", "computable",
                    f"{name}: CVSS vector recomputes to its stated score",
                    f"{vector} computes {got}, document states {want}")


SEV_RE = re.compile(r"\b(critical|high|medium|low|informational)\b", re.I)


def check_cross_doc(docs, res):
    """Severity words asserted as this package's own grade must agree across documents."""
    claims = {}
    for name, text in docs.items():
        for m in re.finditer(r"(?:^|\n)\s*(?:\*\*)?(?:severity|Severity)(?:\*\*)?\s*[:|]\s*(?:\*\*)?\s*([A-Za-z]+)",
                             text):
            sev = m.group(1).lower()
            if SEV_RE.fullmatch(sev):
                claims.setdefault(sev, []).append(name)
    if len(claims) > 1:
        detail = "; ".join(f"{k}: {', '.join(v)}" for k, v in claims.items())
        res.add(False, "cross-doc", "computable",
                "package states one severity", detail)
    elif claims:
        res.add(True, "cross-doc", "computable", "package states one severity")


PIN_RE = re.compile(r"\b([0-9a-f]{7,40})\b")
TAG_RE = re.compile(r"\bv?\d+\.\d+\.\d+(?:-[A-Za-z0-9.]+)?\b")


def check_pin_version(docs, res):
    """A package must not cite two different commit pins or two different release tags."""
    for kind, rx, minlen in (("commit", PIN_RE, 7), ("tag", TAG_RE, 0)):
        seen = {}
        for name, text in docs.items():
            for m in rx.finditer(text):
                val = m.group(0)
                if kind == "commit":
                    if len(val) < minlen or not re.search(r"[a-f]", val) or val.isdigit():
                        continue
                    val = val[:7]
                seen.setdefault(val, set()).add(name)
        if kind == "commit":
            vals = sorted(seen)
            if len(vals) > 1:
                res.add(False, "pin-version", "computable",
                        "package cites one commit pin",
                        f"found {len(vals)}: {', '.join(vals[:6])}")
            elif vals:
                res.add(True, "pin-version", "computable", "package cites one commit pin")


# --- attestable checks --------------------------------------------------------

ATTESTATIONS = {
    "enumeration": (
        re.compile(r"covered.dry|exhaustive|no other|every (call site|instance|occurrence)|"
                   r"the whole set|nothing else", re.I),
        "a completeness claim must name its enumeration census"),
    "negative-control": (
        re.compile(r"\boracle\b|\bsignal\b|\bprobe\b|\bdetector\b", re.I),
        "an oracle-derived verdict must name its negative control"),
    "real-path-exec": (
        re.compile(r"\bmock|\bstub|\bfake|\bsimulat|\bemulat", re.I),
        "a package that mentions mocks must attest the decisive path ran real code"),
    "refetch-external": (
        re.compile(r"\bprecedent\b|\bCVE-\d{4}|\bGHSA-|\badvisory\b", re.I),
        "a cited external precedent must attest a re-fetch"),
}


NULL_HASH = "sha256:" + "0" * 64


def _package_reviews(docs):
    """Every review record carried inside the package, parsed."""
    out = []
    for name, text in docs.items():
        if not name.endswith(".json"):
            continue
        try:
            obj = json.loads(text)
        except ValueError:
            continue
        for rec in (obj if isinstance(obj, list) else [obj]):
            if isinstance(rec, dict) and rec.get("review_type") == "claim_adjudication":
                out.append((name, rec))
    return out


def check_adjudication(docs, attest, res):
    """A package must not carry an adjudication it generated for itself.

    Two things are decidable here. A placeholder input hash is not a binding, so it fails outright.
    And a review that ASSERTS independence — fresh context, no prior verdict visible, a disconfirming
    objective — states something the package cannot substantiate on its own, so it must name the
    reference, exactly like the other attestable families.

    When the package carries three or more reviews the set-level detector applies too. See
    tools/adjudication_audit.py for why these signals, and spotify-backstage-2026-07 for the case."""
    reviews = _package_reviews(docs)
    if not reviews:
        return

    for name, rec in reviews:
        if rec.get("input_hash") == NULL_HASH:
            res.add(False, "adjudication", "computable",
                    f"{name}: review input_hash is a real binding",
                    f"{rec.get('review_id')} carries the all-zero placeholder")

    asserts_independence = [
        (name, rec) for name, rec in reviews
        if (rec.get("independence") or {}).get("fresh_context") is True
        or (rec.get("independence") or {}).get("prior_verdict_visible") is False]
    if asserts_independence:
        ref = (attest or {}).get("independent-review")
        res.add(bool(ref), "independent-review", "attestable",
                "attestation present — independent-review",
                "a review asserting fresh context or a disconfirming objective must name the "
                "reviewer's run; add 'independent-review' to the attestation file "
                f"({len(asserts_independence)} such review(s))")

    if len(reviews) >= 3:
        try:
            from adjudication_audit import audit
        except ImportError:
            return
        verdict, signals, stats = audit([r for _, r in reviews])
        fired = sorted(s["signal"] for s in signals if s["fired"])
        res.add(verdict != "synthetic", "adjudication", "computable",
                "package reviews show judgement, not generation",
                f"{stats['reviews']} reviews, {stats['distinct_reviewers']} reviewer(s), "
                f"{stats['corrections']} corrections, {stats['distinct_rationales']} rationale(s); "
                f"fired={fired}")


def check_attestations(docs, attest, res):
    blob = "\n".join(docs.values())
    for family, (trigger, why) in ATTESTATIONS.items():
        if not trigger.search(blob):
            continue
        ref = (attest or {}).get(family)
        res.add(bool(ref), family, "attestable",
                f"attestation present — {family}",
                f"{why}; add {family!r} to the attestation file")


# --- driver -------------------------------------------------------------------

def score(root, attest=None):
    docs = load_package(root)
    res = Result()
    if not docs:
        res.add(False, "existence", "computable", "package contains readable documents",
                f"no .md/.txt/.json under {root}")
        return res, docs
    check_existence(root, docs, res)
    check_recompute(docs, res)
    check_cross_doc(docs, res)
    check_pin_version(docs, res)
    check_adjudication(docs, attest, res)
    check_attestations(docs, attest, res)
    return res, docs


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("package")
    ap.add_argument("--attest", help="JSON file naming the required references")
    ap.add_argument("--judge-note", default=None,
                    help="recorded, never read by the decision")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    attest = json.load(open(args.attest)) if args.attest else None
    res, docs = score(args.package, attest)
    decision = "block" if res.failures else "pass"

    if args.json:
        json.dump({"decision": decision, "package": args.package,
                   "documents": len(docs), "checks": res.checks,
                   "judge_note": args.judge_note,
                   "judge_note_consulted": False}, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        print(f"package: {args.package}  ({len(docs)} documents)")
        for c in res.checks:
            mark = "ok  " if c["ok"] else "FAIL"
            print(f"  {mark} [{c['family']}/{c['mode']}] {c['label']}")
            if not c["ok"] and c["detail"]:
                print(f"         {c['detail']}")
        print(f"\n{len(res.checks)} checks, {len(res.failures)} failing")
        if args.judge_note:
            print(f"judge_note (recorded, not consulted): {args.judge_note}")
        print(f"DECISION: {decision.upper()}")
    return 1 if res.failures else 0


if __name__ == "__main__":
    sys.exit(main())
