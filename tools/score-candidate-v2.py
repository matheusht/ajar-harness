#!/usr/bin/env python3
"""Fail-closed CLI for new candidate scores; v1 remains frozen for historical campaigns."""

import argparse
import importlib.util
import json
import math
import os
import stat
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEGACY_PATH = os.path.join(ROOT, "tools", "score-candidate.py")
_SPEC = importlib.util.spec_from_file_location("score_candidate_v1", LEGACY_PATH)
LEGACY = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(LEGACY)


def _finite_nonnegative(value):
    if type(value) not in (int, float) or value < 0:
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _valid_cost(cost):
    return (
        isinstance(cost, dict)
        and all(_finite_nonnegative(cost.get(key)) for key in ("model_calls", "target_calls"))
        and _finite_nonnegative(cost["model_calls"] + cost["target_calls"])
    )


def _input_errors(incumbent, candidate):
    errors = []
    for label, data in (("incumbent", incumbent), ("candidate", candidate)):
        if not isinstance(data, dict):
            errors.append(f"{label} must be an object")
            continue
        coverage = data.get("clean_confirmed_coverage")
        if not isinstance(coverage, list) or any(
            not isinstance(item, str) or not item.strip() or item != item.strip() for item in coverage
        ):
            errors.append(f"{label}.clean_confirmed_coverage must be a list of canonical nonempty strings")
        protected = data.get("protected_cases")
        if not isinstance(protected, dict) or any(
            not isinstance(key, str) or not key or type(passed) is not bool
            for key, passed in protected.items()
        ):
            errors.append(f"{label}.protected_cases must map names to booleans")
        cost = data.get("cost")
        if not _valid_cost(cost):
            errors.append(f"{label}.cost needs finite nonnegative model_calls and target_calls with a finite total")

    if isinstance(candidate, dict):
        for key in ("conformance_passed", "evidence_contract_complete", "budget_unchanged", "single_mutation"):
            if type(candidate.get(key)) is not bool:
                errors.append(f"candidate.{key} must be boolean")
        rate = candidate.get("false_discovery_rate")
        if not _finite_nonnegative(rate) or rate > 1:
            errors.append("candidate.false_discovery_rate must be a finite number from 0 to 1")
    return errors


def _load(path):
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))
    with os.fdopen(fd, "r", encoding="utf-8") as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise OSError("JSON input is not a regular file")
        return json.load(handle)


def decide(incumbent, candidate):
    errors = _input_errors(incumbent, candidate)
    if not errors:
        return LEGACY.decide(incumbent, candidate)

    # Give the frozen policy safe-shaped data so malformed input still returns a normal BLOCK result.
    safe_incumbent = dict(incumbent) if isinstance(incumbent, dict) else {}
    safe_candidate = dict(candidate) if isinstance(candidate, dict) else {}
    for data in (safe_incumbent, safe_candidate):
        if not isinstance(data.get("clean_confirmed_coverage"), list) or any(
            not isinstance(item, str) or not item.strip() or item != item.strip()
            for item in data["clean_confirmed_coverage"]
        ):
            data["clean_confirmed_coverage"] = []
        protected = data.get("protected_cases")
        if not isinstance(protected, dict) or any(
            not isinstance(key, str) or not key or type(passed) is not bool
            for key, passed in protected.items()
        ):
            data["protected_cases"] = {}
        cost = data.get("cost")
        if not _valid_cost(cost):
            data["cost"] = {"model_calls": 0, "target_calls": 0}
    for key in ("conformance_passed", "evidence_contract_complete", "budget_unchanged", "single_mutation"):
        if type(safe_candidate.get(key)) is not bool:
            safe_candidate[key] = False
    rate = safe_candidate.get("false_discovery_rate")
    if not _finite_nonnegative(rate) or rate > 1:
        safe_candidate["false_discovery_rate"] = 1.0

    result = LEGACY.decide(safe_incumbent, safe_candidate)
    result["verdict"] = "block"
    if len(errors) == 1 and "false_discovery_rate" in errors[0]:
        reason = "false-discovery rate missing or invalid (hard veto)"
    else:
        reason = "invalid scorer input: " + "; ".join(errors)
    result["reasons"].insert(0, reason)
    if any("false_discovery_rate" in error for error in errors):
        result["eligibility"]["false_discovery_zero"] = False
    if any("protected_cases" in error for error in errors):
        result["eligibility"]["no_protected_regression"] = False
    if any("clean_confirmed_coverage" in error or ".cost " in error or "must be an object" in error for error in errors):
        result["eligibility"]["evidence_contract_complete"] = False
    for key in ("conformance_passed", "evidence_contract_complete", "budget_unchanged", "single_mutation"):
        if any(f"candidate.{key} " in error for error in errors):
            result["eligibility"][key] = False
    return result


def main(argv):
    parser = argparse.ArgumentParser(description="Fail-closed candidate scorer.")
    parser.add_argument("--incumbent", required=True)
    parser.add_argument("--candidate", required=True)
    args = parser.parse_args(argv[1:])
    try:
        incumbent, candidate = _load(args.incumbent), _load(args.candidate)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"input error: {exc}", file=sys.stderr)
        return 2
    LEGACY.report(decide(incumbent, candidate))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
