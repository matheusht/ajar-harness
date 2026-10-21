#!/usr/bin/env python3
"""Run the T01 Kanboard observer preflight against owned loopback copies."""

from __future__ import annotations

import argparse
import base64
import hashlib
import http.client
import json
import os
import re
import shutil
import socket
import subprocess
import tarfile
import tempfile
import time
from pathlib import Path
from urllib.request import urlopen


PINS = {
    "vulnerable": ("f0f7d27007f5a788f14416c548421efd740b7bce", "3f24269475bf00137d4b0d957d97a2567a5249101dad89067a49d609f4df2edf"),
    "fixed": ("a98bc5f855d4e7e47eb3425a6c7da6c6cc6748a3", "44db3df81a25bbd56c768c8b3180a1f05879e2c7fbaa6ac73707e7f3e9098f56"),
}
PHP_IMAGE = "kanboard/kanboard:v1.2.49"
PHP_IMAGE_DIGEST = "kanboard/kanboard@sha256:e22b60748cdd75e4ec85501715ec2a2f9fafbd2f97f01117f18eac5dbcc19ba9"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def call(port: int, username: str, password: str, method: str, params: list, trace: list) -> dict:
    body = json.dumps({"jsonrpc": "2.0", "method": method, "id": 1, "params": params}).encode()
    credential = base64.b64encode(f"{username}:{password}".encode()).decode()
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        connection.request("POST", "/jsonrpc.php", body, {
            "Content-Type": "application/json", "Authorization": f"Basic {credential}"
        })
        response = connection.getresponse()
        raw = response.read(64 * 1024)
        require(response.status in (200, 403), f"{method}: HTTP {response.status}")
        safe_params = ["[REDACTED]" if method == "createUser" and i == 1 else p for i, p in enumerate(params)]
        trace.append({"actor": username, "method": method, "params": safe_params,
                      "http_status": response.status, "raw_response": raw.decode(errors="replace")})
        value = json.loads(raw)
        require(isinstance(value, dict), f"{method}: invalid JSON-RPC object")
        value["_http_status"] = response.status
        return value
    finally:
        connection.close()


def result(value: dict, label: str):
    require("error" not in value, f"{label}: API error {value.get('error', {}).get('code')}")
    require("result" in value, f"{label}: missing result")
    return value["result"]


def denial(value: dict, label: str) -> dict:
    error = value.get("error")
    require(isinstance(error, dict), f"{label}: unexpectedly returned a result")
    code = error.get("code")
    message = str(error.get("message", ""))
    require(value.get("_http_status") == 403 and (code == 403 or "access denied" in message.lower()), f"{label}: unrelated error {code}: {message}")
    return {"code": code, "message": message}


def default_admin_password(source: Path) -> str:
    # Read the application's shipped initial credential at runtime; never save it in evidence.
    text = (source / "app/Schema/Sqlite.php").read_text()
    match = re.search(r"password_hash\('([^']+)', PASSWORD_BCRYPT\)", text)
    require(match is not None, "initial local admin credential unavailable")
    return match.group(1)


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def run_arm(label: str, source: Path, work: Path, evidence: Path, container_php: bool) -> dict:
    app = work / "app"
    shutil.copytree(source, app)
    port = free_port()
    log_path = work / "server.log"
    admin_secret = default_admin_password(app)
    # Synthetic credentials exist only in this process and the disposable app database.
    import secrets
    alice_secret, bob_secret = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
    trace: list = []
    with log_path.open("wb") as log:
        if container_php:
            container_id = subprocess.check_output([
                "docker", "run", "-d", "--rm", "--pull=never", "--read-only", "--user", str(os.getuid()),
                "--network", "bridge", "--memory", "512m", "--cpus", "2", "--pids-limit", "128",
                "--tmpfs", "/tmp:rw,nosuid,size=64m", "-p", f"127.0.0.1:{port}:{port}",
                "--mount", f"type=bind,source={app},target=/app", "--workdir", "/app",
                "--entrypoint", "php", PHP_IMAGE, "-S", f"0.0.0.0:{port}", "-t", "/app",
            ], text=True).strip()
            server = None
        else:
            container_id = None
            server = subprocess.Popen(
                ["php", "-S", f"127.0.0.1:{port}", "-t", str(app)],
                cwd=app, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "TMPDIR": str(work)},
            )
        try:
            for _ in range(50):
                require(server is None or server.poll() is None, f"{label}: server exited during startup")
                try:
                    with urlopen(f"http://127.0.0.1:{port}/robots.txt", timeout=0.2) as ready:
                        require(ready.status == 200, f"{label}: readiness request failed")
                        break
                except OSError:
                    time.sleep(0.1)
            else:
                raise RuntimeError(f"{label}: server did not bind")

            admin = lambda method, params: call(port, "admin", admin_secret, method, params, trace)
            alice = lambda method, params: call(port, "alice", alice_secret, method, params, trace)
            bob = lambda method, params: call(port, "bob", bob_secret, method, params, trace)
            alice_id = result(admin("createUser", ["alice", alice_secret]), "create alice")
            bob_id = result(admin("createUser", ["bob", bob_secret]), "create bob")
            require(type(alice_id) is int and type(bob_id) is int and alice_id != bob_id, "synthetic users invalid")
            project_id = result(admin("createProject", ["Observer Private Project"]), "create project")
            require(type(project_id) is int, "private project invalid")
            result(admin("addProjectUser", [project_id, alice_id, "project-manager"]), "grant alice")
            own_project = result(alice("getProjectById", [project_id]), "authorized project")
            require(own_project["id"] == project_id, "authorized project identity mismatch")
            denied_project = denial(bob("getProjectById", [project_id]), "private project control")
            swimlane_id = result(alice("addSwimlane", [project_id, "Observer Swimlane", "Synthetic description"]), "create swimlane")
            require(type(swimlane_id) is int, "synthetic swimlane invalid")
            own_swimlane = result(alice("getSwimlane", [swimlane_id]), "authorized swimlane")
            require(own_swimlane["id"] == swimlane_id and own_swimlane["project_id"] == project_id, "authorized swimlane identity mismatch")
            cross_read = bob("getSwimlane", [swimlane_id])
            if label == "vulnerable":
                cross_metadata = result(cross_read, "vulnerable cross-role read")
                require(cross_metadata["id"] == swimlane_id and cross_metadata["project_id"] == project_id, "cross-role effect identity mismatch")
                effect = {"result": {"id": cross_metadata["id"], "project_id": cross_metadata["project_id"], "name": cross_metadata["name"]}}
            else:
                effect = {"denial": denial(cross_read, "fixed cross-role read")}
            require((app / "data/db.sqlite").is_file(), f"{label}: expected SQLite database absent")
            summary = {
                "release": label, "loopback": True,
                "php": subprocess.check_output(["docker", "run", "--rm", "--network", "none", "--entrypoint", "php", PHP_IMAGE, "--version"], text=True).splitlines()[0]
                if container_php else subprocess.check_output(["php", "--version"], text=True).splitlines()[0],
                "runtime": PHP_IMAGE_DIGEST if container_php else "host",
                "project_id": project_id, "swimlane_id": swimlane_id,
                "authorized_project": own_project["id"], "authorized_swimlane": own_swimlane["id"],
                "private_project_control": denied_project, "cross_role_read": effect,
            }
            for entry in trace:
                for secret in (admin_secret, alice_secret, bob_secret):
                    entry["raw_response"] = entry["raw_response"].replace(secret, "[REDACTED]")
                entry["raw_response"] = re.sub(r'("(?:token|access_token|session|cookie)"\s*:\s*")[^"]*(")',
                                               r'\1[REDACTED]\2', entry["raw_response"], flags=re.I)
            (evidence / f"{label}-requests.json").write_text(json.dumps(trace, indent=2) + "\n")
            return summary
        finally:
            if container_id:
                try:
                    raw = subprocess.check_output(["docker", "logs", container_id], stderr=subprocess.STDOUT, text=True)
                finally:
                    stopped = subprocess.run(["docker", "stop", "--time", "5", container_id], check=True, capture_output=True, text=True)
                container_absent = False
                for _ in range(50):
                    if subprocess.run(["docker", "inspect", container_id], capture_output=True).returncode != 0:
                        container_absent = True
                        break
                    time.sleep(0.1)
                require(container_absent, f"{label}: owned container still exists")
            else:
                server.terminate()
                try:
                    server.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait(timeout=5)
                require(server.poll() is not None, f"{label}: owned PHP process still exists")
                raw = log_path.read_text(errors="replace")
            for secret in (admin_secret, alice_secret, bob_secret):
                raw = raw.replace(secret, "[REDACTED]")
            (evidence / f"{label}-server.log").write_text(raw)
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                    raise RuntimeError(f"{label}: owned server still listening")
            except OSError:
                pass
            if "summary" in locals():
                summary["cleanup"] = {
                    "container_id": container_id,
                    "host_pid": None if container_id else server.pid,
                    "loopback_port": port,
                    "stop_returncode": stopped.returncode if container_id else server.returncode,
                    "container_absent": container_absent if container_id else None,
                    "port_closed": True,
                }


def prepare_source(root: Path, label: str, commit: str, digest: str) -> Path:
    archive = root / f"{label}.tar.gz"
    source = root / label / "app"
    if not archive.exists():
        pending = root / f"{label}.download"
        require(not pending.exists(), f"{label}: incomplete prior download present")
        try:
            with urlopen(f"https://codeload.github.com/kanboard/kanboard/tar.gz/{commit}", timeout=60) as response, pending.open("xb") as out:
                while chunk := response.read(1024 * 1024):
                    out.write(chunk)
            require(hashlib.sha256(pending.read_bytes()).hexdigest() == digest, f"{label}: downloaded archive hash mismatch")
            pending.rename(archive)
        finally:
            pending.unlink(missing_ok=True)
    require(archive.is_file() and hashlib.sha256(archive.read_bytes()).hexdigest() == digest, f"{label}: archive hash mismatch")
    if not source.exists():
        source.parent.mkdir(mode=0o700)
        with tempfile.TemporaryDirectory(prefix=f"{label}-extract-", dir=root) as temp:
            with tarfile.open(archive, "r:gz") as tf:
                tf.extractall(temp, filter="data")
            extracted = Path(temp) / f"kanboard-{commit}"
            require(extracted.is_dir(), f"{label}: unexpected archive root")
            extracted.rename(source)
    require(source.is_dir() and (source / "vendor/autoload.php").is_file(), f"{label}: source/dependencies absent")
    with tarfile.open(archive, "r:gz") as tf:
        members = [m for m in tf.getmembers() if m.isfile()]
        expected = set()
        for member in members:
            relative = Path(member.name).relative_to(f"kanboard-{commit}")
            expected.add(relative)
            target = source / relative
            require(target.is_file() and not target.is_symlink(), f"{label}: source file absent or linked: {relative}")
            require(hashlib.sha256(target.read_bytes()).digest() == hashlib.sha256(tf.extractfile(member).read()).digest(),
                    f"{label}: source file changed: {relative}")
    actual = {p.relative_to(source) for p in source.rglob("*") if p.is_file()}
    require(actual == expected, f"{label}: source contains extra or missing files")
    require(not any(p.name == ".git" for p in source.rglob(".git")), f"{label}: Git history leaked")
    return source


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--observer-root", type=Path, required=True)
    parser.add_argument("--researcher-root", type=Path, help="create one clean, answer-free researcher copy")
    parser.add_argument("--container-php", action="store_true", help="use the pinned Kanboard PHP image")
    args = parser.parse_args()
    root = args.observer_root.expanduser()
    root.mkdir(mode=0o700, exist_ok=True)
    root = root.resolve(strict=True)
    require(root.is_dir() and root.stat().st_uid == os.getuid() and root.stat().st_mode & 0o077 == 0,
            "observer root must be private and owned by current user")
    evidence = root / "evidence"
    evidence.mkdir(mode=0o700, exist_ok=True)
    if args.container_php:
        image = json.loads(subprocess.check_output(["docker", "image", "inspect", PHP_IMAGE], text=True))[0]
        require(PHP_IMAGE_DIGEST in image["RepoDigests"], "pinned PHP image digest absent")
    summaries = []
    for label, (commit, digest) in PINS.items():
        source = prepare_source(root, label, commit, digest)
        with tempfile.TemporaryDirectory(prefix=f"{label}-run-", dir=root) as temp:
            summary = run_arm(label, source, Path(temp), evidence, args.container_php)
            run_dir = Path(temp)
            db_path = run_dir / "app/data/db.sqlite"
        require(not run_dir.exists() and not db_path.exists(), f"{label}: disposable run directory or DB remained")
        summary["cleanup"].update({
            "run_dir": str(run_dir), "run_dir_absent": True,
            "db_path": str(db_path), "db_absent": True,
        })
        summary["commit"] = commit
        summary["archive_sha256"] = digest
        summaries.append(summary)
    output = {"case": "Kanboard local observer preflight", "status": "pass", "arms": summaries}
    (evidence / "observer-results.json").write_text(json.dumps(output, indent=2) + "\n")
    if args.researcher_root:
        researcher = args.researcher_root.expanduser()
        require(not researcher.exists(), "researcher destination already exists")
        require(not researcher.resolve().is_relative_to(root), "researcher destination must be outside observer root")
        researcher.mkdir(mode=0o700)
        shutil.copytree(root / "vulnerable" / "app", researcher / "source")
        shutil.copyfile(Path(__file__).with_name("RESEARCHER-BRIEF.md"), researcher / "BRIEF.md")
        require(not any(p.name == ".git" for p in researcher.rglob(".git")), "researcher copy contains Git history")
        require(not any(p.name in ("observer-results.json", "CHECKS.md", "observer_case.py") for p in researcher.rglob("*")),
                "researcher copy contains observer material")
    print(json.dumps({"status": "pass", "evidence": str(evidence / "observer-results.json")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
