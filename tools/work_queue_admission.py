#!/usr/bin/env python3
"""Closed, machine-readable mutation predicates for reducer-selected queue actions."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from engagement_records import RecordError
from engagement_state import TRANSITIONS, _filing_ready_review_refs
from reasoned_escalation import route_digest


def _constraint(document: str, path: list[str], operator: str, value: Any) -> dict[str, Any]:
    return {"document": document, "path": path, "operator": operator, "value": value}


def _spec(documents: list[dict[str, str]], constraints: list[dict[str, Any]]) -> dict[str, Any]:
    if not documents or not constraints:
        raise RecordError("work_queue_admission_empty", "predicate")
    return {"schema_version": 1, "documents": documents, "constraints": constraints}


def _event(*constraints: dict[str, Any], event_type: str) -> dict[str, Any]:
    return _spec(
        [{"name": "proposal", "argument": "--file"}],
        [_constraint("proposal", ["event_type"], "equals", event_type), *constraints],
    )


def _attempt(*constraints: dict[str, Any]) -> dict[str, Any]:
    return _spec([{"name": "proposal", "argument": "--file"}], list(constraints))


def _review(review_type: str, entity_ref: str, finding_revision: int | None, *constraints: dict[str, Any]) -> dict[str, Any]:
    event_types = {
        "claim_adjudication": "claim.adjudicated",
        "coverage": "review.coverage_completed",
        "regrade": "review.regrade_completed",
        "pocinator": "review.pocinator_completed",
        "higher_impact_route": "review.higher_impact_route_completed",
    }
    try:
        event_type = event_types[review_type]
    except KeyError as exc:
        raise RecordError("work_queue_admission_review_type_invalid", review_type) from exc
    event_constraints: list[dict[str, Any]] = []
    if review_type == "claim_adjudication":
        event_constraints.extend(
            [
                _constraint("proposal", ["proposed_finding_id"], "equals", entity_ref),
                _constraint("event", ["payload", "entity_id"], "equals", entity_ref),
                _constraint(
                    "event",
                    ["payload", "status"],
                    "document_path_equals",
                    {"document": "proposal", "path": ["verdict"]},
                ),
            ]
        )
    elif review_type in {"regrade", "pocinator"}:
        event_constraints.extend(
            [
                _constraint(
                    "proposal",
                    ["independence", "reviewer_signer_fingerprint"],
                    "not_one_of",
                    [None],
                ),
                _constraint("proposal", ["proposed_finding_id"], "equals", entity_ref),
                _constraint("event", ["payload", "finding_id"], "equals", entity_ref),
                _constraint("event", ["payload", "finding_revision"], "equals", finding_revision),
                _constraint(
                    "event",
                    ["payload", "claim_tuple_hash"],
                    "document_path_equals",
                    {"document": "proposal", "path": ["claim_tuple_hash"]},
                ),
                _constraint(
                    "event",
                    ["payload", "verdict"],
                    "document_path_equals",
                    {"document": "proposal", "path": ["verdict"]},
                ),
            ]
        )
        if review_type == "pocinator":
            event_constraints.append(
                _constraint(
                    "event",
                    ["payload", "high_value"],
                    "document_path_equals",
                    {"document": "proposal", "path": ["high_value"]},
                )
            )
    else:
        event_constraints.append(
            _constraint(
                "event",
                ["payload", "verdict"],
                "document_path_equals",
                {"document": "proposal", "path": ["verdict"]},
            )
        )
    return _spec(
        [
            {"name": "proposal", "argument": "--file"},
            {"name": "event", "argument": "--event"},
        ],
        [
            _constraint("proposal", ["review_type"], "equals", review_type),
            _constraint("proposal", ["entity_ref"], "equals", entity_ref),
            _constraint("proposal", ["finding_revision"], "equals", finding_revision),
            _constraint("event", ["event_type"], "equals", event_type),
            _constraint("event", ["review_refs"], "length_equals", 1),
            *event_constraints,
            *constraints,
        ],
    )


def _hypothesis_status_event(
    hypothesis_id: str,
    hypothesis: dict[str, Any],
    *,
    target_status: str,
) -> dict[str, Any]:
    previous_status = hypothesis.get("status")
    if not isinstance(previous_status, str):
        raise RecordError("work_queue_admission_hypothesis_missing", hypothesis_id)
    next_route = hypothesis.get("next_experiment") if target_status == "selected" else hypothesis.get("next_route")
    return _event(
        _constraint("proposal", ["payload", "hypothesis_id"], "equals", hypothesis_id),
        _constraint("proposal", ["payload", "status"], "equals", target_status),
        _constraint("proposal", ["payload", "experiment_refs"], "set_equals", list(hypothesis.get("experiment_refs", []))),
        _constraint("proposal", ["payload", "control_refs"], "set_equals", list(hypothesis.get("control_refs", []))),
        _constraint("proposal", ["payload", "supporting_evidence_refs"], "set_equals", list(hypothesis.get("supporting_evidence_refs", []))),
        _constraint("proposal", ["payload", "conflicting_evidence_refs"], "set_equals", list(hypothesis.get("conflicting_evidence_refs", []))),
        _constraint("proposal", ["payload", "unresolved_questions"], "set_equals", list(hypothesis.get("unresolved_questions", []))),
        _constraint("proposal", ["payload", "next_route"], "equals", next_route),
        _constraint(
            "proposal",
            ["state_changes"],
            "equals",
            [{"dimension": "search", "entity_id": hypothesis_id, "previous": previous_status, "current": target_status}],
        ),
        event_type="hypothesis.status_changed",
    )


def _hypothesis_disposition(
    item: dict[str, Any], state: dict[str, Any], engagement: Path, hypothesis_id: str
) -> dict[str, Any]:
    hypothesis = state.get("hypotheses", {}).get(hypothesis_id)
    if not isinstance(hypothesis, dict) or not isinstance(hypothesis.get("status"), str):
        raise RecordError("work_queue_admission_hypothesis_missing", hypothesis_id)
    item_class = item.get("class")
    previous_status = hypothesis["status"]
    legal_statuses = sorted(TRANSITIONS["search"].get(previous_status, set()))
    if not legal_statuses:
        raise RecordError("work_queue_admission_hypothesis_transition_missing", hypothesis_id)
    if item_class == "hypothesis_unrouted":
        expected = "selected" if previous_status == "queued" else "running"
        return _hypothesis_status_event(hypothesis_id, hypothesis, target_status=expected)
    if item_class == "hypothesis_running_unattempted":
        return _hypothesis_status_event(hypothesis_id, hypothesis, target_status="queued")

    common = [
        _constraint("proposal", ["payload", "hypothesis_id"], "equals", hypothesis_id),
        _constraint("proposal", ["payload", "status"], "one_of", legal_statuses),
        _constraint("proposal", ["state_changes"], "length_equals", 1),
        _constraint("proposal", ["state_changes", "0", "dimension"], "equals", "search"),
        _constraint("proposal", ["state_changes", "0", "entity_id"], "equals", hypothesis_id),
        _constraint("proposal", ["state_changes", "0", "previous"], "equals", previous_status),
        _constraint("proposal", ["state_changes", "0", "current"], "one_of", legal_statuses),
    ]
    preserved_refs = [
        _constraint("proposal", ["payload", "supporting_evidence_refs"], "set_equals", list(hypothesis.get("supporting_evidence_refs", []))),
        _constraint("proposal", ["payload", "conflicting_evidence_refs"], "set_equals", list(hypothesis.get("conflicting_evidence_refs", []))),
    ]
    if item_class == "hypothesis_ran_unadjudicated":
        pending_context = state.get("work_queue_context", {}).get("pending_attempts", {})
        pending = pending_context.get(hypothesis_id) if isinstance(pending_context, dict) else None
        if not isinstance(pending, list):
            pending = []
        if not pending:
            raise RecordError("work_queue_admission_attempt_missing", hypothesis_id)
        experiment_refs = set(hypothesis.get("experiment_refs", []))
        control_refs = set(hypothesis.get("control_refs", []))
        for attempt in pending:
            reference = attempt.get("attempt_id")
            if not isinstance(reference, str):
                raise RecordError("work_queue_admission_attempt_invalid", hypothesis_id)
            (control_refs if attempt.get("kind") in {"negative_control", "positive_control"} else experiment_refs).add(reference)
        supporting_refs = set(hypothesis.get("supporting_evidence_refs", []))
        routed_rows = [
            row
            for row in state.get("outstanding_reviews", [])
            if row.get("status") == "routed" and row.get("hypothesis_ref") == hypothesis_id
        ]
        for attempt in pending:
            if any(_timestamp_after(attempt.get("recorded_at"), row.get("opened_at")) for row in routed_rows):
                supporting_refs.add(str(attempt["attempt_id"]))
                evidence = attempt.get("evidence")
                if not isinstance(evidence, list):
                    raise RecordError("work_queue_admission_attempt_invalid", hypothesis_id)
                for item in evidence:
                    if (
                        not isinstance(item, dict)
                        or not isinstance(item.get("reference"), str)
                        or not isinstance(item.get("recorded_at"), str)
                    ):
                        raise RecordError("work_queue_admission_attempt_invalid", hypothesis_id)
                    if any(
                        _timestamp_after(item["recorded_at"], row.get("opened_at"))
                        for row in routed_rows
                    ):
                        supporting_refs.add(item["reference"])
        return _event(
            *common,
            _constraint("proposal", ["payload", "experiment_refs"], "set_equals", sorted(experiment_refs)),
            _constraint("proposal", ["payload", "control_refs"], "set_equals", sorted(control_refs)),
            _constraint("proposal", ["payload", "supporting_evidence_refs"], "set_equals", sorted(supporting_refs)),
            _constraint("proposal", ["payload", "conflicting_evidence_refs"], "set_equals", list(hypothesis.get("conflicting_evidence_refs", []))),
            _constraint("proposal", ["payload", "unresolved_questions"], "set_equals", list(hypothesis.get("unresolved_questions", []))),
            _constraint("proposal", ["payload", "next_route"], "equals", hypothesis.get("next_route")),
            event_type="hypothesis.status_changed",
        )
    if item_class == "hypothesis_open_route":
        return _event(
            *common,
            _constraint("proposal", ["payload", "experiment_refs"], "set_equals", list(hypothesis.get("experiment_refs", []))),
            _constraint("proposal", ["payload", "control_refs"], "set_equals", list(hypothesis.get("control_refs", []))),
            _constraint("proposal", ["payload", "unresolved_questions"], "set_equals", list(hypothesis.get("unresolved_questions", []))),
            _constraint("proposal", ["payload", "next_route"], "equals", None),
            *preserved_refs,
            event_type="hypothesis.status_changed",
        )
    if item_class == "hypothesis_unresolved_question":
        question = item.get("entity", {}).get("detail")
        current_questions = list(hypothesis.get("unresolved_questions", []))
        if not isinstance(question, str) or question not in current_questions:
            raise RecordError("work_queue_admission_question_missing", hypothesis_id)
        return _event(
            *common,
            _constraint("proposal", ["payload", "experiment_refs"], "set_equals", list(hypothesis.get("experiment_refs", []))),
            _constraint("proposal", ["payload", "control_refs"], "set_equals", list(hypothesis.get("control_refs", []))),
            _constraint("proposal", ["payload", "unresolved_questions"], "set_equals", [value for value in current_questions if value != question]),
            _constraint("proposal", ["payload", "next_route"], "equals", hypothesis.get("next_route")),
            *preserved_refs,
            event_type="hypothesis.status_changed",
        )
    raise RecordError("work_queue_admission_hypothesis_class_invalid", str(item_class))


def _current_finding_revision(state: dict[str, Any], finding_id: str) -> int | None:
    finding = state.get("findings", {}).get(finding_id)
    revision = finding.get("revision") if isinstance(finding, dict) else None
    return revision if isinstance(revision, int) else None


def _current_finding_review_constraints(
    state: dict[str, Any], finding_id: str
) -> list[dict[str, Any]]:
    finding = state.get("findings", {}).get(finding_id)
    claim_hash = finding.get("claim_tuple_hash") if isinstance(finding, dict) else None
    revision_event_ref = finding.get("revision_event_ref") if isinstance(finding, dict) else None
    if not isinstance(claim_hash, str) or not isinstance(revision_event_ref, str):
        raise RecordError("work_queue_admission_finding_binding_missing", finding_id)
    return [
        _constraint("proposal", ["claim_tuple_hash"], "equals", claim_hash),
        _constraint(
            "proposal",
            ["independence", "originating_run_id"],
            "equals",
            revision_event_ref,
        ),
    ]


def _current_claim_review_origin(state: dict[str, Any], finding_id: str) -> str:
    adjudication = state.get("claim_adjudications", {}).get(finding_id)
    adjudication_event_ref = (
        adjudication.get("event_ref") if isinstance(adjudication, dict) else None
    )
    if isinstance(adjudication_event_ref, str):
        return adjudication_event_ref
    finding = state.get("findings", {}).get(finding_id)
    revision_event_ref = finding.get("revision_event_ref") if isinstance(finding, dict) else None
    if isinstance(revision_event_ref, str):
        return revision_event_ref
    raise RecordError("work_queue_admission_claim_origin_missing", finding_id)


def _review_row(state: dict[str, Any], review_ref: str) -> dict[str, Any]:
    matches = [row for row in state.get("outstanding_reviews", []) if row.get("review_ref") == review_ref]
    if len(matches) != 1:
        raise RecordError("work_queue_admission_review_missing", review_ref)
    return matches[0]


def _control(state: dict[str, Any], routing_ref: str) -> dict[str, Any]:
    matches = [row for row in state.get("control_candidates", []) if row.get("routing_event_id") == routing_ref]
    if len(matches) != 1:
        raise RecordError("work_queue_admission_control_missing", routing_ref)
    return matches[0]


def _finding_subject(item: dict[str, Any], state: dict[str, Any], entity_id: str) -> str:
    if item.get("class") != "review_obligation_open":
        return entity_id
    row = _review_row(state, entity_id)
    finding_id = row.get("entity_ref")
    if not isinstance(finding_id, str):
        raise RecordError("work_queue_admission_finding_missing", entity_id)
    return finding_id


def _created_hypothesis(origin_type: str, origin_ref: str) -> dict[str, Any]:
    return _event(
        _constraint("proposal", ["payload", "origin_type"], "equals", origin_type),
        _constraint("proposal", ["payload", "origin_ref"], "equals", origin_ref),
        _constraint("proposal", ["payload", "status"], "equals", "queued"),
        event_type="hypothesis.created",
    )


def _attempt_scope(state: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        _constraint("proposal", ["scope_hash"], "equals", state.get("scope_hash")),
        _constraint("proposal", ["environment_ref"], "equals", state.get("active_environment_ref")),
    ]


def _timestamp_after(left: Any, right: Any) -> bool:
    try:
        return datetime.fromisoformat(str(left).replace("Z", "+00:00")) > datetime.fromisoformat(
            str(right).replace("Z", "+00:00")
        )
    except ValueError:
        return False


def build_action_admission(
    item: dict[str, Any], action: dict[str, Any], state: dict[str, Any], engagement: Path
) -> dict[str, Any]:
    """Return the exact proposal predicate admitted for one decorated first queue item."""

    action_id = action.get("action_id")
    entity = item.get("entity")
    if not isinstance(action_id, str) or not isinstance(entity, dict):
        raise RecordError("work_queue_admission_context_invalid", str(action_id))
    entity_id = str(entity.get("id"))

    if action_id in {"record_hypothesis_disposition", "requeue_unattempted_hypothesis"}:
        return _hypothesis_disposition(item, state, engagement, entity_id)
    if action_id == "record_higher_impact_route_review":
        hypothesis = state["hypotheses"][entity_id]
        digest = route_digest(hypothesis["higher_impact_route"])
        return _review(
            "higher_impact_route", entity_id, None,
            _constraint("proposal", ["route_digest"], "equals", digest),
            _constraint("proposal", ["independence", "originating_run_id"], "equals", hypothesis["created_event_ref"]),
            _constraint("event", ["payload", "hypothesis_id"], "equals", entity_id),
            _constraint("event", ["payload", "route_digest"], "equals", digest),
        )
    if action_id in {"hold_higher_impact_hypothesis", "run_higher_impact_hypothesis"}:
        hypothesis = state["hypotheses"][entity_id]
        admission = _hypothesis_status_event(entity_id, hypothesis, target_status="held" if action_id.startswith("hold") else "running")
        if action_id.startswith("run"):
            review = state["higher_impact_route_reviews"][entity_id]
            admission["constraints"].extend([
                _constraint("proposal", ["payload", "route_digest"], "equals", route_digest(hypothesis["higher_impact_route"])),
                _constraint("proposal", ["payload", "route_review_ref"], "equals", review["review_ref"]),
                _constraint("proposal", ["review_refs"], "set_equals", [review["review_ref"]]),
            ])
        return admission
    if action_id == "route_review_obligation":
        return _created_hypothesis("reviewer_challenge", entity_id)
    if action_id in {"select_review_hypothesis", "run_review_hypothesis", "requeue_review_hypothesis"}:
        row = _review_row(state, entity_id)
        hypothesis_ref = row.get("hypothesis_ref")
        if not isinstance(hypothesis_ref, str):
            raise RecordError("work_queue_admission_hypothesis_missing", entity_id)
        hypothesis = state.get("hypotheses", {}).get(hypothesis_ref)
        if not isinstance(hypothesis, dict):
            raise RecordError("work_queue_admission_hypothesis_missing", hypothesis_ref)
        targets = {
            "select_review_hypothesis": "selected",
            "run_review_hypothesis": "running",
            "requeue_review_hypothesis": "queued",
        }
        return _hypothesis_status_event(hypothesis_ref, hypothesis, target_status=targets[action_id])
    if action_id == "collect_review_evidence":
        row = _review_row(state, entity_id)
        hypothesis_ref = row.get("hypothesis_ref")
        if not isinstance(hypothesis_ref, str):
            raise RecordError("work_queue_admission_hypothesis_missing", entity_id)
        artifacts = state.get("work_queue_context", {}).get("artifacts", {})
        fresh_artifacts = sorted(
            reference
            for reference, artifact in artifacts.items()
            if isinstance(reference, str)
            and isinstance(artifact, dict)
            and isinstance(artifact.get("created_at"), str)
            and artifact.get("environment_ref") == state.get("active_environment_ref")
            and _timestamp_after(artifact["created_at"], row.get("opened_at"))
        ) if isinstance(artifacts, dict) else []
        if not fresh_artifacts:
            raise RecordError("work_queue_admission_fresh_evidence_missing", entity_id)
        return _attempt(
            _constraint("proposal", ["kind"], "equals", "primary"),
            _constraint("proposal", ["hypothesis_ref"], "equals", hypothesis_ref),
            _constraint("proposal", ["experiment_ref"], "equals", entity_id),
            _constraint("proposal", ["recorded_at"], "timestamp_after", row.get("opened_at")),
            _constraint("proposal", ["evidence_refs"], "nonempty_subset_of", fresh_artifacts),
            _constraint(
                "proposal",
                ["observation", "source"],
                "one_of",
                ["broker", "runtime", "source_inspection", "operator"],
            ),
            *_attempt_scope(state),
        )
    if action_id == "supersede_blocked_review_obligation":
        row = _review_row(state, entity_id)
        review_type = "pocinator" if row.get("review_type") == "pocinator" else "regrade"
        finding_id = str(row.get("entity_ref"))
        opening_run_id = row.get("opening_reviewer_run_id")
        if not isinstance(opening_run_id, str):
            raise RecordError("work_queue_admission_review_lineage_missing", entity_id)
        return _review(
            review_type,
            finding_id,
            _current_finding_revision(state, finding_id),
            *_current_finding_review_constraints(state, finding_id),
            _constraint("proposal", ["prior_review_run_ids"], "set_equals", [opening_run_id]),
            _constraint("event", ["payload", "resolves_review_refs"], "set_equals", [entity_id]),
        )
    if action_id == "record_distinct_pocinator_second_review":
        row = _review_row(state, entity_id)
        finding_id = str(row.get("entity_ref"))
        proof = state.get("proof_reviews", {}).get(
            f"{finding_id}:r{_current_finding_revision(state, finding_id)}"
        )
        prior_runs = proof.get("reviewer_run_ids") if isinstance(proof, dict) else None
        prior_reviewers = proof.get("reviewer_ids") if isinstance(proof, dict) else None
        prior_fingerprints = (
            proof.get("reviewer_signer_fingerprints") if isinstance(proof, dict) else None
        )
        if (
            not isinstance(prior_runs, list)
            or not prior_runs
            or any(not isinstance(value, str) for value in prior_runs)
            or not isinstance(prior_reviewers, list)
            or not prior_reviewers
            or any(not isinstance(value, str) for value in prior_reviewers)
            or not isinstance(prior_fingerprints, list)
            or not prior_fingerprints
            or any(not isinstance(value, str) for value in prior_fingerprints)
        ):
            raise RecordError("work_queue_admission_review_lineage_missing", entity_id)
        return _review(
            "pocinator",
            finding_id,
            _current_finding_revision(state, finding_id),
            *_current_finding_review_constraints(state, finding_id),
            _constraint("proposal", ["prior_review_run_ids"], "set_equals", prior_runs),
            _constraint("proposal", ["independence", "reviewer_id"], "not_one_of", prior_reviewers),
            _constraint(
                "proposal",
                ["independence", "reviewer_signer_fingerprint"],
                "not_one_of",
                prior_fingerprints,
            ),
            _constraint("event", ["payload", "resolves_review_refs"], "absent_or_set_equals", []),
        )
    if action_id == "create_control_hypothesis":
        return _created_hypothesis("reviewer_challenge", entity_id)
    if action_id in {"select_control_hypothesis", "run_control_hypothesis", "requeue_control_hypothesis"}:
        control = _control(state, entity_id)
        hypothesis_ref = control.get("hypothesis_ref")
        if not isinstance(hypothesis_ref, str):
            raise RecordError("work_queue_admission_hypothesis_missing", entity_id)
        hypothesis = state.get("hypotheses", {}).get(hypothesis_ref)
        if not isinstance(hypothesis, dict):
            raise RecordError("work_queue_admission_hypothesis_missing", hypothesis_ref)
        targets = {
            "select_control_hypothesis": "selected",
            "run_control_hypothesis": "running",
            "requeue_control_hypothesis": "queued",
        }
        return _hypothesis_status_event(hypothesis_ref, hypothesis, target_status=targets[action_id])
    if action_id == "record_control_primary":
        control = _control(state, entity_id)
        return _attempt(
            _constraint("proposal", ["kind"], "equals", "primary"),
            _constraint("proposal", ["hypothesis_ref"], "equals", control.get("hypothesis_ref")),
            _constraint("proposal", ["experiment_ref"], "equals", entity_id),
            _constraint("proposal", ["control_of"], "set_equals", []),
            *_attempt_scope(state),
        )
    if action_id == "record_control_attempt":
        control = _control(state, entity_id)
        return _attempt(
            _constraint("proposal", ["kind"], "one_of", ["negative_control", "positive_control"]),
            _constraint("proposal", ["hypothesis_ref"], "equals", control.get("hypothesis_ref")),
            _constraint("proposal", ["experiment_ref"], "equals", entity_id),
            _constraint("proposal", ["control_of"], "set_equals", [control.get("primary_attempt_ref")]),
            *_attempt_scope(state),
        )
    if action_id == "create_candidate_hypothesis":
        return _created_hypothesis("candidate", entity_id)
    if action_id == "select_candidate":
        candidate = state.get("candidates", {}).get(entity_id)
        if not isinstance(candidate, dict) or candidate.get("status") != "queued":
            raise RecordError("work_queue_admission_candidate_missing", entity_id)
        return _event(
            _constraint("proposal", ["payload", "candidate_id"], "equals", entity_id),
            _constraint("proposal", ["payload", "status"], "equals", "selected"),
            _constraint("proposal", ["state_changes"], "equals", [{"dimension": "search", "entity_id": entity_id, "previous": "queued", "current": "selected"}]),
            event_type="candidate.selected",
        )
    if action_id == "reopen_candidate":
        return _event(
            _constraint("proposal", ["payload", "candidate_id"], "equals", entity_id),
            _constraint("proposal", ["payload", "status"], "equals", "selected"),
            _constraint("proposal", ["state_changes"], "equals", [{"dimension": "search", "entity_id": entity_id, "previous": "closed", "current": "selected"}]),
            event_type="candidate.reopened",
        )
    if action_id == "record_candidate_skipped":
        return _event(
            _constraint("proposal", ["payload", "candidate_id"], "equals", entity_id),
            _constraint("proposal", ["payload", "status"], "equals", "closed"),
            _constraint("proposal", ["state_changes"], "equals", [{"dimension": "search", "entity_id": entity_id, "previous": "deferred", "current": "closed"}]),
            event_type="candidate.skipped",
        )
    if action_id == "record_claim_adjudication":
        finding_id = _finding_subject(item, state, entity_id)
        filing_refs = set(_filing_ready_review_refs(state, finding_id))
        filing_rows = [
            row
            for row in state.get("outstanding_reviews", [])
            if row.get("review_ref") in filing_refs and row.get("entity_ref") == finding_id
        ]
        required_inputs = sorted(
            {
                reference
                for row in filing_rows
                for reference in [
                    str(row["review_ref"]),
                    *(str(value) for value in row.get("resolution_input_refs", [])),
                ]
            }
        )
        required_statuses = {
            row.get("required_claim_status")
            for row in filing_rows
            if row.get("required_claim_status") is not None
        }
        if len(required_statuses) > 1:
            raise RecordError("work_queue_admission_claim_status_conflict", finding_id)
        claim_constraints = [
            _constraint("proposal", ["recorded_at"], "timestamp_after", row.get("opened_at"))
            for row in filing_rows
        ]
        if required_inputs:
            claim_constraints.append(
                _constraint("proposal", ["input_refs"], "contains_all", required_inputs)
            )
        if required_statuses:
            claim_constraints.append(
                _constraint("proposal", ["verdict"], "equals", next(iter(required_statuses)))
            )
        return _review(
            "claim_adjudication",
            finding_id,
            _current_finding_revision(state, finding_id),
            _constraint(
                "proposal",
                ["independence", "originating_run_id"],
                "equals",
                _current_claim_review_origin(state, finding_id),
            ),
            *claim_constraints,
        )
    if action_id == "record_current_revision_regrade":
        adjudication = state.get("claim_adjudications", {}).get(entity_id)
        prior_run_id = adjudication.get("reviewer_run_id") if isinstance(adjudication, dict) else None
        if not isinstance(prior_run_id, str):
            raise RecordError("work_queue_admission_review_lineage_missing", entity_id)
        return _review(
            "regrade",
            entity_id,
            _current_finding_revision(state, entity_id),
            *_current_finding_review_constraints(state, entity_id),
            _constraint("proposal", ["prior_review_run_ids"], "set_equals", [prior_run_id]),
            _constraint("event", ["payload", "resolves_review_refs"], "absent_or_set_equals", []),
        )
    if action_id == "record_current_revision_pocinator":
        revision = _current_finding_revision(state, entity_id)
        regrade = state.get("regrade_reviews", {}).get(f"{entity_id}:r{revision}")
        prior_run_id = regrade.get("reviewer_run_id") if isinstance(regrade, dict) else None
        if not isinstance(prior_run_id, str):
            raise RecordError("work_queue_admission_review_lineage_missing", entity_id)
        return _review(
            "pocinator",
            entity_id,
            revision,
            *_current_finding_review_constraints(state, entity_id),
            _constraint("proposal", ["prior_review_run_ids"], "set_equals", [prior_run_id]),
            _constraint("event", ["payload", "resolves_review_refs"], "absent_or_set_equals", []),
        )
    if action_id == "record_cold_coverage_review":
        coverage_origin = state.get("coverage_relevant_event_ref")
        if not isinstance(coverage_origin, str):
            raise RecordError("work_queue_admission_coverage_origin_missing", entity_id)
        dispositions = sorted(
            (
                (hypothesis_id, hypothesis.get("status"))
                for hypothesis_id, hypothesis in state.get("hypotheses", {}).items()
                if isinstance(hypothesis, dict)
            ),
            key=lambda item: item[0],
        )
        constraints = [
            _constraint(
                "proposal",
                ["independence", "originating_run_id"],
                "equals",
                coverage_origin,
            ),
            _constraint(
                "proposal",
                ["hypothesis_dispositions"],
                "length_equals",
                len(dispositions),
            )
        ]
        for index, (hypothesis_id, status) in enumerate(dispositions):
            constraints.extend(
                [
                    _constraint(
                        "proposal",
                        ["hypothesis_dispositions", str(index), "hypothesis_ref"],
                        "equals",
                        hypothesis_id,
                    ),
                    _constraint(
                        "proposal",
                        ["hypothesis_dispositions", str(index), "status"],
                        "equals",
                        status,
                    ),
                ]
            )
        return _review("coverage", state["engagement_id"], None, *constraints)
    if action_id == "record_coverage_dry":
        latest = state.get("latest_coverage_review")
        if not isinstance(latest, dict):
            raise RecordError("work_queue_admission_coverage_review_missing", entity_id)
        return _event(
            _constraint("proposal", ["payload", "entity_id"], "equals", state["engagement_id"]),
            _constraint("proposal", ["payload", "status"], "equals", "coverage_dry"),
            _constraint("proposal", ["payload", "coverage_review_ref"], "equals", latest.get("event_ref")),
            event_type="coverage.status_changed",
        )
    if action_id == "record_coverage_blocked":
        latest = state.get("latest_coverage_review")
        if not isinstance(latest, dict):
            raise RecordError("work_queue_admission_coverage_review_missing", entity_id)
        return _event(
            _constraint("proposal", ["payload", "entity_id"], "equals", state["engagement_id"]),
            _constraint("proposal", ["payload", "status"], "equals", "blocked"),
            _constraint("proposal", ["payload", "coverage_review_ref"], "equals", latest.get("event_ref")),
            event_type="coverage.status_changed",
        )
    if action_id == "create_coverage_followup_hypothesis":
        latest = state.get("latest_coverage_review")
        review_refs = latest.get("review_refs") if isinstance(latest, dict) else None
        if not isinstance(review_refs, list) or not review_refs:
            raise RecordError("work_queue_admission_coverage_review_missing", entity_id)
        return _created_hypothesis("reviewer_challenge", review_refs[0])
    if action_id == "request_finding_revision_authority":
        finding_id = _finding_subject(item, state, entity_id)
        latest = state.get("claim_adjudications", {}).get(finding_id)
        if not isinstance(latest, dict):
            raise RecordError("work_queue_admission_adjudication_missing", finding_id)
        filing_refs = _filing_ready_review_refs(state, finding_id)
        return _spec(
            [{"name": "proposal", "argument": "--action-file"}],
            [
                _constraint("proposal", ["action_kind"], "equals", "revise-finding"),
                _constraint("proposal", ["action_version"], "equals", 2),
                _constraint("proposal", ["target", "id"], "equals", finding_id),
                _constraint("proposal", ["target", "expected_revision"], "equals", latest.get("expected_filing_revision")),
                _constraint("proposal", ["target", "claim_state"], "equals", latest.get("status")),
                _constraint("proposal", ["target", "adjudication_event_ref"], "equals", latest.get("event_ref")),
                _constraint("proposal", ["target", "adjudication_review_ref"], "equals", latest.get("review_ref")),
                _constraint("proposal", ["target", "resolves_review_refs"], "set_equals", filing_refs),
                _constraint("proposal", ["proposal", "finding_id"], "equals", finding_id),
                _constraint("proposal", ["proposal", "revision"], "equals", latest.get("expected_filing_revision")),
                _constraint("proposal", ["proposal", "claim_state"], "equals", latest.get("status")),
            ],
        )
    if action_id == "settle_approved_finding_revision":
        finding_id = _finding_subject(item, state, entity_id)
        arguments = action.get("arguments")
        if not isinstance(arguments, list):
            raise RecordError("work_queue_admission_authority_ambiguous", finding_id)
        try:
            request_index = arguments.index("--authority-request-id") + 1
            request_id = arguments[request_index]
        except (ValueError, IndexError):
            raise RecordError("work_queue_admission_authority_ambiguous", finding_id) from None
        request = state.get("authority_requests", {}).get(request_id)
        if (
            not isinstance(request, dict)
            or request.get("action_kind") != "revise-finding"
            or request.get("status") != "approved"
            or not isinstance(request.get("target"), dict)
            or request["target"].get("id") != finding_id
        ):
            raise RecordError("work_queue_admission_authority_ambiguous", finding_id)
        return _spec(
            [{"name": "proposal", "argument": "--file"}],
            [_constraint("proposal", [], "canonical_sha256_equals", request["target"].get("file_digest"))],
        )
    raise RecordError("work_queue_action_admission_unmapped", action_id)
