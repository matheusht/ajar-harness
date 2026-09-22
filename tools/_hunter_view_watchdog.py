#!/usr/bin/env python3
"""Remove one exact hunter-view directory when its parent lifetime pipe closes."""

from __future__ import annotations

import os
import shutil
import stat
import sys
from pathlib import Path


def _remove(path: Path) -> None:
    for directory in [path, *(candidate for candidate in path.rglob("*") if candidate.is_dir())]:
        os.chmod(directory, 0o700, follow_symlinks=False)
    shutil.rmtree(path)


def main() -> int:
    if len(sys.argv) != 6:
        return 64
    try:
        lifetime_fd, ready_fd, device, inode = map(int, (sys.argv[1], sys.argv[2], sys.argv[4], sys.argv[5]))
        path = Path(sys.argv[3])
        entry = path.stat(follow_symlinks=False)
        if not path.is_absolute() or not stat.S_ISDIR(entry.st_mode) or stat.S_ISLNK(entry.st_mode) or (entry.st_dev, entry.st_ino) != (device, inode):
            return 65
        os.write(ready_fd, b"1")
        os.close(ready_fd)
        while os.read(lifetime_fd, 4096):
            pass
        os.close(lifetime_fd)
        current = path.stat(follow_symlinks=False)
        if (current.st_dev, current.st_ino) != (device, inode) or not stat.S_ISDIR(current.st_mode):
            return 66
        _remove(path)
        return 0
    except OSError:
        return 66


if __name__ == "__main__":
    raise SystemExit(main())
