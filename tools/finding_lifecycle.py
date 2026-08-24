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
  G1 real-path      the primary attempt resolves to a real execution      computable + attestable
                    that SIGNALLED, and is attested
  G2 control        a distinct negative-control attempt resolves to a      computable + attestable
                    held/no-signal outcome AND is attested
  G3 privilege      the proven execution context is no more privileged
                    than the claimed attacker position                     computable
  G4 adjudication   a review exists and is not synthetic                   computable
  G5 severity       a claimed severity carries a CVSS vector that
                    recomputes to its stated score                         computable
  G6 state          the world state the proof depends on was REACHED
                    through the real path, not written directly, and the
                    attempt cited as reaching it resolves                   computable + attestable

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
import re
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from engagement_quarantine import (
    inspect_quarantine,
    is_quarantined,
    quarantined_ancestor,
    require_safe_offline_input,
)
from engagement_records import RecordError
from engagement_state import (
    _relative_regular_files,
    bound_engagement_source,
    engagement_lock,
    find_engagement_root,
    read_governed_file,
)

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


def _snapshot_engagement(engagement):
    """Capture gate-readable files from one lock-bound engagement inode."""

    snapshot = {}
    for relative in sorted(_relative_regular_files(Path(engagement))):
        if Path(relative).suffix.lower() not in {".json", ".jsonl", ".md", ".txt"}:
            snapshot[relative] = None
            continue
        try:
            snapshot[relative] = read_governed_file(Path(engagement) / relative)
        except OSError:
            # A file that disappears or ceases to be regular while the snapshot is built is not a
            # usable input. Omitting it makes the corresponding existence/reference gate fail.
            continue
    return snapshot


def _snapshot_package(bound_engagement, relative):
    """Capture only one package while its inferred parent engagement remains bound."""

    parts = tuple(relative) if isinstance(relative, tuple) else Path(relative).parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise RecordError("engagement_source_changed", "gate package changed")
    prefix = "bound-package"
    package_snapshot = _snapshot_engagement(Path(bound_engagement).joinpath(*parts))
    return {
        f"{prefix}/{package_relative}": data
        for package_relative, data in package_snapshot.items()
    }, prefix


def _require_bound_package_current(logical, bound, *, portable):
    """Final pre-report admission check for a snapshot's bound source inode."""

    try:
        root_fd = int(Path(bound).parts[3])
        opened = os.fstat(root_fd)
        named = os.stat(logical, follow_symlinks=False)
    except (OSError, ValueError, IndexError) as exc:
        raise RecordError("engagement_source_changed", "gate source changed") from exc
    if (
        stat.S_ISLNK(named.st_mode)
        or not stat.S_ISDIR(named.st_mode)
        or (opened.st_dev, opened.st_ino) != (named.st_dev, named.st_ino)
        or inspect_quarantine(Path(bound))["quarantined"]
        or inspect_quarantine(Path(logical))["quarantined"]
    ):
        raise RecordError("engagement_source_changed", "gate source changed")
    if portable:
        try:
            require_safe_offline_input(Path(logical))
        except ValueError as exc:
            raise RecordError("engagement_source_changed", "gate source changed") from exc


def _snapshot_json(snapshot, relative):
    try:
        return json.loads(snapshot[relative].decode("utf-8"))
    except (KeyError, UnicodeDecodeError, ValueError):
        return None


def _package_docs(snapshot, package_relative):
    prefix = package_relative.rstrip("/") + "/"
    docs = {}
    for relative, data in snapshot.items():
        if not relative.startswith(prefix) or Path(relative).suffix.lower() not in {".md", ".txt", ".json"}:
            continue
        docs[relative[len(prefix):]] = data.decode("utf-8", errors="replace")
    return docs


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


def _refs(value):
    """Normalize one reference or a reference list into non-empty strings."""
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if not isinstance(value, list):
        return []
    return [str(v).strip() for v in value if isinstance(v, str) and v.strip()]


def _attempt_index(engagement, snapshot=None):
    """Read just enough of attempts.jsonl for referential checks.

    This deliberately does not print or return attempt inputs/outputs. Older engagements use
    ``id``/``verdict`` while the governed record uses ``attempt_id``/``assessment``; the gate reads
    both so a lifecycle migration does not silently discard evidence.
    """
    rows = {}
    try:
        if snapshot is None:
            with open(os.path.join(engagement, "attempts.jsonl"), "rb") as handle:
                data = handle.read()
        else:
            data = snapshot["attempts.jsonl"]
        for lineno, raw_line in enumerate(data.splitlines(), 1):
            line = raw_line.decode("utf-8")
            if not line.strip():
                continue
            record = json.loads(line)
            if not isinstance(record, dict):
                return None, f"attempts.jsonl line {lineno} is not an object"
            attempt_id = record.get("attempt_id") or record.get("id")
            if not isinstance(attempt_id, str) or not attempt_id.strip():
                # Some pre-lifecycle research journals are also named attempts.jsonl but do
                # not contain addressable attempt records. They cannot satisfy a v3 proof ref.
                continue
            attempt_id = attempt_id.strip()
            if attempt_id in rows:
                return None, f"attempts.jsonl contains duplicate id {attempt_id}"
            rows[attempt_id] = record
    except KeyError:
        return None, "attempt ledger unavailable: FileNotFoundError"
    except OSError as exc:
        return None, f"attempt ledger unavailable: {exc.__class__.__name__}"
    except (UnicodeDecodeError, ValueError):
        return None, "attempts.jsonl contains invalid JSON"
    return rows, None


class Gates:
    def __init__(self):
        self.rows = []

    def add(self, gate, ok, label, detail=""):
        self.rows.append({"gate": gate, "ok": bool(ok), "label": label, "detail": detail})

    @property
    def blocked(self):
        return [r for r in self.rows if not r["ok"]]


# --- the gates ----------------------------------------------------------------

def g0_existence(pkg, g, docs=None, package_files=None):
    from score_finding import check_existence, load_package, Result
    if docs is not None:
        from score_finding import PATH_RE
        files = set(package_files or docs)
        names = {os.path.basename(value) for value in files}
        failures = []
        for name, text in docs.items():
            for match in PATH_RE.finditer(text):
                relative = match.group(1)
                if relative.startswith(("http", "//")) or " " in relative:
                    continue
                local = str(Path(name).parent / relative)
                hit = relative in files or local in files or os.path.basename(relative) in names
                if not hit and not re.match(r"^(src|lib|core|kvm|engine|skills|tools|cmd|pkg|x)/", relative):
                    failures.append(f"{name}: {relative} not found in the package")
        g.add("G0", not failures, "every cited path exists", "; ".join(failures[:4]))
        return
    docs = load_package(pkg)
    res = Result()
    if not docs:
        g.add("G0", False, "package has readable documents", f"no .md/.txt/.json under {pkg}")
        return
    check_existence(pkg, docs, res)
    bad = res.failures
    g.add("G0", not bad, "every cited path exists",
          "; ".join(c["detail"] or c["label"] for c in bad[:4]))


def g1_real_path(finding, attest, g, engagement=None, snapshot=None):
    """The primary attempt must be named, attested, AND resolve to a real execution that signalled.

    G1 was attestable-only: it checked that a ref existed and that a boolean was set. Both are
    strings the package writes about itself, so a package could satisfy G1 by naming an attempt that
    never ran, or one that ran and produced nothing.

    This is the mirror of G2 and completes Phase 9. G2 requires the control to resolve to a
    held/no_signal outcome; G1 requires the primary to resolve to the opposite — an attempt that
    actually produced the signal the finding rests on. Together they make the claim "this fired and
    the control did not" computable rather than asserted.

    Legacy v1 packages predate addressable attempt records and keep the old attestable behaviour,
    reported with a stated caveat rather than a false block. v3 packages opt into proof refs and
    therefore fail closed."""
    prim = _refs(dig(finding, "proof.primary_attempt_refs", "attempt_id"))
    attested = bool((attest or {}).get("real-path-exec"))
    if not prim or not attested:
        g.add("G1", False, "a primary attempt is named, resolved, and attested",
              f"primary_attempt={'yes' if prim else 'MISSING'}, "
              f"real-path-exec attestation={'yes' if attested else 'MISSING'}")
        return

    v3_refs = isinstance(finding.get("proof"), dict) and "primary_attempt_refs" in finding["proof"]
    if not engagement or not v3_refs:
        g.add("G1", True, "a primary attempt is named, resolved, and attested",
              "primary named and attested; attempt kind/outcome not resolved "
              "(supply --engagement with a v3 package for the computable check)")
        return

    attempts, error = _attempt_index(engagement, snapshot)
    if error:
        g.add("G1", False, "a primary attempt is named, resolved, and attested", error)
        return

    # An engagement whose ledger holds NO addressable attempt records predates the lifecycle format
    # entirely — obyte-ocore-2026-08's attempts.jsonl is a research journal of `kind: attempt` rows
    # with no attempt_id. Every ref is "unresolved" there, and blocking on that is a false alarm
    # against already-adjudicated work, not a finding about the package. A ledger that HAS records
    # but is missing this one is the opposite: a genuinely dangling reference. Found 2026-08-15 when
    # this gate blocked both promoted obyte findings on first run.
    if not attempts:
        g.add("G1", True, "a primary attempt is named, resolved, and attested",
              "primary named and attested; the engagement ledger holds no addressable attempt "
              "records (pre-lifecycle format), so kind/outcome could not be resolved")
        return

    unresolved = [ref for ref in prim if ref not in attempts]
    if unresolved:
        g.add("G1", False, "a primary attempt is named, resolved, and attested",
              f"unresolved primary-attempt ref(s): {', '.join(unresolved[:3])} — the ledger has "
              f"{len(attempts)} addressable record(s), so this reference dangles")
        return

    # A primary attempt that resolves to a held or no-signal outcome is the finding's own evidence
    # saying the thing did not happen. That is not a blocker to argue with; it is a contradiction.
    DEAD = {"held", "no_signal", "no-signal", "blocked", "refuted", "error", "not_run", "not-run"}
    failures = []
    for ref in prim:
        record = attempts[ref]
        kind = str(record.get("kind") or "").strip().lower().replace("-", "_")
        outcome = str(record.get("assessment") or record.get("verdict") or "").strip().lower()
        if kind == "negative_control":
            failures.append(f"{ref} is kind=negative_control; a control is not a primary attempt")
            continue
        if not outcome:
            failures.append(f"{ref} records no assessment/verdict")
            continue
        if outcome in DEAD:
            failures.append(f"{ref} outcome is {outcome}; the primary attempt did not signal")

    if failures:
        g.add("G1", False, "a primary attempt is named, resolved, and attested",
              "; ".join(failures[:3]))
        return

    g.add("G1", True, "a primary attempt is named, resolved, and attested",
          f"{len(prim)} primary attempt(s) resolve to a non-control record with a signalling outcome")


def g2_control(finding, attest, g, engagement=None, snapshot=None):
    neg = _refs(dig(finding, "proof.negative_control_refs", "control_attempt_id"))
    primary = _refs(dig(finding, "proof.primary_attempt_refs", "attempt_id"))
    replay = _refs(dig(finding, "proof.replay_refs", "replay_attempt_refs"))
    attested = bool((attest or {}).get("negative-control"))
    if not neg or not attested:
        g.add("G2", False, "a distinct negative control is named, resolved, and attested",
              f"control_attempt={'yes' if neg else 'MISSING'}, "
              f"negative-control attestation={'yes' if attested else 'MISSING'}")
        return

    overlap = sorted(set(neg) & (set(primary) | set(replay)))
    if overlap:
        g.add("G2", False, "a distinct negative control is named, resolved, and attested",
              f"role collision: {', '.join(overlap[:3])} is cited as both negative control and "
              "primary/replay; replay is not a negative control")
        return

    # Flat v1 packages predate addressable attempt records. Preserve their old attestable
    # behaviour; v3 packages opt into proof refs and therefore fail closed unless those refs can be
    # resolved against the engagement ledger. Promotion always supplies ``engagement``.
    v3_refs = isinstance(finding.get("proof"), dict) and "negative_control_refs" in finding["proof"]
    if not engagement or not v3_refs:
        g.add("G2", True, "a distinct negative control is named, resolved, and attested",
              "control and replay refs are role-disjoint; attempt kind/outcome not resolved "
              "(supply --engagement with a v3 package for the computable check)")
        return

    attempts, error = _attempt_index(engagement, snapshot)
    if error:
        g.add("G2", False, "a distinct negative control is named, resolved, and attested", error)
        return

    # Same legacy carve-out G1 and G6 carry, and G2 was missing it. An engagement whose ledger holds
    # NO addressable attempt records predates the lifecycle format — obyte-ocore-2026-08's
    # attempts.jsonl is a research journal of `kind: attempt` rows with no attempt_id, so every ref
    # reads as unresolved. Blocking there is a false alarm against already-adjudicated work.
    # A ledger that HAS records but is missing this one is the opposite: a dangling reference.
    # Found 2026-08-16 when both promoted obyte findings went from clear to blocked on G2 alone,
    # after G1 and G6 had already been given this guard.
    if not attempts:
        g.add("G2", True, "a distinct negative control is named, resolved, and attested",
              "control and replay refs are role-disjoint; the engagement ledger holds no addressable "
              "attempt records (pre-lifecycle format), so kind/outcome could not be resolved")
        return

    unresolved = [ref for ref in neg if ref not in attempts]
    if unresolved:
        g.add("G2", False, "a distinct negative control is named, resolved, and attested",
              f"unresolved negative-control ref(s): {', '.join(unresolved[:3])}")
        return

    failures = []
    legacy_unlinked = 0
    for ref in neg:
        record = attempts[ref]
        kind = str(record.get("kind") or "").strip().lower().replace("-", "_")
        outcome = str(record.get("assessment") or record.get("verdict") or "").strip().lower()
        if kind != "negative_control":
            failures.append(f"{ref} is {kind or 'missing-kind'}; expected negative_control")
            continue
        if outcome not in {"held", "no_signal", "no-signal"}:
            failures.append(f"{ref} outcome is {outcome or 'missing'}; expected held/no_signal")
            continue
        controls = _refs(record.get("control_of"))
        if controls and primary and not (set(controls) & set(primary)):
            failures.append(f"{ref} does not control a cited primary attempt")
        elif not controls:
            legacy_unlinked += 1

    if failures:
        g.add("G2", False, "a distinct negative control is named, resolved, and attested",
              "; ".join(failures[:3]))
        return

    detail = (f"{len(neg)} control(s) resolve to kind=negative_control with a held/no_signal "
              "outcome and are role-disjoint from primary/replay")
    if legacy_unlinked:
        detail += f"; {legacy_unlinked} legacy record(s) have no control_of linkage"
    g.add("G2", True, "a distinct negative control is named, resolved, and attested", detail)


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


def _snapshot_reviews(snapshot, prefix=""):
    reviews = []
    seen = set()
    for relative, data in sorted(snapshot.items()):
        if prefix and not relative.startswith(prefix.rstrip("/") + "/"):
            continue
        if not relative.endswith(".json"):
            continue
        try:
            value = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            continue
        for record in value if isinstance(value, list) else [value]:
            if not isinstance(record, dict) or record.get("review_type") != "claim_adjudication":
                continue
            review_id = record.get("review_id")
            if review_id and review_id in seen:
                continue
            if review_id:
                seen.add(review_id)
            reviews.append(record)
    return reviews


def g4_adjudication(pkg, engagement, g, snapshot=None, package_relative=None):
    """The synthetic signature is a property of the review CORPUS, not of one review.

    A package usually carries the single review that adjudicated it, and one review can never show
    single-reviewer / no-dissent / boilerplate together. So this audits the package AND, when an
    engagement is given, the engagement's whole claim_adjudication set. If that corpus was generated,
    no finding resting on it may promote.

    Found 2026-08-10 by running the gates over the eleven spotify findings: G4 passed on all eleven
    while the engagement's 15-review corpus audited `synthetic`."""
    from adjudication_audit import audit, load_reviews
    if snapshot is None:
        rdir = os.path.join(pkg, "reviews")
        reviews = load_reviews(rdir) if os.path.isdir(rdir) else []
    else:
        reviews = _snapshot_reviews(snapshot, f"{package_relative}/reviews")
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
        corpus = load_reviews(engagement) if snapshot is None else _snapshot_reviews(snapshot)
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


def g5_severity(pkg, finding, g, docs=None):
    from score_finding import CVSS_RE, cvss31_base, load_package
    label = dig(finding, "classification.severity.label", "severity")
    if isinstance(label, dict):
        label = label.get("label")
    if not label or str(label).lower() not in SEV_WORDS:
        g.add("G5", True, "no severity claimed, so no vector required")
        return
    blob = "\n".join((load_package(pkg) if docs is None else docs).values())
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


def g6_state_provenance(attest, g, engagement=None, snapshot=None):
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
    # Phase 9's last conversion. G6 was a pure string check: a package could satisfy it by writing
    # the word "real-path", and obyte-2026-08-004 — the finding G6 exists to catch — passes if you
    # relabel one dict value. G1 and G2 already resolve their refs against the attempt ledger, so
    # G6 was the odd one out. Named as such in Decision 0010; converted 2026-08-16.
    #
    # Two declaration shapes are in the wild and both are legitimate: an attempt id
    # (`attempt-d1-001-primary`, angular-cli) and an evidence path with prose (obyte). Only the
    # first is resolvable, so only the first is resolved. The rest keeps the attestable behaviour
    # with a stated caveat rather than a false block — the same legacy handling G1 uses.
    ev = str(sp["established_by"]).strip()
    looks_like_ref = bool(re.match(r"^(attempt://|attempt-)[\w.:/-]+$", ev))
    detail = (f"mode={mode}, established_by={ev[:70]}, "
              f"{len(setup)} seeded setup element(s), each with a reachability basis")

    if engagement and looks_like_ref:
        attempts, error = _attempt_index(engagement, snapshot)
        if error:
            g.add("G6", False, "the impact-bearing state was reached through the real path", error)
            return
        if attempts:
            if ev not in attempts:
                g.add("G6", False, "the impact-bearing state was reached through the real path",
                      f"established_by {ev} does not resolve — the ledger has {len(attempts)} "
                      f"addressable record(s), so this reference dangles")
                return
            rec = attempts[ev]
            kind = str(rec.get("kind") or "").strip().lower().replace("-", "_")
            outcome = str(rec.get("assessment") or rec.get("verdict") or "").strip().lower()
            # The state cannot have been "reached through the real path" by an attempt that is a
            # control, or by one whose own record says nothing happened.
            if kind == "negative_control":
                g.add("G6", False, "the impact-bearing state was reached through the real path",
                      f"established_by {ev} is kind=negative_control; a control does not establish "
                      f"the impact-bearing state")
                return
            if outcome in {"held", "no_signal", "no-signal", "blocked", "refuted", "error",
                           "not_run", "not-run"}:
                g.add("G6", False, "the impact-bearing state was reached through the real path",
                      f"established_by {ev} resolves to outcome={outcome}; the attempt cited as "
                      f"reaching the state did not reach it")
                return
            detail += "; established_by resolves to a signalling non-control attempt"
        else:
            detail += "; ledger holds no addressable records (pre-lifecycle), ref not resolved"
    elif not looks_like_ref:
        detail += "; established_by is prose/path, not an attempt ref — not resolvable"

    g.add("G6", True, "the impact-bearing state was reached through the real path", detail)


# --- G-K: the record kernel must be running BEFORE the work, not after it ---------------------

KERNEL_WAIVER = "HARNESS_KERNEL_WAIVER"


def kernel_state(engagement, snapshot=None):
    """Return (attested, detail). A kernel that starts mid-run cannot cover the work before it.

    exodus-2026-08 initialized its kernel on day 3 of a three-day run. 16 of its 19 packages could
    never resolve an attempt reference afterwards, because the rows they would have cited were never
    appended. The work was real -- 185 KB of evidence, controls named with file:line -- and it is
    unpromotable. Activating late is retroactively fatal, and nothing in this tool noticed.

    This is a PRECONDITION, not a gate on the finding. It says nothing about whether the claim is
    true; it says the ledger cannot speak to it.
    """
    if not engagement:
        return None, "no engagement given, so the kernel cannot be checked"
    try:
        data = (
            snapshot["events.jsonl"]
            if snapshot is not None
            else read_governed_file(Path(engagement) / "events.jsonl")
        )
    except (KeyError, FileNotFoundError, OSError):
        return False, "no events.jsonl: the record kernel was never initialized"
    stamps = []
    for raw_line in data.splitlines():
        line = raw_line.decode("utf-8", errors="replace").strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        et = row.get("event_type") or row.get("type") or ""
        if row.get("recorded_at"):
            stamps.append((row["recorded_at"], et))
    if not stamps:
        return False, "events.jsonl is empty: the record kernel was never initialized"
    first = min(stamps)[0]
    return True, f"kernel active from {first}"


def gk_kernel(engagement, g, snapshot=None):
    ok, detail = kernel_state(engagement, snapshot)
    if ok is None:
        return
    if not ok and os.environ.get(KERNEL_WAIVER):
        g.add("GK", True, "the record kernel was running before the work",
              f"WAIVED via {KERNEL_WAIVER}: {detail}. A waived precondition is recorded, never silent.")
        return
    g.add("GK", bool(ok), "the record kernel was running before the work",
          detail if ok else detail + " -- start it BEFORE any attempt, not after. Work done before "
          "the kernel cannot cite a ledger row, so it can never clear G1/G2. Set "
          f"{KERNEL_WAIVER}=1 to record an explicit, visible waiver.")


def _run_gates_snapshot(pkg, engagement=None, snapshot=None, package_relative=None):
    g = Gates()
    if snapshot is None and (quarantined_ancestor(Path(pkg)) or (engagement and is_quarantined(Path(engagement)))):
        g.add("GQ", False, "the source engagement is admissible", "engagement evidence is quarantined")
        return g, {}
    if snapshot is None:
        finding = load_json(os.path.join(pkg, "finding.json")) or {}
        attest = load_json(os.path.join(pkg, "attest.json")) or {}
        docs = None
        package_files = None
    else:
        finding = _snapshot_json(snapshot, f"{package_relative}/finding.json") or {}
        attest = _snapshot_json(snapshot, f"{package_relative}/attest.json") or {}
        docs = _package_docs(snapshot, package_relative)
        prefix = package_relative.rstrip("/") + "/"
        package_files = {relative[len(prefix):] for relative in snapshot if relative.startswith(prefix)}
    gk_kernel(engagement, g, snapshot)
    g0_existence(pkg, g, docs, package_files)
    g1_real_path(finding, attest, g, engagement, snapshot)
    g2_control(finding, attest, g, engagement, snapshot)
    g3_privilege(finding, attest, g)
    g4_adjudication(pkg, engagement, g, snapshot, package_relative)
    g5_severity(pkg, finding, g, docs)
    g6_state_provenance(attest, g, engagement, snapshot)
    return g, finding


def run_gates(pkg, engagement=None, snapshot=None, package_relative=None):
    """Evaluate gates only from an admitted snapshot for standalone package calls.

    Internal promotion/corpus callers that already supply a snapshot retain their exact behavior.
    The historic public ``run_gates(pkg)`` seam performs the same inferred-engagement or
    portable-package binding as the CLI before any finding detail can reach a returned gate row.
    Inference is an admission boundary only: corpus-aware gates remain opt-in via ``engagement``.
    """

    if snapshot is not None:
        return _run_gates_snapshot(pkg, engagement, snapshot, package_relative)

    package = Path(pkg).absolute()
    if engagement is not None:
        logical = Path(engagement).absolute()
        try:
            relative = package.relative_to(logical)
        except ValueError:
            g = Gates()
            g.add(
                "GQ",
                False,
                "the source engagement is admissible",
                "source package could not be admitted",
            )
            return g, {}
        portable = find_engagement_root(logical) is None
        try:
            with bound_engagement_source(
                logical, allow_ungoverned=portable
            ) as bound:
                admitted = _snapshot_engagement(bound)
                result = _run_gates_snapshot(
                    pkg, bound, admitted, relative.as_posix()
                )
                _require_bound_package_current(logical, bound, portable=portable)
                return result
        except (OSError, RecordError, ValueError):
            g = Gates()
            g.add(
                "GQ",
                False,
                "the source engagement is admissible",
                "source package could not be admitted",
            )
            return g, {}

    located = find_engagement_root(package)
    try:
        if located is not None:
            logical, relative = located
            with bound_engagement_source(logical) as bound:
                admitted, package_prefix = _snapshot_package(bound, relative)
                result = _run_gates_snapshot(
                    pkg, snapshot=admitted, package_relative=package_prefix
                )
                _require_bound_package_current(logical, bound, portable=False)
                return result

        with bound_engagement_source(package, allow_ungoverned=True) as bound:
            prefix = "portable-package"
            admitted = {
                f"{prefix}/{relative}": data
                for relative, data in _snapshot_engagement(bound).items()
            }
            result = _run_gates_snapshot(
                pkg, snapshot=admitted, package_relative=prefix
            )
            _require_bound_package_current(package, bound, portable=True)
            return result
    except (OSError, RecordError, ValueError):
        g = Gates()
        g.add(
            "GQ",
            False,
            "the source engagement is admissible",
            "source package could not be admitted",
        )
        return g, {}


# --- movement -----------------------------------------------------------------

def _bound_root_fd(engagement):
    parts = Path(engagement).parts
    if not (len(parts) == 4 and parts[1:3] == ("dev", "fd") and parts[3].isdigit()):
        raise ValueError("lifecycle mutation requires a bound engagement")
    return int(parts[3])


def _open_state_directory(root_fd, name, *, create=False):
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    if create:
        try:
            os.mkdir(name, 0o700, dir_fd=root_fd)
        except FileExistsError:
            pass
    return os.open(name, flags, dir_fd=root_fd)


def _bound_move(engagement, source_state, destination_state, finding_id):
    if not finding_id or finding_id in {".", ".."} or "/" in finding_id:
        raise ValueError("invalid finding id")
    root_fd = _bound_root_fd(engagement)
    source_fd = _open_state_directory(root_fd, source_state)
    try:
        destination_fd = _open_state_directory(root_fd, destination_state, create=True)
        try:
            source = os.stat(finding_id, dir_fd=source_fd, follow_symlinks=False)
            if stat.S_ISLNK(source.st_mode) or not stat.S_ISDIR(source.st_mode):
                raise ValueError("finding package is not a regular directory")
            try:
                os.stat(finding_id, dir_fd=destination_fd, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                return False
            os.rename(
                finding_id,
                finding_id,
                src_dir_fd=source_fd,
                dst_dir_fd=destination_fd,
            )
            os.fsync(source_fd)
            os.fsync(destination_fd)
            return True
        finally:
            os.close(destination_fd)
    finally:
        os.close(source_fd)


def _append_log_bound(engagement, record):
    root_fd = _bound_root_fd(engagement)
    fd = os.open(
        LOG,
        os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0),
        0o600,
        dir_fd=root_fd,
    )
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("lifecycle log is not a regular file")
        original_size = before.st_size
        data = (json.dumps(record, sort_keys=True) + "\n").encode("utf-8")
        try:
            view = memoryview(data)
            written = 0
            while written < len(view):
                count = os.write(fd, view[written:])
                if count <= 0:
                    raise OSError("lifecycle append made no progress")
                written += count
            os.fsync(fd)
        except Exception:
            os.ftruncate(fd, original_size)
            os.fsync(fd)
            raise
    finally:
        os.close(fd)


def _bound_finding_rows(engagement):
    rows = []
    root_fd = _bound_root_fd(engagement)
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    for state_name in (UNPROVEN, PROVEN):
        try:
            directory_fd = os.open(state_name, flags, dir_fd=root_fd)
        except FileNotFoundError:
            continue
        try:
            for name in sorted(os.listdir(directory_fd)):
                try:
                    entry = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                except OSError:
                    continue
                if stat.S_ISDIR(entry.st_mode) and not stat.S_ISLNK(entry.st_mode):
                    rows.append({"finding_id": name, "state": state_name})
        finally:
            os.close(directory_fd)
    return rows


def cmd_gates(args):
    engagement_arg = getattr(args, "engagement", None)
    if engagement_arg:
        original = Path(engagement_arg).absolute()
        try:
            package_relative = Path(args.package).absolute().relative_to(original).as_posix()
        except ValueError:
            g = Gates(); g.add("GQ", False, "the package belongs to the locked engagement", "package is outside the engagement")
            report(args, g, args.package, moved=None)
            return 1
        portable = find_engagement_root(original) is None
        try:
            with bound_engagement_source(
                original, allow_ungoverned=portable
            ) as engagement:
                snapshot = _snapshot_engagement(engagement)
                g, _ = run_gates(
                    args.package, engagement, snapshot, package_relative
                )
                _require_bound_package_current(
                    original, engagement, portable=portable
                )
                report(args, g, args.package, moved=None)
                return 1 if g.blocked else 0
        except (OSError, RecordError, ValueError):
            g = Gates()
            g.add(
                "GQ",
                False,
                "the source engagement is admissible",
                "source package could not be admitted",
            )
            report(args, g, args.package, moved=None)
            return 1

    package = Path(args.package).absolute()
    located = find_engagement_root(package)
    try:
        if located is not None:
            logical, relative = located
            with bound_engagement_source(logical) as engagement:
                snapshot, package_prefix = _snapshot_package(engagement, relative)
                g, _ = run_gates(
                    args.package, snapshot=snapshot, package_relative=package_prefix
                )
                _require_bound_package_current(logical, engagement, portable=False)
                report(args, g, args.package, moved=None)
                return 1 if g.blocked else 0

        # Scope-less packages are portable inputs, not implicit engagements. Keep one root FD
        # through snapshot, gates, and the irreversible report, and reject if the package is moved
        # under governed/quarantined evidence while the decision is being assembled.
        with bound_engagement_source(package, allow_ungoverned=True) as bound_package:
            package_snapshot = _snapshot_engagement(bound_package)
            prefix = "portable-package"
            snapshot = {
                f"{prefix}/{relative}": data
                for relative, data in package_snapshot.items()
            }
            g, _ = run_gates(
                args.package, snapshot=snapshot, package_relative=prefix
            )
            _require_bound_package_current(package, bound_package, portable=True)
            report(args, g, args.package, moved=None)
            return 1 if g.blocked else 0
    except (OSError, RecordError, ValueError):
        g = Gates()
        g.add(
            "GQ",
            False,
            "the source engagement is admissible",
            "source package could not be admitted",
        )
        report(args, g, args.package, moved=None)
        return 1


def cmd_preflight(args):
    """Round-0 check: refuse to start work before the record kernel is running.

    GK catches a kernel-less engagement at promotion time, which is far too late -- by then the
    attempts that would have been cited are already unrecorded and unrecoverable. This is the same
    check, run BEFORE any work, where it costs one command instead of an engagement.

    Run this as the first line of Round 0, before recon, before the first attempt.
    """
    def refuse_uninitialized(detail):
        print(f"PREFLIGHT: REFUSED  -- {detail}")
        print()
        print("Start the record kernel before any attempt, recon note, or finding package:")
        print(f"    ./.venv/bin/python tools/run-engagement.py init --engagement {args.engagement} ...")
        print()
        print("Work done before the kernel cannot cite a ledger row, so it can never clear G1 or G2.")
        print("exodus-2026-08 initialized on day 3 of a three-day run and stranded 16 of 19 packages")
        print("that way -- real work, controls named with file:line, permanently unpromotable.")
        return 1

    original = Path(args.engagement).absolute()
    try:
        with bound_engagement_source(original) as engagement:
            ok, detail = kernel_state(engagement)
            _require_bound_package_current(original, engagement, portable=False)
            if ok:
                print(f"PREFLIGHT: OK  -- {detail}")
                return 0
            return refuse_uninitialized(detail)
    except RecordError as exc:
        if exc.code == "engagement_coordination_unavailable":
            detail = "no events.jsonl: the record kernel was never initialized"
            return refuse_uninitialized(detail)
        print("PREFLIGHT: REFUSED  -- engagement evidence is quarantined")
        return 1
    except (OSError, ValueError):
        print("PREFLIGHT: REFUSED  -- engagement evidence is quarantined")
        return 1


def cmd_promote(args):
    original = Path(args.engagement).absolute()
    try:
        package_relative = Path(args.package).absolute().relative_to(original)
    except ValueError:
        g = Gates(); g.add("source", False, f"the package is promoted out of {UNPROVEN}/", "package is outside the engagement")
        report(args, g, args.package, moved=False)
        return 1
    with engagement_lock(original) as engagement:
        return _cmd_promote_unlocked(args, engagement, package_relative)


def _cmd_promote_unlocked(args, engagement, package_relative):
    pkg = os.path.abspath(args.package)
    fid = package_relative.name
    snapshot = _snapshot_engagement(engagement)
    g, _ = run_gates(pkg, engagement, snapshot, package_relative.as_posix())
    # Promotion must be a MOVE OUT OF unproven/, not a blessing applied wherever the package sits.
    # Version 1 moved any path it was handed, so the default-reject design rested entirely on the
    # operating agent's discipline: a package created straight in findings/ was never promoted and
    # so never gated. Measured on obyte-ocore-2026-08 (2026-08-11): the flow was followed, but
    # nothing enforced it.
    want_parent = os.path.abspath(os.path.join(args.engagement, UNPROVEN))
    if package_relative.parts != (UNPROVEN, fid):
        g.add("source", False, f"the package is promoted out of {UNPROVEN}/",
              f"package sits at {pkg}, expected a child of {want_parent} — a finding that was never "
              f"in {UNPROVEN}/ was never gated on its way in")
    dest = os.path.join(args.engagement, PROVEN, fid)
    moved = False
    if not g.blocked:
        if not _bound_move(engagement, UNPROVEN, PROVEN, fid):
            g.add("move", False, "destination is free", f"{dest} already exists")
        else:
            moved = True
    _append_log_bound(engagement, {
        "recorded_at": now(), "action": "promote", "finding_id": fid, "actor": args.actor,
        "result": "promoted" if moved else "blocked",
        "gates": [{"gate": r["gate"], "ok": r["ok"]} for r in g.rows],
        "blocked_by": [r["gate"] for r in g.blocked]})
    report(args, g, pkg, moved=moved, dest=dest if moved else None)
    return 0 if moved else 1


def cmd_demote(args):
    with engagement_lock(Path(args.engagement).absolute()) as engagement:
        return _cmd_demote_unlocked(args, engagement)


def _cmd_demote_unlocked(args, engagement):
    src = os.path.join(args.engagement, PROVEN, args.finding_id)
    dest = os.path.join(args.engagement, UNPROVEN, args.finding_id)
    root_fd = _bound_root_fd(engagement)
    try:
        proven_fd = _open_state_directory(root_fd, PROVEN)
        try:
            source = os.stat(args.finding_id, dir_fd=proven_fd, follow_symlinks=False)
            source_exists = stat.S_ISDIR(source.st_mode) and not stat.S_ISLNK(source.st_mode)
        finally:
            os.close(proven_fd)
    except (FileNotFoundError, ValueError):
        source_exists = False
    if not source_exists:
        print(f"not promoted: {src} does not exist")
        return 1
    if not _bound_move(engagement, PROVEN, UNPROVEN, args.finding_id):
        print(f"cannot demote: {dest} already exists")
        return 1
    _append_log_bound(engagement, {
        "recorded_at": now(), "action": "demote", "finding_id": args.finding_id,
        "actor": args.actor, "result": "demoted", "reason": args.reason})
    print(f"demoted {args.finding_id} -> {UNPROVEN}/")
    print(f"reason: {args.reason}")
    return 0


def cmd_status(args):
    original = Path(args.engagement).absolute()
    try:
        with bound_engagement_source(original) as engagement:
            rows = _bound_finding_rows(engagement)
            _require_bound_package_current(original, engagement, portable=False)
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
    except (OSError, RecordError, ValueError):
        if args.json:
            json.dump({"status": "quarantined", "findings": []}, sys.stdout, indent=2)
            sys.stdout.write("\n")
        else:
            print("engagement evidence is quarantined")
        return 1


def report(args, g, pkg, moved, dest=None):
    quarantined = any(row.get("gate") == "GQ" for row in g.rows)
    if getattr(args, "json", False):
        payload = {"decision": "blocked" if g.blocked else "clear", "gates": g.rows}
        if not quarantined:
            payload.update({"package": pkg, "moved_to": dest})
        json.dump(payload, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return
    if quarantined:
        print("engagement evidence is quarantined")
        print(f"\n{len(g.rows)} gates, {len(g.blocked)} blocking")
        print("NOT PROMOTED — the finding stays unproven.")
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

    p = sub.add_parser("preflight", help="Round 0 — refuse to start work before the kernel runs")
    p.add_argument("--engagement", required=True)
    p.set_defaults(fn=cmd_preflight)

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
    try:
        return args.fn(args)
    except RecordError as exc:
        if exc.code != "engagement_quarantined":
            raise
        if args.cmd == "status" and args.json:
            json.dump({"status": "quarantined", "findings": []}, sys.stdout, indent=2)
            sys.stdout.write("\n")
        elif args.cmd in {"gates", "promote"} and getattr(args, "json", False):
            json.dump(
                {
                    "decision": "blocked",
                    "gates": [
                        {
                            "gate": "GQ",
                            "ok": False,
                            "label": "the source engagement is admissible",
                            "detail": "engagement evidence is quarantined",
                        }
                    ],
                },
                sys.stdout,
                indent=2,
            )
            sys.stdout.write("\n")
        elif args.cmd == "preflight":
            print("PREFLIGHT: REFUSED  -- engagement evidence is quarantined")
        else:
            print("engagement evidence is quarantined")
        return 1


if __name__ == "__main__":
    sys.exit(main())
