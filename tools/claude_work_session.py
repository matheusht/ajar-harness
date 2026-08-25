#!/usr/bin/env python3
"""Run one broker-scoped Claude Code session without retaining model content.

The outer work-queue driver owns repetition and completion.  This adapter owns only one process:
it starts Claude in the already-bound target workspace, applies the harness Stop-hook settings,
enforces a leader wall timeout, and returns a content-free execution summary. Cleanup proves absence
of the original process group and same-UID descendants that retain the inherited sentinel vnode.
It does not claim to contain a deliberate daemon that closes that descriptor before detaching; the
wall timeout is not a security boundary for that residual (tracked by #83).
"""

from __future__ import annotations

import json
import math
import os
import select
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from darwin_process_containment import (
    ContainmentUnavailable,
    create_sentinel,
    drain_holders,
)


MAX_CAPTURE_BYTES = 1024 * 1024
CAPTURE_READ_BYTES = 64 * 1024
CAPTURE_POLL_SECONDS = 0.05
WATCHDOG_READY_TIMEOUT_SECONDS = 2.0
WATCHDOG_EXIT_TIMEOUT_SECONDS = 5.0
OPERATOR_ENV_KEYS = frozenset(
    {
        "HARNESS_OPERATOR_SIGNATURE_FILE",
        "HARNESS_OPERATOR_ALLOWED_SIGNERS_FILE",
    }
)
DRIVER_SCOPE_ENV_KEYS = frozenset(
    {
        "HARNESS_EXPECTED_LEDGER_HASH",
        "HARNESS_EXPECTED_SOURCE_HASHES",
        "HARNESS_EXPECTED_RUNTIME_SESSION_REF",
        "HARNESS_DRIVER_ACTION_BROKER",
    }
)
RUNTIME_ENV_KEYS = frozenset(
    {
        "PATH",
        "HOME",
        "USER",
        "LOGNAME",
        "SHELL",
        "TMPDIR",
        "TMP",
        "TEMP",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "TERM",
        "COLORTERM",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "NODE_EXTRA_CA_CERTS",
    }
)
MODEL_AUTH_ENV_KEYS = frozenset(
    {
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "CLAUDE_CODE_OAUTH_TOKEN",
        "ANTHROPIC_BASE_URL",
    }
)


class SessionLaunchError(Exception):
    """The session could not be started safely."""

    def __init__(self, message: str, *, code: str = "session_start_failed"):
        super().__init__(message)
        self.code = code


@contextmanager
def _containment_sentinel() -> Any:
    try:
        descriptor, path = create_sentinel()
    except (OSError, ContainmentUnavailable) as exc:
        raise SessionLaunchError(
            "Darwin sentinel descendant containment is unavailable",
            code="descendant_containment_unavailable",
        ) from exc
    try:
        yield descriptor, path
    finally:
        _close_fd(descriptor)
        path.unlink(missing_ok=True)


@dataclass(frozen=True)
class SessionResult:
    session_ref: str
    started: bool
    timed_out: bool
    returncode: int | None
    output_was_json: bool
    runtime_reported_error: bool | None
    cost_usd: float | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "session_ref": self.session_ref,
            "started": self.started,
            "timed_out": self.timed_out,
            "returncode": self.returncode,
            "output_was_json": self.output_was_json,
            "runtime_reported_error": self.runtime_reported_error,
            "cost_usd": self.cost_usd,
        }


def _bounded_capture(value: bytes) -> bytes:
    if len(value) > MAX_CAPTURE_BYTES:
        return value[:MAX_CAPTURE_BYTES]
    return value


class _BoundedOutputCapture:
    """Continuously drain child output while retaining only a fixed stdout prefix."""

    def __init__(self) -> None:
        self._stdout_read_fd, self.stdout_write_fd = os.pipe()
        self._stderr_read_fd, self.stderr_write_fd = os.pipe()
        self._captured_stdout = bytearray()
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._drain,
            name="claude-session-output-drain",
        )
        self._started = False
        self._finished = False

    def __enter__(self) -> _BoundedOutputCapture:
        try:
            os.set_blocking(self._stdout_read_fd, False)
            os.set_blocking(self._stderr_read_fd, False)
            self._thread.start()
            self._started = True
        except BaseException:
            self.close_writers()
            _close_fd(self._stdout_read_fd)
            _close_fd(self._stderr_read_fd)
            raise
        return self

    def close_writers(self) -> None:
        _close_fd(self.stdout_write_fd)
        _close_fd(self.stderr_write_fd)
        self.stdout_write_fd = -1
        self.stderr_write_fd = -1

    def _drain(self) -> None:
        active = {
            self._stdout_read_fd: True,
            self._stderr_read_fd: False,
        }
        try:
            while active:
                try:
                    readable, _, _ = select.select(
                        list(active),
                        [],
                        [],
                        CAPTURE_POLL_SECONDS,
                    )
                except (OSError, ValueError):
                    break
                stopping = self._stop.is_set()
                if not readable:
                    # Cleanup requests the stop only after all contained writers have been drained.
                    # This also prevents an admitted residual which closes the sentinel descriptor
                    # but keeps an output pipe open from hanging the adapter indefinitely.
                    if stopping:
                        break
                    continue
                for descriptor in readable:
                    while True:
                        try:
                            chunk = os.read(descriptor, CAPTURE_READ_BYTES)
                        except BlockingIOError:
                            break
                        except OSError:
                            chunk = b""
                        if not chunk:
                            _close_fd(descriptor)
                            active.pop(descriptor, None)
                            break
                        if active.get(descriptor):
                            remaining = MAX_CAPTURE_BYTES - len(self._captured_stdout)
                            if remaining > 0:
                                self._captured_stdout.extend(chunk[:remaining])
                        if stopping:
                            break
                if stopping:
                    break
        finally:
            for descriptor in active:
                _close_fd(descriptor)

    def finish(self) -> None:
        if self._finished:
            return
        self.close_writers()
        self._stop.set()
        if self._started:
            self._thread.join()
        self._finished = True

    @property
    def stdout(self) -> bytes:
        if not self._finished:
            raise RuntimeError("output capture is still active")
        return bytes(self._captured_stdout)

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.finish()


@contextmanager
def _bound_model_scratch() -> Any:
    """Create scratch and bind both it and its parent for parent-death cleanup."""

    with tempfile.TemporaryDirectory(prefix="harness-model-scratch-") as scratch:
        scratch_path = Path(scratch).resolve()
        directory_flags = (
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        scratch_fd: int | None = None
        parent_fd: int | None = None
        try:
            parent_fd = os.open(scratch_path.parent, directory_flags)
            scratch_fd = os.open(scratch_path.name, directory_flags, dir_fd=parent_fd)
            scratch_stat = os.fstat(scratch_fd)
        except OSError as exc:
            _close_fd(scratch_fd)
            _close_fd(parent_fd)
            raise SessionLaunchError("Claude scratch directory could not be bound") from exc
        try:
            yield scratch_path, scratch_fd, parent_fd, scratch_stat.st_dev, scratch_stat.st_ino
        finally:
            _close_fd(scratch_fd)
            _close_fd(parent_fd)


def _summary_from_output(raw: bytes) -> tuple[bool, bool | None, float | None]:
    try:
        value = json.loads(_bounded_capture(raw))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return False, None, None
    if not isinstance(value, dict):
        return True, None, None
    reported_error = value.get("is_error") if type(value.get("is_error")) is bool else None
    raw_cost = value.get("total_cost_usd")
    cost = (
        float(raw_cost)
        if isinstance(raw_cost, (int, float))
        and not isinstance(raw_cost, bool)
        and math.isfinite(float(raw_cost))
        and raw_cost >= 0
        else None
    )
    return True, reported_error, cost


def _process_group_exists(process_group: int) -> bool:
    try:
        os.killpg(process_group, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _wait_for_process_group_exit(
    process_group: int,
    timeout: float,
    process: subprocess.Popen[bytes] | None = None,
) -> bool:
    deadline = time.monotonic() + timeout
    while _process_group_exists(process_group):
        if process is not None:
            process.poll()
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.01)
    return True


def _terminate_process_group(process: subprocess.Popen[bytes]) -> None:
    """Terminate and prove absence of every process left in the launched session group."""

    process_group = process.pid
    try:
        os.killpg(process_group, signal.SIGTERM)
    except ProcessLookupError:
        pass

    # poll/wait reaps the leader while group-existence checks cover any descendants which outlive
    # it.  A normal leader exit therefore does not let a background child escape the adapter.
    process.poll()
    if not _wait_for_process_group_exit(process_group, 2.0, process):
        try:
            os.killpg(process_group, signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=2.0)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process_group, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=2.0)
    if not _wait_for_process_group_exit(process_group, 2.0):
        raise SessionLaunchError("Claude process group could not be drained")


def _close_fd(file_descriptor: int | None) -> None:
    if file_descriptor is None:
        return
    try:
        os.close(file_descriptor)
    except OSError:
        pass


def _await_watchdog_ready(
    watchdog: subprocess.Popen[bytes],
    ready_read_fd: int,
) -> None:
    deadline = time.monotonic() + WATCHDOG_READY_TIMEOUT_SECONDS
    while True:
        if watchdog.poll() is not None:
            raise SessionLaunchError("Claude session watchdog failed before readiness")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise SessionLaunchError("Claude session watchdog did not become ready")
        readable, _, _ = select.select([ready_read_fd], [], [], min(remaining, 0.05))
        if not readable:
            continue
        try:
            ready = os.read(ready_read_fd, 1)
        except OSError as exc:
            raise SessionLaunchError("Claude session watchdog readiness failed") from exc
        if ready != b"1":
            raise SessionLaunchError("Claude session watchdog failed before readiness")
        return


def _wait_for_session_or_timeout(
    process: subprocess.Popen[bytes],
    watchdog: subprocess.Popen[bytes],
    timeout_seconds: float,
) -> bool:
    """Return true on timeout and fail closed if the armed watchdog exits early."""

    deadline = time.monotonic() + timeout_seconds
    while process.poll() is None:
        if watchdog.poll() is not None:
            raise SessionLaunchError("Claude session watchdog exited while the session was active")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return True
        time.sleep(min(remaining, 0.01))
    return False


def _reap_watchdog(
    watchdog: subprocess.Popen[bytes],
    lifetime_write_fd: int | None,
) -> int:
    """Close the parent lifetime signal and prove that its helper was reaped."""

    _close_fd(lifetime_write_fd)
    try:
        returncode = watchdog.wait(timeout=WATCHDOG_EXIT_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired as exc:
        try:
            os.killpg(watchdog.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        watchdog.wait(timeout=2.0)
        raise SessionLaunchError("Claude session watchdog could not be reaped") from exc
    return returncode


def _cleanup_session(
    process: subprocess.Popen[bytes],
    watchdog: subprocess.Popen[bytes] | None,
    lifetime_write_fd: int | None,
    containment_path: Path,
    *,
    require_watchdog_success: bool,
) -> None:
    """Drain the target group first, then release and reap the independent watchdog."""

    target_error: BaseException | None = None
    try:
        _terminate_process_group(process)
    except BaseException as exc:
        target_error = exc
    try:
        descendants_drained = drain_holders(containment_path, exclude={os.getpid()})
    except (OSError, ContainmentUnavailable) as exc:
        if target_error is None:
            target_error = SessionLaunchError(
                "Darwin sentinel descendant containment became unavailable",
                code="descendant_containment_unavailable",
            )
            target_error.__cause__ = exc
    else:
        if not descendants_drained and target_error is None:
            target_error = SessionLaunchError(
                "Claude sentinel-retaining descendants could not be drained",
                code="descendant_containment_failed",
            )
    watchdog_error: BaseException | None = None
    watchdog_returncode: int | None = None
    if watchdog is None:
        _close_fd(lifetime_write_fd)
    else:
        try:
            watchdog_returncode = _reap_watchdog(watchdog, lifetime_write_fd)
        except BaseException as exc:
            watchdog_error = exc
    if target_error is not None:
        raise target_error
    if watchdog_error is not None:
        raise watchdog_error
    if require_watchdog_success and watchdog_returncode not in (None, 0):
        if watchdog_returncode == 68:
            raise SessionLaunchError(
                "Darwin sentinel descendant containment became unavailable",
                code="descendant_containment_unavailable",
            )
        if watchdog_returncode == 69:
            raise SessionLaunchError(
                "Claude sentinel-retaining descendants could not be drained",
                code="descendant_containment_failed",
            )
        if watchdog_returncode == 70:
            raise SessionLaunchError(
                "Claude model scratch directory could not be cleaned",
                code="scratch_cleanup_failed",
            )
        raise SessionLaunchError("Claude session watchdog failed during cleanup")


def run_claude_session(
    *,
    executable: Path,
    model: str,
    prompt: str,
    session_ref: str,
    workspace_fd: int,
    engagement: Path,
    settings: dict[str, Any],
    driver_scope: dict[str, str],
    timeout_seconds: float,
    max_budget_usd: float | None,
    on_process_started: Callable[[int], None] | None = None,
) -> SessionResult:
    """Run one Claude process in the inode-bound target workspace.

    Raw stdout/stderr and prompt text never appear in the returned value.  The workspace descriptor
    remains open through ``exec`` so ``/dev/fd/<n>`` is an inode-bound cwd rather than a second lookup
    of the operator-supplied path. The wall timeout drains the original process group and discovered
    sentinel-retaining descendants. It is not containment for a deliberate FD-closing daemon.
    """

    if timeout_seconds <= 0:
        raise SessionLaunchError("session timeout must be positive")
    if not model.strip():
        raise SessionLaunchError("model must be nonblank")
    try:
        parsed_session_ref = uuid.UUID(session_ref)
    except (AttributeError, TypeError, ValueError) as exc:
        raise SessionLaunchError("session ref must be a canonical UUID") from exc
    if str(parsed_session_ref) != session_ref:
        raise SessionLaunchError("session ref must be a canonical UUID")
    if on_process_started is not None and not callable(on_process_started):
        raise SessionLaunchError("process-start callback must be callable")
    try:
        executable = executable.resolve(strict=True)
    except OSError as exc:
        raise SessionLaunchError("Claude executable is unavailable or unsafe") from exc
    if not executable.is_file() or not os.access(executable, os.X_OK):
        raise SessionLaunchError("Claude executable is unavailable or unsafe")

    command = [
        str(executable),
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
        if max_budget_usd <= 0:
            raise SessionLaunchError("session budget must be positive")
        command.extend(["--max-budget-usd", str(max_budget_usd)])
    command.append(prompt)

    # The target session gets runtime necessities and explicitly scoped model authentication only.
    # GitHub/cloud/SSH credentials from the operator shell are unrelated ambient authority and must
    # never become prompt-reachable merely because the driver was launched from that shell.
    child_env = {
        key: value
        for key, value in os.environ.items()
        if key in RUNTIME_ENV_KEYS or key in MODEL_AUTH_ENV_KEYS
    }
    child_env["HARNESS_ACTIVE_ENGAGEMENT"] = str(engagement)
    required_driver_scope = set(DRIVER_SCOPE_ENV_KEYS)
    if set(driver_scope) != required_driver_scope or any(
        not isinstance(value, str) or not value for value in driver_scope.values()
    ):
        raise SessionLaunchError("driver scope is malformed")
    child_env.update(driver_scope)
    child_env.pop("PWD", None)

    if sys.platform != "darwin" or not Path("/usr/bin/sandbox-exec").is_file():
        raise SessionLaunchError("target-write sandbox is unavailable")

    launcher = Path(__file__).with_name("_fd_exec.py").absolute()
    watchdog_launcher = Path(__file__).with_name("_session_watchdog.py").absolute()
    python = Path(os.path.abspath(sys.executable))
    with (
        _containment_sentinel() as (containment_fd, containment_path),
        _bound_model_scratch()
        as (scratch_path, scratch_fd, scratch_parent_fd, scratch_device, scratch_inode),
        _BoundedOutputCapture() as output_capture,
    ):
        child_env["HARNESS_DRIVER_SCRATCH"] = str(scratch_path)
        child_env["HOME"] = str(scratch_path)
        child_env["TMPDIR"] = str(scratch_path)
        child_env["TMP"] = str(scratch_path)
        child_env["TEMP"] = str(scratch_path)
        child_env["PYTHONDONTWRITEBYTECODE"] = "1"
        quoted_scratch = json.dumps(str(scratch_path))
        sandbox_profile = "\n".join(
            (
                "(version 1)",
                "(allow default)",
                "(deny file-write*)",
                "(deny signal)",
                f"(allow file-write* (literal {quoted_scratch}))",
                f"(allow file-write* (subpath {quoted_scratch}))",
                f"(deny file-write-flags (literal {quoted_scratch}))",
                f"(deny file-write-flags (subpath {quoted_scratch}))",
                f"(deny file-write-acl (literal {quoted_scratch}))",
                f"(deny file-write-acl (subpath {quoted_scratch}))",
                '(allow file-write* (literal "/dev/null"))',
                "(allow signal (target self))",
                "(allow signal (target same-sandbox))",
            )
        )
        gate_read_fd, gate_write_fd = os.pipe()
        lifetime_read_fd, lifetime_write_fd = os.pipe()
        ready_read_fd, ready_write_fd = os.pipe()
        watchdog: subprocess.Popen[bytes] | None = None
        try:
            process = subprocess.Popen(
                [
                    "/usr/bin/sandbox-exec",
                    "-p",
                    sandbox_profile,
                    str(python),
                    str(launcher),
                    str(workspace_fd),
                    str(gate_read_fd),
                    str(containment_fd),
                    str(max(1, math.ceil(timeout_seconds) + 5)),
                    *command,
                ],
                env=child_env,
                stdin=subprocess.DEVNULL,
                stdout=output_capture.stdout_write_fd,
                stderr=output_capture.stderr_write_fd,
                pass_fds=(workspace_fd, gate_read_fd, containment_fd),
                start_new_session=True,
            )
        except OSError as exc:
            _close_fd(gate_read_fd)
            _close_fd(gate_write_fd)
            _close_fd(lifetime_read_fd)
            _close_fd(lifetime_write_fd)
            _close_fd(ready_read_fd)
            _close_fd(ready_write_fd)
            raise SessionLaunchError("Claude session could not start") from exc
        finally:
            output_capture.close_writers()
        _close_fd(gate_read_fd)
        gate_read_fd = None

        try:
            os_session_id = os.getsid(process.pid)
            try:
                watchdog = subprocess.Popen(
                    [
                        str(python),
                        str(watchdog_launcher),
                        str(lifetime_read_fd),
                        str(ready_write_fd),
                        str(os_session_id),
                        str(os.getpid()),
                        str(containment_path),
                        str(scratch_fd),
                        str(scratch_parent_fd),
                        str(scratch_device),
                        str(scratch_inode),
                        scratch_path.name,
                    ],
                    env=child_env,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    pass_fds=(
                        lifetime_read_fd,
                        ready_write_fd,
                        scratch_fd,
                        scratch_parent_fd,
                    ),
                    start_new_session=True,
                )
            except OSError as exc:
                raise SessionLaunchError("Claude session watchdog could not start") from exc
            _close_fd(lifetime_read_fd)
            lifetime_read_fd = None
            _close_fd(ready_write_fd)
            ready_write_fd = None
            _await_watchdog_ready(watchdog, ready_read_fd)
            _close_fd(ready_read_fd)
            ready_read_fd = None
            if on_process_started is not None:
                on_process_started(os_session_id)
            if os.write(gate_write_fd, b"1") != 1:
                raise OSError("short process-start gate write")
        except Exception as exc:
            _close_fd(gate_write_fd)
            gate_write_fd = None
            _close_fd(lifetime_read_fd)
            _close_fd(ready_read_fd)
            _close_fd(ready_write_fd)
            try:
                _cleanup_session(
                    process,
                    watchdog,
                    lifetime_write_fd,
                    containment_path,
                    require_watchdog_success=False,
                )
            except BaseException as cleanup_exc:
                if isinstance(cleanup_exc, SessionLaunchError):
                    raise cleanup_exc
                raise SessionLaunchError("Claude session cleanup failed") from cleanup_exc
            if isinstance(exc, SessionLaunchError):
                raise
            raise SessionLaunchError("Claude process-start callback failed") from exc
        except BaseException:
            _close_fd(gate_write_fd)
            gate_write_fd = None
            _close_fd(lifetime_read_fd)
            _close_fd(ready_read_fd)
            _close_fd(ready_write_fd)
            _cleanup_session(
                process,
                watchdog,
                lifetime_write_fd,
                containment_path,
                require_watchdog_success=False,
            )
            raise
        else:
            _close_fd(gate_write_fd)
            gate_write_fd = None

        try:
            timed_out = _wait_for_session_or_timeout(process, watchdog, timeout_seconds)
        except BaseException:
            _cleanup_session(
                process,
                watchdog,
                lifetime_write_fd,
                containment_path,
                require_watchdog_success=False,
            )
            raise
        else:
            _cleanup_session(
                process,
                watchdog,
                lifetime_write_fd,
                containment_path,
                require_watchdog_success=True,
            )
        finally:
            _close_fd(lifetime_read_fd)
            _close_fd(ready_read_fd)
            _close_fd(ready_write_fd)
        if timed_out:
            return SessionResult(session_ref, True, True, process.returncode, False, None, None)
    stdout = output_capture.stdout

    output_was_json, reported_error, cost = _summary_from_output(stdout)
    return SessionResult(
        session_ref,
        True,
        False,
        process.returncode,
        output_was_json,
        reported_error,
        cost,
    )
