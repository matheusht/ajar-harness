#!/usr/bin/env python3
"""Findings start unproven. Promotion is an act that must pass gates.

Why this exists
---------------
Until now a finding was created directly in `findings/` and carried its own status field. The run
that produced the finding also set the field. On 2026-08-09 a script set `claim_state: supported` on
seven findings in spotify-backstage-2026-07 and nothing objected, because nothing had to.

That is a default-accept pipeline. Every check that does not run is a silent pass, so a broken
unattended run produces confident garbage and looks productive.

This inverts it. A finding is written to `unproven/`. It has no status. It has a LOCATION, and the
location changes only by running `promote`, which runs gates that can each say no. A broken
unattended run now produces nothing, which is visible and harmless.

Ownership (CLAUDE.md section 2)
-------------------------------
Hunters write into `unproven/` and may not move anything. Only the orchestrator runs `promote`.
`demote` is open to any role and needs only a reason: a wrong demote costs a re-review, a wrong
promote reaches a vendor, so the asymmetry matches the cost.

The gates
---------
  G0 existence      every path the package cites exists                    computable
  G1 real-path      a primary attempt is named AND real execution attested computable + attestable
  G2 control        a negative control attempt is named AND attested       computable + attestable
  G3 privilege      the proven execution context is no more privileged
                    than the claimed attacker position                     computable
  G4 adjudication   a review exists and is not synthetic                   computable
  G5 severity       a claimed severity carries a CVSS vector that
                    recomputes to its stated score                         computable

G3 is the gate this harness did not have. It cannot decide whether a proof really ran as a low
privilege user. It can decide that the package DECLARES both positions and that they agree. That
catches the failure ZSec documented: a named pipe that looked exploitable from SYSTEM and was
unreachable as a standard user.

Package layout
--------------
  unproven/<FINDING_ID>/
    finding.json      the finding record (v1 flat or v3 nested; both are read)
    attest.json       the attestations the attestable gates require
    REPORT.md         the writeup
    reviews/*.json    claim_adjudication reviews, if any

Usage
-----
  finding_lifecycle.py gates   PACKAGE_DIR [--json]
  finding_lifecycle.py promote PACKAGE_DIR --engagement DIR --actor ID [--json]
  finding_lifecycle.py demote  FINDING_ID  --engagement DIR --actor ID --reason TEXT
  finding_lifecycle.py status  --engagement DIR [--json]

Exit 0 = clear or moved, 1 = blocked.
"""

import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

UNPROVEN = "unproven"
PROVEN = "findings"
LOG = "lifecycle.jsonl"

# Privilege ladder. A proof may run at or BELOW the claimed position, never above.
# Proving from less privilege than claimed is a stronger result, so it passes.
PRIVILEGE_RANK = {
    "unauthenticated": 0, "anonymous": 0, "pre-auth": 0, "remote-unauthenticated": 0,
    "authenticated-user": 1, "low-privilege-user": 1, "standard-user": 1, "co-tenant": 1,
    "authenticated": 1, "user": 1,
    "privileged-user": 2, "admin": 2, "administrator": 2, "operator": 2,
    "system": 3, "root": 3, "kernel": 3, "superuser": 3,
}


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def load_json(path):
    try:
        return json.load(open(path))
    except (OSError, ValueError):
        return None


def dig(obj, *paths):
    """First present value among dotted paths."""
    for p in paths:
        cur = obj
        for part in p.split("."):
            if not isinstance(cur, dict) or part not in cur:
                cur = None
                break
            cur = cur[part]
        if cur not in (None, "", [], {}):
            return cur
    return None


class Gates:
    def __init__(self):
        self.rows = []

    def add(self, gate, ok, label, detail=""):
        self.rows.append({"gate": gate, "ok": bool(ok), "label": label, "detail": detail})

    @property
    def blocked(self):
        return [r for r in self.rows if not r["ok"]]


# --- the gates ----------------------------------------------------------------

def g0_existence(pkg, g):
    from score_finding import check_existence, load_package, Result
    docs = load_package(pkg)
    res = Result()
    if not docs:
        g.add("G0", False, "package has readable documents", f"no .md/.txt/.json under {pkg}")
        return
    check_existence(pkg, docs, res)
    bad = res.failures
    g.add("G0", not bad, "every cited path exists",
          "; ".join(c["detail"] or c["label"] for c in bad[:4]))


def g1_real_path(finding, attest, g):
    prim = dig(finding, "proof.primary_attempt_refs", "attempt_id")
    attested = bool((attest or {}).get("real-path-exec"))
    g.add("G1", bool(prim) and attested, "a primary attempt is named and real execution is attested",
          f"primary_attempt={'yes' if prim else 'MISSING'}, "
          f"real-path-exec attestation={'yes' if attested else 'MISSING'}")


def g2_control(finding, attest, g):
    neg = dig(finding, "proof.negative_control_refs", "control_attempt_id")
    attested = bool((attest or {}).get("negative-control"))
    g.add("G2", bool(neg) and attested, "a negative control is named and attested",
          f"control_attempt={'yes' if neg else 'MISSING'}, "
          f"negative-control attestation={'yes' if attested else 'MISSING'}")


def _rank(name):
    return PRIVILEGE_RANK.get(str(name).strip().lower().replace("_", "-"))


def g3_privilege(finding, attest, g):
    """The proof must not run at MORE privilege than the finding claims an attacker holds."""
    ctx = (dig(finding, "privilege_context", "proof.privilege_context", "claims.privilege_context")
           or (attest or {}).get("privilege_context") or {})
    claimed = ctx.get("claimed") if isinstance(ctx, dict) else None
    proven = ctx.get("proven") if isinstance(ctx, dict) else None
    if not claimed or not proven:
        g.add("G3", False, "claimed and proven privilege positions are both declared",
              f"claimed={claimed or 'MISSING'}, proven={proven or 'MISSING'}; "
              f"known positions: {', '.join(sorted(set(PRIVILEGE_RANK)))}")
        return
    rc, rp = _rank(claimed), _rank(proven)
    if rc is None or rp is None:
        unknown = [n for n, r in ((claimed, rc), (proven, rp)) if r is None]
        g.add("G3", False, "both privilege positions are recognised",
              f"unrecognised: {', '.join(map(str, unknown))}")
        return
    g.add("G3", rp <= rc, "the proof ran at or below the claimed attacker privilege",
          f"claimed {claimed} (rank {rc}), proven from {proven} (rank {rp}) — "
          f"a proof run at more privilege than the attacker holds does not establish reach")


def g4_adjudication(pkg, engagement, g):
    """The synthetic signature is a property of the review CORPUS, not of one review.

    A package usually carries the single review that adjudicated it, and one review can never show
    single-reviewer / no-dissent / boilerplate together. So this audits the package AND, when an
    engagement is given, the engagement's whole claim_adjudication set. If that corpus was generated,
    no finding resting on it may promote.

    Found 2026-08-10 by running the gates over the eleven spotify findings: G4 passed on all eleven
    while the engagement's 15-review corpus audited `synthetic`."""
    from adjudication_audit import audit, load_reviews
    rdir = os.path.join(pkg, "reviews")
    reviews = load_reviews(rdir) if os.path.isdir(rdir) else []
    if not reviews:
        g.add("G4", False, "an independent adjudication review exists",
              "no claim_adjudication review found under reviews/")
        return
    verdict, signals, stats = audit(reviews)
    fired = sorted(s["signal"] for s in signals if s["fired"])
    detail = (f"package: {stats['reviews']} review(s), {stats['distinct_reviewers']} reviewer(s), "
              f"{stats['corrections']} correction(s); fired={fired}")

    corpus_verdict = None
    if engagement:
        cdir = os.path.join(engagement, "reviews")
        corpus = load_reviews(cdir) if os.path.isdir(cdir) else []
        if corpus:
            corpus_verdict, csig, cstats = audit(corpus)
            cfired = sorted(s["signal"] for s in csig if s["fired"])
            detail += (f" | engagement corpus: {cstats['reviews']} review(s), "
                       f"{cstats['distinct_reviewers']} reviewer(s), "
                       f"{cstats['corrections']} correction(s); fired={cfired}")

    ok = verdict != "synthetic" and corpus_verdict != "synthetic"
    g.add("G4", ok, "the adjudication is judgement, not generation", detail)


SEV_WORDS = {"critical", "high", "medium", "low", "informational", "none"}


def g5_severity(pkg, finding, g):
    from score_finding import CVSS_RE, cvss31_base, load_package
    label = dig(finding, "classification.severity.label", "severity")
    if isinstance(label, dict):
        label = label.get("label")
    if not label or str(label).lower() not in SEV_WORDS:
        g.add("G5", True, "no severity claimed, so no vector required")
        return
    blob = "\n".join(load_package(pkg).values())
    vector = dig(finding, "classification.severity.vector") or ""
    hits = list(CVSS_RE.finditer(blob + "\n" + str(vector)))
    if not hits:
        g.add("G5", False, "a claimed severity carries a CVSS vector",
              f"severity {label!r} is claimed with no CVSS:3.x vector anywhere in the package")
        return
    for m in hits:
        got = cvss31_base(*m.groups())
        tail = (blob + "\n" + str(vector))[m.end():m.end() + 120]
        import re
        stated = re.search(r"=?\s*\**(\d{1,2}\.\d)\b", tail)
        if stated and abs(float(stated.group(1)) - got) >= 0.05:
            g.add("G5", False, "the CVSS vector recomputes to its stated score",
                  f"{m.group(0)} computes {got}, package states {stated.group(1)}")
            return
    g.add("G5", True, "a claimed severity carries a CVSS vector that recomputes")


def run_gates(pkg, engagement=None):
    g = Gates()
    finding = load_json(os.path.join(pkg, "finding.json")) or {}
    attest = load_json(os.path.join(pkg, "attest.json")) or {}
    g0_existence(pkg, g)
    g1_real_path(finding, attest, g)
    g2_control(finding, attest, g)
    g3_privilege(finding, attest, g)
    g4_adjudication(pkg, engagement, g)
    g5_severity(pkg, finding, g)
    return g, finding


# --- movement -----------------------------------------------------------------

def append_log(engagement, record):
    with open(os.path.join(engagement, LOG), "a") as fh:
        fh.write(json.dumps(record, sort_keys=True) + "\n")


def cmd_gates(args):
    g, _ = run_gates(args.package, getattr(args, "engagement", None))
    report(args, g, args.package, moved=None)
    return 1 if g.blocked else 0


def cmd_promote(args):
    pkg = os.path.abspath(args.package)
    fid = os.path.basename(pkg.rstrip("/"))
    g, _ = run_gates(pkg, args.engagement)
    dest = os.path.join(args.engagement, PROVEN, fid)
    moved = False
    if not g.blocked:
        os.makedirs(os.path.join(args.engagement, PROVEN), exist_ok=True)
        if os.path.exists(dest):
            g.add("move", False, "destination is free", f"{dest} already exists")
        else:
            shutil.move(pkg, dest)
            moved = True
    append_log(args.engagement, {
        "recorded_at": now(), "action": "promote", "finding_id": fid, "actor": args.actor,
        "result": "promoted" if moved else "blocked",
        "gates": [{"gate": r["gate"], "ok": r["ok"]} for r in g.rows],
        "blocked_by": [r["gate"] for r in g.blocked]})
    report(args, g, pkg, moved=moved, dest=dest if moved else None)
    return 0 if moved else 1


def cmd_demote(args):
    src = os.path.join(args.engagement, PROVEN, args.finding_id)
    dest = os.path.join(args.engagement, UNPROVEN, args.finding_id)
    if not os.path.isdir(src):
        print(f"not promoted: {src} does not exist")
        return 1
    os.makedirs(os.path.join(args.engagement, UNPROVEN), exist_ok=True)
    if os.path.exists(dest):
        print(f"cannot demote: {dest} already exists")
        return 1
    shutil.move(src, dest)
    append_log(args.engagement, {
        "recorded_at": now(), "action": "demote", "finding_id": args.finding_id,
        "actor": args.actor, "result": "demoted", "reason": args.reason})
    print(f"demoted {args.finding_id} -> {UNPROVEN}/")
    print(f"reason: {args.reason}")
    return 0


def cmd_status(args):
    rows = []
    for state in (UNPROVEN, PROVEN):
        d = os.path.join(args.engagement, state)
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            p = os.path.join(d, name)
            if os.path.isdir(p):
                rows.append({"finding_id": name, "state": state})
    if args.json:
        json.dump({"engagement": args.engagement, "findings": rows}, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        if not rows:
            print("no findings")
        for r in rows:
            mark = "PROVEN  " if r["state"] == PROVEN else "unproven"
            print(f"  {mark} {r['finding_id']}")
        print(f"\n{sum(1 for r in rows if r['state']==PROVEN)} proven, "
              f"{sum(1 for r in rows if r['state']==UNPROVEN)} unproven")
    return 0


def report(args, g, pkg, moved, dest=None):
    if getattr(args, "json", False):
        json.dump({"package": pkg, "decision": "blocked" if g.blocked else "clear",
                   "moved_to": dest, "gates": g.rows}, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return
    print(f"package: {pkg}")
    for r in g.rows:
        print(f"  {'ok  ' if r['ok'] else 'BLOCK'} [{r['gate']}] {r['label']}")
        if not r["ok"] and r["detail"]:
            print(f"           {r['detail']}")
    print(f"\n{len(g.rows)} gates, {len(g.blocked)} blocking")
    if moved:
        print(f"PROMOTED -> {dest}")
    elif moved is False:
        print("NOT PROMOTED — the finding stays unproven.")
    else:
        print("DECISION: " + ("BLOCKED" if g.blocked else "CLEAR"))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("gates", help="run the gates without moving anything")
    p.add_argument("package")
    p.add_argument("--engagement", default=None,
                   help="also audit this engagement's whole review corpus for G4")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_gates)

    p = sub.add_parser("promote", help="orchestrator only — run gates and move to findings/")
    p.add_argument("package")
    p.add_argument("--engagement", required=True)
    p.add_argument("--actor", required=True)
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_promote)

    p = sub.add_parser("demote", help="any role — move back to unproven/")
    p.add_argument("finding_id")
    p.add_argument("--engagement", required=True)
    p.add_argument("--actor", required=True)
    p.add_argument("--reason", required=True)
    p.set_defaults(fn=cmd_demote)

    p = sub.add_parser("status", help="list findings and where they sit")
    p.add_argument("--engagement", required=True)
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_status)

    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
