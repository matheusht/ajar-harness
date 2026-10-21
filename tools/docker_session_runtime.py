#!/usr/bin/env python3
"""Exact-ID Docker session boundary for one untrusted runtime process.

This module deliberately owns only the OS/runtime boundary.  The caller owns semantic admission,
the record broker, and interpretation of the bounded stdout prefix.  Preparation is two phase:

1. :func:`prepare_docker_session` creates and revalidates a stopped container and its private
   network, binds a private control directory, and arms an independent parent-lifetime watchdog.
2. The caller writes bounded control files, activates its broker using the returned immutable
   identity, and calls :meth:`PreparedDockerSession.start` to release the container.

No image is pulled or built.  Cleanup addresses only the exact container and network IDs after
checking a random ownership nonce; it never scans processes, containers, or same-UID resources.
"""

from __future__ import annotations

import json
import hashlib
import math
import os
import re
import select
import stat
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Callable, Mapping, Sequence


MAX_DOCKER_OUTPUT_BYTES = 2 * 1024 * 1024
MAX_RUNTIME_OUTPUT_BYTES = 1024 * 1024
MAX_CONTROL_FILES = 16
MAX_CONTROL_FILE_BYTES = 512 * 1024
MAX_CONTROL_TOTAL_BYTES = 1024 * 1024
DOCKER_COMMAND_TIMEOUT_SECONDS = 15.0
WATCHDOG_READY_TIMEOUT_SECONDS = 10.0
WATCHDOG_EXIT_TIMEOUT_SECONDS = 15.0
CONTAINER_STOP_TIMEOUT_SECONDS = 10.0
POLL_SECONDS = 0.025

OWNER_LABEL = "io.llm-redteam-harness.runtime"
NONCE_LABEL = "io.llm-redteam-harness.session-nonce"
OWNER_LABEL_VALUE = "docker-session-v1"
CONTROL_DESTINATION = "/run/lrh-control"
WORKSPACE_DESTINATION = "/workspace"
HARNESS_DESTINATION = "/harness"
SUPERVISOR_DESTINATION = f"{HARNESS_DESTINATION}/tools/container_session_supervisor.py"
SCRATCH_DESTINATION = "/scratch"
SHM_DESTINATION = "/dev/shm"
_ID_RE = re.compile(r"^[0-9a-f]{64}$")
_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_CONTROL_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class DockerRuntimeError(RuntimeError):
    """A Docker boundary could not be established or cleaned safely."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class DockerRuntimeLimits:
    """Finite per-session resource limits enforced by Docker/cgroup/tmpfs."""

    memory_bytes: int = 2 * 1024 * 1024 * 1024
    cpu_count: float = 2.0
    pids: int = 128
    nofile: int = 1024
    scratch_bytes: int = 256 * 1024 * 1024
    scratch_inodes: int = 16_384
    shm_bytes: int = 16 * 1024 * 1024
    shm_inodes: int = 1024

    def validate(self) -> None:
        integer_bounds = (
            (self.memory_bytes, 128 * 1024 * 1024, 16 * 1024 * 1024 * 1024),
            (self.pids, 16, 4096),
            (self.nofile, 64, 65_536),
            (self.scratch_bytes, 1024 * 1024, 4 * 1024 * 1024 * 1024),
            (self.scratch_inodes, 32, 1_000_000),
            (self.shm_bytes, 1024 * 1024, 1024 * 1024 * 1024),
            (self.shm_inodes, 32, 1_000_000),
        )
        if any(type(value) is not int or not low <= value <= high for value, low, high in integer_bounds):
            raise DockerRuntimeError("docker_limits_invalid")
        if (
            not isinstance(self.cpu_count, (int, float))
            or isinstance(self.cpu_count, bool)
            or not math.isfinite(float(self.cpu_count))
            or not 0.1 <= float(self.cpu_count) <= 64.0
        ):
            raise DockerRuntimeError("docker_limits_invalid")


@dataclass(frozen=True)
class DockerRuntimeSpec:
    """Immutable preparation inputs for one containerized executable."""

    image: str
    executable: str
    argv: tuple[str, ...]
    workspace: Path
    harness: Path
    read_only_inputs: tuple[Path, ...] = ()
    limits: DockerRuntimeLimits = field(default_factory=DockerRuntimeLimits)
    docker_executable: Path = Path("/usr/local/bin/docker")
    network_internal: bool = False
    runtime_user: str | None = None
    supervisor_write_broker: bool = False


@dataclass(frozen=True)
class DockerSessionIdentity:
    container_id: str
    container_name: str
    network_id: str
    network_name: str
    nonce: str
    config_digest: str
    control_directory: Path
    mount_manifest: Mapping[str, str]


@dataclass(frozen=True)
class DockerSessionResult:
    """Sanitized execution summary plus a bounded stdout prefix for the caller's parser."""

    started: bool
    timed_out: bool
    interrupted: bool
    returncode: int | None
    oom_killed: bool
    output_truncated: bool
    container_id: str
    network_id: str
    _stdout: bytes = field(repr=False)

    @property
    def stdout(self) -> bytes:
        return self._stdout

    def as_dict(self) -> dict[str, object]:
        return {
            "started": self.started,
            "timed_out": self.timed_out,
            "interrupted": self.interrupted,
            "returncode": self.returncode,
            "oom_killed": self.oom_killed,
            "output_truncated": self.output_truncated,
            "output_bytes": len(self._stdout),
        }


@dataclass(frozen=True)
class _PreparedInputs:
    spec: DockerRuntimeSpec
    docker: Path
    workspace: Path
    harness: Path
    inputs: tuple[Path, ...]
    runtime_user: str
    image_id: str


class _BoundedPipeCapture:
    def __init__(self, stream: object, *, retain: bool) -> None:
        self._stream = stream
        self._retain = retain
        self._captured = bytearray()
        self._total = 0
        self._thread = threading.Thread(target=self._drain, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def _drain(self) -> None:
        read = getattr(self._stream, "read")
        while True:
            try:
                chunk = read(64 * 1024)
            except OSError:
                return
            if not chunk:
                return
            self._total += len(chunk)
            if self._retain and len(self._captured) < MAX_RUNTIME_OUTPUT_BYTES:
                remaining = MAX_RUNTIME_OUTPUT_BYTES - len(self._captured)
                self._captured.extend(chunk[:remaining])

    def finish(self) -> None:
        self._thread.join(timeout=5.0)
        if self._thread.is_alive():
            raise DockerRuntimeError("docker_output_drain_failed")
        try:
            close = getattr(self._stream, "close")
            close()
        except OSError:
            pass

    @property
    def value(self) -> bytes:
        return bytes(self._captured)

    @property
    def truncated(self) -> bool:
        return self._total > MAX_RUNTIME_OUTPUT_BYTES


def _docker_environment() -> dict[str, str]:
    allowed = {"HOME", "PATH", "DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_CONFIG"}
    result = {key: value for key, value in os.environ.items() if key in allowed and value}
    result.setdefault("PATH", "/usr/local/bin:/usr/bin:/bin")
    result["PYTHONDONTWRITEBYTECODE"] = "1"
    return result


def _run_docker(
    docker: Path,
    arguments: Sequence[str],
    *,
    timeout: float = DOCKER_COMMAND_TIMEOUT_SECONDS,
    allow_failure: bool = False,
    pass_fds: tuple[int, ...] = (),
) -> subprocess.CompletedProcess[bytes]:
    try:
        result = subprocess.run(
            [str(docker), *arguments],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=_docker_environment(),
            timeout=timeout,
            check=False,
            pass_fds=pass_fds,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DockerRuntimeError("docker_command_unavailable") from exc
    if len(result.stdout) > MAX_DOCKER_OUTPUT_BYTES or len(result.stderr) > MAX_DOCKER_OUTPUT_BYTES:
        raise DockerRuntimeError("docker_command_output_oversize")
    if result.returncode != 0 and not allow_failure:
        raise DockerRuntimeError("docker_command_failed")
    return result


def _json_object(raw: bytes, *, code: str) -> dict[str, object]:
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise DockerRuntimeError(code) from exc
    if not isinstance(value, dict):
        raise DockerRuntimeError(code)
    return value


def _inspect_one(docker: Path, kind: str, identifier: str) -> dict[str, object]:
    result = _run_docker(docker, [kind, "inspect", identifier])
    try:
        values = json.loads(result.stdout)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise DockerRuntimeError("docker_inspect_invalid") from exc
    if not isinstance(values, list) or len(values) != 1 or not isinstance(values[0], dict):
        raise DockerRuntimeError("docker_inspect_invalid")
    return values[0]


def _is_absent(docker: Path, kind: str, identifier: str) -> bool:
    result = _run_docker(docker, [kind, "inspect", identifier], allow_failure=True)
    if result.returncode == 0:
        return False
    lowered = result.stderr.lower()
    encoded_id = identifier.encode("ascii")
    expected = (
        (b"no such container: " + encoded_id, b"no such object: " + encoded_id)
        if kind == "container"
        else (b"no such network: " + encoded_id, b"network " + encoded_id + b" not found")
    )
    if not any(message in lowered for message in expected):
        raise DockerRuntimeError("docker_cleanup_unverifiable")
    # A 404-like CLI result is meaningful only while the engine itself still answers.
    _run_docker(docker, ["info", "--format", "{{json .ServerVersion}}"])
    return True


def _validate_id(value: object, *, code: str) -> str:
    if not isinstance(value, str) or _ID_RE.fullmatch(value) is None:
        raise DockerRuntimeError(code)
    return value


def _validate_image_reference(image: str) -> tuple[str, str]:
    if not isinstance(image, str) or any(character.isspace() for character in image):
        raise DockerRuntimeError("docker_image_unpinned")
    repository, marker, digest = image.rpartition("@sha256:")
    if marker != "@sha256:" or not repository or _ID_RE.fullmatch(digest) is None or "@" in repository:
        raise DockerRuntimeError("docker_image_unpinned")
    # A registry port is legal; a tag on the final repository component is not.
    if ":" in repository.rsplit("/", 1)[-1]:
        raise DockerRuntimeError("docker_image_unpinned")
    return repository, digest


def _canonical_path(path: Path, *, directory: bool | None, code: str) -> Path:
    try:
        supplied = Path(path)
    except (TypeError, ValueError) as exc:
        raise DockerRuntimeError(code) from exc
    if not supplied.is_absolute() or "\x00" in os.fspath(supplied):
        raise DockerRuntimeError(code)
    try:
        canonical = supplied.resolve(strict=True)
        entry = canonical.stat(follow_symlinks=False)
    except (OSError, RuntimeError) as exc:
        raise DockerRuntimeError(code) from exc
    if Path(os.path.abspath(supplied)) != canonical:
        raise DockerRuntimeError(code)
    if directory is True and not stat.S_ISDIR(entry.st_mode):
        raise DockerRuntimeError(code)
    if directory is False and not stat.S_ISREG(entry.st_mode):
        raise DockerRuntimeError(code)
    if "," in os.fspath(canonical) or "\n" in os.fspath(canonical):
        raise DockerRuntimeError(code)
    return canonical


def _paths_overlap(first: Path, second: Path) -> bool:
    return (
        first == second
        or first.is_relative_to(second)
        or second.is_relative_to(first)
    )


def _validate_read_only_inputs(
    values: Sequence[Path], *, workspace: Path, harness: Path
) -> tuple[Path, ...]:
    """Admit only distinct regular files outside the two fixed directory mounts."""

    if isinstance(values, (str, bytes, os.PathLike)) or not isinstance(values, Sequence):
        raise DockerRuntimeError("docker_input_invalid")
    inputs = tuple(
        _canonical_path(Path(value), directory=False, code="docker_input_invalid")
        for value in values
    )
    if len(inputs) > 32 or len(set(inputs)) != len(inputs):
        raise DockerRuntimeError("docker_input_invalid")
    identities: set[tuple[int, int]] = set()
    for source in inputs:
        if _paths_overlap(source, workspace) or _paths_overlap(source, harness):
            raise DockerRuntimeError("docker_mount_overlap")
        try:
            entry = source.stat(follow_symlinks=False)
        except OSError as exc:
            raise DockerRuntimeError("docker_input_invalid") from exc
        identity = (entry.st_dev, entry.st_ino)
        if identity in identities:
            raise DockerRuntimeError("docker_input_invalid")
        identities.add(identity)
    return inputs


def _validate_runtime_text(executable: str, argv: Sequence[str]) -> tuple[str, tuple[str, ...]]:
    if (
        not isinstance(executable, str)
        or not executable.startswith("/")
        or "\x00" in executable
        or len(executable) > 4096
    ):
        raise DockerRuntimeError("docker_runtime_command_invalid")
    if isinstance(argv, (str, bytes)) or not isinstance(argv, Sequence) or len(argv) > 1024:
        raise DockerRuntimeError("docker_runtime_command_invalid")
    frozen = tuple(argv)
    if any(not isinstance(value, str) or "\x00" in value or len(value) > 128 * 1024 for value in frozen):
        raise DockerRuntimeError("docker_runtime_command_invalid")
    return executable, frozen


def _validate_supervisor_write_broker(
    *, enabled: object, executable: str, argv: tuple[str, ...]
) -> None:
    """Bind the pidfd/seccomp admission to the one trusted supervisor command shape."""

    if type(enabled) is not bool:
        raise DockerRuntimeError("docker_runtime_config_invalid")
    if not enabled:
        return
    disallowed_executable_roots = (
        WORKSPACE_DESTINATION,
        SCRATCH_DESTINATION,
        SHM_DESTINATION,
        "/inputs",
        CONTROL_DESTINATION,
        HARNESS_DESTINATION,
    )
    if (
        re.fullmatch(r"python(?:3(?:\.[0-9]+)?)?", Path(executable).name) is None
        or any(
            executable == root or executable.startswith(root + "/")
            for root in disallowed_executable_roots
        )
        or len(argv) != 5
        or argv[0] != SUPERVISOR_DESTINATION
        or argv[1] != "--session"
        or argv[2] != f"{CONTROL_DESTINATION}/session.json"
        or argv[3] != "--session-sha256"
        or _SHA256_RE.fullmatch(argv[4]) is None
    ):
        raise DockerRuntimeError("docker_supervisor_profile_invalid")


def _resolve_docker(path: Path) -> Path:
    try:
        supplied = Path(path)
    except (TypeError, ValueError) as exc:
        raise DockerRuntimeError("docker_runtime_unavailable") from exc
    if not supplied.is_absolute():
        raise DockerRuntimeError("docker_runtime_unavailable")
    try:
        resolved = supplied.resolve(strict=True)
        entry = resolved.stat(follow_symlinks=False)
    except (OSError, RuntimeError) as exc:
        raise DockerRuntimeError("docker_runtime_unavailable") from exc
    if (
        not stat.S_ISREG(entry.st_mode)
        or entry.st_uid not in {0, os.getuid()}
        or stat.S_IMODE(entry.st_mode) & 0o022
        or not os.access(resolved, os.X_OK)
    ):
        raise DockerRuntimeError("docker_runtime_unavailable")
    return resolved


def _validate_local_docker_endpoint(docker: Path) -> None:
    configured_host = os.environ.get("DOCKER_HOST")
    if configured_host:
        host = configured_host
    else:
        context = _json_object(
            _run_docker(docker, ["context", "inspect", "--format", "{{json .}}"]).stdout,
            code="docker_preflight_invalid",
        )
        endpoints = context.get("Endpoints")
        endpoint = endpoints.get("docker") if isinstance(endpoints, dict) else None
        host = endpoint.get("Host") if isinstance(endpoint, dict) else None
    if not isinstance(host, str) or not host.startswith("unix://"):
        raise DockerRuntimeError("docker_preflight_invalid")
    socket_text = host.removeprefix("unix://")
    if not socket_text.startswith("/") or any(value in socket_text for value in ("\x00", "\n", "?", "#")):
        raise DockerRuntimeError("docker_preflight_invalid")
    try:
        socket_path = Path(socket_text).resolve(strict=True)
        entry = socket_path.stat(follow_symlinks=False)
    except (OSError, RuntimeError) as exc:
        raise DockerRuntimeError("docker_preflight_invalid") from exc
    if (
        not stat.S_ISSOCK(entry.st_mode)
        or entry.st_uid not in {0, os.getuid()}
        or stat.S_IMODE(entry.st_mode) & 0o022
    ):
        raise DockerRuntimeError("docker_preflight_invalid")


def _preflight(spec: DockerRuntimeSpec) -> _PreparedInputs:
    if not isinstance(spec, DockerRuntimeSpec):
        raise DockerRuntimeError("docker_runtime_config_invalid")
    if type(spec.network_internal) is not bool:
        raise DockerRuntimeError("docker_runtime_config_invalid")
    if not isinstance(spec.limits, DockerRuntimeLimits):
        raise DockerRuntimeError("docker_limits_invalid")
    spec.limits.validate()
    _repository, requested_digest = _validate_image_reference(spec.image)
    executable, argv = _validate_runtime_text(spec.executable, spec.argv)
    _validate_supervisor_write_broker(
        enabled=spec.supervisor_write_broker,
        executable=executable,
        argv=argv,
    )
    if sys.platform != "darwin" or os.getuid() == 0:
        raise DockerRuntimeError("docker_runtime_unsupported")
    docker = _resolve_docker(spec.docker_executable)
    _validate_local_docker_endpoint(docker)
    workspace = _canonical_path(spec.workspace, directory=True, code="docker_workspace_invalid")
    harness = _canonical_path(spec.harness, directory=True, code="docker_harness_invalid")
    if _paths_overlap(workspace, harness):
        raise DockerRuntimeError("docker_mount_overlap")
    inputs = _validate_read_only_inputs(
        spec.read_only_inputs,
        workspace=workspace,
        harness=harness,
    )
    runtime_user = f"{os.getuid()}:{os.getgid()}" if spec.runtime_user is None else spec.runtime_user
    if not isinstance(runtime_user, str) or re.fullmatch(r"[1-9][0-9]{0,9}:[0-9]{1,10}", runtime_user) is None:
        raise DockerRuntimeError("docker_runtime_user_invalid")

    version_result = _run_docker(docker, ["version", "--format", "{{json .}}"])
    version = _json_object(version_result.stdout, code="docker_preflight_invalid")
    client = version.get("Client")
    server = version.get("Server")
    platform = server.get("Platform") if isinstance(server, dict) else None
    if (
        not isinstance(client, dict)
        or client.get("Os") != "darwin"
        or client.get("Arch") != "arm64"
        or not isinstance(server, dict)
        or server.get("Os") != "linux"
        or server.get("Arch") != "arm64"
        or not isinstance(platform, dict)
        or not str(platform.get("Name", "")).startswith("Docker Desktop")
    ):
        raise DockerRuntimeError("docker_preflight_invalid")

    info_result = _run_docker(docker, ["info", "--format", "{{json .}}"])
    info = _json_object(info_result.stdout, code="docker_preflight_invalid")
    security = info.get("SecurityOptions")
    if (
        info.get("OperatingSystem") != "Docker Desktop"
        or info.get("OSType") != "linux"
        or info.get("Architecture") not in {"aarch64", "arm64"}
        or info.get("CgroupVersion") != "2"
        or info.get("MemoryLimit") is not True
        or info.get("SwapLimit") is not True
        or info.get("PidsLimit") is not True
        or info.get("LiveRestoreEnabled") is not False
        or not isinstance(security, list)
        or "name=seccomp,profile=builtin" not in security
    ):
        raise DockerRuntimeError("docker_preflight_invalid")

    image_result = _run_docker(
        docker, ["image", "inspect", "--", spec.image], allow_failure=True
    )
    if image_result.returncode != 0:
        # Docker Desktop's containerd image store may retain the verified RepoDigest while resolving
        # only the exact local image ID. This remains non-enumerating and immutable: inspect that
        # single digest-derived ID, then require the requested repo@digest below.
        image_result = _run_docker(
            docker,
            ["image", "inspect", "--", f"sha256:{requested_digest}"],
            allow_failure=True,
        )
    if image_result.returncode != 0:
        raise DockerRuntimeError("docker_image_unavailable")
    try:
        images = json.loads(image_result.stdout)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise DockerRuntimeError("docker_image_unavailable") from exc
    if not isinstance(images, list) or len(images) != 1 or not isinstance(images[0], dict):
        raise DockerRuntimeError("docker_image_unavailable")
    image = images[0]
    repo_digests = image.get("RepoDigests")
    image_id = image.get("Id")
    if (
        image.get("Os") != "linux"
        or image.get("Architecture") != "arm64"
        or not isinstance(repo_digests, list)
        or spec.image not in repo_digests
        or not isinstance(image_id, str)
        or not image_id.startswith("sha256:")
        or _ID_RE.fullmatch(image_id.removeprefix("sha256:")) is None
    ):
        raise DockerRuntimeError("docker_image_invalid")
    normalized_spec = DockerRuntimeSpec(
        image=spec.image,
        executable=executable,
        argv=argv,
        workspace=workspace,
        harness=harness,
        read_only_inputs=inputs,
        limits=spec.limits,
        docker_executable=docker,
        network_internal=spec.network_internal,
        runtime_user=runtime_user,
        supervisor_write_broker=spec.supervisor_write_broker,
    )
    return _PreparedInputs(
        normalized_spec,
        docker,
        workspace,
        harness,
        inputs,
        runtime_user,
        image_id,
    )


def _mount_argument(source: Path, destination: str) -> str:
    suffix = ",bind-propagation=rprivate,bind-recursive=readonly" if source.is_dir() else ""
    return f"type=bind,src={source},dst={destination},readonly{suffix}"


def _create_command(
    prepared: _PreparedInputs,
    *,
    container_name: str,
    network_id: str,
    nonce: str,
    control_directory: Path,
) -> list[str]:
    spec = prepared.spec
    limits = spec.limits
    uid, gid = prepared.runtime_user.split(":", 1)
    command = [
        "container",
        "create",
        "--name",
        container_name,
        "--pull",
        "never",
        "--platform",
        "linux/arm64",
        "--interactive",
        "--read-only",
        "--restart",
        "no",
        "--log-driver",
        "none",
        "--stop-timeout",
        "0",
        "--cgroupns",
        "private",
        "--ipc",
        "private",
        "--cap-drop",
        "ALL",
        *(
            ["--cap-add", "SYS_PTRACE"]
            if spec.supervisor_write_broker
            else []
        ),
        "--security-opt",
        "no-new-privileges=true",
        "--pids-limit",
        str(limits.pids),
        "--memory",
        str(limits.memory_bytes),
        "--memory-swap",
        str(limits.memory_bytes),
        "--memory-swappiness",
        "0",
        "--cpus",
        format(float(limits.cpu_count), ".6g"),
        "--ulimit",
        f"nofile={limits.nofile}:{limits.nofile}",
        "--ulimit",
        "core=0:0",
        "--shm-size",
        str(limits.shm_bytes),
        "--tmpfs",
        (
            f"{SCRATCH_DESTINATION}:rw,nosuid,nodev,size={limits.scratch_bytes},"
            f"nr_inodes={limits.scratch_inodes},mode=0700,uid={uid},gid={gid}"
        ),
        "--tmpfs",
        (
            f"{SHM_DESTINATION}:rw,nosuid,nodev,noexec,size={limits.shm_bytes},"
            f"nr_inodes={limits.shm_inodes},mode=1777"
        ),
        "--network",
        network_id,
        "--user",
        prepared.runtime_user,
        "--hostname",
        "lrh-session",
        "--no-healthcheck",
        "--label",
        f"{OWNER_LABEL}={OWNER_LABEL_VALUE}",
        "--label",
        f"{NONCE_LABEL}={nonce}",
        "--env",
        f"HOME={SCRATCH_DESTINATION}",
        "--env",
        f"TMPDIR={SCRATCH_DESTINATION}",
        "--env",
        f"TMP={SCRATCH_DESTINATION}",
        "--env",
        f"TEMP={SCRATCH_DESTINATION}",
        "--env",
        f"HARNESS_DRIVER_SCRATCH={SCRATCH_DESTINATION}",
        "--env",
        f"HARNESS_RUNTIME_CONTROL={CONTROL_DESTINATION}",
        "--mount",
        _mount_argument(prepared.workspace, WORKSPACE_DESTINATION),
        "--mount",
        _mount_argument(prepared.harness, HARNESS_DESTINATION),
        "--mount",
        _mount_argument(control_directory, CONTROL_DESTINATION),
    ]
    for index, source in enumerate(prepared.inputs):
        command.extend(["--mount", _mount_argument(source, f"/inputs/{index:03d}")])
    command.extend(
        [
            "--workdir",
            WORKSPACE_DESTINATION,
            "--entrypoint",
            spec.executable,
            prepared.image_id,
            *spec.argv,
        ]
    )
    return command


def _network_labels(nonce: str) -> dict[str, str]:
    return {OWNER_LABEL: OWNER_LABEL_VALUE, NONCE_LABEL: nonce}


def _validate_network(
    value: dict[str, object], *, network_id: str, network_name: str, nonce: str, internal: bool
) -> None:
    if (
        value.get("Id") != network_id
        or value.get("Name") != network_name
        or value.get("Driver") != "bridge"
        or value.get("Scope") != "local"
        or value.get("Ingress") is True
        or value.get("Attachable") is True
        or value.get("Internal") is not internal
        or value.get("Labels") != _network_labels(nonce)
    ):
        raise DockerRuntimeError("docker_network_manifest_mismatch")


def _validate_network_members(value: dict[str, object], allowed: set[str]) -> None:
    members = value.get("Containers")
    if not isinstance(members, dict) or not set(members).issubset(allowed):
        raise DockerRuntimeError("docker_network_manifest_mismatch")


def _expected_mounts(prepared: _PreparedInputs, control_directory: Path) -> dict[str, str]:
    result = {
        WORKSPACE_DESTINATION: str(prepared.workspace),
        HARNESS_DESTINATION: str(prepared.harness),
        CONTROL_DESTINATION: str(control_directory),
    }
    result.update({f"/inputs/{index:03d}": str(path) for index, path in enumerate(prepared.inputs)})
    return result


def _validate_container(
    value: dict[str, object],
    *,
    prepared: _PreparedInputs,
    container_id: str,
    container_name: str,
    network_id: str,
    network_name: str,
    nonce: str,
    control_directory: Path,
) -> str:
    config = value.get("Config")
    host = value.get("HostConfig")
    state = value.get("State")
    network_settings = value.get("NetworkSettings")
    if not all(isinstance(item, dict) for item in (config, host, state, network_settings)):
        raise DockerRuntimeError("docker_container_manifest_mismatch")
    assert isinstance(config, dict) and isinstance(host, dict) and isinstance(state, dict)
    assert isinstance(network_settings, dict)
    labels = config.get("Labels")
    security = host.get("SecurityOpt")
    log_config = host.get("LogConfig")
    restart = host.get("RestartPolicy")
    ulimits = host.get("Ulimits")
    tmpfs = host.get("Tmpfs")
    networks = network_settings.get("Networks")
    expected_nano_cpus = int(round(float(prepared.spec.limits.cpu_count) * 1_000_000_000))
    expected_cap_add = (
        {"CAP_SYS_PTRACE"} if prepared.spec.supervisor_write_broker else set()
    )
    expected_env = {
        f"HOME={SCRATCH_DESTINATION}",
        f"TMPDIR={SCRATCH_DESTINATION}",
        f"TMP={SCRATCH_DESTINATION}",
        f"TEMP={SCRATCH_DESTINATION}",
        f"HARNESS_DRIVER_SCRATCH={SCRATCH_DESTINATION}",
        f"HARNESS_RUNTIME_CONTROL={CONTROL_DESTINATION}",
    }
    if (
        value.get("Id") != container_id
        or value.get("Name") != f"/{container_name}"
        or value.get("Image") != prepared.image_id
        or value.get("Platform") != "linux"
        or state.get("Running") is not False
        or state.get("Status") != "created"
        or config.get("Image") not in {prepared.spec.image, prepared.image_id}
        or config.get("User") != prepared.runtime_user
        or config.get("Entrypoint") != [prepared.spec.executable]
        or config.get("Cmd") != list(prepared.spec.argv)
        or config.get("Hostname") != "lrh-session"
        or config.get("Domainname") != ""
        or config.get("WorkingDir") != WORKSPACE_DESTINATION
        or config.get("Healthcheck") != {"Test": ["NONE"]}
        or config.get("AttachStdin") is not True
        or config.get("AttachStdout") is not True
        or config.get("AttachStderr") is not True
        or config.get("OpenStdin") is not True
        or config.get("StdinOnce") is not True
        or config.get("Tty") is not False
        or not isinstance(config.get("Env"), list)
        or any(not isinstance(value, str) for value in config["Env"])
        or not expected_env.issubset(set(config["Env"]))
        or not isinstance(labels, dict)
        or labels.get(OWNER_LABEL) != OWNER_LABEL_VALUE
        or labels.get(NONCE_LABEL) != nonce
        or host.get("ReadonlyRootfs") is not True
        or host.get("Privileged") is not False
        or set(host.get("CapDrop") or []) != {"ALL"}
        or set(host.get("CapAdd") or []) != expected_cap_add
        or not isinstance(security, list)
        or any(not isinstance(value, str) for value in security)
        or set(security) != {"no-new-privileges=true"}
        or host.get("AutoRemove") is not False
        or not isinstance(log_config, dict)
        or log_config.get("Type") != "none"
        or not isinstance(restart, dict)
        or restart.get("Name") != "no"
        or host.get("PidsLimit") != prepared.spec.limits.pids
        or host.get("Memory") != prepared.spec.limits.memory_bytes
        or host.get("MemorySwap") != prepared.spec.limits.memory_bytes
        or host.get("MemorySwappiness") not in {0, None}
        or host.get("NanoCpus") != expected_nano_cpus
        or host.get("ShmSize") != prepared.spec.limits.shm_bytes
        or host.get("CgroupnsMode") != "private"
        or host.get("IpcMode") != "private"
        # Docker spells its private PID namespace as the empty default value;
        # only a host/container namespace reference would be non-empty here.
        or host.get("PidMode") != ""
        or host.get("UTSMode") != ""
        or host.get("UsernsMode") != ""
        or host.get("OomKillDisable") is not False
        or host.get("Init") is not None
        or host.get("NetworkMode") != network_id
        or host.get("PublishAllPorts") is True
        or host.get("PortBindings") not in (None, {})
        or host.get("Devices") not in (None, [])
        or not isinstance(ulimits, list)
        or len(ulimits) != 2
        or any(not isinstance(item, dict) for item in ulimits)
        or {item.get("Name"): (item.get("Soft"), item.get("Hard")) for item in ulimits if isinstance(item, dict)}
        != {"nofile": (prepared.spec.limits.nofile, prepared.spec.limits.nofile), "core": (0, 0)}
        or not isinstance(tmpfs, dict)
        or set(tmpfs) != {SCRATCH_DESTINATION, SHM_DESTINATION}
        or not isinstance(networks, dict)
        or set(networks) != {network_name}
    ):
        raise DockerRuntimeError("docker_container_manifest_mismatch")
    environment = config["Env"]
    for expected in expected_env:
        key = expected.split("=", 1)[0] + "="
        if [value for value in environment if value.startswith(key)] != [expected]:
            raise DockerRuntimeError("docker_container_manifest_mismatch")
    scratch_options = str(tmpfs[SCRATCH_DESTINATION])
    required_tmpfs = {
        "rw",
        "nosuid",
        "nodev",
        f"size={prepared.spec.limits.scratch_bytes}",
        f"nr_inodes={prepared.spec.limits.scratch_inodes}",
        "mode=0700",
        f"uid={prepared.runtime_user.split(':', 1)[0]}",
        f"gid={prepared.runtime_user.split(':', 1)[1]}",
    }
    if set(scratch_options.split(",")) != required_tmpfs:
        raise DockerRuntimeError("docker_container_manifest_mismatch")
    shm_options = str(tmpfs[SHM_DESTINATION])
    required_shm_tmpfs = {
        "rw",
        "nosuid",
        "nodev",
        "noexec",
        f"size={prepared.spec.limits.shm_bytes}",
        f"nr_inodes={prepared.spec.limits.shm_inodes}",
        "mode=1777",
    }
    if set(shm_options.split(",")) != required_shm_tmpfs:
        raise DockerRuntimeError("docker_container_manifest_mismatch")
    endpoint = networks[network_name]
    # A created-but-never-started container has the exact network selected in
    # HostConfig.NetworkMode while Docker leaves this endpoint ID empty until
    # activation.  Once populated, it must be the same exact network ID.
    if not isinstance(endpoint, dict) or endpoint.get("NetworkID") not in {"", network_id}:
        raise DockerRuntimeError("docker_container_manifest_mismatch")
    mounts = value.get("Mounts")
    if not isinstance(mounts, list):
        raise DockerRuntimeError("docker_container_manifest_mismatch")
    actual_mounts: dict[str, str] = {}
    for mount in mounts:
        if (
            not isinstance(mount, dict)
            or mount.get("Type") != "bind"
            or mount.get("RW") is not False
            or mount.get("Propagation") != "rprivate"
            or mount.get("Mode") != ""
        ):
            raise DockerRuntimeError("docker_container_manifest_mismatch")
        source, destination = mount.get("Source"), mount.get("Destination")
        if not isinstance(source, str) or not isinstance(destination, str):
            raise DockerRuntimeError("docker_container_manifest_mismatch")
        if destination in actual_mounts:
            raise DockerRuntimeError("docker_container_manifest_mismatch")
        actual_mounts[destination] = source
    if actual_mounts != _expected_mounts(prepared, control_directory):
        raise DockerRuntimeError("docker_container_manifest_mismatch")
    # Hash the complete normalized boundary contract rather than Docker's volatile inspect output.
    # The immutable image ID covers inherited image configuration; every runtime-controlled field
    # that can affect authority, visibility, or resource use is represented here.
    manifest = {
        "schema_version": 1,
        "container_id": container_id,
        "container_name": container_name,
        "image_id": prepared.image_id,
        "runtime": {
            "user": prepared.runtime_user,
            "executable": prepared.spec.executable,
            "argv": list(prepared.spec.argv),
            "working_directory": WORKSPACE_DESTINATION,
            "stdin_once": True,
            "environment": sorted(expected_env),
        },
        "network": {
            "id": network_id,
            "name": network_name,
            "internal": prepared.spec.network_internal,
        },
        "labels": {OWNER_LABEL: OWNER_LABEL_VALUE, NONCE_LABEL: nonce},
        "mounts": actual_mounts,
        "host_config": {
            "readonly_root": True,
            "privileged": False,
            "cap_drop": ["ALL"],
            "cap_add": sorted(expected_cap_add),
            "no_new_privileges": True,
            "auto_remove": False,
            "restart": "no",
            "log_driver": "none",
            "cgroup_namespace": "private",
            "ipc_namespace": "private",
            "pid_namespace": "private",
            "uts_namespace": "private",
            "memory": prepared.spec.limits.memory_bytes,
            "memory_swap": prepared.spec.limits.memory_bytes,
            "nano_cpus": expected_nano_cpus,
            "pids": prepared.spec.limits.pids,
            "nofile": prepared.spec.limits.nofile,
            "core": 0,
            "shm_bytes": prepared.spec.limits.shm_bytes,
            "shm_inodes": prepared.spec.limits.shm_inodes,
            "scratch_bytes": prepared.spec.limits.scratch_bytes,
            "scratch_inodes": prepared.spec.limits.scratch_inodes,
        },
    }
    return "sha256:" + hashlib.sha256(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _owned(value: dict[str, object], *, identifier: str, nonce: str) -> bool:
    config = value.get("Config")
    labels = config.get("Labels") if isinstance(config, dict) else value.get("Labels")
    return bool(
        value.get("Id") == identifier
        and isinstance(labels, dict)
        and labels.get(OWNER_LABEL) == OWNER_LABEL_VALUE
        and labels.get(NONCE_LABEL) == nonce
    )


def _cleanup_exact(
    docker: Path,
    *,
    container_id: str,
    container_nonce: str,
    network_id: str,
    network_nonce: str,
) -> None:
    if not _is_absent(docker, "container", container_id):
        container = _inspect_one(docker, "container", container_id)
        if not _owned(container, identifier=container_id, nonce=container_nonce):
            raise DockerRuntimeError("docker_cleanup_identity_mismatch")
        _run_docker(docker, ["container", "rm", "--force", "--volumes", container_id])
        if not _is_absent(docker, "container", container_id):
            raise DockerRuntimeError("docker_cleanup_failed")
    if not _is_absent(docker, "network", network_id):
        network = _inspect_one(docker, "network", network_id)
        if not _owned(network, identifier=network_id, nonce=network_nonce):
            raise DockerRuntimeError("docker_cleanup_identity_mismatch")
        containers = network.get("Containers")
        if containers not in (None, {}):
            raise DockerRuntimeError("docker_cleanup_network_busy")
        _run_docker(docker, ["network", "rm", network_id])
        if not _is_absent(docker, "network", network_id):
            raise DockerRuntimeError("docker_cleanup_failed")


def _remove_control_directory(path: Path, *, device: int, inode: int) -> None:
    try:
        directory_fd = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
    except FileNotFoundError:
        return
    try:
        entry = os.fstat(directory_fd)
        if not stat.S_ISDIR(entry.st_mode) or (entry.st_dev, entry.st_ino) != (device, inode):
            raise DockerRuntimeError("docker_control_identity_mismatch")
        names = os.listdir(directory_fd)
        if len(names) > MAX_CONTROL_FILES or any(
            _CONTROL_NAME_RE.fullmatch(name) is None for name in names
        ):
            raise DockerRuntimeError("docker_control_cleanup_failed")
        for name in names:
            current = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            if not stat.S_ISREG(current.st_mode) or current.st_size > MAX_CONTROL_FILE_BYTES:
                raise DockerRuntimeError("docker_control_cleanup_failed")
            os.unlink(name, dir_fd=directory_fd)
    finally:
        os.close(directory_fd)
    path.rmdir()


def _watchdog_ready(process: subprocess.Popen[bytes], ready_fd: int) -> None:
    deadline = time.monotonic() + WATCHDOG_READY_TIMEOUT_SECONDS
    while True:
        if process.poll() is not None:
            raise DockerRuntimeError("docker_watchdog_unavailable")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise DockerRuntimeError("docker_watchdog_unavailable")
        readable, _, _ = select.select([ready_fd], [], [], remaining)
        if not readable:
            continue
        if os.read(ready_fd, 1) != b"1":
            raise DockerRuntimeError("docker_watchdog_unavailable")
        return


class PreparedDockerSession:
    """Stopped, revalidated container with an armed independent cleanup watchdog."""

    def __init__(
        self,
        *,
        prepared: _PreparedInputs,
        identity: DockerSessionIdentity,
        control_device: int,
        control_inode: int,
        lifetime_write_fd: int,
        watchdog: subprocess.Popen[bytes],
    ) -> None:
        self._prepared = prepared
        self.identity = identity
        self._control_device = control_device
        self._control_inode = control_inode
        self._lifetime_write_fd = lifetime_write_fd
        self._watchdog = watchdog
        self._started = False
        self._closed = False
        self._control_total = 0
        self._control_names: set[str] = set()

    def write_control_file(self, name: str, value: bytes) -> Path:
        """Create one bounded 0400 file while the container is still stopped."""
        if self._closed or self._started:
            raise DockerRuntimeError("docker_control_phase_closed")
        if _CONTROL_NAME_RE.fullmatch(name) is None or name in self._control_names:
            raise DockerRuntimeError("docker_control_file_invalid")
        if not isinstance(value, bytes) or len(value) > MAX_CONTROL_FILE_BYTES:
            raise DockerRuntimeError("docker_control_file_invalid")
        if len(self._control_names) >= MAX_CONTROL_FILES or self._control_total + len(value) > MAX_CONTROL_TOTAL_BYTES:
            raise DockerRuntimeError("docker_control_file_invalid")
        directory = self.identity.control_directory
        entry = directory.stat(follow_symlinks=False)
        if (entry.st_dev, entry.st_ino) != (self._control_device, self._control_inode):
            raise DockerRuntimeError("docker_control_identity_mismatch")
        directory_fd = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
        descriptor = -1
        try:
            opened = os.fstat(directory_fd)
            if (opened.st_dev, opened.st_ino) != (self._control_device, self._control_inode):
                raise DockerRuntimeError("docker_control_identity_mismatch")
            descriptor = os.open(
                name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                0o400,
                dir_fd=directory_fd,
            )
            total = 0
            while total < len(value):
                total += os.write(descriptor, value[total:])
            os.fsync(descriptor)
        except OSError as exc:
            raise DockerRuntimeError("docker_control_file_invalid") from exc
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            os.close(directory_fd)
        self._control_names.add(name)
        self._control_total += len(value)
        return Path(CONTROL_DESTINATION) / name

    def _kill_if_running(self) -> None:
        container = _inspect_one(self._prepared.docker, "container", self.identity.container_id)
        if not _owned(container, identifier=self.identity.container_id, nonce=self.identity.nonce):
            raise DockerRuntimeError("docker_cleanup_identity_mismatch")
        state = container.get("State")
        if isinstance(state, dict) and state.get("Running") is True:
            result = _run_docker(
                self._prepared.docker,
                ["container", "kill", "--signal", "KILL", self.identity.container_id],
                allow_failure=True,
            )
            if result.returncode != 0:
                current = _inspect_one(self._prepared.docker, "container", self.identity.container_id)
                current_state = current.get("State")
                if not isinstance(current_state, dict) or current_state.get("Running") is True:
                    raise DockerRuntimeError("docker_container_kill_failed")

    def start(
        self,
        *,
        timeout_seconds: float,
        on_process_started: Callable[[DockerSessionIdentity], None] | None = None,
        stop_requested: Callable[[], bool] = lambda: False,
        stdin_bytes: bytes = b"",
    ) -> DockerSessionResult:
        """Revalidate, invoke the stopped-state release callback, run, and clean exactly.

        ``on_process_started`` is intentionally invoked before ``docker start`` so a caller can
        activate authority only after checking the returned exact identity, while the untrusted
        process is still unable to run.
        """
        if self._closed or self._started:
            raise DockerRuntimeError("docker_session_phase_invalid")
        if (
            not isinstance(timeout_seconds, (int, float))
            or isinstance(timeout_seconds, bool)
            or not math.isfinite(float(timeout_seconds))
            or timeout_seconds <= 0
            or timeout_seconds > 24 * 60 * 60
            or not isinstance(stdin_bytes, bytes)
            or len(stdin_bytes) > MAX_CONTROL_TOTAL_BYTES
            or on_process_started is not None
            and not callable(on_process_started)
            or not callable(stop_requested)
        ):
            raise DockerRuntimeError("docker_session_start_invalid")
        self._started = True
        try:
            if self._watchdog.poll() is not None:
                raise DockerRuntimeError("docker_watchdog_unavailable")
            # Revalidate the entire stopped manifest immediately before semantic activation.
            digest = _validate_container(
                _inspect_one(self._prepared.docker, "container", self.identity.container_id),
                prepared=self._prepared,
                container_id=self.identity.container_id,
                container_name=self.identity.container_name,
                network_id=self.identity.network_id,
                network_name=self.identity.network_name,
                nonce=self.identity.nonce,
                control_directory=self.identity.control_directory,
            )
            if digest != self.identity.config_digest:
                raise DockerRuntimeError("docker_container_manifest_mismatch")
            network = _inspect_one(self._prepared.docker, "network", self.identity.network_id)
            _validate_network(
                network,
                network_id=self.identity.network_id,
                network_name=self.identity.network_name,
                nonce=self.identity.nonce,
                internal=self._prepared.spec.network_internal,
            )
            _validate_network_members(network, {self.identity.container_id})
            if on_process_started is not None:
                on_process_started(self.identity)
        except BaseException:
            self.close()
            raise

        process: subprocess.Popen[bytes] | None = None
        stdout_capture: _BoundedPipeCapture | None = None
        stderr_capture: _BoundedPipeCapture | None = None
        timed_out = False
        interrupted = False
        try:
            process = subprocess.Popen(
                [
                    str(self._prepared.docker),
                    "container",
                    "start",
                    "--attach",
                    "--interactive",
                    self.identity.container_id,
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=_docker_environment(),
                start_new_session=True,
            )
            assert process.stdin is not None and process.stdout is not None and process.stderr is not None
            stdout_capture = _BoundedPipeCapture(process.stdout, retain=True)
            stderr_capture = _BoundedPipeCapture(process.stderr, retain=False)
            stdout_capture.start()
            stderr_capture.start()

            def write_stdin() -> None:
                try:
                    if stdin_bytes:
                        process.stdin.write(stdin_bytes)
                        process.stdin.flush()
                except (BrokenPipeError, OSError):
                    pass
                finally:
                    try:
                        process.stdin.close()
                    except OSError:
                        pass

            writer = threading.Thread(target=write_stdin, daemon=True)
            writer.start()
            deadline = time.monotonic() + float(timeout_seconds)
            while process.poll() is None:
                if stop_requested():
                    interrupted = True
                    self._kill_if_running()
                    break
                if time.monotonic() >= deadline:
                    timed_out = True
                    self._kill_if_running()
                    break
                time.sleep(POLL_SECONDS)
            try:
                process.wait(timeout=CONTAINER_STOP_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2.0)
                self._kill_if_running()
            writer.join(timeout=2.0)
            if writer.is_alive():
                raise DockerRuntimeError("docker_stdin_drain_failed")
            stdout_capture.finish()
            stderr_capture.finish()
            container = _inspect_one(self._prepared.docker, "container", self.identity.container_id)
            if not _owned(container, identifier=self.identity.container_id, nonce=self.identity.nonce):
                raise DockerRuntimeError("docker_container_identity_mismatch")
            state = container.get("State")
            if not isinstance(state, dict) or state.get("Running") is not False:
                raise DockerRuntimeError("docker_container_survived")
            returncode = state.get("ExitCode")
            if type(returncode) is not int:
                raise DockerRuntimeError("docker_container_state_invalid")
            return DockerSessionResult(
                started=True,
                timed_out=timed_out,
                interrupted=interrupted,
                returncode=returncode,
                oom_killed=state.get("OOMKilled") is True,
                output_truncated=stdout_capture.truncated,
                container_id=self.identity.container_id,
                network_id=self.identity.network_id,
                _stdout=stdout_capture.value,
            )
        except OSError as exc:
            raise DockerRuntimeError("docker_container_start_failed") from exc
        finally:
            if process is not None and process.poll() is None:
                process.kill()
                try:
                    process.wait(timeout=2.0)
                except subprocess.TimeoutExpired:
                    pass
            if process is not None:
                for stream in (process.stdin, process.stdout, process.stderr):
                    if stream is not None:
                        try:
                            stream.close()
                        except (OSError, ValueError):
                            pass
            self.close()

    def close(self) -> None:
        if self._closed:
            return
        cleanup_error: BaseException | None = None
        try:
            _cleanup_exact(
                self._prepared.docker,
                container_id=self.identity.container_id,
                container_nonce=self.identity.nonce,
                network_id=self.identity.network_id,
                network_nonce=self.identity.nonce,
            )
            _remove_control_directory(
                self.identity.control_directory,
                device=self._control_device,
                inode=self._control_inode,
            )
        except BaseException as exc:
            cleanup_error = exc
        finally:
            try:
                os.close(self._lifetime_write_fd)
            except OSError:
                pass
            self._lifetime_write_fd = -1
            try:
                returncode = self._watchdog.wait(timeout=WATCHDOG_EXIT_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired as exc:
                self._watchdog.kill()
                self._watchdog.wait(timeout=2.0)
                if cleanup_error is None:
                    cleanup_error = DockerRuntimeError("docker_watchdog_cleanup_failed")
            else:
                if returncode != 0 and cleanup_error is None:
                    cleanup_error = DockerRuntimeError("docker_watchdog_cleanup_failed")
            self._closed = True
        if cleanup_error is not None:
            if isinstance(cleanup_error, DockerRuntimeError):
                raise cleanup_error
            raise DockerRuntimeError("docker_cleanup_failed") from cleanup_error

    def __enter__(self) -> "PreparedDockerSession":
        return self

    def __exit__(self, _type: object, _value: object, _traceback: object) -> None:
        self.close()


def prepare_docker_session(spec: DockerRuntimeSpec) -> PreparedDockerSession:
    """Create a stopped exact-manifest container and arm cleanup before returning it."""

    prepared = _preflight(spec)
    nonce = uuid.uuid4().hex
    network_name = f"lrh-{nonce}"
    container_name = f"lrh-{nonce}"
    control_directory = Path(tempfile.mkdtemp(prefix="lrh-docker-control-")).resolve()
    os.chmod(control_directory, 0o700)
    control_stat = control_directory.stat(follow_symlinks=False)
    network_id: str | None = None
    container_id: str | None = None
    lifetime_read_fd = lifetime_write_fd = ready_read_fd = ready_write_fd = -1
    watchdog: subprocess.Popen[bytes] | None = None
    try:
        network_command = [
            "network",
            "create",
            "--driver",
            "bridge",
            "--label",
            f"{OWNER_LABEL}={OWNER_LABEL_VALUE}",
            "--label",
            f"{NONCE_LABEL}={nonce}",
        ]
        if spec.network_internal:
            network_command.append("--internal")
        network_command.append(network_name)
        network_result = _run_docker(prepared.docker, network_command)
        network_id = _validate_id(
            network_result.stdout.decode("ascii", errors="strict").strip(),
            code="docker_network_id_invalid",
        )
        network = _inspect_one(prepared.docker, "network", network_id)
        _validate_network(
            network,
            network_id=network_id,
            network_name=network_name,
            nonce=nonce,
            internal=spec.network_internal,
        )
        _validate_network_members(network, set())
        create_result = _run_docker(
            prepared.docker,
            _create_command(
                prepared,
                container_name=container_name,
                network_id=network_id,
                nonce=nonce,
                control_directory=control_directory,
            ),
            timeout=30.0,
        )
        container_id = _validate_id(
            create_result.stdout.decode("ascii", errors="strict").strip(),
            code="docker_container_id_invalid",
        )
        config_digest = _validate_container(
            _inspect_one(prepared.docker, "container", container_id),
            prepared=prepared,
            container_id=container_id,
            container_name=container_name,
            network_id=network_id,
            network_name=network_name,
            nonce=nonce,
            control_directory=control_directory,
        )
        network = _inspect_one(prepared.docker, "network", network_id)
        _validate_network(
            network,
            network_id=network_id,
            network_name=network_name,
            nonce=nonce,
            internal=spec.network_internal,
        )
        _validate_network_members(network, {container_id})

        lifetime_read_fd, lifetime_write_fd = os.pipe()
        ready_read_fd, ready_write_fd = os.pipe()
        watchdog_path = Path(__file__).with_name("_docker_session_watchdog.py").resolve(strict=True)
        watchdog = subprocess.Popen(
            [
                str(Path(sys.executable).resolve(strict=True)),
                str(watchdog_path),
                str(lifetime_read_fd),
                str(ready_write_fd),
                str(prepared.docker),
                container_id,
                nonce,
                network_id,
                nonce,
                str(control_directory),
                str(control_stat.st_dev),
                str(control_stat.st_ino),
                "1",
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            pass_fds=(lifetime_read_fd, ready_write_fd),
            env=_docker_environment(),
            start_new_session=True,
        )
        os.close(lifetime_read_fd)
        lifetime_read_fd = -1
        os.close(ready_write_fd)
        ready_write_fd = -1
        _watchdog_ready(watchdog, ready_read_fd)
        os.close(ready_read_fd)
        ready_read_fd = -1
        identity = DockerSessionIdentity(
            container_id=container_id,
            container_name=container_name,
            network_id=network_id,
            network_name=network_name,
            nonce=nonce,
            config_digest=config_digest,
            control_directory=control_directory,
            mount_manifest=MappingProxyType(_expected_mounts(prepared, control_directory)),
        )
        return PreparedDockerSession(
            prepared=prepared,
            identity=identity,
            control_device=control_stat.st_dev,
            control_inode=control_stat.st_ino,
            lifetime_write_fd=lifetime_write_fd,
            watchdog=watchdog,
        )
    except BaseException:
        for descriptor in (lifetime_read_fd, lifetime_write_fd, ready_read_fd, ready_write_fd):
            if descriptor >= 0:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
        if watchdog is not None:
            try:
                watchdog.wait(timeout=WATCHDOG_EXIT_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                watchdog.kill()
                watchdog.wait(timeout=2.0)
        if container_id is not None and network_id is not None:
            try:
                _cleanup_exact(
                    prepared.docker,
                    container_id=container_id,
                    container_nonce=nonce,
                    network_id=network_id,
                    network_nonce=nonce,
                )
            except DockerRuntimeError:
                pass
        elif network_id is not None:
            try:
                network = _inspect_one(prepared.docker, "network", network_id)
                if _owned(network, identifier=network_id, nonce=nonce):
                    _run_docker(prepared.docker, ["network", "rm", network_id], allow_failure=True)
            except DockerRuntimeError:
                pass
        try:
            _remove_control_directory(
                control_directory,
                device=control_stat.st_dev,
                inode=control_stat.st_ino,
            )
        except DockerRuntimeError:
            pass
        raise
