#!/usr/bin/env python3
"""Exercise frozen recovery mechanics with the pinned SDK ScriptedModel."""

from __future__ import annotations

import asyncio
import hashlib
import json
import pathlib
import subprocess
import sys
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = ROOT / "docs/experiments/recovery-v3"
OUT_DEFAULT = pathlib.Path("/tmp/redteam-pilots/recovery-v3")


def sha_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def sha(path: pathlib.Path) -> str:
    return sha_bytes(path.read_bytes())


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


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


def inspect_baseline(protocol: dict[str, Any]) -> dict[str, Any]:
    pin = protocol["baseline"]["pin"]
    observations = []
    terms = ["RunState", "resume", "restore", "checkpoint", "cancel("]
    for relative, expected in protocol["baseline"]["source_files"].items():
        result = subprocess.run(["git", "show", f"{pin}:{relative}"], cwd=ROOT, capture_output=True, check=True)
        observed = sha_bytes(result.stdout)
        if observed != expected:
            raise RuntimeError(f"baseline source mismatch: {relative}")
        text = result.stdout.decode()
        matches = [term for term in terms if term in text]
        observations.append({"path": relative, "sha256": observed, "recovery_api_terms_found": matches})
    return {
        "status": "unsupported_not_executed",
        "invoked_recovery_interfaces": [],
        "received_arguments": None,
        "source_inspection": observations,
        "reason": "The pinned baseline files expose no native serialized pause/restore or late pending-input interface. A prose occurrence of 'pause' is not such an interface.",
    }


def snapshot_call(call: Any) -> dict[str, Any]:
    def clean(value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, list | tuple):
            return [clean(item) for item in value]
        if isinstance(value, dict):
            return {str(key): clean(item) for key, item in value.items()}
        if hasattr(value, "model_dump"):
            return clean(value.model_dump())
        return repr(value)

    return clean({"input": call.input, "tools": [getattr(tool, "name", repr(tool)) for tool in call.tools]})


def contains_type(value: Any, wanted: str) -> bool:
    if isinstance(value, dict):
        return value.get("type") == wanted or any(contains_type(item, wanted) for item in value.values())
    if isinstance(value, list):
        return any(contains_type(item, wanted) for item in value)
    return False


async def run_sdk(out: pathlib.Path) -> list[dict[str, Any]]:
    sdk = pathlib.Path("/tmp/redteam-recovery-sdk")
    sys.path.insert(0, str(sdk / "src"))
    from agents import Agent, RunConfig, Runner, RunState, function_tool
    from agents.testing import ScriptedModel
    from openai.types.responses import ResponseFunctionToolCall, ResponseOutputMessage, ResponseOutputText

    def call(name: str, arguments: dict[str, str], call_id: str):
        return ResponseFunctionToolCall(id="function-" + call_id, call_id=call_id, type="function_call", name=name, arguments=json.dumps(arguments))

    def message(text: str):
        return ResponseOutputMessage(id="message", type="message", role="assistant", content=[ResponseOutputText(text=text, type="output_text", annotations=[], logprobs=[])], status="completed")

    config = RunConfig(tracing_disabled=True)
    rows = []

    # Late input is staged only after the completed v1 tool turn is softly cancelled.
    late_effects: list[str] = []

    @function_tool
    def record_revision(revision: str) -> str:
        late_effects.append(revision)
        return "recorded:" + revision

    late_model = ScriptedModel([[call("record_revision", {"revision": "workshop-v1"}, "late-v1")], [message("late correction admitted")]], emit_traces=False)
    late_agent = Agent(name="late-correction", model=late_model, tools=[record_revision])
    streamed = Runner.run_streamed(late_agent, "Use workshop-v1; wait for later updates.", run_config=config)
    late_events = []
    async for event in streamed.stream_events():
        late_events.append({"type": event.type, "name": getattr(event, "name", None)})
        if event.type == "run_item_stream_event" and event.name == "tool_output":
            streamed.cancel(mode="after_turn")
    late_state = streamed.to_state()
    late_state.add_input("Correction c1: replace workshop-v1 with workshop-v2.")
    late_json = late_state.to_json()
    (out / "late-correction-state.json").write_text(json.dumps(late_json, indent=2, sort_keys=True, default=str) + "\n")
    late_restored = await RunState.from_json(late_agent, late_json)
    pending_before = late_restored.pending_input
    late_done = await Runner.run(late_agent, late_restored, run_config=config)
    late_last_input = snapshot_call(late_model.calls[-1])["input"]
    correction_count = canonical(late_last_input).count("Correction c1: replace workshop-v1 with workshop-v2.")
    rows.append({
        "case": "late-correction",
        "arm": "sdk",
        "mechanism": "soft_cancel_after_turn_plus_pending_input",
        "stream_events": late_events,
        "state_sha256": sha(out / "late-correction-state.json"),
        "pending_input_before_resume": pending_before,
        "next_model_input": late_last_input,
        "correction_occurrences_in_next_input": correction_count,
        "effects": late_effects,
        "final_output": late_done.final_output,
        "passed": late_effects == ["workshop-v1"] and correction_count == 1,
    })

    # Cooperative pause completes phase one, leaves one scripted turn, serializes, and resumes.
    pause_effects: list[str] = []

    @function_tool
    def complete_phase(phase: str) -> str:
        pause_effects.append(phase)
        return "completed:" + phase

    pause_model = ScriptedModel([[call("complete_phase", {"phase": "phase-one"}, "pause-one")], [message("phase two completed after resume")]], emit_traces=False)
    pause_agent = Agent(name="cooperative-pause", model=pause_model, tools=[complete_phase])
    pause_stream = Runner.run_streamed(pause_agent, "Complete phase one, then phase two.", run_config=config)
    pause_events = []
    async for event in pause_stream.stream_events():
        pause_events.append({"type": event.type, "name": getattr(event, "name", None)})
        if event.type == "run_item_stream_event" and event.name == "tool_output":
            pause_stream.cancel(mode="after_turn")
    remaining_at_pause = pause_model.remaining_steps
    pause_json = pause_stream.to_state().to_json()
    (out / "cooperative-pause-state.json").write_text(json.dumps(pause_json, indent=2, sort_keys=True, default=str) + "\n")
    pause_restored = await RunState.from_json(pause_agent, pause_json)
    pause_done = await Runner.run(pause_agent, pause_restored, run_config=config)
    rows.append({
        "case": "cooperative-pause",
        "arm": "sdk",
        "mechanism": "soft_cancel_after_turn",
        "stream_events": pause_events,
        "state_sha256": sha(out / "cooperative-pause-state.json"),
        "unfinished_model_steps_at_pause": remaining_at_pause,
        "effects_before_and_after_resume": pause_effects,
        "next_model_input": snapshot_call(pause_model.calls[-1])["input"],
        "final_output": pause_done.final_output,
        "passed": remaining_at_pause == 1 and pause_effects == ["phase-one"],
    })

    # Lost receipt: snapshot before effect, fail after append and before return, then replay snapshot.
    class LostBeforeReceipt(BaseException):
        pass

    effect_path = out / "lost-receipt-effects.jsonl"
    attempts = 0

    @function_tool(needs_approval=True)
    def write_note(payload: str) -> str:
        nonlocal attempts
        attempts += 1
        with effect_path.open("a") as handle:
            handle.write(json.dumps({"attempt": attempts, "payload": payload}, sort_keys=True) + "\n")
        if attempts == 1:
            raise LostBeforeReceipt("local effect completed before tool receipt")
        return "receipt:" + payload

    lost_model = ScriptedModel([[call("write_note", {"payload": "attendee-note-v2"}, "lost-write")], [message("receipt observed after retry")]], emit_traces=False)
    lost_agent = Agent(name="lost-receipt", model=lost_model, tools=[write_note])
    interrupted = await Runner.run(lost_agent, "Write attendee-note-v2.", run_config=config)
    pre_effect_json = interrupted.to_state().to_json()
    (out / "lost-receipt-pre-effect-state.json").write_text(json.dumps(pre_effect_json, indent=2, sort_keys=True, default=str) + "\n")
    first_state = await RunState.from_json(lost_agent, pre_effect_json)
    first_state.approve(first_state.get_interruptions()[0])
    first_error = None
    try:
        await Runner.run(lost_agent, first_state, run_config=config)
    except BaseException as exc:
        first_error = f"{type(exc).__name__}: {exc}"
    effects_after_failure = effect_path.read_text().splitlines()
    retry_state = await RunState.from_json(lost_agent, pre_effect_json)
    retry_state.approve(retry_state.get_interruptions()[0])
    retried = await Runner.run(lost_agent, retry_state, run_config=config)
    effects_after_retry = effect_path.read_text().splitlines()
    retry_input = snapshot_call(lost_model.calls[-1])["input"]
    rows.append({
        "case": "lost-receipt",
        "arm": "sdk",
        "mechanism": "approved_pre_effect_snapshot_replay",
        "pre_effect_state_sha256": sha(out / "lost-receipt-pre-effect-state.json"),
        "receipt_visible_in_pre_effect_state": contains_type(pre_effect_json, "function_call_output"),
        "first_attempt_error": first_error,
        "effects_after_failure": effects_after_failure,
        "effects_after_retry": effects_after_retry,
        "retry_next_model_input": retry_input,
        "receipt_visible_after_retry": contains_type(retry_input, "function_call_output"),
        "exactly_once_external_effects": False,
        "final_output": retried.final_output,
        "passed": first_error is not None and len(effects_after_failure) == 1 and len(effects_after_retry) == 2 and contains_type(retry_input, "function_call_output"),
    })
    return rows


async def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=pathlib.Path, default=OUT_DEFAULT)
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
    sdk = pathlib.Path(protocol["sdk"]["checkout"])
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=sdk, text=True, capture_output=True, check=True).stdout.strip()
    if commit != protocol["sdk"]["commit"] or sha(sdk / "uv.lock") != protocol["sdk"]["lock_sha256"]:
        raise SystemExit("SDK pin or lock mismatch")
    baseline = inspect_baseline(protocol)
    rows = []
    for case in protocol["cases"]:
        rows.append({"case": case, "arm": "baseline", **baseline})
    rows.extend(await run_sdk(args.output))
    verify_manifest()
    result = {
        "manifest_id": manifest["manifest_id"],
        "sdk_commit": commit,
        "trace_export": False,
        "model_calls": 0,
        "rows": rows,
        "all_sdk_scenarios_passed": all(row["passed"] for row in rows if row["arm"] == "sdk"),
    }
    (args.output / "results.json").write_text(json.dumps(result, indent=2, sort_keys=True, default=str) + "\n")


if __name__ == "__main__":
    asyncio.run(main())
