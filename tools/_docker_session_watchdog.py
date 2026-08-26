#!/usr/bin/env python3
"""Independent exact-ID cleanup watchdog for one prepared Docker session.

The parent keeps the lifetime pipe's write end open.  Kernel EOF after normal close, crash, or
SIGKILL causes this process to remove only the nonce-bound container/network and the exact private
control directory.  It never enumerates Docker objects or host processes.
"""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

from docker_session_runtime import (
    DockerRuntimeError,
    _cleanup_exact,
    _inspect_one,
    _owned,
    _remove_control_directory,
    _validate_id,
)


def _positive_descriptor(raw: str) -> int:
    try:
        value = int(raw)
    except ValueError as exc:
        raise DockerRuntimeError("docker_watchdog_argument_invalid") from exc
    if value < 0:
        raise DockerRuntimeError("docker_watchdog_argument_invalid")
    os.fstat(value)
    return value


def _positive_integer(raw: str) -> int:
    try:
        value = int(raw)
    except ValueError as exc:
        raise DockerRuntimeError("docker_watchdog_argument_invalid") from exc
    if value < 0:
        raise DockerRuntimeError("docker_watchdog_argument_invalid")
    return value


def _validate_control(path: Path, *, device: int, inode: int) -> None:
    if not path.is_absolute() or "\x00" in os.fspath(path):
        raise DockerRuntimeError("docker_watchdog_argument_invalid")
    entry = path.stat(follow_symlinks=False)
    if (
        not stat.S_ISDIR(entry.st_mode)
        or stat.S_ISLNK(entry.st_mode)
        or (entry.st_dev, entry.st_ino) != (device, inode)
    ):
        raise DockerRuntimeError("docker_control_identity_mismatch")


def main() -> int:
    if len(sys.argv) != 12:
        return 64
    try:
        lifetime_fd = _positive_descriptor(sys.argv[1])
        ready_fd = _positive_descriptor(sys.argv[2])
        docker = Path(sys.argv[3])
        container_id = _validate_id(sys.argv[4], code="docker_watchdog_argument_invalid")
        container_nonce = sys.argv[5]
        network_id = _validate_id(sys.argv[6], code="docker_watchdog_argument_invalid")
        network_nonce = sys.argv[7]
        control = Path(sys.argv[8])
        control_device = _positive_integer(sys.argv[9])
        control_inode = _positive_integer(sys.argv[10])
        # The final reserved argument keeps the CLI shape versioned.  Version 1 is the only value.
        if sys.argv[11] != "1":
            raise DockerRuntimeError("docker_watchdog_argument_invalid")
        if (
            not docker.is_absolute()
            or not docker.is_file()
            or not os.access(docker, os.X_OK)
            or len(container_nonce) != 32
            or len(network_nonce) != 32
        ):
            raise DockerRuntimeError("docker_watchdog_argument_invalid")
        _validate_control(control, device=control_device, inode=control_inode)
        container = _inspect_one(docker, "container", container_id)
        network = _inspect_one(docker, "network", network_id)
        if not _owned(container, identifier=container_id, nonce=container_nonce) or not _owned(
            network, identifier=network_id, nonce=network_nonce
        ):
            raise DockerRuntimeError("docker_cleanup_identity_mismatch")
    except (OSError, DockerRuntimeError):
        return 65

    try:
        if os.write(ready_fd, b"1") != 1:
            return 65
    except OSError:
        return 65
    finally:
        try:
            os.close(ready_fd)
        except OSError:
            pass

    try:
        while os.read(lifetime_fd, 4096):
            # The protocol currently sends no messages.  Ignoring data makes an accidental write
            # harmless while EOF remains the only cleanup trigger.
            pass
    except OSError:
        return 66
    finally:
        try:
            os.close(lifetime_fd)
        except OSError:
            pass

    try:
        _cleanup_exact(
            docker,
            container_id=container_id,
            container_nonce=container_nonce,
            network_id=network_id,
            network_nonce=network_nonce,
        )
        _remove_control_directory(control, device=control_device, inode=control_inode)
    except DockerRuntimeError:
        return 66
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
