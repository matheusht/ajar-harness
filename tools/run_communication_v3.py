#!/usr/bin/env python3
"""Run the frozen matched communication and correction pilot."""

from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess
import sys
import time
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = ROOT / "docs/experiments/communication-v3"
DEFAULT_OUT = pathlib.Path("/tmp/redteam-pilots/communication-v3")


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


def parse_json(text: str) -> Any:
    return json.loads(text.strip())


class Budget:
    def __init__(self, protocol: dict[str, Any]):
        self.protocol = protocol
        self.calls = self.input_tokens = self.output_tokens = 0
        self.started = time.monotonic()

    def reserve(self) -> None:
        local, prior, total = self.protocol["ceilings"], self.protocol["prior_aggregate_usage"], self.protocol["aggregate_ceilings"]
        checks = {
            "local calls": self.calls + 1 <= local["calls"],
            "local input reservation": self.input_tokens + local["reserved_input_tokens_per_call"] <= local["input_tokens"],
            "local output reservation": self.output_tokens + local["reserved_output_tokens_per_call"] <= local["output_tokens"],
            "aggregate calls": prior["calls"] + self.calls + 1 <= total["calls"],
            "aggregate input reservation": prior["input_tokens"] + self.input_tokens + local["reserved_input_tokens_per_call"] <= total["input_tokens"],
            "aggregate output reservation": prior["output_tokens"] + self.output_tokens + local["reserved_output_tokens_per_call"] <= total["output_tokens"],
            "elapsed": time.monotonic() - self.started < local["elapsed_seconds"],
        }
        failed = [name for name, ok in checks.items() if not ok]
        if failed:
            raise RuntimeError("budget stop: " + ", ".join(failed))

    def record(self, usage: Any) -> None:
        if not isinstance(usage, dict) or not all(isinstance(usage.get(key), int) for key in ("input_tokens", "output_tokens")):
            raise RuntimeError("unknown usage")
        self.calls += 1
        self.input_tokens += usage["input_tokens"]
        self.output_tokens += usage["output_tokens"]


def model_call(identifier: str, prompt: str, out: pathlib.Path, config: dict[str, Any], budget: Budget) -> dict[str, Any]:
    budget.reserve()
    directory = out / "calls" / identifier
    directory.mkdir(parents=True, exist_ok=False)
    (directory / "prompt.txt").write_text(prompt)
    empty = pathlib.Path(config["working_directory"])
    empty.mkdir(parents=True, exist_ok=True)
    command = [*config["cli"].split(), "-C", str(empty), *config["flags"]]
    started = time.monotonic()
    try:
        process = subprocess.run(command, input=prompt, text=True, capture_output=True, timeout=config["per_call_timeout_seconds"])
        stdout, stderr, timeout = process.stdout, process.stderr, False
        returncode = process.returncode
    except subprocess.TimeoutExpired as exc:
        def decoded(value: str | bytes | None) -> str:
            if value is None:
                return ""
            return value.decode(errors="replace") if isinstance(value, bytes) else value
        stdout, stderr, timeout, returncode = decoded(exc.stdout), decoded(exc.stderr), True, None
    elapsed = time.monotonic() - started
    (directory / "events.jsonl").write_text(stdout)
    (directory / "stderr.txt").write_text(stderr)
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
        "returncode": returncode,
        "timeout": timeout,
        "usage": usage,
        "output": messages[-1] if messages else None,
        "unexpected_items": unexpected,
        "runtime_messages": [event for event in events if event.get("item", {}).get("type") == "error"],
    }
    (directory / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    budget.record(usage)
    return receipt


def source_block(paths: list[pathlib.Path]) -> str:
    return "\n\n".join(f"FILE {path.name}:\n{path.read_text()}" for path in paths)


def require_note(receipt: dict[str, Any]) -> dict[str, str]:
    if receipt["unexpected_items"] or not isinstance(receipt["output"], str):
        raise RuntimeError("worker output missing or contaminated")
    note = parse_json(receipt["output"])
    if not isinstance(note, dict) or set(note) != {"observation", "uncertainty"}:
        raise RuntimeError("worker note shape invalid")
    if not all(isinstance(note[key], str) and note[key].strip() for key in note) or len(note["observation"]) > 220 or len(note["uncertainty"]) > 80:
        raise RuntimeError("worker note length invalid")
    return note


def initialize_board(out: pathlib.Path, case: str, notes: list[dict[str, str]], source_paths: list[pathlib.Path]) -> tuple[pathlib.Path, list[dict[str, Any]], list[dict[str, Any]]]:
    sys.path.insert(0, str(ROOT / "tools"))
    from engagement_state import _append_kernel_event, base_event, initialize_engagement, read_ledger
    from task_notice import compile_hunter_notices
    from task_board import post_notice

    engagement = out / "boards" / case
    engagement.mkdir(parents=True)
    (engagement / "scope.md").write_text(f"""# Scope - {case} communication pilot
## Surfaces in scope
- Local synthetic documents.
## Benign safe-objective set
- Document synthesis.
## Escalation ceiling
- Local only.
## Impact-demo authorization
- impact_demo_authorized: `no`
- zone2_authorized_categories: `none`
- zone2_escalation_ceiling: `none`
- zone2_containment: `none`
## Accounts / fixtures
- None.
## Independent reviewer identity
- Reviewer allowed signers SHA256: sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
## Authorization
- Operator allowed signers SHA256: sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
- Operator: operator-pilot
- Date: 2026-09-22
- Signed: [x]
- Record kernel: `decision-0006-v2`
""")
    initialize_engagement(engagement, "2026-01-01T00:00:00Z")
    engagement_id = engagement.name
    task_id = "task-" + case
    _append_kernel_event(engagement, base_event(event_id=f"event-task-{case}", engagement_id=engagement_id, recorded_at="2026-01-01T00:00:01Z", actor_role="orchestrator", actor_id="coordinator", event_type="observation.recorded", rationale="Define synthetic communication task.", payload={"entity_id": task_id, "entity_type": "task_definition", "status": "recorded", "task_id": task_id, "source_revision": "task-v1"}, session_id="session-coordinator", operation_class="notebook"))
    for index, (note, path) in enumerate(zip(notes, source_paths), 1):
        _append_kernel_event(engagement, base_event(event_id=f"event-initial-{case}-{index}", engagement_id=engagement_id, recorded_at=f"2026-01-01T00:00:0{index + 1}Z", actor_role="orchestrator", actor_id=f"worker-{index}", event_type="observation.recorded", rationale=note["observation"], payload={"entity_id": f"initial-{case}-{index}", "entity_type": "independent_initial", "status": "recorded", "task_id": task_id, "source_revision": path.name}, session_id=f"session-worker-{index}", operation_class="notebook"))
    empty_projection = compile_hunter_notices(read_ledger(engagement, "event"), task_id=task_id)
    notices = []
    actions = [{"ordinal": 3, "arm": "board", "action": "empty_read", "notice_count": len(empty_projection["files"])}]
    for index, (note, path) in enumerate(zip(notes, source_paths), 1):
        notice = {"notice_version": 1, "notice_id": f"{case}-notice-{index}", "task_id": task_id, "principal_id": f"worker-{index}", "source_event_ref": f"event-initial-{case}-{index}", "source_revision": path.name, "observation": note["observation"], "applicability": f"Only {task_id}.", "uncertainty": note["uncertainty"], "predecessor_event_ref": None}
        event = post_notice(engagement, notice, recorded_at=f"2026-01-01T00:00:0{index + 3}Z")
        notices.append(notice)
        actions.append({"ordinal": index + 3, "arm": "board", "action": "post", "event_id": event["event_id"], "notice": notice})
    return engagement, notices, actions


def board_packet(engagement: pathlib.Path, task_id: str) -> tuple[str, int]:
    sys.path.insert(0, str(ROOT / "tools"))
    from engagement_state import read_ledger
    from task_notice import compile_hunter_notices
    compiled = compile_hunter_notices(read_ledger(engagement, "event"), task_id=task_id)
    packet = "\n".join(data.decode() for _, data in sorted(compiled["files"].items()))
    (engagement / "compiled-notices.json").write_text(json.dumps({"commitment": compiled["commitment"], "brief": compiled["brief"]}, indent=2, sort_keys=True) + "\n")
    return packet, len(compiled["files"])


def add_late_correction(engagement: pathlib.Path, predecessor_event_ref: str) -> dict[str, Any]:
    sys.path.insert(0, str(ROOT / "tools"))
    from engagement_state import _append_kernel_event, base_event, read_ledger
    from task_board import post_notice
    case, task_id = "late", "task-late"
    observation = "binding-v2 corrects binding-v1: 10:30 in Room Pine; 10 spaces and materials-v1 guidance are unchanged."
    _append_kernel_event(engagement, base_event(event_id="event-correction-late-1", engagement_id=engagement.name, recorded_at="2026-01-01T00:00:06Z", actor_role="orchestrator", actor_id="worker-1", event_type="observation.recorded", rationale="Forward the released correction exactly once.", payload={"entity_id": "correction-late-1", "entity_type": "correction_observation", "status": "recorded", "task_id": task_id, "source_revision": "binding-v2.md"}, session_id="session-worker-1", operation_class="notebook"))
    notice = {"notice_version": 1, "notice_id": "late-notice-correction", "task_id": task_id, "principal_id": "worker-1", "source_event_ref": "event-correction-late-1", "source_revision": "binding-v2.md", "observation": observation, "applicability": "Only task-late.", "uncertainty": "Primary correction source controls.", "predecessor_event_ref": predecessor_event_ref}
    event = post_notice(engagement, notice, recorded_at="2026-01-01T00:00:07Z")
    return {"event_id": event["event_id"], "notice": notice}


def main() -> None:
    import argparse
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
    brief = (ROOT / "docs/experiments/communication-v1/inputs/brief.md").read_text()
    finals: dict[tuple[str, str], str | None] = {}
    coordination: dict[str, Any] = {}
    late_drafts: dict[str, str | None] = {}

    for case in protocol["cases"]:
        case_id = case["case_id"]
        paths = [ROOT / path for path in case["sources"]]
        notes = []
        for index, path in enumerate(paths, 1):
            receipt = model_call(f"{case_id}-worker-{index}", f"{brief}\nYou are independent worker {index}. Read only the source below. Return only JSON with observation (max 220 characters, include filename and useful facts) and uncertainty (max 80 characters).\nFILE {path.name}:\n{path.read_text()}", args.output, config, budget)
            notes.append(require_note(receipt))

        serial_draft_receipt = model_call(f"{case_id}-serial-draft", f"{brief}\nCreate a concise initial draft using only these currently released sources. Cite filenames and retain unknowns.\n{source_block(paths)}", args.output, config, budget)
        serial_draft = serial_draft_receipt["output"]
        if case_id == "late":
            late_drafts["serial"] = serial_draft

        engagement, initial_notices, board_actions = initialize_board(args.output, case_id, notes, paths)
        task_id = "task-" + case_id
        initial_board_packet, initial_count = board_packet(engagement, task_id)
        direct_actions = [{"ordinal": 3, "arm": "direct", "action": "empty_receive", "notice_count": 0}]
        for index, notice in enumerate(initial_notices, 1):
            direct_actions.append({"ordinal": index + 3, "arm": "direct", "action": "send", "notice": notice})
        initial_direct_packet = "\n".join(canonical({"task_notice": notice}) for notice in initial_notices)

        correction_source = None
        final_board_packet, final_direct_packet = initial_board_packet, initial_direct_packet
        if case_id == "late":
            for arm, packet in (("direct", initial_direct_packet), ("board", initial_board_packet)):
                receipt = model_call(f"late-{arm}-draft", f"{brief}\nRelease ordinal 5: only the initial advisory packet below is available. Produce a concise pre-correction draft and cite the revisions present.\n{packet}", args.output, config, budget)
                late_drafts[arm] = receipt["output"]
            correction_source = (ROOT / case["correction"]).read_text()
            correction = add_late_correction(engagement, "event-task-notice-late-notice-1")
            board_actions.append({"ordinal": 7, "arm": "board", "action": "post_correction", **correction})
            final_board_packet, final_count = board_packet(engagement, task_id)
            final_direct_packet = initial_direct_packet + "\n" + canonical({"task_notice": correction["notice"]})
            direct_actions.append({"ordinal": 7, "arm": "direct", "action": "send_correction", "notice": correction["notice"]})
        else:
            final_count = initial_count

        current_serial_paths = paths + ([ROOT / case["correction"]] if "correction" in case else [])
        serial_final = model_call(f"{case_id}-serial-final", f"{brief}\nCURRENT RELEASED PRIMARY SOURCES:\n{source_block(current_serial_paths)}\nINITIAL DRAFT:\n{serial_draft}\nProduce the final attendee-facing note. Cite current revisions and retain unknowns.", args.output, config, budget)
        finals[(case_id, "serial")] = serial_final["output"]
        for arm, packet in (("direct", final_direct_packet), ("board", final_board_packet)):
            prior = f"\nPRE-CORRECTION DRAFT:\n{late_drafts[arm]}" if case_id == "late" else ""
            final = model_call(f"{case_id}-{arm}-final", f"{brief}\nYou receive advisory worker communications only. Treat later predecessor-linked notices as corrections.\nRECEIVED PACKET:\n{packet}{prior}\nProduce the final attendee-facing note. Cite revisions present in the packet and retain unknowns.", args.output, config, budget)
            finals[(case_id, arm)] = final["output"]
        board_actions.append({"ordinal": 8, "arm": "board", "action": "read_final", "notice_count": final_count})
        direct_actions.append({"ordinal": 8, "arm": "direct", "action": "receive_final", "notice_count": len(initial_notices) + (1 if case_id == "late" else 0)})
        coordination[case_id] = {"shared_worker_notes": notes, "direct_actions": direct_actions, "board_actions": board_actions, "serial_source_paths": [str(path.relative_to(ROOT)) for path in current_serial_paths], "direct_primary_sources": [], "board_primary_sources": [], "correction_source_released": correction_source}

    (args.output / "coordination.json").write_text(json.dumps(coordination, indent=2, sort_keys=True) + "\n")
    (args.output / "late-drafts.json").write_text(json.dumps(late_drafts, indent=2, sort_keys=True) + "\n")
    calibration_prompt = '''You are a blind document grader. Grade these explicit samples against REFERENCE: "Tuesday 14:00, Room Maple; lunch unknown."
SAMPLE correct: "Tuesday 14:00 in Room Maple; lunch is unspecified."
SAMPLE wrong: "Wednesday 15:00 in Room Oak; lunch is included."
SAMPLE ambiguous: "The event is in the listed room around the scheduled time."
Return only JSON mapping correct, wrong, ambiguous to one of correct|wrong|ambiguous.'''
    calibration = model_call("grader-calibration", calibration_prompt, args.output, config, budget)
    expected_calibration = {"correct": "correct", "wrong": "wrong", "ambiguous": "ambiguous"}
    try:
        observed_calibration = parse_json(calibration["output"] or "")
    except Exception as exc:
        observed_calibration = {"parse_error": f"{type(exc).__name__}: {exc}"}
    calibration_passed = observed_calibration == expected_calibration
    (args.output / "grader-calibration.json").write_text(json.dumps({"expected": expected_calibration, "observed": observed_calibration, "passed": calibration_passed}, indent=2, sort_keys=True) + "\n")
    grades = {}
    mappings = {}
    if calibration_passed:
        orders = {"complete": ["board", "serial", "direct"], "complementary": ["direct", "board", "serial"], "late": ["serial", "direct", "board"]}
        for case in protocol["cases"]:
            case_id = case["case_id"]
            order = orders[case_id]
            labels = {chr(65 + index): arm for index, arm in enumerate(order)}
            mappings[case_id] = labels
            anonymized = {label: finals[(case_id, arm)] for label, arm in labels.items()}
            reference = (ROOT / case["reference"]).read_text()
            prompt = f'''Blindly grade the three final notes. You do not know their communication treatments. Use only this current-case reference and outputs.
REFERENCE:\n{reference}\nOUTPUTS:\n{json.dumps(anonymized, sort_keys=True)}
Return only JSON mapping A/B/C to objects with: decision (correct|wrong|ambiguous), correct_facts (array), missing_facts (array), stale_revision (boolean), unsupported_claims (array), used_released_information (boolean), useful_correction (boolean or null), rationale.'''
            receipt = model_call(f"grader-{case_id}", prompt, args.output, config, budget)
            try:
                grades[case_id] = parse_json(receipt["output"] or "")
            except Exception as exc:
                grades[case_id] = {"parse_error": f"{type(exc).__name__}: {exc}"}
    else:
        grades["qualification"] = "stopped_after_failed_calibration"
    (args.output / "private-arm-mapping.json").write_text(json.dumps(mappings, indent=2, sort_keys=True) + "\n")
    (args.output / "grades.json").write_text(json.dumps(grades, indent=2, sort_keys=True) + "\n")
    verify_manifest()
    result = {"manifest_id": manifest["manifest_id"], "candidate_assignments": 9, "calibration_passed": calibration_passed, "usage": {"calls": budget.calls, "input_tokens": budget.input_tokens, "output_tokens": budget.output_tokens, "elapsed_seconds": time.monotonic() - budget.started}, "finals": {f"{case}:{arm}": value for (case, arm), value in finals.items()}, "notice_receipt": {case: {"direct": data["direct_actions"][-1]["notice_count"], "board": data["board_actions"][-1]["notice_count"]} for case, data in coordination.items()}, "no_favorable_reruns": True}
    (args.output / "results.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
