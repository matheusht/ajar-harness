#!/usr/bin/env python3
"""Internal launcher: bind cwd, await the parent start gate, then exec."""

from __future__ import annotations

import os
import resource
import stat
import sys


def main() -> int:
    if (
        len(sys.argv) < 6
        or not sys.argv[1].isdigit()
        or not sys.argv[2].isdigit()
        or not sys.argv[3].isdigit()
        or not sys.argv[4].isdigit()
    ):
        return 64
    directory_fd = int(sys.argv[1])
    gate_fd = int(sys.argv[2])
    containment_fd = int(sys.argv[3])
    cpu_limit_seconds = int(sys.argv[4])
    try:
        if not stat.S_ISDIR(os.fstat(directory_fd).st_mode):
            return 65
        if not stat.S_ISREG(os.fstat(containment_fd).st_mode) or cpu_limit_seconds <= 0:
            return 65
        resource.setrlimit(
            resource.RLIMIT_CPU,
            (cpu_limit_seconds, cpu_limit_seconds),
        )
        os.fchdir(directory_fd)
        if os.read(gate_fd, 1) != b"1":
            return 67
        os.close(gate_fd)
        os.execv(sys.argv[5], sys.argv[5:])
    except OSError:
        return 66
    return 66


if __name__ == "__main__":
    raise SystemExit(main())
