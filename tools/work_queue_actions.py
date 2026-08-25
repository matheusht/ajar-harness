#!/usr/bin/env python3
"""Typed single-step actions for reducer-owned engagement work queues."""

from __future__ import annotations

import copy
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from engagement_records import RecordError, canonical_json_bytes, sha256_bytes
from engagement_state import WORK_QUEUE_CLASS_ORDER, _filing_blocking_review_error, finding_revision_lane_id, hypothesis_dispositions_hash


SESSION_KINDS = frozenset({"ordinary_bounded", "fresh_independent_reviewer", "operator_required"})
PRINCIPALS = frozenset({"orchestrator", "hunter", "broker", "independent_reviewer", "operator_only"})
EFFECTS = frozenset({"closes_item", "advances_item", "conditional"})
EXECUTION_PRINCIPALS = frozenset({"broker", "operator_only"})
QUEUE_INSPECTION_COMMANDS = frozenset({"next", "list", "gate"})


def queue_command_payload(command: str, state: dict[str, Any], engagement: Path) -> dict[str, Any]:
    """Build one canonical inspection envelope from an already-bound reduction."""

    if command not in QUEUE_INSPECTION_COMMANDS:
        raise RecordError("queue_command_invalid", command)
    raw_queue = state.get("work_queue")
    if not isinstance(raw_queue, list):
        raise RecordError("work_queue_missing", "reduced state has no work queue")
    blocking_count = sum(item.get("blocking") is True for item in raw_queue if isinstance(item, dict))
    total_count = len(raw_queue)
    control_status = state.get("queue_control", {}).get("status") if isinstance(state.get("queue_control"), dict) else None
    coverage_status = state.get("coverage")
    should_block = control_status == "active" and coverage_status == "active" and blocking_count > 0
    result: dict[str, Any] = {
        "schema_version": 1,
        "command": command,
        "ok": True,
        "engagement_id": state.get("engagement_id"),
        "state_hash": sha256_bytes(canonical_json_bytes(state)),
        "ledger_hash": state.get("ledger_hash"),
        "source_hashes": copy.deepcopy(state.get("source_hashes")),
        "queue": {
            "blocking_count": blocking_count,
            "control_status": control_status,
            "coverage_status": coverage_status,
            "decision": "block" if should_block else "release",
            "has_blocking_work": blocking_count > 0,
            "nonblocking_count": total_count - blocking_count,
            "should_block": should_block,
            "total_count": total_count,
        },
    }
    if command == "list":
        # Listing is reducer truth, not a stale executable plan for lower-ranked dependencies.
        result["items"] = copy.deepcopy(raw_queue)
    elif command == "next":
        first = next((item for item in raw_queue if isinstance(item, dict) and item.get("blocking") is True), None)
        if first is None:
            first = next((item for item in raw_queue if isinstance(item, dict)), None)
        result["item"] = None if first is None else decorate_work_queue_item(first, state, engagement)
    return result


def queue_gate_exit(payload: dict[str, Any]) -> int:
    queue = payload.get("queue")
    return 3 if isinstance(queue, dict) and queue.get("should_block") is True else 0


def queue_command_error_payload(command: str, error: RecordError) -> dict[str, Any]:
    """Return no target path, record bytes, or validation details on a machine branch."""

    return {"schema_version": 1, "command": command, "ok": False, "error": {"code": error.code}}


def _required_input(name: str, value_type: str, placeholder: str, *requirements: str) -> dict[str, Any]:
    return {"name": name, "type": value_type, "placeholder": placeholder, "requirements": list(requirements)}


def _action(
    action_id: str,
    command: str,
    engagement: Path,
    arguments: list[str],
    required_inputs: list[dict[str, Any]],
    *,
    session_kind: str,
    principal: str,
    effect: str,
    launchable: bool = True,
) -> dict[str, Any]:
    if session_kind not in SESSION_KINDS or principal not in PRINCIPALS or effect not in EFFECTS:
        raise RecordError("work_queue_action_class_invalid", f"{session_kind}:{principal}:{effect}")
    execution_principal = "broker" if launchable else "operator_only"
    if execution_principal not in EXECUTION_PRINCIPALS:
        raise RecordError("work_queue_execution_principal_invalid", execution_principal)
    # Preserve the venv launcher path. Resolving this symlink would silently discard the
    # environment whose installed dependencies made the rendered command executable.
    python = str(Path(sys.executable).absolute())
    tool = str(Path(__file__).with_name("run-engagement.py").resolve())
    return {
        "action_id": action_id,
        "operation": {"tool": "run-engagement", "command": command},
        "command": command,
        "arguments": ["--engagement", str(engagement), *arguments],
        "local_invocation": {
            "schema_version": 1,
            "launcher": {"kind": "local_python_tool", "resolution": "render_time", "python": python, "tool": tool},
            "argv": [python, tool, command, "--engagement", str(engagement), *arguments],
        },
        "session_kind": session_kind,
        "principal": principal,
        "execution_principal": execution_principal,
        "effect": effect,
        "launchable": launchable,
        "required_inputs": required_inputs,
        "recompute_after": True,
    }


def _event_action(action_id: str, engagement: Path, placeholder: str, requirements: list[str], *, effect: str = "closes_item") -> dict[str, Any]:
    return _action(
        action_id,
        "append-event",
        engagement,
        ["--file", placeholder],
        [_required_input("event_file", "path", placeholder, *requirements, "actor and provenance.actor/session_id are the current process-bound broker identity")],
        session_kind="ordinary_bounded",
        principal="orchestrator",
        effect=effect,
    )


def _attempt_action(action_id: str, engagement: Path, placeholder: str, requirements: list[str], *, effect: str) -> dict[str, Any]:
    return _action(
        action_id,
        "append-attempt",
        engagement,
        ["--file", placeholder],
        [_required_input("attempt_file", "path", placeholder, *requirements, "the hunter supplies the bounded observation; actor and provenance.actor/session_id are the current process-bound broker recorder identity")],
        session_kind="ordinary_bounded",
        principal="hunter",
        effect=effect,
    )


def _review_action(
    action_id: str,
    engagement: Path,
    *,
    review_type: str,
    entity_type: str,
    entity_id: str,
    requirements: list[str],
    effect: str,
) -> dict[str, Any]:
    return _action(
        action_id,
        "record-review",
        engagement,
        [
            "--file", "<review-json>",
            "--event", "<review-event-json>",
            "--actor-id", "<broker-id>",
            "--session-id", "<broker-session-id>",
            "--signature", "<review-signature>",
            "--allowed-signers", "<reviewer-allowed-signers>",
        ],
        [
            _required_input("review_file", "path", "<review-json>", f"valid independently produced {review_type} review", f"binds exact {entity_type} {entity_id}", *requirements),
            _required_input("review_event_file", "path", "<review-event-json>", "typed notebook completion event for the exact review and entity"),
            _required_input("broker_id", "string", "<broker-id>", "current runtime-identity broker actor id"),
            _required_input("broker_session_id", "string", "<broker-session-id>", "current runtime-identity broker session id"),
            _required_input("review_signature", "path", "<review-signature>", "SSH signature over canonical review bytes by the independent reviewer"),
            _required_input("reviewer_allowed_signers", "path", "<reviewer-allowed-signers>", "bytes match the reviewer signer digest pinned by signed scope"),
        ],
        session_kind="fresh_independent_reviewer",
        principal="independent_reviewer",
        effect=effect,
    )


def _request_revision_action(engagement: Path, finding_id: str) -> dict[str, Any]:
    return _action(
        "request_finding_revision_authority",
        "request-authority",
        engagement,
        [
            "--request-id", "<request-id>", "--action-kind", "revise-finding",
            "--action-file", "<revise-finding-v2-action-json>", "--lane-id", "<code-owned-lane-id>",
            "--actor-role", "broker", "--actor-id", "<broker-id>", "--session-id", "<broker-session-id>",
            "--recorded-at", "<recorded-at>", "--expires-at", "<expires-at>", "--reason", "<reason>",
        ],
        [
            _required_input("request_id", "string", "<request-id>", "new engagement-unique request id"),
            _required_input("action_file", "path", "<revise-finding-v2-action-json>", "canonical action_version 2 proposal", f"binds exact latest adjudication and current revision for finding {finding_id}", "resolves the exact reducer-computed filing-ready review set"),
            _required_input("lane_id", "string", "<code-owned-lane-id>", "equals finding_revision_lane_id for the exact target"),
            _required_input("broker_id", "string", "<broker-id>", "current runtime-identity broker actor id"),
            _required_input("broker_session_id", "string", "<broker-session-id>", "current runtime-identity broker session id and action principal"),
            _required_input("recorded_at", "rfc3339", "<recorded-at>", "current request time"),
            _required_input("expires_at", "rfc3339", "<expires-at>", "future authority expiry"),
            _required_input("reason", "string", "<reason>", "non-sensitive rationale"),
        ],
        session_kind="ordinary_bounded",
        principal="broker",
        effect="closes_item",
    )


def _settle_approved_revision_action(engagement: Path, request: dict[str, Any]) -> dict[str, Any]:
    target = request.get("target")
    application = request.get("application")
    if not isinstance(target, dict) or not isinstance(application, dict):
        raise RecordError("work_queue_approved_revision_context_missing", str(request.get("request_id")))
    resolution_args = [argument for review_ref in target.get("resolves_review_refs", []) for argument in ("--resolve-review", review_ref)]
    return _action(
        "settle_approved_finding_revision",
        "settle-approved-revision",
        engagement,
        [
            "--file", "<approved-finding-proposal-json>",
            *resolution_args,
            "--operator-id", str(application["operator_id"]),
            "--recorded-at", "<recorded-at>",
            "--authority-request-id", str(request["request_id"]),
            "--lane-id", str(request["lane_id"]),
            "--executor-id", str(application["executor_id"]),
            "--session-id", str(application["session_id"]),
        ],
        [
            _required_input("proposal_file", "path", "<approved-finding-proposal-json>", f"canonical bytes equal proposal inside {application['action_path']}", f"sha256 is exact approved target digest {target['file_digest']}"),
            _required_input("recorded_at", "rfc3339", "<recorded-at>", "fresh current command time", "the atomic command applies while authority is live or records objective expiry after the recorded deadline"),
        ],
        session_kind="ordinary_bounded",
        principal="broker",
        effect="conditional",
    )


def _approved_revision_request(state: dict[str, Any], finding_id: str) -> dict[str, Any] | None:
    latest = state.get("claim_adjudications", {}).get(finding_id)
    filing_refs = sorted(row["review_ref"] for row in _filing_rows(state, finding_id))
    matches = [
        request for request in state.get("authority_requests", {}).values()
        if request.get("action_kind") == "revise-finding"
        and request.get("status") == "approved"
        and isinstance(request.get("target"), dict)
        and request["target"].get("id") == finding_id
        and isinstance(latest, dict)
        and request["target"].get("expected_revision") == latest.get("expected_filing_revision")
        and request["target"].get("claim_state") == latest.get("status")
        and request["target"].get("adjudication_event_ref") == latest.get("event_ref")
        and request["target"].get("adjudication_review_ref") == latest.get("review_ref")
        and request["target"].get("resolves_review_refs") == filing_refs
        and request.get("lane_id") == finding_revision_lane_id(request["target"])
        and _filing_blocking_review_error(state, finding_id) is None
    ]
    if len(matches) > 1:
        raise RecordError("work_queue_approved_revision_ambiguous", finding_id)
    return matches[0] if matches else None


def _revision_action(engagement: Path, finding_id: str, state: dict[str, Any]) -> dict[str, Any]:
    """Choose from record state only; live-versus-expired settles atomically in the command."""

    approved_request = _approved_revision_request(state, finding_id)
    return (
        _request_revision_action(engagement, finding_id)
        if approved_request is None
        else _settle_approved_revision_action(engagement, approved_request)
    )


def _effective_claim_status(state: dict[str, Any], finding_id: str) -> str | None:
    latest = state.get("claim_adjudications", {}).get(finding_id)
    if isinstance(latest, dict):
        return latest.get("status")
    finding = state.get("findings", {}).get(finding_id)
    return finding.get("status") if isinstance(finding, dict) else None


def _filing_pending(state: dict[str, Any], finding_id: str) -> bool:
    return any(item.get("class") == "finding_revision_pending" and item.get("entity", {}).get("id") == finding_id for item in state.get("work_queue", []))


def _fresh_adjudication_after_row(state: dict[str, Any], finding_id: str, row: dict[str, Any]) -> bool:
    latest = state.get("claim_adjudications", {}).get(finding_id)
    try:
        required_refs = {str(row["review_ref"]), *(str(reference) for reference in row.get("resolution_input_refs", []))}
        return bool(
            isinstance(latest, dict)
            and datetime.fromisoformat(latest["recorded_at"].replace("Z", "+00:00"))
            > datetime.fromisoformat(row["opened_at"].replace("Z", "+00:00"))
            and required_refs.issubset(set(latest["input_refs"]))
            and (row.get("required_claim_status") is None or latest.get("status") == row["required_claim_status"])
        )
    except (KeyError, TypeError, ValueError):
        return False


def _all_filing_rows_adjudicated(state: dict[str, Any], finding_id: str) -> bool:
    filing_rows = _filing_rows(state, finding_id)
    return bool(filing_rows) and all(_fresh_adjudication_after_row(state, finding_id, row) for row in filing_rows)


def _filing_rows(state: dict[str, Any], finding_id: str) -> list[dict[str, Any]]:
    return [
        row for row in state.get("outstanding_reviews", [])
        if row.get("entity_ref") == finding_id
        and (
            (row.get("review_type") == "legacy_adjudication" and row.get("status") == "pending")
            or (row.get("review_type") == "regrade" and row.get("status") in {"correction_required", "evidence_collected"})
            or (row.get("review_type") == "regrade_escalation" and row.get("status") == "evidence_collected")
            or (row.get("review_type") == "pocinator" and row.get("status") == "correction_required")
        )
    ]


def _claim_action(
    engagement: Path,
    finding_id: str,
    state: dict[str, Any],
    *,
    for_filing: bool = False,
    review_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    status = _effective_claim_status(state, finding_id)
    rows = review_rows or []
    if for_filing:
        requirements = [
            "binds the current filed revision",
            "becomes the exact latest adjudication for a contiguous filing request",
        ]
        requirements.append("uses a legal terminal verdict for the current claim state")
        effect = "advances_item"
    elif status == "needs_review":
        requirements = ["verdict is supported, contaminated, or refuted; confirmed is not a legal needs_review transition", "supported advances the same item; contaminated or refuted closes it"]
        effect = "conditional"
    elif status == "supported":
        requirements = ["verdict is confirmed, contaminated, or refuted so effective claim status leaves {needs_review, supported}"]
        effect = "closes_item"
    else:
        raise RecordError("work_queue_claim_status_invalid", f"{finding_id}:{status}")
    if rows:
        exact_refs = sorted({
            reference
            for row in rows
            for reference in [str(row["review_ref"]), *(str(value) for value in row.get("resolution_input_refs", []))]
        })
        requirements.extend([
            f"input_refs includes every exact review obligation {exact_refs}",
            "the immutable review recorded_at is later than every bound obligation opening",
        ])
        required_statuses = {row.get("required_claim_status") for row in rows if row.get("required_claim_status") is not None}
        if required_statuses:
            if len(required_statuses) != 1:
                raise RecordError("work_queue_review_claim_status_conflict", finding_id)
            requirements.append(f"verdict is exactly {next(iter(required_statuses))}")
    return _review_action("record_claim_adjudication", engagement, review_type="claim_adjudication", entity_type="finding", entity_id=finding_id, requirements=requirements, effect=effect)


def _hypothesis_action(item_class: str, engagement: Path, entity_id: str, detail: Any, state: dict[str, Any]) -> dict[str, Any]:
    hypothesis = state.get("hypotheses", {}).get(entity_id)
    if not isinstance(hypothesis, dict):
        raise RecordError("work_queue_hypothesis_missing", entity_id)
    status = hypothesis.get("status")
    requirements = ["valid hypothesis.status_changed notebook event", f"binds exact hypothesis {entity_id}"]
    effect = "closes_item"
    if item_class == "hypothesis_unrouted":
        if status == "queued":
            requirements.extend(["changes queued to selected", "records the exact selected next experiment"])
            effect = "advances_item"
        elif status == "selected":
            requirements.extend(["changes selected to running", "records the bounded route now being executed"])
        else:
            raise RecordError("work_queue_hypothesis_status_invalid", f"{entity_id}:{status}")
    elif item_class == "hypothesis_ran_unadjudicated":
        requirements.extend(["cites every matching unadjudicated attempt in experiment_refs or control_refs", "uses a legal next search status", "preserves exact supporting/conflicting evidence and unresolved questions"])
        routed_rows = [row for row in state.get("outstanding_reviews", []) if row.get("status") == "routed" and row.get("hypothesis_ref") == entity_id]
        if routed_rows:
            requirements.extend(["includes every fresh matching attempt in supporting_evidence_refs", "each supporting ref is recorded after the routed review opened so that exact row advances to evidence_collected"])
    elif item_class == "hypothesis_open_route":
        requirements.extend([f"disposes exact next_route {detail}", "sets next_route to null", "uses a legal next search status"])
    else:
        requirements.extend([f"removes exact unresolved question {detail}", "preserves every other unresolved question", "uses a legal next search status"])
    return _event_action("record_hypothesis_disposition", engagement, "<hypothesis-disposition-event-json>", requirements, effect=effect)


def _review_obligation_action(engagement: Path, item_id: str, state: dict[str, Any]) -> dict[str, Any]:
    row = next((candidate for candidate in state.get("outstanding_reviews", []) if candidate.get("review_ref") == item_id), None)
    if not isinstance(row, dict):
        raise RecordError("work_queue_review_missing", item_id)
    review_type = row.get("review_type")
    status = row.get("status")
    finding_id = str(row.get("entity_ref"))
    if review_type == "legacy_adjudication":
        filing_rows = _filing_rows(state, finding_id)
        return _revision_action(engagement, finding_id, state) if _filing_pending(state, finding_id) and _all_filing_rows_adjudicated(state, finding_id) else _claim_action(engagement, finding_id, state, for_filing=True, review_rows=filing_rows)
    if review_type in {"regrade", "regrade_escalation"} and status == "pending":
        return _event_action(
            "route_review_obligation",
            engagement,
            "<review-obligation-hypothesis-created-event-json>",
            ["valid hypothesis.created notebook event", "origin_type is reviewer_challenge", f"origin_ref is exact opening event {item_id}", "status is queued"],
            effect="advances_item",
        )
    if review_type in {"regrade", "regrade_escalation"} and status == "routed":
        hypothesis_ref = row.get("hypothesis_ref")
        hypothesis = state.get("hypotheses", {}).get(hypothesis_ref)
        if not isinstance(hypothesis, dict):
            raise RecordError("work_queue_review_hypothesis_missing", item_id)
        hypothesis_status = hypothesis.get("status")
        if hypothesis_status == "queued":
            return _event_action("select_review_hypothesis", engagement, "<review-hypothesis-selected-event-json>", [f"binds exact hypothesis {hypothesis_ref}", "changes queued to selected"], effect="advances_item")
        if hypothesis_status == "selected":
            return _event_action("run_review_hypothesis", engagement, "<review-hypothesis-running-event-json>", [f"binds exact hypothesis {hypothesis_ref}", "changes selected to running"], effect="advances_item")
        if hypothesis_status == "running":
            return _attempt_action("collect_review_evidence", engagement, "<review-primary-attempt-json>", ["valid fresh primary attempt", f"hypothesis_ref is exact {hypothesis_ref}", f"recorded_at is later than opening event {item_id}", "binds active environment and committed evidence"], effect="advances_item")
        if hypothesis_status in {"held", "exhausted", "deferred", "blocked", "closed"}:
            return _event_action("requeue_review_hypothesis", engagement, "<review-hypothesis-requeued-event-json>", [f"binds exact hypothesis {hypothesis_ref}", f"changes {hypothesis_status} to queued", "preserves all adjudicated evidence refs"], effect="advances_item")
        raise RecordError("work_queue_review_hypothesis_status_invalid", f"{item_id}:{hypothesis_status}")
    if (review_type, status) in {("regrade", "blocked"), ("pocinator", "blocked")}:
        subject_type = "pocinator" if review_type == "pocinator" else "regrade"
        verdicts = ["verified", "needs_rework", "claim_mismatch", "reward_hacked", "blocked"] if subject_type == "pocinator" else ["confirmed", "confirmed_with_correction", "escalation_found", "needs_more_evidence", "refuted", "blocked"]
        return _review_action(
            "supersede_blocked_review_obligation",
            engagement,
            review_type=subject_type,
            entity_type="finding",
            entity_id=finding_id,
            requirements=[f"records whichever schema-valid verdict the fresh review reaches from {verdicts}", f"completion event resolves_review_refs is exactly [{item_id}]", f"prior_review_run_ids includes the signed run opened by {item_id}", "fresh completion removes only the named row before applying its own verdict", "a new blocking or correction verdict replaces debt rather than erasing it"],
            effect="conditional",
        )
    if review_type == "pocinator" and status == "correction_required":
        finding = state.get("findings", {}).get(finding_id)
        proof = state.get("proof_reviews", {}).get(f"{finding_id}:r{finding.get('revision')}") if isinstance(finding, dict) else None
        if isinstance(proof, dict) and proof.get("terminal_status") == "pending_second_review":
            prior_runs = proof.get("reviewer_run_ids")
            if not isinstance(prior_runs, list) or not prior_runs:
                raise RecordError("work_queue_pocinator_prior_run_missing", item_id)
            return _review_action(
                "record_distinct_pocinator_second_review",
                engagement,
                review_type="pocinator",
                entity_type="finding",
                entity_id=finding_id,
                requirements=["records whichever schema-valid Pocinator verdict the fresh review reaches", "reviewer identity is distinct from every prior proof reviewer", f"prior_review_run_ids includes every exact prior pocinator run {sorted(prior_runs)}", "binds the exact current claim tuple and records high_value truthfully"],
                effect="conditional",
            )
    if (review_type, status) in {("regrade", "correction_required"), ("regrade", "evidence_collected"), ("regrade_escalation", "evidence_collected"), ("pocinator", "correction_required")}:
        filing_rows = _filing_rows(state, finding_id)
        return _revision_action(engagement, finding_id, state) if _filing_pending(state, finding_id) and _all_filing_rows_adjudicated(state, finding_id) else _claim_action(engagement, finding_id, state, for_filing=True, review_rows=filing_rows)
    raise RecordError("work_queue_review_status_unmapped", f"{review_type}:{status}")


def _control_action(engagement: Path, routing_ref: str, state: dict[str, Any]) -> dict[str, Any]:
    control = next((candidate for candidate in state.get("control_candidates", []) if candidate.get("routing_event_id") == routing_ref), None)
    if not isinstance(control, dict):
        raise RecordError("work_queue_control_missing", routing_ref)
    hypothesis_ref = control.get("hypothesis_ref")
    primary_ref = control.get("primary_attempt_ref")
    if hypothesis_ref is None:
        return _event_action("create_control_hypothesis", engagement, "<control-hypothesis-created-event-json>", ["valid hypothesis.created notebook event", "origin_type is reviewer_challenge", f"origin_ref is exact negative routing event {routing_ref}", "status is queued"], effect="advances_item")
    hypothesis = state.get("hypotheses", {}).get(hypothesis_ref)
    if not isinstance(hypothesis, dict):
        raise RecordError("work_queue_control_hypothesis_missing", routing_ref)
    status = hypothesis.get("status")
    if status == "queued":
        return _event_action("select_control_hypothesis", engagement, "<control-hypothesis-selected-event-json>", [f"binds exact hypothesis {hypothesis_ref}", "changes queued to selected"], effect="advances_item")
    if status == "selected":
        return _event_action("run_control_hypothesis", engagement, "<control-hypothesis-running-event-json>", [f"binds exact hypothesis {hypothesis_ref}", "changes selected to running"], effect="advances_item")
    if primary_ref is None and status == "running":
        return _attempt_action("record_control_primary", engagement, "<control-primary-attempt-json>", ["valid primary attempt", f"hypothesis_ref is exact {hypothesis_ref}", f"experiment_ref is exact routing event {routing_ref}", "control_of is empty"], effect="advances_item")
    if primary_ref is None and status in {"held", "exhausted", "deferred", "blocked", "closed"}:
        return _event_action("requeue_control_hypothesis", engagement, "<control-hypothesis-requeued-event-json>", [f"binds exact hypothesis {hypothesis_ref}", f"changes {status} to queued", "preserves adjudicated refs"], effect="advances_item")
    if primary_ref is not None:
        return _attempt_action("record_control_attempt", engagement, "<control-attempt-json>", ["valid negative_control or positive_control attempt", f"hypothesis_ref is exact {hypothesis_ref}", f"experiment_ref is exact routing event {routing_ref}", f"control_of contains exact prior primary {primary_ref}"], effect="closes_item")
    raise RecordError("work_queue_control_progress_invalid", routing_ref)


def decorate_work_queue_item(item: dict[str, Any], state: dict[str, Any], engagement: Path) -> dict[str, Any]:
    """Attach exactly one reducer-valid action; callers must reduce again after it."""

    result = copy.deepcopy(item)
    item_class = item.get("class")
    entity = item.get("entity")
    if item_class not in WORK_QUEUE_CLASS_ORDER or not isinstance(entity, dict):
        raise RecordError("work_queue_item_unmapped", str(item_class))
    entity_id = str(entity.get("id"))
    entity_type = str(entity.get("type"))
    detail = entity.get("detail")
    engagement = engagement.absolute()

    if item_class in {"hypothesis_ran_unadjudicated", "hypothesis_unrouted", "hypothesis_open_route", "hypothesis_unresolved_question"}:
        action = _hypothesis_action(item_class, engagement, entity_id, detail, state)
    elif item_class == "claim_unadjudicated":
        action = _claim_action(engagement, entity_id, state, review_rows=_filing_rows(state, entity_id))
    elif item_class == "review_obligation_open":
        action = _review_obligation_action(engagement, entity_id, state)
    elif item_class == "finding_revision_pending":
        action = _revision_action(engagement, entity_id, state)
    elif item_class == "finding_unproved":
        finding = state.get("findings", {}).get(entity_id)
        if not isinstance(finding, dict):
            raise RecordError("work_queue_finding_missing", entity_id)
        progress = state.get("regrade_reviews", {}).get(f"{entity_id}:r{finding.get('revision')}")
        if not isinstance(progress, dict) or progress.get("verdict") != "confirmed":
            action = _review_action("record_current_revision_regrade", engagement, review_type="regrade", entity_type=entity_type, entity_id=entity_id, requirements=["binds the current filed revision", "records whichever schema-valid regrade verdict the fresh review reaches", "prior_review_run_ids includes the current finding adjudication review run", "only a confirmed result enables the proof-review stage; every other verdict remains actionable reducer truth"], effect="conditional")
        else:
            action = _review_action("record_current_revision_pocinator", engagement, review_type="pocinator", entity_type=entity_type, entity_id=entity_id, requirements=["binds the same current filed revision", "records whichever schema-valid Pocinator verdict the fresh review reaches", f"prior_review_run_ids includes exact regrade run {progress['reviewer_run_id']}", "only a verified end-to-end result closes proof debt; every other verdict remains actionable reducer truth"], effect="conditional")
    elif item_class == "candidate_undisposed":
        action = _event_action("create_candidate_hypothesis", engagement, "<hypothesis-created-event-json>", ["valid hypothesis.created notebook event", "origin_type is candidate", f"origin_ref is exact selected candidate {entity_id}"], effect="closes_item")
    elif item_class == "deferred_candidate_unreviewed":
        action = _event_action("record_candidate_skipped", engagement, "<candidate-skipped-event-json>", ["valid candidate.skipped notebook event", f"binds exact deferred candidate {entity_id}", "changes deferred to closed"], effect="closes_item")
    elif item_class == "control_candidate_unverified":
        action = _control_action(engagement, entity_id, state)
    elif item_class == "awaiting_operator":
        action = _action(
            "operator_resolve_authority",
            "resolve-authority",
            engagement,
            ["--request-id", entity_id, "--resolution", "<resolution>", "--operator-id", "<operator-id>", "--session-id", "<operator-session-id>", "--recorded-at", "<recorded-at>", "--reason", "<reason>"],
            [
                _required_input("resolution", "enum", "<resolution>", "one of approved, rejected, expired, superseded"),
                _required_input("operator_id", "string", "<operator-id>", "matches the current signed-scope operator"),
                _required_input("operator_session_id", "string", "<operator-session-id>", "operator-console-bound session id"),
                _required_input("recorded_at", "rfc3339", "<recorded-at>", "current operator resolution time"),
                _required_input("reason", "string", "<reason>", "non-sensitive operator rationale"),
            ],
            session_kind="operator_required",
            principal="operator_only",
            effect="closes_item",
            launchable=False,
        )
    elif item_class == "coverage_review_missing":
        latest = state.get("latest_coverage_review")
        current_dispositions_hash = hypothesis_dispositions_hash(state.get("hypotheses", {}))
        review_is_current = (
            isinstance(latest, dict)
            and latest.get("event_sequence") == state.get("coverage_relevant_sequence")
            and latest.get("hypothesis_dispositions_hash") == current_dispositions_hash
        )
        if review_is_current and latest.get("verdict") == "coverage_dry":
            action = _event_action("record_coverage_dry", engagement, "<coverage-status-event-json>", ["valid coverage.status_changed notebook event", f"coverage_review_ref is exact current review event {latest['event_ref']}", "reviewed hypothesis dispositions remain unchanged", "sets active coverage to coverage_dry"], effect="closes_item")
        elif review_is_current and latest.get("verdict") == "blocked":
            action = _event_action("record_coverage_blocked", engagement, "<coverage-status-event-json>", ["valid coverage.status_changed notebook event", f"coverage_review_ref is exact current blocked review event {latest['event_ref']}", "reviewed hypothesis dispositions remain unchanged", "sets active coverage to blocked without manufacturing dry coverage"], effect="closes_item")
        elif review_is_current and latest.get("verdict") == "continue":
            review_refs = latest.get("review_refs")
            if not isinstance(review_refs, list) or not review_refs or not isinstance(review_refs[0], str):
                raise RecordError("work_queue_coverage_review_context_missing", str(latest.get("event_ref")))
            action = _event_action(
                "create_coverage_followup_hypothesis",
                engagement,
                "<hypothesis-created-event-json>",
                [
                    "valid hypothesis.created notebook event",
                    "origin_type is reviewer_challenge",
                    f"origin_ref is exact current cold-review record {review_refs[0]}",
                    "the bounded hypothesis follows the review's omitted-branch challenge or required next action",
                    "initial search status is queued",
                ],
                effect="advances_item",
            )
        else:
            action = _review_action("record_cold_coverage_review", engagement, review_type="coverage", entity_type=entity_type, entity_id=entity_id, requirements=["fresh cold review binds every current hypothesis disposition", "records whichever schema-valid outcome the cold review reaches: continue, coverage_dry, or blocked", "budget_bounded is reserved to the outer driver"], effect="conditional")
    else:  # pragma: no cover - guarded by the closed order
        raise RecordError("work_queue_item_unmapped", str(item_class))
    result["next_action"] = action
    return result
