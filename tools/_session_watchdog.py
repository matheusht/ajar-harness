#!/usr/bin/env python3
"""Internal parent-lifetime watchdog for one Claude process group.

The session adapter keeps the lifetime pipe's write end open.  An unexpected adapter exit closes
that descriptor in the kernel, which wakes this independent process and drains the already-known
Claude process group.  The Claude launcher stays behind a separate start gate until this watchdog
has acknowledged readiness, so there is no unprotected executable-session window.
"""

from __future__ import annotations

import ctypes
import os
import signal
import stat
import sys
import time
from pathlib import Path

from darwin_process_containment import ContainmentUnavailable, drain_holders, path_holders


DIRECTORY_FLAGS = (
    os.O_RDONLY
    | getattr(os, "O_DIRECTORY", 0)
    | getattr(os, "O_NOFOLLOW", 0)
    | getattr(os, "O_NONBLOCK", 0)
)
SCRATCH_CLEANUP_MAX_ENTRIES = 20_000
SCRATCH_CLEANUP_MAX_DEPTH = 4_096
SCRATCH_CLEANUP_MAX_WORK = 4_000_000
SCRATCH_CLEANUP_MAX_SECONDS = 20.0
SCRATCH_FAILURE_SUFFIX = ".cleanup-failed"


class _ScratchCleanupError(Exception):
    """The exact bound scratch tree could not be removed within its cleanup bounds."""


class _CleanupBudget:
    def __init__(self) -> None:
        self.entries = 0
        self.work = 0
        self.deadline = time.monotonic() + SCRATCH_CLEANUP_MAX_SECONDS

    def step(self, amount: int = 1) -> None:
        self.work += amount
        if self.work > SCRATCH_CLEANUP_MAX_WORK or time.monotonic() >= self.deadline:
            raise _ScratchCleanupError("work bound")

    def entry(self) -> None:
        self.entries += 1
        if self.entries > SCRATCH_CLEANUP_MAX_ENTRIES:
            raise _ScratchCleanupError("entry bound")
        self.step()


def _process_group_exists(process_group: int) -> bool:
    try:
        os.killpg(process_group, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _wait_for_process_group_exit(process_group: int, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while _process_group_exists(process_group):
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.01)
    return True


def _drain_process_group(process_group: int) -> None:
    try:
        os.killpg(process_group, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        return
    if _wait_for_process_group_exit(process_group, 2.0):
        return
    try:
        os.killpg(process_group, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        return
    _wait_for_process_group_exit(process_group, 2.0)


def _same_identity(value: os.stat_result, *, device: int, inode: int) -> bool:
    return value.st_dev == device and value.st_ino == inode


def _user_settable_flags(value: os.stat_result) -> int:
    mask = getattr(
        stat,
        "UF_SETTABLE",
        getattr(stat, "UF_IMMUTABLE", 0) | getattr(stat, "UF_APPEND", 0),
    )
    return int(getattr(value, "st_flags", 0)) & int(mask)


def _clear_fd_user_flags(file_descriptor: int, current_flags: int) -> None:
    function = getattr(ctypes.CDLL(None, use_errno=True), "fchflags", None)
    if function is None:
        raise _ScratchCleanupError("fchflags unavailable")
    function.argtypes = [ctypes.c_int, ctypes.c_uint]
    function.restype = ctypes.c_int
    if function(file_descriptor, current_flags) != 0:
        error_number = ctypes.get_errno()
        raise OSError(error_number, os.strerror(error_number))


def _make_bound_directory_mutable(
    directory_fd: int,
    *,
    device: int,
    inode: int,
    budget: _CleanupBudget,
) -> None:
    budget.step()
    before = os.fstat(directory_fd)
    if not stat.S_ISDIR(before.st_mode) or not _same_identity(
        before,
        device=device,
        inode=inode,
    ):
        raise _ScratchCleanupError("directory identity")
    user_flags = _user_settable_flags(before)
    if user_flags:
        budget.step()
        _clear_fd_user_flags(
            directory_fd,
            int(getattr(before, "st_flags", 0)) & ~user_flags,
        )
    budget.step()
    os.fchmod(directory_fd, 0o700)
    budget.step()
    after = os.fstat(directory_fd)
    if (
        not _same_identity(after, device=device, inode=inode)
        or _user_settable_flags(after)
    ):
        raise _ScratchCleanupError("directory mutation")


def _clear_bound_leaf_flags(
    parent_fd: int,
    name: str,
    expected: os.stat_result,
    budget: _CleanupBudget,
) -> None:
    user_flags = _user_settable_flags(expected)
    if not user_flags:
        return
    if expected.st_nlink != 1:
        raise _ScratchCleanupError("leaf flags")
    flags = (
        os.O_RDONLY
        | getattr(os, "O_NONBLOCK", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    if stat.S_ISLNK(expected.st_mode):
        flags |= getattr(os, "O_SYMLINK", 0)
    budget.step()
    leaf_fd = os.open(name, flags, dir_fd=parent_fd)
    try:
        budget.step()
        opened = os.fstat(leaf_fd)
        if (
            not _same_identity(opened, device=expected.st_dev, inode=expected.st_ino)
            or stat.S_IFMT(opened.st_mode) != stat.S_IFMT(expected.st_mode)
            or opened.st_nlink != 1
        ):
            raise _ScratchCleanupError("leaf identity")
        _clear_fd_user_flags(
            leaf_fd,
            int(getattr(opened, "st_flags", 0)) & ~user_flags,
        )
        budget.step()
        after = os.fstat(leaf_fd)
        if (
            not _same_identity(after, device=expected.st_dev, inode=expected.st_ino)
            or _user_settable_flags(after)
        ):
            raise _ScratchCleanupError("leaf mutation")
    finally:
        os.close(leaf_fd)


def _unlink_bound_leaf(
    parent_fd: int,
    name: str,
    expected: os.stat_result,
    budget: _CleanupBudget,
) -> None:
    if stat.S_ISDIR(expected.st_mode):
        raise _ScratchCleanupError("directory leaf")
    _clear_bound_leaf_flags(parent_fd, name, expected, budget)
    budget.step()
    current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    if (
        not _same_identity(current, device=expected.st_dev, inode=expected.st_ino)
        or stat.S_IFMT(current.st_mode) != stat.S_IFMT(expected.st_mode)
    ):
        raise _ScratchCleanupError("leaf identity")
    budget.step()
    os.unlink(name, dir_fd=parent_fd)


def _empty_bound_directory(directory_fd: int) -> bool:
    """Iteratively remove a bounded tree relative to its exact root descriptor."""

    stack: list[tuple[int, object, str | None, int, int, int]] = []
    try:
        root = os.fstat(directory_fd)
        if not stat.S_ISDIR(root.st_mode):
            return False
        budget = _CleanupBudget()
        budget.step()
        root_fd = os.dup(directory_fd)
        try:
            _make_bound_directory_mutable(
                root_fd,
                device=root.st_dev,
                inode=root.st_ino,
                budget=budget,
            )
            budget.step()
            root_entries = os.scandir(root_fd)
        except BaseException:
            os.close(root_fd)
            raise
        stack.append(
            (
                root_fd,
                root_entries,
                None,
                root.st_dev,
                root.st_ino,
                0,
            )
        )
        while stack:
            current_fd, raw_entries, child_name, device, inode, depth = stack[-1]
            entries = raw_entries
            try:
                directory_entry = next(entries)  # type: ignore[arg-type]
            except StopIteration:
                entries.close()  # type: ignore[union-attr]
                budget.step()
                with os.scandir(current_fd) as verification:
                    if next(verification, None) is not None:
                        raise _ScratchCleanupError("not empty")
                if child_name is not None:
                    if len(stack) < 2:
                        raise _ScratchCleanupError("missing parent")
                    parent_fd = stack[-2][0]
                    budget.step()
                    current = os.stat(
                        child_name,
                        dir_fd=parent_fd,
                        follow_symlinks=False,
                    )
                    if not stat.S_ISDIR(current.st_mode) or not _same_identity(
                        current,
                        device=device,
                        inode=inode,
                    ):
                        raise _ScratchCleanupError("post identity")
                    os.close(current_fd)
                    current_fd = -1
                    budget.step()
                    os.rmdir(child_name, dir_fd=parent_fd)
                else:
                    os.close(current_fd)
                    current_fd = -1
                stack.pop()
                continue

            budget.entry()
            name = directory_entry.name
            if not name or name in {".", ".."} or "/" in name:
                raise _ScratchCleanupError("entry name")
            budget.step()
            entry = os.stat(
                name,
                dir_fd=current_fd,
                follow_symlinks=False,
            )
            if not stat.S_ISDIR(entry.st_mode):
                _unlink_bound_leaf(current_fd, name, entry, budget)
                continue
            if depth + 1 > SCRATCH_CLEANUP_MAX_DEPTH:
                raise _ScratchCleanupError("depth bound")
            budget.step()
            child_fd = os.open(name, DIRECTORY_FLAGS, dir_fd=current_fd)
            try:
                child = os.fstat(child_fd)
                if not _same_identity(
                    child,
                    device=entry.st_dev,
                    inode=entry.st_ino,
                ):
                    raise _ScratchCleanupError("child identity")
                _make_bound_directory_mutable(
                    child_fd,
                    device=child.st_dev,
                    inode=child.st_ino,
                    budget=budget,
                )
                budget.step()
                child_entries = os.scandir(child_fd)
            except BaseException:
                os.close(child_fd)
                raise
            stack.append(
                (
                    child_fd,
                    child_entries,
                    name,
                    child.st_dev,
                    child.st_ino,
                    depth + 1,
                )
            )
        return True
    except (OSError, _ScratchCleanupError):
        return False
    finally:
        for open_fd, raw_entries, _name, _device, _inode, _depth in reversed(stack):
            try:
                raw_entries.close()  # type: ignore[union-attr]
            except (AttributeError, OSError):
                pass
            try:
                os.close(open_fd)
            except OSError:
                pass


def _arm_cleanup_failure_marker(
    scratch_parent_fd: int,
    scratch_name: str,
) -> str:
    """Durably pre-arm a marker before the model is released."""

    marker_name = f".{scratch_name}{SCRATCH_FAILURE_SUFFIX}"
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    marker_fd = os.open(marker_name, flags, 0o600, dir_fd=scratch_parent_fd)
    try:
        payload = b"scratch_cleanup_armed\n"
        if os.write(marker_fd, payload) != len(payload):
            raise OSError("short cleanup marker write")
        os.fsync(marker_fd)
    finally:
        os.close(marker_fd)
    os.fsync(scratch_parent_fd)
    return marker_name


def _clear_cleanup_failure_marker(
    scratch_parent_fd: int,
    marker_name: str,
) -> None:
    os.unlink(marker_name, dir_fd=scratch_parent_fd)
    os.fsync(scratch_parent_fd)


def _remove_bound_scratch(
    scratch_fd: int,
    scratch_parent_fd: int,
    scratch_name: str,
    *,
    device: int,
    inode: int,
) -> bool:
    """Empty and unlink only the original scratch inode bound before model launch."""

    if not scratch_name or scratch_name in {".", ".."} or "/" in scratch_name:
        return False
    try:
        bound = os.fstat(scratch_fd)
        parent = os.fstat(scratch_parent_fd)
        named = os.stat(
            scratch_name,
            dir_fd=scratch_parent_fd,
            follow_symlinks=False,
        )
    except OSError:
        return False
    if (
        not stat.S_ISDIR(bound.st_mode)
        or not stat.S_ISDIR(parent.st_mode)
        or not stat.S_ISDIR(named.st_mode)
        or not _same_identity(bound, device=device, inode=inode)
        or not _same_identity(named, device=device, inode=inode)
    ):
        return False
    if not _empty_bound_directory(scratch_fd):
        return False
    try:
        named = os.stat(
            scratch_name,
            dir_fd=scratch_parent_fd,
            follow_symlinks=False,
        )
    except OSError:
        return False
    if not stat.S_ISDIR(named.st_mode) or not _same_identity(
        named,
        device=device,
        inode=inode,
    ):
        return False
    try:
        os.rmdir(scratch_name, dir_fd=scratch_parent_fd)
    except OSError:
        return False
    return True


def main() -> int:
    numeric_arguments = (1, 2, 3, 4, 6, 7, 8, 9)
    if len(sys.argv) != 11 or not all(
        sys.argv[index].isdigit() for index in numeric_arguments
    ):
        return 64
    lifetime_fd = int(sys.argv[1])
    ready_fd = int(sys.argv[2])
    process_group = int(sys.argv[3])
    owner_pid = int(sys.argv[4])
    sentinel = Path(sys.argv[5])
    scratch_fd = int(sys.argv[6])
    scratch_parent_fd = int(sys.argv[7])
    scratch_device = int(sys.argv[8])
    scratch_inode = int(sys.argv[9])
    scratch_name = sys.argv[10]
    if (
        process_group <= 0
        or owner_pid <= 0
        or scratch_device < 0
        or scratch_inode <= 0
        or not sentinel.is_absolute()
        or not scratch_name
        or scratch_name in {".", ".."}
        or "/" in scratch_name
    ):
        return 64
    failure_marker_name: str | None = None
    initialization_error: int | None = None
    try:
        try:
            if not stat.S_ISFIFO(os.fstat(lifetime_fd).st_mode):
                return 65
            if not stat.S_ISFIFO(os.fstat(ready_fd).st_mode):
                return 65
            scratch_bound = os.fstat(scratch_fd)
            if not stat.S_ISDIR(scratch_bound.st_mode):
                return 65
            if not stat.S_ISDIR(os.fstat(scratch_parent_fd).st_mode):
                return 65
            scratch_named = os.stat(
                scratch_name,
                dir_fd=scratch_parent_fd,
                follow_symlinks=False,
            )
            if not stat.S_ISDIR(scratch_named.st_mode) or not _same_identity(
                scratch_named,
                device=scratch_device,
                inode=scratch_inode,
            ):
                return 65
            if not _same_identity(
                scratch_bound,
                device=scratch_device,
                inode=scratch_inode,
            ):
                return 65
        except OSError:
            return 66
        try:
            failure_marker_name = _arm_cleanup_failure_marker(
                scratch_parent_fd,
                scratch_name,
            )
        except OSError:
            initialization_error = 66
        if initialization_error is None:
            try:
                owner_present = owner_pid in path_holders(sentinel)
            except (OSError, ContainmentUnavailable):
                owner_present = False
            if not owner_present:
                initialization_error = 68
        if initialization_error is None:
            try:
                if os.write(ready_fd, b"1") != 1:
                    raise OSError("short watchdog readiness write")
            except OSError:
                initialization_error = 66
    finally:
        try:
            os.close(ready_fd)
        except OSError:
            pass

    lifetime_read_failed = False
    if initialization_error is None:
        try:
            while os.read(lifetime_fd, 1024):
                # The descriptor itself is the lifetime capability. Payload bytes have no authority;
                # cleanup begins on EOF whether the adapter exited normally or became an unreaped
                # zombie after SIGKILL.
                pass
        except OSError:
            lifetime_read_failed = True
        finally:
            try:
                os.close(lifetime_fd)
            except OSError:
                pass
    else:
        try:
            os.close(lifetime_fd)
        except OSError:
            pass

    _drain_process_group(process_group)
    try:
        drained = drain_holders(sentinel, exclude={owner_pid})
    except (OSError, ContainmentUnavailable):
        drained = None
    try:
        sentinel.unlink(missing_ok=True)
    except OSError:
        drained = None
    cleanup_succeeded = False
    if drained is True:
        cleanup_succeeded = _remove_bound_scratch(
            scratch_fd,
            scratch_parent_fd,
            scratch_name,
            device=scratch_device,
            inode=scratch_inode,
        )
    if cleanup_succeeded and failure_marker_name is not None:
        try:
            _clear_cleanup_failure_marker(
                scratch_parent_fd,
                failure_marker_name,
            )
        except OSError:
            cleanup_succeeded = False
    try:
        os.close(scratch_fd)
    except OSError:
        pass
    try:
        os.close(scratch_parent_fd)
    except OSError:
        pass
    if drained is None:
        return 68
    if not drained:
        return 69
    if not cleanup_succeeded:
        return 70
    if initialization_error is not None:
        return initialization_error
    if lifetime_read_failed:
        return 67
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
