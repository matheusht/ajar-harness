"""Validation and projection for advisory task-local notices."""

from __future__ import annotations

from typing import Any

from engagement_records import RecordError


NOTICE_KEYS = {
    "notice_version", "notice_id", "task_id", "principal_id", "source_event_ref",
    "source_revision", "observation", "applicability", "uncertainty", "predecessor_event_ref",
}
AUTHORITY_KEYS = {
    "authority", "authority_request_ref", "operator_id", "permission", "approved", "claim_state",
    "verdict", "completion", "coverage", "memory_disposition",
}


def _notice_events(events: list[dict[str, Any]], task_id: str | None = None) -> list[dict[str, Any]]:
    return [event for event in events if event.get("event_type") == "observation.recorded"
            and event.get("payload", {}).get("entity_type") == "task_notice"
            and (task_id is None or event.get("payload", {}).get("task_notice", {}).get("task_id") == task_id)]


def validate_notice(events: list[dict[str, Any]], event: dict[str, Any]) -> None:
    payload = event.get("payload", {})
    notice = payload.get("task_notice")
    context = str(event.get("event_id", "unknown"))
    if not isinstance(notice, dict):
        raise RecordError("task_notice_shape_invalid", context)
    if set(notice) & AUTHORITY_KEYS or any(key in AUTHORITY_KEYS for key in payload if key != "task_notice"):
        raise RecordError("task_notice_authority_field", context)
    if set(notice) != NOTICE_KEYS:
        raise RecordError("task_notice_shape_invalid", context)
    if notice.get("notice_version") != 1:
        raise RecordError("task_notice_shape_invalid", context)
    actor = event.get("actor", {})
    if actor.get("role") != "broker" or event.get("provenance", {}).get("actor") != actor:
        raise RecordError("task_notice_principal_mismatch", context)
    for field in ("notice_id", "source_event_ref", "source_revision", "observation", "applicability", "uncertainty"):
        if not isinstance(notice.get(field), str) or not notice[field].strip():
            raise RecordError("task_notice_shape_invalid", f"{context}:{field}")
    if sum(len(notice[field]) for field in ("observation", "applicability", "uncertainty")) > 400:
        raise RecordError("task_notice_too_long", context)
    existing = _notice_events(events, notice["task_id"])
    if len(existing) >= 5:
        raise RecordError("task_notice_limit_exceeded", context)
    existing_ids = {row["payload"]["task_notice"]["notice_id"] for row in existing}
    if notice["notice_id"] in existing_ids:
        raise RecordError("task_notice_id_collision", notice["notice_id"])
    task_definition = next((row for row in events if row.get("event_type") == "observation.recorded" and row.get("payload", {}).get("entity_type") == "task_definition" and row.get("payload", {}).get("task_id") == notice["task_id"]), None)
    if task_definition is None:
        raise RecordError("task_notice_task_unbound", context)
    predecessor = notice.get("predecessor_event_ref")
    existing_event_ids = {row["event_id"] for row in existing}
    if predecessor is not None and (not isinstance(predecessor, str) or predecessor not in existing_event_ids):
        raise RecordError("task_notice_predecessor_invalid", context)
    source = next((row for row in events if row.get("event_id") == notice["source_event_ref"]), None)
    if source is None or source.get("event_type") != "observation.recorded" or source.get("payload", {}).get("entity_type") == "task_notice":
        raise RecordError("task_notice_source_invalid", context)
    if source.get("engagement_id") != event.get("engagement_id") or source.get("payload", {}).get("task_id") != notice["task_id"]:
        raise RecordError("task_notice_cross_task", context)
    if source.get("actor", {}).get("id") != notice["principal_id"]:
        raise RecordError("task_notice_principal_mismatch", context)
    if source.get("payload", {}).get("source_revision") != notice["source_revision"]:
        raise RecordError("task_notice_source_revision_mismatch", context)
    first_notice_sequence = min((row.get("sequence", 0) for row in existing), default=event.get("sequence", 10**18))
    initials = [row for row in events if row.get("event_type") == "observation.recorded"
                and row.get("payload", {}).get("entity_type") == "independent_initial"
                and row.get("payload", {}).get("task_id") == notice["task_id"]
                and row.get("sequence", 0) < first_notice_sequence]
    if len({row.get("actor", {}).get("id") for row in initials}) < 2 or notice["principal_id"] not in {row.get("actor", {}).get("id") for row in initials}:
        raise RecordError("task_notice_independence_missing", context)
    if event.get("entity_refs") != [notice["source_event_ref"]] + ([predecessor] if predecessor else []) or event.get("evidence_refs") or event.get("review_refs") or event.get("finding_refs") or event.get("artifact_refs"):
        raise RecordError("task_notice_hidden_reference", context)


def compile_projection(events: list[dict[str, Any]], *, task_id: str, after_sequence: int = 0) -> dict[str, Any]:
    if not any(row.get("event_type") == "observation.recorded" and row.get("payload", {}).get("entity_type") == "task_definition" and row.get("payload", {}).get("task_id") == task_id for row in events):
        raise RecordError("task_notice_task_unbound", task_id)
    notices = []
    for event in _notice_events(events, task_id):
        if event.get("sequence", 0) <= after_sequence:
            continue
        notice = dict(event["payload"]["task_notice"])
        notice.update({"event_id": event["event_id"], "sequence": event["sequence"], "recorded_at": event["recorded_at"]})
        notices.append(notice)
    return {"schema_version": 1, "task_id": task_id, "after_sequence": after_sequence, "notices": notices}
