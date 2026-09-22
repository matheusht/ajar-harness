#!/usr/bin/env python3
"""External, budget-bounded driver for one target-local engagement queue."""

from __future__ import annotations

import base64
import copy
import fcntl
import json
import math
import os
import re
import shlex
import stat
import subprocess
import sys
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterator, Sequence

from claude_work_session import (
    SessionLaunchError,
    SessionResult,
    _summary_from_output,
    run_claude_session,
)
from docker_session_runtime import (
    CONTROL_DESTINATION,
    HARNESS_DESTINATION,
    WORKSPACE_DESTINATION,
    DockerRuntimeError,
    DockerRuntimeLimits,
    DockerRuntimeSpec,
    DockerSessionIdentity,
    prepare_docker_session,
)
from engagement_records import RecordError, canonical_json_bytes, sha256_bytes
from engagement_state import (
    _append_kernel_event_idempotent,
    _open_absolute_directory,
    _reduce_engagement_unchecked,
    base_event,
    blocking_work_identities,
    bound_engagement_lock,
    engagement_may_end,
    project_current_terminal_work_state,
    read_governed_file,
    read_ledger,
    utc_now,
)
from driver_action_admission import (
    BROKER_ENDPOINT_ENV,
    SESSION_ENV,
    DriverActionBroker,
    activate_docker_action_admission,
    activate_action_admission,
    arm_action_admission,
    disarm_action_admission,
    new_admission_token,
    new_container_broker_session_key,
)
from frozen_corpus import require_enumerated_count_matches, resolve_frozen_corpus_denominator
from hunter_view import HunterView, HunterViewError, compile_hunter_view


ROOT = Path(__file__).resolve().parents[1]
STOP_HOOK = ROOT / "tools" / "claude-stop-hook.py"
IMMUTABLE_CLAUDE_MODEL = re.compile(r"^claude-[a-z0-9]+(?:-[a-z0-9]+)*-[0-9]{8}$")
IMMUTABLE_DOCKER_IMAGE = re.compile(r"^[^\s@]+@sha256:[0-9a-f]{64}$")
DOCKER_STORAGE_EXIT_CODE = 73
DOCKER_SESSION_FILE = "session.json"
DOCKER_BROKER_MANIFEST_FILE = "broker-manifest.json"
CONTAINER_SUPERVISOR = f"{HARNESS_DESTINATION}/tools/container_session_supervisor.py"
CONTAINER_BROKER_CLIENT = f"{HARNESS_DESTINATION}/tools/container_broker_client.py"
CONTAINER_STOP_HOOK = f"{HARNESS_DESTINATION}/tools/container_broker_client.py"
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


def _is_immutable_docker_image(value: object) -> bool:
    if not isinstance(value, str) or IMMUTABLE_DOCKER_IMAGE.fullmatch(value) is None:
        return False
    repository = value.rsplit("@sha256:", 1)[0]
    return ":" not in repository.rsplit("/", 1)[-1]


def _is_absolute_container_executable(value: object) -> bool:
    if not isinstance(value, str) or "\x00" in value:
        return False
    try:
        encoded = value.encode("utf-8")
        normalized = PurePosixPath(value)
    except (UnicodeError, TypeError, ValueError):
        return False
    return bool(
        1 <= len(encoded) <= 4096
        and normalized.is_absolute()
        and not value.startswith("//")
        and ".." not in normalized.parts
        and normalized.name
        and str(normalized) == value
    )


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


@dataclass(frozen=True)
class DockerQueueBackend:
    """Explicit, immutable parent-side configuration for the strong queue backend."""

    image: str
    python_executable: str
    docker_executable: Path
    limits: DockerRuntimeLimits
    advertised_broker_host: str = "host.docker.internal"

    def validate(self) -> None:
        if (
            not _is_immutable_docker_image(self.image)
            or not _is_absolute_container_executable(self.python_executable)
            or not isinstance(self.docker_executable, Path)
            or not self.docker_executable.is_absolute()
            or not isinstance(self.limits, DockerRuntimeLimits)
            or self.advertised_broker_host != "host.docker.internal"
        ):
            raise DriverError("driver_docker_backend_invalid")
        try:
            self.limits.validate()
        except DockerRuntimeError as exc:
            raise DriverError(f"driver_{exc.code}") from exc


@dataclass(frozen=True)
class _QueueSessionExecution:
    session: SessionResult
    interrupted: bool


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
        blocking = _blocking_items(state)
        if blocking:
            identities = blocking_work_identities(state)
            digest = sha256_bytes(canonical_json_bytes(identities))
            exact_override = next(
                (
                    override
                    for override in reversed(state.get("ending_overrides", []))
                    if isinstance(override, dict)
                    and override.get("terminal_kind") == "coverage"
                    and override.get("status") == "coverage_dry"
                    and override.get("event_ref") == state.get("coverage_relevant_event_ref")
                    and override.get("blocking_items") == identities
                    and override.get("blocking_queue_digest") == digest
                    and override.get("attempt_ledger_count") == state.get("attempt_count")
                    and override.get("attempt_ledger_digest")
                    == state.get("source_hashes", {}).get("attempts.jsonl")
                ),
                None,
            )
            if exact_override is None:
                raise DriverError("driver_terminal_queue_invariant")
            return "completed"
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


def _driver_binding_values(
    state: dict[str, Any], *, runtime_session_ref: str
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
    }


def _driver_scope(
    state: dict[str, Any], *, broker_endpoint: Path, runtime_session_ref: str
) -> dict[str, str]:
    try:
        canonical_broker_endpoint = broker_endpoint.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise DriverError("driver_action_broker_unavailable") from exc
    return {
        **_driver_binding_values(state, runtime_session_ref=runtime_session_ref),
        BROKER_ENDPOINT_ENV: str(canonical_broker_endpoint),
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


def _container_session_prompt(
    item: dict[str, Any], state: dict[str, Any], item_ref: str, *, python_executable: str
) -> str:
    """Render the same reducer action with a container-local authenticated invocation hint."""

    value = json.loads(_session_prompt(item, state, item_ref))
    action = value.get("item", {}).get("next_action")
    if not isinstance(action, dict):
        raise DriverError("driver_next_action_invalid")
    command = action.get("command")
    arguments = action.get("arguments")
    if not isinstance(command, str) or not isinstance(arguments, list):
        raise DriverError("driver_next_action_invalid")
    value["container_action_transport"] = {
        "kind": "authenticated_supervisor_relay",
        "python": python_executable,
        "client": CONTAINER_BROKER_CLIENT,
        "argv_template": [
            python_executable,
            CONTAINER_BROKER_CLIENT,
            "action",
            "--command",
            command,
            "--arguments-json",
            "<JSON array matching next_action.arguments after resolving placeholders>",
        ],
    }
    value["constraints"].insert(
        1,
        "Inside the container, use container_action_transport; host local_invocation paths are evidence only and are not executable here.",
    )
    return canonical_json_bytes(value).decode("utf-8")


def _hunter_container_prompt(*, item: dict[str, Any], view_digest: str, python_executable: str) -> str:
    action = item.get("next_action")
    if not isinstance(action, dict) or action.get("principal") != "hunter" or not isinstance(action.get("arguments"), list):
        raise DriverError("driver_next_action_invalid")
    arguments = list(action["arguments"])
    for index, value in enumerate(arguments):
        if index and arguments[index - 1] == "--engagement":
            arguments[index] = "/workspace"
        elif isinstance(value, str) and value.startswith("<") and value.endswith(">"):
            arguments[index] = "/scratch/hunter-action-input.json"
    return canonical_json_bytes({
        "schema_version": 1,
        "task": "Read /workspace/brief.json, execute exactly its one bounded experiment, write the exact admitted input document under /scratch, submit it through the authenticated broker, then stop.",
        "principal": "hunter",
        "view_type": "hunter-current-v1",
        "view_digest": view_digest,
        "container_action_transport": {
            "kind": "authenticated_supervisor_relay",
            "python": python_executable,
            "client": CONTAINER_BROKER_CLIENT,
            "argv": [python_executable, CONTAINER_BROKER_CLIENT, "action", "--command", action["command"], "--arguments-json", json.dumps(arguments, separators=(",", ":"))],
        },
        "constraints": [
            "Use only files present under /workspace and /scratch.",
            "Do not infer or request hidden engagement state, prior verdicts, memory, gold, or unrelated source.",
            "Return observed evidence truthfully; only the orchestrator adjudicates.",
        ],
    }).decode("utf-8")


def _container_stop_hook_settings(python_executable: str) -> dict[str, Any]:
    command = " ".join(
        (
            shlex.quote(python_executable),
            shlex.quote(CONTAINER_STOP_HOOK),
            "stop-hook",
        )
    )
    return {
        "hooks": {
            "Stop": [
                {
                    "hooks": [
                        {"command": command, "timeout": 10, "type": "command"}
                    ]
                }
            ]
        }
    }


def _container_engagement_path(bound: BoundRun) -> str:
    return f"{WORKSPACE_DESTINATION}/engagements/{bound.engagement.name}"


def _docker_session_bytes(
    *,
    bound: BoundRun,
    backend: DockerQueueBackend,
    executable: Path,
    model: str,
    prompt: str,
    session_ref: str,
    state: dict[str, Any],
    max_budget_usd: float | None,
    view_binding: dict[str, str] | None = None,
) -> bytes:
    executable_text = os.fspath(executable)
    if not _is_absolute_container_executable(executable_text):
        raise DriverError("driver_container_runtime_invalid")
    settings = _container_stop_hook_settings(backend.python_executable)
    command = [
        executable_text,
        "-p",
        "--session-id",
        session_ref,
        "--no-session-persistence",
        "--output-format",
        "json",
        "--permission-mode",
        "dontAsk",
        "--model",
        model,
        "--settings",
        json.dumps(settings, sort_keys=True, separators=(",", ":")),
    ]
    if max_budget_usd is not None:
        command.extend(["--max-budget-usd", str(max_budget_usd)])
    command.append(prompt)
    environment = {
        **_driver_binding_values(state, runtime_session_ref=session_ref),
        "HARNESS_ACTIVE_ENGAGEMENT": "/workspace" if view_binding is not None else _container_engagement_path(bound),
    }
    if view_binding is not None:
        environment.update({"HARNESS_COGNITIVE_PRINCIPAL": "hunter", "HARNESS_HUNTER_VIEW_DIGEST": view_binding["view_digest"]})
    raw = canonical_json_bytes({
        "schema_version": 1,
        "command": command,
        "environment": environment,
    })
    if len(raw) > 512 * 1024:
        raise DriverError("driver_container_session_invalid")
    return raw


def _model_auth_bootstrap(session_key: bytes) -> bytes:
    if not isinstance(session_key, bytes) or len(session_key) != 32:
        raise DriverError("driver_container_broker_key_invalid")
    raw = canonical_json_bytes(
        {
            "schema_version": 1,
            "environment": {},
            "broker_session_key_base64": base64.b64encode(session_key).decode("ascii"),
        }
    )
    if len(raw) > 64 * 1024:
        raise DriverError("driver_model_auth_invalid")
    return raw


def _validate_parent_provider_auth() -> None:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        if any(
            os.environ.get(name)
            for name in ("ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN")
        ):
            raise DriverError("driver_provider_auth_unsupported")
        raise DriverError("driver_provider_auth_missing")
    if "\x00" in api_key or len(api_key.encode("utf-8")) > 32 * 1024:
        raise DriverError("driver_provider_auth_invalid")


def _run_docker_queue_session(
    *,
    bound: BoundRun,
    backend: DockerQueueBackend,
    executable: Path,
    model: str,
    prompt: str,
    session_ref: str,
    state: dict[str, Any],
    timeout_seconds: float,
    max_budget_usd: float | None,
    read_only_inputs: tuple[Path, ...],
    admission: dict[str, Any],
    admission_token: str,
    execution_deadline: float,
    stop_requested: Callable[[], bool],
    workspace_mount: Path | None = None,
    harness_mount: Path | None = None,
    view_binding: dict[str, str] | None = None,
    cognitive_view: HunterView | None = None,
) -> _QueueSessionExecution:
    _validate_parent_provider_auth()
    session_bytes = _docker_session_bytes(
        bound=bound,
        backend=backend,
        executable=executable,
        model=model,
        prompt=prompt,
        session_ref=session_ref,
        state=state,
        max_budget_usd=max_budget_usd,
        view_binding=view_binding,
    )
    session_digest = sha256_bytes(session_bytes)
    spec = DockerRuntimeSpec(
        image=backend.image,
        executable=backend.python_executable,
        argv=(
            CONTAINER_SUPERVISOR,
            "--session",
            f"{CONTROL_DESTINATION}/{DOCKER_SESSION_FILE}",
            "--session-sha256",
            session_digest,
        ),
        workspace=bound.workspace if workspace_mount is None else workspace_mount,
        harness=ROOT if harness_mount is None else harness_mount,
        read_only_inputs=read_only_inputs,
        limits=backend.limits,
        docker_executable=backend.docker_executable,
        network_internal=False,
        supervisor_write_broker=True,
    )
    try:
        with prepare_docker_session(spec) as prepared:
            identity = prepared.identity
            docker_identity = {
                "container_id": identity.container_id,
                "container_config_digest": identity.config_digest,
            }
            session_key = new_container_broker_session_key()
            auth_bootstrap = _model_auth_bootstrap(session_key)
            with DriverActionBroker(
                engagement_fd=bound.engagement_fd,
                logical_engagement=bound.engagement,
                admission=admission,
                execution_deadline=execution_deadline,
                docker_identity=docker_identity,
                docker_session_key=session_key,
            ) as broker:
                manifest_bytes = canonical_json_bytes(
                    broker.container_manifest(
                        advertised_host=backend.advertised_broker_host
                    )
                )
                prepared.write_control_file(DOCKER_SESSION_FILE, session_bytes)
                prepared.write_control_file(
                    DOCKER_BROKER_MANIFEST_FILE, manifest_bytes
                )

                def activate(current: DockerSessionIdentity) -> None:
                    if current != identity or not _named_identity_is_current(
                        bound.workspace, bound.workspace_fd
                    ) or not _named_identity_is_current(
                        bound.engagement, bound.engagement_fd
                    ):
                        raise DriverError("driver_target_identity_changed")
                    if cognitive_view is not None:
                        try:
                            current_state = _reduce(bound)
                            cognitive_view.assert_current(workspace=bound.workspace, engagement=bound.engagement, state=current_state, item=_queue_payload(current_state, bound.engagement)["item"], methodology_root=ROOT / "skills")
                        except HunterViewError as exc:
                            raise DriverError(exc.code) from exc
                    activate_docker_action_admission(
                        engagement_fd=bound.engagement_fd,
                        token=admission_token,
                        container_id=identity.container_id,
                        container_config_digest=identity.config_digest,
                        admission=admission,
                    )
                    broker.activate_docker()

                result = prepared.start(
                    timeout_seconds=timeout_seconds,
                    on_process_started=activate,
                    stop_requested=stop_requested,
                    stdin_bytes=auth_bootstrap,
                )
    except DockerRuntimeError as exc:
        raise DriverError(f"driver_{exc.code}") from exc

    if result.returncode == DOCKER_STORAGE_EXIT_CODE and not (
        result.timed_out or result.interrupted
    ):
        raise DriverError("driver_session_storage_exceeded")
    if result.oom_killed:
        raise DriverError("driver_session_oom_killed")
    if result.timed_out:
        session = SessionResult(session_ref, True, True, result.returncode, False, None, None)
    elif result.output_truncated:
        # A retained prefix is not a complete Claude result document even when that prefix happens
        # to parse.  Queue truth still comes from the reducer, but runtime telemetry must not label
        # truncated model output as a valid provider response.
        session = SessionResult(
            session_ref, True, False, result.returncode, False, None, None
        )
    else:
        output_was_json, reported_error, cost = _summary_from_output(result.stdout)
        session = SessionResult(
            session_ref,
            True,
            False,
            result.returncode,
            output_was_json,
            reported_error,
            cost,
        )
    return _QueueSessionExecution(session=session, interrupted=result.interrupted)


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
    enumerated_count: int,
    corpus_enumeration_ref: str,
    corpus_artifact_refs: Sequence[str],
    recorded_at: str,
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
        recorded_at=recorded_at,
        actor_role="broker",
        actor_id=actor_id,
        event_type="coverage.status_changed",
        rationale=rationale,
        payload={
            "entity_id": state["engagement_id"],
            "status": "budget_bounded",
            # This count has the corpus row as its unit. The driver has no authoritative
            # visitation evidence yet, so queue-item progress must never be substituted here.
            "disposed_count": 0,
            "enumerated_count": enumerated_count,
            "corpus_enumeration_ref": corpus_enumeration_ref,
            "driver_run_ref": run_ref,
            "driver_state_hash": state_hash,
            "budget_kind": budget_kind,
            "max_sessions": budget.max_sessions,
            "max_wall_seconds": budget.max_wall_seconds,
            "sessions_started": sessions_started,
            "wall_seconds": elapsed_seconds,
        },
        evidence_refs=list(corpus_artifact_refs),
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
    corpus_enumeration_ref: str | None = None,
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
            recorded_at = utc_now()
            projected = project_current_terminal_work_state(
                state,
                read_ledger(engagement, "attempt"),
                coverage="budget_bounded",
            )
            if not engagement_may_end(projected) or not corpus_enumeration_ref:
                return "operator_required", state
            artifacts = read_ledger(engagement, "artifact")
            events = read_ledger(engagement, "event")
            genesis_scope = events[0]
            scope_bytes = read_governed_file(
                engagement
                / genesis_scope["payload"]["scope_snapshot_path"]
            )
            denominator = resolve_frozen_corpus_denominator(
                engagement,
                artifacts,
                corpus_enumeration_ref,
                recorded_at,
                scope_bytes,
                genesis_scope["recorded_at"],
            )
            enumerated_count = denominator["row_count"]
            require_enumerated_count_matches(enumerated_count, denominator)
            if enumerated_count < 1:
                raise DriverError("driver_budget_denominator_invalid")
            event = _budget_event(
                state=state,
                run_ref=run_ref,
                budget_kind=budget_kind,
                budget=budget,
                sessions_started=sessions_started,
                elapsed_seconds=elapsed_seconds,
                enumerated_count=enumerated_count,
                corpus_enumeration_ref=corpus_enumeration_ref,
                corpus_artifact_refs=[
                    denominator["manifest_artifact_ref"],
                    denominator["enumeration_artifact_ref"],
                ],
                recorded_at=recorded_at,
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
            # These are queue-identity counts, kept separate from the corpus-row counts in a
            # coverage.status_changed event and the reducer's coverage_counts projection.
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
    read_only_inputs: Sequence[Path] = (),
    stop_requested: Callable[[], bool] = lambda: False,
    docker_backend: DockerQueueBackend | None = None,
    corpus_enumeration_ref: str | None = None,
) -> dict[str, Any]:
    budget.validate()
    if docker_backend is not None:
        if not isinstance(docker_backend, DockerQueueBackend):
            raise DriverError("driver_docker_backend_invalid")
        docker_backend.validate()
    if isinstance(read_only_inputs, (str, bytes, os.PathLike)) or not isinstance(
        read_only_inputs, Sequence
    ):
        raise DriverError("driver_read_input_invalid")
    try:
        frozen_read_only_inputs = tuple(Path(value) for value in read_only_inputs)
    except (TypeError, ValueError) as exc:
        raise DriverError("driver_read_input_invalid") from exc
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
                    corpus_enumeration_ref=corpus_enumeration_ref,
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
            if docker_backend is None and settings is None:
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
            docker_interrupted = False
            hunter_view: HunterView | None = None

            try:
                if action.get("principal") == "hunter":
                    if docker_backend is None:
                        raise DriverError("driver_hunter_requires_docker")
                    try:
                        hunter_view = compile_hunter_view(
                            workspace=bound.workspace,
                            engagement=bound.engagement,
                            state=state,
                            item=item,
                            target_inputs=frozen_read_only_inputs,
                            methodology_root=ROOT / "skills",
                        )
                    except HunterViewError as exc:
                        raise DriverError(exc.code) from exc
                view_binding = None if hunter_view is None else {
                    "cognitive_principal": "hunter",
                    "view_type": "hunter-current-v1",
                    "view_digest": hunter_view.view_digest,
                    "input_corpus_digest": hunter_view.input_corpus_digest,
                    "treatment": hunter_view.manifest["treatment"],
                }
                admission = arm_action_admission(
                    engagement_fd=bound.engagement_fd,
                    state=state,
                    item=item,
                    item_ref=item_ref,
                    driver_run_ref=run_ref,
                    runtime_session_ref=runtime_session_ref,
                    runtime_model=session_model,
                    token=admission_token,
                    view_binding=view_binding,
                )
                try:
                    if docker_backend is not None:
                        execution = _run_docker_queue_session(
                            bound=bound,
                            backend=docker_backend,
                            executable=executable,
                            model=session_model,
                            prompt=(
                                _hunter_container_prompt(item=item, view_digest=hunter_view.view_digest, python_executable=docker_backend.python_executable)
                                if hunter_view is not None else
                                _container_session_prompt(item, state, item_ref, python_executable=docker_backend.python_executable)
                            ),
                            session_ref=runtime_session_ref,
                            state=state,
                            timeout_seconds=timeout,
                            max_budget_usd=budget.session_max_budget_usd,
                            read_only_inputs=() if hunter_view is not None else frozen_read_only_inputs,
                            admission=admission,
                            admission_token=admission_token,
                            execution_deadline=started_at + budget.max_wall_seconds,
                            stop_requested=stop_requested,
                            workspace_mount=None if hunter_view is None else hunter_view.projection,
                            harness_mount=None if hunter_view is None else hunter_view.runtime,
                            view_binding=view_binding,
                            cognitive_view=hunter_view,
                        )
                        session = execution.session
                        docker_interrupted = execution.interrupted
                    else:
                        assert settings is not None
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
                                workspace=bound.workspace,
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
                                read_only_inputs=frozen_read_only_inputs,
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
            finally:
                if hunter_view is not None:
                    hunter_view.close()
            sessions_started += 1
            state = _reduce(bound)
            history_entry = {
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
            if view_binding is not None:
                history_entry["cognitive_view"] = copy.deepcopy(view_binding)
                # The hunter never sees reducer commitments. The parent retains the full current
                # ledger/source binding separately so unrelated hidden changes cannot perturb the
                # cognitive digest while admission remains bound to all authoritative inputs.
                history_entry["admission_state_binding"] = copy.deepcopy(admission["state_binding"])
            terminal_status = _state_stop(state)
            if terminal_status is not None:
                history.append(history_entry)
                return _result(
                    run_ref=run_ref,
                    status=terminal_status,
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
            if docker_interrupted:
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
            history.append(history_entry)


class SignalStop:
    def __init__(self) -> None:
        self.requested = False

    def __call__(self) -> bool:
        return self.requested

    def handle(self, _signum: int, _frame: object) -> None:
        self.requested = True
