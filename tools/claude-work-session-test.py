#!/usr/bin/env python3
"""Direct subprocess contract tests for one bounded Claude work session."""

from __future__ import annotations

import json
import os
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from typing import Callable
from unittest import mock

import claude_work_session as session_module
import _session_watchdog as watchdog_module
from claude_work_session import SessionLaunchError, run_claude_session as _run_claude_session


# The production Claude runtime is a self-contained Mach-O binary. This fixture is intentionally a
# Python script, so its import trees are additional declared inputs rather than ambient runtime
# authority granted by the launcher.
_FIXTURE_RUNTIME_READ_INPUTS = tuple(
    dict.fromkeys((Path(sys.prefix), Path(sys.base_prefix)))
)


def run_claude_session(**kwargs: object):
    declared = tuple(kwargs.pop("read_only_inputs", ()))
    kwargs["read_only_inputs"] = tuple(
        dict.fromkeys((*declared, *_FIXTURE_RUNTIME_READ_INPUTS))
    )
    return _run_claude_session(**kwargs)


FAKE_RUNTIME = """import json
import os
import pathlib
import signal
import socket
import stat
import subprocess
import sys
import time

try:
    fixture = json.loads(sys.argv[-1])
except (IndexError, json.JSONDecodeError):
    fixture = {}
if not isinstance(fixture, dict):
    fixture = {}
capture = {
    "argv": sys.argv[1:],
    "os_session_id": os.getsid(0),
    "active_engagement": os.environ.get("HARNESS_ACTIVE_ENGAGEMENT"),
    "operator_signature_present": "HARNESS_OPERATOR_SIGNATURE_FILE" in os.environ,
    "operator_signers_present": "HARNESS_OPERATOR_ALLOWED_SIGNERS_FILE" in os.environ,
    "driver_scope": {
        key: value
        for key, value in os.environ.items()
        if key.startswith("HARNESS_DRIVER_") or key.startswith("HARNESS_EXPECTED_")
    },
}
read_probes = fixture.get("fixture_read_probes")
if isinstance(read_probes, dict):
    read_results = {}
    for label, raw_path in read_probes.items():
        try:
            pathlib.Path(raw_path).read_bytes()
        except OSError:
            read_results[str(label)] = False
        else:
            read_results[str(label)] = True
    scratch_probe = pathlib.Path(os.environ["HARNESS_DRIVER_SCRATCH"]) / "read-probe"
    scratch_probe.write_text("scratch-readable", encoding="utf-8")
    read_results["scratch"] = scratch_probe.read_text(encoding="utf-8") == "scratch-readable"
    descendant_path = fixture.get("fixture_descendant_read_probe")
    if descendant_path:
        descendant = subprocess.run(
            [
                sys.executable,
                "-c",
                "import pathlib,sys; pathlib.Path(sys.argv[1]).read_bytes()",
                str(descendant_path),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        read_results["descendant_outside"] = descendant.returncode == 0
    capture["read_results"] = read_results
signal_targets = fixture.get("fixture_signal_targets")
signal_targets_file = fixture.get("fixture_signal_targets_file")
if signal_targets_file:
    signal_targets = json.loads(
        pathlib.Path(signal_targets_file).read_text(encoding="utf-8")
    )
if isinstance(signal_targets, dict):
    signal_results = {}
    self_hits = []
    signal.signal(signal.SIGUSR1, lambda *_: self_hits.append(True))
    os.kill(os.getpid(), signal.SIGUSR1)
    signal_results["self"] = "delivered" if self_hits else "missing"
    signal_child = subprocess.Popen(["/bin/sleep", "30"])
    try:
        os.kill(signal_child.pid, signal.SIGTERM)
        signal_child.wait(timeout=2)
        signal_results["same_sandbox_child"] = signal_child.returncode
    finally:
        if signal_child.poll() is None:
            signal_child.kill()
            signal_child.wait()
    signal_group_child = subprocess.Popen(["/bin/sleep", "30"], start_new_session=True)
    try:
        os.killpg(signal_group_child.pid, signal.SIGTERM)
        signal_group_child.wait(timeout=2)
        signal_results["same_sandbox_group"] = signal_group_child.returncode
    finally:
        if signal_group_child.poll() is None:
            signal_group_child.kill()
            signal_group_child.wait()

    def attempt_signal(process_id):
        try:
            os.kill(int(process_id), signal.SIGUSR1)
        except PermissionError:
            return "denied"
        except ProcessLookupError:
            return "missing"
        return "delivered"

    for label, process_id in signal_targets.items():
        signal_results[str(label)] = attempt_signal(process_id)
    capture["signal_results"] = signal_results
if fixture.get("fixture_scratch_marker"):
    scratch_path = pathlib.Path(os.environ["HARNESS_DRIVER_SCRATCH"])
    nested = scratch_path / "nested"
    nested.mkdir()
    (nested / "marker").write_text("fixture", encoding="utf-8")
    symlink_target = fixture.get("fixture_scratch_symlink_target")
    if symlink_target:
        (scratch_path / "outside-link").symlink_to(str(symlink_target))
    capture["scratch_path"] = str(scratch_path)
if fixture.get("fixture_scratch_metadata_probes"):
    scratch_path = pathlib.Path(os.environ["HARNESS_DRIVER_SCRATCH"])
    metadata_dir = scratch_path / "metadata-probe"
    metadata_dir.mkdir()
    ordinary = metadata_dir / "ordinary"
    ordinary.write_text("fixture", encoding="utf-8")
    hardlink = metadata_dir / "hardlink"
    os.link(ordinary, hardlink)
    try:
        os.chflags(ordinary, stat.UF_IMMUTABLE)
    except PermissionError:
        flags_result = "denied"
    except OSError as exc:
        flags_result = f"error:{exc.errno}"
    else:
        flags_result = "allowed"
        os.chflags(ordinary, 0)
    acl_dir = metadata_dir / "acl"
    acl_dir.mkdir()
    acl = subprocess.run(
        ["/bin/chmod", "+a", "everyone deny delete_child", str(acl_dir)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if acl.returncode == 0:
        subprocess.run(
            ["/bin/chmod", "-N", str(acl_dir)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    capture["scratch_metadata"] = {
        "ordinary_created": ordinary.is_file(),
        "hardlink_count": ordinary.stat().st_nlink,
        "flags_result": flags_result,
        "acl_returncode": acl.returncode,
        "scratch_path": str(scratch_path),
    }
background_mode = fixture.get("fixture_background")
if background_mode:
    child = subprocess.Popen([
        sys.executable,
        "-c",
        "import time; time.sleep(30)",
    ])
    capture["background_pid"] = child.pid
if fixture.get("fixture_detached"):
    read_fd, write_fd = os.pipe()
    first = os.fork()
    if first == 0:
        os.close(read_fd)
        os.setsid()
        detached = os.fork()
        if detached == 0:
            os.close(write_fd)
            time.sleep(30)
            os._exit(0)
        os.write(write_fd, str(detached).encode("ascii"))
        os.close(write_fd)
        os._exit(0)
    os.close(write_fd)
    detached_pid = int(os.read(read_fd, 64))
    os.close(read_fd)
    os.waitpid(first, 0)
    capture["detached_pid"] = detached_pid
if fixture.get("fixture_notify_socket"):
    connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    connection.connect(fixture["fixture_notify_socket"])
    connection.sendall(json.dumps(capture).encode("utf-8"))
    connection.close()
if background_mode:
    if background_mode == "abnormal":
        os.kill(os.getpid(), signal.SIGKILL)
if fixture.get("fixture_sleep"):
    time.sleep(float(fixture["fixture_sleep"]))
for descriptor, key, byte in (
    (1, "fixture_stdout_bytes", b"x"),
    (2, "fixture_stderr_bytes", b"e"),
):
    remaining = int(fixture.get(key, 0))
    while remaining > 0:
        chunk = byte * min(remaining, 65536)
        os.write(descriptor, chunk)
        remaining -= len(chunk)
print(json.dumps({"type": "result", "is_error": False, "total_cost_usd": 0.125, "result": "not retained", "fixture_capture": capture}))
"""


class ClaudeWorkSessionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="cws-", dir="/tmp")
        self.root = Path(self.temporary.name).resolve()
        self.workspace = self.root / "target"
        self.engagement = self.workspace / "engagements" / "fixture"
        self.engagement.mkdir(parents=True)
        self.executable = self.root / "fixture-claude"
        self.executable.write_text(
            f"#!{Path(sys.executable).resolve()}\n{FAKE_RUNTIME}",
            encoding="utf-8",
        )
        self.executable.chmod(self.executable.stat().st_mode | stat.S_IXUSR)
        self.workspace_fd = os.open(
            self.workspace,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
        )

    def tearDown(self) -> None:
        os.close(self.workspace_fd)
        self.temporary.cleanup()

    @staticmethod
    def _driver_scope(session_ref: str) -> dict[str, str]:
        return {
            "HARNESS_EXPECTED_LEDGER_HASH": "sha256:" + "1" * 64,
            "HARNESS_EXPECTED_SOURCE_HASHES": json.dumps(
                {
                    "artifacts.jsonl": "sha256:" + "2" * 64,
                    "attempts.jsonl": "sha256:" + "3" * 64,
                    "events.jsonl": "sha256:" + "4" * 64,
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
            "HARNESS_EXPECTED_RUNTIME_SESSION_REF": session_ref,
            "HARNESS_DRIVER_ACTION_BROKER": str(Path(tempfile.gettempdir()) / "fixture-broker.sock"),
        }

    @staticmethod
    def _wait_until(predicate: Callable[[], bool], timeout: float = 5.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return True
            time.sleep(0.02)
        return predicate()

    @staticmethod
    def _pid_exists(process_id: int) -> bool:
        try:
            os.kill(process_id, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    @staticmethod
    def _watchdog_pids(process_group: int) -> list[int]:
        listing = subprocess.run(
            ["ps", "-axo", "pid=,command="],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        matches: list[int] = []
        for raw_line in listing.splitlines():
            columns = raw_line.strip().split(None, 1)
            if len(columns) != 2:
                continue
            process_id, command = columns
            if "_session_watchdog.py" in command and str(process_group) in command.split():
                matches.append(int(process_id))
        return matches

    def test_exact_safe_cli_and_content_free_result(self) -> None:
        settings = {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "/safe/hook"}]}]}}
        with mock.patch.dict(
            os.environ,
            {
                "HARNESS_OPERATOR_SIGNATURE_FILE": "/private/operator.sig",
                "HARNESS_OPERATOR_ALLOWED_SIGNERS_FILE": "/private/allowed-signers",
                "HARNESS_DRIVER_PRIVATE": "must-not-cross",
            },
        ):
            session_ref = "11111111-1111-4111-8111-111111111111"
            driver_scope = self._driver_scope(session_ref)
            emitted: list[dict[str, object]] = []
            original_summary = session_module._summary_from_output

            def capture_summary(raw: bytes) -> tuple[bool, bool | None, float | None]:
                emitted.append(json.loads(raw))
                return original_summary(raw)

            with mock.patch.object(session_module, "_summary_from_output", side_effect=capture_summary):
                result = run_claude_session(
                    executable=self.executable,
                    model="fixture-model",
                    prompt=json.dumps({"queue_item": "fixture"}),
                    session_ref=session_ref,
                    workspace=self.workspace,
                    workspace_fd=self.workspace_fd,
                    engagement=self.engagement,
                    settings=settings,
                    driver_scope=driver_scope,
                    timeout_seconds=5,
                    max_budget_usd=1.5,
                )

        capture = emitted[0]["fixture_capture"]
        argv = capture["argv"]
        self.assertEqual(result.returncode, 0)
        self.assertFalse(result.timed_out)
        self.assertTrue(result.output_was_json)
        self.assertIs(result.runtime_reported_error, False)
        self.assertEqual(result.cost_usd, 0.125)

        self.assertNotIn("result", result.as_dict())
        self.assertEqual(argv.count("-p"), 1)
        self.assertEqual(argv[argv.index("--session-id") + 1], "11111111-1111-4111-8111-111111111111")
        self.assertIn("--no-session-persistence", argv)
        self.assertEqual(argv[argv.index("--output-format") + 1], "json")
        self.assertEqual(argv[argv.index("--permission-mode") + 1], "dontAsk")
        self.assertEqual(argv[argv.index("--model") + 1], "fixture-model")
        self.assertEqual(argv[argv.index("--max-budget-usd") + 1], "1.5")
        self.assertEqual(json.loads(argv[argv.index("--settings") + 1]), settings)
        self.assertNotIn("--add-dir", argv)
        self.assertNotIn("--dangerously-skip-permissions", argv)
        self.assertNotIn("--allow-dangerously-skip-permissions", argv)
        self.assertEqual(capture["active_engagement"], str(self.engagement))
        self.assertFalse(capture["operator_signature_present"])
        self.assertFalse(capture["operator_signers_present"])
        captured_scope = dict(capture["driver_scope"])
        scratch = captured_scope.pop("HARNESS_DRIVER_SCRATCH")
        self.assertEqual(captured_scope, driver_scope)
        self.assertFalse(Path(scratch).exists(), "model scratch must be removed after the session")
        self.assertEqual(self._watchdog_pids(capture["os_session_id"]), [])

    def test_bound_scratch_cleanup_handles_immutable_leaf_and_deep_tree(self) -> None:
        scratch_path = self.root / "direct-watchdog-scratch"
        scratch_path.mkdir(mode=0o700)
        immutable = scratch_path / "immutable-marker"
        immutable.write_text("fixture", encoding="utf-8")
        if hasattr(os, "chflags") and hasattr(stat, "UF_IMMUTABLE"):
            os.chflags(immutable, stat.UF_IMMUTABLE)
        parent_fd = os.open(
            self.root,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
        scratch_fd = os.open(
            scratch_path.name,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=parent_fd,
        )
        scratch_identity = os.fstat(scratch_fd)
        current_fd = os.dup(scratch_fd)
        try:
            for _ in range(1_100):
                os.mkdir("d", mode=0o700, dir_fd=current_fd)
                child_fd = os.open(
                    "d",
                    os.O_RDONLY
                    | getattr(os, "O_DIRECTORY", 0)
                    | getattr(os, "O_NOFOLLOW", 0),
                    dir_fd=current_fd,
                )
                os.close(current_fd)
                current_fd = child_fd
            marker_fd = os.open(
                "marker",
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
                dir_fd=current_fd,
            )
            os.close(marker_fd)
            self.assertTrue(
                watchdog_module._remove_bound_scratch(
                    scratch_fd,
                    parent_fd,
                    scratch_path.name,
                    device=scratch_identity.st_dev,
                    inode=scratch_identity.st_ino,
                )
            )
            self.assertFalse(scratch_path.exists())
        finally:
            os.close(current_fd)
            os.close(scratch_fd)
            os.close(parent_fd)
            if immutable.exists() and hasattr(os, "chflags"):
                os.chflags(immutable, 0)

    def test_cleanup_failure_marker_is_prearmed_and_cleared(self) -> None:
        parent_fd = os.open(
            self.root,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
        marker_name = ""
        try:
            marker_name = watchdog_module._arm_cleanup_failure_marker(
                parent_fd,
                "marker-fixture",
            )
            marker_path = self.root / marker_name
            self.assertEqual(
                marker_path.read_bytes(),
                b"scratch_cleanup_armed\n",
            )
            watchdog_module._clear_cleanup_failure_marker(parent_fd, marker_name)
            self.assertFalse(marker_path.exists())
        finally:
            os.close(parent_fd)
            if marker_name:
                (self.root / marker_name).unlink(missing_ok=True)

    def test_readiness_reader_loss_still_drains_and_cleans(self) -> None:
        sentinel_fd, sentinel_path = session_module.create_sentinel()
        scratch_path = self.root / "pre-readiness-scratch"
        scratch_path.mkdir(mode=0o700)
        parent_fd = os.open(
            self.root,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
        scratch_fd = os.open(
            scratch_path.name,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=parent_fd,
        )
        scratch_identity = os.fstat(scratch_fd)
        lifetime_read_fd, lifetime_write_fd = os.pipe()
        ready_read_fd, ready_write_fd = os.pipe()
        target = subprocess.Popen(
            ["/bin/sleep", "30"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            pass_fds=(sentinel_fd,),
            start_new_session=True,
        )
        watchdog: subprocess.Popen[bytes] | None = None
        marker_path = scratch_path.parent / (
            f".{scratch_path.name}{watchdog_module.SCRATCH_FAILURE_SUFFIX}"
        )
        try:
            os.close(lifetime_write_fd)
            lifetime_write_fd = -1
            os.close(ready_read_fd)
            ready_read_fd = -1
            watchdog = subprocess.Popen(
                [
                    sys.executable,
                    str(Path(watchdog_module.__file__).resolve()),
                    str(lifetime_read_fd),
                    str(ready_write_fd),
                    str(os.getsid(target.pid)),
                    str(os.getpid()),
                    str(sentinel_path),
                    str(scratch_fd),
                    str(parent_fd),
                    str(scratch_identity.st_dev),
                    str(scratch_identity.st_ino),
                    scratch_path.name,
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                pass_fds=(
                    lifetime_read_fd,
                    ready_write_fd,
                    scratch_fd,
                    parent_fd,
                ),
                start_new_session=True,
            )
            os.close(lifetime_read_fd)
            lifetime_read_fd = -1
            os.close(ready_write_fd)
            ready_write_fd = -1
            os.close(scratch_fd)
            scratch_fd = -1
            os.close(parent_fd)
            parent_fd = -1

            watchdog_returncode = watchdog.wait(timeout=10)
            watchdog_stderr = (
                watchdog.stderr.read().decode("utf-8", errors="replace")
                if watchdog.stderr is not None
                else ""
            )
            if watchdog.stderr is not None:
                watchdog.stderr.close()
            self.assertEqual(watchdog_returncode, 66, watchdog_stderr)
            target.wait(timeout=5)
            self.assertFalse(self._pid_exists(target.pid))
            self.assertFalse(scratch_path.exists())
            self.assertFalse(marker_path.exists())
            self.assertFalse(sentinel_path.exists())
        finally:
            for descriptor in (
                lifetime_read_fd,
                lifetime_write_fd,
                ready_read_fd,
                ready_write_fd,
                scratch_fd,
                parent_fd,
                sentinel_fd,
            ):
                if descriptor >= 0:
                    try:
                        os.close(descriptor)
                    except OSError:
                        pass
            if watchdog is not None and watchdog.poll() is None:
                watchdog.kill()
                watchdog.wait(timeout=2)
            if target.poll() is None:
                try:
                    os.killpg(target.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                target.wait(timeout=2)
            sentinel_path.unlink(missing_ok=True)
            marker_path.unlink(missing_ok=True)

    def test_scratch_denies_flags_and_acl_but_allows_ordinary_files(self) -> None:
        session_ref = "19191919-1919-4919-8919-191919191919"
        emitted: list[dict[str, object]] = []
        original_summary = session_module._summary_from_output

        def capture_summary(raw: bytes) -> tuple[bool, bool | None, float | None]:
            emitted.append(json.loads(raw))
            return original_summary(raw)

        with mock.patch.object(
            session_module,
            "_summary_from_output",
            side_effect=capture_summary,
        ):
            result = run_claude_session(
                executable=self.executable,
                model="fixture-model",
                prompt=json.dumps({"fixture_scratch_metadata_probes": True}),
                session_ref=session_ref,
                workspace=self.workspace,
                workspace_fd=self.workspace_fd,
                engagement=self.engagement,
                settings={},
                driver_scope=self._driver_scope(session_ref),
                timeout_seconds=5,
                max_budget_usd=None,
            )

        metadata = emitted[0]["fixture_capture"]["scratch_metadata"]
        self.assertEqual(result.returncode, 0)
        self.assertTrue(metadata["ordinary_created"])
        self.assertEqual(metadata["hardlink_count"], 2)
        self.assertEqual(metadata["flags_result"], "denied")
        self.assertNotEqual(metadata["acl_returncode"], 0)
        self.assertFalse(Path(metadata["scratch_path"]).exists())

    def test_launched_session_reads_only_approved_roots_and_descendants_inherit(self) -> None:
        workspace_marker = self.workspace / "workspace-readable"
        workspace_marker.write_text("workspace", encoding="utf-8")
        outside_marker = self.root / "outside-denied"
        outside_marker.write_text("outside", encoding="utf-8")
        workspace_escape = self.workspace / "outside-link"
        workspace_escape.symlink_to(outside_marker)
        explicit_file = self.root / "explicit-readable"
        explicit_file.write_text("explicit", encoding="utf-8")
        explicit_directory = self.root / "explicit-directory"
        explicit_directory.mkdir()
        explicit_directory_marker = explicit_directory / "nested-readable"
        explicit_directory_marker.write_text("directory", encoding="utf-8")
        harness_marker = Path(__file__).resolve()
        session_ref = "20202020-2020-4020-8020-202020202020"
        emitted: list[dict[str, object]] = []
        original_summary = session_module._summary_from_output

        def capture_summary(raw: bytes) -> tuple[bool, bool | None, float | None]:
            emitted.append(json.loads(raw))
            return original_summary(raw)

        prompt = json.dumps(
            {
                "fixture_read_probes": {
                    "workspace": str(workspace_marker),
                    "workspace_symlink_escape": str(workspace_escape),
                    "harness": str(harness_marker),
                    "runtime": str(self.executable),
                    "explicit_file": str(explicit_file),
                    "explicit_directory": str(explicit_directory_marker),
                    "outside": str(outside_marker),
                },
                "fixture_descendant_read_probe": str(outside_marker),
            }
        )
        with mock.patch.object(
            session_module,
            "_summary_from_output",
            side_effect=capture_summary,
        ):
            result = run_claude_session(
                executable=self.executable,
                model="fixture-model",
                prompt=prompt,
                session_ref=session_ref,
                workspace=self.workspace,
                workspace_fd=self.workspace_fd,
                engagement=self.engagement,
                settings={},
                driver_scope=self._driver_scope(session_ref),
                timeout_seconds=5,
                max_budget_usd=None,
                read_only_inputs=(explicit_file, explicit_directory),
            )

        self.assertEqual(result.returncode, 0)
        self.assertTrue(result.output_was_json)
        self.assertEqual(
            emitted[0]["fixture_capture"]["read_results"],
            {
                "workspace": True,
                "workspace_symlink_escape": False,
                "harness": True,
                "runtime": True,
                "explicit_file": True,
                "explicit_directory": True,
                "outside": False,
                "scratch": True,
                "descendant_outside": False,
            },
        )

    def test_read_policy_failures_happen_before_process_activation(self) -> None:
        activated: list[int] = []
        session_ref = "21212121-2121-4121-8121-212121212121"
        with self.assertRaises(SessionLaunchError) as undeclared_runtime:
            _run_claude_session(
                executable=self.executable,
                model="fixture-model",
                prompt="{}",
                session_ref=session_ref,
                workspace=self.workspace,
                workspace_fd=self.workspace_fd,
                engagement=self.engagement,
                settings={},
                driver_scope=self._driver_scope(session_ref),
                timeout_seconds=5,
                max_budget_usd=None,
                on_process_started=activated.append,
            )
        self.assertEqual(undeclared_runtime.exception.code, "read_input_invalid")
        self.assertEqual(activated, [])

        missing = self.root / "missing-read-input"
        with self.assertRaises(SessionLaunchError) as missing_error:
            run_claude_session(
                executable=self.executable,
                model="fixture-model",
                prompt="{}",
                session_ref=session_ref,
                workspace=self.workspace,
                workspace_fd=self.workspace_fd,
                engagement=self.engagement,
                settings={},
                driver_scope=self._driver_scope(session_ref),
                timeout_seconds=5,
                max_budget_usd=None,
                read_only_inputs=(missing,),
                on_process_started=activated.append,
            )
        self.assertEqual(missing_error.exception.code, "read_input_invalid")
        self.assertEqual(activated, [])

        certificate = self.root / "operator-ca.pem"
        certificate.write_text("fixture certificate", encoding="utf-8")
        with mock.patch.dict(os.environ, {"SSL_CERT_FILE": str(certificate)}):
            with self.assertRaises(SessionLaunchError) as undeclared_error:
                run_claude_session(
                    executable=self.executable,
                    model="fixture-model",
                    prompt="{}",
                    session_ref=session_ref,
                    workspace=self.workspace,
                    workspace_fd=self.workspace_fd,
                    engagement=self.engagement,
                    settings={},
                    driver_scope=self._driver_scope(session_ref),
                    timeout_seconds=5,
                    max_budget_usd=None,
                    on_process_started=activated.append,
                )
        self.assertEqual(undeclared_error.exception.code, "read_input_invalid")
        self.assertEqual(activated, [])

    def test_workspace_name_must_still_select_the_bound_directory(self) -> None:
        alias = self.root / "target-alias"
        alias.symlink_to(self.workspace, target_is_directory=True)
        with self.assertRaises(SessionLaunchError) as raised:
            run_claude_session(
                executable=self.executable,
                model="fixture-model",
                prompt="{}",
                session_ref="23232323-2323-4323-8323-232323232323",
                workspace=alias,
                workspace_fd=self.workspace_fd,
                engagement=self.engagement,
                settings={},
                driver_scope=self._driver_scope("23232323-2323-4323-8323-232323232323"),
                timeout_seconds=5,
                max_budget_usd=None,
            )
        self.assertEqual(raised.exception.code, "target_identity_changed")

    def test_timeout_kills_the_bounded_process_group(self) -> None:
        session_ref = "22222222-2222-4222-8222-222222222222"
        started_session_ids: list[int] = []
        result = run_claude_session(
            executable=self.executable,
            model="fixture-model",
            prompt=json.dumps({"fixture_sleep": 30}),
            session_ref=session_ref,
            workspace=self.workspace,
            workspace_fd=self.workspace_fd,
            engagement=self.engagement,
            settings={},
            driver_scope=self._driver_scope(session_ref),
            timeout_seconds=0.1,
            max_budget_usd=None,
            on_process_started=started_session_ids.append,
        )
        self.assertTrue(result.started)
        self.assertTrue(result.timed_out)
        self.assertIsNotNone(result.returncode)
        self.assertFalse(result.output_was_json)
        self.assertEqual(len(started_session_ids), 1)
        self.assertEqual(self._watchdog_pids(started_session_ids[0]), [])

    def test_output_pipes_are_drained_while_only_a_bounded_prefix_is_retained(self) -> None:
        session_ref = "13131313-1313-4313-8313-131313131313"
        retained: list[bytes] = []
        original_summary = session_module._summary_from_output

        def capture_summary(raw: bytes) -> tuple[bool, bool | None, float | None]:
            retained.append(raw)
            return original_summary(raw)

        with (
            mock.patch.object(session_module, "MAX_CAPTURE_BYTES", 4096),
            mock.patch.object(
                session_module,
                "_summary_from_output",
                side_effect=capture_summary,
            ),
        ):
            result = run_claude_session(
                executable=self.executable,
                model="fixture-model",
                prompt=json.dumps(
                    {
                        "fixture_stdout_bytes": 2 * 1024 * 1024,
                        "fixture_stderr_bytes": 2 * 1024 * 1024,
                    }
                ),
                session_ref=session_ref,
                workspace=self.workspace,
                workspace_fd=self.workspace_fd,
                engagement=self.engagement,
                settings={},
                driver_scope=self._driver_scope(session_ref),
                timeout_seconds=5,
                max_budget_usd=None,
            )

        self.assertEqual(result.returncode, 0)
        self.assertFalse(result.timed_out)
        self.assertFalse(result.output_was_json)
        self.assertEqual(retained, [b"x" * 4096])

    def test_sandbox_signal_scope_excludes_driver_canary_and_watchdog(self) -> None:
        session_ref = "14141414-1414-4414-8414-141414141414"
        canary = subprocess.Popen(["/bin/sleep", "30"])
        driver_hits: list[int] = []
        previous_handler = signal.signal(
            signal.SIGUSR1,
            lambda signum, _frame: driver_hits.append(signum),
        )
        signal_targets_file = self.workspace / "signal-targets.json"
        observed_watchdogs: list[int] = []
        emitted: list[dict[str, object]] = []
        canary_returncode_before_cleanup: int | None = None
        original_summary = session_module._summary_from_output

        def capture_summary(raw: bytes) -> tuple[bool, bool | None, float | None]:
            emitted.append(json.loads(raw))
            return original_summary(raw)

        def bind_signal_targets(os_session_id: int) -> None:
            observed_watchdogs.extend(self._watchdog_pids(os_session_id))
            if not observed_watchdogs:
                raise RuntimeError("armed watchdog was not observable")
            signal_targets_file.write_text(
                json.dumps(
                    {
                        "driver": os.getpid(),
                        "canary": canary.pid,
                        **{
                            f"watchdog-{process_id}": process_id
                            for process_id in observed_watchdogs
                        },
                    }
                ),
                encoding="utf-8",
            )

        try:
            with mock.patch.object(
                session_module,
                "_summary_from_output",
                side_effect=capture_summary,
            ):
                result = run_claude_session(
                    executable=self.executable,
                    model="fixture-model",
                    prompt=json.dumps(
                        {
                            "fixture_signal_targets_file": str(signal_targets_file),
                        }
                    ),
                    session_ref=session_ref,
                    workspace=self.workspace,
                    workspace_fd=self.workspace_fd,
                    engagement=self.engagement,
                    settings={},
                    driver_scope=self._driver_scope(session_ref),
                    timeout_seconds=5,
                    max_budget_usd=None,
                    on_process_started=bind_signal_targets,
                )
            canary_returncode_before_cleanup = canary.poll()
        finally:
            signal.signal(signal.SIGUSR1, previous_handler)
            if canary.poll() is None:
                canary.terminate()
            canary.wait(timeout=2)

        self.assertEqual(result.returncode, 0)
        self.assertTrue(result.output_was_json)
        self.assertEqual(driver_hits, [])
        signal_results = emitted[0]["fixture_capture"]["signal_results"]
        self.assertEqual(signal_results["self"], "delivered")
        self.assertEqual(signal_results["same_sandbox_child"], -signal.SIGTERM)
        self.assertEqual(signal_results["same_sandbox_group"], -signal.SIGTERM)
        self.assertEqual(signal_results["driver"], "denied")
        self.assertEqual(signal_results["canary"], "denied")
        self.assertIsNone(canary_returncode_before_cleanup)
        self.assertTrue(observed_watchdogs)
        self.assertEqual(
            {signal_results[f"watchdog-{process_id}"] for process_id in observed_watchdogs},
            {"denied"},
        )

    def test_unavailable_sentinel_backend_has_a_distinct_fail_closed_error(self) -> None:
        session_ref = "12121212-1212-4212-8212-121212121212"
        with mock.patch.object(
            session_module,
            "create_sentinel",
            side_effect=session_module.ContainmentUnavailable("fixture unavailable"),
        ), self.assertRaises(SessionLaunchError) as raised:
            run_claude_session(
                executable=self.executable,
                model="fixture-model",
                prompt="{}",
                session_ref=session_ref,
                workspace=self.workspace,
                workspace_fd=self.workspace_fd,
                engagement=self.engagement,
                settings={},
                driver_scope=self._driver_scope(session_ref),
                timeout_seconds=1,
                max_budget_usd=None,
            )
        self.assertEqual(raised.exception.code, "descendant_containment_unavailable")

    def test_descendant_drain_failure_still_reaps_watchdog_and_closes_lifetime(self) -> None:
        lifetime_read_fd, lifetime_write_fd = os.pipe()
        reaped: list[object] = []

        def reap_watchdog(watchdog: object, write_fd: int | None) -> int:
            reaped.append(watchdog)
            self.assertEqual(write_fd, lifetime_write_fd)
            os.close(lifetime_write_fd)
            return 0

        watchdog = object()
        try:
            with (
                mock.patch.object(session_module, "_terminate_process_group"),
                mock.patch.object(session_module, "drain_holders", return_value=False),
                mock.patch.object(
                    session_module,
                    "_reap_watchdog",
                    side_effect=reap_watchdog,
                ),
                self.assertRaises(SessionLaunchError) as raised,
            ):
                session_module._cleanup_session(
                    mock.Mock(),
                    watchdog,
                    lifetime_write_fd,
                    self.root / "fixture-sentinel",
                    require_watchdog_success=True,
                )
            with self.assertRaises(OSError):
                os.fstat(lifetime_write_fd)
        finally:
            os.close(lifetime_read_fd)
            try:
                os.close(lifetime_write_fd)
            except OSError:
                pass
        self.assertEqual(raised.exception.code, "descendant_containment_failed")
        self.assertEqual(reaped, [watchdog])

    def test_normal_and_abnormal_leader_exit_cannot_leave_background_mutator(self) -> None:
        for mode in ("normal", "abnormal"):
            with self.subTest(mode=mode):
                session_ref = (
                    "33333333-3333-4333-8333-333333333333"
                    if mode == "normal"
                    else "44444444-4444-4444-8444-444444444444"
                )
                started_session_ids: list[int] = []
                result = run_claude_session(
                    executable=self.executable,
                    model="fixture-model",
                    prompt=json.dumps(
                        {
                            "fixture_background": mode,
                        }
                    ),
                    session_ref=session_ref,
                    workspace=self.workspace,
                    workspace_fd=self.workspace_fd,
                    engagement=self.engagement,
                    settings={},
                    driver_scope=self._driver_scope(session_ref),
                    timeout_seconds=5,
                    max_budget_usd=None,
                    on_process_started=started_session_ids.append,
                )
                self.assertTrue(result.started)
                self.assertFalse(result.timed_out)
                self.assertEqual(len(started_session_ids), 1)
                if mode == "normal":
                    self.assertEqual(result.returncode, 0)
                else:
                    self.assertLess(result.returncode or 0, 0)
                self.assertEqual(self._watchdog_pids(started_session_ids[0]), [])
                with self.assertRaises(ProcessLookupError):
                    os.killpg(started_session_ids[0], 0)

    def test_inherited_sentinel_drains_double_fork_setsid_on_exit_and_timeout(self) -> None:
        for mode in ("normal", "timeout"):
            with self.subTest(mode=mode):
                notify_path = self.workspace / (
                    f"cws-detached-{mode}-{os.getpid()}-{time.time_ns()}.sock"
                )
                listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                listener.bind(str(notify_path))
                listener.listen(1)
                try:
                    result = run_claude_session(
                        executable=self.executable,
                        model="fixture-model",
                        prompt=json.dumps(
                            {
                                "fixture_detached": True,
                                "fixture_notify_socket": str(notify_path),
                                **({"fixture_sleep": 30} if mode == "timeout" else {}),
                            }
                        ),
                        session_ref=(
                            "88888888-8888-4888-8888-888888888888"
                            if mode == "normal"
                            else "99999999-9999-4999-8999-999999999999"
                        ),
                        workspace=self.workspace,
                        workspace_fd=self.workspace_fd,
                        engagement=self.engagement,
                        settings={},
                        driver_scope=self._driver_scope(
                            "88888888-8888-4888-8888-888888888888"
                            if mode == "normal"
                            else "99999999-9999-4999-8999-999999999999"
                        ),
                        timeout_seconds=5 if mode == "normal" else 0.15,
                        max_budget_usd=None,
                    )
                    listener.settimeout(2.0)
                    connection, _ = listener.accept()
                    with connection:
                        notification = json.loads(connection.recv(65536))
                    detached_pid = int(notification["detached_pid"])
                    self.assertEqual(result.timed_out, mode == "timeout")
                    self.assertFalse(
                        self._pid_exists(detached_pid),
                        "sentinel-retaining setsid descendant survived session cleanup",
                    )
                finally:
                    listener.close()
                    notify_path.unlink(missing_ok=True)

    def test_process_start_callback_runs_before_child_gate_opens_and_failure_kills_child(self) -> None:
        callback_session_ids: list[int] = []
        notify_path = self.workspace / f"cws-gate-{os.getpid()}-{time.time_ns()}.sock"
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            listener.bind(str(notify_path))
            listener.listen(1)
        except BaseException:
            listener.close()
            notify_path.unlink(missing_ok=True)
            raise

        def observe_start(os_session_id: int) -> None:
            callback_session_ids.append(os_session_id)
            listener.settimeout(0.05)
            with self.assertRaises(TimeoutError):
                listener.accept()

        try:
            result = run_claude_session(
                executable=self.executable,
                model="fixture-model",
                prompt=json.dumps({"fixture_notify_socket": str(notify_path)}),
                session_ref="55555555-5555-4555-8555-555555555555",
                workspace=self.workspace,
                workspace_fd=self.workspace_fd,
                engagement=self.engagement,
                settings={},
                driver_scope=self._driver_scope("55555555-5555-4555-8555-555555555555"),
                timeout_seconds=5,
                max_budget_usd=None,
                on_process_started=observe_start,
            )
            listener.settimeout(1.0)
            connection, _ = listener.accept()
            with connection:
                notification = json.loads(connection.recv(65536))
                self.assertEqual(notification["os_session_id"], callback_session_ids[0])
        finally:
            listener.close()
            notify_path.unlink(missing_ok=True)
        self.assertEqual(result.session_ref, "55555555-5555-4555-8555-555555555555")
        self.assertEqual(len(callback_session_ids), 1)
        self.assertGreater(callback_session_ids[0], 0)

        rejected_session_ids: list[int] = []
        rejected_notify = self.workspace / f"cws-reject-{os.getpid()}-{time.time_ns()}.sock"
        rejected_listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            rejected_listener.bind(str(rejected_notify))
            rejected_listener.listen(1)
        except BaseException:
            rejected_listener.close()
            rejected_notify.unlink(missing_ok=True)
            raise

        def reject_start(os_session_id: int) -> None:
            rejected_session_ids.append(os_session_id)
            raise RuntimeError("fixture admission rejected")

        try:
            with self.assertRaises(SessionLaunchError) as raised:
                run_claude_session(
                    executable=self.executable,
                    model="fixture-model",
                    prompt=json.dumps({"fixture_notify_socket": str(rejected_notify)}),
                    session_ref="66666666-6666-4666-8666-666666666666",
                    workspace=self.workspace,
                    workspace_fd=self.workspace_fd,
                    engagement=self.engagement,
                    settings={},
                    driver_scope=self._driver_scope("66666666-6666-4666-8666-666666666666"),
                    timeout_seconds=5,
                    max_budget_usd=None,
                    on_process_started=reject_start,
                )
            rejected_listener.settimeout(0.1)
            with self.assertRaises(TimeoutError):
                rejected_listener.accept()
        finally:
            rejected_listener.close()
            rejected_notify.unlink(missing_ok=True)
        self.assertEqual(str(raised.exception), "Claude process-start callback failed")
        self.assertIsInstance(raised.exception.__cause__, RuntimeError)
        self.assertEqual(len(rejected_session_ids), 1)
        self.assertEqual(self._watchdog_pids(rejected_session_ids[0]), [])

    def test_sigkill_of_session_parent_cannot_leave_claude_descendants(self) -> None:
        session_ref = "77777777-7777-4777-8777-777777777777"
        notify_path = self.workspace / f"cws-death-{os.getpid()}-{time.time_ns()}.sock"
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            listener.bind(str(notify_path))
            listener.listen(1)
        except BaseException:
            listener.close()
            notify_path.unlink(missing_ok=True)
            raise
        outside_marker = self.root / "outside-scratch-marker"
        outside_marker.write_text("must survive", encoding="utf-8")
        prompt = json.dumps(
            {
                "fixture_detached": True,
                "fixture_notify_socket": str(notify_path),
                "fixture_scratch_marker": True,
                "fixture_scratch_symlink_target": str(outside_marker),
                "fixture_sleep": 30,
            }
        )

        runner_pid = os.fork()
        if runner_pid == 0:
            try:
                run_claude_session(
                    executable=self.executable,
                    model="fixture-model",
                    prompt=prompt,
                    session_ref=session_ref,
                    workspace=self.workspace,
                    workspace_fd=self.workspace_fd,
                    engagement=self.engagement,
                    settings={},
                    driver_scope=self._driver_scope(session_ref),
                    timeout_seconds=30,
                    max_budget_usd=None,
                )
            except BaseException:
                os._exit(2)
            os._exit(0)

        runner_reaped = False
        runtime_pid: int | None = None
        scratch_path: Path | None = None
        try:
            listener.settimeout(5.0)
            connection, _ = listener.accept()
            with connection:
                notification = json.loads(connection.recv(65536))
            runtime_pid = int(notification["os_session_id"])
            child_pid = int(notification["detached_pid"])
            scratch_path = Path(notification["scratch_path"])
            failure_marker = scratch_path.parent / (
                f".{scratch_path.name}{watchdog_module.SCRATCH_FAILURE_SUFFIX}"
            )
            self.assertTrue(self._pid_exists(runtime_pid))
            self.assertTrue(self._pid_exists(child_pid))
            self.assertTrue((scratch_path / "nested" / "marker").is_file())
            self.assertTrue((scratch_path / "outside-link").is_symlink())
            self.assertTrue(failure_marker.is_file())
            self.assertNotEqual(self._watchdog_pids(runtime_pid), [])

            os.kill(runner_pid, signal.SIGKILL)

            self.assertTrue(
                self._wait_until(lambda: not self._pid_exists(runtime_pid)),
                "fixture Claude leader survived its parent",
            )
            self.assertTrue(
                self._wait_until(lambda: not self._pid_exists(child_pid)),
                "fixture Claude descendant survived its parent",
            )
            self.assertTrue(
                self._wait_until(lambda: self._watchdog_pids(runtime_pid) == []),
                "parent-death watchdog did not exit after draining the Claude group",
            )
            self.assertTrue(
                self._wait_until(lambda: not scratch_path.exists()),
                "parent-death watchdog did not remove the bound model scratch directory",
            )
            self.assertFalse(failure_marker.exists())
            self.assertEqual(outside_marker.read_text(encoding="utf-8"), "must survive")

            waited_pid, waited_status = os.waitpid(runner_pid, 0)
            runner_reaped = True
            self.assertEqual(waited_pid, runner_pid)
            self.assertTrue(os.WIFSIGNALED(waited_status))
            self.assertEqual(os.WTERMSIG(waited_status), signal.SIGKILL)
        finally:
            listener.close()
            notify_path.unlink(missing_ok=True)
            if not runner_reaped:
                try:
                    os.kill(runner_pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                try:
                    os.waitpid(runner_pid, 0)
                except ChildProcessError:
                    pass
            if runtime_pid is not None:
                try:
                    os.killpg(runtime_pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass


if __name__ == "__main__":
    unittest.main(verbosity=2)
