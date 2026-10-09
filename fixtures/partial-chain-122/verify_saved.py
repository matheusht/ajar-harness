#!/usr/bin/env python3
"""Verify a saved synthetic partial-chain run without trusting its test verdict."""

import argparse
import hashlib
import json
from pathlib import Path


def canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    root = parser.parse_args().output.resolve()
    result = json.loads((root / "result.json").read_bytes())
    events_raw = (root / "events.jsonl").read_bytes()
    events = [json.loads(line) for line in events_raw.splitlines() if line]
    attempts = [json.loads(line) for line in (root / "attempts.jsonl").read_bytes().splitlines() if line]
    state = json.loads((root / "state.snapshot.json").read_bytes())
    projection = json.loads((root / "partial-chain.json").read_bytes())
    chain_events = [row for row in events if row["event_type"] == "partial_chain.recorded"]
    chain = state["partial_chains"][result["finding_id"]]
    checks = {
        "signed_scope": "- Signed: [x]" in (root / "scope.md").read_text(encoding="utf-8"),
        "event_hash_chain": all(row["sequence"] == index + 1 and row["previous_hash"] == (events[index - 1]["record_hash"] if index else None) and digest(canonical({key: value for key, value in row.items() if key != "record_hash"})) == row["record_hash"] for index, row in enumerate(events)),
        "attempt_hash_chain": all(row["sequence"] == index + 1 and row["previous_hash"] == (attempts[index - 1]["record_hash"] if index else None) and digest(canonical({key: value for key, value in row.items() if key != "record_hash"})) == row["record_hash"] for index, row in enumerate(attempts)),
        "argued_then_refuted": [row["event_id"] for row in chain_events] == [result["argued_event_ref"], result["refuted_event_ref"]] and chain_events[0]["payload"]["stages"][1]["state"] == "argued" and chain_events[1]["payload"]["stages"][1]["state"] == "refuted",
        "proven_base_evidence": len(attempts) == 1 and attempts[0]["attempt_id"] == chain["stages"][0]["evidence_refs"][0] and attempts[0]["kind"] == "primary",
        "projection_matches_event": projection == chain == {"event_ref": chain_events[-1]["event_id"], "event_sequence": chain_events[-1]["sequence"], **chain_events[-1]["payload"]},
        "route_closed": state["hypotheses"][result["hypothesis_id"]]["status"] == "closed" and not any(item["entity"]["id"] == result["hypothesis_id"] for item in state["work_queue"]),
        "invalid_inputs_absent": all(row["event_id"] not in {"event-chain-unsupported", "event-chain-secret"} for row in events) and b"synthetic-password-value" not in events_raw,
        "local_only": result["provider"] == "none" and result["target_contact"] is False,
    }
    print(json.dumps({"valid": all(checks.values()), "checks": checks, "source_head": result["source_head"]}, sort_keys=True))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
