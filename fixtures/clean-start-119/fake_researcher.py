#!/usr/bin/env python3
"""Deterministic fake model for the host driver replay; it reads the pinned source."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    prompt = json.loads(sys.argv[-1])
    action = prompt["item"]["next_action"]
    intake = prompt["state_binding"]["intake"]
    engagement = Path(os.environ["HARNESS_ACTIVE_ENGAGEMENT"])
    source = engagement.parent.parent / intake["source_path"]
    data = source.read_bytes()
    source_hash = "sha256:" + hashlib.sha256(data).hexdigest()
    if source_hash != intake["source_hash"] or len(data) != intake["source_size"]:
        return 80
    source_text = data.decode("utf-8")
    source_sentence = source_text.strip().split(".", 1)[0]
    candidate_signal = all(marker in source_text.lower() for marker in ("legacy route", "new route", "owner guard"))

    argv = list(action["local_invocation"]["argv"])
    sys.path.insert(0, str(Path(argv[1]).parent))
    from engagement_records import canonical_json_bytes  # noqa: E402
    from engagement_state import base_event, utc_now  # noqa: E402

    uid, sid = os.getuid(), os.getsid(0)
    action_id = action["action_id"]
    common = {
        "engagement_id": engagement.name,
        "recorded_at": utc_now(),
        "actor_role": "broker",
        "actor_id": f"local-uid-{uid}:broker",
        "session_id": f"session-posix-{uid}-{sid}",
        "operation_class": "notebook",
        "model": sys.argv[sys.argv.index("--model") + 1],
        "provider": "deterministic-host-fixture",
    }
    # The admission pins the active environment even before the intake has an observation.
    scope_hash = next(row["value"] for row in action["admission"]["constraints"] if row["path"] == ["payload", "scope_hash"])
    environment_ref = next(row["value"] for row in action["admission"]["constraints"] if row["path"] == ["payload", "environment_ref"])
    if action_id == "record_source_observation":
        event = base_event(
            event_id="event-host-source-observation", event_type="observation.recorded",
            rationale=f"Read signed source: {source_sentence}.",
            payload={"entity_id": "host-source-observation", "entity_type": "source_intake", "status": "recorded", "source_path": intake["source_path"], "source_hash": source_hash, "source_size": len(data), "scope_hash": scope_hash, "environment_ref": environment_ref},
            **common,
        )
        placeholder = "<source-observation-event-json>"
    elif action_id == "route_source_observation":
        if candidate_signal:
            strength, cards, status = "weak", ["pattern.legacy-route-differential"], "assessed"
        else:
            strength, cards, status = "none", [], "deferred"
        event = base_event(
            event_id="event-host-source-routing", event_type="routing.assessed",
            rationale="The inspected source names a guard difference; reachability remains unverified." if candidate_signal else "No allowed card is justified by the inspected source.",
            payload={"entity_id": "host-source-routing", "source_observation_ref": intake["observation_ref"], "activation_strength": strength, "card_ids": cards, "status": status, "source_path": intake["source_path"], "source_hash": source_hash, "source_size": len(data), "scope_hash": scope_hash, "environment_ref": environment_ref},
            entity_refs=[intake["observation_ref"]], **common,
        )
        placeholder = "<source-routing-event-json>"
    elif action_id == "create_source_hypothesis" and candidate_signal:
        hypothesis_id = "hypothesis-host-source-route"
        event = base_event(
            event_id="event-host-source-hypothesis", event_type="hypothesis.created",
            rationale="A source-derived guard difference justifies one local fixture experiment, not a finding.",
            payload={"hypothesis_id": hypothesis_id, "origin_type": "target_model", "origin_ref": intake["observation_ref"], "routing_review_ref": intake["routing_ref"], "source_hash": source_hash, "scope_hash": scope_hash, "environment_ref": environment_ref, "hypothesis_statement": f"The inspected statement '{source_sentence}' may indicate a missing guard on the legacy route.", "suspected_invariant": "Both route variants should apply the same owner guard.", "trust_boundary": "caller owner id to route authorization guard", "attacker_path": ["inert fixture request", "legacy route", "owner guard"], "impact_ceiling": "local inert fixture only", "bounded_space": "One benign request compared across two local route variants.", "lens_ids": ["authorization"], "card_ids": ["pattern.legacy-route-differential"], "expected_confirming_evidence": [{"evidence_type": "trace", "description": "local traces show different guard decisions for the same benign request", "required": True}], "decisive_falsifiers": ["both variants call the same guard before reading"], "cost_estimate": {"wall_seconds": 0, "model_seconds": 0, "tool_seconds": 0, "target_calls": 0, "model_calls": 0, "human_review_seconds": 0}, "constraints": ["no live target", "no impact demonstration"], "next_experiment": "Run one inert same-actor route comparison and capture guard traces.", "completion_criteria": ["both decisions and guard traces are recorded"], "status": "queued"},
            entity_refs=[intake["observation_ref"], intake["routing_ref"]],
            state_changes=[{"dimension": "search", "entity_id": hypothesis_id, "previous": None, "current": "queued"}],
            **common,
        )
        placeholder = "<source-hypothesis-event-json>"
    else:
        return 81

    proposal_path = Path(os.environ["HARNESS_DRIVER_SCRATCH"]) / "proposal.json"
    proposal_path.write_bytes(canonical_json_bytes(event))
    command = [str(proposal_path) if value == placeholder else value for value in argv]
    result = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if result.returncode != 0:
        print(json.dumps({"type": "result", "is_error": True, "action_id": action_id, "command_result": result.stdout.decode("utf-8", "replace")[:400]}))
        return result.returncode
    print(json.dumps({"type": "result", "is_error": False, "total_cost_usd": 0.0}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
