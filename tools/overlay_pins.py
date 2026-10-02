#!/usr/bin/env python3
"""Safety-overlay pin integrity for research-kernel preregistrations.

`docs/engineering/002-decisions.md` D-03 states the rule: a preregistration pins a sha256 of
`AGENTS.md`, and **a change to the bytes invalidates a frozen preregistration record**. D-03 then
added `check_doctrine_mirror()` so CLAUDE.md and AGENTS.md cannot silently diverge.

Nothing was ever added for the pins themselves. On 2026-08-23 all FOUR files in
`evals/research-kernel/ab-readiness/preregistration.json`'s `common_safety_overlay` had drifted off
their pinned hashes, and no check anywhere noticed. A pin with no enforcement is the fail-open shape
this repository keeps rediscovering: an instrument that returns a pass because it never ran.

The check is STATUS-AWARE, because drift means two different things:

  execution_authorized: false  -- a draft. Doctrine is still moving and drift is EXPECTED. Reported
                                  as stale so it is visible, and `repin` refreshes it in one command.
                                  Refreshing a draft is not amending a frozen record; no data exists.
  execution_authorized: true   -- frozen. Drift INVALIDATES the record (D-03) and is a hard failure.
                                  `repin` refuses. The record is void and must be re-declared, not
                                  quietly re-pinned to whatever the bytes say today.

That asymmetry is the whole point. A check that always fails on a draft gets muted; a check that
never fails on a frozen record is the pin we already had.

Usage:
  python3 tools/overlay_pins.py check [--json]
  python3 tools/overlay_pins.py repin [--apply]     # drafts only; refuses on an authorized record
"""

import argparse
import glob
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PREREG_GLOB = os.path.join(ROOT, "evals", "**", "preregistration.json")


def sha256_file(path):
    with open(path, "rb") as fh:
        return "sha256:" + hashlib.sha256(fh.read()).hexdigest()


def find_preregs():
    return sorted(candidate for candidate in glob.glob(PREREG_GLOB, recursive=True)
                  if pinned_path(os.path.relpath(candidate, ROOT)) is not None)


def pinned_path(relative):
    if not isinstance(relative, str) or os.path.isabs(relative):
        return None
    root = Path(ROOT).resolve()
    try:
        path = (root / relative).resolve()
        path.relative_to(root)
        # A repository-local hard link can still alias a path outside ROOT.
        if not path.is_file() or path.stat().st_nlink != 1:
            return None
        return path
    except (OSError, ValueError):
        return None


def inspect(path):
    """Return (doc, rows). rows = [{path, pinned, actual, state}] for every overlay file."""
    with open(path) as fh:
        doc = json.load(fh)
    overlay = doc.get("common_safety_overlay") or {}
    rows = []
    for entry in overlay.get("files", []):
        rel = entry["path"]
        full = pinned_path(rel)
        if full is None:
            rows.append({"path": rel, "pinned": entry.get("sha256"), "actual": None,
                         "state": "missing"})
            continue
        actual = sha256_file(full)
        rows.append({"path": rel, "pinned": entry.get("sha256"), "actual": actual,
                     "state": "ok" if actual == entry.get("sha256") else "drifted"})
    return doc, rows


def cmd_check(args):
    results, failures, stale = [], 0, 0
    for prereg in find_preregs():
        doc, rows = inspect(prereg)
        if not rows:
            continue
        authorized = bool(doc.get("execution_authorized"))
        bad = [r for r in rows if r["state"] != "ok"]
        rel = os.path.relpath(prereg, ROOT)
        results.append({"preregistration": rel, "study_id": doc.get("study_id"),
                        "status": doc.get("status"), "execution_authorized": authorized,
                        "rows": rows})
        if not args.json:
            print(f"{rel}")
            print(f"  study      : {doc.get('study_id')}")
            print(f"  status     : {doc.get('status')}  (execution_authorized={authorized})")
            for r in rows:
                mark = {"ok": "ok  ", "drifted": "DRIFT", "missing": "GONE "}[r["state"]]
                print(f"  {mark} {r['path']}")
                if r["state"] == "drifted":
                    print(f"        pinned {r['pinned'][7:23]}  actual {r['actual'][7:23]}")
        if bad and authorized:
            failures += len(bad)
            if not args.json:
                print(f"  => FAIL: {len(bad)} file(s) drifted on an AUTHORIZED record. Per D-03 the")
                print("     record is INVALIDATED. Re-declare it; do not re-pin to today's bytes.")
        elif bad:
            stale += len(bad)
            if not args.json:
                print(f"  => STALE: {len(bad)} file(s) drifted on a draft. Expected while doctrine")
                print("     moves. Refresh with: tools/overlay_pins.py repin --apply")
        elif not args.json:
            print("  => pins match")
    if args.json:
        print(json.dumps({"results": results, "failures": failures, "stale": stale},
                         indent=2, sort_keys=True))
    return 1 if failures else 0


def cmd_repin(args):
    changed = 0
    for prereg in find_preregs():
        doc, rows = inspect(prereg)
        if not rows:
            continue
        rel = os.path.relpath(prereg, ROOT)
        if doc.get("execution_authorized"):
            bad = [r for r in rows if r["state"] != "ok"]
            if bad:
                print(f"REFUSING {rel}: execution_authorized=true.")
                print("  Drift on an authorized record invalidates it (D-03). Re-pinning would")
                print("  silently rewrite the frozen baseline to whatever the bytes say now.")
                return 1
            continue
        drifted = [r for r in rows if r["state"] == "drifted"]
        missing = [r for r in rows if r["state"] == "missing"]
        if missing:
            print(f"REFUSING {rel}: {[m['path'] for m in missing]} no longer exist.")
            print("  A vanished overlay file is a doctrine change, not a hash refresh. Fix by hand.")
            return 1
        if not drifted:
            continue
        print(f"{rel}: {len(drifted)} pin(s) to refresh")
        for r in drifted:
            print(f"  {r['path']}\n    {r['pinned'][7:23]} -> {r['actual'][7:23]}")
        if not args.apply:
            print("  (dry run — pass --apply to write)")
            continue
        for entry in doc["common_safety_overlay"]["files"]:
            for r in drifted:
                if entry["path"] == r["path"]:
                    entry["sha256"] = r["actual"]
        with open(prereg, "w") as fh:
            json.dump(doc, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        changed += len(drifted)
        print(f"  refreshed {len(drifted)} pin(s)")
    if args.apply and not changed:
        print("nothing to refresh")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check"); c.add_argument("--json", action="store_true")
    c.set_defaults(fn=cmd_check)
    r = sub.add_parser("repin"); r.add_argument("--apply", action="store_true")
    r.set_defaults(fn=cmd_repin)
    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
