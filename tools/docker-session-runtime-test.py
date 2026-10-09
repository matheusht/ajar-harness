#!/usr/bin/env python3
"""Focused unit and opt-in Docker integration tests for the session runtime boundary.

The integration lane is deliberately guarded and never pulls or builds. Run it only when the
immutable image below is already cached:

    HARNESS_RUN_DOCKER_INTEGRATION=1 python3 tools/docker-session-runtime-test.py
"""

from __future__ import annotations

import json
import os
import socket
import stat
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
from pathlib import Path
from unittest import mock

import docker_session_runtime as runtime


TOOLS = Path(__file__).resolve().parent
HARNESS = TOOLS.parent.resolve()
DOCKER = Path("/usr/local/bin/docker")
DEFAULT_IMAGE_DIGEST = "05b2b8b732ecd268fee8727a369f936f022d1321b59befd13c30ede22769dcdc"
IMAGE = os.environ.get(
    "HARNESS_DOCKER_RUNTIME_TEST_IMAGE", f"python@sha256:{DEFAULT_IMAGE_DIGEST}"
)
IMAGE_DIGEST = IMAGE.rsplit("@sha256:", 1)[-1]
IMAGE_ID = f"sha256:{IMAGE_DIGEST}"
RUN_DOCKER_INTEGRATION = os.environ.get("HARNESS_RUN_DOCKER_INTEGRATION") == "1"
EVASIVE_READY_PATH = "/scratch/lrh-evader-ready"
EVASIVE_LAUNCH_SCRIPT = r"""
    (
      (
        for descriptor_path in /proc/self/fd/*; do
          descriptor=${descriptor_path##*/}
          case "$descriptor" in
            0|1|2) ;;
            *) eval "exec ${descriptor}>&-" 2>/dev/null || true ;;
          esac
        done
        cd /
        setsid /bin/sh -c 'printf ready > /scratch/lrh-evader-ready; exec /bin/sleep 60' \
          </dev/null >/dev/null 2>&1 &
      ) &
    ) &
    ready_attempt=0
    while [ ! -f /scratch/lrh-evader-ready ]; do
      ready_attempt=$((ready_attempt + 1))
      [ "$ready_attempt" -lt 500 ] || exit 97
      /bin/sleep 0.01
    done
"""
EVASIVE_HOLD_SCRIPT = EVASIVE_LAUNCH_SCRIPT + r"""
    printf 'evader-ready\n'
    exec /bin/sleep 60
"""


def _limits() -> runtime.DockerRuntimeLimits:
    return runtime.DockerRuntimeLimits(
        memory_bytes=128 * 1024 * 1024,
        cpu_count=0.5,
        pids=32,
        nofile=128,
        scratch_bytes=1024 * 1024,
        scratch_inodes=64,
        shm_bytes=1024 * 1024,
        shm_inodes=32,
    )


def _docker(*arguments: str, check: bool = True, timeout: float = 20.0) -> subprocess.CompletedProcess[bytes]:
    result = subprocess.run(
        [str(DOCKER), *arguments],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=runtime._docker_environment(),
        timeout=timeout,
        check=False,
    )
    if check and result.returncode != 0:
        raise AssertionError(
            f"exact Docker command failed ({result.returncode}): "
            f"{result.stderr[:4096].decode('utf-8', errors='replace')}"
        )
    return result


def _inspect(kind: str, identifier: str) -> dict[str, object]:
    result = _docker(kind, "inspect", identifier)
    values = json.loads(result.stdout)
    if not isinstance(values, list) or len(values) != 1 or not isinstance(values[0], dict):
        raise AssertionError("unexpected exact inspect response")
    return values[0]


def _is_absent(kind: str, identifier: str) -> bool:
    return _docker(kind, "inspect", identifier, check=False).returncode != 0


def _wait_absent(kind: str, identifier: str, timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _is_absent(kind, identifier):
            return
        time.sleep(0.05)
    raise AssertionError(f"{kind} {identifier} survived exact cleanup")


def _wait_path_absent(path: Path, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not path.exists():
            return
        time.sleep(0.025)
    raise AssertionError(f"path {path} survived exact cleanup")


def _wait_container_running(identifier: str, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = _inspect("container", identifier)
        state = value.get("State")
        if isinstance(state, dict) and state.get("Running") is True:
            return
        time.sleep(0.05)
    raise AssertionError(f"container {identifier} never reached running state")


class DockerRuntimeUnitTest(unittest.TestCase):
    def test_unsupported_platform_or_root_fails_before_docker_access(self) -> None:
        spec = runtime.DockerRuntimeSpec(
            image=IMAGE,
            executable="/bin/true",
            argv=(),
            workspace=Path("/tmp/lrh-never-read-workspace"),
            harness=Path("/tmp/lrh-never-read-harness"),
        )
        cases = (("linux", 501), ("darwin", 0))
        for platform, uid in cases:
            with (
                self.subTest(platform=platform, uid=uid),
                mock.patch.object(runtime.sys, "platform", platform),
                mock.patch.object(runtime.os, "getuid", return_value=uid),
                mock.patch.object(runtime, "_resolve_docker") as resolve_docker,
                self.assertRaises(runtime.DockerRuntimeError) as raised,
            ):
                runtime._preflight(spec)
            self.assertEqual(raised.exception.code, "docker_runtime_unsupported")
            resolve_docker.assert_not_called()

    def test_only_immutable_digest_references_are_accepted(self) -> None:
        repository, digest = runtime._validate_image_reference(IMAGE)
        self.assertEqual(repository, IMAGE.split("@", 1)[0])
        self.assertEqual(digest, IMAGE_DIGEST)
        self.assertEqual(
            runtime._validate_image_reference(f"localhost:5000/team/golang@sha256:{IMAGE_DIGEST}"),
            ("localhost:5000/team/golang", IMAGE_DIGEST),
        )
        for invalid in (
            "golang:latest",
            f"golang:latest@sha256:{IMAGE_DIGEST}",
            f"golang@sha256:{IMAGE_DIGEST[:-1]}",
            f"golang@sha256:{IMAGE_DIGEST.upper()}",
            f"golang @sha256:{IMAGE_DIGEST}",
            f"golang@sha512:{IMAGE_DIGEST}",
        ):
            with self.subTest(invalid=invalid), self.assertRaises(runtime.DockerRuntimeError) as raised:
                runtime._validate_image_reference(invalid)
            self.assertEqual(raised.exception.code, "docker_image_unpinned")

    def test_resource_limits_are_finite_and_bounded(self) -> None:
        _limits().validate()
        invalid = (
            runtime.DockerRuntimeLimits(memory_bytes=0),
            runtime.DockerRuntimeLimits(cpu_count=float("inf")),
            runtime.DockerRuntimeLimits(cpu_count=True),
            runtime.DockerRuntimeLimits(pids=15),
            runtime.DockerRuntimeLimits(nofile=63),
            runtime.DockerRuntimeLimits(scratch_bytes=1024),
            runtime.DockerRuntimeLimits(scratch_inodes=31),
            runtime.DockerRuntimeLimits(shm_bytes=1024),
            runtime.DockerRuntimeLimits(shm_inodes=31),
        )
        for limits in invalid:
            with self.subTest(limits=limits), self.assertRaises(runtime.DockerRuntimeError) as raised:
                limits.validate()
            self.assertEqual(raised.exception.code, "docker_limits_invalid")

    def test_optional_mounts_are_distinct_nonoverlapping_regular_files(self) -> None:
        with tempfile.TemporaryDirectory(prefix="docker-input-policy-") as temporary:
            root = Path(temporary).resolve()
            workspace = root / "workspace"
            harness = root / "harness"
            outside = root / "outside"
            for directory in (workspace, harness, outside):
                directory.mkdir()
            regular = outside / "input.txt"
            regular.write_bytes(b"input")
            self.assertEqual(
                runtime._validate_read_only_inputs(
                    (regular,), workspace=workspace, harness=harness
                ),
                (regular,),
            )

            inside_workspace = workspace / "already-mounted.txt"
            inside_workspace.write_bytes(b"workspace")
            with self.assertRaises(runtime.DockerRuntimeError) as overlap:
                runtime._validate_read_only_inputs(
                    (inside_workspace,), workspace=workspace, harness=harness
                )
            self.assertEqual(overlap.exception.code, "docker_mount_overlap")

            alias = outside / "hardlink.txt"
            os.link(regular, alias)
            with self.assertRaises(runtime.DockerRuntimeError) as duplicate:
                runtime._validate_read_only_inputs(
                    (regular, alias), workspace=workspace, harness=harness
                )
            self.assertEqual(duplicate.exception.code, "docker_input_invalid")

            fifo = outside / "input.fifo"
            os.mkfifo(fifo)
            unix_socket = Path("/tmp").resolve() / ("lrh-input-" + uuid.uuid4().hex + ".sock")
            listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            listener.bind(str(unix_socket))
            try:
                for invalid in (outside, fifo, unix_socket):
                    with (
                        self.subTest(invalid=invalid),
                        self.assertRaises(runtime.DockerRuntimeError) as rejected,
                    ):
                        runtime._validate_read_only_inputs(
                            (invalid,), workspace=workspace, harness=harness
                        )
                    self.assertEqual(rejected.exception.code, "docker_input_invalid")
            finally:
                listener.close()
                unix_socket.unlink(missing_ok=True)

    def test_create_command_is_pull_free_read_only_and_resource_bounded(self) -> None:
        with tempfile.TemporaryDirectory(prefix="docker-runtime-unit-") as temporary:
            root = Path(temporary).resolve()
            workspace = root / "workspace"
            harness = root / "harness"
            control = root / "control"
            input_file = root / "input.json"
            for directory in (workspace, harness, control):
                directory.mkdir()
            input_file.write_bytes(b"{}")
            spec = runtime.DockerRuntimeSpec(
                image=IMAGE,
                executable="/bin/sh",
                argv=("-c", "printf ok"),
                workspace=workspace,
                harness=harness,
                read_only_inputs=(input_file,),
                limits=_limits(),
            )
            prepared = runtime._PreparedInputs(
                spec=spec,
                docker=DOCKER,
                workspace=workspace,
                harness=harness,
                inputs=(input_file,),
                runtime_user="501:20",
                image_id=IMAGE_ID,
            )
            command = runtime._create_command(
                prepared,
                container_name="lrh-" + "a" * 32,
                network_id="b" * 64,
                nonce="a" * 32,
                control_directory=control,
            )

        def value(flag: str) -> str:
            return command[command.index(flag) + 1]

        self.assertEqual(command[:2], ["container", "create"])
        self.assertEqual(value("--pull"), "never")
        self.assertEqual(value("--platform"), "linux/arm64")
        self.assertIn("--interactive", command)
        self.assertIn("--read-only", command)
        self.assertEqual(value("--restart"), "no")
        self.assertEqual(value("--log-driver"), "none")
        self.assertEqual(value("--cgroupns"), "private")
        self.assertEqual(value("--ipc"), "private")
        self.assertEqual(value("--cap-drop"), "ALL")
        self.assertNotIn("--cap-add", command)
        self.assertEqual(value("--security-opt"), "no-new-privileges=true")
        self.assertEqual(value("--pids-limit"), "32")
        self.assertEqual(value("--memory"), str(128 * 1024 * 1024))
        self.assertEqual(value("--memory-swap"), str(128 * 1024 * 1024))
        self.assertEqual(value("--cpus"), "0.5")
        self.assertEqual(value("--network"), "b" * 64)
        self.assertEqual(value("--user"), "501:20")
        self.assertNotIn("--privileged", command)
        self.assertNotIn("--publish", command)
        self.assertNotIn("--volume", command)
        mounts = [command[index + 1] for index, item in enumerate(command[:-1]) if item == "--mount"]
        self.assertEqual(len(mounts), 4)
        self.assertTrue(all(",readonly" in mount for mount in mounts))
        tmpfs_values = [
            command[index + 1]
            for index, item in enumerate(command[:-1])
            if item == "--tmpfs"
        ]
        self.assertEqual(len(tmpfs_values), 2)
        self.assertTrue(
            any(
                item.startswith("/scratch:")
                and "size=1048576" in item
                and "nr_inodes=64" in item
                for item in tmpfs_values
            )
        )
        self.assertTrue(
            any(
                item.startswith("/dev/shm:")
                and "size=1048576" in item
                and "nr_inodes=32" in item
                for item in tmpfs_values
            )
        )
        image_index = command.index(IMAGE_ID)
        self.assertEqual(command[image_index + 1 :], ["-c", "printf ok"])
        self.assertNotIn(IMAGE, command)

    def test_write_broker_admission_is_bound_to_the_trusted_supervisor(self) -> None:
        digest = "sha256:" + "1" * 64
        trusted_argv = (
            runtime.SUPERVISOR_DESTINATION,
            "--session",
            f"{runtime.CONTROL_DESTINATION}/session.json",
            "--session-sha256",
            digest,
        )
        runtime._validate_supervisor_write_broker(
            enabled=True,
            executable="/usr/local/bin/python3",
            argv=trusted_argv,
        )
        invalid_commands = (
            ("/bin/sh", trusted_argv),
            ("/workspace/python3", trusted_argv),
            ("/harness/python3", trusted_argv),
            ("/usr/local/bin/python3", ("/tmp/not-supervisor.py", *trusted_argv[1:])),
            ("/usr/local/bin/python3", (*trusted_argv[:-1], "sha256:" + "g" * 64)),
        )
        for executable, argv in invalid_commands:
            with self.subTest(executable=executable, argv=argv):
                with self.assertRaises(runtime.DockerRuntimeError) as raised:
                    runtime._validate_supervisor_write_broker(
                        enabled=True,
                        executable=executable,
                        argv=argv,
                    )
                self.assertEqual(raised.exception.code, "docker_supervisor_profile_invalid")

        with tempfile.TemporaryDirectory(prefix="docker-supervisor-profile-") as temporary:
            root = Path(temporary).resolve()
            workspace = root / "workspace"
            harness = root / "harness"
            control = root / "control"
            for directory in (workspace, harness, control):
                directory.mkdir()
            spec = runtime.DockerRuntimeSpec(
                image=IMAGE,
                executable="/usr/local/bin/python3",
                argv=trusted_argv,
                workspace=workspace,
                harness=harness,
                limits=_limits(),
                supervisor_write_broker=True,
            )
            prepared = runtime._PreparedInputs(
                spec=spec,
                docker=DOCKER,
                workspace=workspace,
                harness=harness,
                inputs=(),
                runtime_user="501:20",
                image_id=IMAGE_ID,
            )
            command = runtime._create_command(
                prepared,
                container_name="lrh-" + "a" * 32,
                network_id="b" * 64,
                nonce="a" * 32,
                control_directory=control,
            )
        self.assertEqual(
            command[command.index("--cap-add") + 1],
            "SYS_PTRACE",
        )
        self.assertEqual(command[command.index("--cap-drop") + 1], "ALL")
        self.assertEqual(command.count("--cap-add"), 1)

    def test_public_result_summary_does_not_echo_output_or_exact_ids(self) -> None:
        result = runtime.DockerSessionResult(
            started=True,
            timed_out=False,
            interrupted=False,
            returncode=0,
            oom_killed=False,
            output_truncated=False,
            container_id="a" * 64,
            network_id="b" * 64,
            _stdout=b"potentially sensitive raw output",
        )
        summary = result.as_dict()
        self.assertEqual(result.stdout, b"potentially sensitive raw output")
        self.assertEqual(summary["output_bytes"], len(result.stdout))
        self.assertNotIn("stdout", summary)
        self.assertNotIn("container_id", summary)
        self.assertNotIn("network_id", summary)
        self.assertNotIn(b"potentially sensitive", json.dumps(summary).encode("utf-8"))


@unittest.skipUnless(
    RUN_DOCKER_INTEGRATION,
    "set HARNESS_RUN_DOCKER_INTEGRATION=1 to exercise the cached Docker image",
)
class DockerRuntimeIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if sys.platform != "darwin" or not DOCKER.is_file():
            raise unittest.SkipTest("Docker Desktop integration requires this Darwin host")
        image = _docker("image", "inspect", IMAGE, check=False)
        if image.returncode != 0:
            raise unittest.SkipTest("immutable Python image is not cached; test refuses to pull")
        values = json.loads(image.stdout)
        if (
            not isinstance(values, list)
            or len(values) != 1
            or not isinstance(values[0], dict)
            or IMAGE not in values[0].get("RepoDigests", [])
        ):
            raise unittest.SkipTest("cached image does not carry the required immutable RepoDigest")

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="docker-runtime-integration-")
        self.root = Path(self.temporary.name).resolve()
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def spec(
        self,
        script: str,
        *,
        read_only_inputs: tuple[Path, ...] = (),
        limits: runtime.DockerRuntimeLimits | None = None,
    ) -> runtime.DockerRuntimeSpec:
        return runtime.DockerRuntimeSpec(
            image=IMAGE,
            executable="/bin/sh",
            argv=("-c", script),
            workspace=self.workspace,
            harness=HARNESS,
            read_only_inputs=read_only_inputs,
            limits=limits or _limits(),
            docker_executable=DOCKER,
        )

    def assert_cleaned(self, container_id: str, network_id: str, control: Path) -> None:
        self.assertTrue(_is_absent("container", container_id))
        self.assertTrue(_is_absent("network", network_id))
        self.assertFalse(control.exists())

    def test_two_phase_identity_control_injection_and_exact_cleanup(self) -> None:
        input_file = self.root / "input.txt"
        input_file.write_bytes(b"input-ok")
        prepared = runtime.prepare_docker_session(
            self.spec(
                "if touch /workspace/must-not-write 2>/dev/null; then exit 91; fi; "
                "test \"$(stat -c %u /run/lrh-control/manifest.json)\" = \"$(id -u)\" || exit 93; "
                "test \"$(stat -c %a /run/lrh-control/manifest.json)\" = 400 || exit 94; "
                "IFS= read -r stdin_value || exit 95; "
                "cat /run/lrh-control/manifest.json /inputs/000 || exit 92; "
                "printf ':runtime-ok:%s' \"$stdin_value\"",
                read_only_inputs=(input_file,),
            )
        )
        identity = prepared.identity
        self.assertRegex(identity.container_id, r"^[0-9a-f]{64}$")
        self.assertRegex(identity.network_id, r"^[0-9a-f]{64}$")
        self.assertRegex(identity.config_digest, r"^sha256:[0-9a-f]{64}$")
        inspected = _inspect("container", identity.container_id)
        self.assertEqual(inspected["State"]["Status"], "created")
        self.assertIs(inspected["State"]["Running"], False)
        self.assertEqual(identity.mount_manifest["/workspace"], str(self.workspace))
        with self.assertRaises(TypeError):
            identity.mount_manifest["/workspace"] = "/tampered"  # type: ignore[index]

        manifest = json.dumps(
            {
                "container_id": identity.container_id,
                "container_config_digest": identity.config_digest,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        prepared.write_control_file("manifest.json", manifest)
        mode = stat.S_IMODE((identity.control_directory / "manifest.json").stat().st_mode)
        self.assertEqual(mode, 0o400)
        callbacks: list[runtime.DockerSessionIdentity] = []

        def on_release(current: runtime.DockerSessionIdentity) -> None:
            callbacks.append(current)
            state = _inspect("container", current.container_id)["State"]
            self.assertIsInstance(state, dict)
            self.assertIs(state["Running"], False)

        result = prepared.start(
            timeout_seconds=5.0,
            on_process_started=on_release,
            stdin_bytes=b"stdin-ok\n",
        )
        self.assertEqual(callbacks, [identity])
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, manifest + b"input-ok:runtime-ok:stdin-ok")
        self.assertFalse(result.output_truncated)
        self.assert_cleaned(identity.container_id, identity.network_id, identity.control_directory)

    def test_stopped_manifest_is_revalidated_and_callback_failure_cleans(self) -> None:
        prepared = runtime.prepare_docker_session(self.spec("printf never-ran"))
        identity = prepared.identity
        _docker("container", "rename", identity.container_id, "lrh-tampered-" + uuid.uuid4().hex)
        with self.assertRaises(runtime.DockerRuntimeError) as raised:
            prepared.start(timeout_seconds=5.0)
        self.assertEqual(raised.exception.code, "docker_container_manifest_mismatch")
        self.assert_cleaned(identity.container_id, identity.network_id, identity.control_directory)

        callback_prepared = runtime.prepare_docker_session(self.spec("printf never-ran"))
        callback_identity = callback_prepared.identity

        def reject(_identity: runtime.DockerSessionIdentity) -> None:
            raise LookupError("broker activation rejected")

        with self.assertRaisesRegex(LookupError, "broker activation rejected"):
            callback_prepared.start(timeout_seconds=5.0, on_process_started=reject)
        self.assert_cleaned(
            callback_identity.container_id,
            callback_identity.network_id,
            callback_identity.control_directory,
        )

    def test_any_pre_gate_execution_is_rejected(self) -> None:
        prepared = runtime.prepare_docker_session(self.spec("exit 0"))
        identity = prepared.identity
        _docker("container", "start", identity.container_id)
        _docker("container", "wait", identity.container_id)
        state = _inspect("container", identity.container_id)["State"]
        self.assertEqual(state["Status"], "exited")
        with self.assertRaises(runtime.DockerRuntimeError) as raised:
            prepared.start(timeout_seconds=5.0)
        self.assertEqual(raised.exception.code, "docker_container_manifest_mismatch")
        self.assert_cleaned(identity.container_id, identity.network_id, identity.control_directory)

    def test_timeout_kills_exact_container_and_output_is_bounded(self) -> None:
        prepared = runtime.prepare_docker_session(self.spec(EVASIVE_HOLD_SCRIPT))
        identity = prepared.identity
        started = time.monotonic()
        result = prepared.start(timeout_seconds=2.0)
        self.assertLess(time.monotonic() - started, 10.0)
        self.assertTrue(result.timed_out)
        self.assertFalse(result.interrupted)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"evader-ready\n")
        self.assert_cleaned(identity.container_id, identity.network_id, identity.control_directory)

        interrupt_prepared = runtime.prepare_docker_session(
            self.spec(EVASIVE_HOLD_SCRIPT)
        )
        interrupt_identity = interrupt_prepared.identity
        interrupt_deadline = time.monotonic() + 2.0
        interrupted = interrupt_prepared.start(
            timeout_seconds=5.0,
            stop_requested=lambda: time.monotonic() >= interrupt_deadline,
        )
        self.assertTrue(interrupted.interrupted)
        self.assertFalse(interrupted.timed_out)
        self.assertNotEqual(interrupted.returncode, 0)
        self.assertEqual(interrupted.stdout, b"evader-ready\n")
        self.assert_cleaned(
            interrupt_identity.container_id,
            interrupt_identity.network_id,
            interrupt_identity.control_directory,
        )

        output_prepared = runtime.prepare_docker_session(
            self.spec("head -c 1200000 /dev/zero | tr '\\000' x")
        )
        output_identity = output_prepared.identity
        output = output_prepared.start(timeout_seconds=10.0)
        self.assertEqual(output.returncode, 0)
        self.assertTrue(output.output_truncated)
        self.assertEqual(len(output.stdout), runtime.MAX_RUNTIME_OUTPUT_BYTES)
        self.assertEqual(set(output.stdout), {ord("x")})
        self.assert_cleaned(
            output_identity.container_id,
            output_identity.network_id,
            output_identity.control_directory,
        )

    def test_close_fd_double_fork_setsid_chdir_exec_cannot_survive(self) -> None:
        script = EVASIVE_LAUNCH_SCRIPT + "\nprintf 'evader-ready\\n'\n"
        prepared = runtime.prepare_docker_session(self.spec(script))
        identity = prepared.identity
        started = time.monotonic()
        result = prepared.start(timeout_seconds=5.0)
        self.assertLess(time.monotonic() - started, 5.0)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"evader-ready\n")
        self.assert_cleaned(identity.container_id, identity.network_id, identity.control_directory)

    def test_tmpfs_byte_inode_and_sparse_accounting_are_bounded(self) -> None:
        script = r"""
            set -u
            if ! dd if=/dev/zero of=/scratch/sparse bs=1 count=0 seek=1073741824 2>/dev/null; then
              exit 21
            fi
            sparse_size=$(stat -c %s /scratch/sparse)
            if dd if=/dev/zero of=/scratch/fill bs=65536 count=32 2>/dev/null; then
              byte_result=unbounded
            else
              byte_result=blocked
            fi
            rm -f /scratch/sparse /scratch/fill
            inode_count=0
            while [ "$inode_count" -lt 256 ]; do
              if ! /bin/touch "/scratch/inode-${inode_count}" 2>/dev/null; then
                break
              fi
              inode_count=$((inode_count + 1))
            done
            printf 'sparse=%s byte=%s inodes=%s' "$sparse_size" "$byte_result" "$inode_count"
            [ "$sparse_size" = 1073741824 ]
            [ "$byte_result" = blocked ]
            [ "$inode_count" -lt 256 ]
        """
        prepared = runtime.prepare_docker_session(self.spec(script))
        identity = prepared.identity
        result = prepared.start(timeout_seconds=10.0)
        self.assertEqual(result.returncode, 0, result.stdout)
        fields = dict(item.split("=", 1) for item in result.stdout.decode("ascii").split())
        self.assertEqual(fields["sparse"], "1073741824")
        self.assertEqual(fields["byte"], "blocked")
        self.assertLess(int(fields["inodes"]), 256)
        self.assert_cleaned(identity.container_id, identity.network_id, identity.control_directory)

    def test_parent_sigkill_triggers_watchdog_and_unrelated_canary_survives(self) -> None:
        canary_name = "lrh-unrelated-canary-" + uuid.uuid4().hex
        canary_result = _docker(
            "container",
            "create",
            "--pull",
            "never",
            "--platform",
            "linux/arm64",
            "--network",
            "none",
            "--log-driver",
            "none",
            "--restart",
            "no",
            "--name",
            canary_name,
            "--entrypoint",
            "/bin/sleep",
            IMAGE_ID,
            "60",
        )
        canary_id = canary_result.stdout.decode("ascii").strip()
        _docker("container", "start", canary_id)
        child: subprocess.Popen[bytes] | None = None
        identity: dict[str, str] | None = None
        try:
            identity_file = self.root / "child-identity.json"
            child_program = self.root / "parent-death-child.py"
            child_program.write_text(
                """
import json
import pathlib
import sys

sys.path.insert(0, sys.argv[1])
from docker_session_runtime import DockerRuntimeLimits, DockerRuntimeSpec, prepare_docker_session

spec = DockerRuntimeSpec(
    image=sys.argv[2],
    executable='/bin/sh',
    argv=('-c', __EVASIVE_SCRIPT__),
    workspace=pathlib.Path(sys.argv[3]),
    harness=pathlib.Path(sys.argv[4]),
    docker_executable=pathlib.Path(sys.argv[5]),
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
prepared = prepare_docker_session(spec)
pathlib.Path(sys.argv[6]).write_text(json.dumps({
    'container_id': prepared.identity.container_id,
    'network_id': prepared.identity.network_id,
    'control_directory': str(prepared.identity.control_directory),
}), encoding='utf-8')
prepared.start(timeout_seconds=60.0)
""".replace("__EVASIVE_SCRIPT__", repr(EVASIVE_HOLD_SCRIPT)).lstrip(),
                encoding="utf-8",
            )
            child = subprocess.Popen(
                [
                    sys.executable,
                    str(child_program),
                    str(TOOLS),
                    IMAGE,
                    str(self.workspace),
                    str(HARNESS),
                    str(DOCKER),
                    str(identity_file),
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )
            deadline = time.monotonic() + 15.0
            while time.monotonic() < deadline and identity is None:
                if child.poll() is not None:
                    stdout, stderr = child.communicate()
                    self.fail(
                        "parent-death fixture exited early: "
                        + (stdout + stderr)[:4096].decode("utf-8", errors="replace")
                    )
                try:
                    loaded = json.loads(identity_file.read_text(encoding="utf-8"))
                except (FileNotFoundError, json.JSONDecodeError):
                    time.sleep(0.05)
                    continue
                if isinstance(loaded, dict) and all(
                    isinstance(loaded.get(key), str)
                    for key in ("container_id", "network_id", "control_directory")
                ):
                    identity = loaded
            self.assertIsNotNone(identity, "child did not expose its exact prepared identity")
            assert identity is not None
            _wait_container_running(identity["container_id"])
            readiness_deadline = time.monotonic() + 10.0
            while time.monotonic() < readiness_deadline:
                ready = _docker(
                    "container",
                    "exec",
                    identity["container_id"],
                    "/bin/sh",
                    "-c",
                    f"test -f {EVASIVE_READY_PATH}",
                    check=False,
                    timeout=5.0,
                )
                if ready.returncode == 0:
                    break
                if child.poll() is not None:
                    stdout, stderr = child.communicate()
                    self.fail(
                        "parent-death fixture exited before evader readiness: "
                        + (stdout + stderr)[:4096].decode("utf-8", errors="replace")
                    )
                time.sleep(0.05)
            else:
                state = _docker(
                    "container", "inspect", identity["container_id"], check=False
                )
                self.fail(
                    "detached evader did not reach its post-setsid/post-exec barrier: "
                    f"exec={ready.stderr[:1024].decode('utf-8', errors='replace')!r} "
                    f"inspect={state.stderr[:1024].decode('utf-8', errors='replace')!r} "
                    f"child_returncode={child.poll()!r}"
                )

            child.kill()
            child.wait(timeout=5.0)
            child.communicate(timeout=2.0)
            child = None
            _wait_absent("container", identity["container_id"])
            _wait_absent("network", identity["network_id"])
            _wait_path_absent(Path(identity["control_directory"]))

            canary = _inspect("container", canary_id)
            self.assertEqual(canary["Id"], canary_id)
            self.assertIs(canary["State"]["Running"], True)
        finally:
            if child is not None:
                if child.poll() is None:
                    child.kill()
                    child.wait(timeout=5.0)
                child.communicate(timeout=2.0)
            _docker("container", "rm", "--force", "--volumes", canary_id, check=False)


if __name__ == "__main__":
    unittest.main(verbosity=2)
