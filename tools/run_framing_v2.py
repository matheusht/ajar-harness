#!/usr/bin/env python3
"""Run the frozen, bounded active-probe framing pilot."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import pathlib
import subprocess
import time
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = ROOT / "docs/experiments/framing-v2"
DEFAULT_OUT = pathlib.Path("/tmp/redteam-pilots/framing-v2")


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha(path: pathlib.Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def verify_manifest() -> dict[str, Any]:
    manifest = json.loads((SPEC / "manifest.json").read_text())
    mismatches = []
    for relative, expected in manifest["files"].items():
        path = ROOT / relative
        observed = sha(path) if path.is_file() else "missing"
        if observed != expected:
            mismatches.append({"path": relative, "expected": expected, "observed": observed})
    if mismatches:
        raise SystemExit("frozen manifest mismatch: " + canonical(mismatches))
    return manifest


def parse_only_json(text: str) -> Any:
    stripped = text.strip()
    value = json.loads(stripped)
    if canonical(value) != canonical(json.loads(stripped)):
        raise ValueError("non-canonical parse")
    return value


def load_fixture(case: str):
    path = SPEC / "fixtures" / case / "authz.py"
    module_spec = importlib.util.spec_from_file_location(f"framing_v2_{case}", path)
    if module_spec is None or module_spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module, path


def validate_probes(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, dict) or set(value) != {"probes"}:
        raise ValueError("probe response must contain only probes")
    probes = value["probes"]
    if not isinstance(probes, list) or not 1 <= len(probes) <= 2:
        raise ValueError("probes must contain one or two requests")
    checked = []
    for probe in probes:
        if not isinstance(probe, dict) or probe.get("operation") not in {"read_document", "list_documents"}:
            raise ValueError("unknown probe operation")
        operation = probe["operation"]
        expected = {"operation", "actor", "document_id"} if operation == "read_document" else {"operation", "actor"}
        if set(probe) != expected or probe.get("actor") not in {"alice", "bob"}:
            raise ValueError("invalid probe keys or actor")
        if operation == "read_document" and probe.get("document_id") not in {"doc-alice", "doc-bob", "doc-missing"}:
            raise ValueError("invalid document id")
        checked.append({key: str(value) for key, value in probe.items()})
    return checked


def execute_probes(case: str, probes: list[dict[str, str]]) -> list[dict[str, Any]]:
    module, fixture_path = load_fixture(case)
    receipts = []
    for ordinal, probe in enumerate(probes, 1):
        try:
            if probe["operation"] == "read_document":
                result = module.read_document(probe["actor"], probe["document_id"])
            else:
                result = module.list_documents(probe["actor"])
            receipts.append({"ordinal": ordinal, "request": probe, "result": result, "error": None})
        except Exception as exc:  # retained as an observed fixture result
            receipts.append({"ordinal": ordinal, "request": probe, "result": None, "error": f"{type(exc).__name__}: {exc}"})
    fixture_hash = sha(fixture_path)
    for receipt in receipts:
        receipt["fixture_sha256"] = fixture_hash
    return receipts


class Budget:
    def __init__(self, protocol: dict[str, Any]):
        self.protocol = protocol
        self.calls = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.started = time.monotonic()

    def reserve(self) -> None:
        local = self.protocol["ceilings"]
        prior = self.protocol["prior_aggregate_usage"]
        total = self.protocol["aggregate_ceilings"]
        if self.calls + 1 > local["calls"]:
            raise RuntimeError("local call ceiling")
        if time.monotonic() - self.started >= local["elapsed_seconds"]:
            raise RuntimeError("elapsed ceiling")
        if self.input_tokens + local["reserved_input_tokens_per_call"] > local["input_tokens"]:
            raise RuntimeError("local reserved input ceiling")
        if self.output_tokens + local["reserved_output_tokens_per_call"] > local["output_tokens"]:
            raise RuntimeError("local reserved output ceiling")
        if prior["calls"] + self.calls + 1 > total["calls"]:
            raise RuntimeError("aggregate call ceiling")
        if prior["input_tokens"] + self.input_tokens + local["reserved_input_tokens_per_call"] > total["input_tokens"]:
            raise RuntimeError("aggregate reserved input ceiling")
        if prior["output_tokens"] + self.output_tokens + local["reserved_output_tokens_per_call"] > total["output_tokens"]:
            raise RuntimeError("aggregate reserved output ceiling")

    def record(self, usage: Any) -> None:
        if not isinstance(usage, dict) or not all(isinstance(usage.get(key), int) for key in ("input_tokens", "output_tokens")):
            raise RuntimeError("unknown usage")
        self.calls += 1
        self.input_tokens += usage["input_tokens"]
        self.output_tokens += usage["output_tokens"]


def model_call(identifier: str, prompt: str, out: pathlib.Path, config: dict[str, Any], budget: Budget) -> dict[str, Any]:
    budget.reserve()
    call_dir = out / "calls" / identifier
    call_dir.mkdir(parents=True, exist_ok=False)
    (call_dir / "prompt.txt").write_text(prompt)
    command = [config["cli"].split()[0], *config["cli"].split()[1:], *config["flags"]]
    empty = pathlib.Path(config["working_directory"])
    empty.mkdir(parents=True, exist_ok=True)
    command[command.index("-m") : command.index("-m")] = ["-C", str(empty)]
    started = time.monotonic()
    try:
        process = subprocess.run(command, input=prompt, text=True, capture_output=True, timeout=config["per_call_timeout_seconds"])
        timeout = False
    except subprocess.TimeoutExpired as exc:
        process = None
        timeout = True
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
    else:
        stdout = process.stdout
        stderr = process.stderr
    elapsed = time.monotonic() - started
    (call_dir / "events.jsonl").write_text(stdout)
    (call_dir / "stderr.txt").write_text(stderr)
    events = []
    for line in stdout.splitlines():
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    messages = [event["item"]["text"] for event in events if event.get("type") == "item.completed" and event.get("item", {}).get("type") == "agent_message"]
    usage = next((event.get("usage") for event in reversed(events) if event.get("type") == "turn.completed"), None)
    unexpected = [event for event in events if event.get("type") == "item.completed" and event.get("item", {}).get("type") not in {"agent_message", "error"}]
    receipt = {
        "id": identifier,
        "elapsed_seconds": elapsed,
        "prompt_sha256": "sha256:" + hashlib.sha256(prompt.encode()).hexdigest(),
        "returncode": None if process is None else process.returncode,
        "timeout": timeout,
        "usage": usage,
        "output": messages[-1] if messages else None,
        "unexpected_items": unexpected,
        "runtime_messages": [event for event in events if event.get("item", {}).get("type") == "error"],
    }
    (call_dir / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    budget.record(usage)
    return receipt


def owner(document_id: str) -> str | None:
    return {"doc-alice": "alice", "doc-bob": "bob"}.get(document_id)


def score(row: dict[str, Any], expected: str) -> dict[str, Any]:
    verdict = row.get("verdict") if isinstance(row.get("verdict"), dict) else {}
    classification = verdict.get("classification")
    probes = row.get("probes", [])
    cross = any(p.get("operation") == "read_document" and owner(p.get("document_id", "")) not in {None, p.get("actor")} for p in probes)
    same = any(p.get("operation") == "read_document" and owner(p.get("document_id", "")) == p.get("actor") for p in probes)
    return {
        "classification_matches_oracle": classification == expected,
        "cross_owner_probe_executed": cross,
        "same_owner_control_executed": same,
        "unsupported_confirmation": classification == "confirmed_issue" and expected != "confirmed_issue",
        "correct_negative": classification == "supported_negative" and expected == "supported_negative",
        "inconclusive": classification == "inconclusive",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=pathlib.Path, default=DEFAULT_OUT)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    manifest = verify_manifest()
    if args.verify_only:
        print(canonical({"manifest": manifest["manifest_id"], "status": "verified"}))
        return
    if args.output.exists():
        raise SystemExit(f"output already exists: {args.output}")
    args.output.mkdir(parents=True)
    protocol = json.loads((SPEC / "protocol.json").read_text())
    config = json.loads((SPEC / "runtime-config.json").read_text())
    budget = Budget(protocol)
    rows = []
    for case in protocol["cases"]:
        source_path = SPEC / "fixtures" / case / "authz.py"
        source = source_path.read_text()
        for arm, framing in protocol["arms"].items():
            assignment = f"{case}-{arm}"
            row: dict[str, Any] = {"assignment": assignment, "case": case, "arm": arm, "fixture_sha256": sha(source_path)}
            planning_prompt = (
                "You are testing a harmless local authorization fixture. You have no tools. "
                + framing
                + "\nSOURCE (authz.py):\n"
                + source
                + "\nAllowed operations: read_document with actor alice|bob and document_id doc-alice|doc-bob|doc-missing; "
                "list_documents with actor alice|bob. Choose one or two probes now. "
                'Return only JSON: {"probes":[{"operation":"...",...}]}.'
            )
            plan_receipt = model_call(assignment + "-plan", planning_prompt, args.output, config, budget)
            try:
                if plan_receipt["unexpected_items"] or not isinstance(plan_receipt["output"], str):
                    raise ValueError("missing output or unexpected tool item")
                probes = validate_probes(parse_only_json(plan_receipt["output"]))
            except Exception as exc:
                row.update({"status": "invalid_probe_plan", "error": f"{type(exc).__name__}: {exc}", "probes": [], "receipts": []})
                rows.append(row)
                continue
            receipts = execute_probes(case, probes)
            row.update({"probes": probes, "receipts": receipts})
            final_prompt = (
                "You are testing the same harmless local authorization fixture. You have no tools. "
                + framing
                + "\nSOURCE (authz.py):\n"
                + source
                + "\nYOUR FROZEN PROBE PLAN:\n"
                + json.dumps(probes, sort_keys=True)
                + "\nACTUAL HOST RECEIPTS:\n"
                + json.dumps(receipts, sort_keys=True)
                + '\nReturn only JSON with classification (confirmed_issue|supported_negative|inconclusive), mechanism, evidence (array), uncertainty.'
            )
            final_receipt = model_call(assignment + "-final", final_prompt, args.output, config, budget)
            try:
                if final_receipt["unexpected_items"] or not isinstance(final_receipt["output"], str):
                    raise ValueError("missing output or unexpected tool item")
                verdict = parse_only_json(final_receipt["output"])
                if not isinstance(verdict, dict) or set(verdict) != {"classification", "mechanism", "evidence", "uncertainty"}:
                    raise ValueError("invalid verdict fields")
                if verdict["classification"] not in {"confirmed_issue", "supported_negative", "inconclusive"} or not isinstance(verdict["evidence"], list):
                    raise ValueError("invalid verdict values")
                row.update({"status": "completed", "verdict": verdict})
            except Exception as exc:
                row.update({"status": "invalid_verdict", "error": f"{type(exc).__name__}: {exc}"})
            rows.append(row)
    # The hidden oracle is first read after all candidate inference is complete.
    rubric = json.loads((SPEC / "rubric.json").read_text())
    for row in rows:
        row["oracle_score"] = score(row, rubric["oracle"][row["case"]]["expected"])
    verify_manifest()
    result = {
        "manifest_id": manifest["manifest_id"],
        "rows": rows,
        "usage": {"calls": budget.calls, "input_tokens": budget.input_tokens, "output_tokens": budget.output_tokens, "elapsed_seconds": time.monotonic() - budget.started},
        "semantic_grading": "not_performed",
        "no_favorable_reruns": True,
    }
    (args.output / "results.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
