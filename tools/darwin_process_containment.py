#!/usr/bin/env python3
"""Bounded Darwin descendant discovery through one inherited sentinel vnode.

This backend follows processes that retain the sentinel descriptor across fork, including children
that change process group/session or are reparented.  It deliberately does not claim to discover a
malicious daemon that closes the descriptor before detaching; callers combine it with Seatbelt,
process-group cleanup, and an inherited CPU limit.
"""

from __future__ import annotations

import ctypes
import os
import signal
import stat
import tempfile
import time
from pathlib import Path


PROC_UID_ONLY = 4


class ContainmentUnavailable(RuntimeError):
    """The platform cannot prove sentinel-holder discovery."""


def _libproc() -> ctypes.CDLL:
    try:
        library = ctypes.CDLL("libproc.dylib", use_errno=True)
        function = library.proc_listpidspath
    except (OSError, AttributeError) as exc:
        raise ContainmentUnavailable("Darwin libproc path-holder query unavailable") from exc
    function.argtypes = [
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_char_p,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_int,
    ]
    function.restype = ctypes.c_int
    return library


def path_holders(path: Path) -> set[int]:
    encoded = os.fsencode(path)
    function = _libproc().proc_listpidspath
    minimum = function(PROC_UID_ONLY, os.getuid(), encoded, 0, None, 0)
    if minimum <= 0:
        raise ContainmentUnavailable("Darwin libproc sizing query failed")
    capacity = max(minimum + 256, 4096)
    for _ in range(3):
        buffer = (ctypes.c_int * (capacity // ctypes.sizeof(ctypes.c_int)))()
        returned = function(
            PROC_UID_ONLY,
            os.getuid(),
            encoded,
            0,
            ctypes.byref(buffer),
            ctypes.sizeof(buffer),
        )
        if returned < 0:
            raise ContainmentUnavailable("Darwin libproc holder query failed")
        if returned < ctypes.sizeof(buffer):
            return {pid for pid in buffer[: returned // ctypes.sizeof(ctypes.c_int)] if pid > 0}
        capacity *= 2
    raise ContainmentUnavailable("Darwin libproc holder query remained truncated")


def create_sentinel() -> tuple[int, Path]:
    descriptor, raw_path = tempfile.mkstemp(prefix="lrh-session-containment-")
    path = Path(raw_path).resolve()
    try:
        os.fchmod(descriptor, 0o400)
        entry = os.fstat(descriptor)
        named = path.stat(follow_symlinks=False)
        if (
            not stat.S_ISREG(entry.st_mode)
            or entry.st_uid != os.getuid()
            or (entry.st_dev, entry.st_ino) != (named.st_dev, named.st_ino)
            or os.getpid() not in path_holders(path)
        ):
            raise ContainmentUnavailable("containment sentinel identity could not be proved")
        return descriptor, path
    except BaseException:
        os.close(descriptor)
        path.unlink(missing_ok=True)
        raise


def drain_holders(path: Path, *, exclude: set[int], timeout: float = 2.0) -> bool:
    """Terminate every discoverable same-UID process retaining the sentinel."""

    deadline = time.monotonic() + timeout
    signalled: set[int] = set()
    while True:
        holders = path_holders(path) - exclude - {os.getpid()}
        if not holders:
            return True
        for pid in holders - signalled:
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        signalled.update(holders)
        if time.monotonic() >= deadline:
            break
        time.sleep(0.01)
    holders = path_holders(path) - exclude - {os.getpid()}
    for pid in holders:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not (path_holders(path) - exclude - {os.getpid()}):
            return True
        time.sleep(0.01)
    return not (path_holders(path) - exclude - {os.getpid()})
