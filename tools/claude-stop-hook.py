#!/usr/bin/env python3
"""Explicit legacy Claude Code Stop adapter for the target-local work queue.

Legacy launchers opt in through --print-additional-settings; repository sessions do not
inherit this hook from project settings.

The platform contract is intentionally tiny: stdout is always exactly one JSON object and this
process never exits 2.  A valid top-level ``decision: block`` is emitted only after the same locked
transaction both derives the queue and commits a generic ``session.end_checked`` notebook event.
"""

from __future__ import annotations

import json
import os
import secrets
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from engagement_records import RecordError, canonical_json_bytes, sha256_bytes
from driver_action_admission import BROKER_ENDPOINT_ENV, forward_stop_check_to_broker
from engagement_state import (
    _reduce_engagement_unchecked,
    append_event,
    base_event,
    existing_engagement_transaction,
    read_governed_file,
    read_ledger,
    utc_now,
)
from work_queue_actions import queue_command_payload

ROOT = Path(__file__).resolve().parents[1]
ACTIVE_ENGAGEMENT_ENV = "HARNESS_ACTIVE_ENGAGEMENT"
EXPECTED_LEDGER_HASH_ENV = "HARNESS_EXPECTED_LEDGER_HASH"
EXPECTED_SOURCE_HASHES_ENV = "HARNESS_EXPECTED_SOURCE_HASHES"
BLOCK_BUDGET = 6
MAX_STDIN_BYTES = 1024 * 1024
SESSION_NAMESPACE = b"llm-redteam-harness:session-end:v1:"
SESSION_AUDIT_STATE_KEYS = frozenset({
    "event_count",
    "last_event_id",
    "ledger_hash",
    "source_hashes",
})


class ReleaseTurn(Exception):
    """Internal control flow for an intentional fail-open release."""


@dataclass(frozen=True)
class HookInput:
    session_ref: str
    stop_hook_active: bool
    request_ref: str


@dataclass(frozen=True)
class SessionBaseline:
    ledger_hash: str
    events_hash: str
    attempts_hash: str
    artifacts_hash: str


@dataclass(frozen=True)
class GateView:
    state_hash: str
    queue_digest: str
    blocking_count: int
    total_count: int
    control_status: str
    coverage_status: str
    should_block: bool


@dataclass(frozen=True)
class EndDecision:
    decision: str
    reason_code: str
    confirmed_consecutive_blocks: int


def emit(value: dict[str, Any]) -> None:
    sys.stdout.buffer.write(canonical_json_bytes(value))


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ReleaseTurn
        value[key] = item
    return value


def parse_hook_input() -> HookInput:
    raw = sys.stdin.buffer.read(MAX_STDIN_BYTES + 1)
    if not raw or len(raw) > MAX_STDIN_BYTES:
        raise ReleaseTurn
    try:
        incoming = json.loads(raw, object_pairs_hook=_reject_duplicate_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError, ReleaseTurn):
        raise ReleaseTurn from None
    if not isinstance(incoming, dict):
        raise ReleaseTurn

    # Stop and SubagentStop are structurally distinct. Presence of subagent-only fields means a
    # caller misrouted the payload, so release without reading or persisting anything else.
    if "agent_id" in incoming or "agent_type" in incoming:
        raise ReleaseTurn
    session_id = incoming.get("session_id")
    if (
        incoming.get("hook_event_name") != "Stop"
        or type(incoming.get("stop_hook_active")) is not bool
        or not isinstance(session_id, str)
        or not 1 <= len(session_id) <= 512
    ):
        raise ReleaseTurn

    # The whitelist ends here. In particular transcript_path, last_assistant_message, cwd,
    # background_tasks, session_crons, and all unknown fields are never returned or persisted.
    # Only a domain-separated digest of the exact delivery crosses to the ephemeral parent cache,
    # allowing transport retries to be idempotent without retaining model content.
    session_ref = sha256_bytes(SESSION_NAMESPACE + session_id.encode("utf-8"))
    return HookInput(
        session_ref=session_ref,
        stop_hook_active=incoming["stop_hook_active"],
        request_ref=sha256_bytes(
            b"llm-redteam-harness:session-end-request:v1:" + raw
        ),
    )


def active_engagement_path() -> Path:
    raw = os.environ.get(ACTIVE_ENGAGEMENT_ENV)
    if not raw:
        raise ReleaseTurn
    candidate = Path(raw)
    if not candidate.is_absolute() or Path(os.path.normpath(raw)) != candidate:
        raise ReleaseTurn
    try:
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError):
        raise ReleaseTurn from None
    if resolved.parent.name != "engagements":
        raise ReleaseTurn
    try:
        resolved.relative_to(ROOT.resolve(strict=True))
    except ValueError:
        pass
    else:
        # Plane 3 belongs to a target repository, never this portable harness checkout.
        raise ReleaseTurn
    return resolved


def _is_sha256(value: object) -> bool:
    return bool(
        isinstance(value, str)
        and len(value) == 71
        and value.startswith("sha256:")
        and all(character in "0123456789abcdef" for character in value[7:])
    )


def scoped_session_baseline() -> SessionBaseline | None:
    """Read #78's optional opaque pre-session head without accepting a partial contract."""

    ledger_hash = os.environ.get(EXPECTED_LEDGER_HASH_ENV)
    raw_source_hashes = os.environ.get(EXPECTED_SOURCE_HASHES_ENV)
    if ledger_hash is None and raw_source_hashes is None:
        return None
    if ledger_hash is None or raw_source_hashes is None or not _is_sha256(ledger_hash):
        raise ReleaseTurn
    try:
        source_hashes = json.loads(
            raw_source_hashes,
            object_pairs_hook=_reject_duplicate_pairs,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ReleaseTurn):
        raise ReleaseTurn from None
    if (
        not isinstance(source_hashes, dict)
        or set(source_hashes)
        != {"events.jsonl", "attempts.jsonl", "artifacts.jsonl"}
        or not all(_is_sha256(value) for value in source_hashes.values())
    ):
        raise ReleaseTurn
    return SessionBaseline(
        ledger_hash=ledger_hash,
        events_hash=source_hashes["events.jsonl"],
        attempts_hash=source_hashes["attempts.jsonl"],
        artifacts_hash=source_hashes["artifacts.jsonl"],
    )


def baseline_is_current(
    baseline: SessionBaseline,
    state: dict[str, Any],
    events: list[dict[str, Any]],
    session_ref: str,
) -> bool:
    """Allow only this session's own audit tail after #78's pre-session source head."""

    source_hashes = state.get("source_hashes")
    if (
        not isinstance(source_hashes, dict)
        or source_hashes.get("attempts.jsonl") != baseline.attempts_hash
        or source_hashes.get("artifacts.jsonl") != baseline.artifacts_hash
    ):
        return False

    matching_indexes = [
        index
        for index, event in enumerate(events)
        if event.get("record_hash") == baseline.ledger_hash
    ]
    if len(matching_indexes) != 1:
        return False
    baseline_index = matching_indexes[0]
    if (
        sha256_bytes(
            b"".join(canonical_json_bytes(event) for event in events[:baseline_index + 1])
        )
        != baseline.events_hash
    ):
        return False
    return all(
        event.get("event_type") == "session.end_checked"
        and event.get("payload", {}).get("session_ref") == session_ref
        for event in events[baseline_index + 1:]
    )


def _parse_gate_payload(payload: dict[str, Any], queue: list[dict[str, Any]]) -> GateView:
    summary = payload.get("queue")
    if (
        payload.get("schema_version") != 1
        or payload.get("command") != "gate"
        or payload.get("ok") is not True
        or not _is_sha256(payload.get("state_hash"))
        or not isinstance(summary, dict)
        or type(summary.get("blocking_count")) is not int
        or type(summary.get("total_count")) is not int
        or type(summary.get("should_block")) is not bool
        or summary.get("blocking_count", -1) < 0
        or summary.get("total_count", -1) < summary.get("blocking_count", 0)
        or summary.get("total_count") != len(queue)
        or summary.get("blocking_count")
        != sum(
            item.get("blocking") is True
            for item in queue
            if isinstance(item, dict)
        )
        or summary.get("decision")
        != ("block" if summary.get("should_block") else "release")
        or summary.get("control_status") not in {"active", "parked"}
        or summary.get("coverage_status")
        not in {"active", "blocked", "coverage_dry", "budget_bounded"}
    ):
        raise RecordError("stop_gate_contract_invalid", "canonical gate payload is malformed")
    return GateView(
        state_hash=payload["state_hash"],
        queue_digest=sha256_bytes(canonical_json_bytes(queue)),
        blocking_count=summary["blocking_count"],
        total_count=summary["total_count"],
        control_status=summary["control_status"],
        coverage_status=summary["coverage_status"],
        should_block=summary["should_block"],
    )


def gate_from_state(state: dict[str, Any], engagement: Path) -> GateView:
    queue = state.get("work_queue")
    if not isinstance(queue, list):
        raise RecordError("stop_gate_contract_invalid", "reducer emitted no queue")
    return _parse_gate_payload(queue_command_payload("gate", state, engagement), queue)


def _latest_same_session_check(
    events: list[dict[str, Any]], session_ref: str
) -> dict[str, Any] | None:
    return next(
        (
            event
            for event in reversed(events)
            if event.get("event_type") == "session.end_checked"
            and event.get("payload", {}).get("session_ref") == session_ref
        ),
        None,
    )


def decide_end(
    gate: GateView,
    hook_input: HookInput,
    events: list[dict[str, Any]],
) -> EndDecision:
    if not gate.should_block:
        raise RecordError("stop_gate_contract_invalid", "non-blocking gate reached block policy")

    previous = _latest_same_session_check(events, hook_input.session_ref)
    valid_previous = bool(
        previous is not None
        and previous.get("payload", {}).get("decision") == "block"
        and type(previous.get("payload", {}).get("confirmed_consecutive_blocks")) is int
        and 1
        <= previous["payload"]["confirmed_consecutive_blocks"]
        <= BLOCK_BUDGET
    )
    if not hook_input.stop_hook_active:
        return EndDecision("block", "blocking_work_remaining", 1)

    if not valid_previous:
        return EndDecision("release", "reentrant_state_unmatched", 0)

    prior_count = previous["payload"]["confirmed_consecutive_blocks"]
    if prior_count >= BLOCK_BUDGET:
        return EndDecision("release", "block_budget_exhausted", BLOCK_BUDGET)
    return EndDecision("block", "blocking_work_remaining", prior_count + 1)


def _record_end_check(
    engagement: Path,
    state: dict[str, Any],
    gate: GateView,
    hook_input: HookInput,
    decision: EndDecision,
) -> dict[str, Any]:
    recorded_at = utc_now()
    random_ref = secrets.token_hex(12)
    event_id = f"event-session-end-{random_ref}"
    if decision.reason_code == "blocking_work_remaining":
        rationale = "Session end backstop found blocking work and requested continuation."
    elif decision.reason_code == "block_budget_exhausted":
        rationale = "Session end backstop released at its six-block budget with work remaining."
    else:
        rationale = "Session end backstop checked the queue and released the session."
    return append_event(
        engagement,
        base_event(
            event_id=event_id,
            engagement_id=state["engagement_id"],
            recorded_at=recorded_at,
            actor_role="broker",
            actor_id="session-end-backstop",
            event_type="session.end_checked",
            rationale=rationale,
            payload={
                "session_ref": hook_input.session_ref,
                "decision": decision.decision,
                "reason_code": decision.reason_code,
                "confirmed_consecutive_blocks": decision.confirmed_consecutive_blocks,
                "blocking_work_count": gate.blocking_count,
                "remaining_work_count": gate.total_count,
                "queue_digest": gate.queue_digest,
                "observed_state_hash": gate.state_hash,
            },
            session_id=hook_input.session_ref,
            operation_class="notebook",
        ),
        lock_held=True,
    )


def assert_audit_only_append(
    before: dict[str, Any],
    after: dict[str, Any],
    recorded: dict[str, Any],
) -> None:
    before_domain = {
        key: value for key, value in before.items() if key not in SESSION_AUDIT_STATE_KEYS
    }
    after_domain = {
        key: value for key, value in after.items() if key not in SESSION_AUDIT_STATE_KEYS
    }
    before_sources = before.get("source_hashes")
    after_sources = after.get("source_hashes")
    if (
        after_domain != before_domain
        or type(before.get("event_count")) is not int
        or after.get("event_count") != before["event_count"] + 1
        or after.get("last_event_id") != recorded.get("event_id")
        or after.get("ledger_hash") != recorded.get("record_hash")
        or not isinstance(before_sources, dict)
        or not isinstance(after_sources, dict)
        or after_sources.get("attempts.jsonl") != before_sources.get("attempts.jsonl")
        or after_sources.get("artifacts.jsonl") != before_sources.get("artifacts.jsonl")
        or after_sources.get("events.jsonl") == before_sources.get("events.jsonl")
    ):
        raise RecordError(
            "stop_hook_mutated_domain_state",
            "session end check changed non-audit state",
        )


def _remainder_text(gate: GateView) -> str:
    blocking_word = "item" if gate.blocking_count == 1 else "items"
    total_word = "item" if gate.total_count == 1 else "items"
    return (
        f"{gate.blocking_count} blocking {blocking_word} remain "
        f"({gate.total_count} total {total_word}; queue digest {gate.queue_digest}). "
        "Run the harness work-queue next command for the exact next action."
    )


def output_for(decision: EndDecision, gate: GateView) -> dict[str, Any]:
    if decision.decision == "block":
        return {
            "decision": "block",
            "reason": (
                f"{_remainder_text(gate)} "
                f"Session end backstop continuation "
                f"{decision.confirmed_consecutive_blocks} of {BLOCK_BUDGET}."
            ),
        }
    if decision.reason_code == "block_budget_exhausted":
        return {
            "systemMessage": (
                f"Session end backstop released after {BLOCK_BUDGET} consecutive "
                f"continuations; {_remainder_text(gate)}"
            )
        }
    if decision.reason_code == "reentrant_state_unmatched":
        return {
            "systemMessage": (
                "Session end backstop released because stop_hook_active had no matching "
                f"recorded continuation; {_remainder_text(gate)}"
            )
        }
    return {}


def run_hook() -> dict[str, Any]:
    hook_input = parse_hook_input()
    if os.environ.get(BROKER_ENDPOINT_ENV):
        # A driver-scoped model cannot write the target.  The hook therefore forwards only its
        # opaque, parent-bound session digest and re-entrancy bit; the trusted parent derives the
        # queue, appends the audit event, and returns the small Claude Stop response.
        return forward_stop_check_to_broker(
            hook_session_ref=hook_input.session_ref,
            stop_hook_active=hook_input.stop_hook_active,
            request_ref=hook_input.request_ref,
        )
    baseline = scoped_session_baseline()
    logical_engagement = active_engagement_path()
    with existing_engagement_transaction(logical_engagement) as engagement:
        state = _reduce_engagement_unchecked(engagement)
        # A session check must never become the mechanism that preserves or activates scope drift.
        if sha256_bytes(read_governed_file(engagement / "scope.md")) != state.get("scope_hash"):
            raise RecordError("stop_hook_scope_drift", "active scope bytes drifted")
        events = read_ledger(engagement, "event")
        if baseline is not None and not baseline_is_current(
            baseline,
            state,
            events,
            hook_input.session_ref,
        ):
            return {}
        gate = gate_from_state(state, engagement)
        if not gate.should_block:
            return {}
        decision = decide_end(gate, hook_input, events)
        recorded = _record_end_check(engagement, state, gate, hook_input, decision)
        after = _reduce_engagement_unchecked(engagement)
        assert_audit_only_append(state, after, recorded)
    return output_for(decision, gate)


def additional_settings() -> dict[str, Any]:
    python_path = str(Path(sys.executable).absolute())
    hook_path = str(Path(__file__).absolute())
    return {
        "hooks": {
            "Stop": [{
                "hooks": [{
                    "type": "command",
                    "command": shlex.join([python_path, hook_path]),
                    "timeout": 10,
                }]
            }]
        }
    }


def main() -> int:
    if sys.argv[1:] == ["--print-additional-settings"]:
        emit(additional_settings())
        return 0
    if sys.argv[1:]:
        emit({})
        return 0
    try:
        result = run_hook()
    except Exception:
        # Claude Code releases Stop on exit-0 non-blocking JSON. Never emit diagnostics containing
        # target paths, reducer details, raw stdin, or other Plane-3 material from this boundary.
        result = {}
    emit(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
