"""Read caller-supplied text without blocking on special files."""

import json
import os
import stat


def read_regular_text(path, *, encoding=None, errors="strict"):
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))
    with os.fdopen(fd, "r", encoding=encoding, errors=errors) as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise OSError(f"{path}: input must be a regular file")
        return handle.read()


def load_json(path):
    return json.loads(read_regular_text(path, encoding="utf-8"))
