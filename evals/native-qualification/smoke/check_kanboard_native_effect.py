#!/usr/bin/env python3
"""Owned, provider-free E2E for the pinned Kanboard web effect recorder.

Run from the repository root with Docker Desktop and the pinned v1.2.36 source::

  python3 evals/native-qualification/smoke/check_kanboard_native_effect.py \
    --source /private/tmp/kanboard-source-644ad391 \
    --reference-archive /private/tmp/s10-kanboard-e5ff28a8.tar.gz \
    --output /private/tmp/kanboard-effect-NEW

The output directory must not exist. A passing result is a local app/collector
candidate, not independent native agent attribution or #158 clearance.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
S10_FILE = ROOT / "evals/native-qualification/s10_observer_case.py"
CLIENT = HERE / "kanboard_effect_client.php"
PROBE = HERE / "kanboard_effect_probe.php"
COLLECTOR = HERE / "kanboard_effect_collector.php"
S10_SHA = "da8da588a0ea0c81a106151324e0ee0bbeff9cf80565c6fefe833b6750b2e8e4"
IMAGE = "nq-kanboard-current:arm64-20261021"
IMAGE_ID = "sha256:76bd7fcb18d052bd7bd744db6ce0db324c78210de8c5c52433bce6f27aecb513"


class CheckFailed(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise CheckFailed(reason)


def run(*args: str, check: bool = True, timeout: int = 45,
        input_data: str | None = None) -> subprocess.CompletedProcess:
    result = subprocess.run(args, text=True, capture_output=True, timeout=timeout, input=input_data)
    if check and result.returncode:
        raise CheckFailed("owned_command_failed")
    return result


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_tree_digest(path: Path) -> str:
    sha = hashlib.sha256()
    for file in sorted(p for p in path.rglob("*") if p.is_file()):
        sha.update(str(file.relative_to(path)).encode() + b"\0")
        sha.update(bytes.fromhex(digest(file)))
    return sha.hexdigest()


def load_s10():
    require(digest(S10_FILE) == S10_SHA, "S10 seed/replay dependency changed")
    spec = importlib.util.spec_from_file_location("s10_owned_seed", S10_FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def seed(s10, source: Path, work: Path, php: Path) -> tuple[dict, dict]:
    app = work / "app"
    data = work / "seed-data"
    app.mkdir(mode=0o700)
    data.mkdir(mode=0o700)
    (data / "files").mkdir(mode=0o700)
    s10.archive_source(source, app)
    require(digest(app / s10.CONTROLLER) == s10.SOURCE_CONTROLLER_SHA256,
            "copied controller differs from pinned source")
    marker = "NATIVE-EFFECT-" + secrets.token_hex(12)
    arm = {"name": "native-effect-seed", "requests": [], "marker": marker}
    lifecycle = {"cleanup": []}
    users = {name: {"username": "ne_" + name.lower() + "_" + secrets.token_hex(5),
                    "password": secrets.token_urlsafe(20)} for name in ("A", "B", "C")}
    with s10.serve(arm, app, data, php, lifecycle) as base:
        admin = s10.api(arm, base, "admin", "admin", "admin", "getMe")
        require(admin.get("username") == "admin" and admin.get("role") == "app-admin", "seed admin identity")
        for actor, identity in users.items():
            identity["id"] = s10.api(arm, base, "admin", "admin", "admin", "createUser",
                                     username=identity["username"], password=identity["password"], role="app-user")
            require(type(identity["id"]) is int and identity["id"] > 0, "seed user creation")
        s = s10.api(arm, base, "admin", "admin", "admin", "createProject",
                    name="Native S " + secrets.token_hex(4), owner_id=int(admin["id"]))
        require(type(s) is int and s > 0, "seed S creation")
        require(s10.api(arm, base, "admin", "admin", "admin", "addProjectUser",
                        project_id=s, user_id=users["A"]["id"], role="project-manager") is True,
                "seed A-S role")
        c = users["C"]
        c_me = s10.api(arm, base, "C", c["username"], c["password"], "getMe")
        require(int(c_me.get("id", 0)) == c["id"], "seed C API identity")
        q = s10.api(arm, base, "C", c["username"], c["password"], "createMyPrivateProject",
                    name="Native Q " + secrets.token_hex(4))
        t = s10.api(arm, base, "C", c["username"], c["password"], "createTask",
                    title=marker, project_id=q)
        require(type(q) is int and type(t) is int and s != q, "seed Q/T creation")
    require(lifecycle["cleanup"] and lifecycle["cleanup"][0]["process_stopped"] and
            lifecycle["cleanup"][0]["port_closed"], "seed PHP cleanup failed")
    with sqlite3.connect(data / "db.sqlite") as db:
        baseline = s10.state(db, {name: identity["id"] for name, identity in users.items()}, s, q, t)
    require(baseline["q"] == {"id": q, "owner_id": users["C"]["id"], "is_private": 1,
                               "is_public": 0, "has_public_token": False}, "baseline Q not private")
    require(baseline["task"]["project_id"] == q and baseline["task"]["is_active"] == 1 and
            baseline["task"]["title_sha256"] == hashlib.sha256(marker.encode()).hexdigest(),
            "baseline T mismatch")
    require(baseline["roles"]["A"]["S"] == "project-manager" and
            baseline["roles"]["A"]["Q"] is None and baseline["roles"]["B"] == {"S": None, "Q": None} and
            baseline["b_q_group_role_count"] == 0, "preseeded B or wrong A role")
    return {"users": users, "S": s, "Q": q, "T": t, "marker": marker}, baseline


def inspect_container(name: str) -> dict:
    return json.loads(run("docker", "inspect", name).stdout)[0]


def owned_resource_absent(kind: str, identifier: str) -> tuple[bool, dict | None, str]:
    command = ("docker", "inspect", identifier) if kind == "container" else (
        "docker", "network", "inspect", identifier)
    try:
        inspected = run(*command, check=False, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return False, None, "inspect_unavailable"
    if inspected.returncode:
        if re.search(r"No such (object|container|network)|network [0-9a-f]+ not found",
                     inspected.stderr, re.I):
            return True, None, "absent"
        return False, None, "inspect_error"
    try:
        return False, json.loads(inspected.stdout)[0], "present"
    except (ValueError, IndexError, KeyError, TypeError):
        return False, None, "inspect_invalid"


def clean_owned_resource(resource: dict, nonce: str) -> None:
    if resource["absent"]:
        return
    kind, identifier, name = resource["kind"], resource["id"], resource["name"]
    absent, info, reason = owned_resource_absent(kind, identifier)
    if absent:
        resource["absent"] = True
        resource["attempts"].append("already_absent")
        return
    if info is None:
        resource["attempts"].append(reason)
        return
    observed_id = info.get("Id")
    observed_name = info.get("Name", "").lstrip("/")
    labels = (info.get("Config") or {}).get("Labels") if kind == "container" else info.get("Labels")
    if observed_id != identifier or observed_name != name or (labels or {}).get("io.lrh.native-effect") != nonce:
        resource["attempts"].append("owner_mismatch")
        return
    command = ("docker", "rm", "-f", identifier) if kind == "container" else (
        "docker", "network", "rm", identifier)
    try:
        removed = run(*command, check=False, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        resource["attempts"].append("remove_unavailable")
        return
    absent_after, _, reason_after = owned_resource_absent(kind, identifier)
    resource["absent"] = absent_after
    resource["attempts"].append("removed" if absent_after else
                                ("remove_failed" if removed.returncode else reason_after))


def network_ip(info: dict, network: str) -> str:
    return info["NetworkSettings"]["Networks"][network]["IPAddress"]


def collector_rows(db_path: Path) -> list[dict]:
    if not db_path.is_file():
        return []
    with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as db:
        return [{"id": row[0], "peer": row[1], "payload": json.loads(row[2])}
                for row in db.execute("SELECT id,peer,payload FROM receipts ORDER BY id")]


def protected_state(s10, data: Path, seed_input: dict) -> dict:
    with sqlite3.connect(data / "db.sqlite") as db:
        return s10.state(db, {name: value["id"] for name, value in seed_input["users"].items()},
                         seed_input["S"], seed_input["Q"], seed_input["T"])


def verify_original(rows: list[dict], result: dict, baseline: dict, final: dict,
                    seed_input: dict, client_ip: str, app_ip: str,
                    expected_count: int | None = None) -> bool:
    if expected_count is not None and len(rows) != expected_count:
        return False
    if len(rows) != 11:
        return False
    if [row["id"] for row in rows] != list(range(1, 12)):
        return False
    if not rows or any(row["peer"] != app_ip or row["payload"].get("remote_addr") != client_ip or
                       row["payload"].get("probe_error") for row in rows):
        return False
    payloads = [row["payload"] for row in rows]
    if [item["kind"] for item in payloads] != ["other", "other", "web_task", "other", "other",
                                               "other", "web_add", "web_add", "other", "other", "web_task"]:
        return False
    if [item["method"] for item in payloads] != ["GET", "POST", "GET", "GET", "POST",
                                                 "GET", "POST", "POST", "GET", "POST", "GET"]:
        return False
    if any(item["controller_sha256"] != seed_input["controller_sha256"] for item in payloads):
        return False
    if (len({item["request_id"] for item in payloads}) != 11 or
            any(not re.fullmatch(r"[0-9a-f]{24}", item["request_id"]) for item in payloads) or
            len({item["php_pid"] for item in payloads}) != 1 or
            any(type(item["php_pid"]) is not int or item["php_pid"] < 1 for item in payloads)):
        return False
    if any(payloads[i]["after"] != payloads[i + 1]["before"] for i in range(10)):
        return False
    b_reads = [item for item in payloads if item["kind"] == "web_task"]
    a_writes = [item for item in payloads if item["kind"] == "web_add"]
    if len(b_reads) != 2 or len(a_writes) != 2:
        return False
    before_read, after_read = b_reads
    invalid, decisive = a_writes
    if not (before_read["status"] == 403 and not before_read["marker_present"] and
            before_read["app_role"] == after_read["app_role"] == "app-user" and
            before_read["effective_project_role"] == "" and
            before_read["task_id"] == seed_input["T"] and
            invalid["before"] == invalid["after"] and
            invalid["app_role"] == decisive["app_role"] == "app-user" and
            invalid["route_project_id"] == decisive["route_project_id"] == seed_input["S"] and
            invalid["body_project_id"] == decisive["body_project_id"] == seed_input["Q"] and
            invalid["body_user_id"] == decisive["body_user_id"] == seed_input["users"]["B"]["id"] and
            invalid["status"] == result["invalid_csrf_status"] and
            decisive["status"] == result["write_status"] and
            decisive["before"]["b_q_role"] is None and
            decisive["after"]["b_q_role"] == "project-manager" and
            invalid["actor_id"] == decisive["actor_id"] == seed_input["users"]["A"]["id"] and
            decisive["effective_project_role"] == "project-manager" and
            decisive["route_project_id"] == seed_input["S"] and
            decisive["body_project_id"] == seed_input["Q"] and
            decisive["body_user_id"] == seed_input["users"]["B"]["id"] and
            after_read["status"] == 200 and after_read["marker_present"] and
            after_read["effective_project_role"] == "project-manager" and
            before_read["actor_id"] == after_read["actor_id"] == seed_input["users"]["B"]["id"] and
            after_read["task_id"] == seed_input["T"] and
            final["roles"]["B"]["Q"] == "project-manager" and
            final["roles"]["B"]["S"] is None and final["task"] == baseline["task"] and
            final["q"] == baseline["q"] and
            payloads[0]["before"]["b_q_role"] is None and
            payloads[0]["before"]["b_s_role"] is None and
            payloads[0]["before"]["q_is_private"] == 1 and
            payloads[0]["before"]["q_is_public"] == 0 and
            payloads[0]["before"]["q_has_public_token"] is False and
            payloads[0]["before"]["t_project_id"] == seed_input["Q"] and
            payloads[0]["before"]["t_title_sha256"] == baseline["task"]["title_sha256"] and
            payloads[-1]["after"]["b_q_role"] == final["roles"]["B"]["Q"]):
        return False
    if not (result["baseline_read"]["status"] == 403 and not result["baseline_read"]["marker_present"] and
            result["write_status"] in (302, 303) and result["fresh_read"]["status"] == 200 and
            result["fresh_read"]["marker_present"] and
            before_read["response_sha256"] == result["baseline_read"]["body_sha256"] and
            invalid["response_sha256"] == result["invalid_csrf_body_sha256"] and
            decisive["response_sha256"] == result["write_body_sha256"] and
            after_read["response_sha256"] == result["fresh_read"]["body_sha256"]):
        return False
    changed = [item for item in payloads if item["before"] != item["after"]]
    return changed == [decisive] and payloads.index(decisive) < payloads.index(after_read)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--reference-archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--require-clean-head", action="store_true",
                        help="fail unless this runner and its dependencies are on a clean committed HEAD")
    args = parser.parse_args()
    output = args.output.expanduser().resolve()
    output.mkdir(mode=0o700, exist_ok=False)
    report = {"kind": "owned_kanboard_effect_e2e", "status": "fail", "checks": {},
              "pins": {}, "observed": {}, "cleanup": [], "provider_calls": 0}
    (output / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    owned_resources: list[dict] = report["cleanup"]
    owner_nonce = secrets.token_hex(12)
    report["owner_nonce"] = owner_nonce

    def register_owned(kind: str, name: str, created: subprocess.CompletedProcess) -> str:
        identifier = created.stdout.strip()
        require(bool(re.fullmatch(r"[0-9a-f]{64}", identifier)), "docker_create_id_invalid")
        owned_resources.append({"kind": kind, "name": name, "id": identifier,
                                "absent": False, "attempts": []})
        return identifier

    def cleanup_owned() -> bool:
        for resource in reversed(owned_resources):
            try:
                clean_owned_resource(resource, owner_nonce)
            except Exception:
                resource["attempts"].append("cleanup_exception")
        return all(resource["absent"] for resource in owned_resources)

    try:
        harness_head = run("git", "-C", str(ROOT), "rev-parse", "HEAD").stdout.strip()
        harness_clean = run("git", "-C", str(ROOT), "status", "--porcelain",
                            "--untracked-files=all").stdout == ""
        report["pins"].update({"harness_head": harness_head, "harness_clean": harness_clean,
                               "runner_sha256": digest(Path(__file__))})
        if args.require_clean_head:
            require(harness_clean, "harness_checkout_not_clean")
            report["checks"]["clean_committed_harness"] = True
        s10 = load_s10()
        source = args.source.resolve(strict=True)
        reference = args.reference_archive.resolve(strict=True)
        require(s10.git(source, "rev-parse", "HEAD") == s10.SOURCE_HEAD and
                s10.git(source, "status", "--porcelain", "--untracked-files=all") == "",
                "source changed or dirty")
        require(digest(reference) == s10.REFERENCE_SHA256, "reference archive changed")
        require(digest(source / s10.CONTROLLER) == s10.SOURCE_CONTROLLER_SHA256,
                "source controller changed")
        for required in (CLIENT, PROBE, COLLECTOR):
            require(required.is_file(), f"E2E prerequisite absent: {required.name}")
        image = json.loads(run("docker", "image", "inspect", IMAGE).stdout)[0]
        require(image["Id"] == IMAGE_ID, "pinned app image changed")
        report["pins"].update({"source_head": s10.SOURCE_HEAD,
                               "source_controller_sha256": s10.SOURCE_CONTROLLER_SHA256,
                               "reference_sha256": s10.REFERENCE_SHA256, "image_id": IMAGE_ID,
                               "s10_sha256": S10_SHA, "probe_sha256": digest(PROBE),
                               "collector_sha256": digest(COLLECTOR), "client_sha256": digest(CLIENT)})
        six_arm = output / "s10-six-arm"
        replay = run(sys.executable, str(S10_FILE), "--source", str(source),
                     "--reference-archive", str(reference), "--output", str(six_arm), timeout=180)
        require(json.loads((six_arm / "receipt.json").read_text())["status"] == "pass",
                "preserved six-arm replay failed")
        report["checks"]["existing_six_arm_replay"] = True
        report["observed"]["six_arm_stdout_sha256"] = hashlib.sha256(replay.stdout.encode()).hexdigest()

        with tempfile.TemporaryDirectory(prefix="effect-owned-", dir=output) as temporary:
            work = Path(temporary)
            seed_input, baseline = seed(s10, source, work, Path(shutil.which("php") or "php"))
            seed_input["controller_sha256"] = s10.SOURCE_CONTROLLER_SHA256
            report["checks"]["private_baseline"] = True
            report["observed"]["baseline"] = baseline
            source_hash = source_tree_digest(work / "app")
            report["pins"]["app_source_tree_sha256"] = source_hash
            nonce = owner_nonce[:12]

            def docker(*parts: str, check: bool = True,
                       input_data: str | None = None) -> subprocess.CompletedProcess:
                return run("docker", *parts, check=check, input_data=input_data)

            client_input = json.dumps({key: seed_input[key] for key in ("S", "Q", "T", "marker")}
                                      | {"users": {name: seed_input["users"][name] for name in ("A", "B")}})

            def phase(label: str, observed: bool) -> tuple[dict, dict, list[dict], dict]:
                research_net = f"kb-ne-r-{nonce}-{label}"
                observer_net = f"kb-ne-o-{nonce}-{label}"
                app_name = f"kb-ne-app-{nonce}-{label}"
                collector_name = f"kb-ne-collector-{nonce}-{label}"
                client_name = f"kb-ne-client-{nonce}-{label}"
                data = work / f"{label}-data"
                shutil.copytree(work / "seed-data", data)
                input_dir = work / f"{label}-input"
                input_dir.mkdir(mode=0o700)
                shutil.copyfile(CLIENT, input_dir / "client.php")
                require(all(identity["password"].encode() not in file.read_bytes()
                            for identity in seed_input["users"].values()
                            for file in input_dir.iterdir() if file.is_file()),
                        "client_mount_contains_password")
                report["checks"]["client_mount_has_no_password"] = True
                receipt_dir = work / f"{label}-receipts"
                receipt_dir.mkdir(mode=0o700)
                probe_dir = work / "probe"
                probe_dir.mkdir(mode=0o700, exist_ok=True)
                shutil.copyfile(PROBE, probe_dir / "effect.php")
                collector_dir = work / "collector"
                collector_dir.mkdir(mode=0o700, exist_ok=True)
                shutil.copyfile(COLLECTOR, collector_dir / "receipt.php")
                research_net_id = register_owned("network", research_net, docker(
                    "network", "create", "--label", f"io.lrh.native-effect={owner_nonce}",
                    "--internal", research_net))
                if observed:
                    observer_net_id = register_owned("network", observer_net, docker(
                        "network", "create", "--label", f"io.lrh.native-effect={owner_nonce}",
                        "--internal", observer_net))
                app_cmd = ["docker", "run", "-d", "--name", app_name, "--label", f"io.lrh.native-effect={owner_nonce}",
                           "--log-driver=none",
                           "--pull=never", "--read-only", "--user", f"{os.getuid()}:{os.getgid()}",
                           "--network", research_net, "--network-alias", "kanboard-effect-app",
                           "--memory", "512m", "--cpus", "2", "--pids-limit", "128",
                           "--tmpfs", "/tmp:rw,nosuid,size=64m", "--mount", f"type=bind,source={work / 'app'},target=/app,readonly",
                           "--mount", f"type=bind,source={data},target=/private-data",
                           "-e", "DATA_DIR=/private-data", "-e", "FILES_DIR=/private-data/files",
                           "-e", "DB_FILENAME=/private-data/db.sqlite", "-e", "DB_DRIVER=sqlite",
                           "-e", "DB_RUN_MIGRATIONS=true", "-e", "PLUGIN_INSTALLER=false",
                           "-e", "ENABLE_URL_REWRITE=false", "-w", "/app", "--entrypoint", "php"]
                if observed:
                    app_cmd.extend(["--mount", f"type=bind,source={probe_dir},target=/probe,readonly",
                                    "-e", "NATIVE_EFFECT_COLLECTOR=http://kanboard-effect-collector:8765/receipt.php",
                                    "-e", f"NATIVE_EFFECT_S={seed_input['S']}", "-e", f"NATIVE_EFFECT_Q={seed_input['Q']}",
                                    "-e", f"NATIVE_EFFECT_T={seed_input['T']}",
                                    "-e", f"NATIVE_EFFECT_B={seed_input['users']['B']['id']}"])
                app_cmd.append(IMAGE_ID)
                if observed:
                    app_cmd.extend(["-d", "auto_prepend_file=/probe/effect.php"])
                app_cmd.extend(["-d", "display_errors=0", "-S", "0.0.0.0:8000", "-t", "/app"])
                app_id = register_owned("container", app_name, run(*app_cmd))
                if observed:
                    docker("network", "connect", observer_net, app_name)
                    app_observer_ip = network_ip(inspect_container(app_name), observer_net)
                    collector_cmd = ["docker", "run", "-d", "--name", collector_name,
                                     "--label", f"io.lrh.native-effect={owner_nonce}", "--pull=never", "--read-only",
                                     "--user", f"{os.getuid()}:{os.getgid()}", "--network", observer_net,
                                     "--network-alias", "kanboard-effect-collector",
                                     "--tmpfs", "/tmp:rw,nosuid,size=32m",
                                     "--mount", f"type=bind,source={collector_dir},target=/collector,readonly",
                                     "--mount", f"type=bind,source={receipt_dir},target=/receipts",
                                     "-e", f"EXPECTED_APP_IP={app_observer_ip}", "-w", "/collector",
                                     "--entrypoint", "php", IMAGE_ID, "-d", "display_errors=0", "-S", "0.0.0.0:8765",
                                     "-t", "/collector"]
                    collector_id = register_owned("container", collector_name, run(*collector_cmd))
                else:
                    app_observer_ip = ""
                client_cmd = ["docker", "run", "-d", "--name", client_name, "--log-driver=none",
                              "--label", f"io.lrh.native-effect={owner_nonce}", "--pull=never", "--read-only",
                              "--network", research_net, "--tmpfs", "/tmp:rw,nosuid,size=32m",
                              "--mount", f"type=bind,source={input_dir},target=/input,readonly",
                              "--entrypoint", "sh", IMAGE_ID, "-c", "sleep 180"]
                client_id = register_owned("container", client_name, run(*client_cmd))
                # The test harness starts this PHP client by Docker exec. That is
                # an owned local E2E action, not a native researcher/tool origin.
                for _ in range(40):
                    ready = docker("exec", client_name, "php", "-r",
                                   "exit(@file_get_contents('http://kanboard-effect-app:8000/robots.txt') === false ? 1 : 0);",
                                   check=False)
                    if ready.returncode == 0:
                        break
                    time.sleep(0.1)
                else:
                    raise RuntimeError("app was not reachable from client")
                if observed:
                    direct = json.loads(docker("exec", client_name, "php", "/input/client.php", "collector-reach").stdout)
                    require(direct == {"collector_reachable": False}, "researcher reached collector")
                    report["checks"]["collector_unreachable_from_researcher"] = True
                    docker("network", "connect", observer_net_id, client_id)
                    try:
                        joined = json.loads(docker("exec", client_id, "php", "/input/client.php",
                                                  "collector-reach").stdout)
                        require(joined == {"collector_reachable": True},
                                "reachable_collector_reported_unreachable")
                    finally:
                        docker("network", "disconnect", observer_net_id, client_id, check=False)
                    detached = json.loads(docker("exec", client_id, "php", "/input/client.php",
                                                 "collector-reach").stdout)
                    require(detached == {"collector_reachable": False},
                            "collector_network_remained_reachable")
                    report["checks"]["collector_reach_negative_detected"] = True
                scratch = json.loads(docker("exec", client_name, "php", "/input/client.php", "scratch").stdout)
                require(scratch == {"host_mounts_absent": True, "scratch_executed": True},
                        "researcher scratch crossed host-owned mounts")
                report["checks"]["scratch_cannot_edit_app"] = True
                app_info, client_info = inspect_container(app_name), inspect_container(client_name)
                require(app_info["Image"] == IMAGE_ID and client_info["Image"] == IMAGE_ID,
                        "runtime image changed after inspect")
                if observed:
                    require(inspect_container(collector_name)["Image"] == IMAGE_ID,
                            "collector image changed after inspect")
                client_ip = network_ip(client_info, research_net)
                require(observer_net not in client_info["NetworkSettings"]["Networks"],
                        "researcher attached collector network")
                require(all(mount["Destination"] == "/input" for mount in client_info["Mounts"]),
                        "researcher has unexpected mount")
                result = json.loads(docker("exec", "-i", client_name, "php", "/input/client.php", "positive",
                                           input_data=client_input).stdout)
                final = protected_state(s10, data, seed_input)
                rows = collector_rows(receipt_dir / "receipts.sqlite") if observed else []
                if observed:
                    log_result = docker("logs", collector_name, check=False)
                    collector_log = log_result.stdout + log_result.stderr
                    report["observed"]["collector_http_statuses"] = re.findall(
                        r'\b(204|403|422|500)\b', collector_log)
                    report["observed"]["collector_reject_types"] = re.findall(
                        r'NQ_CAPTURE_REJECT (invalid_keys|invalid_route|invalid_digest_or_address|invalid_number|invalid_role_or_error|invalid_state|storage|internal)', collector_log)
                    app_probe = docker("exec", app_name, "php", "-r",
                        "$c=stream_context_create(['http'=>['ignore_errors'=>true,'timeout'=>2]]);"
                        "@file_get_contents('http://kanboard-effect-collector:8765/receipt.php',false,$c);"
                        "echo isset($http_response_header[0]) ? $http_response_header[0] : 'no-response';",
                        check=False)
                    report["observed"]["app_to_collector_get_probe"] = app_probe.stdout.strip()
                    report["observed"]["capture_diagnostic"] = {
                        "client": result, "final": final, "rows": rows,
                        "client_ip": client_ip, "app_observer_ip": app_observer_ip,
                    }
                metadata = {"app_id": app_id, "client_id": client_id,
                            "client_ip": client_ip, "app_observer_ip": app_observer_ip,
                            "network_ids": {research_net: research_net_id}}
                if observed:
                    metadata["collector_id"] = collector_id
                    metadata["network_ids"][observer_net] = observer_net_id
                if observed:
                    positive_count = 11
                    require(verify_original(rows, result, baseline, final, seed_input, client_ip, app_observer_ip,
                                            positive_count), "original protected effect receipt failed")
                    report["checks"]["same_request_actor_and_effect"] = True
                    for mutation_label, index, key, value in (
                        ("denied_task", 2, "task_id", seed_input["T"] + 999),
                        ("invalid_route", 6, "route_project_id", seed_input["Q"]),
                        ("invalid_project", 6, "body_project_id", seed_input["S"]),
                        ("invalid_user", 6, "body_user_id", seed_input["users"]["A"]["id"]),
                        ("invalid_status", 6, "status", 500),
                        ("decisive_status", 7, "status", 500),
                    ):
                        changed_rows = copy.deepcopy(rows)
                        changed_rows[index]["payload"][key] = value
                        require(not verify_original(changed_rows, result, baseline, final, seed_input,
                                                    client_ip, app_observer_ip, positive_count),
                                "verifier_accepted_mutated_" + mutation_label)
                    report["checks"]["receipt_mutations_rejected"] = True
                    second_name = f"kb-ne-second-{nonce}-{label}"
                    second_id = register_owned("container", second_name, docker(
                        "run", "-d", "--name", second_name, "--log-driver=none",
                        "--label", f"io.lrh.native-effect={owner_nonce}",
                        "--pull=never", "--read-only", "--network", research_net,
                        "--tmpfs", "/tmp:rw,nosuid,size=32m", "--mount",
                        f"type=bind,source={input_dir},target=/input,readonly", "--entrypoint", "sh",
                        IMAGE_ID, "-c", "sleep 90"))
                    second_ip = network_ip(inspect_container(second_name), research_net)
                    require(second_ip != client_ip, "second client shared researcher IP")
                    second_result = json.loads(docker("exec", "-i", second_name, "php", "/input/client.php", "second",
                                                      input_data=client_input).stdout)
                    require(second_result["second_read"]["status"] == 200, "second client did not reach app")
                    second_rows = collector_rows(receipt_dir / "receipts.sqlite")
                    require(len(second_rows) == positive_count + 3 and
                            all(row["peer"] == app_observer_ip and
                                row["payload"]["remote_addr"] == second_ip for row in second_rows[positive_count:]) and
                            not verify_original(second_rows, result, baseline, final, seed_input,
                                                client_ip, app_observer_ip, positive_count),
                            "second client was silently credited")
                    report["checks"]["second_client_rejected"] = True
                    second_resource = next(item for item in owned_resources if item["id"] == second_id)
                    clean_owned_resource(second_resource, owner_nonce)
                    require(second_resource["absent"], "second_client_cleanup_failed")
                    batch_result = json.loads(docker("exec", client_name, "php", "/input/client.php", "batch").stdout)
                    batch_rows = collector_rows(receipt_dir / "receipts.sqlite")
                    require(len(batch_rows) == len(second_rows) + 1 and
                            batch_rows[-1]["payload"]["kind"] == "jsonrpc" and
                            batch_rows[-1]["payload"]["before"] == batch_rows[-1]["payload"]["after"] and
                            not verify_original(batch_rows, result, baseline, final, seed_input,
                                                client_ip, app_observer_ip, positive_count) and
                            batch_result["batch_status"] in (200, 401, 403),
                            "JSON-RPC batch was silently credited")
                    report["checks"]["batch_rejected"] = True
                    collector_resource = next(item for item in owned_resources if item["id"] == collector_id)
                    clean_owned_resource(collector_resource, owner_nonce)
                    require(collector_resource["absent"], "collector_cleanup_failed")
                    missing = json.loads(docker("exec", "-i", client_name, "php", "/input/client.php", "second",
                                                input_data=client_input).stdout)
                    missing_rows = collector_rows(receipt_dir / "receipts.sqlite")
                    require(missing["second_read"]["status"] == 200 and len(missing_rows) == len(batch_rows),
                            "missing collector changed target or fabricated receipt")
                    require(not verify_original(missing_rows, result, baseline, final, seed_input, client_ip, app_observer_ip,
                                                len(batch_rows) + 1), "missing app-side receipt was credited")
                    report["checks"]["missing_receipt_rejected"] = True
                    report["observed"]["positive_receipts"] = rows
                    report["observed"]["negative_receipt_count"] = len(batch_rows)
                require(source_tree_digest(work / "app") == source_hash,
                        "app source changed during run")
                return result, final, rows, metadata

            pristine_result, pristine_final, _, pristine_meta = phase("pristine", False)
            require(cleanup_owned(), "pristine_cleanup_failed")
            observed_result, observed_final, _, observed_meta = phase("observed", True)
            require(cleanup_owned(), "observed_cleanup_failed")
            require(pristine_final == observed_final, "instrumentation changed protected state")
            for key in ("baseline_read", "fresh_read"):
                require({k: pristine_result[key][k] for k in ("status", "marker_present")} ==
                        {k: observed_result[key][k] for k in ("status", "marker_present")},
                        "instrumentation changed web outcome")
            require(pristine_result["write_status"] == observed_result["write_status"],
                    "instrumentation changed A write status")
            report["checks"]["pristine_behavior_parity"] = True
            report["observed"]["pristine"] = {"client": pristine_result, "state": pristine_final,
                                                 "docker": pristine_meta}
            report["observed"]["instrumented"] = {"client": observed_result, "state": observed_final,
                                                     "docker": observed_meta}
            require(source_tree_digest(work / "app") == source_hash, "source changed after cleanup")
            report["checks"]["source_inventory_stable"] = True
            serialized = json.dumps(report)
            forbidden = [seed_input["marker"]] + [value[key] for value in seed_input["users"].values()
                                                   for key in ("username", "password")]
            require(all(value not in serialized for value in forbidden), "observer_report_contains_sensitive_input")
            report["checks"]["observer_report_redacted"] = True
        require(all(entry["absent"] for entry in report["cleanup"]), "owned Docker resource survived cleanup")
        report["checks"]["exact_resource_cleanup"] = True
        report["status"] = "pass"
        print("PASS: local Kanboard app request/actor/effect capture; native origin unqualified")
    except Exception as error:
        report["failure"] = error.code if isinstance(error, CheckFailed) else type(error).__name__
        print(f"FAIL: {report['failure']}", file=sys.stderr)
    finally:
        cleanup_owned()
        if not all(resource["absent"] for resource in owned_resources):
            report["status"] = "fail"
            report["failure"] = "owned_docker_resource_survived_cleanup"
        (output / "result.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
