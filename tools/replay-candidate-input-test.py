#!/usr/bin/env python3
"""CLI checks for replay-candidate campaign input handling."""

import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "tools", "replay-candidate.py")


def main():
    failures = []
    with tempfile.TemporaryDirectory(prefix="replay-candidate-input-") as temp:
        fifo = os.path.join(temp, "campaign.fifo")
        os.mkfifo(fifo)
        try:
            result = subprocess.run(
                [sys.executable, SCRIPT, "--campaign", fifo],
                cwd=ROOT, capture_output=True, text=True, timeout=2, check=False,
            )
        except subprocess.TimeoutExpired:
            result = None
        fifo_ok = result is not None and result.returncode == 2 and "regular file" in result.stderr
        print(f"{'ok' if fifo_ok else 'FAIL'} FIFO campaign rejected promptly")
        if not fifo_ok:
            failures.append("FIFO campaign blocks or is not rejected cleanly")

    with tempfile.TemporaryDirectory(prefix="replay-candidate-regular-") as temp:
        campaign = os.path.join(temp, "campaign.json")
        with open(campaign, "w", encoding="utf-8") as handle:
            json.dump({"campaign_id": "input-test", "budgets": {}, "frozen_inputs": {}}, handle)
        with open(os.path.join(temp, "report.json"), "w", encoding="utf-8") as handle:
            json.dump({"baseline_scoreboard": {}, "candidates": []}, handle)
        result = subprocess.run(
            [sys.executable, SCRIPT, "--campaign", campaign],
            cwd=ROOT, capture_output=True, text=True, timeout=5, check=False,
        )
        regular_ok = result.returncode == 0 and "Replay report — input-test" in result.stdout
        print(f"{'ok' if regular_ok else 'FAIL'} regular campaign still runs")
        if not regular_ok:
            failures.append(f"regular campaign failed: exit={result.returncode} {result.stderr}")

    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    print("REPLAY-CANDIDATE INPUT E2E: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
