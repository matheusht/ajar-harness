#!/usr/bin/env python3
"""Check the saved synthetic hunter pair without trusting the test's verdict."""

import argparse
import hashlib
import json
from pathlib import Path


def digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.output.resolve()
    result = json.loads((root / "result.json").read_bytes())
    attempts = [json.loads(line) for line in (root / "attempts.jsonl").read_bytes().splitlines() if line]
    selected = [row for row in attempts if row.get("attempt_id") in result["attempt_ids"]]
    sources = [("primary", (root / "primary.txt").read_bytes()), ("control", (root / "control.txt").read_bytes())]
    manifest_raw = (root / "view-manifest.json").read_bytes()
    manifest = json.loads(manifest_raw)
    source_rows = {row["target_relative_path"]: row["digest"] for row in manifest["target_inputs"]}
    comparison = manifest["hypothesis"]["source_comparison"]
    chain_ok = all(
        row["sequence"] == index + 1
        and row["previous_hash"] == (attempts[index - 1]["record_hash"] if index else None)
        and digest(canonical({key: value for key, value in row.items() if key != "record_hash"})) == row["record_hash"]
        for index, row in enumerate(attempts)
    )
    checks = {
        "ledger_hash_chain": chain_ok,
        "two_distinct_attempts": len(selected) == 2 and len(set(result["attempt_ids"])) == 2,
        "primary_and_held_control": len(selected) == 2 and [row["kind"] for row in selected] == ["primary", "negative_control"] and selected[1]["assessment"] == "held" and selected[1]["control_of"] == [selected[0]["attempt_id"]],
        "parent_observed": len(selected) == 2 and all(row["observation"]["source"] == "broker" and "Parent must replace" not in row["observation"]["statement"] for row in selected),
        "parent_owned_action": len(selected) == 2 and all(row["action_summary"] == f"Compared allowlisted source {path}." for row, path in zip(selected, (comparison["primary_path"], comparison["control_path"]))),
        "raw_output_commitments": len(selected) == 2 and all(digest(raw) in selected[index]["observation"]["statement"] and digest(raw) == result["source_hashes"][index] for index, (_name, raw) in enumerate(sources)),
        "exact_view_sources": source_rows.get(comparison["primary_path"]) == digest(sources[0][1]) and source_rows.get(comparison["control_path"]) == digest(sources[1][1]) and len(source_rows) == 2,
        "matched_signal": comparison["signal"].encode("ascii") in sources[0][1] and comparison["signal"].encode("ascii") not in sources[1][1],
        "saved_manifest": digest(manifest_raw) == result["manifest_digest"] and digest(canonical({key: value for key, value in manifest.items() if key != "view_digest"})) == manifest["view_digest"] and manifest.get("action", {}).get("action_id") == "record_hunter_pair",
        "runtime_boundary": result["provider"] == "owned fake provider" and "@sha256:" in result["docker_image"] and bool(result["docker_python"]),
        "open_adjudication": "hypothesis_ran_unadjudicated" in result["queue_classes"],
    }
    if "crash_exit" in result:
        restart = json.loads((root / "restart-result.json").read_bytes())
        state = json.loads((root / "state.snapshot.json").read_bytes())
        events = [json.loads(line) for line in (root / "events.jsonl").read_bytes().splitlines() if line]
        checks.update({
            "real_parent_crash": result["crash_exit"] == 77,
            "restart_observed_open_queue": restart["status"] == result["restart_status"] == "interrupted_unrecorded" and "hypothesis_ran_unadjudicated" in result["queue_classes"],
            "restart_did_not_duplicate_attempts": (root / "attempts-before-restart.jsonl").read_bytes() == (root / "attempts.jsonl").read_bytes(),
            "signed_scope_bound": bool(events) and events[0]["event_type"] == "scope.attested" and events[0]["payload"]["scope_hash"] == digest((root / "scope.md").read_bytes()),
            "restart_state_bound": digest(canonical(state)) == restart["final_state_hash"] and "hypothesis_ran_unadjudicated" in {row["class"] for row in state["work_queue"]},
        })
    print(json.dumps({"valid": all(checks.values()), "checks": checks, "source_head": result["source_head"]}, sort_keys=True))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
