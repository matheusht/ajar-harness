#!/usr/bin/env python3
"""Projector-safe G2 demonstration. Offline only; no target data or network."""

from __future__ import annotations

import json
import sys
from pathlib import Path

FIXTURE = Path(__file__).resolve().parent
ROOT = FIXTURE.parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from finding_lifecycle import Gates, g2_control  # noqa: E402


def run_case(name: str) -> dict:
    case = FIXTURE / "cases" / name
    finding = json.loads((case / "finding.json").read_text())
    attest = json.loads((case / "attest.json").read_text())
    gates = Gates()
    g2_control(finding, attest, gates, str(FIXTURE))
    assert len(gates.rows) == 1
    return gates.rows[0]


def main() -> int:
    replay = run_case("replay-as-control")
    matched = run_case("matched-control")

    print("G2 CONTROL ROLE")
    print(f"replay-as-control  {'CLEAR' if replay['ok'] else 'BLOCKED'}")
    print(f"matched-control    {'CLEAR' if matched['ok'] else 'BLOCKED'}")

    expected = (not replay["ok"]) and matched["ok"]
    print(f"fixture-invariant  {'PASS' if expected else 'FAIL'}")
    return 0 if expected else 1


if __name__ == "__main__":
    raise SystemExit(main())
