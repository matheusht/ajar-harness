"""Build portable evidence from protected application observations.

The core validates sanitized evidence. Runtime adapters own collection and this
module never invokes a model, provider, target, or generic telemetry service.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any


SCHEMA_VERSION = 1
ROOT_KEYS = {
    "cases",
    "chain_state",
    "cleanup",
    "hypothesis",
    "observer_boundary",
    "repeatability",
    "scenario_id",
    "schema_version",
    "source_pins",
}
HYPOTHESIS_KEYS = {
    "agent_discovery_credited",
    "allowed_effects",
    "authority",
    "conditions",
    "hypothesis_id",
    "next_test",
    "nonclaims",
    "objective",
    "origin",
    "statement",
    "status",
}
CASE_KEYS = {
    "application_receipts",
    "bypass_receipts",
    "case_id",
    "dispatch",
    "host_activity",
    "producer_observer_visible",
    "producer_observer_writable",
    "response",
    "trace",
}
DISPATCH_KEYS = {
    "close_sequence",
    "dispatch_id",
    "open_sequence",
    "request_intent_sha256",
    "session_binding",
    "tool_binding",
}
TRACE_KEYS = {
    "attribution_verified",
    "connects",
    "process_binding",
    "raw_trace_retained",
    "subtree_exit",
}
CONNECT_KEYS = {"address_class", "admitted", "destination_class"}
RECEIPT_KEYS = {
    "case_id",
    "effect",
    "effect_after_sha256",
    "effect_before_sha256",
    "method",
    "outcome",
    "path_class",
    "request_sha256",
    "response_sha256",
    "route_class",
    "sequence",
    "status_code",
}
RESPONSE_KEYS = {"sha256", "status_code"}
HOST_ACTIVITY_KEYS = {"case_id", "kind", "sequence"}
OBSERVER_KEYS = {
    "allowed_address_classes",
    "allowed_nonroute_destination_classes",
    "available",
    "declared_route",
    "producer_storage_visibility",
    "qualification_scope",
    "route_completeness_claimed",
    "storage_owner",
}
CLEANUP_KEYS = {"checks", "status", "stop_verified"}
CLEANUP_CHECK_KEYS = {
    "observer_endpoints_released",
    "observer_processes_stopped",
    "owned_resources_only",
    "private_scratch_removed",
    "producer_processes_stopped",
    "raw_capture_removed",
}
CHAIN_KEYS = {
    "consumed",
    "contrary_results",
    "missing_transitions",
    "produced",
    "unfinished_conditions",
}
PRODUCED_KEYS = {"producer_case_id", "state_id", "state_sha256"}
CONSUMED_KEYS = {"consumer_case_id", "observed_sha256", "state_id"}
CONTRARY_KEYS = {"case_id", "meaning"}
MISSING_KEYS = {"case_id", "transition"}
UNFINISHED_KEYS = {"condition", "status"}
SENSITIVE_KEYS = {
    "access_token",
    "api_key",
    "apikey",
    "auth",
    "authorization",
    "capability",
    "client_secret",
    "cookie",
    "credential",
    "credentials",
    "jwt",
    "password",
    "passwd",
    "private_key",
    "proxy_authorization",
    "raw_body",
    "refresh_token",
    "request_body",
    "response_body",
    "secret",
    "set_cookie",
    "signed_url",
    "token",
}
COLLAPSED_SENSITIVE_KEYS = {
    "accesstoken",
    "apikey",
    "authorization",
    "capability",
    "clientsecret",
    "cookie",
    "credential",
    "jwt",
    "password",
    "privatekey",
    "proxyauthorization",
    "refreshtoken",
    "secret",
    "setcookie",
    "signedurl",
    "token",
}
SECRET_VALUE_RE = re.compile(
    r"(?i)(?:\b(?:basic|bearer)\s+[A-Za-z0-9._~+/=-]{8,}|"
    r"\bsk(?:-|_)(?:(?:live|proj)(?:-|_))?[A-Za-z0-9_-]{12,}|"
    r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}|"
    r"[?&](?:access_token|api_key|signature|token|x-amz-signature)=)"
)


class EvidenceError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, allow_nan=False, indent=2, sort_keys=True) + "\n"
    ).encode()


def digest(value: Any) -> str:
    data = value if isinstance(value, bytes) else canonical_bytes(value)
    return hashlib.sha256(data).hexdigest()


def copy_json(value: Any) -> Any:
    return json.loads(canonical_bytes(value))


def validate_portable_json_shape(value: Any) -> None:
    if value is None or type(value) in {str, bool, int}:
        return
    if type(value) is float:
        if not math.isfinite(value):
            raise EvidenceError("nonportable_json_value")
        return
    if type(value) is list:
        for item in value:
            validate_portable_json_shape(item)
        return
    if type(value) is dict:
        if any(type(key) is not str for key in value):
            raise EvidenceError("nonportable_json_value")
        for item in value.values():
            validate_portable_json_shape(item)
        return
    raise EvidenceError("nonportable_json_value")


def reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise EvidenceError("input_json_duplicate_key")
        result[key] = value
    return result


def reject_nonfinite_json(value: str) -> None:
    raise EvidenceError("input_json_nonfinite")


def is_sha256(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def normalized_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).lower()).strip("_")


def sensitive_key(value: object) -> bool:
    normalized = normalized_key(value)
    if normalized in SENSITIVE_KEYS:
        return True
    if any(
        normalized.startswith(alias + "_")
        or normalized.endswith("_" + alias)
        or ("_" + alias + "_") in normalized
        for alias in SENSITIVE_KEYS
    ):
        return True
    collapsed = normalized.replace("_", "")
    return any(
        collapsed == alias
        or collapsed.startswith(alias)
        or collapsed.endswith(alias)
        for alias in COLLAPSED_SENSITIVE_KEYS
    )


def contains_sensitive(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            sensitive_key(key) or contains_sensitive(nested)
            for key, nested in value.items()
        )
    if isinstance(value, (list, tuple)):
        if len(value) == 2 and isinstance(value[0], str) and sensitive_key(value[0]):
            return True
        return any(contains_sensitive(item) for item in value)
    return isinstance(value, str) and SECRET_VALUE_RE.search(value) is not None


def require_keys(value: Any, expected: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise EvidenceError(label + "_schema_mismatch")
    return value


def require_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise EvidenceError(label + "_missing")
    return value


def require_integer(
    value: Any,
    label: str,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    if (
        type(value) is not int
        or (minimum is not None and value < minimum)
        or (maximum is not None and value > maximum)
    ):
        raise EvidenceError(label + "_schema_mismatch")
    return value


def require_string_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item for item in value
    ):
        raise EvidenceError(label + "_schema_mismatch")
    return value


def validate_source_schema(source_pins: Any) -> None:
    source = require_keys(source_pins, {"manifest", "manifest_sha256"}, "source_pins")
    manifest = require_keys(
        source["manifest"],
        {"dependencies", "files", "parent_version_ids", "source_id", "version_id"},
        "source_manifest",
    )
    require_string(manifest["source_id"], "source_id")
    require_string(manifest["version_id"], "source_version")
    require_string_list(manifest["parent_version_ids"], "parent_versions")
    for label in ("files", "dependencies"):
        values = manifest[label]
        if not isinstance(values, dict) or any(
            not isinstance(name, str) or not name or not is_sha256(value)
            for name, value in values.items()
        ):
            raise EvidenceError("source_" + label + "_schema_mismatch")
    if not manifest["files"] or not is_sha256(source["manifest_sha256"]):
        raise EvidenceError("source_pins_schema_mismatch")


def validate_receipt(receipt: Any, label: str) -> None:
    receipt = require_keys(receipt, RECEIPT_KEYS, label)
    for key in (
        "case_id",
        "effect",
        "method",
        "outcome",
        "path_class",
        "route_class",
    ):
        require_string(receipt[key], label + "_" + key)
    for key in (
        "effect_after_sha256",
        "effect_before_sha256",
        "request_sha256",
        "response_sha256",
    ):
        if not is_sha256(receipt[key]):
            raise EvidenceError(label + "_digest_mismatch")
    require_integer(receipt["sequence"], label + "_sequence", minimum=0)
    require_integer(
        receipt["status_code"], label + "_status", minimum=100, maximum=599
    )
    if receipt["effect"] not in {"changed", "unchanged"}:
        raise EvidenceError(label + "_effect_schema_mismatch")
    changed = receipt["effect_before_sha256"] != receipt["effect_after_sha256"]
    if (receipt["effect"] == "changed") != changed:
        raise EvidenceError(label + "_effect_digest_mismatch")


def validate_case(case: Any) -> None:
    case = require_keys(case, CASE_KEYS, "case")
    case_id = require_string(case["case_id"], "case_id")
    for key in ("application_receipts", "bypass_receipts", "host_activity"):
        if not isinstance(case[key], list):
            raise EvidenceError("case_" + key + "_schema_mismatch")
    for receipt in case["application_receipts"] + case["bypass_receipts"]:
        validate_receipt(receipt, "receipt")
        if receipt["case_id"] != case_id:
            raise EvidenceError("receipt_case_mismatch")
    for activity in case["host_activity"]:
        activity = require_keys(activity, HOST_ACTIVITY_KEYS, "host_activity")
        if activity["case_id"] != case_id:
            raise EvidenceError("host_activity_case_or_sequence_mismatch")
        require_integer(activity["sequence"], "host_activity_sequence", minimum=0)
        require_string(activity["kind"], "host_activity_kind")
    response = require_keys(case["response"], RESPONSE_KEYS, "response")
    if not is_sha256(response["sha256"]):
        raise EvidenceError("response_schema_mismatch")
    require_integer(
        response["status_code"], "response_status", minimum=100, maximum=599
    )

    if case["dispatch"] is None:
        if case["trace"] is not None:
            raise EvidenceError("host_trace_must_be_absent")
        if case["producer_observer_visible"] is not None or case[
            "producer_observer_writable"
        ] is not None:
            raise EvidenceError("host_producer_probe_must_be_absent")
        return

    dispatch = require_keys(case["dispatch"], DISPATCH_KEYS, "dispatch")
    for key in ("dispatch_id", "session_binding", "tool_binding"):
        require_string(dispatch[key], key)
    if not is_sha256(dispatch["request_intent_sha256"]):
        raise EvidenceError("request_intent_digest_mismatch")
    require_integer(dispatch["open_sequence"], "dispatch_open_sequence", minimum=0)
    require_integer(dispatch["close_sequence"], "dispatch_close_sequence", minimum=0)
    trace = require_keys(case["trace"], TRACE_KEYS, "trace")
    process_binding = require_string(trace["process_binding"], "process_binding")
    if process_binding != "exact_spawned_subtree":
        raise EvidenceError("process_attribution_unsupported")
    require_string(trace["subtree_exit"], "subtree_exit")
    if not isinstance(trace["attribution_verified"], bool) or not isinstance(
        trace["raw_trace_retained"], bool
    ):
        raise EvidenceError("trace_boolean_mismatch")
    if not isinstance(trace["connects"], list):
        raise EvidenceError("trace_connects_schema_mismatch")
    for connect in trace["connects"]:
        connect = require_keys(connect, CONNECT_KEYS, "connect")
        require_string(connect["address_class"], "address_class")
        require_string(connect["destination_class"], "destination_class")
        if not isinstance(connect["admitted"], bool):
            raise EvidenceError("connect_admission_schema_mismatch")
    if not isinstance(case["producer_observer_visible"], bool):
        raise EvidenceError("producer_observer_visibility_missing")
    if not isinstance(case["producer_observer_writable"], bool):
        raise EvidenceError("producer_observer_writability_missing")


def validate_chain_schema(chain_state: Any, case_ids: set[str]) -> None:
    chain = require_keys(chain_state, CHAIN_KEYS, "chain_state")
    specs = [
        ("produced", PRODUCED_KEYS, "producer_case_id"),
        ("consumed", CONSUMED_KEYS, "consumer_case_id"),
        ("contrary_results", CONTRARY_KEYS, "case_id"),
        ("missing_transitions", MISSING_KEYS, "case_id"),
    ]
    for name, keys, case_key in specs:
        if not isinstance(chain[name], list):
            raise EvidenceError(name + "_schema_mismatch")
        for item in chain[name]:
            item = require_keys(item, keys, name)
            case_reference = require_string(item[case_key], name + "_" + case_key)
            if case_reference not in case_ids:
                raise EvidenceError(name + "_case_mismatch")
            for key, value in item.items():
                if key.endswith("sha256"):
                    if not is_sha256(value):
                        raise EvidenceError(name + "_digest_mismatch")
                else:
                    require_string(value, name + "_" + key)
    if not isinstance(chain["unfinished_conditions"], list):
        raise EvidenceError("unfinished_conditions_schema_mismatch")
    for item in chain["unfinished_conditions"]:
        item = require_keys(item, UNFINISHED_KEYS, "unfinished_condition")
        require_string(item["condition"], "unfinished_condition")
        require_string(item["status"], "unfinished_status")


def validate_run_schema(run: Any) -> None:
    run = require_keys(run, ROOT_KEYS, "input")
    if type(run["schema_version"]) is not int or run["schema_version"] != SCHEMA_VERSION:
        raise EvidenceError("unsupported_schema_version")
    require_string(run["scenario_id"], "scenario_id")
    validate_source_schema(run["source_pins"])
    hypothesis = require_keys(run["hypothesis"], HYPOTHESIS_KEYS, "hypothesis")
    for key in (
        "authority",
        "hypothesis_id",
        "objective",
        "origin",
        "statement",
        "status",
    ):
        require_string(hypothesis[key], "hypothesis_" + key)
    if hypothesis["next_test"] is not None:
        require_string(hypothesis["next_test"], "hypothesis_next_test")
    if not isinstance(hypothesis["agent_discovery_credited"], bool) or not isinstance(
        hypothesis["conditions"], dict
    ):
        raise EvidenceError("hypothesis_state_schema_mismatch")
    if hypothesis["agent_discovery_credited"] is True:
        raise EvidenceError("discovery_credit_unsupported")
    require_string_list(hypothesis["allowed_effects"], "allowed_effects")
    require_string_list(hypothesis["nonclaims"], "nonclaims")

    if not isinstance(run["cases"], list) or not run["cases"]:
        raise EvidenceError("cases_schema_mismatch")
    for case in run["cases"]:
        validate_case(case)
    case_ids = [case["case_id"] for case in run["cases"]]
    if len(case_ids) != len(set(case_ids)):
        raise EvidenceError("duplicate_case_id")
    validate_chain_schema(run["chain_state"], set(case_ids))

    observer = require_keys(run["observer_boundary"], OBSERVER_KEYS, "observer")
    require_string(observer["declared_route"], "declared_route")
    require_string(observer["producer_storage_visibility"], "producer_storage_visibility")
    require_string(observer["qualification_scope"], "qualification_scope")
    require_string(observer["storage_owner"], "storage_owner")
    require_string_list(observer["allowed_address_classes"], "allowed_address_classes")
    require_string_list(
        observer["allowed_nonroute_destination_classes"],
        "allowed_nonroute_destination_classes",
    )
    if not isinstance(observer["available"], bool) or not isinstance(
        observer["route_completeness_claimed"], bool
    ):
        raise EvidenceError("observer_boolean_mismatch")

    cleanup = require_keys(run["cleanup"], CLEANUP_KEYS, "cleanup")
    if (
        not isinstance(cleanup["checks"], dict)
        or set(cleanup["checks"]) != CLEANUP_CHECK_KEYS
        or any(
            not isinstance(name, str)
            or not name
            or not isinstance(value, bool)
            for name, value in cleanup["checks"].items()
        )
        or not isinstance(cleanup["stop_verified"], bool)
    ):
        raise EvidenceError("cleanup_schema_mismatch")
    require_string(cleanup["status"], "cleanup_status")
    repeatability = require_keys(
        run["repeatability"], {"normalized_match", "runs"}, "repeatability"
    )
    if repeatability["normalized_match"] is not None and not isinstance(
        repeatability["normalized_match"], bool
    ):
        raise EvidenceError("repeatability_schema_mismatch")
    require_integer(repeatability["runs"], "repeatability_runs", minimum=1)


def source_pins_valid(run: dict[str, Any]) -> bool:
    source = run["source_pins"]
    return digest(source["manifest"]) == source["manifest_sha256"]


def response_matches(case: dict[str, Any], receipt: dict[str, Any]) -> bool:
    return (
        case["response"]["status_code"] == receipt["status_code"]
        and case["response"]["sha256"] == receipt["response_sha256"]
    )


def receipt_is_ordered(case: dict[str, Any], receipt: dict[str, Any]) -> bool:
    dispatch = case["dispatch"]
    return dispatch["open_sequence"] < receipt["sequence"] < dispatch["close_sequence"]


def trace_is_complete(case: dict[str, Any], observer: dict[str, Any]) -> bool:
    trace = case["trace"]
    admitted = [connect for connect in trace["connects"] if connect["admitted"]]
    nonroute = [connect for connect in trace["connects"] if not connect["admitted"]]
    return (
        trace["attribution_verified"] is True
        and trace["subtree_exit"] == "observed_zero"
        and trace["raw_trace_retained"] is False
        and len(admitted) == 1
        and admitted[0]["address_class"] in observer["allowed_address_classes"]
        and all(
            connect["destination_class"]
            in observer["allowed_nonroute_destination_classes"]
            for connect in nonroute
        )
    )


def ordinary_binding(case: dict[str, Any], observer: dict[str, Any]) -> bool:
    receipts = case["application_receipts"]
    connects = [
        connect for connect in case["trace"]["connects"] if connect["admitted"]
    ]
    declared = observer["declared_route"]
    return (
        len(receipts) == 1
        and not case["bypass_receipts"]
        and len(connects) == 1
        and connects[0]["destination_class"] == declared
        and receipts[0]["route_class"] == declared
        and receipts[0]["request_sha256"]
        == case["dispatch"]["request_intent_sha256"]
        and response_matches(case, receipts[0])
        and receipt_is_ordered(case, receipts[0])
    )


def bypass_binding(case: dict[str, Any], observer: dict[str, Any]) -> bool:
    receipts = case["bypass_receipts"]
    connects = [
        connect for connect in case["trace"]["connects"] if connect["admitted"]
    ]
    if len(receipts) != 1 or case["application_receipts"] or len(connects) != 1:
        return False
    destination = connects[0]["destination_class"]
    return (
        destination != observer["declared_route"]
        and receipts[0]["route_class"] == destination
        and receipts[0]["request_sha256"]
        == case["dispatch"]["request_intent_sha256"]
        and response_matches(case, receipts[0])
        and receipt_is_ordered(case, receipts[0])
    )


def host_replay_valid(case: dict[str, Any], observer: dict[str, Any]) -> bool:
    receipts = case["application_receipts"]
    activity = case["host_activity"]
    return (
        case["dispatch"] is None
        and case["trace"] is None
        and len(receipts) == 1
        and not case["bypass_receipts"]
        and receipts[0]["route_class"] == observer["declared_route"]
        and len(activity) == 2
        and [item["kind"] for item in activity]
        == ["host_client_open", "host_client_close"]
        and activity[0]["sequence"] < receipts[0]["sequence"] < activity[1]["sequence"]
        and response_matches(case, receipts[0])
    )


def classify_case(case: dict[str, Any], observer: dict[str, Any]) -> str:
    if case["dispatch"] is None:
        return "host_replay" if host_replay_valid(case, observer) else "unavailable"
    if not trace_is_complete(case, observer) or case["host_activity"]:
        return "unavailable"
    if ordinary_binding(case, observer):
        return "observed"
    if bypass_binding(case, observer):
        return "capture_claim_refused"
    return "unavailable"


def chain_state_valid(run: dict[str, Any]) -> bool:
    produced = run["chain_state"]["produced"]
    consumed = run["chain_state"]["consumed"]
    cases = {case["case_id"]: case for case in run["cases"]}
    by_id = {item["state_id"]: item for item in produced}
    if len(by_id) != len(produced):
        return False

    def sole_receipt(case_id: str) -> dict[str, Any] | None:
        case = cases[case_id]
        receipts = case["application_receipts"] + case["bypass_receipts"]
        if len(receipts) != 1:
            return None
        return receipts[0]

    expected_changed = sorted(
        (case["case_id"], receipt["effect_after_sha256"])
        for case in run["cases"]
        for receipt in case["application_receipts"] + case["bypass_receipts"]
        if receipt["effect"] == "changed"
    )
    represented_changed = sorted(
        (item["producer_case_id"], item["state_sha256"]) for item in produced
    )
    if represented_changed != expected_changed:
        return False

    for item in produced:
        receipt = sole_receipt(item["producer_case_id"])
        if (
            receipt is None
            or receipt["effect"] != "changed"
            or receipt["effect_before_sha256"] == receipt["effect_after_sha256"]
            or receipt["effect_after_sha256"] != item["state_sha256"]
        ):
            return False
    for item in consumed:
        producer = by_id.get(item["state_id"])
        receipt = sole_receipt(item["consumer_case_id"])
        if producer is None or receipt is None:
            return False
        producer_receipt = sole_receipt(producer["producer_case_id"])
        consumer_case = cases[item["consumer_case_id"]]
        if (
            producer_receipt is None
            or consumer_case["dispatch"] is None
            or item["observed_sha256"] != producer["state_sha256"]
            or receipt["effect_before_sha256"] != item["observed_sha256"]
            or producer_receipt["sequence"]
            >= consumer_case["dispatch"]["open_sequence"]
        ):
            return False
    return True


def capture_limitations_preserved(
    run: dict[str, Any], outcomes: dict[str, str]
) -> bool:
    refused = {
        case_id
        for case_id, outcome in outcomes.items()
        if outcome == "capture_claim_refused"
    }
    missing = {
        (item["case_id"], item["transition"])
        for item in run["chain_state"]["missing_transitions"]
    }
    observer_receipt_missing = {
        case_id
        for case_id, transition in missing
        if transition == "application-observer-receipt"
    }
    return (
        run["observer_boundary"]["route_completeness_claimed"] is False
        and observer_receipt_missing == refused
    )


def effects_within_declared_authority(run: dict[str, Any]) -> bool:
    allowed = set(run["hypothesis"]["allowed_effects"])
    return all(
        receipt["effect"] != "changed" or receipt["outcome"] in allowed
        for case in run["cases"]
        for receipt in case["application_receipts"] + case["bypass_receipts"]
    )


def case_observation(case: dict[str, Any], status: str) -> dict[str, Any]:
    result = {
        "attribution": (
            "host_replay"
            if status == "host_replay"
            else (
                case["trace"]["process_binding"]
                if status in {"observed", "capture_claim_refused"}
                else "unavailable"
            )
        ),
        "case_id": case["case_id"],
        "status": status,
    }
    selected = (
        case["application_receipts"]
        if case["application_receipts"]
        else case["bypass_receipts"]
    )
    if len(selected) == 1 and status != "unavailable":
        receipt = selected[0]
        result.update(
            {
                "effect": {
                    "after_sha256": receipt["effect_after_sha256"],
                    "before_sha256": receipt["effect_before_sha256"],
                    "classification": receipt["effect"],
                },
                "request": {
                    "method": receipt["method"],
                    "path_class": receipt["path_class"],
                    "route_class": receipt["route_class"],
                    "sha256": receipt["request_sha256"],
                },
                "result": {
                    "outcome": receipt["outcome"],
                    "response_sha256": receipt["response_sha256"],
                    "status_code": receipt["status_code"],
                },
            }
        )
    if case["dispatch"] is not None:
        result["runtime_binding"] = {
            "dispatch_id": case["dispatch"]["dispatch_id"],
            "session": case["dispatch"]["session_binding"],
            "tool": case["dispatch"]["tool_binding"],
        }
    if status == "capture_claim_refused":
        result["missing_transition"] = "application-observer-receipt"
    return result


def connection_projection(case: dict[str, Any]) -> dict[str, Any] | None:
    if case["trace"] is None:
        return None
    nonroute_counts: dict[str, int] = {}
    admitted = 0
    for connect in case["trace"]["connects"]:
        if connect["admitted"]:
            admitted += 1
        else:
            name = connect["destination_class"]
            nonroute_counts[name] = nonroute_counts.get(name, 0) + 1
    return {
        "admitted_count": admitted,
        "nonroute_counts": nonroute_counts,
        "total_connect_syscalls": len(case["trace"]["connects"]),
    }


def evaluate_observation_run(run: dict[str, Any]) -> dict[str, dict[str, Any]]:
    validate_portable_json_shape(run)
    try:
        canonical_bytes(run)
    except (TypeError, ValueError) as error:
        raise EvidenceError("nonportable_json_value") from error
    if contains_sensitive(run):
        raise EvidenceError("sensitive_evidence_detected")
    validate_run_schema(run)
    observer = run["observer_boundary"]
    dispatched = [case for case in run["cases"] if case["dispatch"] is not None]
    host_cases = [case for case in run["cases"] if case["dispatch"] is None]
    outcomes = {
        case["case_id"]: classify_case(case, observer) for case in run["cases"]
    }
    checks = {
        "capture_limitations_preserved": capture_limitations_preserved(run, outcomes),
        "causal_order_valid": all(
            len(case["application_receipts"] + case["bypass_receipts"]) == 1
            and (
                host_replay_valid(case, observer)
                if case["dispatch"] is None
                else receipt_is_ordered(
                    case,
                    (case["application_receipts"] + case["bypass_receipts"])[0],
                )
            )
            for case in run["cases"]
        ),
        "chain_state_consistent": chain_state_valid(run),
        "cleanup_complete": run["cleanup"]["status"] == "complete"
        and all(run["cleanup"]["checks"].values()),
        "dispatch_binding_complete": all(
            bool(case["dispatch"]["session_binding"])
            and bool(case["dispatch"]["tool_binding"])
            for case in dispatched
        ),
        "effects_within_declared_authority": effects_within_declared_authority(run),
        "host_activity_absent_during_dispatch": all(
            not case["host_activity"] for case in dispatched
        ),
        "provided_host_replays_valid": all(
            host_replay_valid(case, observer) for case in host_cases
        ),
        "observer_available": observer["available"] is True,
        "observer_channel_protected": observer["producer_storage_visibility"]
        == "absent_from_producer_namespace"
        and all(case["producer_observer_visible"] is False for case in dispatched),
        "producer_cannot_write_observer": all(
            case["producer_observer_writable"] is False for case in dispatched
        ),
        "repeatability_record_consistent": run["repeatability"]["runs"] >= 1
        and (
            (
                run["repeatability"]["runs"] == 1
                and run["repeatability"]["normalized_match"] is None
            )
            or (
                run["repeatability"]["runs"] >= 2
                and run["repeatability"]["normalized_match"] is True
            )
        ),
        "request_binding_unambiguous": all(
            outcomes[case["case_id"]] != "unavailable" for case in run["cases"]
        ),
        "sensitive_patterns_not_detected": True,
        "source_manifest_self_integrity": source_pins_valid(run),
        "stop_verified": run["cleanup"]["stop_verified"] is True,
        "trace_complete": all(trace_is_complete(case, observer) for case in dispatched),
        "provided_route_evidence_classified": all(
            connect["destination_class"] == observer["declared_route"]
            or outcomes[case["case_id"]] == "capture_claim_refused"
            for case in dispatched
            for connect in case["trace"]["connects"]
            if connect["admitted"]
        ),
    }
    status = (
        "observation_packet_valid"
        if all(checks.values())
        else "observation_packet_invalid"
    )
    observations = [
        case_observation(case, outcomes[case["case_id"]])
        for case in sorted(run["cases"], key=lambda item: item["case_id"])
    ]
    hypothesis = copy_json(run["hypothesis"])
    observation = {
        "case_observations": observations,
        "chain_state": copy_json(run["chain_state"]),
        "scenario_id": run["scenario_id"],
        "schema_version": SCHEMA_VERSION,
        "source_pins": copy_json(run["source_pins"]),
    }
    evidence = {
        "application_observer": copy_json(observer),
        "attribution_scope": observer["qualification_scope"],
        "case_bindings": [
            {
                "case_id": item["case_id"],
                "connection_projection": connection_projection(
                    next(
                        case
                        for case in run["cases"]
                        if case["case_id"] == item["case_id"]
                    )
                ),
                "process_attribution": item["attribution"],
                "status": item["status"],
            }
            for item in observations
        ],
        "cleanup": copy_json(run["cleanup"]),
        "collection": {
            "application_bodies_retained": "not_observed_caller_sanitization_required",
            "network_scope": "caller_declared_not_independently_verified",
            "provider_calls": "not_observed",
            "raw_process_trace_retained": False,
            "sensitive_scan": "defense_in_depth_no_pattern_match",
            "target_calls": "not_observed",
        },
        "coverage": {
            "capture_refusal_cases": sorted(
                case_id
                for case_id, outcome in outcomes.items()
                if outcome == "capture_claim_refused"
            ),
            "host_replay_cases": sorted(
                case_id
                for case_id, outcome in outcomes.items()
                if outcome == "host_replay"
            ),
            "observed_cases": sorted(
                case_id
                for case_id, outcome in outcomes.items()
                if outcome == "observed"
            ),
            "unavailable_cases": sorted(
                case_id
                for case_id, outcome in outcomes.items()
                if outcome == "unavailable"
            ),
        },
        "repeatability": copy_json(run["repeatability"]),
        "schema_version": SCHEMA_VERSION,
    }
    artifacts = {
        "evidence.json": digest(evidence),
        "hypothesis.json": digest(hypothesis),
        "observation.json": digest(observation),
    }
    result = {
        "artifacts": artifacts,
        "case_outcomes": outcomes,
        "checks": checks,
        "nonclaims": copy_json(hypothesis["nonclaims"]),
        "provider_calls": "not_observed",
        "scenario_id": run["scenario_id"],
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "target_calls": "not_observed",
    }
    bundle = {
        "evidence": evidence,
        "hypothesis": hypothesis,
        "observation": observation,
        "result": result,
    }
    if contains_sensitive(bundle):
        raise EvidenceError("sensitive_evidence_detected")
    return bundle


def publish_atomic(output: Path, files: dict[str, bytes]) -> None:
    lexical_output = Path(output)
    if (
        not lexical_output.is_absolute()
        or lexical_output.is_symlink()
        or os.path.lexists(lexical_output)
        or not lexical_output.parent.is_dir()
    ):
        raise EvidenceError("output_must_be_absent_with_existing_parent")
    output = lexical_output.resolve()
    temporary = Path(
        tempfile.mkdtemp(prefix="." + output.name + ".", dir=output.parent)
    )
    try:
        os.chmod(temporary, 0o700)
        for name, data in files.items():
            path = temporary / name
            path.write_bytes(data)
            os.chmod(path, 0o600)
        os.replace(temporary, output)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def write_bundle(bundle: dict[str, dict[str, Any]], output: Path) -> None:
    if set(bundle) != {"evidence", "hypothesis", "observation", "result"}:
        raise EvidenceError("bundle_inventory_mismatch")
    if contains_sensitive(bundle):
        raise EvidenceError("sensitive_evidence_detected")
    files = {}
    artifacts = {}
    for name in ("hypothesis.json", "observation.json", "evidence.json"):
        key = name.removesuffix(".json")
        files[name] = canonical_bytes(bundle[key])
        artifacts[name] = hashlib.sha256(files[name]).hexdigest()
    result = copy_json(bundle["result"])
    result["artifacts"] = artifacts
    files["result.json"] = canonical_bytes(result)
    publish_atomic(output, files)


def publish_rejection(output: Path, code: str) -> None:
    if output.exists():
        return
    failure = {
        "failure_code": code,
        "provider_calls": "not_observed",
        "schema_version": SCHEMA_VERSION,
        "status": "observation_packet_rejected",
        "target_calls": "not_observed",
    }
    try:
        publish_atomic(output, {"result.json": canonical_bytes(failure)})
    except (EvidenceError, OSError):
        pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.input.is_symlink():
        raise SystemExit("--input must not be a symlink")
    try:
        input_path = args.input.resolve(strict=True)
    except FileNotFoundError as error:
        raise SystemExit("--input must be a regular file") from error
    if not input_path.is_file():
        raise SystemExit("--input must be a regular file")
    if (
        not args.output.is_absolute()
        or args.output.is_symlink()
        or os.path.lexists(args.output)
        or not args.output.parent.is_dir()
    ):
        raise SystemExit("--output must be absent under an existing directory")
    output = args.output.resolve()
    try:
        try:
            run = json.loads(
                input_path.read_text(),
                object_pairs_hook=reject_duplicate_json_keys,
                parse_constant=reject_nonfinite_json,
            )
        except (json.JSONDecodeError, OSError, UnicodeError) as error:
            raise EvidenceError("input_json_invalid") from error
        bundle = evaluate_observation_run(run)
        write_bundle(bundle, output)
    except EvidenceError as error:
        publish_rejection(output, error.code)
        print(
            json.dumps(
                {"failure_code": error.code, "status": "observation_packet_rejected"},
                sort_keys=True,
            )
        )
        return 1
    except Exception:
        code = "internal_evaluator_error"
        publish_rejection(output, code)
        print(
            json.dumps(
                {"failure_code": code, "status": "observation_packet_rejected"},
                sort_keys=True,
            )
        )
        return 1
    print(
        json.dumps(
            {
                "provider_calls": bundle["result"]["provider_calls"],
                "status": bundle["result"]["status"],
                "target_calls": bundle["result"]["target_calls"],
            },
            sort_keys=True,
        )
    )
    return 0 if bundle["result"]["status"] == "observation_packet_valid" else 1


if __name__ == "__main__":
    raise SystemExit(main())
