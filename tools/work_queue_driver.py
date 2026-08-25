#!/usr/bin/env python3
"""External, budget-bounded driver for one target-local engagement queue."""

from __future__ import annotations

import copy
import fcntl
import json
import math
import os
import re
import stat
import subprocess
import sys
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator, Sequence

from claude_work_session import SessionLaunchError, run_claude_session
from engagement_records import RecordError, canonical_json_bytes, sha256_bytes
from engagement_state import (
    _append_kernel_event_idempotent,
    _open_absolute_directory,
    _reduce_engagement_unchecked,
    base_event,
    bound_engagement_lock,
    read_ledger,
    utc_now,
)
from driver_action_admission import (
    BROKER_ENDPOINT_ENV,
    SESSION_ENV,
    DriverActionBroker,
    activate_action_admission,
    arm_action_admission,
    disarm_action_admission,
    new_admission_token,
)


ROOT = Path(__file__).resolve().parents[1]
STOP_HOOK = ROOT / "tools" / "claude-stop-hook.py"
IMMUTABLE_CLAUDE_MODEL = re.compile(r"^claude-[a-z0-9]+(?:-[a-z0-9]+)*-[0-9]{8}$")
NONCOMPLETION_STATUSES = frozenset(
    {
        "budget_spent",
        "operator_parked",
        "operator_required",
        "coverage_blocked",
        "coverage_budget_bounded",
        "interrupted_unrecorded",
        "reviewer_model_unavailable",
    }
)


class DriverError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class BoundRun:
    workspace: Path
    engagement: Path
    workspace_fd: int
    engagement_fd: int


@dataclass(frozen=True)
class DriverBudget:
    max_sessions: int
    max_wall_seconds: float
    session_timeout_seconds: float
    session_max_budget_usd: float | None

    def validate(self) -> None:
        if type(self.max_sessions) is not int or self.max_sessions < 1:
            raise DriverError("driver_max_sessions_invalid")
        if (
            not isinstance(self.max_wall_seconds, (int, float))
            or isinstance(self.max_wall_seconds, bool)
            or not math.isfinite(float(self.max_wall_seconds))
            or self.max_wall_seconds <= 0
        ):
            raise DriverError("driver_max_wall_invalid")
        if (
            not isinstance(self.session_timeout_seconds, (int, float))
            or isinstance(self.session_timeout_seconds, bool)
            or not math.isfinite(float(self.session_timeout_seconds))
            or self.session_timeout_seconds <= 0
        ):
            raise DriverError("driver_session_timeout_invalid")
        if self.session_max_budget_usd is not None:
            if (
                not isinstance(self.session_max_budget_usd, (int, float))
                or isinstance(self.session_max_budget_usd, bool)
                or not math.isfinite(float(self.session_max_budget_usd))
                or self.session_max_budget_usd <= 0
            ):
                raise DriverError("driver_session_budget_invalid")


def _named_identity_is_current(path: Path, fd: int) -> bool:
    try:
        opened = os.fstat(fd)
        named = os.stat(path, follow_symlinks=False)
    except OSError:
        return False
    return bool(
        stat.S_ISDIR(opened.st_mode)
        and stat.S_ISDIR(named.st_mode)
        and not stat.S_ISLNK(named.st_mode)
        and (opened.st_dev, opened.st_ino) == (named.st_dev, named.st_ino)
    )


def _paths_overlap(left: Path, right: Path) -> bool:
    try:
        left.relative_to(right)
        return True
    except ValueError:
        pass
    try:
        right.relative_to(left)
        return True
    except ValueError:
        return False


def _directory_contains(ancestor_fd: int, candidate_fd: int) -> bool:
    """Return whether one bound directory inode is an ancestor of the other.

    Path strings cannot answer this safely on case-insensitive filesystems or through an aliasing
    parent symlink.  Walking ``..`` from the already-open candidate compares the filesystem's
    directory identities instead.
    """

    ancestor = os.fstat(ancestor_fd)
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    cursor = os.open(".", flags, dir_fd=candidate_fd)
    try:
        while True:
            current = os.fstat(cursor)
            if (current.st_dev, current.st_ino) == (ancestor.st_dev, ancestor.st_ino):
                return True
            parent = os.open("..", flags, dir_fd=cursor)
            parent_stat = os.fstat(parent)
            if (parent_stat.st_dev, parent_stat.st_ino) == (current.st_dev, current.st_ino):
                os.close(parent)
                return False
            os.close(cursor)
            cursor = parent
    finally:
        os.close(cursor)


def _bound_directories_overlap(left_fd: int, right_fd: int) -> bool:
    return _directory_contains(left_fd, right_fd) or _directory_contains(right_fd, left_fd)


def _open_child_directory(parent_fd: int, name: str) -> int:
    if not name or name in {".", ".."} or "/" in name or "\x00" in name:
        raise OSError("unsafe directory component")
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    return os.open(name, flags, dir_fd=parent_fd)


@contextmanager
def bind_run(workspace: Path, engagement: Path) -> Iterator[BoundRun]:
    """Bind the target hierarchy and structurally lock its workspace inode for the whole run."""

    supplied_workspace = Path(workspace)
    supplied_engagement = Path(engagement)
    if not supplied_workspace.is_absolute() or not supplied_engagement.is_absolute():
        raise DriverError("driver_target_layout_invalid")
    workspace = Path(os.path.abspath(supplied_workspace))
    engagement = Path(os.path.abspath(supplied_engagement))
    if (
        engagement.parent.name != "engagements"
        or engagement.parent.parent != workspace
        or _paths_overlap(workspace, ROOT)
    ):
        raise DriverError("driver_target_layout_invalid")

    workspace_fd: int | None = None
    portable_fd: int | None = None
    engagements_fd: int | None = None
    engagement_fd: int | None = None
    lock_fd: int | None = None
    try:
        try:
            workspace_fd = _open_absolute_directory(workspace)
            portable_fd = _open_absolute_directory(ROOT)
            if _bound_directories_overlap(workspace_fd, portable_fd):
                raise DriverError("driver_target_layout_invalid")

            # The workspace directory itself is the lock object.  A separate open description
            # keeps the lock out of the descriptor inherited by Claude and, unlike a target-local
            # lockfile, there is no name the target can unlink and replace to manufacture a second
            # lock.
            flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
            lock_fd = os.open(".", flags, dir_fd=workspace_fd)
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise DriverError("driver_already_running") from exc

            # Resolve the engagement only through the bound workspace hierarchy.  This rejects an
            # ``engagements`` symlink and prevents a separately resolved pathname from selecting a
            # directory outside the workspace after the workspace has been bound.
            engagements_fd = _open_child_directory(workspace_fd, "engagements")
            engagement_fd = _open_child_directory(engagements_fd, engagement.name)
        except (OSError, RecordError) as exc:
            raise DriverError("driver_target_unavailable") from exc

        assert workspace_fd is not None and engagement_fd is not None
        if not _named_identity_is_current(workspace, workspace_fd) or not _named_identity_is_current(engagement, engagement_fd):
            raise DriverError("driver_target_identity_changed")
        bound = BoundRun(workspace, engagement, workspace_fd, engagement_fd)
        yield bound
        if not _named_identity_is_current(workspace, workspace_fd) or not _named_identity_is_current(engagement, engagement_fd):
            raise DriverError("driver_target_identity_changed")
    finally:
        if lock_fd is not None:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
            finally:
                os.close(lock_fd)
        if engagement_fd is not None:
            os.close(engagement_fd)
        if engagements_fd is not None:
            os.close(engagements_fd)
        if portable_fd is not None:
            os.close(portable_fd)
        if workspace_fd is not None:
            os.close(workspace_fd)


def _reduce(bound: BoundRun) -> dict[str, Any]:
    if not _named_identity_is_current(bound.workspace, bound.workspace_fd) or not _named_identity_is_current(bound.engagement, bound.engagement_fd):
        raise DriverError("driver_target_identity_changed")
    try:
        with bound_engagement_lock(bound.engagement_fd, create=False) as engagement:
            state = _reduce_engagement_unchecked(engagement)
    except RecordError as exc:
        raise DriverError(f"driver_record_{exc.code}") from exc
    if not _named_identity_is_current(bound.workspace, bound.workspace_fd) or not _named_identity_is_current(bound.engagement, bound.engagement_fd):
        raise DriverError("driver_target_identity_changed")
    return state


def _queue_payload(state: dict[str, Any], engagement: Path) -> dict[str, Any]:
    # Imported here so the #74 queue contract remains the only source of item selection policy.
    try:
        from work_queue_actions import queue_command_payload
    except ImportError as exc:  # pragma: no cover - dependency enforced by conformance
        raise DriverError("driver_queue_contract_unavailable") from exc
    try:
        payload = queue_command_payload("next", state, engagement)
    except RecordError as exc:
        raise DriverError(f"driver_queue_{exc.code}") from exc
    if (
        not isinstance(payload, dict)
        or payload.get("command") != "next"
        or payload.get("ok") is not True
        or payload.get("state_hash") != sha256_bytes(canonical_json_bytes(state))
        or payload.get("ledger_hash") != state.get("ledger_hash")
        or payload.get("source_hashes") != state.get("source_hashes")
    ):
        raise DriverError("driver_queue_contract_invalid")
    return payload


def _item_ref(item: dict[str, Any]) -> str:
    stable = {
        "class": item.get("class"),
        "entity": item.get("entity"),
        "predicate": item.get("predicate"),
        "closes_when": item.get("closes_when"),
    }
    return sha256_bytes(canonical_json_bytes(stable))


def _blocking_items(state: dict[str, Any]) -> list[dict[str, Any]]:
    queue = state.get("work_queue")
    if not isinstance(queue, list) or any(not isinstance(item, dict) for item in queue):
        raise DriverError("driver_queue_state_invalid")
    return [item for item in queue if item.get("blocking") is True]


def _normalize_model_pool(
    model: str, reviewer_model: str | Sequence[str]
) -> tuple[str, tuple[str, ...]]:
    """Validate and freeze the ordinary model and ordered reviewer pool.

    A string remains accepted by the Python API for compatibility, while the CLI supplies the
    repeated ``--reviewer-model`` values as an ordered list. Duplicate entries are rejected rather
    than silently collapsed: the configured pool is immutable evidence about which independent
    runtimes were available to the driver.
    """

    if not isinstance(model, str):
        raise DriverError("driver_model_invalid")
    if isinstance(reviewer_model, str):
        raw_pool: list[Any] = [reviewer_model]
    elif isinstance(reviewer_model, (list, tuple)):
        raw_pool = list(reviewer_model)
    else:
        raise DriverError("driver_model_invalid")
    model = model.strip()
    pool = tuple(value.strip() for value in raw_pool if isinstance(value, str))
    if (
        not model
        or IMMUTABLE_CLAUDE_MODEL.fullmatch(model) is None
        or len(pool) != len(raw_pool)
        or not pool
        or any(not value or IMMUTABLE_CLAUDE_MODEL.fullmatch(value) is None for value in pool)
    ):
        raise DriverError("driver_model_invalid")
    if model in pool:
        raise DriverError("driver_reviewer_model_not_independent")
    if len(set(pool)) != len(pool):
        raise DriverError("driver_reviewer_model_pool_invalid")
    return model, pool


def _exact_admission_constraint(
    action: dict[str, Any], path: list[str], operator: str, *, required: bool
) -> Any:
    admission = action.get("admission")
    constraints = admission.get("constraints") if isinstance(admission, dict) else None
    if not isinstance(constraints, list):
        raise DriverError("driver_reviewer_lineage_invalid")
    matches = [
        constraint
        for constraint in constraints
        if isinstance(constraint, dict)
        and constraint.get("document") == "proposal"
        and constraint.get("path") == path
        and constraint.get("operator") == operator
    ]
    if len(matches) > 1 or (required and len(matches) != 1):
        raise DriverError("driver_reviewer_lineage_invalid")
    return matches[0].get("value") if matches else None


def _origin_model(bound: BoundRun, origin_ref: str) -> str | None:
    """Read the exact admitted subject's model from the already-bound engagement inode."""

    try:
        with bound_engagement_lock(bound.engagement_fd, create=False) as engagement:
            matches = [
                record
                for kind, identity in (("event", "event_id"), ("attempt", "attempt_id"))
                for record in read_ledger(engagement, kind)
                if record.get(identity) == origin_ref
            ]
    except RecordError as exc:
        raise DriverError(f"driver_record_{exc.code}") from exc
    if len(matches) != 1:
        raise DriverError("driver_reviewer_lineage_invalid")
    model = matches[0].get("provenance", {}).get("model")
    return model if isinstance(model, str) and model else None


def _select_reviewer_model(
    *,
    bound: BoundRun,
    state: dict[str, Any],
    action: dict[str, Any],
    reviewer_pool: tuple[str, ...],
) -> str | None:
    """Select the first configured model independent of the exact reducer-owned lineage.

    The subject origin and prior reviewer run set come only from the immutable admission predicate.
    Prior run models come from the reducer's committed-review projection. ``None`` is a deliberate
    safe pause: no child is launched and the outer loop cannot spend a budget retrying an impossible
    review with the same pool.
    """

    origin_ref = _exact_admission_constraint(
        action, ["independence", "originating_run_id"], "equals", required=True
    )
    prior_runs = _exact_admission_constraint(
        action, ["prior_review_run_ids"], "set_equals", required=False
    )
    if not isinstance(origin_ref, str) or not origin_ref:
        raise DriverError("driver_reviewer_lineage_invalid")
    if prior_runs is None:
        prior_runs = []
    if (
        not isinstance(prior_runs, list)
        or any(not isinstance(value, str) or not value for value in prior_runs)
        or len(set(prior_runs)) != len(prior_runs)
    ):
        raise DriverError("driver_reviewer_lineage_invalid")

    origin_model = _origin_model(bound, origin_ref)
    run_models = state.get("reviewer_run_models")
    if not isinstance(run_models, dict):
        raise DriverError("driver_reviewer_lineage_invalid")
    prior_models: list[str] = []
    for run_id in prior_runs:
        prior_model = run_models.get(run_id)
        if not isinstance(prior_model, str) or not prior_model:
            return None
        prior_models.append(prior_model)
    if origin_model is None:
        return None
    forbidden = {origin_model, *prior_models}
    return next((candidate for candidate in reviewer_pool if candidate not in forbidden), None)


def _state_stop(state: dict[str, Any]) -> str | None:
    queue = state.get("work_queue")
    queue_control = state.get("queue_control")
    coverage = state.get("coverage")
    if not isinstance(queue, list) or not isinstance(queue_control, dict):
        raise DriverError("driver_queue_state_invalid")
    if queue_control.get("status") == "parked":
        return "operator_parked"
    if coverage == "blocked":
        return "coverage_blocked"
    if coverage == "budget_bounded":
        return "coverage_budget_bounded"
    if coverage == "coverage_dry":
        if queue:
            raise DriverError("driver_terminal_queue_invariant")
        return "completed"
    if coverage != "active":
        raise DriverError("driver_coverage_state_invalid")
    blocking = _blocking_items(state)
    if not blocking:
        if queue:
            return "operator_required"
        raise DriverError("driver_active_queue_invariant")
    return None


def load_stop_hook_settings() -> dict[str, Any]:
    if not STOP_HOOK.is_file() or STOP_HOOK.is_symlink():
        raise DriverError("driver_stop_hook_unavailable")
    python = os.path.abspath(sys.executable)
    try:
        process = subprocess.run(
            [python, str(STOP_HOOK), "--print-additional-settings"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DriverError("driver_stop_hook_unavailable") from exc
    try:
        settings = json.loads(process.stdout)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DriverError("driver_stop_hook_invalid") from exc
    if (
        process.returncode != 0
        or process.stderr
        or not isinstance(settings, dict)
        or not isinstance(settings.get("hooks"), dict)
        or not isinstance(settings["hooks"].get("Stop"), list)
        or not settings["hooks"]["Stop"]
    ):
        raise DriverError("driver_stop_hook_invalid")
    return settings


def _driver_scope(
    state: dict[str, Any], *, broker_endpoint: Path, runtime_session_ref: str
) -> dict[str, str]:
    sources = state.get("source_hashes")
    if not isinstance(sources, dict):
        raise DriverError("driver_state_sources_invalid")
    if set(sources) != {"events.jsonl", "attempts.jsonl", "artifacts.jsonl"} or any(
        not isinstance(value, str) for value in sources.values()
    ):
        raise DriverError("driver_state_sources_invalid")
    ledger_hash = state.get("ledger_hash")
    if not isinstance(ledger_hash, str):
        raise DriverError("driver_state_sources_invalid")
    return {
        "HARNESS_EXPECTED_LEDGER_HASH": ledger_hash,
        "HARNESS_EXPECTED_SOURCE_HASHES": canonical_json_bytes(sources).decode("utf-8"),
        SESSION_ENV: runtime_session_ref,
        BROKER_ENDPOINT_ENV: str(broker_endpoint),
    }


def _session_prompt(item: dict[str, Any], state: dict[str, Any], item_ref: str) -> str:
    action = item.get("next_action")
    if not isinstance(action, dict) or action.get("launchable") is not True or action.get("recompute_after") is not True:
        raise DriverError("driver_next_action_invalid")
    value = {
        "schema_version": 1,
        "task": "Execute exactly this one reducer-computed next_action, record its truthful result, then stop so the outer driver can recompute.",
        "item_ref": item_ref,
        "item": copy.deepcopy(item),
        "state_binding": {
            "ledger_hash": state.get("ledger_hash"),
            "source_hashes": copy.deepcopy(state.get("source_hashes")),
        },
        "constraints": [
            "Work only in the target repository that is already your cwd.",
            "Do not choose, reorder, or substitute another queue item.",
            "Do not prescribe or manufacture a review verdict; record the independently obtained result.",
            "Do not claim completion. The outer driver recomputes completion from the ledger.",
            "Stop after one next_action changes authoritative records, even if the same item remains.",
            "Never use operator signature material or perform an operator-only action.",
        ],
    }
    return canonical_json_bytes(value).decode("utf-8")


def _validate_action_binding(action: dict[str, Any], engagement: Path) -> None:
    """Fail closed if a rendered semantic action redirects the local execution path."""

    command = action.get("command")
    arguments = action.get("arguments")
    operation = action.get("operation")
    invocation = action.get("local_invocation")
    session_kind = action.get("session_kind")
    principal = action.get("principal")
    principal_pair_valid = (
        session_kind == "fresh_independent_reviewer" and principal == "independent_reviewer"
    ) or (
        session_kind == "ordinary_bounded" and principal in {"orchestrator", "hunter", "broker"}
    )
    expected_python = str(Path(sys.executable).absolute())
    expected_tool = str((ROOT / "tools" / "run-engagement.py").resolve())
    if (
        not isinstance(command, str)
        or not isinstance(arguments, list)
        or any(not isinstance(value, str) for value in arguments)
        or arguments[:2] != ["--engagement", str(engagement)]
        or operation != {"tool": "run-engagement", "command": command}
        or not isinstance(invocation, dict)
        or action.get("execution_principal") != "broker"
        or action.get("launchable") is not True
        or not isinstance(action.get("admission"), dict)
        or action.get("recompute_after") is not True
        or not principal_pair_valid
    ):
        raise DriverError("driver_action_binding_invalid")
    launcher = invocation.get("launcher")
    argv = invocation.get("argv")
    if (
        launcher
        != {
            "kind": "local_python_tool",
            "resolution": "render_time",
            "python": expected_python,
            "tool": expected_tool,
        }
        or not isinstance(argv, list)
        or argv != [expected_python, expected_tool, command, *arguments]
    ):
        raise DriverError("driver_action_binding_invalid")


def _budget_event(
    *,
    state: dict[str, Any],
    run_ref: str,
    budget_kind: str,
    budget: DriverBudget,
    sessions_started: int,
    elapsed_seconds: float,
    disposed_count: int,
    enumerated_count: int,
) -> dict[str, Any]:
    state_hash = sha256_bytes(canonical_json_bytes(state))
    identity = {
        "run_ref": run_ref,
        "budget_kind": budget_kind,
        "state_hash": state_hash,
        "sessions_started": sessions_started,
    }
    actor_id = f"local-uid-{os.getuid()}:broker"
    session_id = f"session-posix-{os.getuid()}-{os.getsid(0)}"
    rationale = f"External work-queue driver spent its {budget_kind} budget and recorded bounded non-completion."
    return base_event(
        event_id=f"event-driver-budget-{sha256_bytes(canonical_json_bytes(identity))[-12:]}",
        engagement_id=state["engagement_id"],
        recorded_at=utc_now(),
        actor_role="broker",
        actor_id=actor_id,
        event_type="coverage.status_changed",
        rationale=rationale,
        payload={
            "entity_id": state["engagement_id"],
            "status": "budget_bounded",
            "disposed_count": disposed_count,
            "enumerated_count": enumerated_count,
            "driver_run_ref": run_ref,
            "driver_state_hash": state_hash,
            "budget_kind": budget_kind,
            "max_sessions": budget.max_sessions,
            "max_wall_seconds": budget.max_wall_seconds,
            "sessions_started": sessions_started,
            "wall_seconds": elapsed_seconds,
        },
        state_changes=[
            {
                "dimension": "coverage",
                "entity_id": state["engagement_id"],
                "previous": state["coverage"],
                "current": "budget_bounded",
            }
        ],
        session_id=session_id,
        operation_class="notebook",
    )


def record_budget_boundary(
    *,
    bound: BoundRun,
    run_ref: str,
    budget_kind: str,
    budget: DriverBudget,
    sessions_started: int,
    elapsed_seconds: float,
    seen_item_refs: set[str],
) -> tuple[str, dict[str, Any]]:
    """Atomically let a newer operator/coverage transition win, else record budget spent."""

    if not _named_identity_is_current(bound.workspace, bound.workspace_fd) or not _named_identity_is_current(bound.engagement, bound.engagement_fd):
        raise DriverError("driver_target_identity_changed")
    try:
        with bound_engagement_lock(bound.engagement_fd, create=False) as engagement:
            if not _named_identity_is_current(bound.workspace, bound.workspace_fd) or not _named_identity_is_current(bound.engagement, bound.engagement_fd):
                raise DriverError("driver_target_identity_changed")
            state = _reduce_engagement_unchecked(engagement)
            prior_stop = _state_stop(state)
            if prior_stop is not None:
                return prior_stop, state
            current_refs = {_item_ref(item) for item in _blocking_items(state)}
            seen_item_refs.update(current_refs)
            enumerated_count = len(seen_item_refs)
            disposed_count = len(seen_item_refs - current_refs)
            if enumerated_count < 1:
                raise DriverError("driver_budget_denominator_invalid")
            event = _budget_event(
                state=state,
                run_ref=run_ref,
                budget_kind=budget_kind,
                budget=budget,
                sessions_started=sessions_started,
                elapsed_seconds=elapsed_seconds,
                disposed_count=disposed_count,
                enumerated_count=enumerated_count,
            )
            _append_kernel_event_idempotent(engagement, event, lock_held=True)
            after = _reduce_engagement_unchecked(engagement)
    except RecordError as exc:
        raise DriverError(f"driver_budget_{exc.code}") from exc
    if not _named_identity_is_current(bound.workspace, bound.workspace_fd) or not _named_identity_is_current(bound.engagement, bound.engagement_fd):
        raise DriverError("driver_target_identity_changed")
    return "budget_spent", after


def _result(
    *,
    run_ref: str,
    status: str,
    budget_kind: str | None,
    budget: DriverBudget,
    sessions_started: int,
    started_at: float,
    state: dict[str, Any],
    seen_item_refs: set[str],
    history: list[dict[str, Any]],
    model: str,
    reviewer_pool: tuple[str, ...],
) -> dict[str, Any]:
    current_refs = {_item_ref(item) for item in _blocking_items(state)}
    seen_item_refs.update(current_refs)
    wall_seconds = round(time.monotonic() - started_at, 6)
    wall_deadline_overrun_seconds = round(
        max(0.0, wall_seconds - budget.max_wall_seconds),
        6,
    )
    return {
        "schema_version": 1,
        "ok": True,
        "run_ref": run_ref,
        "status": status,
        "completed": status == "completed",
        "budget_kind": budget_kind,
        "budget": {
            "max_sessions": budget.max_sessions,
            "max_wall_seconds": budget.max_wall_seconds,
            "session_timeout_seconds": budget.session_timeout_seconds,
            "session_max_budget_usd": budget.session_max_budget_usd,
        },
        "models": {"ordinary": model, "reviewer_pool": list(reviewer_pool)},
        "sessions_started": sessions_started,
        "wall_seconds": wall_seconds,
        "wall_deadline_overrun_seconds": wall_deadline_overrun_seconds,
        "queue": {
            "blocking_count": len(current_refs),
            "total_count": len(state.get("work_queue", [])),
            "seen_count": len(seen_item_refs),
            "disposed_count": len(seen_item_refs - current_refs),
        },
        "final_state_hash": sha256_bytes(canonical_json_bytes(state)),
        "history": history,
    }


def run_driver(
    *,
    workspace: Path,
    engagement: Path,
    executable: Path,
    model: str,
    reviewer_model: str | Sequence[str],
    budget: DriverBudget,
    stop_requested: Callable[[], bool] = lambda: False,
) -> dict[str, Any]:
    budget.validate()
    model, reviewer_pool = _normalize_model_pool(model, reviewer_model)
    run_ref = "driver-" + uuid.uuid4().hex
    started_at = time.monotonic()
    sessions_started = 0
    seen_item_refs: set[str] = set()
    history: list[dict[str, Any]] = []
    settings: dict[str, Any] | None = None

    with bind_run(workspace, engagement) as bound:
        state = _reduce(bound)
        while True:
            seen_item_refs.update(_item_ref(item) for item in _blocking_items(state))
            stop = _state_stop(state)
            if stop is not None:
                return _result(
                    run_ref=run_ref,
                    status=stop,
                    budget_kind=None,
                    budget=budget,
                    sessions_started=sessions_started,
                    started_at=started_at,
                    state=state,
                    seen_item_refs=seen_item_refs,
                    history=history,
                    model=model,
                    reviewer_pool=reviewer_pool,
                )
            if stop_requested():
                return _result(
                    run_ref=run_ref,
                    status="interrupted_unrecorded",
                    budget_kind=None,
                    budget=budget,
                    sessions_started=sessions_started,
                    started_at=started_at,
                    state=state,
                    seen_item_refs=seen_item_refs,
                    history=history,
                    model=model,
                    reviewer_pool=reviewer_pool,
                )

            elapsed = time.monotonic() - started_at
            budget_kind = None
            if elapsed >= budget.max_wall_seconds:
                budget_kind = "max_wall_seconds"
            elif sessions_started >= budget.max_sessions:
                budget_kind = "max_sessions"
            if budget_kind is not None:
                status, state = record_budget_boundary(
                    bound=bound,
                    run_ref=run_ref,
                    budget_kind=budget_kind,
                    budget=budget,
                    sessions_started=sessions_started,
                    elapsed_seconds=elapsed,
                    seen_item_refs=seen_item_refs,
                )
                return _result(
                    run_ref=run_ref,
                    status=status,
                    budget_kind=budget_kind if status == "budget_spent" else None,
                    budget=budget,
                    sessions_started=sessions_started,
                    started_at=started_at,
                    state=state,
                    seen_item_refs=seen_item_refs,
                    history=history,
                    model=model,
                    reviewer_pool=reviewer_pool,
                )

            payload = _queue_payload(state, bound.engagement)
            queue_view = payload.get("queue")
            if not isinstance(queue_view, dict) or queue_view.get("should_block") is not True:
                raise DriverError("driver_queue_gate_mismatch")
            item = payload.get("item")
            if not isinstance(item, dict) or item.get("blocking") is not True:
                raise DriverError("driver_next_item_invalid")
            item_ref = _item_ref(item)
            action = item.get("next_action")
            if not isinstance(action, dict):
                raise DriverError("driver_next_action_invalid")
            _validate_action_binding(action, bound.engagement)
            session_kind = action.get("session_kind")
            if session_kind == "ordinary_bounded":
                session_model = model
            elif session_kind == "fresh_independent_reviewer":
                session_model = _select_reviewer_model(
                    bound=bound,
                    state=state,
                    action=action,
                    reviewer_pool=reviewer_pool,
                )
                if session_model is None:
                    return _result(
                        run_ref=run_ref,
                        status="reviewer_model_unavailable",
                        budget_kind=None,
                        budget=budget,
                        sessions_started=sessions_started,
                        started_at=started_at,
                        state=state,
                        seen_item_refs=seen_item_refs,
                        history=history,
                        model=model,
                        reviewer_pool=reviewer_pool,
                    )
            else:
                raise DriverError("driver_session_kind_invalid")
            before_hash = sha256_bytes(canonical_json_bytes(state))
            if settings is None:
                settings = load_stop_hook_settings()
            # Hook loading and operator activity may advance the ledger after selection. Recompute
            # before launch so a stale item is never knowingly dispatched.
            launch_state = _reduce(bound)
            if sha256_bytes(canonical_json_bytes(launch_state)) != before_hash:
                state = launch_state
                continue
            if stop_requested():
                continue
            remaining_wall = budget.max_wall_seconds - (time.monotonic() - started_at)
            if remaining_wall <= 0:
                continue
            timeout = min(budget.session_timeout_seconds, remaining_wall)
            runtime_session_ref = str(uuid.uuid4())
            admission_token = new_admission_token()
            os_session_id: int | None = None

            try:
                admission = arm_action_admission(
                    engagement_fd=bound.engagement_fd,
                    state=state,
                    item=item,
                    item_ref=item_ref,
                    driver_run_ref=run_ref,
                    runtime_session_ref=runtime_session_ref,
                    runtime_model=session_model,
                    token=admission_token,
                )
                try:
                    with DriverActionBroker(
                        engagement_fd=bound.engagement_fd,
                        logical_engagement=bound.engagement,
                        admission=admission,
                        execution_deadline=started_at + budget.max_wall_seconds,
                    ) as broker:
                        def activate(os_sid: int) -> None:
                            nonlocal os_session_id
                            os_session_id = os_sid
                            activate_action_admission(
                                engagement_fd=bound.engagement_fd,
                                token=admission_token,
                                os_session_id=os_sid,
                                admission=admission,
                            )
                            broker.activate(os_sid)

                        session = run_claude_session(
                            executable=executable,
                            model=session_model,
                            prompt=_session_prompt(item, state, item_ref),
                            session_ref=runtime_session_ref,
                            workspace_fd=bound.workspace_fd,
                            engagement=bound.engagement,
                            settings=settings,
                            driver_scope=_driver_scope(
                                state,
                                broker_endpoint=broker.endpoint,
                                runtime_session_ref=runtime_session_ref,
                            ),
                            timeout_seconds=timeout,
                            max_budget_usd=budget.session_max_budget_usd,
                            on_process_started=activate,
                        )
                finally:
                    disarm_action_admission(
                        engagement_fd=bound.engagement_fd,
                        token=admission_token,
                        os_session_id=os_session_id,
                    )
            except RecordError as exc:
                raise DriverError(f"driver_admission_{exc.code}") from exc
            except SessionLaunchError as exc:
                raise DriverError(f"driver_{exc.code}") from exc
            sessions_started += 1
            state = _reduce(bound)
            history.append(
                {
                    "ordinal": sessions_started,
                    "item_ref": item_ref,
                    "item_class": item.get("class"),
                    "action_id": action.get("action_id"),
                    "session_kind": action.get("session_kind"),
                    "principal": action.get("principal"),
                    "execution_principal": action.get("execution_principal"),
                    "runtime_model": session_model,
                    "before_state_hash": before_hash,
                    "after_state_hash": sha256_bytes(canonical_json_bytes(state)),
                    "runtime": session.as_dict(),
                }
            )


class SignalStop:
    def __init__(self) -> None:
        self.requested = False

    def __call__(self) -> bool:
        return self.requested

    def handle(self, _signum: int, _frame: object) -> None:
        self.requested = True
