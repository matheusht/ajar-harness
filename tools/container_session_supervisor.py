#!/usr/bin/env python3
"""PID-1 boundary for one Docker-contained model session.

The parent creates ``session.json`` while the container is stopped and places only its digest in
the immutable Docker argv.  Model authentication arrives as one bounded canonical JSON document
on stdin, so neither secrets nor the prompt are retained by Docker inspect or the log driver.

The Docker tmpfs is the hard aggregate byte/inode boundary. This supervisor latches storage errors
and full filesystems at syscall boundaries across the traced descendant tree, and reserves exit 73
for storage exhaustion.
Exiting PID 1 makes the container runtime terminate every descendant, including a process that
closed descriptors, double-forked, or created a new session.
"""

from __future__ import annotations

import argparse
import array
import base64
import binascii
import ctypes
import errno
import hashlib
import http.client
import json
import os
import re
import select
import signal
import socket
import stat
import struct
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import container_broker_client as broker_client


CONTROL_ROOT = Path("/run/lrh-control")
SESSION_PATH = CONTROL_ROOT / "session.json"
BROKER_MANIFEST_PATH = CONTROL_ROOT / "broker-manifest.json"
SCRATCH_PATH = Path("/scratch")
SHM_PATH = Path("/dev/shm")
WORKSPACE_PATH = Path("/workspace")
BROKER_RELAY_PATH = SCRATCH_PATH / ".lrh-broker.sock"
MAX_SESSION_BYTES = 512 * 1024
MAX_AUTH_BYTES = 64 * 1024
MAX_COMMAND_ARGUMENTS = 1024
MAX_COMMAND_BYTES = 1024 * 1024
MAX_EMULATED_WRITE_BYTES = 16 * 1024 * 1024
RELAY_IO_TIMEOUT_SECONDS = 2.0
PROVIDER_IO_TIMEOUT_SECONDS = 30.0
MAX_PROVIDER_HEADER_BYTES = 64 * 1024
TRACE_BOOTSTRAP_TIMEOUT_SECONDS = 5.0
STORAGE_EXIT_CODE = 73
INTERNAL_FAILURE_EXIT_CODE = 74
PR_SET_DUMPABLE = 4
PR_SET_NO_NEW_PRIVS = 38
PR_SET_SECCOMP = 22
SECCOMP_SET_MODE_FILTER = 1
SECCOMP_GET_NOTIF_SIZES = 3
SECCOMP_FILTER_FLAG_NEW_LISTENER = 1 << 3
SECCOMP_FILTER_FLAG_WAIT_KILLABLE_RECV = 1 << 5
AUDIT_ARCH_AARCH64 = 0xC00000B7
SECCOMP_RET_KILL_PROCESS = 0x80000000
SECCOMP_RET_ERRNO = 0x00050000
SECCOMP_RET_USER_NOTIF = 0x7FC00000
SECCOMP_RET_ALLOW = 0x7FFF0000
SECCOMP_USER_NOTIF_FLAG_CONTINUE = 1
BPF_LD = 0x00
BPF_W = 0x00
BPF_ABS = 0x20
BPF_JMP = 0x05
BPF_JEQ = 0x10
BPF_JGE = 0x30
BPF_JSET = 0x40
BPF_K = 0x00
BPF_RET = 0x06
SECCOMP_DATA_ARCH_OFFSET = 4
SECCOMP_DATA_NR_OFFSET = 0
SECCOMP_DATA_ARG0_OFFSET = 16
SECCOMP_DATA_ARG2_OFFSET = 32
SECCOMP_DATA_ARG3_OFFSET = 40
AARCH64_NR_IO_SETUP = 0
AARCH64_NR_IO_DESTROY = 1
AARCH64_NR_IO_SUBMIT = 2
AARCH64_NR_IO_CANCEL = 3
AARCH64_NR_IO_GETEVENTS = 4
AARCH64_NR_CLONE = 220
AARCH64_NR_SOCKET = 198
AARCH64_NR_SOCKETPAIR = 199
AARCH64_NR_BIND = 200
AARCH64_NR_LISTEN = 201
AARCH64_NR_ACCEPT = 202
AARCH64_NR_CONNECT = 203
AARCH64_NR_SENDTO = 206
AARCH64_NR_SENDMSG = 211
AARCH64_NR_WRITE = 64
AARCH64_NR_WRITEV = 66
AARCH64_NR_PWRITE64 = 68
AARCH64_NR_PWRITEV = 70
AARCH64_NR_SENDFILE = 71
AARCH64_NR_SPLICE = 76
AARCH64_NR_UNSHARE = 97
AARCH64_NR_PRCTL = 167
AARCH64_NR_MMAP = 222
AARCH64_NR_ACCEPT4 = 242
AARCH64_NR_PROCESS_VM_WRITEV = 271
AARCH64_NR_SENDMMSG = 269
AARCH64_NR_SECCOMP = 277
AARCH64_NR_COPY_FILE_RANGE = 285
AARCH64_NR_PWRITEV2 = 287
AARCH64_NR_IO_PGETEVENTS = 292
AARCH64_NR_IO_URING_SETUP = 425
AARCH64_NR_IO_URING_ENTER = 426
AARCH64_NR_IO_URING_REGISTER = 427
AARCH64_NR_PIDFD_OPEN = 434
AARCH64_NR_CLONE3 = 435
AARCH64_NR_CLOSE_RANGE = 436
AARCH64_NR_PIDFD_GETFD = 438
AARCH64_REVIEWED_SYSCALL_LIMIT = 473
CLONE_UNTRACED = 0x00800000
CLONE_FILES = 0x00000400
CLONE_THREAD = 0x00010000
CLOSE_RANGE_UNSHARE = 1 << 1
PIDFD_THREAD = 0x80
MAP_SHARED = 0x01
MAP_ANONYMOUS = 0x20
PTRACE_TRACEME = 0
PTRACE_CONT = 7
PTRACE_SYSCALL = 24
PTRACE_SETOPTIONS = 0x4200
PTRACE_GET_SYSCALL_INFO = 0x420E
PTRACE_O_TRACESYSGOOD = 0x00000001
PTRACE_O_TRACEFORK = 0x00000002
PTRACE_O_TRACEVFORK = 0x00000004
PTRACE_O_TRACECLONE = 0x00000008
PTRACE_O_EXITKILL = 0x00100000
PTRACE_SYSCALL_INFO_ENTRY = 1
PTRACE_SYSCALL_INFO_EXIT = 2
PTRACE_SYSCALL_STOP = signal.SIGTRAP | 0x80
WAIT_ALL_TRACED = 0x40000000
WAIT_NOHANG = os.WNOHANG
_IOC_NRBITS = 8
_IOC_TYPEBITS = 8
_IOC_SIZEBITS = 14
_IOC_NRSHIFT = 0
_IOC_TYPESHIFT = _IOC_NRSHIFT + _IOC_NRBITS
_IOC_SIZESHIFT = _IOC_TYPESHIFT + _IOC_TYPEBITS
_IOC_DIRSHIFT = _IOC_SIZESHIFT + _IOC_SIZEBITS
_IOC_WRITE = 1
_IOC_READ = 2
_SECCOMP_IOC_MAGIC = ord("!")
_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_LEDGER_KEYS = frozenset(
    {
        "HARNESS_ACTIVE_ENGAGEMENT",
        "HARNESS_EXPECTED_LEDGER_HASH",
        "HARNESS_EXPECTED_SOURCE_HASHES",
        "HARNESS_EXPECTED_RUNTIME_SESSION_REF",
    }
)
_COGNITIVE_KEYS = frozenset(
    {
        "HARNESS_COGNITIVE_PRINCIPAL",
        "HARNESS_HUNTER_VIEW_DIGEST",
    }
)
_AUTH_KEYS = frozenset(
    {
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "CLAUDE_CODE_OAUTH_TOKEN",
        "ANTHROPIC_BASE_URL",
    }
)
_UNAVAILABLE_TRACE_SYSCALLS = (
    AARCH64_NR_IO_SETUP,
    AARCH64_NR_IO_DESTROY,
    AARCH64_NR_IO_SUBMIT,
    AARCH64_NR_IO_CANCEL,
    AARCH64_NR_IO_GETEVENTS,
    AARCH64_NR_WRITEV,
    AARCH64_NR_PWRITEV,
    AARCH64_NR_SENDFILE,
    AARCH64_NR_SPLICE,
    AARCH64_NR_PROCESS_VM_WRITEV,
    AARCH64_NR_SECCOMP,
    AARCH64_NR_COPY_FILE_RANGE,
    AARCH64_NR_PWRITEV2,
    AARCH64_NR_IO_PGETEVENTS,
    AARCH64_NR_IO_URING_SETUP,
    AARCH64_NR_IO_URING_ENTER,
    AARCH64_NR_IO_URING_REGISTER,
    AARCH64_NR_CLONE3,
)
_INHERITED_RUNTIME_KEYS = frozenset(
    {
        "PATH",
        "HOME",
        "USER",
        "LOGNAME",
        "SHELL",
        "TMPDIR",
        "TMP",
        "TEMP",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "TERM",
        "COLORTERM",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "NODE_EXTRA_CA_CERTS",
    }
)


class SupervisorError(RuntimeError):
    pass


class _SockFilter(ctypes.Structure):
    _fields_ = (
        ("code", ctypes.c_ushort),
        ("jt", ctypes.c_ubyte),
        ("jf", ctypes.c_ubyte),
        ("k", ctypes.c_uint),
    )


class _SockFprog(ctypes.Structure):
    _fields_ = (
        ("length", ctypes.c_ushort),
        ("filters", ctypes.POINTER(_SockFilter)),
    )


class _SeccompData(ctypes.Structure):
    _fields_ = (
        ("number", ctypes.c_int),
        ("architecture", ctypes.c_uint32),
        ("instruction_pointer", ctypes.c_uint64),
        ("arguments", ctypes.c_uint64 * 6),
    )


class _SeccompNotif(ctypes.Structure):
    _fields_ = (
        ("identifier", ctypes.c_uint64),
        ("pid", ctypes.c_uint32),
        ("flags", ctypes.c_uint32),
        ("data", _SeccompData),
    )


class _SeccompNotifResp(ctypes.Structure):
    _fields_ = (
        ("identifier", ctypes.c_uint64),
        ("value", ctypes.c_int64),
        ("error", ctypes.c_int32),
        ("flags", ctypes.c_uint32),
    )


class _SeccompNotifSizes(ctypes.Structure):
    _fields_ = (
        ("notif", ctypes.c_uint16),
        ("notif_resp", ctypes.c_uint16),
        ("data", ctypes.c_uint16),
    )


class _IOVec(ctypes.Structure):
    _fields_ = (
        ("base", ctypes.c_void_p),
        ("length", ctypes.c_size_t),
    )


def _ioctl_number(direction: int, number: int, size: int) -> int:
    return (
        direction << _IOC_DIRSHIFT
        | _SECCOMP_IOC_MAGIC << _IOC_TYPESHIFT
        | number << _IOC_NRSHIFT
        | size << _IOC_SIZESHIFT
    )


SECCOMP_IOCTL_NOTIF_RECV = _ioctl_number(
    _IOC_READ | _IOC_WRITE, 0, ctypes.sizeof(_SeccompNotif)
)
SECCOMP_IOCTL_NOTIF_SEND = _ioctl_number(
    _IOC_READ | _IOC_WRITE, 1, ctypes.sizeof(_SeccompNotifResp)
)
SECCOMP_IOCTL_NOTIF_ID_VALID = _ioctl_number(
    _IOC_WRITE, 2, ctypes.sizeof(ctypes.c_uint64)
)


@dataclass(frozen=True)
class _SyscallObservation:
    operation: int
    number: int | None
    arguments: tuple[int, ...]
    result: int | None
    is_error: bool


@dataclass(frozen=True)
class _BrokeredWriteResult:
    value: int
    error: int
    storage_exhausted: bool


def _socket_policy(family: int, kind: int, protocol: int) -> bool:
    base_kind = kind & 0xF
    return bool(
        family == socket.AF_UNIX
        and base_kind in {socket.SOCK_STREAM, socket.SOCK_SEQPACKET}
        and protocol == 0
        or family == socket.AF_INET
        and base_kind == socket.SOCK_STREAM
        and protocol in {0, socket.IPPROTO_TCP}
    )


def _harden_process_memory() -> None:
    """Prevent the same-UID model child from reading PID 1 memory through ptrace/procfs."""

    if not sys.platform.startswith("linux"):
        return
    _set_process_dumpable(False)


def _set_process_dumpable(enabled: bool) -> None:
    """Set the Linux dumpability bit without leaking kernel details to model output."""

    if not sys.platform.startswith("linux"):
        raise SupervisorError("process_hardening_unavailable")
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        result = libc.prctl(PR_SET_DUMPABLE, int(enabled), 0, 0, 0)
    except (AttributeError, OSError) as exc:
        raise SupervisorError("process_hardening_unavailable") from exc
    if result != 0:
        raise SupervisorError("process_hardening_unavailable")


def _require_zero_runtime_privileges() -> None:
    """Fail closed unless the process has no usable capability and cannot gain one."""

    try:
        status = Path("/proc/self/status").read_text(encoding="ascii")
    except (OSError, UnicodeError) as exc:
        raise SupervisorError("process_privileges_unverifiable") from exc
    fields: dict[str, str] = {}
    for line in status.splitlines():
        key, separator, value = line.partition(":")
        if separator:
            fields[key] = value.strip()
    if any(
        fields.get(key) != "0000000000000000"
        for key in ("CapInh", "CapPrm", "CapEff", "CapAmb")
    ):
        raise SupervisorError("process_privileges_invalid")
    if fields.get("NoNewPrivs") != "1":
        raise SupervisorError("process_privileges_invalid")


def _ptrace(request: int, pid: int, *, address: int = 0, data: int = 0) -> int:
    """Issue one ptrace operation without exposing kernel errors to model output."""

    if not sys.platform.startswith("linux"):
        raise SupervisorError("ptrace_unavailable")
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        operation = libc.ptrace
        operation.restype = ctypes.c_long
        ctypes.set_errno(0)
        result = operation(
            request,
            pid,
            ctypes.c_void_p(address),
            ctypes.c_void_p(data),
        )
    except (AttributeError, OSError, TypeError, ValueError) as exc:
        raise SupervisorError("ptrace_unavailable") from exc
    if result == -1 and ctypes.get_errno() != 0:
        raise SupervisorError("ptrace_unavailable")
    return int(result)


def _syscall(number: int, *arguments: object) -> int:
    """Call one Linux syscall and preserve its errno as an ``OSError``."""

    if not sys.platform.startswith("linux"):
        raise OSError(errno.ENOSYS, "linux syscall unavailable")
    libc = ctypes.CDLL(None, use_errno=True)
    operation = libc.syscall
    operation.restype = ctypes.c_long
    ctypes.set_errno(0)
    result = int(operation(ctypes.c_long(number), *arguments))
    error_number = ctypes.get_errno()
    if result == -1 and error_number:
        raise OSError(error_number, os.strerror(error_number))
    return result


def _seccomp_notification_sizes() -> _SeccompNotifSizes:
    sizes = _SeccompNotifSizes()
    try:
        _syscall(
            AARCH64_NR_SECCOMP,
            ctypes.c_uint(SECCOMP_GET_NOTIF_SIZES),
            ctypes.c_uint(0),
            ctypes.byref(sizes),
        )
    except (AttributeError, OSError, TypeError, ValueError) as exc:
        raise SupervisorError("write_broker_unavailable") from exc
    if (
        sizes.notif != ctypes.sizeof(_SeccompNotif)
        or sizes.notif_resp != ctypes.sizeof(_SeccompNotifResp)
        or sizes.data != ctypes.sizeof(_SeccompData)
    ):
        raise SupervisorError("write_broker_abi_unsupported")
    return sizes


def _seccomp_ioctl(descriptor: int, request: int, value: object) -> None:
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        operation = libc.ioctl
        operation.restype = ctypes.c_int
        ctypes.set_errno(0)
        result = operation(
            ctypes.c_int(descriptor),
            ctypes.c_ulong(request),
            ctypes.byref(value),
        )
    except (AttributeError, OSError, TypeError, ValueError) as exc:
        raise OSError(errno.ENOSYS, "seccomp notification ioctl unavailable") from exc
    error_number = ctypes.get_errno()
    if result == -1:
        raise OSError(error_number or errno.EIO, os.strerror(error_number or errno.EIO))


def _notification_id_valid(descriptor: int, identifier: int) -> None:
    value = ctypes.c_uint64(identifier)
    _seccomp_ioctl(descriptor, SECCOMP_IOCTL_NOTIF_ID_VALID, value)


def _tracee_process_id(thread_id: int) -> int:
    """Resolve a notification TID to its thread-group leader while the task is blocked."""

    try:
        with open(f"/proc/{thread_id}/status", "r", encoding="ascii") as stream:
            status = stream.read(16 * 1024 + 1)
    except (OSError, UnicodeError) as exc:
        raise SupervisorError("write_broker_tracee_unavailable") from exc
    if len(status) > 16 * 1024:
        raise SupervisorError("write_broker_tracee_invalid")
    matches = [
        line.removeprefix("Tgid:").strip()
        for line in status.splitlines()
        if line.startswith("Tgid:")
    ]
    if len(matches) != 1 or not matches[0].isdigit():
        raise SupervisorError("write_broker_tracee_invalid")
    process_id = int(matches[0])
    if process_id <= 0:
        raise SupervisorError("write_broker_tracee_invalid")
    return process_id


def _pidfd_getfd(thread_id: int, target_descriptor: int) -> int:
    """Duplicate a tracee descriptor into PID 1 from a stable open-file description."""

    if thread_id <= 0 or target_descriptor < 0 or target_descriptor > 2**31 - 1:
        raise OSError(errno.EBADF, os.strerror(errno.EBADF))
    process_descriptor = _syscall(
        AARCH64_NR_PIDFD_OPEN,
        ctypes.c_int(thread_id),
        ctypes.c_uint(PIDFD_THREAD),
    )
    try:
        return _syscall(
            AARCH64_NR_PIDFD_GETFD,
            ctypes.c_int(process_descriptor),
            ctypes.c_int(target_descriptor),
            ctypes.c_uint(0),
        )
    finally:
        os.close(process_descriptor)


def _read_tracee_memory(thread_id: int, address: int, count: int) -> bytes:
    if count < 0 or count > MAX_EMULATED_WRITE_BYTES:
        raise SupervisorError("write_broker_request_too_large")
    if count == 0:
        return b""
    process_id = _tracee_process_id(thread_id)
    buffer = ctypes.create_string_buffer(count)
    local = _IOVec(ctypes.addressof(buffer), count)
    remote = _IOVec(address, count)
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        operation = libc.process_vm_readv
        operation.restype = ctypes.c_ssize_t
        operation.argtypes = (
            ctypes.c_int,
            ctypes.POINTER(_IOVec),
            ctypes.c_ulong,
            ctypes.POINTER(_IOVec),
            ctypes.c_ulong,
            ctypes.c_ulong,
        )
        ctypes.set_errno(0)
        copied = int(
            operation(
                process_id,
                ctypes.byref(local),
                1,
                ctypes.byref(remote),
                1,
                0,
            )
        )
    except (AttributeError, OSError, TypeError, ValueError) as exc:
        raise SupervisorError("write_broker_memory_unavailable") from exc
    if copied == -1:
        error_number = ctypes.get_errno() or errno.EIO
        raise OSError(error_number, os.strerror(error_number))
    if copied != count:
        raise OSError(errno.EFAULT, os.strerror(errno.EFAULT))
    return buffer.raw[:count]


def _tracee_filter_instructions() -> tuple[_SockFilter, ...]:
    """Deny paths through which a tracee could perform unobserved storage allocation.

    Every ordinary syscall is observed at exit by ptrace. Scalar writes are instead brokered by
    PID 1 through seccomp user notification so their descriptor identity and result are one stable
    operation. The inherited filter prevents
    ``CLONE_UNTRACED`` (and ``clone3``, whose pointed-to flags classic BPF cannot inspect) from
    escaping descendant tracing. Kernel async-I/O setup is denied because its eventual completion
    status is not a syscall return visible to ptrace. Ambiguous regular-file transfer syscalls and
    file-backed shared mappings are denied so a positive partial result cannot be erased by a
    sibling cleanup race before the tracer observes capacity. Unreviewed future syscall numbers are
    unavailable until this arm64 matrix is updated.
    """

    load_word = BPF_LD | BPF_W | BPF_ABS
    jump_equal = BPF_JMP | BPF_JEQ | BPF_K
    jump_greater_equal = BPF_JMP | BPF_JGE | BPF_K
    jump_set = BPF_JMP | BPF_JSET | BPF_K
    return_value = BPF_RET | BPF_K
    unavailable = SECCOMP_RET_ERRNO | errno.ENOSYS
    clone_escape_denied = SECCOMP_RET_ERRNO | errno.EPERM
    instructions = [
        _SockFilter(load_word, 0, 0, SECCOMP_DATA_ARCH_OFFSET),
        _SockFilter(jump_equal, 1, 0, AUDIT_ARCH_AARCH64),
        _SockFilter(return_value, 0, 0, SECCOMP_RET_KILL_PROCESS),
        _SockFilter(load_word, 0, 0, SECCOMP_DATA_NR_OFFSET),
        _SockFilter(jump_equal, 0, 1, AARCH64_NR_WRITE),
        _SockFilter(return_value, 0, 0, SECCOMP_RET_USER_NOTIF),
        _SockFilter(jump_equal, 0, 1, AARCH64_NR_PWRITE64),
        _SockFilter(return_value, 0, 0, SECCOMP_RET_USER_NOTIF),
        _SockFilter(jump_equal, 0, 1, AARCH64_NR_SOCKET),
        _SockFilter(return_value, 0, 0, SECCOMP_RET_USER_NOTIF),
        _SockFilter(jump_equal, 0, 1, AARCH64_NR_SOCKETPAIR),
        _SockFilter(return_value, 0, 0, SECCOMP_RET_USER_NOTIF),
        _SockFilter(jump_equal, 0, 1, AARCH64_NR_CONNECT),
        _SockFilter(return_value, 0, 0, SECCOMP_RET_USER_NOTIF),
    ]
    for syscall_number in _UNAVAILABLE_TRACE_SYSCALLS:
        instructions.extend(
            (
                _SockFilter(jump_equal, 0, 1, syscall_number),
                _SockFilter(return_value, 0, 0, unavailable),
            )
        )
    for syscall_number in (
        AARCH64_NR_BIND,
        AARCH64_NR_LISTEN,
        AARCH64_NR_ACCEPT,
        AARCH64_NR_ACCEPT4,
    ):
        instructions.extend(
            (
                _SockFilter(jump_equal, 0, 1, syscall_number),
                _SockFilter(return_value, 0, 0, clone_escape_denied),
            )
        )
    instructions.extend(
        (
            # TCP Fast Open can combine an unobserved destination with the first payload.  Ordinary
            # send variants remain available for already-brokered stream sockets.
            _SockFilter(jump_equal, 0, 3, AARCH64_NR_SENDTO),
            _SockFilter(load_word, 0, 0, SECCOMP_DATA_ARG3_OFFSET),
            _SockFilter(jump_set, 0, 1, getattr(socket, "MSG_FASTOPEN", 0x20000000)),
            _SockFilter(return_value, 0, 0, clone_escape_denied),
            _SockFilter(load_word, 0, 0, SECCOMP_DATA_NR_OFFSET),
            _SockFilter(jump_equal, 0, 3, AARCH64_NR_SENDMSG),
            _SockFilter(load_word, 0, 0, SECCOMP_DATA_ARG2_OFFSET),
            _SockFilter(jump_set, 0, 1, getattr(socket, "MSG_FASTOPEN", 0x20000000)),
            _SockFilter(return_value, 0, 0, clone_escape_denied),
            _SockFilter(load_word, 0, 0, SECCOMP_DATA_NR_OFFSET),
            _SockFilter(jump_equal, 0, 3, AARCH64_NR_SENDMMSG),
            _SockFilter(load_word, 0, 0, SECCOMP_DATA_ARG3_OFFSET),
            _SockFilter(jump_set, 0, 1, getattr(socket, "MSG_FASTOPEN", 0x20000000)),
            _SockFilter(return_value, 0, 0, clone_escape_denied),
            _SockFilter(load_word, 0, 0, SECCOMP_DATA_NR_OFFSET),
            # File-backed MAP_SHARED pages can be dirtied by any syscall that writes to user
            # memory. Reject them; anonymous shared memory remains memory-cgroup bounded.
            _SockFilter(jump_equal, 0, 4, AARCH64_NR_MMAP),
            _SockFilter(load_word, 0, 0, SECCOMP_DATA_ARG3_OFFSET),
            _SockFilter(jump_set, 0, 2, MAP_SHARED),
            _SockFilter(jump_set, 1, 0, MAP_ANONYMOUS),
            _SockFilter(return_value, 0, 0, unavailable),
            _SockFilter(load_word, 0, 0, SECCOMP_DATA_NR_OFFSET),
            _SockFilter(jump_equal, 0, 5, AARCH64_NR_CLONE),
            _SockFilter(load_word, 0, 0, SECCOMP_DATA_ARG0_OFFSET),
            _SockFilter(jump_set, 2, 0, CLONE_UNTRACED),
            _SockFilter(jump_set, 0, 2, CLONE_THREAD),
            _SockFilter(jump_set, 1, 0, CLONE_FILES),
            _SockFilter(return_value, 0, 0, clone_escape_denied),
            _SockFilter(load_word, 0, 0, SECCOMP_DATA_NR_OFFSET),
            _SockFilter(jump_equal, 0, 3, AARCH64_NR_UNSHARE),
            _SockFilter(load_word, 0, 0, SECCOMP_DATA_ARG0_OFFSET),
            _SockFilter(jump_set, 0, 1, CLONE_FILES),
            _SockFilter(return_value, 0, 0, clone_escape_denied),
            _SockFilter(load_word, 0, 0, SECCOMP_DATA_NR_OFFSET),
            _SockFilter(jump_equal, 0, 3, AARCH64_NR_CLOSE_RANGE),
            _SockFilter(load_word, 0, 0, SECCOMP_DATA_ARG2_OFFSET),
            _SockFilter(jump_set, 0, 1, CLOSE_RANGE_UNSHARE),
            _SockFilter(return_value, 0, 0, clone_escape_denied),
            _SockFilter(load_word, 0, 0, SECCOMP_DATA_NR_OFFSET),
            _SockFilter(jump_equal, 0, 3, AARCH64_NR_PRCTL),
            _SockFilter(load_word, 0, 0, SECCOMP_DATA_ARG0_OFFSET),
            _SockFilter(jump_equal, 0, 1, PR_SET_SECCOMP),
            _SockFilter(return_value, 0, 0, unavailable),
            _SockFilter(load_word, 0, 0, SECCOMP_DATA_NR_OFFSET),
            _SockFilter(jump_greater_equal, 0, 1, AARCH64_REVIEWED_SYSCALL_LIMIT),
            _SockFilter(return_value, 0, 0, unavailable),
            _SockFilter(return_value, 0, 0, SECCOMP_RET_ALLOW),
        )
    )
    return tuple(instructions)


def _install_tracee_filter() -> int:
    if not sys.platform.startswith("linux") or os.uname().machine not in {
        "aarch64",
        "arm64",
    }:
        raise SupervisorError("tracee_platform_unsupported")
    instructions = _tracee_filter_instructions()
    array_type = _SockFilter * len(instructions)
    array = array_type(*instructions)
    program = _SockFprog(len(array), array)
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        if libc.prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0:
            raise SupervisorError("tracee_filter_unavailable")
        return _syscall(
            AARCH64_NR_SECCOMP,
            ctypes.c_uint(SECCOMP_SET_MODE_FILTER),
            ctypes.c_uint(
                SECCOMP_FILTER_FLAG_NEW_LISTENER
                | SECCOMP_FILTER_FLAG_WAIT_KILLABLE_RECV
            ),
            ctypes.byref(program),
        )
    except (AttributeError, OSError, TypeError, ValueError) as exc:
        raise SupervisorError("tracee_filter_unavailable") from exc


def _send_listener_descriptor(transport_descriptor: int, listener_descriptor: int) -> None:
    descriptors = array.array("i", [listener_descriptor])
    try:
        with socket.socket(fileno=transport_descriptor) as transport:
            sent = transport.sendmsg(
                [b"L"],
                [(socket.SOL_SOCKET, socket.SCM_RIGHTS, descriptors.tobytes())],
            )
    except OSError as exc:
        raise SupervisorError("write_broker_handoff_failed") from exc
    if sent != 1:
        raise SupervisorError("write_broker_handoff_failed")


def _receive_listener_descriptor(transport: socket.socket) -> int:
    item_size = array.array("i").itemsize
    transport.settimeout(TRACE_BOOTSTRAP_TIMEOUT_SECONDS)
    try:
        message, ancillary, flags, _address = transport.recvmsg(
            1, socket.CMSG_SPACE(item_size)
        )
    except (OSError, TimeoutError) as exc:
        raise SupervisorError("write_broker_handoff_failed") from exc
    received: list[int] = []
    try:
        for level, kind, raw in ancillary:
            if level != socket.SOL_SOCKET or kind != socket.SCM_RIGHTS:
                continue
            values = array.array("i")
            values.frombytes(raw[: len(raw) - len(raw) % item_size])
            received.extend(values.tolist())
        if (
            message != b"L"
            or flags & (socket.MSG_CTRUNC | socket.MSG_TRUNC)
            or len(received) != 1
            or received[0] < 0
        ):
            raise SupervisorError("write_broker_handoff_failed")
        return received.pop()
    finally:
        for descriptor in received:
            try:
                os.close(descriptor)
            except OSError:
                pass


def _wait_for_trace_stop(pid: int) -> None:
    deadline = time.monotonic() + TRACE_BOOTSTRAP_TIMEOUT_SECONDS
    while True:
        try:
            waited_pid, status = os.waitpid(pid, WAIT_NOHANG)
        except ChildProcessError as exc:
            raise SupervisorError("ptrace_start_failed") from exc
        if waited_pid == pid:
            if os.WIFSTOPPED(status) and os.WSTOPSIG(status) == signal.SIGSTOP:
                return
            raise SupervisorError("ptrace_start_failed")
        if waited_pid != 0 or time.monotonic() >= deadline:
            raise SupervisorError("ptrace_start_failed")
        time.sleep(0.005)


def _trace_child(command: list[str], transport_descriptor: int) -> int:
    """Become traceable, hand PID 1 the inherited filter listener, then exec the model."""

    if (
        not command
        or not command[0].startswith("/")
        or transport_descriptor < 3
    ):
        raise SupervisorError("trace_child_command_invalid")
    _ptrace(PTRACE_TRACEME, 0)
    os.kill(os.getpid(), signal.SIGSTOP)
    _require_zero_runtime_privileges()
    # PID 1 stays non-dumpable. Only this contained, already traced descendant tree is made
    # inspectable so the parent can duplicate the exact descriptor named by a notification.
    _set_process_dumpable(True)
    listener_descriptor = _install_tracee_filter()
    try:
        _send_listener_descriptor(transport_descriptor, listener_descriptor)
    finally:
        os.close(listener_descriptor)
    os.kill(os.getpid(), signal.SIGSTOP)
    try:
        os.execv(command[0], command)
    except OSError as exc:
        raise SupervisorError("model_launch_failed") from exc


def _bounded_storage_devices() -> frozenset[int]:
    devices: set[int] = set()
    for path in (SCRATCH_PATH, SHM_PATH):
        try:
            entry = path.stat()
        except OSError as exc:
            raise SupervisorError("storage_unavailable") from exc
        if not stat.S_ISDIR(entry.st_mode):
            raise SupervisorError("storage_unavailable")
        devices.add(entry.st_dev)
    return frozenset(devices)


def _emulate_brokered_write(
    notification: _SeccompNotif,
    bounded_devices: frozenset[int],
    listener_descriptor: int,
) -> _BrokeredWriteResult:
    if (
        notification.flags != 0
        or notification.data.architecture != AUDIT_ARCH_AARCH64
        or notification.data.number not in {AARCH64_NR_WRITE, AARCH64_NR_PWRITE64}
    ):
        raise SupervisorError("write_broker_notification_invalid")
    _notification_id_valid(listener_descriptor, int(notification.identifier))
    arguments = tuple(int(value) for value in notification.data.arguments)
    target_descriptor, address, count = arguments[:3]
    if target_descriptor > 2**31 - 1 or count > MAX_EMULATED_WRITE_BYTES:
        raise SupervisorError("write_broker_request_invalid")
    try:
        duplicate = _pidfd_getfd(int(notification.pid), int(target_descriptor))
    except OSError as exc:
        if exc.errno == errno.EBADF:
            return _BrokeredWriteResult(0, -errno.EBADF, False)
        raise SupervisorError("write_broker_descriptor_unavailable") from exc
    try:
        try:
            payload = _read_tracee_memory(int(notification.pid), address, count)
        except OSError as exc:
            if exc.errno in {errno.EFAULT, errno.EINVAL}:
                return _BrokeredWriteResult(0, -errno.EFAULT, False)
            raise SupervisorError("write_broker_memory_unavailable") from exc
        try:
            entry = os.fstat(duplicate)
        except OSError as exc:
            raise SupervisorError("write_broker_descriptor_unavailable") from exc
        bounded = stat.S_ISREG(entry.st_mode) and entry.st_dev in bounded_devices
        # The task may disappear while PID 1 copies its pointer arguments. Revalidate immediately
        # before the only side effect; USER_NOTIF_FLAG_CONTINUE is never used.
        _notification_id_valid(listener_descriptor, int(notification.identifier))
        try:
            if notification.data.number == AARCH64_NR_WRITE:
                result = os.write(duplicate, payload)
            else:
                offset = ctypes.c_int64(arguments[3]).value
                result = os.pwrite(duplicate, payload, offset)
        except OSError as exc:
            error_number = exc.errno or errno.EIO
            return _BrokeredWriteResult(
                0,
                -error_number,
                bounded and error_number in {errno.ENOSPC, errno.EDQUOT},
            )
        return _BrokeredWriteResult(
            result,
            0,
            bounded and 0 < result < count,
        )
    finally:
        os.close(duplicate)


def _emulate_brokered_connect(
    notification: _SeccompNotif,
    listener_descriptor: int,
    provider_endpoint: tuple[str, int],
) -> _BrokeredWriteResult:
    """Connect the exact tracee socket to PID 1 using one immutable sockaddr copy."""

    if (
        notification.flags != 0
        or notification.data.architecture != AUDIT_ARCH_AARCH64
        or notification.data.number != AARCH64_NR_CONNECT
    ):
        raise SupervisorError("network_broker_notification_invalid")
    _notification_id_valid(listener_descriptor, int(notification.identifier))
    target_descriptor, address, count = (
        int(notification.data.arguments[index]) for index in range(3)
    )
    if target_descriptor > 2**31 - 1 or count < 2 or count > 128:
        return _BrokeredWriteResult(0, -errno.EINVAL, False)
    try:
        copied = _read_tracee_memory(int(notification.pid), address, count)
    except OSError as exc:
        if exc.errno in {errno.EFAULT, errno.EINVAL}:
            return _BrokeredWriteResult(0, -errno.EFAULT, False)
        raise SupervisorError("network_broker_memory_unavailable") from exc
    family = struct.unpack_from("=H", copied)[0]
    if family == socket.AF_INET and count >= 16:
        destination: str | tuple[str, int] = provider_endpoint
    elif family == socket.AF_UNIX:
        raw_path = copied[2:].split(b"\0", 1)[0]
        if raw_path != os.fsencode(BROKER_RELAY_PATH):
            return _BrokeredWriteResult(0, -errno.EACCES, False)
        destination = str(BROKER_RELAY_PATH)
    else:
        return _BrokeredWriteResult(0, -errno.EAFNOSUPPORT, False)
    try:
        duplicate = _pidfd_getfd(int(notification.pid), target_descriptor)
    except OSError as exc:
        if exc.errno == errno.EBADF:
            return _BrokeredWriteResult(0, -errno.EBADF, False)
        raise SupervisorError("network_broker_descriptor_unavailable") from exc
    wrapped: socket.socket | None = None
    try:
        wrapped = socket.socket(fileno=duplicate)
        if (
            wrapped.family != family
            or wrapped.type & 0xF != socket.SOCK_STREAM
            or family == socket.AF_INET
            and wrapped.proto not in {0, socket.IPPROTO_TCP}
            or family == socket.AF_UNIX
            and wrapped.proto != 0
        ):
            return _BrokeredWriteResult(0, -errno.EPROTOTYPE, False)
        _notification_id_valid(listener_descriptor, int(notification.identifier))
        try:
            wrapped.connect(destination)
        except OSError as exc:
            return _BrokeredWriteResult(0, -(exc.errno or errno.EIO), False)
        return _BrokeredWriteResult(0, 0, False)
    finally:
        if wrapped is not None:
            try:
                wrapped.detach()
            except (AttributeError, OSError):
                pass
        os.close(duplicate)


def _continue_socket_notification(notification: _SeccompNotif) -> _SeccompNotifResp:
    arguments = tuple(int(value) for value in notification.data.arguments)
    if notification.data.number == AARCH64_NR_SOCKET:
        allowed = _socket_policy(*arguments[:3])
    elif notification.data.number == AARCH64_NR_SOCKETPAIR:
        allowed = (
            arguments[0] == socket.AF_UNIX
            and _socket_policy(*arguments[:3])
        )
    else:
        raise SupervisorError("network_broker_notification_invalid")
    return _SeccompNotifResp(
        identifier=notification.identifier,
        value=0,
        error=0 if allowed else -errno.EAFNOSUPPORT,
        flags=SECCOMP_USER_NOTIF_FLAG_CONTINUE if allowed else 0,
    )


class _WriteBroker:
    """Own one seccomp listener and emulate scalar writes without ``CONTINUE`` races."""

    def __init__(
        self,
        listener_descriptor: int,
        bounded_devices: frozenset[int],
        tracee_pid: int,
        provider_endpoint: tuple[str, int] = ("127.0.0.1", 9),
    ) -> None:
        self._listener_descriptor = listener_descriptor
        self._bounded_devices = bounded_devices
        self._tracee_pid = tracee_pid
        self._provider_endpoint = provider_endpoint
        self._stop = threading.Event()
        self.storage_exhausted = threading.Event()
        self.failed = threading.Event()
        self._thread = threading.Thread(target=self._serve_guarded, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def _fail_notification(self, notification: _SeccompNotif) -> None:
        response = _SeccompNotifResp(
            identifier=notification.identifier,
            value=0,
            error=-errno.EIO,
            flags=0,
        )
        try:
            _seccomp_ioctl(
                self._listener_descriptor, SECCOMP_IOCTL_NOTIF_SEND, response
            )
        except OSError:
            pass

    def _mark_failed(self) -> None:
        self.failed.set()
        try:
            os.kill(self._tracee_pid, signal.SIGKILL)
        except OSError:
            pass

    def _serve_guarded(self) -> None:
        try:
            self._serve()
        except BaseException:
            if not self._stop.is_set():
                self._mark_failed()

    def _serve(self) -> None:
        while not self._stop.is_set():
            try:
                ready, _writable, _exceptional = select.select(
                    [self._listener_descriptor], [], [], 0.05
                )
            except (OSError, ValueError):
                if not self._stop.is_set():
                    self._mark_failed()
                return
            if not ready:
                continue
            notification = _SeccompNotif()
            try:
                _seccomp_ioctl(
                    self._listener_descriptor,
                    SECCOMP_IOCTL_NOTIF_RECV,
                    notification,
                )
            except OSError as exc:
                if exc.errno in {errno.EINTR, errno.ENOENT}:
                    continue
                if not self._stop.is_set():
                    self._mark_failed()
                return
            try:
                if notification.data.number in {AARCH64_NR_SOCKET, AARCH64_NR_SOCKETPAIR}:
                    response = _continue_socket_notification(notification)
                    result = None
                elif notification.data.number == AARCH64_NR_CONNECT:
                    result = _emulate_brokered_connect(
                        notification,
                        self._listener_descriptor,
                        self._provider_endpoint,
                    )
                    response = _SeccompNotifResp(
                        identifier=notification.identifier,
                        value=result.value,
                        error=result.error,
                        flags=0,
                    )
                else:
                    result = _emulate_brokered_write(
                        notification,
                        self._bounded_devices,
                        self._listener_descriptor,
                    )
                    response = _SeccompNotifResp(
                        identifier=notification.identifier,
                        value=result.value,
                        error=result.error,
                        flags=0,
                    )
            except OSError as exc:
                if exc.errno == errno.ENOENT:
                    continue
                self._fail_notification(notification)
                self._mark_failed()
                return
            except SupervisorError:
                self._fail_notification(notification)
                self._mark_failed()
                return
            if result is not None and result.storage_exhausted:
                self.storage_exhausted.set()
            try:
                _seccomp_ioctl(
                    self._listener_descriptor,
                    SECCOMP_IOCTL_NOTIF_SEND,
                    response,
                )
            except OSError as exc:
                if exc.errno == errno.ENOENT:
                    continue
                self._mark_failed()
                return

    def close(self) -> None:
        self._stop.set()
        try:
            os.close(self._listener_descriptor)
        except OSError:
            pass
        self._thread.join(timeout=1.0)


def _decode_syscall_info(raw: bytes, returned_size: int) -> _SyscallObservation:
    if not raw:
        raise SupervisorError("ptrace_syscall_info_invalid")
    operation = raw[0]
    if operation == PTRACE_SYSCALL_INFO_ENTRY:
        if returned_size < 80 or len(raw) < 80:
            raise SupervisorError("ptrace_syscall_info_invalid")
        return _SyscallObservation(
            operation=operation,
            number=struct.unpack_from("Q", raw, 24)[0],
            arguments=struct.unpack_from("6Q", raw, 32),
            result=None,
            is_error=False,
        )
    if operation == PTRACE_SYSCALL_INFO_EXIT:
        if returned_size < 33 or len(raw) < 33:
            raise SupervisorError("ptrace_syscall_info_invalid")
        return _SyscallObservation(
            operation=operation,
            number=None,
            arguments=(),
            result=struct.unpack_from("q", raw, 24)[0],
            is_error=bool(raw[32]),
        )
    raise SupervisorError("ptrace_syscall_info_invalid")


def _syscall_exit_is_storage_failure(
    observation: _SyscallObservation, *, syscall_number: int | None
) -> bool:
    return (
        observation.operation == PTRACE_SYSCALL_INFO_EXIT
        and observation.is_error
        and observation.result in {-errno.ENOSPC, -errno.EDQUOT}
        and syscall_number not in {AARCH64_NR_WRITE, AARCH64_NR_PWRITE64}
    )


def _tracee_syscall_observation(pid: int) -> _SyscallObservation:
    information = ctypes.create_string_buffer(128)
    returned_size = _ptrace(
        PTRACE_GET_SYSCALL_INFO,
        pid,
        address=len(information),
        data=ctypes.addressof(information),
    )
    return _decode_syscall_info(information.raw, returned_size)


def _wait_returncode(status: int) -> int:
    if os.WIFEXITED(status):
        return os.WEXITSTATUS(status)
    if os.WIFSIGNALED(status):
        return -os.WTERMSIG(status)
    raise SupervisorError("ptrace_wait_invalid")


def _run_traced_command(
    command: list[str],
    environment: dict[str, str],
    provider_endpoint: tuple[str, int] = ("127.0.0.1", 9),
) -> int:
    """Run one model process and permanently latch storage failures from every descendant."""

    if not sys.platform.startswith("linux"):
        raise SupervisorError("ptrace_unavailable")
    _require_zero_runtime_privileges()
    _seccomp_notification_sizes()
    bounded_devices = _bounded_storage_devices()
    try:
        parent_transport, child_transport = socket.socketpair(
            socket.AF_UNIX, socket.SOCK_SEQPACKET
        )
    except OSError as exc:
        raise SupervisorError("write_broker_handoff_failed") from exc
    launcher = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--trace-child",
        str(child_transport.fileno()),
        "--",
        *command,
    ]
    process: subprocess.Popen[bytes] | None = None
    broker: _WriteBroker | None = None
    try:
        try:
            process = subprocess.Popen(
                launcher,
                stdin=subprocess.DEVNULL,
                stdout=None,
                stderr=None,
                env=environment,
                cwd=WORKSPACE_PATH,
                start_new_session=True,
                pass_fds=(child_transport.fileno(),),
            )
        except OSError as exc:
            raise SupervisorError("model_launch_failed") from exc
        child_transport.close()
        _wait_for_trace_stop(process.pid)
        options = (
            PTRACE_O_TRACESYSGOOD
            | PTRACE_O_TRACEFORK
            | PTRACE_O_TRACEVFORK
            | PTRACE_O_TRACECLONE
            | PTRACE_O_EXITKILL
        )
        _ptrace(PTRACE_SETOPTIONS, process.pid, data=options)
        _ptrace(PTRACE_CONT, process.pid)
        _wait_for_trace_stop(process.pid)
        listener_descriptor = _receive_listener_descriptor(parent_transport)
        # Prove the exact kernel and Docker policy allow stable descriptor duplication before the
        # untrusted executable runs. The duplicate shares stdout's open-file description and is
        # discarded without reading or writing it.
        try:
            bootstrap_duplicate = _pidfd_getfd(process.pid, 1)
        except OSError as exc:
            os.close(listener_descriptor)
            raise SupervisorError("write_broker_bootstrap_failed") from exc
        os.close(bootstrap_duplicate)
        broker = _WriteBroker(
            listener_descriptor, bounded_devices, process.pid, provider_endpoint
        )
        broker.start()
        _ptrace(PTRACE_SYSCALL, process.pid)
        pending_syscalls: dict[int, int] = {}
        while True:
            if broker.storage_exhausted.is_set():
                return STORAGE_EXIT_CODE
            if broker.failed.is_set():
                raise SupervisorError("write_broker_failed")
            try:
                waited_pid, status = os.waitpid(-1, WAIT_ALL_TRACED)
            except ChildProcessError as exc:
                raise SupervisorError("ptrace_wait_failed") from exc
            if broker.storage_exhausted.is_set():
                return STORAGE_EXIT_CODE
            if broker.failed.is_set():
                raise SupervisorError("write_broker_failed")
            if os.WIFEXITED(status) or os.WIFSIGNALED(status):
                pending_syscalls.pop(waited_pid, None)
                if waited_pid != process.pid:
                    continue
                raw_returncode = _wait_returncode(status)
                process.returncode = raw_returncode
                if broker.storage_exhausted.is_set():
                    return STORAGE_EXIT_CODE
                if broker.failed.is_set():
                    raise SupervisorError("write_broker_failed")
                if _storage_exhausted():
                    return STORAGE_EXIT_CODE
                return _returncode(raw_returncode)
            if not os.WIFSTOPPED(status):
                raise SupervisorError("ptrace_wait_invalid")
            stop_signal = os.WSTOPSIG(status)
            if stop_signal == PTRACE_SYSCALL_STOP:
                observation = _tracee_syscall_observation(waited_pid)
                if observation.operation == PTRACE_SYSCALL_INFO_ENTRY:
                    if observation.number is None:
                        raise SupervisorError("ptrace_syscall_info_invalid")
                    pending_syscalls[waited_pid] = observation.number
                else:
                    syscall_number = pending_syscalls.pop(waited_pid, None)
                    if _syscall_exit_is_storage_failure(
                        observation, syscall_number=syscall_number
                    ):
                        return STORAGE_EXIT_CODE
                if broker.storage_exhausted.is_set():
                    return STORAGE_EXIT_CODE
                if broker.failed.is_set():
                    raise SupervisorError("write_broker_failed")
                if _storage_exhausted():
                    return STORAGE_EXIT_CODE
            if stop_signal == signal.SIGBUS:
                return STORAGE_EXIT_CODE
            if stop_signal == signal.SIGXFSZ:
                return STORAGE_EXIT_CODE
            delivered_signal = 0
            if stop_signal not in {
                PTRACE_SYSCALL_STOP,
                signal.SIGSTOP,
                signal.SIGTRAP,
            }:
                delivered_signal = stop_signal
            _ptrace(PTRACE_SYSCALL, waited_pid, data=delivered_signal)
    finally:
        child_transport.close()
        parent_transport.close()
        if process is not None:
            _terminate_child(process)
        if broker is not None:
            broker.close()


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise SupervisorError("duplicate_json_key")
        value[key] = item
    return value


def _sha256(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _read_stable_regular(path: Path, *, max_bytes: int, private: bool) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise SupervisorError("input_invalid") from exc
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_size > max_bytes
            or before.st_uid != os.geteuid()
            or private
            and stat.S_IMODE(before.st_mode) & 0o077
        ):
            raise SupervisorError("input_invalid")
        data = bytearray()
        while True:
            remaining = max_bytes - len(data)
            chunk = os.read(descriptor, min(64 * 1024, remaining + 1))
            if not chunk:
                break
            data.extend(chunk)
            if len(data) > max_bytes:
                raise SupervisorError("input_invalid")
        after = os.fstat(descriptor)
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ):
            raise SupervisorError("input_changed")
        return bytes(data)
    finally:
        os.close(descriptor)


def _parse_json_object(raw: bytes) -> dict[str, Any]:
    try:
        value = json.loads(raw, object_pairs_hook=_reject_duplicate_pairs)
    except SupervisorError:
        raise
    except (UnicodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise SupervisorError("json_invalid") from exc
    if not isinstance(value, dict):
        raise SupervisorError("json_invalid")
    return value


def _validate_session(value: dict[str, Any]) -> tuple[list[str], dict[str, str]]:
    if set(value) != {"schema_version", "command", "environment"} or value.get(
        "schema_version"
    ) != 1:
        raise SupervisorError("session_invalid")
    command = value.get("command")
    environment = value.get("environment")
    if (
        not isinstance(command, list)
        or not command
        or len(command) > MAX_COMMAND_ARGUMENTS
        or any(not isinstance(argument, str) or "\x00" in argument for argument in command)
        or not command[0].startswith("/")
        or sum(len(argument.encode("utf-8")) for argument in command) > MAX_COMMAND_BYTES
        or not isinstance(environment, dict)
        or frozenset(environment) not in {_LEDGER_KEYS, _LEDGER_KEYS | _COGNITIVE_KEYS}
        or any(
            not isinstance(key, str)
            or not isinstance(item, str)
            or not item
            or "\x00" in item
            for key, item in environment.items()
        )
    ):
        raise SupervisorError("session_invalid")
    engagement = environment["HARNESS_ACTIVE_ENGAGEMENT"]
    engagement_path = Path(engagement)
    cognitive = frozenset(environment) == _LEDGER_KEYS | _COGNITIVE_KEYS
    engagement_valid = (
        engagement_path.is_absolute()
        and Path(os.path.normpath(engagement)) == engagement_path
        and (
            (cognitive and engagement_path == Path("/workspace"))
            or (
                not cognitive
                and engagement_path.parent.parent == Path("/workspace")
                and engagement_path.parent.name == "engagements"
            )
        )
    )
    if not engagement_valid:
        raise SupervisorError("session_invalid")
    if cognitive and (
        environment["HARNESS_COGNITIVE_PRINCIPAL"] != "hunter"
        or _SHA256_RE.fullmatch(environment["HARNESS_HUNTER_VIEW_DIGEST"]) is None
    ):
        raise SupervisorError("session_invalid")
    if _SHA256_RE.fullmatch(environment["HARNESS_EXPECTED_LEDGER_HASH"]) is None:
        raise SupervisorError("session_invalid")
    try:
        parsed_sources = json.loads(
            environment["HARNESS_EXPECTED_SOURCE_HASHES"],
            object_pairs_hook=_reject_duplicate_pairs,
        )
    except (SupervisorError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise SupervisorError("session_invalid") from exc
    if (
        not isinstance(parsed_sources, dict)
        or set(parsed_sources) != {"events.jsonl", "attempts.jsonl", "artifacts.jsonl"}
        or any(_SHA256_RE.fullmatch(item) is None for item in parsed_sources.values())
    ):
        raise SupervisorError("session_invalid")
    try:
        runtime_ref = uuid.UUID(environment["HARNESS_EXPECTED_RUNTIME_SESSION_REF"])
    except (AttributeError, TypeError, ValueError) as exc:
        raise SupervisorError("session_invalid") from exc
    if str(runtime_ref) != environment["HARNESS_EXPECTED_RUNTIME_SESSION_REF"]:
        raise SupervisorError("session_invalid")
    return list(command), dict(environment)


def _read_bootstrap() -> tuple[dict[str, str], bytes]:
    raw = sys.stdin.buffer.read(MAX_AUTH_BYTES + 1)
    if not raw or len(raw) > MAX_AUTH_BYTES:
        raise SupervisorError("auth_invalid")
    value = _parse_json_object(raw)
    if set(value) != {
        "schema_version",
        "environment",
        "broker_session_key_base64",
    } or type(value.get("schema_version")) is not int or value["schema_version"] != 1:
        raise SupervisorError("auth_invalid")
    environment = value.get("environment")
    if (
        not isinstance(environment, dict)
        or not set(environment).issubset(_AUTH_KEYS)
        or any(
            not isinstance(key, str)
            or not isinstance(item, str)
            or not item
            or "\x00" in item
            or len(item.encode("utf-8")) > 32 * 1024
            for key, item in environment.items()
        )
    ):
        raise SupervisorError("auth_invalid")
    encoded_key = value.get("broker_session_key_base64")
    try:
        key = base64.b64decode(encoded_key, validate=True)
    except (binascii.Error, TypeError, ValueError) as exc:
        raise SupervisorError("broker_key_invalid") from exc
    if (
        len(key) != broker_client.SESSION_KEY_BYTES
        or base64.b64encode(key).decode("ascii") != encoded_key
    ):
        raise SupervisorError("broker_key_invalid")
    return dict(environment), key


def _load_broker_manifest() -> dict[str, Any]:
    raw = _read_stable_regular(
        BROKER_MANIFEST_PATH, max_bytes=256 * 1024, private=True
    )
    try:
        value = json.loads(raw, object_pairs_hook=_reject_duplicate_pairs)
        return broker_client.validate_manifest(value)
    except SupervisorError:
        raise
    except broker_client.ContainerBrokerClientError as exc:
        raise SupervisorError("broker_manifest_invalid") from exc
    except (UnicodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise SupervisorError("broker_manifest_invalid") from exc


def _child_environment(
    session: dict[str, str],
    auth: dict[str, str],
    *,
    provider_endpoint: str = "http://127.0.0.1:9",
) -> dict[str, str]:
    environment = {
        key: value for key, value in os.environ.items() if key in _INHERITED_RUNTIME_KEYS
    }
    environment.setdefault("PATH", "/usr/local/bin:/usr/bin:/bin")
    environment.update(
        {
            "HOME": str(SCRATCH_PATH),
            "TMPDIR": str(SCRATCH_PATH),
            "TMP": str(SCRATCH_PATH),
            "TEMP": str(SCRATCH_PATH),
            "CLAUDE_CONFIG_DIR": str(SCRATCH_PATH / ".claude"),
            "PYTHONDONTWRITEBYTECODE": "1",
            broker_client.RELAY_SOCKET_ENV: str(BROKER_RELAY_PATH),
        }
    )
    environment.update(session)
    # Provider authority remains in the host parent.  The child receives only the fixed PID-1
    # endpoint and an inert token for SDKs that require a non-empty value.
    environment.update(
        {
            "ANTHROPIC_BASE_URL": provider_endpoint,
            "ANTHROPIC_API_KEY": "lrh-parent-owned",
        }
    )
    return environment


def _storage_exhausted(paths: tuple[Path, ...] | None = None) -> bool:
    paths = (SCRATCH_PATH, SHM_PATH) if paths is None else paths
    for path in paths:
        try:
            value = os.statvfs(path)
        except OSError as exc:
            raise SupervisorError("storage_unavailable") from exc
        free_bytes = value.f_bavail * value.f_frsize
        free_inodes = value.f_favail
        byte_floor = max(value.f_frsize, 4096)
        if free_bytes < byte_floor or free_inodes < 1:
            return True
    return False


class _BrokerRelay:
    """Keep the HMAC key in PID 1 and expose only the semantic broker operations."""

    def __init__(self, *, manifest: dict[str, Any], key: bytes) -> None:
        try:
            self._manifest = broker_client.validate_manifest(manifest)
        except broker_client.ContainerBrokerClientError as exc:
            raise SupervisorError("broker_manifest_invalid") from exc
        if not isinstance(key, bytes) or len(key) != broker_client.SESSION_KEY_BYTES:
            raise SupervisorError("broker_key_invalid")
        self._key = key
        self._stop = threading.Event()
        self._listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._listener.settimeout(0.1)
        self._thread = threading.Thread(target=self._serve, daemon=True)
        try:
            BROKER_RELAY_PATH.unlink(missing_ok=True)
            self._listener.bind(str(BROKER_RELAY_PATH))
            os.chmod(BROKER_RELAY_PATH, 0o600)
            self._listener.listen(4)
        except OSError as exc:
            self._listener.close()
            raise SupervisorError("broker_relay_unavailable") from exc

    def start(self) -> None:
        self._thread.start()

    def _peer_is_local_runtime(self, connection: socket.socket) -> bool:
        if not sys.platform.startswith("linux"):
            return True
        peer_option = getattr(socket, "SO_PEERCRED", None)
        if peer_option is None:
            return False
        try:
            raw = connection.getsockopt(socket.SOL_SOCKET, peer_option, 12)
            _pid, uid, _gid = struct.unpack("3i", raw)
        except (OSError, struct.error):
            return False
        return uid == os.geteuid()

    def _serve_one(self, connection: socket.socket) -> None:
        connection.settimeout(RELAY_IO_TIMEOUT_SECONDS)
        try:
            if not self._peer_is_local_runtime(connection):
                raise SupervisorError("broker_relay_peer_invalid")
            request = broker_client.recv_frame(
                connection, timeout=RELAY_IO_TIMEOUT_SECONDS
            )
            returncode, output = broker_client.handle_relay_request(
                self._manifest, self._key, request
            )
        except Exception:
            returncode = 1
            output = broker_client.canonical_json_bytes(
                {
                    "valid": False,
                    "error": {"code": "container_broker_relay_failed"},
                }
            )
        try:
            broker_client.send_frame(
                connection,
                broker_client.relay_response(returncode=returncode, output=output),
            )
        except (OSError, broker_client.ContainerBrokerClientError):
            pass

    def _serve(self) -> None:
        while not self._stop.is_set():
            try:
                connection, _address = self._listener.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            with connection:
                self._serve_one(connection)

    def close(self) -> None:
        self._stop.set()
        self._listener.close()
        self._thread.join(timeout=1.0)
        try:
            BROKER_RELAY_PATH.unlink(missing_ok=True)
        except OSError:
            pass


class _ProviderProxy:
    """Fixed HTTP/1.1 provider endpoint backed by the authenticated parent broker."""

    def __init__(self, *, manifest: dict[str, Any], key: bytes) -> None:
        self._manifest = manifest
        self._key = key
        self._stop = threading.Event()
        self._listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._listener.bind(("127.0.0.1", 0))
        self._listener.listen(4)
        self._listener.settimeout(0.1)
        host, port = self._listener.getsockname()[:2]
        if host != "127.0.0.1" or type(port) is not int:
            raise SupervisorError("provider_proxy_unavailable")
        self.endpoint = (host, port)
        self._thread = threading.Thread(target=self._serve, daemon=True)

    def start(self) -> None:
        self._thread.start()

    @staticmethod
    def _read_request(connection: socket.socket) -> tuple[dict[str, str], bytes, str]:
        deadline = time.monotonic() + PROVIDER_IO_TIMEOUT_SECONDS

        def recv_before_deadline(size: int) -> bytes:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise socket.timeout("provider request deadline")
            connection.settimeout(remaining)
            return connection.recv(size)

        data = bytearray()
        while b"\r\n\r\n" not in data:
            chunk = recv_before_deadline(
                min(4096, MAX_PROVIDER_HEADER_BYTES + 1 - len(data))
            )
            if not chunk:
                raise SupervisorError("provider_request_invalid")
            data.extend(chunk)
            if len(data) > MAX_PROVIDER_HEADER_BYTES:
                raise SupervisorError("provider_request_invalid")
        raw_headers, body_prefix = bytes(data).split(b"\r\n\r\n", 1)
        try:
            lines = raw_headers.decode("iso-8859-1").split("\r\n")
        except UnicodeError as exc:
            raise SupervisorError("provider_request_invalid") from exc
        allowed_request_lines = {
            "POST /v1/messages HTTP/1.1": "/v1/messages",
            "POST /v1/messages?beta=true HTTP/1.1": "/v1/messages?beta=true",
        }
        if lines[0] not in allowed_request_lines:
            raise SupervisorError("provider_request_denied")
        path = allowed_request_lines[lines[0]]
        headers: dict[str, str] = {}
        for line in lines[1:]:
            name, separator, value = line.partition(":")
            lowered = name.strip().lower()
            if not separator or not lowered or lowered in headers:
                raise SupervisorError("provider_request_invalid")
            headers[lowered] = value.strip()
        if "transfer-encoding" in headers or headers.get("expect"):
            raise SupervisorError("provider_request_denied")
        try:
            content_length = int(headers.get("content-length", ""))
        except ValueError as exc:
            raise SupervisorError("provider_request_invalid") from exc
        if content_length < 0 or content_length > broker_client.RAW_INPUT_LIMIT:
            raise SupervisorError("provider_request_invalid")
        body = bytearray(body_prefix)
        while len(body) < content_length:
            chunk = recv_before_deadline(content_length - len(body))
            if not chunk:
                raise SupervisorError("provider_request_invalid")
            body.extend(chunk)
        if len(body) != content_length:
            raise SupervisorError("provider_request_invalid")
        forwarded = {
            name: value
            for name, value in headers.items()
            if name in {"accept", "content-type", "anthropic-version", "anthropic-beta"}
        }
        return forwarded, bytes(body), path

    def _serve_one(self, connection: socket.socket) -> None:
        connection.settimeout(PROVIDER_IO_TIMEOUT_SECONDS)
        started = False
        try:
            headers, body, path = self._read_request(connection)
            def send_headers(status: int, response_headers: list[list[str]]) -> None:
                nonlocal started
                phrase = http.client.responses.get(status, "Response")
                safe_headers = "".join(
                    f"{name}: {value}\r\n"
                    for name, value in response_headers
                    if name.lower() in {"content-type", "request-id", "anthropic-request-id"}
                    and "\r" not in value
                    and "\n" not in value
                )
                connection.sendall(
                    f"HTTP/1.1 {status} {phrase}\r\n{safe_headers}Transfer-Encoding: chunked\r\nConnection: close\r\n\r\n".encode("iso-8859-1")
                )
                started = True

            def send_chunk(chunk: bytes) -> None:
                connection.sendall(f"{len(chunk):x}\r\n".encode("ascii") + chunk + b"\r\n")

            broker_client.stream_provider(
                self._manifest,
                self._key,
                path=path,
                headers=headers,
                body=body,
                on_headers=send_headers,
                on_chunk=send_chunk,
            )
            connection.sendall(b"0\r\n\r\n")
        except Exception:
            if not started:
                try:
                    connection.sendall(
                        b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
                    )
                except OSError:
                    pass

    def _serve(self) -> None:
        while not self._stop.is_set():
            try:
                connection, _address = self._listener.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            with connection:
                self._serve_one(connection)

    def close(self) -> None:
        self._stop.set()
        self._listener.close()
        self._thread.join(timeout=1.0)


def _returncode(value: int) -> int:
    if value == STORAGE_EXIT_CODE:
        return INTERNAL_FAILURE_EXIT_CODE
    if value < 0:
        return min(255, 128 + abs(value))
    return min(255, value)


def _terminate_child(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except OSError:
        try:
            process.kill()
        except OSError:
            pass
    try:
        process.wait(timeout=2.0)
    except subprocess.TimeoutExpired:
        pass


def run(*, expected_session_hash: str) -> int:
    _harden_process_memory()
    _require_zero_runtime_privileges()
    if _SHA256_RE.fullmatch(expected_session_hash) is None:
        raise SupervisorError("session_hash_invalid")
    raw_session = _read_stable_regular(
        SESSION_PATH, max_bytes=MAX_SESSION_BYTES, private=True
    )
    if _sha256(raw_session) != expected_session_hash:
        raise SupervisorError("session_hash_mismatch")
    command, session_environment = _validate_session(_parse_json_object(raw_session))
    manifest = _load_broker_manifest()
    auth, broker_key = _read_bootstrap()
    if _storage_exhausted():
        return STORAGE_EXIT_CODE
    relay = _BrokerRelay(manifest=manifest, key=broker_key)
    provider = _ProviderProxy(manifest=manifest, key=broker_key)
    relay.start()
    provider.start()
    try:
        return _run_traced_command(
            command,
            _child_environment(
                session_environment,
                auth,
                provider_endpoint=f"http://127.0.0.1:{provider.endpoint[1]}",
            ),
            provider.endpoint,
        )
    finally:
        provider.close()
        relay.close()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--session", required=True)
    parser.add_argument("--session-sha256", required=True)
    return parser


def main() -> int:
    try:
        if sys.argv[1:2] == ["--trace-child"]:
            if len(sys.argv) < 5 or sys.argv[3] != "--":
                raise SupervisorError("trace_child_command_invalid")
            try:
                transport_descriptor = int(sys.argv[2])
            except ValueError as exc:
                raise SupervisorError("trace_child_command_invalid") from exc
            return _trace_child(sys.argv[4:], transport_descriptor)
        arguments = _parser().parse_args()
        if arguments.session != str(SESSION_PATH):
            raise SupervisorError("session_path_invalid")
        return run(expected_session_hash=arguments.session_sha256)
    except (SupervisorError, OSError, ValueError):
        return INTERNAL_FAILURE_EXIT_CODE


if __name__ == "__main__":
    raise SystemExit(main())
