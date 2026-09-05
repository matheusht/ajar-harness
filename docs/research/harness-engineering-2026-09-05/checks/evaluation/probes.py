#!/usr/bin/env python3
"""Reproduce local metadata characterizations; output goes to a new temp directory.

Usage: python probes.py [repository-root]
No network, model/provider, kernel initialization or lifecycle operation is called.
Flow checks use pure normalization/coverage helpers, not the public export command.
These assertions describe existing behavior, including invalid favorable verdicts.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

repo = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[5]
out = Path(tempfile.mkdtemp(prefix="harness-evaluation-101-reproduce-")).resolve()
env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
sys.dont_write_bytecode = True
sys.path.insert(0, str(repo / "tools"))
results = []
commands = []


def run(name, tool, arguments):
    argv = [sys.executable, str(repo / "tools" / tool), *map(str, arguments)]
    process = subprocess.run(argv, cwd=repo, env=env, text=True, capture_output=True,
                             timeout=30, check=False)
    (out / f"{name}.stdout").write_text(process.stdout)
    (out / f"{name}.stderr").write_text(process.stderr)
    commands.append({"name": name, "argv": argv, "returncode": process.returncode})
    return process


def save(name, value):
    path = out / name
    path.write_text(json.dumps(value, indent=2) + "\n")
    return path


def record(name, observed, check):
    results.append({"name": name, "observed": observed, "characterization_holds": bool(check)})


for name, tool in (("q02-self-test", "q02_compare.py"),):
    process = run(name, tool, ["--self-test"])
    count = len(re.findall(r"^  ok  ", process.stdout, re.MULTILINE))
    record(name, {"returncode": process.returncode, "named_checks": count},
           process.returncode == 0 and count > 0)

base_m = {
    "arm_a": {"M1_findings": [f"A{i}" for i in range(1, 6)], "M5_subagents": 2},
    "arm_b": {"M1_findings": [f"B{i}" for i in range(1, 3)], "M5_subagents": 2},
}
base_w = {
    "adjudicator": "synthetic-reviewer",
    "blinding_held": True,
    "run_record": {"ran_concurrently": True, "sequence_order_if_sequential": None,
                   "cross_arm_read_occurred": False, "limit_truncated_an_arm": False},
    "M6_overlap": {"both_arms": 2, "arm_a_only": 3, "arm_b_only": 0},
    "M7_waste": {"arm_a_wasted_rounds": None, "arm_b_wasted_rounds": None,
                 "waste_class_a_avoided_that_b_hit": None},
}


def verdict(name, m, w, expected, raw_worksheet=None):
    mp = save(f"{name}.measurements.json", m)
    wp = save(f"{name}.worksheet.json", w)
    if raw_worksheet is not None:
        wp.write_text(raw_worksheet + "\n")
    process = run(name, "q02_compare.py", ["verdict", "--measurements", mp, "--worksheet", wp])
    found = re.search(r"^VERDICT: (.+)$", process.stdout, re.MULTILINE)
    actual = found.group(1) if found else None
    record(name, {"returncode": process.returncode, "verdict": actual,
                  "blockers_printed": "blocked by:" in process.stdout},
           process.returncode == 0 and actual == expected)
    return process


verdict("q02-control-count-gap", base_m, base_w, "prompt_earns_its_keep")
missing = {"M6_overlap": copy.deepcopy(base_w["M6_overlap"])}
verdict("q02-missing-integrity", base_m, missing, "prompt_earns_its_keep")
wrong_overlap = copy.deepcopy(base_w)
wrong_overlap["M6_overlap"] = {"both_arms": 0, "arm_a_only": 0, "arm_b_only": 0}
verdict("q02-inconsistent-overlap", base_m, wrong_overlap, "prompt_earns_its_keep")
wrong_types = copy.deepcopy(base_w)
wrong_types["blinding_held"] = 0
wrong_types["M6_overlap"] = {"both_arms": "unknown", "arm_a_only": -2.5, "arm_b_only": False}
verdict("q02-wrong-integrity-types", base_m, wrong_types, "prompt_earns_its_keep")
scalar_ids = copy.deepcopy(base_m)
scalar_ids["arm_a"]["M1_findings"] = "ABCDE"
scalar_ids["arm_b"]["M1_findings"] = "AB"
verdict("q02-string-instead-of-id-array", scalar_ids, base_w, "prompt_earns_its_keep")
duplicate_ids = copy.deepcopy(base_m)
duplicate_ids["arm_a"]["M1_findings"] = ["A1"] * 5
duplicate_ids["arm_b"]["M1_findings"] = ["B1"] * 2
verdict("q02-duplicate-result-identities", duplicate_ids, base_w, "prompt_earns_its_keep")
duplicate_json = json.dumps(base_w).replace('"blinding_held": true', '"blinding_held": false, "blinding_held": true')
verdict("q02-duplicate-json-field", base_m, base_w, "prompt_earns_its_keep", duplicate_json)
equal_m = copy.deepcopy(base_m)
equal_m["arm_a"]["M1_findings"] = ["A1"]
equal_m["arm_b"]["M1_findings"] = ["B1"]
waste = copy.deepcopy(base_w)
waste["M6_overlap"] = {"both_arms": 1, "arm_a_only": 0, "arm_b_only": 0}
waste["M7_waste"]["waste_class_a_avoided_that_b_hit"] = " "
verdict("q02-whitespace-waste-description", equal_m, waste, "prompt_earns_its_keep")
failed_blinding = copy.deepcopy(base_w)
failed_blinding["blinding_held"] = False
verdict("q02-explicit-failed-blinding", base_m, failed_blinding, "inconclusive")
truncated = copy.deepcopy(base_w)
truncated["run_record"]["limit_truncated_an_arm"] = True
verdict("q02-explicit-truncation", base_m, truncated, "inconclusive")
bad_m = save("q02-bad-shape.measurements.json", {"arm_a": None, "arm_b": None})
bad_w = save("q02-bad-shape.worksheet.json", base_w)
bad = run("q02-bad-shape", "q02_compare.py", ["verdict", "--measurements", bad_m, "--worksheet", bad_w])
record("q02-bad-shape", {"returncode": bad.returncode, "verdict_present": "VERDICT:" in bad.stdout,
                         "traceback": "Traceback" in bad.stderr},
       bad.returncode != 0 and "VERDICT:" not in bad.stdout and "Traceback" in bad.stderr)

# Three locked synthetic directories, with intentionally no scope, valid kernel ledger,
# finding schema, or target artifacts. Files are harmless text/metadata only.
measurement_root = out / "synthetic-measure-input"
for folder in (measurement_root, measurement_root / "arm-a", measurement_root / "arm-b"):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / ".record-kernel.lock").touch()
for number in range(1, 4):
    folder = measurement_root / "arm-a" / "findings" / f"DOC-{number}"
    folder.mkdir(parents=True)
    (folder / "notes.txt").write_text("Synthetic document bookkeeping; no conclusion has been reviewed.\n")
draft = measurement_root / "arm-a" / "findings" / "DRAFT-V3"
draft.mkdir(parents=True)
(draft / "rev-1.json").write_text(json.dumps({"schema_version": 3, "claim_state": "needs_review"}) + "\n")
(measurement_root / "arm-a" / "progress.md").write_text("Agents budget: 12\nAgents used: 2\n")
measured = run("q02-public-measure-nonresults", "q02_compare.py", ["measure", "--engagement", measurement_root])
parsed = json.loads(measured.stdout) if measured.returncode == 0 else None
record("q02-public-measure-nonresults", parsed,
       measured.returncode == 0 and len(parsed["arm_a"]["M1_findings"]) == 4
       and parsed["arm_a"]["M3_severity"] == {} and parsed["arm_a"]["M5_subagents"] == 14
       and parsed["arm_a"]["M5_attempts"] == 0 and parsed["arm_a"]["M5_events"] == 0)

# No record-kernel fixture: exercise only pure metric helpers.
from flow_telemetry import normalize_generic, _coverage
from research_telemetry import _sum_cost

observation = {
    "schema_version": 1, "document_type": "runtime_observation",
    "engagement_id": "flow-metadata-fixture", "run_id": "run-meta", "session_id": "session-meta",
    "runtime_name": "claude-code", "runtime_version": "synthetic-v1",
    "recorded_at": "2026-07-10T00:00:01Z", "observation_kind": "model_call",
    "operation_id": None, "candidate_id": None, "hypothesis_id": None, "attempt_id": None,
    "duration_seconds": 10, "input_tokens": 100, "output_tokens": 20, "cost_usd": 0.2,
}


def flow(name, rows):
    save(f"{name}.observations.json", rows)
    rows = normalize_generic(rows)
    model_rows = [row for row in rows if row["observation_kind"] == "model_call"]
    # Mirror the four inspected export reductions via the production helper.
    # This validates normalization/arithmetic, not export binding or kernel state.
    summary = {
        "model_calls": _coverage([1 for row in model_rows]),
        "input_tokens": _coverage([row["input_tokens"] for row in model_rows]),
        "cost_usd": _coverage([row["cost_usd"] for row in model_rows]),
        "active_seconds": _coverage([row["duration_seconds"] for row in rows
                                     if row["observation_kind"] != "runtime_wait"]),
    }
    save(f"{name}.helper-summary.json", summary)
    return summary


duplicates = flow("flow-duplicate-observations", [observation, observation])
record("flow-duplicate-observations", duplicates,
       duplicates is not None and duplicates["model_calls"]["value"] == 2
       and duplicates["input_tokens"]["value"] == 200 and duplicates["cost_usd"]["value"] == 0.4)
overlapping = [copy.deepcopy(observation) for _ in range(3)]
for row, kind in zip(overlapping, ("turn", "model_call", "tool_call")):
    row["observation_kind"] = kind
    if kind != "model_call":
        row.update(input_tokens=None, output_tokens=None, cost_usd=None)
overlap_summary = flow("flow-nested-durations", overlapping)
record("flow-nested-durations", overlap_summary,
       overlap_summary is not None and overlap_summary["active_seconds"]["value"] == 30)
partial = copy.deepcopy(observation)
partial.update(recorded_at="2026-07-10T00:00:02Z", cost_usd=None)
partial_summary = flow("flow-partial-cost", [observation, partial])
conservative = _sum_cost([{"cost": {"cost_usd": 0.2}}, {"cost": {"cost_usd": None}}])
record("flow-partial-cost", {"flow": partial_summary["cost_usd"] if partial_summary else None,
                            "research_total": conservative["cost_usd"]},
       partial_summary is not None and partial_summary["cost_usd"] == {"value": 0.2, "records": 2, "measured": 1}
       and conservative["cost_usd"] is None)

manifest = {
    "purpose": "characterization of current code, not repaired acceptance or efficacy",
    "coverage": {"q02": "public measure/verdict CLI and builtin self-test",
                 "flow": "pure normalize_generic/_coverage helpers and research _sum_cost",
                 "not_run": ["flow export", "flow self-test", "kernel initialization/lifecycle",
                             "target", "model/provider", "network"]},
    "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip(),
    "probe_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    "repo": str(repo), "python": sys.version, "executable": sys.executable,
    "jsonschema": importlib.metadata.version("jsonschema"),
    "source_sha256": {str(path.relative_to(repo)): hashlib.sha256(path.read_bytes()).hexdigest()
                      for path in (repo / "tools/q02_compare.py", repo / "tools/flow_telemetry.py",
                                   repo / "tools/intervention_ledger.py", repo / "tools/research_telemetry.py")},
    "loaded_local_python_sha256": {
        str(path.relative_to(repo)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted({Path(module.__file__).resolve() for module in sys.modules.values()
                            if getattr(module, "__file__", None)
                            and Path(module.__file__).resolve().is_relative_to(repo)})
        if path.is_file()
    },
    "commands": commands, "results": results,
    "all_characterizations_hold": all(row["characterization_holds"] for row in results),
}
save("results.json", manifest)
print(json.dumps({"output": str(out), "checks": len(results),
                  "all_characterizations_hold": manifest["all_characterizations_hold"]}, indent=2))
raise SystemExit(0 if manifest["all_characterizations_hold"] else 1)
