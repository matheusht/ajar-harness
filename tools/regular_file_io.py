"""Open regular files without blocking on special files."""

import json
import os
import stat
from contextlib import contextmanager


@contextmanager
def open_regular_file(path, *, binary=False, encoding=None, errors="strict", no_follow=False):
    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0)
    if no_follow:
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags)
    options = {} if binary else {"encoding": encoding, "errors": errors}
    try:
        handle = os.fdopen(fd, "rb" if binary else "r", **options)
    except BaseException:
        os.close(fd)
        raise
    with handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise OSError(f"{path}: input must be a regular file")
        yield handle


def read_regular_text(path, *, encoding=None, errors="strict", no_follow=False):
    with open_regular_file(path, encoding=encoding, errors=errors, no_follow=no_follow) as handle:
        return handle.read()


def load_json(path):
    return json.loads(read_regular_text(path, encoding="utf-8"))
