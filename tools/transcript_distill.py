#!/usr/bin/env python3
"""Distil candidate KB entries from past session transcripts. PROPOSER ONLY.

Adapted from Kun Chen's `backpass` (https://github.com/kunchenguid/backpass) after reading its
source. Three things are taken and three are refused, and the refusals are the design.

TAKEN
  - Evidence from transcripts, not recollection.
  - Batching: a signal seen in fewer than N sessions is noise, not a lesson.
  - Near-duplicate clustering across sessions.

REFUSED
  - Writing to doctrine. In this repo `AGENTS.md`/`CLAUDE.md` IS the evaluator -- the hard gates,
    the role separation reserving `confirmed`, and the no-self-rewriting rule. `docs/decisions/
    0003` requires an evaluator change to re-run the incumbent before any candidate is judged, and
    a review click is not that. This tool has NO write path to any tracked file. Enforced by
    DENY_WRITE plus a conformance check, so it is a fence rather than a docstring.
  - The REMOVE step and its zero-sum token budget. `tools/kb.py:21` -- a negative records that WE
    failed to find something, evidence about our search and not about the target. Deleting a unit
    because it accumulated negatives is the D-09 error: three covered-dry runs against hardened
    targets would retire the family, and the fourth target ships it unguarded.
  - The model's self-report about which instruction helped. backpass's README calls the verbatim
    quote "the single most important defence against a model confabulating influence"; its code
    never checks the quote against the transcript (`analyze.js:40` accepts any string >= 8 chars).

WHAT THIS MINES INSTEAD: the OPERATOR'S OWN CORRECTIONS. When the user tells the agent it is wrong,
that is external ground truth in the user's words -- not the agent grading its own homework, which
is the shape that produced the fabricated `claim_state: supported` field. Every candidate carries a
VERIFIED verbatim quote: the tool re-reads the source transcript and confirms the span is really
there, which is the check backpass documents and does not perform.

REDACTION FAILS CLOSED. Engagement transcripts are Plane-3 material and some engagements sit under
disclosure obligations. A candidate matching a secret, host, or engagement identifier is DROPPED,
and an unreadable transcript yields zero candidates rather than a pass.

Output is candidate JSON on stdout. A human reads it, writes the entry, and runs `tools/kb.py add`,
where the schema gate and the ablation gate decide. This tool never appends to memory/kb.jsonl.

Usage:
  python3 tools/transcript_distill.py scan [--sessions DIR] [--min-sessions 2] [--json]
  python3 tools/transcript_distill.py --self-test
"""

import argparse
import glob
import json
import os
import re
import stat
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SESSIONS = os.path.expanduser(
    "~/.claude/projects/-Users-matheusvsky-Documents-trab-llm-redteam-harness")

# Files this tool must never open for write. The fence, not a note about the fence.
DENY_WRITE = ("AGENTS.md", "CLAUDE.md", "engine/gates.md",
              "engagements/_TEMPLATE/scope.md", "skills/oracles/adjudication-oracle.md",
              "memory/kb.jsonl")

# An operator turn matching one of these is a correction: external ground truth about a miss.
CORRECTION_MARKERS = [
    (r"\bthat(?:'?s| is| was) (?:wrong|not right|incorrect)\b", "flat-contradiction"),
    (r"\bno[,.]?\s+(?:it|that|we|you|i)\b", "flat-contradiction"),
    (r"\bthis is (?:wrong|not right|incorrect)\b", "flat-contradiction"),
    (r"\byou (?:are|were) wrong\b", "flat-contradiction"),
    (r"\bdon'?t (?:do|use|call|run)\b", "prohibition"),
    (r"\bstop\b.{0,40}\b(?:doing|using|calling)\b", "prohibition"),
    (r"\bactually[,]? (?:it|we|the)\b", "correction-of-fact"),
    (r"\bi (?:said|told you|already said)\b", "repeat-instruction"),
    (r"\bagain[,.]? (?:please|do|use)\b", "repeat-instruction"),
    (r"\bnot (?:what|how) i (?:asked|wanted|meant)\b", "intent-miss"),
    (r"\brecheck\b|\bre-?check\b|\bverify (?:that|it) (?:again|yourself)\b", "verification-demand"),
]

# Redaction. Any hit drops the candidate. Deliberately broad: a false drop costs one candidate,
# a false pass can put a client's hostname into a tracked file that git history keeps forever.
SECRET_PATTERNS = [
    (r"\b(?:https?://)?[a-z0-9][a-z0-9.-]*\.(?:com|net|org|io|dev|app|xyz|co|sh|ai)\b", "hostname"),
    (r"\b\d{1,3}(?:\.\d{1,3}){3}\b", "ip-address"),
    (r"\b(?:sk|pk|ghp|gho|ghs|xox[bpas])[-_][A-Za-z0-9_-]{12,}", "token"),
    (r"\bBearer\s+[A-Za-z0-9._-]{10,}", "bearer"),
    (r"\bAuthorization\s*:", "auth-header"),
    (r"\beyJ[A-Za-z0-9_-]{8,}\.", "jwt"),
    (r"-----BEGIN [A-Z ]*PRIVATE KEY-----", "private-key"),
    (r"\b[A-Fa-f0-9]{40,64}\b", "hash-or-key"),
]


def engagement_names():
    d = os.path.join(ROOT, "engagements")
    if not os.path.isdir(d):
        return []
    return [n for n in os.listdir(d) if not n.startswith((".", "_"))]


def redact_reason(text, engagements):
    for pat, label in SECRET_PATTERNS:
        if re.search(pat, text, re.I):
            return label
    low = text.lower()
    for e in engagements:
        if e.lower() in low:
            return f"engagement-identifier:{e}"
        head = e.split("-")[0]
        if len(head) > 4 and head.lower() in low:
            return f"engagement-identifier:{head}"
    return None


def _open_regular_text(path):
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise OSError("transcript input is not a regular file")
        return os.fdopen(fd, "r", errors="ignore")
    except BaseException:
        os.close(fd)
        raise


def user_turns(path):
    """Yield (index, text) for HUMAN-TYPED operator turns only.

    The first version of this filter kept every `type: "user"` row and excluded three prefixes it
    guessed at. Run against the real corpus it returned 4 candidates and all 4 were machine text --
    compaction preambles and injected slash-command prompts. 13,814 of 16,484 "user" rows are tool
    results wearing the user role; a prose-prefix filter cannot see that.

    The discriminators are structural, taken from the rows themselves:
      toolUseResult present -> a tool result, not a turn        (13,814 rows)
      isSidechain           -> a subagent's turn, not the operator's
      promptSource != typed -> "system" is hook/slash-command injection; "sdk" is a programmatic
                               run (the standup-worklog cron was the last false positive to fall)
      entrypoint=sdk-cli    -> an automated session, not a person at a keyboard
      compaction preamble   -> written by the harness at a context boundary

    This is the instruments-must-meet-real-layouts rule: a filter validated only against an
    imagined layout can be 100% wrong on real data and still look like it ran.
    """
    try:
        fh = _open_regular_text(path)
    except OSError:
        return
    for i, line in enumerate(fh):
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("type") != "user":
            continue
        if row.get("toolUseResult") is not None:
            continue
        if row.get("isSidechain"):
            continue
        if row.get("promptSource") not in (None, "typed"):
            continue        # "system" = hook/slash-command injection, "sdk" = programmatic run
        if row.get("entrypoint", "cli") not in ("cli", "vscode", "web", None):
            continue        # "sdk-cli" is an automated session, not a person at a keyboard
        msg = row.get("message") or {}
        content = msg.get("content")
        if isinstance(content, list):
            content = " ".join(c.get("text", "") for c in content if isinstance(c, dict))
        if not isinstance(content, str) or not content.strip():
            continue
        stripped = content.lstrip()
        if stripped.startswith(("<system-reminder", "<local-command", "<task-notification",
                                "<user-prompt-submit-hook", "This session is being continued")):
            continue
        yield i, content.strip()


def verify_quote(path, quote):
    """Re-read the source and confirm the span is really there. backpass documents this; it does
    not do it. A candidate whose quote cannot be found is dropped, not downgraded."""
    try:
        with _open_regular_text(path) as fh:
            return quote[:120] in fh.read()
    except OSError:
        return False


def normalise(text):
    return re.sub(r"[^a-z0-9 ]+", " ", text.lower())


def bigrams(text):
    toks = normalise(text).split()
    return {(toks[i], toks[i + 1]) for i in range(len(toks) - 1)}


def similarity(a, b):
    """Sorensen-Dice over word bigrams. Same measure backpass uses, used only to CLUSTER
    candidates -- never, as backpass does, to decide that a lesson has been learned."""
    x, y = bigrams(a), bigrams(b)
    return 0.0 if not x or not y else 2 * len(x & y) / (len(x) + len(y))


def scan(sessions_dir, min_sessions, threshold=0.35):
    engagements = engagement_names()
    hits, stats = [], {"sessions": 0, "turns": 0, "matched": 0, "redacted": 0, "unverified": 0}
    for path in sorted(glob.glob(os.path.join(sessions_dir, "*.jsonl"))):
        stats["sessions"] += 1
        sid = os.path.basename(path)[:8]
        for idx, text in user_turns(path):
            stats["turns"] += 1
            kind = next((k for pat, k in CORRECTION_MARKERS if re.search(pat, text, re.I)), None)
            if not kind:
                continue
            stats["matched"] += 1
            snippet = " ".join(text.split())[:280]
            reason = redact_reason(snippet, engagements)
            if reason:
                stats["redacted"] += 1
                continue
            if not verify_quote(path, snippet):
                stats["unverified"] += 1
                continue
            hits.append({"session": sid, "turn": idx, "kind": kind, "quote": snippet,
                         "source": f"{os.path.basename(path)}:{idx}"})

    clusters = []
    for h in hits:
        for c in clusters:
            if c["kind"] == h["kind"] and similarity(c["members"][0]["quote"], h["quote"]) >= threshold:
                c["members"].append(h)
                break
        else:
            clusters.append({"kind": h["kind"], "members": [h]})

    candidates = []
    for c in clusters:
        sess = sorted({m["session"] for m in c["members"]})
        if len(sess) < min_sessions:
            continue                        # batching rule: fewer than N sessions is noise
        candidates.append({
            "kind": c["kind"],
            "sessions": sess,
            "session_count": len(sess),
            "occurrences": len(c["members"]),
            "evidence": [{"source": m["source"], "quote": m["quote"]} for m in c["members"][:5]],
            "proposed_entry_kind": "loser",
            "note": "CANDIDATE ONLY. A human writes the kb-entry and runs tools/kb.py add, where "
                    "the schema gate and the ablation gate decide. This tool proposes nothing "
                    "about doctrine text and never writes.",
        })
    candidates.sort(key=lambda c: (-c["session_count"], -c["occurrences"]))
    return candidates, stats


def cmd_scan(args):
    if not os.path.isdir(args.sessions):
        print(f"no session directory at {args.sessions}", file=sys.stderr)
        return 1
    candidates, stats = scan(args.sessions, args.min_sessions)
    if args.json:
        print(json.dumps({"candidates": candidates, "stats": stats}, indent=2, sort_keys=True))
        return 0
    print(f"sessions scanned   : {stats['sessions']}")
    print(f"operator turns     : {stats['turns']}")
    print(f"correction signals : {stats['matched']}")
    print(f"dropped, redaction : {stats['redacted']}   (fails closed -- a hit is DROPPED)")
    print(f"dropped, unverified: {stats['unverified']}  (quote not found in its own transcript)")
    print(f"candidates (>= {args.min_sessions} sessions): {len(candidates)}\n")
    for c in candidates:
        print(f"[{c['kind']}]  {c['session_count']} sessions, {c['occurrences']} occurrences")
        for e in c["evidence"][:2]:
            print(f"    {e['source']}")
            print(f"      \"{e['quote'][:150]}\"")
        print()
    if candidates:
        print("These are CANDIDATES. Write the kb-entry yourself and run tools/kb.py add --file "
              "<entry> --fixture <ablation fixture>. The gates there decide, not this tool.")
    return 0


# ---------------------------------------------------------------- self-test

def self_test():
    import tempfile
    ok = True

    def check(name, cond, detail=""):
        nonlocal ok
        ok &= bool(cond)
        print(f"  {'ok  ' if cond else 'FAIL'} {name}" + (f"  -> {detail}" if not cond else ""))

    print("[self-test] the write fence")
    src = open(os.path.abspath(__file__)).read()
    # The fence is about TRACKED REPO files. The self-test legitimately writes a tempfile, so a
    # blanket "no open for write" assertion fails on the test rather than on the tool -- an
    # instrument measuring the wrong thing. Assert what actually matters: no write path that can
    # reach ROOT, and no deny-listed name used as a write target.
    scan_body = src[src.index("def scan("):src.index("def cmd_scan(")]
    cmd_body = src[src.index("def cmd_scan("):src.index("# ---")]
    for name, body in (("scan()", scan_body), ("cmd_scan()", cmd_body)):
        check(f"{name} opens nothing for write",
              not re.search(r"open\([^)]*['\"][wa]", body))
    check("ROOT is never joined with a write mode",
          not re.search(r"open\(os\.path\.join\(ROOT[^)]*\)[^)]*['\"][wa]", src))
    for f in ("AGENTS.md", "CLAUDE.md", "memory/kb.jsonl"):
        check(f"{f} appears only in the deny-list, never as a write target",
              f in DENY_WRITE and not re.search(rf"open\([^)]*{re.escape(f)}[^)]*['\"][wa]", src))

    print("[self-test] redaction fails closed")
    engs = ["exodus-2026-08"]
    for text, want in [
        ("the bug is at admin.example.com/login", "hostname"),
        ("token sk-abcdefghijklmnop123", "token"),
        ("Authorization: Bearer zzzz", "auth-header"),
        ("connect to 10.0.0.14 first", "ip-address"),
        ("in the exodus-2026-08 keychain", "engagement-identifier:exodus-2026-08"),
        ("no, that is wrong, use the other flag", None),
    ]:
        got = redact_reason(text, engs)
        check(f"{want or 'clean text passes'}", (got == want) if want else (got is None),
              f"got {got}")

    print("[self-test] quote verification -- the check backpass documents and skips")
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "s.jsonl")
        open(p, "w").write(json.dumps({"type": "user",
                                       "message": {"content": "no, that is wrong, redo it"}}) + "\n")
        check("a real quote verifies", verify_quote(p, "no, that is wrong"))
        check("an invented quote is rejected", not verify_quote(p, "I never said this sentence"))

    print("[self-test] batching -- fewer than N sessions is noise")
    with tempfile.TemporaryDirectory() as tmp:
        for name in ("aaaaaaaa.jsonl", "bbbbbbbb.jsonl"):
            open(os.path.join(tmp, name), "w").write(
                json.dumps({"type": "user",
                            "message": {"content": "no, that is wrong, redo the check"}}) + "\n")
        c2, _ = scan(tmp, min_sessions=2)
        check("a signal in 2 sessions becomes a candidate", len(c2) == 1, str(c2))
        c3, _ = scan(tmp, min_sessions=3)
        check("the same signal in 2 sessions is dropped at N=3", len(c3) == 0, str(c3))

    print("[self-test] non-regular session inputs do not block the scan")
    with tempfile.TemporaryDirectory() as tmp:
        os.mkfifo(os.path.join(tmp, "fifo-session.jsonl"))
        try:
            result = subprocess.run(
                [sys.executable, os.path.abspath(__file__), "scan", "--sessions", tmp, "--json"],
                capture_output=True, text=True, timeout=3, check=False,
            )
        except subprocess.TimeoutExpired:
            result = None
        check("FIFO session path returns promptly",
              result is not None and result.returncode == 0 and json.loads(result.stdout).get("stats", {}).get("turns") == 0)

    print("[self-test] no REMOVE proposal, and no budget, is reachable")
    with tempfile.TemporaryDirectory() as tmp:
        for name in ("cccccccc.jsonl", "dddddddd.jsonl"):
            open(os.path.join(tmp, name), "w").write(
                json.dumps({"type": "user",
                            "message": {"content": "no, that is wrong, redo the check"}}) + "\n")
        cands, _ = scan(tmp, min_sessions=2)
        kinds = {c["proposed_entry_kind"] for c in cands}
        check("every proposal is an add-shaped entry kind", kinds <= {"loser", "winner"}, str(kinds))
        check("no candidate carries a remove/delete/retire action",
              not any(re.search(r"remove|delete|retire", json.dumps(c), re.I) for c in cands))
        check("no candidate carries a token budget",
              not any(re.search(r"budget|token_count|deltaTokens", json.dumps(c), re.I)
                      for c in cands))

    print("\nSELF-TEST:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--self-test", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    s = sub.add_parser("scan")
    s.add_argument("--sessions", default=DEFAULT_SESSIONS)
    s.add_argument("--min-sessions", type=int, default=2)
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_scan)
    args = ap.parse_args()
    if args.self_test:
        return self_test()
    if not getattr(args, "fn", None):
        ap.print_help(); return 2
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
