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
  G6 state          the world state the proof depends on was REACHED
                    through the real path, not written directly            attestable

G3 is the gate this harness did not have. It cannot decide whether a proof really ran as a low
privilege user. It can decide that the package DECLARES both positions and that they agree. That
catches the failure ZSec documented: a named pipe that looked exploitable from SYSTEM and was
unreachable as a standard user.

G6 is the gate the obyte run bought. G3 asks WHO the attacker was; G6 asks whether the situation
they attacked can occur at all. obyte-2026-08-004 answered G3 honestly and still promoted a false
impact, because its PoC wrote itself into a state the real network cannot reach. Added 2026-08-11.

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

# Declared honestly when the proof does not start from an attacker position at all — a unit test
# that constructs the post-bypass state, a harness that begins mid-chain. It always blocks, but it
# blocks as a STATEMENT rather than as an omission, which is the difference between "we know this is
# missing" and "nobody looked".
NOT_ESTABLISHED = "not-established"


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
    if NOT_ESTABLISHED in (str(claimed).lower(), str(proven).lower()):
        g.add("G3", False, "the execution position is established",
              f"claimed={claimed}, proven={proven} — the proof does not start from an attacker "
              f"position (declared, not omitted); a PoC that constructs the post-bypass state "
              f"proves the consumer, not the reach")
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

    corpus_ok = True
    if engagement:
        # The engagement ROOT, walked recursively. Version 1 looked in `<engagement>/reviews/`, a
        # directory no engagement has ever had — obyte, spotify and adapta all keep reviews at
        # `<package>/reviews/`. So this arm silently found nothing and contributed nothing for the
        # whole of its existence. The fixture hid it: fixtures/lifecycle-corpus was built with a
        # top-level reviews/ dir, shaped to the code instead of to the world.
        corpus = load_reviews(engagement)
        if not corpus:
            # The package under test lives inside the engagement and carries at least one review
            # (checked above), so a recursive walk that finds none means the walk is broken. Fail
            # closed: an instrument that cannot see its input must not return a pass.
            corpus_ok = False
            detail += " | engagement corpus: NONE FOUND — corpus audit could not run"
        else:
            corpus_verdict, csig, cstats = audit(corpus)
            cfired = sorted(s["signal"] for s in csig if s["fired"])
            corpus_ok = corpus_verdict != "synthetic"
            detail += (f" | engagement corpus: {cstats['reviews']} review(s), "
                       f"{cstats['distinct_reviewers']} reviewer(s), "
                       f"{cstats['corrections']} correction(s); fired={cfired}")

    ok = verdict != "synthetic" and corpus_ok
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


# How the world state a proof depends on came to exist. G3 asks who the attacker was; G6 asks
# whether the situation they attacked can occur. Those are different questions, and the second one
# had no gate.
STATE_REAL_PATH = "real-path"        # produced by executing the target's own code paths
STATE_NONE_REQUIRED = "none-required"  # the proof depends on no precondition state
STATE_SYNTHESIZED = "synthesized"    # written directly: DB insert, constructed object, monkeypatch
STATE_MODES = {STATE_REAL_PATH, STATE_NONE_REQUIRED, STATE_SYNTHESIZED, NOT_ESTABLISHED}
STATE_PASSING = {STATE_REAL_PATH, STATE_NONE_REQUIRED}


def g6_state_provenance(attest, g):
    """The state the proof depends on must have been REACHED, not written.

    obyte-2026-08-004 passed all five earlier gates and promoted. Its PoC ran, its negative control
    ran, its privilege claim was honest. The impact was still false: the drive script wrote the
    system into a `count>=30` fee window that the real network cannot reach, and ten hours later the
    run's own escalation phase refuted it. The same class had already killed a crash PoC in round 1
    of the same engagement, and killed a k8s finding on an earlier one.

    No earlier gate can see this. G0-G2 check that execution happened. G3 checks WHO ran it. None of
    them ask whether the starting situation is reachable, so a proof that begins mid-attack scores
    exactly like a proof that earned its way there.

    This gate is attestable, not computable: it decides that the package DECLARES how the state
    arose, and refuses the answers that mean "we skipped that part".

    `mode` is about the IMPACT-BEARING state only — the state the severity claim rests on. Almost
    every lab seeds SOME background: a genesis, an asset, a funded address. Blocking on that would
    block honest work. obyte-2026-08-003 seeded a private asset and an output by direct INSERT, then
    drove the actual defect through composer -> validation.validate -> writer.saveJoint; its raw log
    shows the real validator accepting both units. That is a real-path proof over ordinary setup.
    obyte-2026-08-004 wrote the `count>=30` fee window itself, and that window WAS the impact claim.

    So background seeding is allowed but must be itemised: each element needs a `reachability_basis`
    saying why that state is ordinary. Listing it is cheap when it is ordinary and awkward when it is
    not, which is the point — 004 could not have written a straight-faced basis for its window."""
    sp = (attest or {}).get("state_provenance")
    if not isinstance(sp, dict) or not sp.get("mode"):
        g.add("G6", False, "the provenance of the proof's precondition state is declared",
              f"state_provenance.mode MISSING; declare one of: {', '.join(sorted(STATE_MODES))}")
        return
    mode = str(sp["mode"]).strip().lower()
    if mode not in STATE_MODES:
        g.add("G6", False, "the declared state provenance is recognised",
              f"unrecognised mode {sp['mode']!r}; known: {', '.join(sorted(STATE_MODES))}")
        return
    if mode == NOT_ESTABLISHED:
        g.add("G6", False, "the precondition state is established",
              "state_provenance=not-established — declared, not omitted; the proof's starting "
              "situation has not been shown reachable")
        return
    if mode == STATE_SYNTHESIZED:
        elems = sp.get("synthesized_elements") or []
        listed = ", ".join(map(str, elems)) if elems else "none listed"
        g.add("G6", False, "the impact-bearing state was reached, not written",
              f"state_provenance=synthesized ({listed}) — the state the severity claim rests on was "
              f"written directly, so the proof demonstrates the sink, not the reach; re-run it "
              f"through the real path, or cap the claim to what the real path shows")
        return
    if not sp.get("established_by"):
        g.add("G6", False, "the state provenance names its evidence",
              f"mode={mode} with no established_by; name the attempt or evidence file that shows the "
              f"impact-bearing state arising from the target's own code")
        return
    # Background seeding is permitted, itemised, and justified one line at a time.
    setup = sp.get("synthesized_setup") or []
    if not isinstance(setup, list):
        g.add("G6", False, "synthesized_setup is a list of itemised elements",
              f"got {type(setup).__name__}")
        return
    unjustified = [s for s in setup
                   if not isinstance(s, dict) or not str(s.get("reachability_basis") or "").strip()]
    if unjustified:
        names = ", ".join(str(s.get("element", s))[:60] if isinstance(s, dict) else str(s)[:60]
                          for s in unjustified[:3])
        g.add("G6", False, "every seeded setup element carries a reachability basis",
              f"{len(unjustified)} of {len(setup)} element(s) have no reachability_basis: {names}")
        return
    g.add("G6", True, "the impact-bearing state was reached through the real path",
          f"mode={mode}, established_by={sp['established_by']}, "
          f"{len(setup)} seeded setup element(s), each with a reachability basis")


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
    g6_state_provenance(attest, g)
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
    # Promotion must be a MOVE OUT OF unproven/, not a blessing applied wherever the package sits.
    # Version 1 moved any path it was handed, so the default-reject design rested entirely on the
    # operating agent's discipline: a package created straight in findings/ was never promoted and
    # so never gated. Measured on obyte-ocore-2026-08 (2026-08-11): the flow was followed, but
    # nothing enforced it.
    want_parent = os.path.abspath(os.path.join(args.engagement, UNPROVEN))
    if os.path.dirname(pkg.rstrip("/")) != want_parent:
        g.add("source", False, f"the package is promoted out of {UNPROVEN}/",
              f"package sits at {pkg}, expected a child of {want_parent} — a finding that was never "
              f"in {UNPROVEN}/ was never gated on its way in")
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
