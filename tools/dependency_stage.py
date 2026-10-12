"""One-use, exact-action Go 1.23.0 dependency staging.

The public CLI supplies no URL or test transport. Every contact is named in an
operator-approved action; a typed kernel event spends that action before contact.
The Go tool is later run only with socket/connect denied by seccomp.
"""

from __future__ import annotations

import base64
import ctypes
import datetime as dt
import errno
import hashlib
import io
import json
import os
import re
import shutil
import socket
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Callable


MAX_REQUESTS = 100
MAX_TOTAL_BYTES = 600 * 1024 * 1024
MAX_GO_BYTES = 256 * 1024 * 1024
MAX_ZIP_BYTES = 64 * 1024 * 1024
MAX_SECONDS = 1800
MAX_UNPACKED_GO = 1536 * 1024 * 1024
MAX_UNPACKED_ZIP = 256 * 1024 * 1024
GO_VERSION = "go1.23.0"
DESTINATION = "sandbox/dependency-retrieval"
OFFICIAL_HOSTS = {"go.dev", "dl.google.com", "proxy.golang.org", "sum.golang.org"}
OFFICIAL_CDN_HOSTS = {"storage.googleapis.com"}
CLOUD_HTTPS_PROXY = "http://proxy:8080"
DECLARED_MODULES = {
    ("github.com/bits-and-blooms/bitset", "v1.24.4"),
    ("github.com/stretchr/testify", "v1.8.4"),
    ("golang.org/x/crypto", "v0.12.0"),
    ("github.com/davecgh/go-spew", "v1.1.1"),
    ("github.com/pmezard/go-difflib", "v1.0.0"),
    ("golang.org/x/sys", "v0.11.0"),
    ("gopkg.in/yaml.v3", "v3.0.1"),
}
KINDS = {"release_metadata", "go_archive", "module_mod", "module_info", "module_zip", "sumdb"}
HEX = re.compile(r"[0-9a-f]{64}\Z")
GIT_SHA1 = re.compile(r"[0-9a-f]{40}\Z")
VERSION = re.compile(r"v[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?\Z")


class StageError(Exception):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(detail or code)
        self.code = code


def _reject(code: str, detail: str = "") -> None:
    raise StageError(code, detail)


def _escape_module(value: str) -> str:
    return "".join("!" + c.lower() if c.isupper() else c for c in value)


def _unescape_module(value: str) -> str:
    return re.sub(r"!([a-z])", lambda match: match.group(1).upper(), value)


def _go_h1_rows(rows: list[tuple[str, str]]) -> str:
    digest = hashlib.sha256()
    for name, file_hash in sorted(rows):
        digest.update(f"{file_hash}  {name}\n".encode())
    return "h1:" + base64.b64encode(digest.digest()).decode()


def _go_mod_h1(data: bytes) -> str:
    return _go_h1_rows([("go.mod", hashlib.sha256(data).hexdigest())])


def _scope_requires_fresh_third_party_confirmation(scope: bytes) -> bool:
    """Recognize the signed trip-wire rule, not a network-policy-v1 target grant."""
    return (b"2. **Reaches a third party.**" in scope
            and b"Each one needs a fresh" in scope
            and b"human confirmation at the moment of the act" in scope
            and b"source-only, no live RPC or vendor service" in scope)


def _scope_harness_revision(scope: bytes) -> str | None:
    matches = re.findall(rb"(?m)^- \*\*harness revision required:\*\* `([0-9a-f]{40})`", scope)
    return matches[0].decode() if len(matches) == 1 else None


def _exact_url(value: str, *, kind: str, redirect: bool = False) -> None:
    if not isinstance(value, str) or len(value) > 2048 or any(ord(c) < 33 for c in value):
        _reject("url_not_admitted")
    try:
        parsed = urllib.parse.urlsplit(value)
        port = parsed.port
    except ValueError:
        _reject("url_not_admitted")
    if (parsed.scheme != "https" or parsed.username is not None or parsed.password is not None
            or port not in (None, 443) or parsed.fragment or not parsed.hostname
            or parsed.hostname != parsed.hostname.lower() or parsed.netloc not in
            {parsed.hostname, parsed.hostname + ":443"}):
        _reject("url_not_admitted")
    host, path = parsed.hostname, parsed.path
    if host not in OFFICIAL_HOSTS | OFFICIAL_CDN_HOSTS:
        _reject("url_not_admitted")
    if host in OFFICIAL_CDN_HOSTS and not redirect:
        _reject("url_not_admitted")
    if "%" in path or "//" in path or ".." in PurePosixPath(path).parts:
        _reject("url_not_admitted")
    if kind == "release_metadata":
        allowed = host == "go.dev" and path == "/dl/" and parsed.query == "mode=json&include=all"
    elif kind == "go_archive":
        allowed = (
            (host == "go.dev" and path == "/dl/go1.23.0.linux-amd64.tar.gz")
            or (host == "dl.google.com" and path == "/go/go1.23.0.linux-amd64.tar.gz")
            or (redirect and host in OFFICIAL_CDN_HOSTS and path.startswith("/go/"))
        ) and not parsed.query
    elif kind in {"module_mod", "module_info", "module_zip"}:
        suffix = {"module_mod": ".mod", "module_info": ".info", "module_zip": ".zip"}[kind]
        allowed = (host == "proxy.golang.org" and "/@v/" in path and path.endswith(suffix)
                   and not parsed.query) or (redirect and host in OFFICIAL_CDN_HOSTS and not parsed.query)
    elif kind == "sumdb":
        allowed = ((host == "sum.golang.org" and path.startswith(("/lookup/", "/tile/")))
                   or (host == "proxy.golang.org" and path.startswith("/sumdb/sum.golang.org/"))) and not parsed.query
    else:
        allowed = False
    if not allowed:
        _reject("url_not_admitted")


def validate_stage_action(action: Any, *, allow_fixture: bool = False) -> None:
    """Validate only the exact action shape used by this capability."""
    keys = {
        "schema_version", "action_kind", "lane_id", "engagement_id", "executor_id", "session_id",
        "operator_id", "scope_hash", "environment_ref", "source_repo", "source_commit",
        "harness_commit", "capability_sha256", "go_version", "destination", "max_requests",
        "max_total_bytes", "deadline_seconds", "requests", "synthetic_fixture",
    }
    if not isinstance(action, dict) or set(action) != keys or action.get("schema_version") != 1:
        _reject("action_invalid", "shape")
    for key in ("lane_id", "engagement_id", "executor_id", "session_id", "operator_id", "environment_ref"):
        if not isinstance(action[key], str) or not action[key]:
            _reject("action_invalid", key)
    if (action["action_kind"] != "stage-go-dependencies" or action["go_version"] != GO_VERSION
            or action["destination"] != DESTINATION or type(action["synthetic_fixture"]) is not bool
            or (action["synthetic_fixture"] and not allow_fixture)):
        _reject("action_invalid", "kind/version/destination/fixture")
    if not isinstance(action["source_repo"], str) or not Path(action["source_repo"]).is_absolute():
        _reject("action_invalid", "source_repo")
    for key in ("source_commit", "harness_commit", "capability_sha256"):
        pattern = HEX if key == "capability_sha256" else GIT_SHA1
        if not isinstance(action[key], str) or pattern.fullmatch(action[key]) is None:
            _reject("action_invalid", key)
    if not isinstance(action["scope_hash"], str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", action["scope_hash"]):
        _reject("action_invalid", "scope_hash")
    if (type(action["max_requests"]) is not int or not 1 <= action["max_requests"] <= MAX_REQUESTS
            or type(action["max_total_bytes"]) is not int
            or not 1 <= action["max_total_bytes"] <= MAX_TOTAL_BYTES
            or type(action["deadline_seconds"]) is not int
            or not 1 <= action["deadline_seconds"] <= MAX_SECONDS):
        _reject("action_invalid", "budgets")
    rows = action["requests"]
    if not isinstance(rows, list) or not rows or len(rows) > MAX_REQUESTS:
        _reject("action_invalid", "requests shape")
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != ({"url", "redirects", "kind", "max_bytes", "sha256"}
                                                    | ({"go_h1"} if row.get("kind") in {"module_mod", "module_zip"} else set())):
            _reject("action_invalid")
        kind = row["kind"]
        if kind not in KINDS or not isinstance(row["redirects"], list) or len(row["redirects"]) > 5:
            _reject("action_invalid")
        _exact_url(row["url"], kind=kind)
        for target in row["redirects"]:
            _exact_url(target, kind=kind, redirect=True)
        if len(set([row["url"], *row["redirects"]])) != 1 + len(row["redirects"]):
            _reject("action_invalid")
        if row["url"] in seen or not isinstance(row["sha256"], str) or HEX.fullmatch(row["sha256"]) is None:
            _reject("action_invalid")
        if kind in {"module_mod", "module_zip"} and (not isinstance(row["go_h1"], str)
                or re.fullmatch(r"h1:[A-Za-z0-9+/]{43}=", row["go_h1"]) is None):
            _reject("action_invalid")
        seen.add(row["url"])
        limit = MAX_GO_BYTES if kind == "go_archive" else MAX_ZIP_BYTES if kind == "module_zip" else 8 * 1024 * 1024
        if type(row["max_bytes"]) is not int or not 1 <= row["max_bytes"] <= limit:
            _reject("action_invalid")
    if sum(1 + len(row["redirects"]) for row in rows) > MAX_REQUESTS:
        _reject("action_invalid")
    if not action["synthetic_fixture"]:
        if sum(row["kind"] == "go_archive" for row in rows) != 1:
            _reject("closure_incomplete")
        if sum(row["kind"] == "release_metadata" for row in rows) != 1:
            _reject("closure_incomplete")
        metadata_index = next(index for index, row in enumerate(rows) if row["kind"] == "release_metadata")
        archive_index = next(index for index, row in enumerate(rows) if row["kind"] == "go_archive")
        if metadata_index >= archive_index:
            _reject("closure_incomplete")
        if any(row["kind"] in {"module_mod", "module_info", "module_zip"}
               and not re.fullmatch(r"/[A-Za-z0-9!._~/-]+/@v/" + VERSION.pattern[:-2]
                                    + r"\.(?:mod|info|zip)", urllib.parse.urlsplit(row["url"]).path)
               for row in rows):
            _reject("module_path_invalid")
        groups: dict[str, set[str]] = {}
        for row in rows:
            if row["kind"] in {"module_mod", "module_info", "module_zip"}:
                path = urllib.parse.urlsplit(row["url"]).path
                key = path.rsplit(".", 1)[0]
                groups.setdefault(key, set()).add(row["kind"])
        if any(kinds != {"module_mod", "module_info", "module_zip"} for kinds in groups.values()):
            _reject("closure_incomplete")
        for module, version in DECLARED_MODULES:
            prefix = f"https://proxy.golang.org/{_escape_module(module)}/@v/{version}"
            if any(not any(row["url"] == prefix + suffix and row["kind"] == kind for row in rows)
                   for kind, suffix in (("module_mod", ".mod"), ("module_info", ".info"),
                                        ("module_zip", ".zip"))):
                _reject("closure_incomplete")


def _git_head(repo: Path) -> str:
    result = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True)
    if result.returncode:
        _reject("source_identity_mismatch")
    return result.stdout.strip()


def _source_clean(repo: Path) -> bool:
    result = subprocess.run(["git", "-C", str(repo), "status", "--porcelain", "--untracked-files=no"],
                            capture_output=True, text=True)
    return result.returncode == 0 and not result.stdout.strip()


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


class RealTransport:
    def __init__(self) -> None:
        # Bind to this Cloud task's internal egress sidecar. Never inherit an
        # arbitrary proxy from the caller's environment.
        self.opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({"https": CLOUD_HTTPS_PROXY}), _NoRedirect())

    def open(self, url: str, timeout: float):
        request = urllib.request.Request(url, method="GET", headers={"User-Agent": "redteam-harness-dependency-stage/1"})
        try:
            response = self.opener.open(request, timeout=timeout)
        except urllib.error.HTTPError as exc:
            response = exc
        def chunks():
            try:
                while part := response.read(65536):
                    yield part
            finally:
                response.close()
        return response.status, dict(response.headers.items()), chunks()


def _atomic_private(path: Path, data: bytes) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".stage-", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def _require_private_dir(path: Path) -> None:
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        _reject("private_root_invalid")


def _seccomp_no_sockets() -> None:
    lib = ctypes.CDLL("libseccomp.so.2", use_errno=True)
    lib.seccomp_init.argtypes = [ctypes.c_uint32]
    lib.seccomp_init.restype = ctypes.c_void_p
    lib.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
    lib.seccomp_syscall_resolve_name.restype = ctypes.c_int
    lib.seccomp_rule_add.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_uint]
    lib.seccomp_rule_add.restype = ctypes.c_int
    lib.seccomp_load.argtypes = [ctypes.c_void_p]
    lib.seccomp_load.restype = ctypes.c_int
    lib.seccomp_release.argtypes = [ctypes.c_void_p]
    context = lib.seccomp_init(0x7FFF0000)
    if not context:
        raise OSError("seccomp_init_failed")
    try:
        for name in (b"socket", b"connect", b"socketpair"):
            number = lib.seccomp_syscall_resolve_name(name)
            if number < 0 or lib.seccomp_rule_add(context, 0x00050000 | errno.EPERM, number, 0):
                raise OSError("seccomp_rule_failed")
        if lib.seccomp_load(context):
            raise OSError("seccomp_load_failed")
    finally:
        lib.seccomp_release(context)


def probe_offline_socket_denial() -> bool:
    program = ("import errno,socket,subprocess,sys\n"
               "for family in (socket.AF_INET,socket.AF_INET6):\n"
               " try: socket.socket(family,socket.SOCK_STREAM)\n"
               " except OSError as e:\n"
               "  if e.errno!=errno.EPERM: raise SystemExit(2)\n"
               " else: raise SystemExit(3)\n"
               "child=subprocess.run([sys.executable,'-c',"
               "'import errno,socket;\\ntry: socket.socket(socket.AF_INET,socket.SOCK_STREAM)\\n"
               "except OSError as e: raise SystemExit(0 if e.errno==errno.EPERM else 2)\\n"
               "raise SystemExit(3)'])\n"
               "raise SystemExit(child.returncode)")
    result = subprocess.run([sys.executable, "-c", program], preexec_fn=_seccomp_no_sockets,
                            close_fds=True, capture_output=True, timeout=10)
    return result.returncode == 0


def _offline_go(go: Path, args: list[str], *, cwd: Path, cache: Path,
                timeout: int = 120) -> subprocess.CompletedProcess[str]:
    """Run only the private verified Go binary with inherited socket denial."""
    env = {"PATH": str(go.parent), "HOME": str(cwd), "GOTOOLCHAIN": "local",
           "GOPROXY": "off", "GOSUMDB": "off", "GOMODCACHE": str(cache),
           "GOPATH": str(cwd / "gopath"), "GOENV": "off", "GOWORK": "off",
           "CGO_ENABLED": "0", "LANG": "C", "LC_ALL": "C"}
    return subprocess.run([str(go), *args], cwd=cwd, env=env, preexec_fn=_seccomp_no_sockets,
                          close_fds=True, capture_output=True, text=True, timeout=timeout)


def _verify_offline_go_closure(go: Path, action: dict, destination: Path) -> None:
    root = destination / "offline-verification"
    root.mkdir(mode=0o700, exist_ok=False)
    cache = destination / "gomodcache"
    version = _offline_go(go, ["version"], cwd=root, cache=cache)
    if version.returncode or version.stdout.strip() != "go version go1.23.0 linux/amd64":
        _reject("go_version_mismatch")
    requirements = "\n".join(f"require {module} {version}" for module, version in sorted(DECLARED_MODULES))
    _atomic_private(root / "go.mod", ("module offline.invalid/starknet-dependency-check\n"
                                       "go 1.23.0\n" + requirements + "\n").encode())
    sums: list[str] = []
    for row in action["requests"]:
        if row["kind"] not in {"module_mod", "module_zip"}:
            continue
        path = urllib.parse.urlsplit(row["url"]).path.lstrip("/")
        module, tail = path.split("/@v/", 1)
        module = _unescape_module(module)
        version = tail.rsplit(".", 1)[0]
        sums.append(f"{module} {version}{'/go.mod' if row['kind'] == 'module_mod' else ''} {row['go_h1']}")
    _atomic_private(root / "go.sum", ("\n".join(sorted(sums)) + "\n").encode())
    for command in (["mod", "download", "all"], ["mod", "verify"]):
        result = _offline_go(go, command, cwd=root, cache=cache)
        if result.returncode:
            _reject("offline_closure_incomplete")


def _download(action: dict, destination: Path, transport: Any, monotonic: Callable[[], float],
              guard: Callable[[], None], meter: dict) -> None:
    start = monotonic()
    deadline = start + action["deadline_seconds"]
    receipts: list[dict] = meter["responses"]
    downloads = destination / "downloads"
    downloads.mkdir(mode=0o700, parents=True, exist_ok=True)
    official_archive: tuple[str, int] | None = None
    for index, row in enumerate(action["requests"]):
        chain = [row["url"], *row["redirects"]]
        for hop, url in enumerate(chain):
            guard()
            if meter["request_count"] >= action["max_requests"]:
                _reject("request_limit")
            if monotonic() >= deadline:
                _reject("deadline_exceeded")
            meter["request_count"] += 1
            try:
                status, headers, chunks = transport.open(url, max(0.001, deadline - monotonic()))
            except Exception as exc:
                _reject("transport_failed", type(exc).__name__)
            location = next((v for k, v in headers.items() if k.lower() == "location"), None)
            if 300 <= status < 400:
                redirected_bytes = 0
                try:
                    for chunk in chunks:
                        if not isinstance(chunk, bytes):
                            _reject("transport_failed")
                        if monotonic() >= deadline:
                            _reject("deadline_exceeded")
                        redirected_bytes += len(chunk)
                        meter["response_bytes"] += len(chunk)
                        if redirected_bytes > row["max_bytes"]:
                            _reject("object_limit")
                        if meter["response_bytes"] > action["max_total_bytes"]:
                            _reject("byte_limit")
                finally:
                    if hasattr(chunks, "close"):
                        chunks.close()
                receipts.append({"host": urllib.parse.urlsplit(url).hostname,
                                 "path_sha256": hashlib.sha256(urllib.parse.urlsplit(url).path.encode()).hexdigest(),
                                 "status": status, "bytes": redirected_bytes,
                                 "redirect_host": urllib.parse.urlsplit(location).hostname if location else None})
                if hop + 1 == len(chain) or location != chain[hop + 1]:
                    _reject("redirect_not_admitted")
                continue
            if status != 200 or hop + 1 != len(chain) or location is not None:
                if hasattr(chunks, "close"):
                    chunks.close()
                _reject("response_not_admitted")
            path = downloads / f"{index:03d}-{row['kind']}"
            digest = hashlib.sha256()
            length = 0
            fd, temporary = tempfile.mkstemp(prefix=".download-", dir=downloads)
            try:
                os.fchmod(fd, 0o600)
                with os.fdopen(fd, "wb") as stream:
                    for chunk in chunks:
                        if not isinstance(chunk, bytes):
                            _reject("transport_failed")
                        if monotonic() >= deadline:
                            _reject("deadline_exceeded")
                        length += len(chunk)
                        meter["response_bytes"] += len(chunk)
                        if length > row["max_bytes"]:
                            _reject("object_limit")
                        if meter["response_bytes"] > action["max_total_bytes"]:
                            _reject("byte_limit")
                        stream.write(chunk)
                        digest.update(chunk)
                    stream.flush()
                    os.fsync(stream.fileno())
                if digest.hexdigest() != row["sha256"]:
                    _reject("checksum_mismatch")
                os.link(temporary, path)
            finally:
                if hasattr(chunks, "close"):
                    chunks.close()
                if os.path.exists(temporary):
                    os.unlink(temporary)
            receipt = {"host": urllib.parse.urlsplit(url).hostname,
                       "path_sha256": hashlib.sha256(urllib.parse.urlsplit(url).path.encode()).hexdigest(),
                       "status": status, "kind": row["kind"], "bytes": length,
                       "sha256": digest.hexdigest(), "relative_file": f"downloads/{path.name}"}
            if "go_h1" in row:
                receipt["go_h1"] = row["go_h1"]
            receipts.append(receipt)
            if row["kind"] == "release_metadata" and not action["synthetic_fixture"]:
                try:
                    releases = json.loads(path.read_bytes())
                    matching = [item for release in releases if release.get("version") == GO_VERSION
                                for item in release.get("files", [])
                                if item.get("filename") == "go1.23.0.linux-amd64.tar.gz"]
                except (OSError, ValueError, AttributeError, TypeError):
                    _reject("release_metadata_invalid")
                if len(matching) != 1 or not isinstance(matching[0].get("size"), int):
                    _reject("release_metadata_invalid")
                official_archive = (matching[0].get("sha256"), matching[0]["size"])
                archive_row = next(r for r in action["requests"] if r["kind"] == "go_archive")
                if official_archive[0] != archive_row["sha256"] or official_archive[1] > archive_row["max_bytes"]:
                    _reject("official_checksum_mismatch")
            if row["kind"] == "go_archive" and not action["synthetic_fixture"]:
                if official_archive is None or (digest.hexdigest(), length) != official_archive:
                    _reject("official_checksum_mismatch")


def _safe_go_archive(archive: Path, destination: Path) -> Path:
    root = destination / "toolchain"
    root.mkdir(mode=0o700, exist_ok=False)
    unpacked = 0
    with tarfile.open(archive, "r:gz") as data:
        for member in data:
            parts = PurePosixPath(member.name).parts
            if not parts or parts[0] != "go" or any(part in ("", ".", "..") for part in parts):
                _reject("archive_path_invalid")
            if not (member.isdir() or member.isfile()) or member.size < 0:
                _reject("archive_member_invalid")
            output = root.joinpath(*parts)
            if member.isdir():
                output.mkdir(mode=0o700, parents=True, exist_ok=True)
                continue
            unpacked += member.size
            if unpacked > MAX_UNPACKED_GO:
                _reject("archive_oversize")
            output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            source = data.extractfile(member)
            if source is None:
                _reject("archive_member_invalid")
            mode = 0o700 if member.mode & 0o111 else 0o600
            fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
            with os.fdopen(fd, "wb") as stream:
                shutil.copyfileobj(source, stream, 65536)
    go = root / "go/bin/go"
    if not go.is_file():
        _reject("archive_member_invalid")
    return go


def _module_zip_h1(path: Path, *, prefix: str) -> str:
    rows: list[tuple[str, str]] = []
    names: set[str] = set()
    total = 0
    with zipfile.ZipFile(path) as archive:
        for entry in archive.infolist():
            if entry.is_dir():
                continue
            parts = PurePosixPath(entry.filename).parts
            if not entry.filename.startswith(prefix + "/") or ".." in parts or stat.S_ISLNK(entry.external_attr >> 16):
                _reject("module_zip_invalid")
            if entry.filename in names:
                _reject("module_zip_invalid")
            names.add(entry.filename)
            total += entry.file_size
            if total > MAX_UNPACKED_ZIP:
                _reject("module_zip_oversize")
            digest = hashlib.sha256()
            with archive.open(entry) as stream:
                while chunk := stream.read(65536):
                    digest.update(chunk)
            rows.append((entry.filename, digest.hexdigest()))
    return _go_h1_rows(rows)


def _materialize_offline_cache(action: dict, destination: Path, receipts: list[dict]) -> None:
    """Populate an isolated file cache; Go must still verify it offline later."""
    cache = destination / "gomodcache/cache/download"
    cache.mkdir(mode=0o700, parents=True, exist_ok=True)
    for row, receipt in zip(action["requests"], (x for x in receipts if x.get("status") == 200)):
        if row["kind"] not in {"module_mod", "module_info", "module_zip"}:
            continue
        path = urllib.parse.urlsplit(row["url"]).path.lstrip("/")
        if "/@v/" not in path:
            _reject("module_path_invalid")
        target = cache / path
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        source = destination / receipt["relative_file"]
        if row["kind"] == "module_mod" and _go_mod_h1(source.read_bytes()) != row["go_h1"]:
            _reject("go_h1_mismatch")
        if row["kind"] == "module_info":
            try:
                info = json.loads(source.read_bytes())
            except (OSError, ValueError):
                _reject("module_info_invalid")
            if not isinstance(info, dict) or info.get("Version") != path.rsplit("/", 1)[-1].removesuffix(".info"):
                _reject("module_info_invalid")
        if row["kind"] == "module_zip":
            stem = path.removesuffix(".zip")
            h1 = _module_zip_h1(source, prefix=stem.replace("/@v/", "@"))
            if h1 != row["go_h1"]:
                _reject("go_h1_mismatch")
        _atomic_private(target, source.read_bytes())
        if row["kind"] == "module_zip":
            _atomic_private(cache / (path + "hash"), (h1 + "\n").encode())


def run_stage(engagement: Path, request_id: str, actor_id: str, session_id: str, *,
              transport: Any | None = None, now: dt.datetime | None = None,
              monotonic: Callable[[], float] = time.monotonic) -> dict:
    """Spend exact kernel authority first, then perform one metered transfer."""
    from engagement_records import canonical_json_bytes, sha256_bytes
    from engagement_state import (RecordError, _append_kernel_event, assert_resume_current,
                                  base_event, engagement_lock, read_governed_file,
                                  read_ledger, reduce_engagement, require_approved_authority)

    engagement = engagement.resolve(strict=True)
    now = now or dt.datetime.now(dt.timezone.utc)
    timestamp = now.isoformat(timespec="seconds").replace("+00:00", "Z")
    if actor_id != f"local-uid-{os.getuid()}:broker" or session_id != f"session-posix-{os.getuid()}-{os.getsid(0)}":
        _reject("principal_mismatch")
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", request_id) is None or ".." in request_id:
        _reject("request_id_invalid")
    scope_file = engagement / "scope.md"
    if not scope_file.is_file():
        _reject("scope_missing")
    with engagement_lock(engagement) as bound:
        # Diagnose a changed governed action before replaying the reducer, which
        # otherwise reports every governed-file drift as a generic resume error.
        action_file = bound / f"authority/requests/{request_id}.action.json"
        try:
            action_bytes = read_governed_file(action_file)
            action = json.loads(action_bytes)
            recorded_request = next(
                item for item in reversed(read_ledger(bound, "event"))
                if item["event_type"] == "authority.requested"
                and item["payload"]["request_id"] == request_id
            )
        except (OSError, ValueError, RecordError, StopIteration, KeyError):
            _reject("action_binding_mismatch")
        if (action_bytes != canonical_json_bytes(action)
                or sha256_bytes(action_bytes) != recorded_request["payload"]["action_digest"]):
            _reject("action_binding_mismatch", "action bytes")
        try:
            state = assert_resume_current(bound)
        except (RecordError, OSError):
            _reject("scope_drift")
        if sha256_bytes(scope_file.read_bytes()) != state["scope_hash"]:
            _reject("scope_drift")
        scope_bytes = scope_file.read_bytes()
        fixture = transport is not None
        if fixture:
            if b"Synthetic dependency-stage fixture: `yes`" not in scope_bytes:
                _reject("scope_grant_missing")
        elif not _scope_requires_fresh_third_party_confirmation(scope_bytes):
            _reject("scope_grant_missing")
        request = state["authority_requests"].get(request_id)
        if request is None or request["status"] != "approved":
            _reject("authority_not_current")
        if action_bytes != canonical_json_bytes(action) or sha256_bytes(action_bytes) != request["action_digest"]:
            _reject("action_binding_mismatch", "action bytes")
        try:
            validate_stage_action(action, allow_fixture=fixture)
        except StageError as exc:
            _reject("action_binding_mismatch", str(exc))
        if (action["engagement_id"] != state["engagement_id"] or action["scope_hash"] != state["scope_hash"]
                or action["environment_ref"] != state["active_environment_ref"]
                or action["executor_id"] != actor_id or action["session_id"] != session_id
                or action["lane_id"] != request["lane_id"]
                or action["capability_sha256"] != hashlib.sha256(Path(__file__).read_bytes()).hexdigest()):
            _reject("action_binding_mismatch", "action bindings")
        if _scope_harness_revision(scope_bytes) != action["harness_commit"]:
            _reject("scope_harness_mismatch")
        if action["synthetic_fixture"] != fixture:
            _reject("fixture_not_admitted")
        preflight_ref = state["active_environment_ref"]
        if not preflight_ref or state["environment_preflights"].get(preflight_ref, {}).get("status") != "ready":
            _reject("environment_not_ready")
        preflight_path = bound / f"environment/preflight-{preflight_ref}.json"
        preflight = json.loads(read_governed_file(preflight_path))
        identity = preflight.get("identity", {})
        if (preflight.get("status") != "ready" or preflight.get("missing_fidelity")
                or identity.get("git_commit") != action["source_commit"]
                or identity.get("dirty_tracked_hash") != "sha256:" + hashlib.sha256(b"").hexdigest()):
            _reject("environment_not_ready")
        source = Path(action["source_repo"])
        harness = Path(__file__).resolve().parents[1]
        if (_git_head(source) != action["source_commit"] or not _source_clean(source)
                or _git_head(harness) != action["harness_commit"]
                or (not fixture and not _source_clean(harness))):
            _reject("source_identity_mismatch")
        if not fixture and source.resolve() != engagement.parent.parent.resolve():
            _reject("source_identity_mismatch")
        if now.tzinfo is None or abs((dt.datetime.now(dt.timezone.utc) - now).total_seconds()) > 60:
            _reject("authority_not_current")
        expires = dt.datetime.fromisoformat(str(request["expires_at"]).replace("Z", "+00:00"))
        if now > expires:
            _reject("authority_not_current")
        try:
            require_approved_authority(bound, request_id, "stage-go-dependencies",
                                       request["action_digest"], action["lane_id"], timestamp)
        except RecordError as exc:
            _reject("action_already_spent" if exc.code == "authority_request_already_consumed"
                    else "authority_not_current")
        operator = next(event["payload"]["operator_id"] for event in reversed(read_ledger(bound, "event"))
                        if event["event_type"] == "scope.attested")
        if action["operator_id"] != operator:
            _reject("action_binding_mismatch")
        if not fixture and os.environ.get("HTTPS_PROXY") != CLOUD_HTTPS_PROXY:
            _reject("cloud_proxy_unavailable")
        sandbox = bound / "sandbox"
        if not sandbox.exists():
            _reject("private_root_missing")
        _require_private_dir(sandbox)
        retrieval_root = sandbox / "dependency-retrieval"
        if retrieval_root.exists() or retrieval_root.is_symlink():
            _require_private_dir(retrieval_root)
        request_destination = retrieval_root / request_id
        if request_destination.exists() or request_destination.is_symlink():
            _reject("destination_exists")
        event = base_event(
            event_id=f"event-stage-spent-{request_id}", engagement_id=state["engagement_id"],
            recorded_at=timestamp, actor_role="broker", actor_id=actor_id,
            event_type="dependency.stage_spent", rationale="Spend exact dependency-staging authority before contact.",
            payload={"entity_id": request_id, "status": "spent", "authority_request_ref": request_id,
                     "action_digest": request["action_digest"], "scope_hash": state["scope_hash"],
                     "environment_ref": preflight_ref, "source_revision": action["source_commit"],
                     "executor_id": actor_id, "operator_id": operator},
            entity_refs=[request["request_event_ref"]], session_id=session_id, operation_class="authority",
        )
        try:
            _append_kernel_event(bound, event, lock_held=True)
        except RecordError as exc:
            _reject("spend_event_invalid", exc.code)

    # A failed transfer remains spent. Recheck source and scope before each HTTP request.
    def guard() -> None:
        if (hashlib.sha256(scope_file.read_bytes()).hexdigest() != action["scope_hash"].removeprefix("sha256:")
                or _git_head(source) != action["source_commit"] or not _source_clean(source)
                or _git_head(harness) != action["harness_commit"]
                or (not fixture and not _source_clean(harness))):
            _reject("identity_gate_failed")
        try:
            live = assert_resume_current(engagement)
        except (RecordError, OSError):
            _reject("identity_gate_failed")
        if (live["scope_hash"] != action["scope_hash"]
                or live["active_environment_ref"] != preflight_ref
                or live["environment_preflights"].get(preflight_ref, {}).get("status") != "ready"):
            _reject("identity_gate_failed")

    # The public CLI is single-process; keep its umask owner-only for all
    # descendants and nested module-cache directories created after spend.
    os.umask(0o077)
    destination = engagement / DESTINATION / request_id
    destination.mkdir(mode=0o700, parents=True, exist_ok=False)
    meter: dict[str, Any] = {"responses": [], "request_count": 0, "response_bytes": 0}
    stop_reason: str | None = None
    try:
        _download(action, destination, transport or RealTransport(), monotonic, guard, meter)
        if not fixture:
            archive = next(destination / row["relative_file"] for row in meter["responses"]
                           if row.get("kind") == "go_archive")
            go = _safe_go_archive(archive, destination)
            _materialize_offline_cache(action, destination, meter["responses"])
            _verify_offline_go_closure(go, action, destination)
    except StageError as exc:
        stop_reason = exc.code
    except (OSError, ValueError, tarfile.TarError, zipfile.BadZipFile,
            subprocess.SubprocessError, StopIteration):
        stop_reason = "stage_io_failed"
    manifest = {"schema_version": 1, "request_id": request_id, "action_digest": request["action_digest"],
                "scope_hash": action["scope_hash"], "source_commit": action["source_commit"],
                "request_count": meter["request_count"], "response_bytes": meter["response_bytes"],
                "responses": meter["responses"], "result": "stopped" if stop_reason else "completed",
                "stop_reason": stop_reason,
                "offline_resolver": {"GOTOOLCHAIN": "local", "GOPROXY": "off", "GOSUMDB": "off",
                                     "socket_syscalls": "seccomp_eperm"}}
    manifest_path = destination / "manifest.json"
    _atomic_private(manifest_path, canonical_json_bytes(manifest))
    from engagement_state import _append_kernel_event
    completed = base_event(
        event_id=f"event-stage-completed-{request_id}", engagement_id=state["engagement_id"],
        recorded_at=max(dt.datetime.now(dt.timezone.utc), now).isoformat(timespec="seconds").replace("+00:00", "Z"),
        actor_role="broker", actor_id=actor_id, event_type="dependency.stage_completed",
        rationale="Record the redacted private dependency-staging receipt.",
        payload={"entity_id": request_id, "status": "stopped" if stop_reason else "completed",
                 "record_path": str(manifest_path.relative_to(engagement)),
                 "record_digest": sha256_bytes(manifest_path.read_bytes()),
                 "source_revision": action["source_commit"]},
        entity_refs=[f"event-stage-spent-{request_id}"], session_id=session_id, operation_class="authority",
    )
    _append_kernel_event(engagement, completed)
    if stop_reason:
        _reject(stop_reason)
    return {"ok": True, "request_id": request_id, "request_count": meter["request_count"],
            "response_bytes": meter["response_bytes"], "manifest_path": str(manifest_path)}
