#!/usr/bin/env python3
"""CLI checks for the versioned scorer's false-discovery hard veto."""

import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SCORER = os.path.join(ROOT, "tools", "score-candidate-v2.py")
LEGACY_SCORER = os.path.join(ROOT, "tools", "score-candidate.py")

INCUMBENT = {
    "clean_confirmed_coverage": ["k1"],
    "protected_cases": {},
    "cost": {"model_calls": 1, "target_calls": 1},
}
CANDIDATE = {
    "candidate_id": "fdr-contract",
    "campaign_id": "test",
    "conformance_passed": True,
    "evidence_contract_complete": True,
    "budget_unchanged": True,
    "single_mutation": True,
    "clean_confirmed_coverage": ["k1", "k2"],
    "protected_cases": {},
    "cost": {"model_calls": 1, "target_calls": 1},
}


def score(scorer, candidate, incumbent=INCUMBENT, extra_args=()):
    with tempfile.TemporaryDirectory(prefix="score-candidate-v2-") as temp:
        incumbent_path = os.path.join(temp, "incumbent.json")
        candidate_path = os.path.join(temp, "candidate.json")
        with open(incumbent_path, "w", encoding="utf-8") as handle:
            json.dump(incumbent, handle)
        with open(candidate_path, "w", encoding="utf-8") as handle:
            json.dump(candidate, handle)
        return subprocess.run(
            [sys.executable, scorer, "--incumbent", incumbent_path, "--candidate", candidate_path, *extra_args],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )


def score_paths(scorer, incumbent_path, candidate_path, timeout=5):
    try:
        return subprocess.run(
            [sys.executable, scorer, "--incumbent", incumbent_path, "--candidate", candidate_path],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return None


def main(argv):
    scorer = os.path.abspath(argv[1]) if len(argv) == 2 else DEFAULT_SCORER
    protected_incumbent = dict(INCUMBENT, protected_cases={"case-a": True})
    malformed_incumbents = [
        ("non-list incumbent coverage", dict(INCUMBENT, clean_confirmed_coverage="k1")),
        ("string incumbent protected flag", dict(INCUMBENT, protected_cases={"case-a": "true"})),
        ("string incumbent cost", dict(INCUMBENT, cost={"model_calls": "100", "target_calls": 1})),
        ("overflowing incumbent cost total", dict(INCUMBENT, cost={"model_calls": 1e308, "target_calls": 1e308})),
    ]
    cases = [
        ("measured zero FDR", dict(CANDIDATE, false_discovery_rate=0.0), "ALLOW", INCUMBENT),
        ("measured FDR regression", dict(CANDIDATE, false_discovery_rate=0.125), "BLOCK", INCUMBENT),
        ("missing FDR", dict(CANDIDATE), "BLOCK", INCUMBENT),
        ("null FDR", dict(CANDIDATE, false_discovery_rate=None), "BLOCK", INCUMBENT),
        ("string FDR", dict(CANDIDATE, false_discovery_rate="0"), "BLOCK", INCUMBENT),
        ("boolean FDR", dict(CANDIDATE, false_discovery_rate=False), "BLOCK", INCUMBENT),
        ("string conformance flag", dict(CANDIDATE, false_discovery_rate=0.0, conformance_passed="false"), "BLOCK", INCUMBENT),
        ("string evidence flag", dict(CANDIDATE, false_discovery_rate=0.0, evidence_contract_complete="false"), "BLOCK", INCUMBENT),
        ("string budget flag", dict(CANDIDATE, false_discovery_rate=0.0, budget_unchanged="false"), "BLOCK", INCUMBENT),
        ("string mutation flag", dict(CANDIDATE, false_discovery_rate=0.0, single_mutation="false"), "BLOCK", INCUMBENT),
        ("string protected flag", dict(CANDIDATE, false_discovery_rate=0.0, protected_cases={"case-a": "false"}), "BLOCK", protected_incumbent),
        ("non-list coverage", dict(CANDIDATE, false_discovery_rate=0.0, clean_confirmed_coverage="k2"), "BLOCK", INCUMBENT),
        ("padded coverage key", dict(CANDIDATE, false_discovery_rate=0.0,
                                      clean_confirmed_coverage=["k1", " k1 "]), "BLOCK", INCUMBENT),
        ("string cost", dict(CANDIDATE, false_discovery_rate=0.0, cost={"model_calls": "1", "target_calls": 1}), "BLOCK", INCUMBENT),
        ("overflowing candidate cost total", dict(CANDIDATE, false_discovery_rate=0.0,
                                                    cost={"model_calls": 1e308, "target_calls": 1e308}), "BLOCK", INCUMBENT),
    ]
    failures = []
    for label, candidate, expected, incumbent in cases:
        result = score(scorer, candidate, incumbent)
        observed = next(
            (word for word in ("ALLOW", "BLOCK", "PROBE") if f": {word}" in result.stdout),
            "PROCESS_ERROR",
        )
        ok = result.returncode == 0 and observed == expected
        if label in {"missing FDR", "null FDR", "string FDR", "boolean FDR"}:
            ok = ok and "false-discovery rate missing or invalid" in result.stdout
        elif label not in {"measured zero FDR", "measured FDR regression"}:
            ok = ok and "invalid scorer input" in result.stdout
        print(f"{'ok' if ok else 'FAIL'} {label}: {observed}, expected {expected}")
        if not ok:
            failures.append((label, result.returncode, result.stdout, result.stderr))
    for label, incumbent in malformed_incumbents:
        result = score(scorer, dict(CANDIDATE, false_discovery_rate=0.0), incumbent)
        ok = result.returncode == 0 and ": BLOCK" in result.stdout and "invalid scorer input" in result.stdout
        print(f"{'ok' if ok else 'FAIL'} {label}: {'BLOCK' if ': BLOCK' in result.stdout else 'PROCESS_ERROR'}")
        if not ok:
            failures.append((label, result.returncode, result.stdout, result.stderr))
    unknown = score(scorer, dict(CANDIDATE, false_discovery_rate=0.0), extra_args=("--typo",))
    unknown_ok = unknown.returncode == 2 and "--typo" in unknown.stderr
    print(f"{'ok' if unknown_ok else 'FAIL'} unknown CLI option rejected")
    if not unknown_ok:
        failures.append(("unknown CLI option", unknown.returncode, unknown.stdout, unknown.stderr))
    with tempfile.TemporaryDirectory(prefix="score-candidate-v2-fifo-") as temp:
        fifo_path = os.path.join(temp, "incumbent.fifo")
        candidate_path = os.path.join(temp, "candidate.json")
        os.mkfifo(fifo_path)
        with open(candidate_path, "w", encoding="utf-8") as handle:
            json.dump(dict(CANDIDATE, false_discovery_rate=0.0), handle)
        result = score_paths(scorer, fifo_path, candidate_path, timeout=1)
        ok = result is not None and result.returncode == 2 and "regular file" in result.stderr
        print(f"{'ok' if ok else 'FAIL'} FIFO input rejected promptly")
        if not ok:
            failures.append(("FIFO input", None if result is None else result.returncode,
                             "timed out" if result is None else result.stdout,
                             "" if result is None else result.stderr))
    if failures:
        for label, code, stdout, stderr in failures:
            print(f"\n{label}: exit={code}\n{stdout}{stderr}", file=sys.stderr)
        return 1
    print("SCORER V2 E2E: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
