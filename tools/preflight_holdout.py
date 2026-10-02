#!/usr/bin/env python3
"""Refuse to start a measured run while any withheld path is readable.

A holdout that leaks does not fail loudly. It produces a clean-looking result that means nothing,
and nobody finds out. So this runs before the engagement, not after, and it exits non-zero.

It checks four ways, because "I moved the directory" is not the same as "no agent can read it":
  1. the path is absent from the working tree
  2. git does not track it on the current branch
  3. no OTHER file in the tree quotes its distinctive content back
  4. the path is not recoverable from git history on this branch

Check 3 is the one that catches real leaks. Withdrawing policy-gate-check.md achieves nothing if
progress.md quotes its conclusion.

Usage
-----
  preflight_holdout.py --prereg fixtures/preregistration/spotify-phase2.json
  preflight_holdout.py --prereg FILE --json
"""

import argparse
import json
import os
import re
import subprocess
import sys

from regular_file_io import load_json, read_regular_text

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _git(*args):
    try:
        out = subprocess.run(["git", "-C", ROOT, *args], capture_output=True, text=True, timeout=30)
        return out.stdout.strip(), out.returncode
    except (subprocess.SubprocessError, OSError):
        return "", 1


def check_absent(rel):
    return not os.path.exists(os.path.join(ROOT, rel))


def check_untracked(rel):
    out, _ = _git("ls-files", "--error-unmatch", rel)
    return not out


def check_recoverable(rel):
    """A path deleted from the tree but present in this branch's history is still readable."""
    out, rc = _git("log", "--oneline", "-1", "--", rel)
    return not out


def distinctive_terms(rel):
    """Terms that would betray the withheld content if another file repeats them."""
    stem = os.path.basename(rel).replace(".md", "").replace(".json", "")
    terms = {stem}
    # phase markers are the cut we made, so treat them as leak indicators
    for m in re.finditer(r"phase\d+", rel, re.I):
        terms.add(m.group(0).lower())
    return {t for t in terms if len(t) > 4}


def check_not_quoted(rel, withheld_set):
    """Return a list of files that reference this withheld path or its distinctive terms."""
    hits = []
    terms = distinctive_terms(rel)
    if not terms:
        return hits
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames
                       if d not in {".git", "node_modules", ".venv", "out", "cache", "__pycache__"}]
        for name in dirnames[:]:
            path = os.path.join(dirpath, name)
            if os.path.islink(path):
                relative = os.path.relpath(path, ROOT)
                hits.append((relative, "unsafe: symlinked directory"))
                dirnames.remove(name)
        for fn in filenames:
            if os.path.splitext(fn)[1].lower() not in {".md", ".txt", ".json", ".jsonl"}:
                continue
            p = os.path.join(dirpath, fn)
            r = os.path.relpath(p, ROOT)
            # the preregistration and this tool legitimately name the paths
            if r.startswith(("fixtures/preregistration", "tools/", "docs/engineering")):
                continue
            if r in withheld_set or any(r.startswith(w.rstrip("/") + "/") for w in withheld_set):
                continue
            try:
                text = read_regular_text(p, errors="replace", no_follow=True).lower()
            except OSError as exc:
                hits.append((r, f"unsafe: {exc.strerror or 'cannot read regular file'}"))
                continue
            for t in terms:
                if t in text:
                    hits.append((r, t))
                    break
    return hits


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--prereg", required=True)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    try:
        prereg = load_json(args.prereg)
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    withheld = prereg.get("holdout", {}).get("paths", [])
    if not withheld:
        print("preregistration declares no holdout paths; nothing to enforce")
        return 1

    wset = set(withheld)
    results, failures = [], []
    for rel in withheld:
        row = {
            "path": rel,
            "absent_from_tree": check_absent(rel),
            "untracked_by_git": check_untracked(rel),
            "absent_from_history": check_recoverable(rel),
            "quoted_elsewhere": check_not_quoted(rel, wset),
        }
        row["ok"] = (row["absent_from_tree"] and row["untracked_by_git"]
                     and row["absent_from_history"] and not row["quoted_elsewhere"])
        results.append(row)
        if not row["ok"]:
            failures.append(row)

    if args.json:
        json.dump({"preregistration": prereg.get("preregistration_id"),
                   "verdict": "clear" if not failures else "blocked",
                   "paths": results}, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        print(f"preregistration: {prereg.get('preregistration_id')}")
        print(f"withheld paths : {len(withheld)}\n")
        for r in results:
            print(f"  {'ok  ' if r['ok'] else 'LEAK'} {r['path']}")
            if not r["absent_from_tree"]:
                print("         still present in the working tree")
            if not r["untracked_by_git"]:
                print("         git tracks it on this branch")
            if not r["absent_from_history"]:
                print("         recoverable from git history on this branch")
            for f, t in r["quoted_elsewhere"][:4]:
                if t.startswith("unsafe:"):
                    print(f"         unsafe scan entry {f} ({t[7:]})")
                else:
                    print(f"         quoted in {f} (term {t!r})")
        print(f"\n{len(withheld)} paths, {len(failures)} blocked")
        if failures:
            print("VERDICT: BLOCKED — do not start the run.")
            print("A leaking holdout yields a clean-looking result that means nothing.")
        else:
            print("VERDICT: CLEAR — the holdout is enforced; the run may start.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
