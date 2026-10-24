#!/usr/bin/env python3
"""Direct subprocess contract tests for the orchestrating-session Stop backstop."""

from __future__ import annotations

import fcntl
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
HOOK = TOOLS / "claude-stop-hook.py"
SETTINGS = ROOT / ".claude" / "settings.json"
sys.path.insert(0, str(TOOLS))

from engagement_records import canonical_json_bytes, sha256_bytes  # noqa: E402
from engagement_state import (  # noqa: E402
    _append_kernel_event,
    append_event,
    base_event,
    initialize_engagement,
    read_ledger,
    reduce_engagement,
    utc_now,
)


def decode_one_json_document(raw: bytes) -> dict[str, Any]:
    text = raw.decode("utf-8")
    value, end = json.JSONDecoder().raw_decode(text)
    if text[end:].strip() or not isinstance(value, dict):
        raise AssertionError(f"stdout is not exactly one JSON object: {text!r}")
    return value


def is_exact_block(value: object) -> bool:
    return bool(
        isinstance(value, dict)
        and set(value) == {"decision", "reason"}
        and value.get("decision") == "block"
        and isinstance(value.get("reason"), str)
        and value["reason"]
    )


def has_stop_continuation_control(value: object) -> bool:
    """Model the two documented Stop continuation controls, not just the block object."""

    if not isinstance(value, dict):
        return False
    if value.get("decision") == "block":
        return True
    specific = value.get("hookSpecificOutput")
    return bool(
        isinstance(specific, dict)
        and specific.get("hookEventName") == "Stop"
        and isinstance(specific.get("additionalContext"), str)
        and specific["additionalContext"]
    )


def is_exact_release_message(value: object) -> bool:
    return bool(
        isinstance(value, dict)
        and set(value) == {"systemMessage"}
        and isinstance(value.get("systemMessage"), str)
        and value["systemMessage"]
        and not has_stop_continuation_control(value)
    )


def make_engagement(target_root: Path, name: str) -> Path:
    engagement = target_root / "engagements" / name
    engagement.mkdir(parents=True)
    signer_digest = "sha256:" + "0" * 64
    engagement.joinpath("scope.md").write_text(
        f"""# Scope — Stop hook contract fixture

## Surfaces in scope
- Synthetic local fixture only.
## Benign safe-objective set
- Exercise the record-only session backstop.
## Escalation ceiling
- Local records only.
## Impact-demo authorization
- impact_demo_authorized: `no`
- zone2_authorized_categories: `none`
- zone2_escalation_ceiling: `none`
- zone2_containment: `not applicable`
## Accounts / fixtures
- None.
## Independent reviewer identity
- Reviewer allowed signers SHA256: {signer_digest}
## Authorization
- Operator allowed signers SHA256: {signer_digest}
- Operator: operator-stop-test
- Date: 2026-08-24
- Signed: [x]
- Record kernel: `decision-0006-v1`
""",
        encoding="utf-8",
    )
    initialize_engagement(engagement, "2026-08-24T00:00:00Z")
    return engagement


def clone_engagement(source: Path, target_root: Path, name: str) -> Path:
    destination = target_root / "engagements" / name
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, destination)
    return destination


def stop_payload(
    *,
    session_id: str = "session-main",
    stop_hook_active: bool = False,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "session_id": session_id,
        "prompt_id": extra.pop("prompt_id", f"prompt-{session_id}"),
        "hook_event_name": "Stop",
        "stop_hook_active": stop_hook_active,
        "transcript_path": "/private/unread-transcript.jsonl",
        "last_assistant_message": "Authorization: Bearer never-persist-this-value-123456",
        **extra,
    }


def invoke(
    engagement: Path | None,
    payload: dict[str, Any] | bytes,
    *,
    extra_env: dict[str, str] | None = None,
    timeout: float = 5,
) -> tuple[subprocess.CompletedProcess[bytes], dict[str, Any]]:
    environment = dict(os.environ)
    environment.pop("HARNESS_ACTIVE_ENGAGEMENT", None)
    environment.pop("HARNESS_STOP_BLOCK_BUDGET", None)
    environment.pop("HARNESS_EXPECTED_LEDGER_HASH", None)
    environment.pop("HARNESS_EXPECTED_SOURCE_HASHES", None)
    if engagement is not None:
        environment["HARNESS_ACTIVE_ENGAGEMENT"] = str(engagement)
    if extra_env:
        environment.update(extra_env)
    raw_input = payload if isinstance(payload, bytes) else canonical_json_bytes(payload)
    result = subprocess.run(
        [sys.executable, str(HOOK)],
        input=raw_input,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=environment,
        timeout=timeout,
        check=False,
    )
    if result.returncode != 0 or result.stderr:
        raise AssertionError(
            f"hook was not a quiet exit-0 contract: rc={result.returncode}, "
            f"stdout={result.stdout!r}, stderr={result.stderr!r}"
        )
    decoded = decode_one_json_document(result.stdout)
    if result.stdout != canonical_json_bytes(decoded):
        raise AssertionError(f"stdout is not one canonical JSON document: {result.stdout!r}")
    return result, decoded


def scoped_session_environment(engagement: Path) -> dict[str, str]:
    state = reduce_engagement(engagement)
    return {
        "HARNESS_EXPECTED_LEDGER_HASH": state["ledger_hash"],
        "HARNESS_EXPECTED_SOURCE_HASHES": json.dumps(
            state["source_hashes"],
            sort_keys=True,
            separators=(",", ":"),
        ),
    }


def append_operator_stop(engagement: Path) -> None:
    state = reduce_engagement(engagement)
    reason = "Operator deliberately parked the synthetic queue."
    _append_kernel_event(
        engagement,
        base_event(
            event_id="event-stop-hook-parked",
            engagement_id=state["engagement_id"],
            recorded_at="2026-08-24T00:01:00Z",
            actor_role="operator",
            actor_id="operator-stop-test",
            event_type="operator_stop.recorded",
            rationale=reason,
            payload={
                "entity_id": state["engagement_id"],
                "status": "parked",
                "operator_id": "operator-stop-test",
                "reason": reason,
            },
            state_changes=[{
                "dimension": "queue",
                "entity_id": state["engagement_id"],
                "previous": "active",
                "current": "parked",
            }],
            session_id="session-operator-stop-test",
            operation_class="authority",
        ),
    )


def append_engagement_blocked(engagement: Path) -> None:
    state = reduce_engagement(engagement)
    reason = "Synthetic external dependency blocks this fixture."
    _append_kernel_event(
        engagement,
        base_event(
            event_id="event-stop-hook-engagement-blocked",
            engagement_id=state["engagement_id"],
            recorded_at="2026-08-24T00:01:00Z",
            actor_role="operator",
            actor_id="operator-stop-test",
            event_type="engagement.blocked",
            rationale=reason,
            payload={
                "entity_id": state["engagement_id"],
                "status": "blocked",
                "reason": reason,
            },
            state_changes=[
                {
                    "dimension": "engagement",
                    "entity_id": state["engagement_id"],
                    "previous": "active",
                    "current": "blocked",
                },
                {
                    "dimension": "coverage",
                    "entity_id": state["engagement_id"],
                    "previous": "active",
                    "current": "blocked",
                },
            ],
            session_id="session-operator-stop-test",
            operation_class="authority",
        ),
    )


def append_operator_only_work(engagement: Path) -> None:
    state = reduce_engagement(engagement)
    append_event(
        engagement,
        base_event(
            event_id="event-stop-hook-operator-request",
            engagement_id=state["engagement_id"],
            recorded_at="2026-08-24T00:01:00Z",
            actor_role="orchestrator",
            actor_id="orchestrator-stop-test",
            event_type="authority.requested",
            rationale="Request an exact synthetic operator-only decision.",
            payload={
                "request_id": "request-stop-hook-operator-only",
                "action_kind": "synthetic-operator-only",
                "action_digest": sha256_bytes(b"synthetic operator action\n"),
                "lane_id": "lane-stop-hook-operator-only",
                "request_status": "pending_authority",
                "scope_hash": state["scope_hash"],
                "environment_ref": state["active_environment_ref"],
                "expires_at": "2099-08-24T00:00:00Z",
            },
            session_id="session-orchestrator-stop-test",
            operation_class="notebook",
        ),
    )


def session_checks(engagement: Path) -> list[dict[str, Any]]:
    return [
        event
        for event in read_ledger(engagement, "event")
        if event["event_type"] == "session.end_checked"
    ]


def open_file_observer() -> str | None:
    """Return the portable mechanism available for observing a child file descriptor."""

    if Path("/proc/self/fd").is_dir():
        return "procfs"
    if shutil.which("lsof"):
        return "lsof"
    return None


def process_has_open_kernel_lock(pid: int, observer: str) -> bool:
    if observer == "procfs":
        descriptor_dir = Path("/proc") / str(pid) / "fd"
        try:
            for descriptor in descriptor_dir.iterdir():
                try:
                    if Path(os.readlink(descriptor)).name == ".record-kernel.lock":
                        return True
                except (FileNotFoundError, OSError):
                    continue
        except (FileNotFoundError, PermissionError):
            return False
        return False

    lsof = shutil.which("lsof")
    if lsof is None:
        return False
    opened_files = subprocess.run(
        [lsof, "-p", str(pid), "-Fn"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    ).stdout
    return b".record-kernel.lock" in opened_files


def main() -> int:
    checks: list[tuple[str, bool, str]] = []
    with tempfile.TemporaryDirectory(prefix="claude-stop-hook-contract-") as temporary:
        root = Path(temporary).resolve()
        target = root / "target-repo"
        target.mkdir()
        target.joinpath(".git").mkdir()
        base = make_engagement(target, "active")

        before_state = reduce_engagement(base)
        before = len(read_ledger(base, "event"))
        _, blocked = invoke(
            base,
            stop_payload(session_id="session-raw-must-be-opaque"),
        )
        recorded = session_checks(base)
        after_state = reduce_engagement(base)
        ledger_bytes = base.joinpath("events.jsonl").read_bytes()
        checks.append((
            "blocking output is exactly the documented top-level Stop shape",
            is_exact_block(blocked) and set(blocked) == {"decision", "reason"},
            repr(blocked),
        ))
        checks.append((
            "a blocking session end is recorded without raw hook input",
            len(read_ledger(base, "event")) == before + 1
            and len(recorded) == 1
            and recorded[-1]["payload"]["decision"] == "block"
            and recorded[-1]["payload"]["confirmed_consecutive_blocks"] == 1
            and b"session-raw-must-be-opaque" not in ledger_bytes
            and b"never-persist-this-value" not in ledger_bytes
            and b"unread-transcript" not in ledger_bytes,
            repr(recorded[-1] if recorded else None),
        ))
        audit_keys = {"event_count", "last_event_id", "ledger_hash", "source_hashes"}
        domain_keys = (set(before_state) | set(after_state)) - audit_keys
        checks.append((
            "the typed session event changes no queue, review, claim, or completion truth",
            all(before_state.get(key) == after_state.get(key) for key in domain_keys),
            repr({
                key: (before_state.get(key), after_state.get(key))
                for key in sorted(domain_keys)
                if before_state.get(key) != after_state.get(key)
            }),
        ))

        nested_process = subprocess.run(
            [
                sys.executable,
                "-c",
                "import json; print(json.dumps({'hookSpecificOutput': "
                "{'hookEventName': 'Stop', 'decision': 'block', 'reason': 'wrong'}}))",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        nested = decode_one_json_document(nested_process.stdout)
        checks.append((
            "the tempting nested block shape is deliberately proven non-blocking",
            nested_process.returncode == 0 and not is_exact_block(nested),
            repr(nested),
        ))

        tempting_context = {
            "hookSpecificOutput": {
                "hookEventName": "Stop",
                "additionalContext": "This looks informational but continues the conversation.",
            }
        }
        checks.append((
            "Stop additionalContext is continuation control and can never represent release",
            has_stop_continuation_control(tempting_context)
            and not is_exact_release_message(tempting_context),
            repr(tempting_context),
        ))

        pristine = make_engagement(target, "pristine")
        capped = clone_engagement(pristine, target, "budget")
        outputs: list[dict[str, Any]] = []
        for index in range(7):
            _, output = invoke(
                capped,
                stop_payload(
                    session_id="session-budget",
                    stop_hook_active=index > 0,
                ),
            )
            outputs.append(output)
        budget_events = session_checks(capped)
        checks.append((
            "exactly six consecutive blocks are honored and the seventh releases with remainder",
            all(is_exact_block(output) for output in outputs[:6])
            and is_exact_release_message(outputs[6])
            and "blocking item" in outputs[6]["systemMessage"]
            and [event["payload"]["decision"] for event in budget_events] == ["block"] * 6 + ["release"]
            and [event["payload"]["confirmed_consecutive_blocks"] for event in budget_events]
            == [1, 2, 3, 4, 5, 6, 6]
            and budget_events[-1]["payload"]["reason_code"] == "block_budget_exhausted",
            repr(outputs),
        ))

        reset = clone_engagement(pristine, target, "reset")
        invoke(reset, stop_payload(session_id="session-reset", stop_hook_active=False))
        invoke(reset, stop_payload(session_id="session-reset", stop_hook_active=True))
        _, reset_output = invoke(
            reset,
            stop_payload(
                session_id="session-reset",
                prompt_id="prompt-session-reset-new",
                stop_hook_active=False,
            ),
        )
        reset_events = [
            event
            for event in session_checks(reset)
            if event["payload"]["decision"] == "block"
            and event["payload"]["session_ref"]
            == session_checks(reset)[-1]["payload"]["session_ref"]
        ]
        checks.append((
            "a non-hook-forced Stop starts a new consecutive-block streak",
            is_exact_block(reset_output)
            and [event["payload"]["confirmed_consecutive_blocks"] for event in reset_events[-3:]]
            == [1, 2, 1],
            repr(reset_events[-3:]),
        ))

        duplicate_delivery = clone_engagement(pristine, target, "duplicate-delivery")
        repeated_payload = stop_payload(
            session_id="session-duplicate-delivery",
            prompt_id="prompt-duplicate-delivery",
            stop_hook_active=False,
        )
        _, first_delivery = invoke(duplicate_delivery, repeated_payload)
        _, second_delivery = invoke(duplicate_delivery, repeated_payload)
        duplicate_events = session_checks(duplicate_delivery)
        checks.append((
            "a repeated non-hook-forced delivery starts a fresh streak as documented",
            is_exact_block(first_delivery)
            and is_exact_block(second_delivery)
            and [
                event["payload"]["confirmed_consecutive_blocks"]
                for event in duplicate_events
            ] == [1, 1]
            and len({event["event_id"] for event in duplicate_events}) == 2,
            repr(duplicate_events),
        ))

        scoped = clone_engagement(pristine, target, "scoped-session")
        scoped_environment = scoped_session_environment(scoped)
        _, scoped_first = invoke(
            scoped,
            stop_payload(session_id="session-scoped"),
            extra_env=scoped_environment,
        )
        _, scoped_second = invoke(
            scoped,
            stop_payload(session_id="session-scoped", stop_hook_active=True),
            extra_env=scoped_environment,
        )
        scoped_before_mutation = len(session_checks(scoped))
        scoped_state = reduce_engagement(scoped)
        append_event(
            scoped,
            base_event(
                event_id="event-scoped-substantive-mutation",
                engagement_id=scoped_state["engagement_id"],
                recorded_at=utc_now(),
                actor_role="orchestrator",
                actor_id="orchestrator-stop-test",
                event_type="observation.recorded",
                rationale="Represent the one substantive action allowed in this driver session.",
                payload={
                    "entity_id": "observation-scoped-substantive-mutation",
                    "entity_type": "observation",
                    "status": "recorded",
                },
                session_id="session-orchestrator-stop-test",
                operation_class="notebook",
            ),
        )
        _, scoped_after_mutation = invoke(
            scoped,
            stop_payload(session_id="session-scoped", stop_hook_active=True),
            extra_env=scoped_environment,
        )
        checks.append((
            "a driver-scoped session tolerates only its own audit tail then releases after one substantive event",
            is_exact_block(scoped_first)
            and is_exact_block(scoped_second)
            and scoped_after_mutation == {}
            and len(session_checks(scoped)) == scoped_before_mutation,
            repr((scoped_first, scoped_second, scoped_after_mutation)),
        ))

        foreign_tail = clone_engagement(pristine, target, "scoped-foreign-tail")
        foreign_environment = scoped_session_environment(foreign_tail)
        invoke(
            foreign_tail,
            stop_payload(session_id="session-scoped-a"),
            extra_env=foreign_environment,
        )
        foreign_before = foreign_tail.joinpath("events.jsonl").read_bytes()
        _, foreign_output = invoke(
            foreign_tail,
            stop_payload(session_id="session-scoped-b"),
            extra_env=foreign_environment,
        )
        checks.append((
            "a driver-scoped session cannot borrow another session's end-check tail",
            foreign_output == {}
            and foreign_tail.joinpath("events.jsonl").read_bytes() == foreign_before,
            repr(foreign_output),
        ))

        source_mismatch_results: list[bool] = []
        for ledger_name in ("attempts.jsonl", "artifacts.jsonl"):
            source_mismatch = clone_engagement(
                pristine,
                target,
                "scoped-" + ledger_name.removesuffix(".jsonl") + "-mismatch",
            )
            mismatch_environment = scoped_session_environment(source_mismatch)
            expected_sources = json.loads(
                mismatch_environment["HARNESS_EXPECTED_SOURCE_HASHES"]
            )
            expected_sources[ledger_name] = "sha256:" + "f" * 64
            mismatch_environment["HARNESS_EXPECTED_SOURCE_HASHES"] = json.dumps(
                expected_sources,
                sort_keys=True,
                separators=(",", ":"),
            )
            mismatch_before = source_mismatch.joinpath("events.jsonl").read_bytes()
            _, mismatch_output = invoke(
                source_mismatch,
                stop_payload(session_id=f"session-{ledger_name}-mismatch"),
                extra_env=mismatch_environment,
            )
            source_mismatch_results.append(
                mismatch_output == {}
                and source_mismatch.joinpath("events.jsonl").read_bytes() == mismatch_before
            )
        checks.append((
            "driver-scoped attempt and artifact source mismatches both release without recording",
            all(source_mismatch_results),
            repr(source_mismatch_results),
        ))

        malformed_baseline = clone_engagement(pristine, target, "scoped-malformed")
        malformed_baseline_before = malformed_baseline.joinpath("events.jsonl").read_bytes()
        _, partial_baseline_output = invoke(
            malformed_baseline,
            stop_payload(session_id="session-scoped-partial"),
            extra_env={
                "HARNESS_EXPECTED_LEDGER_HASH": reduce_engagement(malformed_baseline)[
                    "ledger_hash"
                ],
            },
        )
        _, malformed_baseline_output = invoke(
            malformed_baseline,
            stop_payload(session_id="session-scoped-malformed"),
            extra_env={
                "HARNESS_EXPECTED_LEDGER_HASH": reduce_engagement(malformed_baseline)[
                    "ledger_hash"
                ],
                "HARNESS_EXPECTED_SOURCE_HASHES": "{",
            },
        )
        checks.append((
            "partial or malformed driver baseline input fails open before any ledger write",
            partial_baseline_output == {}
            and malformed_baseline_output == {}
            and malformed_baseline.joinpath("events.jsonl").read_bytes()
            == malformed_baseline_before,
            repr((partial_baseline_output, malformed_baseline_output)),
        ))

        unmatched = clone_engagement(pristine, target, "unmatched")
        _, unmatched_output = invoke(
            unmatched,
            stop_payload(session_id="session-unmatched", stop_hook_active=True),
        )
        unmatched_event = session_checks(unmatched)[-1]
        checks.append((
            "stop_hook_active without a matching recorded block releases instead of borrowing a streak",
            is_exact_release_message(unmatched_output)
            and unmatched_event["payload"]["decision"] == "release"
            and unmatched_event["payload"]["reason_code"] == "reentrant_state_unmatched",
            repr(unmatched_output),
        ))

        inactive_before = base.joinpath("events.jsonl").read_bytes()
        _, inactive = invoke(None, stop_payload())
        checks.append((
            "no explicit active engagement is a clean inert release",
            inactive == {} and base.joinpath("events.jsonl").read_bytes() == inactive_before,
            repr(inactive),
        ))

        portable_template = ROOT / "engagements" / "_TEMPLATE"
        portable_lock = portable_template / ".record-kernel.lock"
        _, portable_output = invoke(
            portable_template,
            stop_payload(session_id="session-portable-template"),
        )
        checks.append((
            "the portable harness tree is never admitted as target-local engagement state",
            portable_output == {} and not portable_lock.exists(),
            repr(portable_output),
        ))

        parked = clone_engagement(pristine, target, "parked")
        append_operator_stop(parked)
        parked_before = parked.joinpath("events.jsonl").read_bytes()
        _, parked_output = invoke(parked, stop_payload(session_id="session-parked"))
        checks.append((
            "an operator-parked queue releases without adding backstop ledger noise",
            parked_output == {}
            and parked.joinpath("events.jsonl").read_bytes() == parked_before,
            repr(parked_output),
        ))

        empty = clone_engagement(pristine, target, "empty")
        append_engagement_blocked(empty)
        empty_before = empty.joinpath("events.jsonl").read_bytes()
        _, empty_output = invoke(empty, stop_payload(session_id="session-empty"))
        checks.append((
            "an empty non-active coverage queue releases without a session event",
            empty_output == {}
            and empty.joinpath("events.jsonl").read_bytes() == empty_before,
            repr(empty_output),
        ))

        operator_only = clone_engagement(pristine, target, "operator-only")
        append_operator_only_work(operator_only)
        operator_before = operator_only.joinpath("events.jsonl").read_bytes()
        _, operator_output = invoke(
            operator_only,
            stop_payload(session_id="session-operator-only"),
        )
        checks.append((
            "operator-only work releases without trapping or bloating the session ledger",
            operator_output == {}
            and operator_only.joinpath("events.jsonl").read_bytes() == operator_before,
            repr(operator_output),
        ))

        malformed_before = base.joinpath("events.jsonl").read_bytes()
        _, malformed = invoke(base, b"{")
        _, duplicate = invoke(
            base,
            b'{"session_id":"a","session_id":"b","hook_event_name":"Stop",'
            b'"stop_hook_active":false}\n',
        )
        checks.append((
            "malformed and duplicate-key hook input both release without recording raw bytes",
            malformed == {}
            and duplicate == {}
            and base.joinpath("events.jsonl").read_bytes() == malformed_before,
            repr((malformed, duplicate)),
        ))

        subagent_before = base.joinpath("events.jsonl").read_bytes()
        _, subagent = invoke(
            base,
            stop_payload(agent_id="hunter-1", agent_type="hunter"),
        )
        checks.append((
            "subagent-shaped input is unaffected even if misrouted to the Stop executable",
            subagent == {} and base.joinpath("events.jsonl").read_bytes() == subagent_before,
            repr(subagent),
        ))

        reducer_error = clone_engagement(pristine, target, "reducer-error")
        reducer_error.joinpath("events.jsonl").write_bytes(
            reducer_error.joinpath("events.jsonl").read_bytes() + b"not-json\n"
        )
        _, reducer_error_output = invoke(
            reducer_error,
            stop_payload(session_id="session-reducer-error"),
        )
        checks.append((
            "a reducer error releases with one harmless JSON document",
            reducer_error_output == {},
            repr(reducer_error_output),
        ))

        missing = target / "engagements" / "missing"
        _, missing_output = invoke(
            missing,
            stop_payload(session_id="session-missing"),
        )
        checks.append((
            "a missing engagement path releases",
            missing_output == {},
            repr(missing_output),
        ))

        uninitialized = target / "engagements" / "uninitialized"
        uninitialized.mkdir()
        _, uninitialized_output = invoke(
            uninitialized,
            stop_payload(session_id="session-uninitialized"),
        )
        checks.append((
            "an uninitialized engagement releases without creating kernel coordination state",
            uninitialized_output == {}
            and not uninitialized.joinpath(".record-kernel.lock").exists(),
            repr(uninitialized_output),
        ))

        identity_observer = open_file_observer()
        if identity_observer is None:
            print(
                "  skip rename-and-replace lock identity check "
                "(requires procfs or lsof file-descriptor observation)"
            )
        else:
            identity_case = clone_engagement(pristine, target, "identity-bound")
            identity_moved = target / "engagements" / "identity-bound-moved"
            identity_lock_fd = os.open(identity_case / ".record-kernel.lock", os.O_RDWR)
            identity_environment = dict(os.environ)
            identity_environment["HARNESS_ACTIVE_ENGAGEMENT"] = str(identity_case)
            identity_process: subprocess.Popen[bytes] | None = None
            identity_opened = False
            identity_output: dict[str, Any] | None = None
            try:
                fcntl.flock(identity_lock_fd, fcntl.LOCK_EX)
                identity_process = subprocess.Popen(
                    [sys.executable, str(HOOK)],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=identity_environment,
                )
                assert identity_process.stdin is not None
                identity_process.stdin.write(
                    canonical_json_bytes(stop_payload(session_id="session-identity-bound"))
                )
                identity_process.stdin.close()
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline and identity_process.poll() is None:
                    if process_has_open_kernel_lock(identity_process.pid, identity_observer):
                        identity_opened = True
                        break
                    time.sleep(0.02)
                if identity_opened:
                    identity_case.rename(identity_moved)
                    shutil.copytree(pristine, identity_case)
            finally:
                fcntl.flock(identity_lock_fd, fcntl.LOCK_UN)
                os.close(identity_lock_fd)
            if identity_process is not None:
                try:
                    identity_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    identity_process.kill()
                    identity_process.wait(timeout=5)
                assert identity_process.stdout is not None
                assert identity_process.stderr is not None
                raw_identity_output = identity_process.stdout.read()
                identity_stderr = identity_process.stderr.read()
                if raw_identity_output:
                    identity_output = decode_one_json_document(raw_identity_output)
                identity_quiet = identity_process.returncode == 0 and not identity_stderr
            else:
                identity_quiet = False
            checks.append((
                "rename-and-replace cannot redirect a locked end check to either directory inode",
                identity_opened
                and identity_quiet
                and identity_output == {}
                and identity_moved.is_dir()
                and not session_checks(identity_moved)
                and not session_checks(identity_case),
                repr((identity_opened, identity_output)),
            ))

        timeout_case = clone_engagement(pristine, target, "timeout")
        timeout_before = timeout_case.joinpath("events.jsonl").read_bytes()
        lock_fd = os.open(timeout_case / ".record-kernel.lock", os.O_RDWR)
        timed_out = False
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            environment = dict(os.environ)
            environment["HARNESS_ACTIVE_ENGAGEMENT"] = str(timeout_case)
            try:
                subprocess.run(
                    [sys.executable, str(HOOK)],
                    input=canonical_json_bytes(stop_payload(session_id="session-timeout")),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=environment,
                    timeout=0.2,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                timed_out = True
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)
        checks.append((
            "a platform timeout cancels the hook without emitting or recording a block",
            timed_out and timeout_case.joinpath("events.jsonl").read_bytes() == timeout_before,
            "hook did not time out safely",
        ))

        startup_released = False
        try:
            subprocess.run(
                [str(root / "missing-hook-executable")],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
        except FileNotFoundError:
            startup_released = True
        checks.append((
            "a missing hook executable cannot synthesize the exact blocking document",
            startup_released,
            "missing executable unexpectedly started",
        ))

        project_settings = json.loads(SETTINGS.read_text(encoding="utf-8"))
        project_hooks = project_settings.get("hooks", {})
        checks.append((
            "repository sessions do not inherit the legacy queue Stop hook",
            "Stop" not in project_hooks,
            repr(project_settings),
        ))

        generated_process = subprocess.run(
            [sys.executable, str(HOOK), "--print-additional-settings"],
            cwd=target,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={key: value for key, value in os.environ.items() if key != "HARNESS_ACTIVE_ENGAGEMENT"},
            check=False,
        )
        generated = decode_one_json_document(generated_process.stdout)
        generated_command = generated["hooks"]["Stop"][0]["hooks"][0]
        checks.append((
            "explicit legacy launch settings retain absolute Stop paths and never install SubagentStop",
            generated_process.returncode == 0
            and not generated_process.stderr
            and set(generated["hooks"]) == {"Stop"}
            and generated_command["timeout"] == 10
            and str(Path(sys.executable).absolute()) in generated_command["command"]
            and str(HOOK.absolute()) in generated_command["command"]
            and "CLAUDE_PROJECT_DIR" not in generated_command["command"],
            repr(generated),
        ))

    failed = [label for label, ok, _ in checks if not ok]
    for label, ok, detail in checks:
        print(f"  {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" :: {detail}"))
    print(f"CLAUDE STOP HOOK CONTRACT: {'PASS' if not failed else 'FAIL'}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
