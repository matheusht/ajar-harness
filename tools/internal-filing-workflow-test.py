#!/usr/bin/env python3
"""Public scoped internal-filing workflow against a saved signed synthetic proof."""

from __future__ import annotations

import argparse
import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from engagement_records import build_reference_index, canonical_json_bytes, sha256_bytes, sha256_file, validate_record
from engagement_state import base_event, compute_review_input_hash, finding_revision_lane_id
from environment_preflight import _collect_legacy_preflight as collect_preflight
from finding_review import claim_rows, claim_tuple_hash


ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable
SCOPE = """# Scope - internal filing fixture
## Surfaces in scope
- One owned local synthetic source.
## Benign safe-objective set
- Verify local proof and draft one internal report.
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
- Reviewer allowed signers SHA256: {signers_hash}
## Authorization
- Operator allowed signers SHA256: {signers_hash}
- Operator: operator-internal-fixture
- Date: 2026-10-09
- Signed: [x]
- Record kernel: `decision-0006-v2`
"""
ZERO_COST = {"wall_seconds": 0, "model_seconds": 0, "tool_seconds": 0, "target_calls": 0, "model_calls": 0, "input_tokens": None, "output_tokens": None, "cost_usd": None, "human_review_seconds": 0}


def call(*args: str, ok: bool = True) -> dict:
    result = subprocess.run([PYTHON, str(ROOT / "tools/run-engagement.py"), *args], text=True, capture_output=True, check=False)
    try:
        response = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(result.stdout + result.stderr) from exc
    assert (result.returncode == 0) is ok, response
    return response


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def seed_v2_proof(root: Path, bundle: Path, broker: str, session: str) -> Path:
    """Re-run the saved inert proof inputs in a separately signed v2 scope."""
    source = bundle / "complete"
    engagement = root / "eng-selftest"
    engagement.mkdir()
    key = root / "reviewer-key"
    subprocess.run(["/usr/bin/ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)], check=True, capture_output=True)
    public = key.with_suffix(".pub").read_text().split()
    signers = root / "allowed-signers"
    signers.write_text(f"reviewer-external-canonical {public[0]} {public[1]}\noperator-internal-fixture {public[0]} {public[1]}\n")
    (engagement / "scope.md").write_text(SCOPE.format(signers_hash=sha256_file(signers)))
    init_time = "2026-10-09T12:00:00Z"
    challenge = {"schema_version": 1, "namespace": "llm-redteam-harness-operator-v1", "engagement_id": engagement.name,
                 "scope_hash": sha256_file(engagement / "scope.md"), "ledger_hash": None,
                 "operation": f"initialize-engagement:{init_time}", "operator_id": "operator-internal-fixture"}
    challenge_file = root / "init-challenge.json"
    challenge_file.write_bytes(canonical_json_bytes(challenge))
    subprocess.run(["/usr/bin/ssh-keygen", "-q", "-Y", "sign", "-f", str(key), "-n", "llm-redteam-harness-operator-v1", str(challenge_file)], check=True, capture_output=True)
    env = {**os.environ, "HARNESS_OPERATOR_SIGNATURE_FILE": str(challenge_file) + ".sig", "HARNESS_OPERATOR_ALLOWED_SIGNERS_FILE": str(signers)}
    initialized = subprocess.run([PYTHON, str(ROOT / "tools/run-engagement.py"), "init", "--engagement", str(engagement), "--recorded-at", init_time], text=True, capture_output=True, env=env)
    assert initialized.returncode == 0, initialized.stdout + initialized.stderr
    target = root / "owned.txt"
    target.write_text("owned benign source marker\n")
    collect_preflight(engagement, preflight_id="preflight-changed-target", mode="package", target=target,
                      expected_identity=sha256_file(target), runtime=Path(PYTHON).resolve(),
                      reproduction_argv=[str(Path(PYTHON).resolve()), "-c", "pass"],
                      operator_id="operator-internal-fixture", recorded_at="2026-10-09T12:00:00.500000Z",
                      operator_redaction_attested=True, endpoint_identity="local", account_role="owner")

    def event(name: str, kind: str, payload: dict, change: tuple[str | None, str] | None = None, *, refs: list[str] | None = None) -> None:
        proposal = base_event(event_id=name, engagement_id=engagement.name, recorded_at=now(), actor_role="broker", actor_id=broker,
                              event_type=kind, rationale=f"Synthetic {name}.", payload=payload, entity_refs=refs or [],
                              state_changes=[{"dimension": "search", "entity_id": payload.get("hypothesis_id", payload.get("candidate_id")), "previous": change[0], "current": change[1]}] if change else [],
                              session_id=session, operation_class="notebook")
        file = root / f"{name}.json"; file.write_bytes(canonical_json_bytes(proposal))
        call("append-event", "--engagement", str(engagement), "--file", str(file))

    cards = ["llm07.system-prompt-leakage", "task-reframing", "adjudication-oracle"]
    event("event-observation", "observation.recorded", {"entity_id": "observation-proof", "entity_type": "observation", "status": "recorded"})
    event("event-routing", "routing.assessed", {"entity_id": "routing-proof", "source_observation_ref": "event-observation", "activation_strength": "strong", "card_ids": cards, "status": "assessed"}, refs=["event-observation"])
    candidate = {"candidate_id": "candidate-c1", "source_observation_ref": "event-observation", "routing_review_ref": "event-routing",
                 "activation_strength": "strong", "card_ids": cards, "status": "queued", "expected_information_gain": 1,
                 "safety_class": "clear_local", "cost_estimate": ZERO_COST}
    proposed = base_event(event_id="event-candidate", engagement_id=engagement.name, recorded_at=now(), actor_role="broker", actor_id=broker,
                          event_type="candidate.proposed", rationale="Synthetic bounded candidate.", payload=candidate,
                          entity_refs=["event-observation", "event-routing"], state_changes=[{"dimension": "search", "entity_id": "candidate-c1", "previous": None, "current": "queued"}],
                          session_id=session, operation_class="notebook")
    proposed["ex_ante"] = {"probability": 0.5, "ordinal": "strong", "recorded_before_outcome": True}
    path = root / "event-candidate.json"; path.write_bytes(canonical_json_bytes(proposed))
    call("append-event", "--engagement", str(engagement), "--file", str(path))
    event("event-candidate-selected", "candidate.selected", {"candidate_id": "candidate-c1", "status": "selected", "reason": "bounded proof"}, ("queued", "selected"))
    hypothesis = {"hypothesis_id": "hypothesis-h1", "origin_type": "candidate", "origin_ref": "candidate-c1", "candidate_ref": "candidate-c1",
                  "hypothesis_statement": "The owned source exposes one bounded marker.", "suspected_invariant": "The matched sibling holds.",
                  "trust_boundary": "owned source to matched sibling", "attacker_path": ["owned source", "matched sibling"],
                  "impact_ceiling": "local synthetic only", "bounded_space": "one source and sibling", "lens_ids": ["composition"],
                  "card_ids": cards, "expected_confirming_evidence": [{"evidence_type": "trace", "description": "owned trace", "required": True}],
                  "decisive_falsifiers": ["matched sibling emits the same marker"], "cost_estimate": ZERO_COST, "constraints": ["read only"],
                  "next_experiment": "read owned marker", "completion_criteria": ["matched trace or refutation"], "status": "queued"}
    event("event-hypothesis-created", "hypothesis.created", hypothesis, (None, "queued"), refs=["candidate-c1"])
    for status, previous in (("selected", "queued"), ("running", "selected")):
        event(f"event-hypothesis-{status}", "hypothesis.status_changed", {"hypothesis_id": "hypothesis-h1", "status": status,
              "reason": "bounded proof", "experiment_refs": [], "control_refs": [], "supporting_evidence_refs": [],
              "conflicting_evidence_refs": [], "disposition_rationale": "continue exact proof", "unresolved_questions": [],
              "next_route": "read owned marker"}, (previous, status))

    artifact_names = ["artifact-canonical-public", *(f"artifact-attempt-canonical-{kind}-output" for kind in ("primary", "negative", "positive", "replay"))]
    source_artifacts = {item["artifact_id"]: item for item in map(json.loads, (source / "artifacts.jsonl").read_bytes().splitlines())}
    (engagement / "evidence").mkdir(exist_ok=True)
    for artifact_id in artifact_names:
        original = source_artifacts[artifact_id]
        filename = Path(original["relative_path"]).name
        input_file = source / original["relative_path"]
        output_file = engagement / "evidence" / filename
        artifact_at = now()
        metadata = {"schema_version": 1, "artifact_id": artifact_id, "engagement_id": engagement.name, "created_at": artifact_at,
                    "producer": {"role": "broker", "id": broker}, "producer_session_id": session, "operation_class": "notebook",
                    "acquisition_method": "source_inspection" if artifact_id == "artifact-canonical-public" else "broker",
                    "target_refs": [], "environment_ref": "preflight-changed-target", "sensitivity": "internal", "redaction_status": "not_needed",
                    "contains_executable_capability": False, "advisory_zone": "clear_local", "escalation_confirmation_event_ref": None,
                    "cleanup_obligation_ref": None, "supersedes_artifact_id": None, "media_type": "text/plain"}
        metadata_file = root / f"{artifact_id}-metadata.json"; metadata_file.write_bytes(canonical_json_bytes(metadata))
        classification = root / f"{artifact_id}-classification.json"
        call("classify-artifact", "--engagement", str(engagement), "--metadata", str(metadata_file), "--source", str(input_file),
             "--relative-path", f"evidence/{filename}", "--recorded-at", artifact_at, "--actor-role", "broker", "--actor-id", broker,
             "--session-id", session, "--output", str(classification))
        shutil.copyfile(input_file, output_file)
        call("register-artifact", "--engagement", str(engagement), "--file", str(output_file),
             "--metadata", str(metadata_file), "--classification", str(classification))

    source_attempts = {item["attempt_id"]: item for item in map(json.loads, (source / "attempts.jsonl").read_bytes().splitlines())}
    for kind in ("primary", "negative", "positive", "replay"):
        attempt_id = f"attempt-canonical-{kind}"
        attempt = {key: copy.deepcopy(value) for key, value in source_attempts[attempt_id].items() if key not in {"sequence", "previous_hash", "record_hash"}}
        attempt.update({"engagement_id": engagement.name, "recorded_at": now(), "actor": {"role": "broker", "id": broker},
                        "scope_hash": sha256_file(engagement / "scope.md"), "environment_ref": "preflight-changed-target",
                        "hypothesis_ref": "hypothesis-h1", "experiment_ref": "event-hypothesis-running"})
        attempt["provenance"].update({"actor": {"role": "broker", "id": broker}, "session_id": session,
                                      "runtime_session_ref": "session-v2-proof-hunter"})
        file = root / f"{attempt_id}.json"; file.write_bytes(canonical_json_bytes(attempt))
        call("append-attempt", "--engagement", str(engagement), "--file", str(file))

    for name, verdict, previous in (("canonical-public", "supported", None), ("proof-complete", "confirmed", "supported")):
        review = json.loads((source / "reviews" / f"review-{name}.json").read_bytes())
        review["engagement_id"] = engagement.name
        review["recorded_at"] = now()
        review["input_refs"] = [ref for ref in review["input_refs"] if ref != "event-canonical-chain-complete"]
        review["independence"]["reviewer_session_id"] = f"session-v2-review-{name}"
        review["independence"]["originating_run_id"] = "attempt-canonical-primary"
        if verdict == "confirmed":
            profile = review["confirmation_profile"]
            profile["scope_provenance"]["scope_hash"] = sha256_file(engagement / "scope.md")
            profile["scope_provenance"]["provenance"]["session_id"] = review["independence"]["reviewer_session_id"]
            review["claim_tuple_hash"] = claim_tuple_hash(profile)
        review["input_hash"] = compute_review_input_hash(engagement, review, build_reference_index(engagement))
        review_file = root / f"review-v2-{name}.json"; review_file.write_bytes(canonical_json_bytes(review))
        subprocess.run(["/usr/bin/ssh-keygen", "-q", "-Y", "sign", "-f", str(key), "-n", "llm-redteam-harness-review-v1", str(review_file)], check=True, capture_output=True)
        payload = {"entity_id": "F-canonical-public", "status": verdict, "review_ref": review["review_id"],
                   "reviewer_id": review["independence"]["reviewer_id"], "review_digest": sha256_file(review_file)}
        if verdict == "confirmed": payload["confirmation_policy_version"] = 1
        event_record = base_event(event_id=f"event-v2-{name}", engagement_id=engagement.name, recorded_at=review["recorded_at"],
                                  actor_role="broker", actor_id=broker, event_type="claim.adjudicated", rationale="Independent synthetic proof review.",
                                  payload=payload, review_refs=[review["review_id"]],
                                  state_changes=[{"dimension": "claim", "entity_id": "F-canonical-public", "previous": previous, "current": verdict}],
                                  session_id=session, operation_class="notebook")
        event_file = root / f"event-v2-{name}.json"; event_file.write_bytes(canonical_json_bytes(event_record))
        call("record-review", "--engagement", str(engagement), "--file", str(review_file), "--event", str(event_file),
             "--actor-id", broker, "--session-id", session, "--signature", str(review_file) + ".sig", "--allowed-signers", str(signers))
    return engagement


def request(engagement: Path, root: Path, request_id: str, action: dict, broker: str, session: str) -> dict:
    file = root / f"{request_id}.json"
    file.write_bytes(canonical_json_bytes(action))
    expires = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(timespec="seconds").replace("+00:00", "Z")
    return call("request-authority", "--engagement", str(engagement), "--request-id", request_id,
                "--action-kind", action["action_kind"], "--action-file", str(file), "--lane-id", action["lane_id"],
                "--actor-role", "broker", "--actor-id", broker, "--session-id", session,
                "--recorded-at", now(), "--expires-at", expires, "--reason", "Exact signed-scope internal draft request.")


def scoped_resolution(engagement: Path, request_id: str, broker: str, session: str, *, ok: bool = True) -> dict:
    return call("resolve-internal-authority", "--engagement", str(engagement), "--request-id", request_id,
                "--executor-id", broker, "--session-id", session, "--recorded-at", now(), ok=ok)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--proof-bundle", type=Path, required=True, help="saved output of run-engagement.py --self-test-proof-output")
    parser.add_argument("--output", type=Path, help="new directory for exact-commit evidence")
    args = parser.parse_args()
    bundle = args.proof_bundle.resolve()
    with tempfile.TemporaryDirectory(prefix="internal-filing-124-") as temporary:
        root = Path(temporary)
        broker = f"local-uid-{os.getuid()}:broker"
        session = f"session-posix-{os.getuid()}-{os.getsid(0)}"
        engagement = seed_v2_proof(root, bundle, broker, session)
        denials = {}
        review = json.loads((engagement / "reviews/review-proof-complete.json").read_bytes())
        profile = review["confirmation_profile"]
        call("reduce", "--engagement", str(engagement))
        state = json.loads((engagement / "state.snapshot.json").read_bytes())
        latest = state["claim_adjudications"]["F-canonical-public"]
        assert latest["status"] == "confirmed" and "F-canonical-public" not in state["findings"]
        operator = json.loads((engagement / "events.jsonl").read_bytes().splitlines()[0])["payload"]["operator_id"]
        finding = json.loads((bundle / "complete/findings/F-selftest/rev-3.json").read_bytes())
        finding.update(copy.deepcopy(profile))
        finding.update({"schema_version": 3, "engagement_id": state["engagement_id"], "finding_id": "F-canonical-public",
                        "revision": 1, "supersedes_revision": None, "recorded_at": now(),
                        "change_reason": "Save the independently confirmed synthetic claim as an internal finding.",
                        "adjudication": {"review_ref": latest["review_ref"], "justification": "Independent proof review confirmed the bounded claim."},
                        "privilege_context": {"claimed_position": "authenticated-user", "execution_position": "authenticated-user", "evidence_refs": ["attempt-canonical-primary"]},
                        "state_provenance": {"mode": "real-path", "evidence_refs": ["attempt-canonical-primary"], "synthesized_setup": []}})
        errors = validate_record(finding, "finding-v3")
        assert not errors, errors
        proposal = root / "finding.json"
        proposal.write_bytes(canonical_json_bytes(finding))
        target = {"type": "finding", "id": finding["finding_id"], "expected_revision": 1,
                  "claim_state": "confirmed", "adjudication_event_ref": latest["event_ref"],
                  "adjudication_review_ref": latest["review_ref"], "resolves_review_refs": [],
                  "file_digest": sha256_bytes(proposal.read_bytes())}
        lane = finding_revision_lane_id(target)
        action = {"action_kind": "revise-finding", "action_version": 3, "lane_id": lane,
                  "executor_id": broker, "session_id": session, "file_digest": target["file_digest"],
                  "operator_id": operator, "proposal": finding, "target": target}
        unsupported = copy.deepcopy(action)
        unsupported["target"]["claim_state"] = "supported"
        (root / "unsupported.json").write_bytes(canonical_json_bytes(unsupported))
        rejected = call("request-authority", "--engagement", str(engagement), "--request-id", "request-unconfirmed",
                        "--action-kind", "revise-finding", "--action-file", str(root / "unsupported.json"),
                        "--lane-id", lane, "--actor-role", "broker", "--actor-id", broker,
                        "--session-id", session, "--recorded-at", now(),
                        "--expires-at", (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(timespec="seconds").replace("+00:00", "Z"),
                        "--reason", "Unconfirmed claim must fail.", ok=False)
        assert rejected["error"]["code"] == "revise_finding_v2_target_stale", rejected
        denials["unconfirmed_target"] = rejected["error"]["code"]
        request(engagement, root, "request-internal-finding", action, broker, session)
        wrong_broker = scoped_resolution(engagement, "request-internal-finding", broker + "-other", session, ok=False)
        assert wrong_broker["error"]["code"] == "runtime_provenance_not_principal_bound", wrong_broker
        denials["wrong_broker"] = wrong_broker["error"]["code"]
        scoped_resolution(engagement, "request-internal-finding", broker, session)
        call("settle-approved-revision", "--engagement", str(engagement), "--file", str(proposal),
             "--operator-id", operator, "--recorded-at", now(), "--authority-request-id", "request-internal-finding",
             "--lane-id", lane, "--executor-id", broker, "--session-id", session)
        replay = call("settle-approved-revision", "--engagement", str(engagement), "--file", str(proposal),
                      "--operator-id", operator, "--recorded-at", now(), "--authority-request-id", "request-internal-finding",
                      "--lane-id", lane, "--executor-id", broker, "--session-id", session)
        assert replay["replayed"] is True, replay
        claim_ids = [row["claim_id"] for row in claim_rows(finding)]
        report_lane = "lane-internal-report-F-canonical-public-r1"
        report_action = {"action_kind": "generate-report", "lane_id": report_lane, "executor_id": broker,
                         "session_id": session, "finding_id": finding["finding_id"], "revision": 1,
                         "included_claim_ids": claim_ids, "omitted_claims": [], "operator_id": operator,
                         "recorded_at": (datetime.now(timezone.utc) + timedelta(minutes=2)).isoformat(timespec="microseconds").replace("+00:00", "Z")}
        incomplete_report = copy.deepcopy(report_action)
        incomplete_report["lane_id"] = "lane-incomplete-report"
        incomplete_report["included_claim_ids"] = []
        request(engagement, root, "request-incomplete-report", incomplete_report, broker, session)
        incomplete_denial = scoped_resolution(engagement, "request-incomplete-report", broker, session, ok=False)
        assert incomplete_denial["error"]["code"] == "internal_report_claim_partition_invalid"
        denials["incomplete_report"] = incomplete_denial["error"]["code"]
        external = {"action_kind": "accept-report", "lane_id": "lane-external-report", "executor_id": broker,
                    "session_id": session, "operator_id": operator}
        request(engagement, root, "request-external-report", external, broker, session)
        external_denial = scoped_resolution(engagement, "request-external-report", broker, session, ok=False)
        assert external_denial["error"]["code"] == "internal_authority_action_forbidden"
        denials["external_accept"] = external_denial["error"]["code"]
        report_action["recorded_at"] = (datetime.now(timezone.utc) + timedelta(seconds=3)).isoformat(timespec="microseconds").replace("+00:00", "Z")
        request(engagement, root, "request-internal-report", report_action, broker, session)
        scoped_resolution(engagement, "request-internal-report", broker, session)
        report_args = ("generate-report", "--engagement", str(engagement), "--finding-id", finding["finding_id"],
                       "--revision", "1", *(item for claim_id in claim_ids for item in ("--include-claim", claim_id)),
                       "--operator-id", operator, "--recorded-at", report_action["recorded_at"],
                       "--authority-request-id", "request-internal-report", "--lane-id", report_lane,
                       "--executor-id", broker, "--session-id", session)
        generated = call(*report_args)
        repeated = call(*report_args)
        assert repeated["report_id"] == generated["report_id"] and repeated["replayed"] is True, repeated
        changed = list(report_args)
        changed[changed.index("--include-claim") + 1] = "changed-claim"
        changed_denial = call(*changed, ok=False)
        assert changed_denial["error"]["code"] != "", changed_denial
        denials["changed_report_retry"] = changed_denial["error"]["code"]
        call("reduce", "--engagement", str(engagement))
        final = json.loads((engagement / "state.snapshot.json").read_bytes())
        assert final["findings"][finding["finding_id"]]["status"] == "confirmed"
        assert final["reports"][generated["report_id"]]["status"] == "draft"
        assert not final["submission_refs"]
        blocked_accept = scoped_resolution(engagement, "request-internal-accept", broker, session, ok=False)
        assert blocked_accept["error"]["code"] == "internal_authority_request_invalid"
        denials["unrequested_accept"] = blocked_accept["error"]["code"]
        if args.output:
            output = args.output.resolve()
            output.mkdir(parents=True, exist_ok=False)
            shutil.copytree(engagement, output / "engagement")
            shutil.copy2(proposal, output / "finding-proposal.json")
            (output / "result.json").write_bytes(canonical_json_bytes({"source_head": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True, check=True).stdout.strip(), "finding_id": finding["finding_id"], "report_id": generated["report_id"], "provider": "none", "target_contact": False, "denials": denials, "finding_replayed": replay["replayed"], "report_replayed": repeated["replayed"]}))
        print(json.dumps({"ok": True, "finding_id": finding["finding_id"], "report_id": generated["report_id"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
