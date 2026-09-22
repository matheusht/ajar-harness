#!/usr/bin/env python3
"""Focused contract tests for the Docker-backed work-queue parent seam."""

from __future__ import annotations

import base64
import contextlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from container_session_supervisor import _validate_session
from docker_session_runtime import (
    CONTROL_DESTINATION,
    DockerRuntimeLimits,
    DockerSessionIdentity,
    DockerSessionResult,
)
from engagement_records import sha256_bytes
from driver_action_admission import DriverActionBroker
from work_queue_driver import (
    CONTAINER_BROKER_CLIENT,
    CONTAINER_STOP_HOOK,
    DOCKER_BROKER_MANIFEST_FILE,
    DOCKER_SESSION_FILE,
    BoundRun,
    DockerQueueBackend,
    DriverError,
    _container_stop_hook_settings,
    _run_docker_queue_session,
)


ROOT = Path(__file__).resolve().parents[1]
RUN_WORK_QUEUE = ROOT / "tools" / "run-work-queue.py"
IMAGE = "golang@sha256:" + "a" * 64
CONTAINER_ID = "b" * 64
NETWORK_ID = "c" * 64
CONFIG_DIGEST = "sha256:" + "d" * 64
SESSION_KEY = b"k" * 32
SESSION_REF = "0d1058c2-32b0-4b8c-9326-9d6bf2e48314"
MODEL_SECRET = "test-model-secret-never-retain"
LIVE_IMAGE = os.environ.get("HARNESS_DOCKER_QUEUE_TEST_IMAGE", "")
LIVE_PYTHON = os.environ.get("HARNESS_DOCKER_QUEUE_TEST_PYTHON", "/usr/local/bin/python3")


def _load_cli_module() -> object:
    spec = importlib.util.spec_from_file_location("docker_work_queue_cli", RUN_WORK_QUEUE)
    if spec is None or spec.loader is None:
        raise RuntimeError("run-work-queue loader unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakePrepared:
    def __init__(
        self,
        *,
        identity: DockerSessionIdentity,
        result: DockerSessionResult,
        events: list[str],
    ) -> None:
        self.identity = identity
        self.result = result
        self.events = events
        self.writes: dict[str, bytes] = {}
        self.start_arguments: dict[str, object] | None = None

    def __enter__(self) -> "_FakePrepared":
        self.events.append("prepared_enter")
        return self

    def __exit__(self, *_args: object) -> None:
        self.events.append("prepared_exit")

    def write_control_file(self, name: str, value: bytes) -> Path:
        self.events.append(f"write:{name}")
        self.writes[name] = value
        return Path(CONTROL_DESTINATION) / name

    def start(self, **arguments: object) -> DockerSessionResult:
        self.events.append("start_called")
        self.start_arguments = arguments
        callback = arguments["on_process_started"]
        assert callable(callback)
        callback(self.identity)
        self.events.append("container_released")
        return self.result


class DockerWorkQueueIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name).resolve()
        self.workspace = root / "target"
        self.engagement = self.workspace / "engagements" / "fixture"
        self.engagement.mkdir(parents=True)
        self.workspace_fd = os.open(self.workspace, os.O_RDONLY | os.O_DIRECTORY)
        self.engagement_fd = os.open(self.engagement, os.O_RDONLY | os.O_DIRECTORY)
        self.bound = BoundRun(
            workspace=self.workspace,
            engagement=self.engagement,
            workspace_fd=self.workspace_fd,
            engagement_fd=self.engagement_fd,
        )
        self.backend = DockerQueueBackend(
            image=IMAGE,
            python_executable="/usr/local/bin/python3",
            docker_executable=Path("/usr/local/bin/docker"),
            limits=DockerRuntimeLimits(),
        )
        self.state = {
            "ledger_hash": "sha256:" + "1" * 64,
            "source_hashes": {
                "events.jsonl": "sha256:" + "2" * 64,
                "attempts.jsonl": "sha256:" + "3" * 64,
                "artifacts.jsonl": "sha256:" + "4" * 64,
            },
        }

    def tearDown(self) -> None:
        os.close(self.engagement_fd)
        os.close(self.workspace_fd)
        self.temporary.cleanup()

    def _exercise(
        self,
        *,
        result: DockerSessionResult,
        stop_requested: object | None = None,
    ) -> tuple[object, _FakePrepared, list[str], object]:
        events: list[str] = []
        identity = DockerSessionIdentity(
            container_id=CONTAINER_ID,
            container_name="lrh-test-container",
            network_id=NETWORK_ID,
            network_name="lrh-test-network",
            nonce="nonce",
            config_digest=CONFIG_DIGEST,
            control_directory=Path(self.temporary.name) / "control",
            mount_manifest={"/workspace": str(self.workspace)},
        )
        prepared = _FakePrepared(identity=identity, result=result, events=events)
        captured: dict[str, object] = {}

        class FakeBroker:
            def __init__(broker_self, **arguments: object) -> None:
                events.append("broker_init")
                captured["broker_arguments"] = arguments

            def __enter__(broker_self) -> "FakeBroker":
                events.append("broker_enter")
                return broker_self

            def __exit__(broker_self, *_args: object) -> None:
                events.append("broker_exit")

            def container_manifest(
                broker_self, *, advertised_host: str | None = None
            ) -> dict[str, object]:
                captured["advertised_host"] = advertised_host
                return {
                    "schema_version": 1,
                    "runtime_identity": {
                        "container_id": CONTAINER_ID,
                        "container_config_digest": CONFIG_DIGEST,
                    },
                }

            def activate_docker(broker_self) -> None:
                events.append("broker_activate")

        def prepare(spec: object) -> _FakePrepared:
            events.append("prepare")
            captured["spec"] = spec
            return prepared

        def activate_sidecar(**arguments: object) -> None:
            events.append("sidecar_activate")
            captured["sidecar_arguments"] = arguments

        cancellation = stop_requested if stop_requested is not None else (lambda: False)
        captured["stop_requested"] = cancellation
        with (
            mock.patch("work_queue_driver.prepare_docker_session", side_effect=prepare),
            mock.patch("work_queue_driver.DriverActionBroker", FakeBroker),
            mock.patch(
                "work_queue_driver.new_container_broker_session_key",
                return_value=SESSION_KEY,
            ),
            mock.patch(
                "work_queue_driver.activate_docker_action_admission",
                side_effect=activate_sidecar,
            ),
            mock.patch("work_queue_driver._named_identity_is_current", return_value=True),
            mock.patch.dict(
                os.environ,
                {"ANTHROPIC_API_KEY": MODEL_SECRET},
                clear=True,
            ),
        ):
            execution = _run_docker_queue_session(
                bound=self.bound,
                backend=self.backend,
                executable=Path("/usr/local/bin/claude"),
                model="claude-test-20260826",
                prompt="bounded prompt",
                session_ref=SESSION_REF,
                state=self.state,
                timeout_seconds=30.0,
                max_budget_usd=1.25,
                read_only_inputs=(),
                admission={"status": "armed"},
                admission_token="admission-token",
                execution_deadline=10_000.0,
                stop_requested=cancellation,  # type: ignore[arg-type]
            )
        return execution, prepared, events, captured

    @staticmethod
    def _result(
        *,
        returncode: int = 0,
        timed_out: bool = False,
        interrupted: bool = False,
        oom_killed: bool = False,
        output_truncated: bool = False,
        stdout: bytes = b'{"is_error":false,"total_cost_usd":0.5}\n',
    ) -> DockerSessionResult:
        return DockerSessionResult(
            started=True,
            timed_out=timed_out,
            interrupted=interrupted,
            returncode=returncode,
            oom_killed=oom_killed,
            output_truncated=output_truncated,
            container_id=CONTAINER_ID,
            network_id=NETWORK_ID,
            _stdout=stdout,
        )

    def test_two_phase_identity_controls_activation_and_secret_handoff(self) -> None:
        execution, prepared, events, captured = self._exercise(result=self._result())

        self.assertEqual(
            events,
            [
                "prepare",
                "prepared_enter",
                "broker_init",
                "broker_enter",
                f"write:{DOCKER_SESSION_FILE}",
                f"write:{DOCKER_BROKER_MANIFEST_FILE}",
                "start_called",
                "sidecar_activate",
                "broker_activate",
                "container_released",
                "broker_exit",
                "prepared_exit",
            ],
        )
        self.assertEqual(set(prepared.writes), {DOCKER_SESSION_FILE, DOCKER_BROKER_MANIFEST_FILE})
        session_bytes = prepared.writes[DOCKER_SESSION_FILE]
        session_value = json.loads(session_bytes)
        command, environment = _validate_session(session_value)
        self.assertEqual(command[0], "/usr/local/bin/claude")
        self.assertEqual(command[-1], "bounded prompt")
        self.assertEqual(
            set(environment),
            {
                "HARNESS_ACTIVE_ENGAGEMENT",
                "HARNESS_EXPECTED_LEDGER_HASH",
                "HARNESS_EXPECTED_SOURCE_HASHES",
                "HARNESS_EXPECTED_RUNTIME_SESSION_REF",
            },
        )
        self.assertEqual(environment["HARNESS_EXPECTED_RUNTIME_SESSION_REF"], SESSION_REF)

        runtime_spec = captured["spec"]
        self.assertEqual(runtime_spec.image, IMAGE)
        self.assertEqual(runtime_spec.argv[-1], sha256_bytes(session_bytes))
        self.assertEqual(runtime_spec.argv[-2], "--session-sha256")
        self.assertEqual(runtime_spec.network_internal, False)
        self.assertTrue(runtime_spec.supervisor_write_broker)
        inspect_material = json.dumps(
            {
                "image": runtime_spec.image,
                "executable": runtime_spec.executable,
                "argv": runtime_spec.argv,
            },
            sort_keys=True,
        ).encode("utf-8")
        self.assertTrue(MODEL_SECRET.encode("utf-8") not in inspect_material)
        self.assertTrue(SESSION_KEY not in inspect_material)
        self.assertTrue(base64.b64encode(SESSION_KEY) not in inspect_material)
        self.assertTrue(b"bounded prompt" not in inspect_material)
        self.assertTrue(MODEL_SECRET.encode("utf-8") not in session_bytes)
        self.assertTrue(base64.b64encode(SESSION_KEY) not in session_bytes)

        self.assertIsNotNone(prepared.start_arguments)
        assert prepared.start_arguments is not None
        bootstrap = json.loads(prepared.start_arguments["stdin_bytes"])
        self.assertEqual(
            bootstrap,
            {
                "schema_version": 1,
                "environment": {"ANTHROPIC_API_KEY": MODEL_SECRET},
                "broker_session_key_base64": base64.b64encode(SESSION_KEY).decode("ascii"),
            },
        )
        self.assertIs(
            prepared.start_arguments["stop_requested"], captured["stop_requested"]
        )
        self.assertEqual(captured["advertised_host"], "host.docker.internal")
        self.assertEqual(
            captured["broker_arguments"]["docker_identity"],
            {
                "container_id": CONTAINER_ID,
                "container_config_digest": CONFIG_DIGEST,
            },
        )
        self.assertEqual(
            captured["sidecar_arguments"]["container_config_digest"], CONFIG_DIGEST
        )
        self.assertFalse(execution.interrupted)
        self.assertEqual(execution.session.returncode, 0)
        self.assertEqual(execution.session.cost_usd, 0.5)

    def test_storage_timeout_interrupt_and_nonzero_are_distinct(self) -> None:
        with self.assertRaises(DriverError) as storage:
            self._exercise(result=self._result(returncode=73, stdout=b"not-json"))
        self.assertEqual(storage.exception.code, "driver_session_storage_exceeded")

        timeout, _prepared, _events, _captured = self._exercise(
            result=self._result(returncode=137, timed_out=True, stdout=b"")
        )
        self.assertTrue(timeout.session.timed_out)
        self.assertFalse(timeout.interrupted)

        interrupted, prepared, _events, _captured = self._exercise(
            result=self._result(returncode=137, interrupted=True, stdout=b"")
        )
        self.assertTrue(interrupted.interrupted)
        self.assertFalse(interrupted.session.timed_out)
        self.assertIsNotNone(prepared.start_arguments)

        ordinary, _prepared, _events, _captured = self._exercise(
            result=self._result(returncode=7, stdout=b"not-json")
        )
        self.assertEqual(ordinary.session.returncode, 7)
        self.assertFalse(ordinary.session.output_was_json)

        truncated, _prepared, _events, _captured = self._exercise(
            result=self._result(output_truncated=True)
        )
        self.assertFalse(truncated.session.output_was_json)
        self.assertIsNone(truncated.session.runtime_reported_error)
        self.assertIsNone(truncated.session.cost_usd)

    def test_container_stop_hook_uses_authenticated_client_mode(self) -> None:
        settings = _container_stop_hook_settings("/usr/local/bin/python3")
        command = settings["hooks"]["Stop"][0]["hooks"][0]["command"]
        self.assertEqual(
            command,
            f"/usr/local/bin/python3 {CONTAINER_BROKER_CLIENT} stop-hook",
        )
        self.assertEqual(CONTAINER_STOP_HOOK, CONTAINER_BROKER_CLIENT)

    def test_backend_rejects_tagged_or_noncanonical_container_paths(self) -> None:
        for image, python_executable in (
            ("python:3.13@sha256:" + "a" * 64, "/usr/local/bin/python3"),
            (IMAGE, "usr/local/bin/python3"),
            (IMAGE, "/usr/local/../local/bin/python3"),
            (IMAGE, "//usr/local/bin/python3"),
        ):
            with self.subTest(image=image, python_executable=python_executable):
                backend = DockerQueueBackend(
                    image=image,
                    python_executable=python_executable,
                    docker_executable=Path("/usr/local/bin/docker"),
                    limits=DockerRuntimeLimits(),
                )
                with self.assertRaises(DriverError) as failure:
                    backend.validate()
                self.assertEqual(failure.exception.code, "driver_docker_backend_invalid")

    def test_public_cli_requires_explicit_docker_backend_configuration(self) -> None:
        module = _load_cli_module()
        parser = module.build_parser()
        base = [
            "run",
            "--workspace", str(self.workspace),
            "--engagement", str(self.engagement),
            "--runtime", "claude-code",
            "--model", "claude-test-20260826",
            "--reviewer-model", "claude-reviewer-20260826",
            "--max-sessions", "1",
            "--max-wall-seconds", "30",
            "--session-timeout-seconds", "20",
        ]
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            parser.parse_args(base)
        complete = [
            *base,
            "--session-backend", "docker",
            "--claude-executable", "/usr/local/bin/claude",
            "--docker-image", IMAGE,
            "--docker-python-executable", "/usr/local/bin/python3",
            "--docker-executable", "/usr/local/bin/docker",
            "--docker-memory-bytes", str(2 * 1024 * 1024 * 1024),
            "--docker-cpus", "2",
            "--docker-pids", "128",
            "--docker-nofile", "1024",
            "--docker-scratch-bytes", str(256 * 1024 * 1024),
            "--docker-scratch-inodes", "16384",
            "--docker-shm-bytes", str(16 * 1024 * 1024),
            "--docker-shm-inodes", "1024",
        ]
        parsed = parser.parse_args(complete)
        self.assertEqual(parsed.session_backend, "docker")
        self.assertEqual(parsed.docker_image, IMAGE)

    @unittest.skipUnless(
        LIVE_IMAGE,
        "set HARNESS_DOCKER_QUEUE_TEST_IMAGE to an already-cached immutable Python image",
    )
    def test_live_supervisor_relay_keeps_broker_key_out_of_model_child(self) -> None:
        docker = shutil.which("docker")
        if docker is None:
            self.skipTest("Docker CLI unavailable")
        fake_claude = self.workspace / "fake-claude"
        fake_claude.write_text(
            """#!/usr/local/bin/python3
import json
import ctypes
import errno
import fcntl
import os
import pathlib
import shlex
import subprocess
import sys
import threading

try:
    pid1_environ = pathlib.Path('/proc/1/environ').read_bytes()
except OSError:
    pid1_environ = b''
try:
    pid1_cmdline = pathlib.Path('/proc/1/cmdline').read_bytes()
except OSError:
    pid1_cmdline = b''
try:
    with pathlib.Path('/proc/1/mem').open('rb') as handle:
        handle.read(1)
except OSError:
    pid1_memory_denied = True
else:
    pid1_memory_denied = False
status_fields = {}
for line in pathlib.Path('/proc/self/status').read_text(encoding='ascii').splitlines():
    key, separator, value = line.partition(':')
    if separator:
        status_fields[key] = value.strip()
pid1_status_fields = {}
for line in pathlib.Path('/proc/1/status').read_text(encoding='ascii').splitlines():
    key, separator, value = line.partition(':')
    if separator:
        pid1_status_fields[key] = value.strip()
libc = ctypes.CDLL(None, use_errno=True)
pid1_descriptor = libc.syscall(434, 1, 0x80)
ctypes.set_errno(0)
pid1_duplicate = libc.syscall(438, pid1_descriptor, 1, 0)
pid1_getfd_denied = pid1_duplicate == -1 and ctypes.get_errno() == errno.EPERM
if pid1_descriptor >= 0:
    os.close(pid1_descriptor)
if pid1_duplicate >= 0:
    os.close(pid1_duplicate)
listener_hidden = True
for descriptor_path in pathlib.Path('/proc/self/fd').iterdir():
    try:
        destination = descriptor_path.readlink()
    except OSError:
        continue
    if 'seccomp notify' in str(destination):
        listener_hidden = False
short_writes = []
def write_from_nonleader_thread():
    reader, writer = os.pipe2(os.O_NONBLOCK)
    try:
        capacity = fcntl.fcntl(writer, fcntl.F_GETPIPE_SZ)
        requested = b'x' * (2 * capacity)
        short_writes.append((os.write(writer, requested), len(requested)))
    finally:
        os.close(writer)
        os.close(reader)
thread = threading.Thread(target=write_from_nonleader_thread)
thread.start()
thread.join()
required = {
    "relay_present": pathlib.Path(os.environ.get("HARNESS_CONTAINER_BROKER_RELAY_SOCKET", "")).exists(),
    "manifest_hidden": "HARNESS_CONTAINER_BROKER_MANIFEST_FILE" not in os.environ,
    "key_hidden": not any(name in os.environ for name in (
        "HARNESS_CONTAINER_BROKER_KEY_FILE", "HARNESS_CONTAINER_BROKER_KEY_FD"
    )),
    "key_file_absent": not pathlib.Path("/run/lrh-control/broker-session.key").exists(),
    "pid1_memory_denied": pid1_memory_denied,
    "model_caps_zero": all(status_fields.get(name) == '0000000000000000' for name in (
        'CapInh', 'CapPrm', 'CapEff', 'CapAmb'
    )),
    "model_no_new_privileges": status_fields.get('NoNewPrivs') == '1',
    "pid1_caps_zero": all(pid1_status_fields.get(name) == '0000000000000000' for name in (
        'CapInh', 'CapPrm', 'CapEff', 'CapAmb'
    )),
    "pid1_getfd_denied": pid1_getfd_denied,
    "listener_hidden": listener_hidden,
    "threaded_nonstorage_short_preserved": (
        len(short_writes) == 1 and 0 < short_writes[0][0] < short_writes[0][1]
    ),
    "auth_absent_from_pid1_inspectable_state": (
        os.environ["ANTHROPIC_API_KEY"].encode("utf-8") not in pid1_environ
        and os.environ["ANTHROPIC_API_KEY"].encode("utf-8") not in pid1_cmdline
    ),
}
settings = json.loads(sys.argv[sys.argv.index("--settings") + 1])
hook = settings["hooks"]["Stop"][0]["hooks"][0]["command"]
hook_result = subprocess.run(
    shlex.split(hook),
    input=(json.dumps({
        "session_id": os.environ["HARNESS_EXPECTED_RUNTIME_SESSION_REF"],
        "hook_event_name": "Stop",
        "stop_hook_active": False,
    }, sort_keys=True, separators=(",", ":")) + "\\n").encode("utf-8"),
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    check=False,
)
try:
    hook_output = json.loads(hook_result.stdout)
except json.JSONDecodeError:
    hook_output = None
if not all(required.values()) or hook_result.returncode != 0 or hook_output != {}:
    raise SystemExit(91)
print(json.dumps({"is_error": False, "total_cost_usd": 0.25}))
""".replace("/usr/local/bin/python3", LIVE_PYTHON),
            encoding="utf-8",
        )
        fake_claude.chmod(0o755)
        backend = DockerQueueBackend(
            image=LIVE_IMAGE,
            python_executable=LIVE_PYTHON,
            docker_executable=Path(docker).resolve(),
            limits=DockerRuntimeLimits(),
        )
        broker_request_seen = threading.Event()
        stopped_manifest_seen: dict[str, object] = {}

        class ObservedBroker(DriverActionBroker):
            def _serve_container_connection(self, connection: object) -> None:
                broker_request_seen.set()
                super()._serve_container_connection(connection)  # type: ignore[arg-type]

        def inspect_stopped_container(**arguments: object) -> None:
            identifier = arguments.get("container_id")
            if not isinstance(identifier, str):
                raise AssertionError("container activation omitted exact identity")
            inspected = subprocess.run(
                [docker, "container", "inspect", identifier],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )
            values = json.loads(inspected.stdout)
            host = values[0]["HostConfig"]
            stopped_manifest_seen.update(
                {
                    "status": values[0]["State"]["Status"],
                    "cap_drop": host["CapDrop"],
                    "cap_add": host["CapAdd"],
                    "security_opt": host["SecurityOpt"],
                }
            )

        engagement_entry = os.fstat(self.engagement_fd)
        admission = {
            "status": "armed",
            "runtime_session_ref": SESSION_REF,
            "action_id": "live-relay-probe",
            "os_session_id": None,
            "runtime_identity": None,
            "hook_session_ref": sha256_bytes(
                b"llm-redteam-harness:session-end:v1:" + SESSION_REF.encode("utf-8")
            ),
            "state_binding": {},
            "engagement_identity": {
                "device": engagement_entry.st_dev,
                "inode": engagement_entry.st_ino,
            },
            "predicate": {
                "documents": [{"name": "probe", "argument": "--file"}]
            },
        }
        with (
            mock.patch("work_queue_driver.DriverActionBroker", ObservedBroker),
            mock.patch(
                "work_queue_driver.activate_docker_action_admission",
                side_effect=inspect_stopped_container,
            ),
            mock.patch.dict(
                os.environ,
                {"ANTHROPIC_API_KEY": MODEL_SECRET},
                clear=False,
            ),
        ):
            execution = _run_docker_queue_session(
                bound=self.bound,
                backend=backend,
                executable=Path("/workspace/fake-claude"),
                model="claude-test-20260826",
                prompt="bounded live relay probe",
                session_ref=SESSION_REF,
                state=self.state,
                timeout_seconds=30.0,
                max_budget_usd=None,
                read_only_inputs=(),
                admission=admission,
                admission_token="live-admission-token",
                execution_deadline=time.monotonic() + 30.0,
                stop_requested=lambda: False,
            )
        self.assertEqual(execution.session.returncode, 0)
        self.assertEqual(execution.session.cost_usd, 0.25)
        self.assertTrue(broker_request_seen.is_set())
        self.assertEqual(
            stopped_manifest_seen,
            {
                "status": "created",
                "cap_drop": ["ALL"],
                "cap_add": ["CAP_SYS_PTRACE"],
                "security_opt": ["no-new-privileges=true"],
            },
        )

    @unittest.skipUnless(
        LIVE_IMAGE,
        "set HARNESS_DOCKER_QUEUE_TEST_IMAGE to an already-cached immutable Python image",
    )
    def test_live_storage_breach_is_sanitized_and_kills_the_session(self) -> None:
        docker = shutil.which("docker")
        if docker is None:
            self.skipTest("Docker CLI unavailable")
        fake_claude = self.workspace / "fake-storage-claude"
        fake_claude.write_text(
            """#!/usr/local/bin/python3
import ctypes
import os
import pathlib
import signal
import threading
import time

thread_completed = []
thread = threading.Thread(target=lambda: thread_completed.append(True))
thread.start()
thread.join()
if thread_completed != [True]:
    raise SystemExit(96)

libc = ctypes.CDLL(None, use_errno=True)
libc.syscall.restype = ctypes.c_long
for syscall_number, arguments, expected_errno in (
    (435, (0, 0), 38),
    (0, (0, 0), 38),
    (66, (0, 0, 0), 38),
    (70, (0, 0, 0, 0), 38),
    (71, (0, 0, 0, 0), 38),
    (76, (0, 0, 0, 0, 0, 0), 38),
    (271, (0, 0, 0, 0, 0, 0), 38),
    (285, (0, 0, 0, 0, 0, 0), 38),
    (287, (0, 0, 0, 0, 0, 0), 38),
    (222, (0, 4096, 1, 1, -1, 0), 38),
    (999, (), 38),
    (220, (0x00800000 | signal.SIGCHLD, 0, 0, 0, 0), 1),
):
    ctypes.set_errno(0)
    result = libc.syscall(syscall_number, *arguments)
    if result == 0:
        os._exit(93)
    if result != -1 or ctypes.get_errno() != expected_errno:
        raise SystemExit(94)

first = os.fork()
if first != 0:
    os.waitpid(first, 0)
    time.sleep(10)
    raise SystemExit(95)
os.setsid()
second = os.fork()
if second != 0:
    os._exit(0)
os.chdir('/')
os.closerange(3, 256)

scratch = pathlib.Path('/scratch')
path = scratch / 'one-shot-oversized'
descriptor = os.open(path, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
requested = 2 * 1024 * 1024
written = os.write(descriptor, b'x' * requested)
os.close(descriptor)
path.unlink(missing_ok=True)
os._exit(0 if 0 < written < requested else 92)
""".replace("/usr/local/bin/python3", LIVE_PYTHON),
            encoding="utf-8",
        )
        fake_claude.chmod(0o755)
        backend = DockerQueueBackend(
            image=LIVE_IMAGE,
            python_executable=LIVE_PYTHON,
            docker_executable=Path(docker).resolve(),
            limits=DockerRuntimeLimits(
                memory_bytes=128 * 1024 * 1024,
                cpu_count=0.5,
                pids=32,
                nofile=128,
                scratch_bytes=1024 * 1024,
                scratch_inodes=64,
                shm_bytes=1024 * 1024,
                shm_inodes=32,
            ),
        )
        engagement_entry = os.fstat(self.engagement_fd)
        admission = {
            "status": "armed",
            "runtime_session_ref": SESSION_REF,
            "action_id": "live-storage-probe",
            "os_session_id": None,
            "runtime_identity": None,
            "hook_session_ref": sha256_bytes(
                b"llm-redteam-harness:session-end:v1:" + SESSION_REF.encode("utf-8")
            ),
            "state_binding": {},
            "engagement_identity": {
                "device": engagement_entry.st_dev,
                "inode": engagement_entry.st_ino,
            },
            "predicate": {"documents": [{"name": "probe", "argument": "--file"}]},
        }
        started = time.monotonic()
        with (
            mock.patch("work_queue_driver.activate_docker_action_admission"),
            mock.patch.dict(os.environ, {}, clear=True),
            self.assertRaises(DriverError) as raised,
        ):
            _run_docker_queue_session(
                bound=self.bound,
                backend=backend,
                executable=Path("/workspace/fake-storage-claude"),
                model="claude-test-20260826",
                prompt="bounded live storage probe",
                session_ref=SESSION_REF,
                state=self.state,
                timeout_seconds=20.0,
                max_budget_usd=None,
                read_only_inputs=(),
                admission=admission,
                admission_token="live-storage-token",
                execution_deadline=time.monotonic() + 20.0,
                stop_requested=lambda: False,
            )
        self.assertEqual(raised.exception.code, "driver_session_storage_exceeded")
        self.assertLess(time.monotonic() - started, 10.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
