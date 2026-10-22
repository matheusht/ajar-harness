#!/usr/bin/env python3
"""Negative-only admission gate for a Kanboard native original observation.

The host owns these inputs. A matching native trace and app window still cannot
prove that the model's tool process made the request, or keep credentials out
of the native store. This module has no positive result until those independent
producers exist.
"""

from __future__ import annotations

import hashlib
import json
import re


DISPATCH_ID = re.compile(r"[0-9a-f]{32}\Z")
DIGEST = re.compile(r"[0-9a-f]{64}\Z")
SESSION = re.compile(r"ses_[A-Za-z0-9]{1,64}\Z")
WINDOW_KEYS = {"kind", "dispatch_id", "dispatch_sha256", "session_id", "role",
               "target", "credential_route", "native_origin"}
WINDOW_OPTIONAL = {"topology", "collector_count_before", "collector_max_id_before",
                   "collector_prefix_sha256"}
ROLES = {"target": {"researcher", "resume"},
         "review-target-1": {"reviewer-1"}, "review-target-2": {"reviewer-2"}}


def _object(pairs: list[tuple[str, object]]) -> dict:
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate_key")
        value[key] = item
    return value


def _invalid_constant(_: str) -> None:
    raise ValueError("nonfinite_number")


def _record(data: bytes, limit: int) -> dict | None:
    if not isinstance(data, bytes) or not 0 < len(data) <= limit:
        return None
    try:
        value = json.loads(data, object_pairs_hook=_object, parse_constant=_invalid_constant)
    except (UnicodeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _held(reason: str, dispatch_id: str) -> dict:
    return {"status": "held", "reason": reason, "dispatch_id": dispatch_id,
            "native_request_attributable": False}


def assess(window: dict, dispatch_before: bytes, dispatch_after: dict,
           native_trace: bytes, host_exec_audit: dict | None = None) -> dict:
    """Check handoff consistency; never grant native original-observation credit.

    `dispatch_before` is the exact fsynced pre-dispatch record, before the
    runner's acknowledgement rewrite. The caller must obtain all records from
    host-owned controls, not an agent mount or a caller-authored packet.
    """
    dispatch_id = window.get("dispatch_id", "") if isinstance(window, dict) else ""
    if not isinstance(dispatch_id, str) or not DISPATCH_ID.fullmatch(dispatch_id):
        dispatch_id = ""
    before = _record(dispatch_before, 1024 * 1024)
    if (not isinstance(window, dict) or not isinstance(dispatch_after, dict)
            or before is None or set(window) - WINDOW_KEYS - WINDOW_OPTIONAL
            or not WINDOW_KEYS <= set(window)
            or window.get("kind") != "kanboard-native-window-v1"
            or window.get("credential_route") != "unavailable"
            or window.get("native_origin") != "unproven"
            or not dispatch_id
            or not isinstance(window.get("dispatch_sha256"), str)
            or not DIGEST.fullmatch(window["dispatch_sha256"])
            or not isinstance(window.get("session_id"), str)
            or not SESSION.fullmatch(window["session_id"])
            or not isinstance(window.get("target"), str)
            or window["target"] not in ROLES
            or not isinstance(window.get("role"), str)
            or window["role"] not in ROLES[window["target"]]
            or before.get("kind") != "native-dispatch-v1"
            or dispatch_after.get("kind") != "native-dispatch-v1"
            or host_exec_audit is not None and (
                not isinstance(host_exec_audit, dict)
                or set(host_exec_audit) != {"kind", "complete", "unexpected_exec_count"}
                or host_exec_audit.get("kind") != "host-exec-audit-projection-v1"
                or type(host_exec_audit.get("complete")) is not bool
                or type(host_exec_audit.get("unexpected_exec_count")) is not int
                or host_exec_audit["unexpected_exec_count"] < 0)):
        return _held("invalid_evidence", dispatch_id)
    if (window["dispatch_sha256"] != hashlib.sha256(dispatch_before).hexdigest()
            or any(item.get("dispatch_id") != dispatch_id
                   or item.get("role") != window["role"]
                   or item.get("session_id") != window["session_id"]
                   for item in (before, dispatch_after))):
        return _held("binding_mismatch", dispatch_id)
    if before.get("status") != "unknown_effect" or dispatch_after.get("status") != "acknowledged":
        return _held("dispatch_uncertain", dispatch_id)
    trace = _record(native_trace, 16 * 1024 * 1024)
    if (trace is None or trace.get("kind") != "protected-native-event-trace-v1"
            or trace.get("session_id") != window["session_id"]
            or not isinstance(trace.get("events"), list)
            or not 1 <= len(trace["events"]) <= 10000
            or any(not isinstance(event, dict) or event.get("session_matches") is not True
                   for event in trace["events"])
            or not any(event.get("part_type") == "tool" and event.get("status") == "completed"
                       for event in trace["events"])
            or any(event.get("part_type") == "tool" and event.get("status") in ("error", "failed")
                   for event in trace["events"])):
        return _held("native_trace_unavailable", dispatch_id)
    if (not isinstance(dispatch_after.get("native_trace_sha256"), str)
            or not DIGEST.fullmatch(dispatch_after["native_trace_sha256"])
            or dispatch_after["native_trace_sha256"] != hashlib.sha256(native_trace).hexdigest()):
        return _held("binding_mismatch", dispatch_id)
    if host_exec_audit is not None and host_exec_audit["unexpected_exec_count"]:
        return _held("host_exec_overlap", dispatch_id)
    # A claimed complete audit is not proof of its independent collection.
    return _held("native_credential_route_unavailable", dispatch_id)
