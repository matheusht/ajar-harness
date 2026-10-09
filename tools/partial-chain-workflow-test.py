#!/usr/bin/env python3
"""Signed synthetic partial-chain save, restart, and queue acceptance."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from engagement_records import RecordError, canonical_json_bytes, sha256_file
from engagement_state import append_attempt, append_event, base_event, initialize_engagement, read_ledger, reduce_engagement
from environment_preflight import _collect_legacy_preflight as collect_preflight


ROOT = Path(__file__).resolve().parents[1]
SCOPE = """# Scope - partial-chain fixture
## Surfaces in scope
- One owned local synthetic source.
## Benign safe-objective set
- Record an incomplete local chain and its next question.
## Escalation ceiling
- Local records only.
## Impact-demo authorization
- impact_demo_authorized: `no`
- zone2_authorized_categories: `none`
- zone2_escalation_ceiling: `none`
- zone2_containment: `none`
## Accounts / fixtures
- No accounts.
## Independent reviewer identity
- Reviewer allowed signers SHA256: sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
## Authorization
- Operator allowed signers SHA256: sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
- Operator: operator-partial-fixture
- Date: 2026-10-09
- Signed: [x]
- Record kernel: `decision-0006-v2`
"""
ZERO_COST = {"wall_seconds": 0, "model_seconds": 0, "tool_seconds": 0, "target_calls": 0, "model_calls": 0, "input_tokens": None, "output_tokens": None, "cost_usd": None, "human_review_seconds": 0}


def cli(workspace: Path, *args: str) -> dict:
    result = subprocess.run([sys.executable, str(ROOT / "tools/run-engagement.py"), *args], cwd=workspace, text=True, capture_output=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout)


def denied(workspace: Path, engagement: Path, path: Path, proposal: dict, expected_code: str) -> None:
    before = (engagement / "events.jsonl").read_bytes()
    path.write_bytes(canonical_json_bytes(proposal))
    result = subprocess.run([sys.executable, str(ROOT / "tools/run-engagement.py"), "append-event", "--engagement", str(engagement), "--file", str(path)], cwd=workspace, text=True, capture_output=True, check=False)
    assert result.returncode != 0 and json.loads(result.stdout)["error"]["code"] == expected_code, result.stdout + result.stderr
    assert (engagement / "events.jsonl").read_bytes() == before


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="partial-chain-122-") as temporary:
        root = Path(temporary)
        workspace = root / "target"
        engagement = workspace / "engagements" / "partial-chain"
        engagement.mkdir(parents=True)
        (engagement / "scope.md").write_text(SCOPE, encoding="utf-8")
        initialize_engagement(engagement, "2026-10-09T12:00:00Z")
        target = workspace / "src" / "owned.txt"
        target.parent.mkdir()
        target.write_text("benign base-effect marker\n", encoding="utf-8")
        collect_preflight(engagement, preflight_id="preflight-chain", mode="package", target=target,
                          expected_identity=sha256_file(target), runtime=Path(sys.executable).resolve(),
                          reproduction_argv=[str(Path(sys.executable).resolve()), "-c", "pass"],
                          operator_id="operator-partial-fixture", recorded_at="2026-10-09T12:00:00.500000Z",
                          operator_redaction_attested=True, endpoint_identity="local", account_role="owner")
        broker_id = f"local-uid-{os.getuid()}:broker"
        broker_session = f"session-posix-{os.getuid()}-{os.getsid(0)}"

        def event(name: str, timestamp: str, kind: str, payload: dict, changes: list[dict] | None = None) -> dict:
            return base_event(event_id=f"event-{name}", engagement_id=engagement.name, recorded_at=timestamp,
                              actor_role="broker", actor_id=broker_id, event_type=kind, rationale=f"Synthetic {name}.",
                              payload=payload, state_changes=changes, session_id=broker_session, operation_class="notebook")

        cards = ["llm07.system-prompt-leakage", "task-reframing", "adjudication-oracle"]
        append_event(engagement, event("observation", "2026-10-09T12:00:01Z", "observation.recorded", {"entity_id": "observation-chain", "entity_type": "observation", "status": "recorded"}))
        routing = event("routing", "2026-10-09T12:00:02Z", "routing.assessed", {"entity_id": "routing-chain", "source_observation_ref": "event-observation", "activation_strength": "strong", "card_ids": cards, "status": "assessed"})
        routing["entity_refs"] = ["event-observation"]
        append_event(engagement, routing)
        candidate = event("candidate", "2026-10-09T12:00:03Z", "candidate.proposed", {"candidate_id": "candidate-chain", "source_observation_ref": "event-observation", "routing_review_ref": "event-routing", "activation_strength": "strong", "card_ids": cards, "status": "queued", "expected_information_gain": 1, "safety_class": "clear_local", "cost_estimate": ZERO_COST}, [{"dimension": "search", "entity_id": "candidate-chain", "previous": None, "current": "queued"}])
        candidate["ex_ante"] = {"probability": 0.5, "ordinal": "strong", "recorded_before_outcome": True}
        candidate["entity_refs"] = ["event-observation", "event-routing"]
        append_event(engagement, candidate)
        append_event(engagement, event("candidate-selected", "2026-10-09T12:00:04Z", "candidate.selected", {"candidate_id": "candidate-chain", "status": "selected", "reason": "bounded chain"}, [{"dimension": "search", "entity_id": "candidate-chain", "previous": "queued", "current": "selected"}]))
        hypothesis = event("hypothesis", "2026-10-09T12:00:05Z", "hypothesis.created", {"hypothesis_id": "hypothesis-chain", "origin_type": "candidate", "origin_ref": "candidate-chain", "candidate_ref": "candidate-chain", "hypothesis_statement": "One local primitive may compose with an adjacent stage.", "suspected_invariant": "The adjacent stage must hold.", "trust_boundary": "owned first stage to owned second stage", "attacker_path": ["owned first stage", "adjacent stage"], "impact_ceiling": "local synthetic only", "bounded_space": "two exact stages", "lens_ids": ["composition"], "card_ids": cards, "expected_confirming_evidence": [{"evidence_type": "trace", "description": "adjacent stage trace", "required": True}], "decisive_falsifiers": ["adjacent stage rejects input"], "cost_estimate": ZERO_COST, "constraints": ["read only"], "next_experiment": "check adjacent stage", "completion_criteria": ["trace or refutation"], "status": "queued"}, [{"dimension": "search", "entity_id": "hypothesis-chain", "previous": None, "current": "queued"}])
        hypothesis["entity_refs"] = ["candidate-chain"]
        append_event(engagement, hypothesis)
        for status, previous, second in (("selected", "queued", "06"), ("running", "selected", "07")):
            append_event(engagement, event(f"hypothesis-{status}", f"2026-10-09T12:00:{second}Z", "hypothesis.status_changed", {"hypothesis_id": "hypothesis-chain", "status": status, "reason": "bounded chain", "experiment_refs": [], "control_refs": [], "supporting_evidence_refs": [], "conflicting_evidence_refs": [], "disposition_rationale": "continue the exact chain", "unresolved_questions": [], "next_route": "check adjacent stage"}, [{"dimension": "search", "entity_id": "hypothesis-chain", "previous": previous, "current": status}]))

        append_attempt(engagement, {"schema_version": 2, "attempt_id": "attempt-base", "engagement_id": engagement.name,
            "recorded_at": "2026-10-09T12:00:07.500000Z", "actor": {"role": "broker", "id": broker_id}, "operation_class": "notebook",
            "provenance": {"actor": {"role": "broker", "id": broker_id}, "session_id": broker_session, "provider": None, "model": "fixture", "prompt_version": "partial-chain-v1", "card_versions": [], "tool_versions": []},
            "scope_hash": reduce_engagement(engagement)["scope_hash"], "environment_ref": "preflight-chain", "escalation_confirmation_event_ref": None,
            "hypothesis_ref": "hypothesis-chain", "experiment_ref": "event-hypothesis-running", "surface": "owned local fixture",
            "action_summary": "Read one benign base-effect marker.", "redaction_attestation": True,
            "observation": {"source": "broker", "statement": "The benign base-effect marker appeared in the owned fixture."}, "evidence_refs": [],
            "kind": "primary", "control_of": [], "assessment": "suspected_signal", "contamination": {"status": "none_observed", "sources": [], "note": ""}, "cost": ZERO_COST})

        stages = [
            {"n": 1, "claim": "The owned base effect is present.", "state": "proven", "evidence_refs": ["attempt-base"], "blocked_by": None, "what_would_close_it": None},
            {"n": 2, "claim": "The adjacent stage accepts the base effect.", "state": "argued", "evidence_refs": [], "blocked_by": "No adjacent-stage trace yet.", "what_would_close_it": "Run the exact owned adjacent-stage check."},
        ]
        partial = event("chain-argued", "2026-10-09T12:00:08Z", "partial_chain.recorded", {"finding_id": "F-full-chain", "hypothesis_id": "hypothesis-chain", "base_finding_ref": None, "stages": stages, "next_question": "Does the owned adjacent stage accept the base output?", "status": "queued"}, [{"dimension": "search", "entity_id": "hypothesis-chain", "previous": "running", "current": "queued"}])
        partial["entity_refs"] = ["hypothesis-chain"]
        proposal = root / "partial-event.json"
        unsupported = json.loads(json.dumps(partial))
        unsupported["event_id"] = "event-chain-unsupported"
        unsupported["payload"]["stages"][0]["evidence_refs"] = ["attempt-not-recorded"]
        denied(workspace, engagement, root / "unsupported.json", unsupported, "record_reference_invalid")
        secret = json.loads(json.dumps(partial))
        secret["event_id"] = "event-chain-secret"
        secret["payload"]["stages"][1]["claim"] = 'password="synthetic-password-value"'
        denied(workspace, engagement, root / "secret.json", secret, "partial_chain_secret_shaped")
        proposal.write_bytes(canonical_json_bytes(partial))
        cli(workspace, "append-event", "--engagement", str(engagement), "--file", str(proposal))
        projected = engagement / "unproven/F-full-chain/partial-chain.json"
        assert projected.is_file()
        cli(workspace, "reduce", "--engagement", str(engagement))
        state = json.loads((engagement / "state.snapshot.json").read_bytes())
        assert state["hypotheses"]["hypothesis-chain"]["status"] == "queued"
        assert state["partial_chains"]["F-full-chain"]["stages"] == stages
        assert "hypothesis_unrouted" in {item["class"] for item in state["work_queue"]}
        assert cli(workspace, "next", "--engagement", str(engagement))["item"]["entity"]["id"] == "hypothesis-chain"
        assert any(row["event_id"] == "event-chain-argued" for row in read_ledger(engagement, "event"))
        assert reduce_engagement(engagement)["partial_chains"] == state["partial_chains"]

        from engagement_state import require_complete_chain
        try:
            require_complete_chain("F-full-chain", state)
        except RecordError as exc:
            assert exc.code == "finding_chain_incomplete", exc.code
        else:
            raise AssertionError("argued chain cleared promotion guard")

        for status, previous, second in (("selected", "queued", "09"), ("running", "selected", "10")):
            append_event(engagement, event(f"hypothesis-re{status}", f"2026-10-09T12:00:{second}Z", "hypothesis.status_changed", {"hypothesis_id": "hypothesis-chain", "status": status, "reason": "check argued stage", "experiment_refs": [], "control_refs": [], "supporting_evidence_refs": [], "conflicting_evidence_refs": [], "disposition_rationale": "recheck exact route", "unresolved_questions": [], "next_route": "check adjacent stage"}, [{"dimension": "search", "entity_id": "hypothesis-chain", "previous": previous, "current": status}]))
        refuted_stages = json.loads(json.dumps(stages))
        refuted_stages[1]["state"] = "refuted"
        refuted_stages[1]["evidence_refs"] = ["attempt-base"]
        refuted_stages[1]["blocked_by"] = "The exact adjacent route rejected the input."
        refuted = event("chain-refuted", "2026-10-09T12:00:11Z", "partial_chain.recorded", {"finding_id": "F-full-chain", "hypothesis_id": "hypothesis-chain", "base_finding_ref": None, "stages": refuted_stages, "next_question": "Which alternative owned route could compose?", "status": "closed"}, [{"dimension": "search", "entity_id": "hypothesis-chain", "previous": "running", "current": "closed"}])
        refuted["entity_refs"] = ["hypothesis-chain"]
        proposal.write_bytes(canonical_json_bytes(refuted))
        cli(workspace, "append-event", "--engagement", str(engagement), "--file", str(proposal))
        cli(workspace, "reduce", "--engagement", str(engagement))
        refuted_state = json.loads((engagement / "state.snapshot.json").read_bytes())
        assert refuted_state["hypotheses"]["hypothesis-chain"]["status"] == "closed"
        assert refuted_state["partial_chains"]["F-full-chain"]["stages"] == refuted_stages
        assert not any(item["entity"]["id"] == "hypothesis-chain" for item in refuted_state["work_queue"])
        try:
            require_complete_chain("F-full-chain", refuted_state)
        except RecordError as exc:
            assert exc.code == "finding_chain_incomplete", exc.code
        else:
            raise AssertionError("refuted chain cleared promotion guard")
        complete_state = json.loads(json.dumps(refuted_state))
        complete_state["partial_chains"]["F-full-chain"]["stages"][1].update({"state": "proven", "blocked_by": None, "what_would_close_it": None})
        complete_state["claim_adjudications"]["F-full-chain"] = {"event_sequence": complete_state["partial_chains"]["F-full-chain"]["event_sequence"] + 1, "input_refs": []}
        try:
            require_complete_chain("F-full-chain", complete_state)
        except RecordError as exc:
            assert exc.code == "finding_chain_review_stale", exc.code
        else:
            raise AssertionError("unreviewed complete chain cleared promotion guard")
        complete_state["claim_adjudications"]["F-full-chain"]["input_refs"] = [complete_state["partial_chains"]["F-full-chain"]["event_ref"]]
        require_complete_chain("F-full-chain", complete_state)
        projected.write_bytes(b"{}\n")
        stale = subprocess.run([sys.executable, str(ROOT / "tools/run-engagement.py"), "check-resume", "--engagement", str(engagement)], cwd=workspace, text=True, capture_output=True, check=False)
        assert stale.returncode != 0 and "stale_derived_views" in stale.stdout + stale.stderr
        cli(workspace, "reduce", "--engagement", str(engagement))
        assert json.loads(projected.read_bytes()) == refuted_state["partial_chains"]["F-full-chain"]
        assert cli(workspace, "check-resume", "--engagement", str(engagement))["ok"] is True
        output_text = os.environ.get("HARNESS_PARTIAL_CHAIN_OUTPUT_DIR")
        if output_text:
            output = Path(output_text).resolve()
            output.mkdir(parents=True, exist_ok=False)
            for name, source in (("events.jsonl", engagement / "events.jsonl"),
                                 ("attempts.jsonl", engagement / "attempts.jsonl"),
                                 ("partial-chain.json", projected),
                                 ("state.snapshot.json", engagement / "state.snapshot.json"),
                                 ("scope.md", engagement / "scope.md")):
                shutil.copyfile(source, output / name)
            source_head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True, check=True).stdout.strip()
            (output / "result.json").write_bytes(canonical_json_bytes({"source_head": source_head, "engagement_id": engagement.name,
                "ledger_hash": refuted_state["ledger_hash"], "argued_event_ref": "event-chain-argued",
                "refuted_event_ref": "event-chain-refuted", "hypothesis_id": "hypothesis-chain",
                "finding_id": "F-full-chain", "command": "<project-python> tools/partial-chain-workflow-test.py",
                "provider": "none", "target_contact": False}))
        print(json.dumps({"ok": True, "checks": ["invalid_evidence", "secret_rejection", "saved_partial", "restart", "next_action", "refuted_close", "promotion_guard", "tamper_repair"], "ledger_hash": refuted_state["ledger_hash"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
