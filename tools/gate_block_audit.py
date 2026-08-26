#!/usr/bin/env python3
"""Gate-block audit: does the gate stack block on SUBSTANCE or on PAPERWORK?

`docs/decisions/0011` records the problem this answers:

  "We have no evidence the gates are well-calibrated. We have evidence they have never had to say
   no... Agents iterate `gates` until clean and then `promote`, so a block never enters the record."

An engagement that produced packages BEFORE its record kernel was initialized breaks that pattern
open: the packages exist, the gates fire, and the blocks are preserved instead of iterated away.
That is the first real block corpus this harness has had.

The whole question is whether those blocks mean anything. The classification rule is computable, and
it is deliberately narrow:

  PAPERWORK  the gate blocks on an ABSENT record -- no attempt cited, no review filed, no package
             written. The underlying work may be excellent. The gate is reporting a recording
             failure, and says nothing about whether the finding is real.

  SUBSTANCE  the gate blocks on a DECLARED NEGATIVE -- the package itself states that reach or
             provenance was not established. Nothing is missing; the claim is short.

Only SUBSTANCE blocks bear on gate calibration. Reporting the two together as one "block rate" is
the mistake this tool exists to prevent -- it would let a recording failure masquerade as rigor.

Paperwork blocks are NOT harmless: a finding that was never recorded is indistinguishable from one
that was never made. They are a different defect, in the run rather than in the gates.

Usage:
  python3 tools/gate_block_audit.py --engagement engagements/<id> [--json] [--kernel-start ISO]
"""

import argparse
import datetime as dt
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

from engagement_records import RecordError
from engagement_state import (
    _open_parent_fd,
    _relative_regular_files,
    bound_engagement_source,
    read_governed_file,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# A gate blocking with any of these markers is reporting an ABSENT record.
ABSENT_MARKERS = ("MISSING", "not found in the package", "no claim_adjudication review found",
                  "no review", "holds no addressable")
# A gate blocking with these is reporting a DECLARED value that fails on merit.
DECLARED_MARKERS = ("not-established", "synthesized", "declared, not omitted")


def classify(gate, detail):
    d = detail or ""
    absent = any(m in d for m in ABSENT_MARKERS)
    declared = any(m in d for m in DECLARED_MARKERS)
    # Order matters: a detail naming a MISSING ref is a recording failure even when it also carries
    # the standing "declared, not omitted" explanatory clause.
    if absent and not (declared and not any(m in d for m in ("MISSING", "not found", "no claim_"))):
        return "paperwork"
    if declared:
        return "substance"
    return "unclassified"


def run_gates(pkg, engagement, snapshot=None, package_relative=None):
    if snapshot is not None:
        from finding_lifecycle import run_gates as evaluate_gates

        gates, _ = evaluate_gates(
            pkg,
            engagement,
            snapshot=snapshot,
            package_relative=package_relative,
        )
        return {
            "decision": "blocked" if gates.blocked else "clear",
            "gates": gates.rows,
        }
    out = subprocess.run(
        [sys.executable, os.path.join(ROOT, "tools", "finding_lifecycle.py"), "gates",
         "--engagement", engagement, "--json", pkg],
        capture_output=True, text=True).stdout
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return None


def kernel_start(engagement, snapshot=None):
    """First scope.attested / preflight event. Packages older than this predate the kernel."""
    if snapshot is None:
        with bound_engagement_source(
            Path(engagement), allow_ungoverned=True
        ) as bound:
            try:
                data = read_governed_file(bound / "events.jsonl")
            except FileNotFoundError:
                return None
    else:
        data = snapshot.get("events.jsonl")
        if not isinstance(data, bytes):
            return None
    stamps = []
    for line in data.decode("utf-8", errors="replace").splitlines():
        if line.strip():
            r = json.loads(line)
            ts = r.get("recorded_at")
            if ts:
                stamps.append(ts)
    return min(stamps) if stamps else None


def newest_mtime(engagement: Path, package_relative: str, regular_files: set[str]):
    prefix = package_relative.rstrip("/") + "/"
    ts = []
    for relative in regular_files:
        below = relative[len(prefix):] if relative.startswith(prefix) else ""
        if not below or len(Path(below).parts) != 1:
            continue
        parts = tuple(Path(relative).parts)
        parent_fd, name = _open_parent_fd(engagement, parts, create=False)
        try:
            entry = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            if stat.S_ISREG(entry.st_mode) and not stat.S_ISLNK(entry.st_mode):
                ts.append(entry.st_mtime)
        finally:
            os.close(parent_fd)
    return dt.datetime.fromtimestamp(max(ts), dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if ts else None


def _package_names(engagement: Path) -> list[str]:
    parts = engagement.parts
    if not (len(parts) == 4 and parts[1:3] == ("dev", "fd") and parts[3].isdigit()):
        raise RecordError("bound_engagement_required", "gate audit source is not bound")
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        directory_fd = os.open("unproven", flags, dir_fd=int(parts[3]))
    except FileNotFoundError:
        return []
    try:
        names = []
        for name in sorted(os.listdir(directory_fd)):
            try:
                entry = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            except OSError:
                continue
            if stat.S_ISDIR(entry.st_mode) and not stat.S_ISLNK(entry.st_mode):
                names.append(name)
        return names
    finally:
        os.close(directory_fd)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--engagement", required=True)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--kernel-start")
    args = ap.parse_args()

    eng = args.engagement
    try:
        with bound_engagement_source(
            Path(eng), allow_ungoverned=True
        ) as bound:
            from finding_lifecycle import _snapshot_engagement

            snapshot = _snapshot_engagement(bound)
            regular_files = _relative_regular_files(bound)
            ks = args.kernel_start or kernel_start(bound, snapshot)
            rows, tally = [], {"paperwork": 0, "substance": 0, "unclassified": 0}
            clear = 0

            for name in _package_names(bound):
                package_relative = f"unproven/{name}"
                pkg = bound / package_relative
                j = run_gates(
                    str(pkg),
                    str(bound),
                    snapshot=snapshot,
                    package_relative=package_relative,
                )
                blocks = [(g["gate"], g.get("detail", "")) for g in j.get("gates", []) if not g.get("ok")]
                if not blocks:
                    clear += 1
                cls = {}
                for gate, detail in blocks:
                    c = classify(gate, detail)
                    cls[gate] = c
                    tally[c] += 1
                rows.append({
                    "package": name,
                    "packaged": f"{package_relative}/finding.json" in snapshot,
                    "blocks": cls,
                    "newest_artifact": newest_mtime(bound, package_relative, regular_files),
                })
    except (RecordError, OSError, ValueError, json.JSONDecodeError) as exc:
        status = "quarantined" if isinstance(exc, RecordError) and exc.code == "engagement_quarantined" else "source-unavailable"
        if args.json:
            print(json.dumps({"status": status, "rows": []}, sort_keys=True))
        else:
            print("engagement evidence is quarantined" if status == "quarantined" else "engagement source is unavailable")
        return 1

    # "Fair chance" means the kernel was ACTUALLY IN USE for this package, and the only honest
    # evidence of that is the package citing an attempt that resolves in the ledger. The first
    # version of this filter used file mtime, which counts a git checkout or a later edit as work
    # and admitted 11 packages that never touched the ledger. mtime is a bad instrument for
    # "was this worked while the kernel ran", the same way string length was a bad instrument for
    # "was a control named".
    fair = [r for r in rows if r["packaged"] and r["blocks"].get("G1") != "paperwork"]
    fair_sub = {}
    for r in fair:
        for g, c in r["blocks"].items():
            if c == "substance":
                fair_sub[g] = fair_sub.get(g, 0) + 1

    if args.json:
        print(json.dumps({"kernel_start": ks, "rows": rows, "tally": tally,
                          "clear": clear, "fair_chance": [r["package"] for r in fair],
                          "substance_blocks_on_fair": fair_sub}, indent=2, sort_keys=True))
        return 0

    print(f"engagement    : {eng}")
    print(f"kernel started: {ks or 'never'}")
    print(f"packages      : {len(rows)}   clear: {clear}   blocked: {len(rows)-clear}\n")
    print(f"{'package':44s} {'pkgd':5s} blocks")
    for r in rows:
        b = " ".join(f"{g}:{c[:4]}" for g, c in sorted(r["blocks"].items())) or "clear"
        print(f"{r['package']:44s} {'yes' if r['packaged'] else 'NO':5s} {b}")

    total = sum(tally.values())
    print(f"\nblock classification ({total} blocks)")
    for k, v in tally.items():
        pct = f"{100*v/total:.0f}%" if total else "-"
        print(f"  {k:13s} {v:3d}  {pct}")

    print(f"\npackages that had a FAIR CHANCE (packaged, and citing an attempt that resolves in "
          f"the ledger): {len(fair)} of {len(rows)}")
    for r in fair:
        b = " ".join(sorted(r["blocks"])) or "CLEAR"
        print(f"  {r['package']:44s} {b}")
    print("\nsubstance blocks on those packages:", fair_sub or "none")
    print("\nOnly the last number bears on gate calibration. The rest is a recording failure,")
    print("which is a defect in the run, not in the gates -- and not a harmless one.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
