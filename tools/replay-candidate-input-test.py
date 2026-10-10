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
        campaign_dir = os.path.join(temp, "evals", "campaign")
        os.makedirs(campaign_dir)
        campaign = os.path.join(campaign_dir, "campaign.json")
        with open(campaign, "w", encoding="utf-8") as handle:
            json.dump({"campaign_id": "input-test", "budgets": {}, "frozen_inputs": {}}, handle)
        with open(os.path.join(campaign_dir, "report.json"), "w", encoding="utf-8") as handle:
            json.dump({"baseline_scoreboard": {
                "routing": [], "hermetic_bola": {"passed": False, "target_calls": 0},
                "false_discovery": {"passed": True}, "hermetic_fakemodel": [], "hermetic_api": [],
            }, "candidates": []}, handle)
        result = subprocess.run(
            [sys.executable, SCRIPT, "--campaign", campaign],
            cwd=ROOT, capture_output=True, text=True, timeout=5, check=False,
        )
        regular_ok = result.returncode == 0 and "Replay report — input-test" in result.stdout
        print(f"{'ok' if regular_ok else 'FAIL'} regular campaign still runs")
        if not regular_ok:
            failures.append(f"regular campaign failed: exit={result.returncode} {result.stderr}")

        with open(os.path.join(campaign_dir, "report.json"), "w", encoding="utf-8") as handle:
            json.dump({"baseline_scoreboard": {
                "routing": [], "hermetic_bola": {"passed": False, "target_calls": 0},
                "false_discovery": {"passed": True}, "hermetic_fakemodel": [], "hermetic_api": [],
            }, "candidates": [{
                "candidate_id": "../../escape", "gate": "allow", "scored": True,
                "keep_discard": {"verdict": "allow"},
            }]}, handle)
        result = subprocess.run(
            [sys.executable, SCRIPT, "--campaign", campaign],
            cwd=ROOT, capture_output=True, text=True, timeout=5, check=False,
        )
        escaped = os.path.join(temp, "evals", "escape", "replays")
        traversal_ok = (result.returncode == 2 and "candidate_id" in result.stderr
                        and "Traceback" not in result.stderr and not os.path.exists(escaped))
        print(f"{'ok' if traversal_ok else 'FAIL'} report candidate ID cannot write outside candidates/")
        if not traversal_ok:
            failures.append(f"unsafe report candidate ID escaped: exit={result.returncode} {result.stderr}")

    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    print("REPLAY-CANDIDATE INPUT E2E: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
