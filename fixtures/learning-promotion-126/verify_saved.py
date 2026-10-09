#!/usr/bin/env python3
"""Verify saved portable learning against its exact synthetic source."""

import argparse
import hashlib
import json
from pathlib import Path


def digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


def order(rows: list[dict], entries: list[dict]) -> list[str]:
    scored = []
    for row in rows:
        delta = sum((1 if entry["kind"] == "winner" else -1)
                    for entry in entries if row["route"] in entry.get("cards", []))
        scored.append((row["priority"] + max(-1, min(1, delta)), row["route"]))
    return [route for _, route in sorted(scored, key=lambda item: -item[0])]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    root = parser.parse_args().output.resolve()
    source = root / "source"
    result = json.loads((root / "result.json").read_bytes())
    kb_bytes = (root / "kb.jsonl").read_bytes()
    entries = [json.loads(row) for row in kb_bytes.splitlines() if row]
    winner, loser = entries
    finding = json.loads((source / "findings/F-canonical-public/rev-1.json").read_bytes())
    state = json.loads((source / "state.snapshot.json").read_bytes())
    attempts = {row["attempt_id"]: row for row in map(json.loads, (source / "attempts.jsonl").read_bytes().splitlines())}
    review_bytes = (source / "reviews/review-proof-complete.json").read_bytes()
    replay = attempts["attempt-canonical-replay"]
    held = attempts["attempt-canonical-negative"]
    route = json.loads((root / "route.json").read_bytes())
    held_route = json.loads((root / "held-route.json").read_bytes())
    expected_evidence = [f"finding-r1:{digest(canonical(finding))}", f"replay:{replay['record_hash']}", f"review:{digest(review_bytes)}"]
    checks = {
        "signed_source": "- Signed: [x]" in (source / "scope.md").read_text() and "decision-0006-v2" in (source / "scope.md").read_text(),
        "exact_current_revision": finding["revision"] == 1 and state["findings"][finding["finding_id"]]["digest"] == digest(canonical(finding)) and state["findings"][finding["finding_id"]]["status"] == "confirmed",
        "replay_and_held_control": replay["kind"] == "replay" and replay["assessment"] == "suspected_signal" and held["kind"] == "negative_control" and held["assessment"] == "no_signal",
        "portable_provenance": all(entry["evidence"] == expected_evidence for entry in entries) and loser["control"]["evidence"] == [f"held-control:{held['record_hash']}"],
        "scrubbed": all(name.encode() not in kb_bytes for name in [state["engagement_id"], finding["finding_id"], replay["attempt_id"]]) and b"password=" not in kb_bytes and b"https://" not in kb_bytes,
        "winner_changes_future_order": order(route["base"], []) != order(route["base"], [winner]) and order(route["base"], entries) == order(route["base"], [winner]),
        "loser_changes_future_order": order(held_route["base"], [winner]) != order(held_route["base"], entries),
        "past_verdict_unchanged": state["claim_adjudications"][finding["finding_id"]]["status"] == "confirmed",
        "denials_without_mutation": len(entries) == 2 and set(result["denials"]) == {"unproved", "stale", "wrong-replay", "source-identifier", "secret", "irrelevant", "overbroad-family", "unproved-control", "unsupported-loser"},
        "exact_retry": "exact retry" in result["replayed"],
        "local_only": result["provider"] == "none" and result["target_contact"] is False,
    }
    print(json.dumps({"valid": all(checks.values()), "checks": checks, "source_head": result["source_head"]}, sort_keys=True))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
