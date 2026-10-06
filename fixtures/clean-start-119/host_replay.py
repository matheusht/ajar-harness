#!/usr/bin/env python3
"""Run the existing host driver with a source-reading fake provider."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from engagement_state import reduce_engagement  # noqa: E402
from work_queue_driver import DriverBudget, DriverError, run_driver  # noqa: E402
import claude_work_session  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    workspace = args.workspace.resolve(strict=True)
    engagement = workspace / "engagements" / "clean-start"
    output = args.output.absolute()
    output.mkdir(parents=True, exist_ok=True)
    fake_cli = output / "fake-cli"
    researcher = Path(__file__).with_name("fake_researcher.py")
    fake_cli.write_text(f"#!{sys.executable}\nimport runpy\nrunpy.run_path({str(researcher)!r}, run_name='__main__')\n")
    fake_cli.chmod(0o700)
    original_summary = claude_work_session._summary_from_output
    capture_index = 0

    def capture_summary(raw: bytes) -> tuple[bool, bool | None, float | None]:
        nonlocal capture_index
        capture_index += 1
        (output / f"fake-session-{capture_index:02d}.json").write_bytes(raw)
        return original_summary(raw)

    claude_work_session._summary_from_output = capture_summary

    def done() -> bool:
        snapshot = engagement / "state.snapshot.json"
        if not snapshot.exists():
            return False
        try:
            return json.loads(snapshot.read_text())["intake"]["status"] == "hypothesized"
        except (KeyError, TypeError, ValueError):
            return False

    result: dict[str, object]
    try:
        driver = run_driver(
            workspace=workspace,
            engagement=engagement,
            executable=fake_cli,
            model="claude-clean-start-fake-20261006",
            reviewer_model="claude-clean-start-reviewer-fake-20261006",
            budget=DriverBudget(3, 120.0, 30.0, None),
            read_only_inputs=tuple(dict.fromkeys((Path(sys.prefix), Path(sys.base_prefix)))),
            stop_requested=done,
        )
        state = reduce_engagement(engagement)
        events = [json.loads(line) for line in (engagement / "events.jsonl").read_text().splitlines()]
        observation = next((event for event in events if event["event_type"] == "observation.recorded" and event["payload"].get("entity_type") == "source_intake"), None)
        source_sentence = (workspace / "inert-source.txt").read_text().strip().split(".", 1)[0]
        result = {
            "status": driver["status"],
            "sessions_started": driver["sessions_started"],
            "action_ids": [entry["action_id"] for entry in driver["history"]],
            "runtimes": [entry["runtime"] for entry in driver["history"]],
            "event_types": [event["event_type"] for event in events],
            "source_read_visible_in_observation": bool(observation and source_sentence in observation["rationale"]),
            "intake": state["intake"],
        }
        result["passed"] = (
            result["sessions_started"] == 3
            and result["action_ids"] == ["record_source_observation", "route_source_observation", "create_source_hypothesis"]
            and result["source_read_visible_in_observation"] is True
            and state["intake"]["status"] == "hypothesized"
            and state["intake"]["denominator"] == 1
            and state["hypotheses"].get("hypothesis-host-source-route", {}).get("next_experiment") is not None
        )
    except (DriverError, OSError, ValueError, KeyError) as exc:
        result = {"passed": False, "error": getattr(exc, "code", type(exc).__name__), "detail": str(exc)}
    (output / "result.json").write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
