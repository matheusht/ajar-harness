#!/usr/bin/env python3
"""Build a bounded Darwin Seatbelt filesystem-read policy for one model session."""

from __future__ import annotations

import json
import os
import re
import selectors
import stat
import subprocess
import sys
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


MAX_EXPLICIT_INPUTS = 32
MAX_EXPLICIT_LITERALS = 256
MAX_RUNTIME_DEPENDENCIES = 128
MAX_RUNTIME_LITERALS = 512
MAX_DEPENDENCY_DEPTH = 12
MAX_RUNTIME_SYMLINKS = 32
MAX_OTOOL_OUTPUT_BYTES = 256 * 1024
MAX_PROFILE_BYTES = 256 * 1024
OTOOL_TIMEOUT_SECONDS = 5.0

SYSTEM_READ_DIRECTORIES = (
    Path("/System"),
    Path("/Library/Apple"),
    Path("/usr/lib"),
    Path("/usr/share"),
    Path("/bin"),
    Path("/sbin"),
    Path("/usr/bin"),
    Path("/usr/sbin"),
    Path("/private/var/db/timezone"),
)
SYSTEM_READ_FILES = (
    Path("/"),
    Path("/dev/autofs_nowait"),
    Path("/dev/dtracehelper"),
    Path("/dev/null"),
    Path("/dev/random"),
    Path("/dev/urandom"),
    Path("/dev/zero"),
    Path("/private/etc/group"),
    Path("/private/etc/hosts"),
    Path("/private/etc/localtime"),
    Path("/private/etc/passwd"),
    Path("/private/etc/protocols"),
    Path("/private/etc/resolv.conf"),
    Path("/private/etc/services"),
    Path("/private/etc/ssl/cert.pem"),
    Path("/private/var/run/resolv.conf"),
)
SYSTEM_METADATA_FILES = (
    Path("/etc"),
    Path("/tmp"),
    Path("/var"),
)
SYSTEM_FD_DIRECTORY = Path("/dev/fd")
SYSTEM_DEPENDENCY_ROOTS = (
    Path("/System"),
    Path("/Library/Apple"),
    Path("/usr/lib"),
)

_MACHO_MAGICS = frozenset(
    {
        b"\xca\xfe\xba\xbe",
        b"\xca\xfe\xba\xbf",
        b"\xbe\xba\xfe\xca",
        b"\xbf\xba\xfe\xca",
        b"\xce\xfa\xed\xfe",
        b"\xcf\xfa\xed\xfe",
        b"\xfe\xed\xfa\xce",
        b"\xfe\xed\xfa\xcf",
    }
)
_DEPENDENCY_LINE = re.compile(r"^\s+(.+?)\s+\(compatibility version ")


class ReadIsolationError(RuntimeError):
    """The read boundary could not be established safely."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class DarwinReadPolicy:
    profile_lines: tuple[str, ...]
    explicit_files: tuple[Path, ...]
    explicit_directories: tuple[Path, ...]
    runtime_files: tuple[Path, ...]
    runtime_directories: tuple[Path, ...]

    @property
    def profile(self) -> str:
        return "\n".join(self.profile_lines)

    def is_explicitly_declared(self, candidate: Path) -> bool:
        try:
            resolved = Path(candidate).resolve(strict=True)
        except (OSError, RuntimeError):
            return False
        if resolved in self.explicit_files:
            return True
        return any(_is_within(resolved, directory) for directory in self.explicit_directories)


def _is_within(candidate: Path, directory: Path) -> bool:
    try:
        candidate.relative_to(directory)
    except ValueError:
        return False
    return True


def _quote(path: Path) -> str:
    return json.dumps(str(path))


def _has_symlink_component(path: Path) -> bool:
    if ".." in path.parts:
        return True
    prefix = Path("/")
    for component in path.parts[1:]:
        prefix /= component
        try:
            entry = os.lstat(prefix)
        except FileNotFoundError:
            return False
        except OSError:
            return True
        if stat.S_ISLNK(entry.st_mode):
            return True
    return False


def _strict_directory(path: Path, *, code: str, reject_aliases: bool = False) -> Path:
    supplied = Path(path)
    if not supplied.is_absolute() or "\x00" in str(supplied):
        raise ReadIsolationError(code)
    if reject_aliases and _has_symlink_component(supplied):
        raise ReadIsolationError(code)
    try:
        resolved = supplied.resolve(strict=True)
        entry = os.stat(resolved, follow_symlinks=False)
    except (OSError, RuntimeError) as exc:
        raise ReadIsolationError(code) from exc
    if not stat.S_ISDIR(entry.st_mode):
        raise ReadIsolationError(code)
    return resolved


def _strict_file(path: Path, *, executable: bool, code: str) -> Path:
    supplied = Path(path)
    if not supplied.is_absolute() or "\x00" in str(supplied):
        raise ReadIsolationError(code)
    try:
        resolved = supplied.resolve(strict=True)
        entry = os.stat(resolved, follow_symlinks=False)
    except (OSError, RuntimeError) as exc:
        raise ReadIsolationError(code) from exc
    if not stat.S_ISREG(entry.st_mode) or (executable and not os.access(resolved, os.X_OK)):
        raise ReadIsolationError(code)
    return resolved


def _runtime_invocation_literals(path: Path) -> tuple[Path, ...]:
    """Return the bounded symlink names execvp must traverse for one runtime.

    ``Path.resolve`` alone is insufficient for Seatbelt: execvp probes each
    symlink name (including a venv's relative ``python -> python3.X`` hop)
    before it reaches the regular Mach-O file. Each name is admitted literally;
    no symlink parent receives subpath authority.
    """

    supplied = Path(path)
    if not supplied.is_absolute() or "\x00" in str(supplied):
        raise ReadIsolationError("runtime_dependencies_unresolved")
    current = Path(os.path.normpath(str(supplied)))
    pending = [current]
    literals: list[Path] = []
    seen: set[Path] = set()
    while pending:
        current = pending.pop()
        if current in seen:
            raise ReadIsolationError("runtime_dependencies_unresolved")
        seen.add(current)
        if len(seen) > MAX_RUNTIME_SYMLINKS:
            raise ReadIsolationError("runtime_dependencies_unresolved")
        literals.append(current)

        # Component symlinks also need exact readlink authority. Do not grant a
        # subpath rule to their parents or targets here.
        prefix = Path("/")
        components = current.parts[1:]
        for index, component in enumerate(components):
            prefix /= component
            try:
                if prefix.is_symlink():
                    if prefix not in literals:
                        literals.append(prefix)
                    # execvp also probes the same unresolved suffix below the
                    # component symlink's canonical target before resolving a
                    # leaf symlink (Homebrew's opt -> Cellar chain does this).
                    expanded = prefix.resolve(strict=True).joinpath(
                        *components[index + 1 :]
                    )
                    if expanded not in seen and expanded not in pending:
                        pending.append(expanded)
            except OSError as exc:
                raise ReadIsolationError("runtime_dependencies_unresolved") from exc

        try:
            if current.is_symlink():
                target = Path(os.readlink(current))
                if not target.is_absolute():
                    target = current.parent / target
                target = Path(os.path.normpath(str(target)))
                if target not in seen and target not in pending:
                    pending.append(target)
        except OSError as exc:
            raise ReadIsolationError("runtime_dependencies_unresolved") from exc
    try:
        literals.append(supplied.resolve(strict=True))
    except (OSError, RuntimeError) as exc:
        raise ReadIsolationError("runtime_dependencies_unresolved") from exc
    return tuple(dict.fromkeys(literals))


def _strict_internal_endpoint(path: Path) -> Path:
    supplied = Path(path)
    if not supplied.is_absolute() or "\x00" in str(supplied) or supplied.name in {"", ".", ".."}:
        raise ReadIsolationError("read_input_invalid")
    try:
        parent = supplied.parent.resolve(strict=True)
        parent_entry = os.stat(parent, follow_symlinks=False)
    except (OSError, RuntimeError) as exc:
        raise ReadIsolationError("read_input_invalid") from exc
    if not stat.S_ISDIR(parent_entry.st_mode):
        raise ReadIsolationError("read_input_invalid")
    return parent / supplied.name


def _validate_sandbox_exec(path: Path) -> Path:
    resolved = _strict_file(path, executable=True, code="read_isolation_unavailable")
    try:
        entry = os.stat(resolved, follow_symlinks=False)
    except OSError as exc:  # pragma: no cover - strict_file already established it
        raise ReadIsolationError("read_isolation_unavailable") from exc
    if entry.st_uid != 0 or entry.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise ReadIsolationError("read_isolation_unavailable")
    return resolved


def _bounded_command(argv: Sequence[str]) -> bytes:
    try:
        process = subprocess.Popen(
            list(argv),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as exc:
        raise ReadIsolationError("runtime_dependencies_unresolved") from exc
    assert process.stdout is not None and process.stderr is not None
    selector = selectors.DefaultSelector()
    outputs = {process.stdout.fileno(): bytearray(), process.stderr.fileno(): bytearray()}
    try:
        for stream in (process.stdout, process.stderr):
            os.set_blocking(stream.fileno(), False)
            selector.register(stream.fileno(), selectors.EVENT_READ)
        deadline = time.monotonic() + OTOOL_TIMEOUT_SECONDS
        while selector.get_map():
            if time.monotonic() >= deadline:
                raise ReadIsolationError("runtime_dependencies_unresolved")
            for key, _events in selector.select(timeout=0.05):
                descriptor = int(key.fd)
                remaining = MAX_OTOOL_OUTPUT_BYTES + 1 - len(outputs[descriptor])
                if remaining <= 0:
                    raise ReadIsolationError("runtime_dependencies_unresolved")
                try:
                    chunk = os.read(descriptor, min(65536, remaining))
                except BlockingIOError:
                    continue
                if not chunk:
                    selector.unregister(descriptor)
                    continue
                outputs[descriptor].extend(chunk)
                if len(outputs[descriptor]) > MAX_OTOOL_OUTPUT_BYTES:
                    raise ReadIsolationError("runtime_dependencies_unresolved")
        try:
            returncode = process.wait(timeout=max(0.01, deadline - time.monotonic()))
        except subprocess.TimeoutExpired as exc:
            raise ReadIsolationError("runtime_dependencies_unresolved") from exc
        stdout = bytes(outputs[process.stdout.fileno()])
        stderr = bytes(outputs[process.stderr.fileno()])
        if returncode != 0 or stderr:
            raise ReadIsolationError("runtime_dependencies_unresolved")
        return stdout
    except BaseException:
        if process.poll() is None:
            process.kill()
        process.wait()
        raise
    finally:
        selector.close()
        process.stdout.close()
        process.stderr.close()


def _is_system_dependency(path: Path) -> bool:
    return any(path == root or _is_within(path, root) for root in SYSTEM_DEPENDENCY_ROOTS)


def _macho_ids(path: Path) -> set[str]:
    raw = _bounded_command(("/usr/bin/otool", "-D", str(path)))
    try:
        output = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ReadIsolationError("runtime_dependencies_unresolved") from exc
    return {
        line.strip()
        for line in output.splitlines()
        if line.strip() and not line.rstrip().endswith(":")
    }


def _macho_rpaths(
    path: Path,
    *,
    loader_invocation: Path,
    executable_root: Path,
) -> tuple[Path, ...]:
    raw = _bounded_command(("/usr/bin/otool", "-l", str(path)))
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise ReadIsolationError("runtime_dependencies_unresolved") from exc
    values: list[Path] = []
    waiting_for_path = False
    for line in lines:
        stripped = line.strip()
        if stripped == "cmd LC_RPATH":
            waiting_for_path = True
            continue
        if not waiting_for_path or not stripped.startswith("path "):
            continue
        value = stripped[5:].split(" (offset ", 1)[0]
        if value.startswith("@loader_path/"):
            candidate = loader_invocation.parent / value[len("@loader_path/") :]
        elif value.startswith("@executable_path/"):
            candidate = executable_root.parent / value[len("@executable_path/") :]
        elif value.startswith("/"):
            candidate = Path(value)
        else:
            raise ReadIsolationError("runtime_dependencies_unresolved")
        candidate = Path(os.path.normpath(str(candidate)))
        try:
            _strict_directory(
                candidate,
                code="runtime_dependencies_unresolved",
            )
        except ReadIsolationError as exc:
            raise ReadIsolationError("runtime_dependencies_unresolved") from exc
        # Keep the raw expanded spelling. dyld searches LC_RPATH entries in
        # load-command order and opens that alias before its canonical target.
        values.append(candidate)
        waiting_for_path = False
    return tuple(dict.fromkeys(values))


def _resolve_install_name(
    value: str,
    *,
    loader: Path,
    executable_root: Path,
    rpaths: Sequence[Path],
) -> Path:
    if value.startswith("@loader_path/"):
        candidates = (loader.parent / value[len("@loader_path/") :],)
    elif value.startswith("@executable_path/"):
        candidates = (executable_root.parent / value[len("@executable_path/") :],)
    elif value.startswith("@rpath/"):
        suffix = value[len("@rpath/") :]
        candidates = tuple(root / suffix for root in rpaths)
    elif value.startswith("/"):
        candidates = (Path(value),)
    else:
        raise ReadIsolationError("runtime_dependencies_unresolved")

    for candidate in candidates:
        if candidate.is_absolute() and _is_system_dependency(candidate):
            return candidate
        try:
            candidate.resolve(strict=True)
        except (OSError, RuntimeError):
            continue
        # Match dyld's declared search order. Selecting lexicographically among
        # same-canonical aliases can admit a spelling dyld never opens while
        # dropping the one it does.
        return candidate
    raise ReadIsolationError("runtime_dependencies_unresolved")


def _runtime_dependency_closure(entrypoints: Sequence[Path]) -> tuple[Path, ...]:
    # ``executable_invocation`` is the raw Mach-O spelling whose directory
    # defines ``@executable_path``. A script hands that role to its absolute
    # interpreter. ``path`` likewise remains the raw loader spelling so nested
    # ``@loader_path`` expansion follows what dyld actually opened.
    pending = deque(
        (Path(path), 0, True, None) for path in entrypoints
    )
    resolved_files: set[Path] = set()
    admitted_literals: set[Path] = set()
    while pending:
        path, depth, must_be_executable, executable_invocation = pending.popleft()
        if depth > MAX_DEPENDENCY_DEPTH:
            raise ReadIsolationError("runtime_dependencies_unresolved")
        admitted_literals.update(_runtime_invocation_literals(path))
        if len(admitted_literals) > MAX_RUNTIME_LITERALS:
            raise ReadIsolationError("runtime_dependencies_unresolved")
        resolved = _strict_file(
            path,
            executable=must_be_executable,
            code="runtime_dependencies_unresolved",
        )
        if resolved in resolved_files:
            continue
        if len(resolved_files) >= MAX_RUNTIME_DEPENDENCIES:
            raise ReadIsolationError("runtime_dependencies_unresolved")
        resolved_files.add(resolved)
        try:
            with resolved.open("rb") as stream:
                prefix = stream.read(4096)
        except OSError as exc:
            raise ReadIsolationError("runtime_dependencies_unresolved") from exc
        if prefix.startswith(b"#!"):
            first_line = prefix.splitlines()[0][2:]
            try:
                shebang = first_line.decode("utf-8").strip().split()
            except UnicodeDecodeError as exc:
                raise ReadIsolationError("runtime_dependencies_unresolved") from exc
            if len(shebang) != 1 or not shebang[0].startswith("/") or shebang[0] == "/usr/bin/env":
                raise ReadIsolationError("runtime_dependencies_unresolved")
            pending.append((Path(shebang[0]), depth + 1, True, None))
            continue
        if prefix[:4] not in _MACHO_MAGICS:
            raise ReadIsolationError("runtime_dependencies_unresolved")
        loader_invocation = path
        if executable_invocation is None:
            executable_invocation = loader_invocation
        image_ids = _macho_ids(resolved)
        rpaths = _macho_rpaths(
            resolved,
            loader_invocation=loader_invocation,
            executable_root=executable_invocation,
        )
        raw = _bounded_command(("/usr/bin/otool", "-L", str(resolved)))
        try:
            output = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ReadIsolationError("runtime_dependencies_unresolved") from exc
        for line in output.splitlines()[1:]:
            match = _DEPENDENCY_LINE.match(line)
            if match is None:
                if line.strip() and line[:1].isspace():
                    raise ReadIsolationError("runtime_dependencies_unresolved")
                continue
            dependency_text = match.group(1)
            if dependency_text in image_ids:
                continue
            dependency = _resolve_install_name(
                dependency_text,
                loader=loader_invocation,
                executable_root=executable_invocation,
                rpaths=rpaths,
            )
            if _is_system_dependency(dependency):
                continue
            pending.append((dependency, depth + 1, False, executable_invocation))
    return tuple(sorted(resolved_files | admitted_literals, key=str))


def _explicit_inputs(
    paths: Sequence[Path],
) -> tuple[tuple[Path, ...], tuple[Path, ...], tuple[Path, ...]]:
    if (
        isinstance(paths, (str, bytes, os.PathLike))
        or not isinstance(paths, Sequence)
        or len(paths) > MAX_EXPLICIT_INPUTS
    ):
        raise ReadIsolationError("read_input_invalid")
    files: set[Path] = set()
    directories: set[Path] = set()
    traversal_literals: set[Path] = set()
    seen: set[Path] = set()
    for raw in paths:
        supplied = Path(raw)
        if not supplied.is_absolute() or "\x00" in str(supplied):
            raise ReadIsolationError("read_input_invalid")
        try:
            resolved = supplied.resolve(strict=True)
            entry = os.stat(resolved, follow_symlinks=False)
        except (OSError, RuntimeError) as exc:
            raise ReadIsolationError("read_input_invalid") from exc
        if resolved in seen:
            raise ReadIsolationError("read_input_invalid")
        seen.add(resolved)
        try:
            aliases = _runtime_invocation_literals(supplied)
        except ReadIsolationError as exc:
            raise ReadIsolationError("read_input_invalid") from exc
        equivalent_aliases: set[Path] = set()
        for alias in aliases:
            try:
                alias_target = alias.resolve(strict=True)
            except (OSError, RuntimeError) as exc:
                raise ReadIsolationError("read_input_invalid") from exc
            if alias_target == resolved:
                equivalent_aliases.add(alias)
            else:
                # A component symlink is needed only to traverse the declared
                # spelling. It receives a literal rule, never directory-subpath
                # authority above the explicitly declared input.
                traversal_literals.add(alias)
        if stat.S_ISREG(entry.st_mode):
            files.update(equivalent_aliases)
        elif stat.S_ISDIR(entry.st_mode):
            directories.update(equivalent_aliases)
        else:
            raise ReadIsolationError("read_input_invalid")
        if len(files | directories | traversal_literals) > MAX_EXPLICIT_LITERALS:
            raise ReadIsolationError("read_input_invalid")
    return (
        tuple(sorted(files, key=str)),
        tuple(sorted(directories, key=str)),
        tuple(sorted(traversal_literals, key=str)),
    )


def _profile_lines(*, directories: Sequence[Path], files: Sequence[Path]) -> tuple[str, ...]:
    unique_directories = tuple(sorted(set(directories), key=str))
    unique_files = tuple(sorted(set(files), key=str))
    lines = [
        "(version 1)",
        "(allow default)",
        "(deny file-read* file-test-existence)",
    ]
    for path in (*unique_directories, *unique_files):
        if path == Path("/"):
            continue
        lines.append(
            f"(allow file-read-metadata file-test-existence (path-ancestors {_quote(path)}))"
        )
    for path in unique_directories:
        quoted = _quote(path)
        lines.append(
            f"(allow file-read* file-test-existence (literal {quoted}) (subpath {quoted}))"
        )
    for path in unique_files:
        lines.append(
            f"(allow file-read* file-test-existence (literal {_quote(path)}))"
        )
    for path in SYSTEM_METADATA_FILES:
        lines.append(
            f"(allow file-read-metadata file-test-existence (literal {_quote(path)}))"
        )
    profile = "\n".join(lines)
    if len(profile.encode("utf-8")) > MAX_PROFILE_BYTES:
        raise ReadIsolationError("read_isolation_unavailable")
    return tuple(lines)


def build_read_policy(
    *,
    workspace: Path,
    harness: Path,
    scratch: Path,
    executable: Path,
    python: Path,
    launcher: Path,
    containment_sentinel: Path,
    internal_endpoints: Sequence[Path] = (),
    explicit_inputs: Sequence[Path] = (),
    platform: str = sys.platform,
    sandbox_exec: Path = Path("/usr/bin/sandbox-exec"),
) -> DarwinReadPolicy:
    """Resolve every admitted path and return a closed, deterministic Seatbelt profile."""

    if platform != "darwin":
        raise ReadIsolationError("read_isolation_unavailable")
    _validate_sandbox_exec(sandbox_exec)
    workspace_root = _strict_directory(
        workspace,
        code="read_input_invalid",
        reject_aliases=True,
    )
    harness_root = _strict_directory(
        harness,
        code="read_isolation_unavailable",
        reject_aliases=True,
    )
    scratch_root = _strict_directory(scratch, code="read_isolation_unavailable")
    if any(
        _is_within(left, right) or _is_within(right, left)
        for left, right in (
            (workspace_root, harness_root),
            (workspace_root, scratch_root),
            (harness_root, scratch_root),
        )
    ):
        raise ReadIsolationError("read_input_invalid")

    executable_invocation = Path(executable)
    python_invocation = Path(python)
    executable_file = _strict_file(
        executable_invocation, executable=True, code="runtime_dependencies_unresolved"
    )
    python_file = _strict_file(
        python_invocation, executable=True, code="runtime_dependencies_unresolved"
    )
    executable_literals = _runtime_invocation_literals(executable_invocation)
    python_literals = _runtime_invocation_literals(python_invocation)
    launcher_file = _strict_file(
        launcher, executable=False, code="runtime_dependencies_unresolved"
    )
    sentinel_file = _strict_file(
        containment_sentinel,
        executable=False,
        code="read_isolation_unavailable",
    )
    # Reject malformed operator-declared authority before doing any dependency
    # discovery. This keeps an invalid read request from being obscured by an
    # unrelated runtime-resolution failure.
    explicit_files, explicit_directories, explicit_traversal_files = _explicit_inputs(
        explicit_inputs
    )
    runtime_files = _runtime_dependency_closure(
        (executable_invocation, python_invocation)
    )
    # Runtime authority is the exact executable/shebang/Mach-O closure. Python
    # installation prefixes are intentionally not admitted: they are commonly
    # same-UID writable, and a future file created after policy construction
    # must not become prompt-readable merely because it lands under a prefix.
    runtime_directories: tuple[Path, ...] = ()
    if (
        isinstance(internal_endpoints, (str, bytes, os.PathLike))
        or not isinstance(internal_endpoints, Sequence)
        or len(internal_endpoints) > 8
    ):
        raise ReadIsolationError("read_input_invalid")
    endpoint_files = tuple(_strict_internal_endpoint(Path(path)) for path in internal_endpoints)

    directories = (
        workspace_root,
        harness_root,
        scratch_root,
        *runtime_directories,
        *explicit_directories,
        *SYSTEM_READ_DIRECTORIES,
        SYSTEM_FD_DIRECTORY,
    )
    files = (
        *executable_literals,
        executable_file,
        *python_literals,
        python_file,
        launcher_file,
        sentinel_file,
        *runtime_files,
        *explicit_files,
        *explicit_traversal_files,
        *endpoint_files,
        *SYSTEM_READ_FILES,
    )
    return DarwinReadPolicy(
        profile_lines=_profile_lines(directories=directories, files=files),
        explicit_files=explicit_files,
        explicit_directories=explicit_directories,
        runtime_files=runtime_files,
        runtime_directories=runtime_directories,
    )
