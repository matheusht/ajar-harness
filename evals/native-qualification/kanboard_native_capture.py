#!/usr/bin/env python3
"""Host-owned Kanboard capture seam for distinct S10 and T01 native cases.

The two case profiles share collector topology, dispatch windows and cleanup.
Neither an app receipt nor a native trace alone proves original tool origin.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import stat
import subprocess
import time
import uuid


HERE = Path(__file__).resolve().parent
PROBE = HERE / "smoke/kanboard_effect_probe.php"
COLLECTOR = HERE / "smoke/kanboard_effect_collector.php"
BROKER = HERE / "smoke/kanboard_role_broker.php"
T01_BROKER = HERE / "smoke/t01_jsonrpc_broker.php"
T01_COLLECTOR = HERE / "smoke/t01_receipt_collector.php"
PROBE_SHA256 = "5484f9ac40a710ea5eb5492bc13b712211e5f1cbcde934e2548e946c8fa0379d"
COLLECTOR_SHA256 = "991d727e36b0c1fedc9898f4a773282ce7f062f8f00de4ae5dd05d2256b9e3b5"
BROKER_SHA256 = "2ee3d3806825f210071b73f53ade076e471f97237b81a0a66cc00632e6e97c8d"
SOURCE_MANIFEST_SHA256 = "056280086b353347075f0352b5826bd20ef7328854e7283e4c5cd71d7e57f839"
CONTROLLER_SHA256 = "6df47c20fe6b1963bd14a86bc3cbd554fbcea9f622a23f67af115a854811aad6"
CONTROLLER = Path("app/Controller/ProjectPermissionController.php")
T01_SOURCE_MANIFEST_SHA256 = "5d49c3f485f555f3118b0afb983997e29a5ddaad4b0ed6f9cf19d855c2e4f884"
T01_SOURCE_PINS = {
    "jsonrpc.php": "fe930f53e4a7c264249f3cb1629788ce4362112b2aef6226a42dfc0197aeff84",
    "app/Api/Middleware/AuthenticationMiddleware.php": "b58767b343bcbfaa1d9ae461cf39dc72e7f489ba3899dea2246541153bdd3c4f",
    "app/Api/Procedure/MeProcedure.php": "70b879a3e98bd92c7e28b52d401f74fd1b857d0cbc699ec57928a5323691d3d0",
    "app/Api/Procedure/SwimlaneProcedure.php": "0bdaf617b9b26f9ca4bc21766b08ae5989a858bfc4d991d8899f01b24332ac16",
    "app/Api/Authorization/ProjectAuthorization.php": "e05d0f980eaed023e5a8b118c888b67768a4384c8e58203b5131aac13c5b8591",
}
T01_BROKER_SHA256 = "b76cecc5a8820dccb604e1677cba09006b251bba0bbaec2d75fa0605d7208026"
T01_COLLECTOR_SHA256 = "21b96ab11307045001c50c1cc5a5043467fdb4ee381e782ee45d2b6989e42e2c"
TARGET_TO_RESEARCH = {"target": "researcher", "review-target-1": "reviewer-1",
                      "review-target-2": "reviewer-2"}
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
SESSION = re.compile(r"ses_[A-Za-z0-9]{1,64}\Z")
DOCKER_BINARY: Path | None = None


def _case(plan: dict) -> str:
    _need(not ("kanboard_capture" in plan and "t01_capture" in plan),
          "capture_modes_conflict")
    if "t01_capture" in plan:
        return "t01"
    _need("kanboard_capture" in plan, "capture_mode_missing")
    return "s10"


class CaptureHold(RuntimeError):
    """A fixed, safe reason for refusing attribution."""


def _need(ok: bool, code: str) -> None:
    if not ok:
        raise CaptureHold(code)


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _set_docker(plan: dict) -> None:
    global DOCKER_BINARY
    binary = Path(str(plan.get("docker_binary", "")))
    try:
        entry = binary.stat(follow_symlinks=False)
        good = (binary.is_absolute() and not binary.is_symlink() and
                binary.resolve(strict=True) == binary and stat.S_ISREG(entry.st_mode) and
                bool(entry.st_mode & 0o111) and not entry.st_mode & 0o022 and
                _sha(binary) == plan.get("docker_sha256"))
    except OSError:
        good = False
    _need(good, "capture_docker_binary_pin_mismatch")
    DOCKER_BINARY = binary


def _private_dir(path: Path) -> Path:
    path = Path(path)
    try:
        entry = path.stat(follow_symlinks=False)
        good = (path.is_absolute() and not path.is_symlink() and
                path.resolve(strict=True) == path and stat.S_ISDIR(entry.st_mode) and
                entry.st_uid == os.getuid() and not entry.st_mode & 0o077)
    except OSError:
        good = False
    _need(good, "host_control_directory_invalid")
    return path


def _regular(path: Path, root: Path) -> Path:
    try:
        entry = path.stat(follow_symlinks=False)
        good = (path.is_relative_to(root) and not path.is_symlink() and
                path.resolve(strict=True) == path and stat.S_ISREG(entry.st_mode) and
                entry.st_uid == os.getuid() and not entry.st_mode & 0o022)
    except OSError:
        good = False
    _need(good, "host_control_file_invalid")
    return path


def _json(path: Path, root: Path) -> dict:
    _regular(path, root)
    _need(path.stat().st_size <= 1024 * 1024, "host_control_file_oversize")
    try:
        value = json.loads(path.read_bytes())
    except (UnicodeError, ValueError) as error:
        raise CaptureHold("host_control_json_invalid") from error
    _need(isinstance(value, dict), "host_control_json_invalid")
    return value


def _write_once(path: Path, value: dict) -> None:
    payload = (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _write_replace(path: Path, value: dict) -> None:
    temporary = path.with_name("." + path.name + "-" + uuid.uuid4().hex)
    try:
        _write_once(temporary, value)
        os.replace(temporary, path)
        fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        temporary.unlink(missing_ok=True)


def _source(root: Path, plan: dict, target: str) -> None:
    case = _case(plan)
    manifest = T01_SOURCE_MANIFEST_SHA256 if case == "t01" else SOURCE_MANIFEST_SHA256
    pins = T01_SOURCE_PINS if case == "t01" else {str(CONTROLLER): CONTROLLER_SHA256}
    _need(plan.get("source_manifest_sha256") == manifest and
          isinstance(plan.get("source_sha256"), dict), "kanboard_source_pin_mismatch")
    for name in ("original", target):
        base = root / name
        _need(base.is_dir() and not base.is_symlink(), "kanboard_source_copy_missing")
        observed = {}
        for path in sorted(base.rglob("*")):
            relative = path.relative_to(base).as_posix()
            if relative == "data" or relative.startswith("data/"):
                continue
            _need(not path.is_symlink(), "kanboard_source_linked")
            if path.is_file():
                observed[relative] = _sha(path)
        expected = {key: value for key, value in plan["source_sha256"].items()
                    if key != "data" and not key.startswith("data/")}
        _need(observed == expected and
              all(_sha(base / relative) == digest for relative, digest in pins.items()),
              "kanboard_source_copy_changed")


def _approved_capture(plan: dict) -> None:
    if _case(plan) == "t01":
        expected = {"adapter_sha256": _sha(Path(__file__)),
                    "broker_sha256": T01_BROKER_SHA256,
                    "collector_sha256": T01_COLLECTOR_SHA256,
                    "source_manifest_sha256": T01_SOURCE_MANIFEST_SHA256,
                    "middleware_sha256": T01_SOURCE_PINS["app/Api/Middleware/AuthenticationMiddleware.php"]}
        _need(_sha(T01_BROKER) == T01_BROKER_SHA256 and
              _sha(T01_COLLECTOR) == T01_COLLECTOR_SHA256 and
              plan.get("t01_capture") == expected,
              "t01_capture_code_not_bound_to_plan")
        return
    expected = {"adapter_sha256": _sha(Path(__file__)), "probe_sha256": PROBE_SHA256,
                "collector_sha256": COLLECTOR_SHA256, "broker_sha256": BROKER_SHA256,
                "source_manifest_sha256": SOURCE_MANIFEST_SHA256,
                "controller_sha256": CONTROLLER_SHA256}
    _need(_sha(PROBE) == PROBE_SHA256 and _sha(COLLECTOR) == COLLECTOR_SHA256 and
          _sha(BROKER) == BROKER_SHA256 and
          plan.get("kanboard_capture") == expected,
          "capture_code_not_bound_to_plan")


def stage(run_root: Path, target: str, *, s: int | None = None, q: int | None = None,
          t: int | None = None, b: int | None = None) -> dict:
    """Prepare observer-only files and return exact target/collector Docker inputs.

    The native owner must create the returned network and containers, retain
    their IDs in resources.json, and call attest before any relevant dispatch.
    """
    root = _private_dir(run_root)
    plan = _json(root / "plan.json", root)
    case = _case(plan)
    _need(target in TARGET_TO_RESEARCH, "capture_target_invalid")
    if case == "s10":
        _need(all(type(x) is int and x > 0 for x in (s, q, t, b)) and s != q,
              "capture_case_ids_invalid")
    else:
        _need(all(x is None for x in (s, q, t, b)), "t01_seed_ids_forbidden")
    _approved_capture(plan)
    _source(root, plan, target)
    controls = _private_dir(root / "controls")
    observer = controls / "observer"
    if not observer.exists():
        observer.mkdir(mode=0o700)
    _private_dir(observer)
    slot = observer / target
    slot.mkdir(mode=0o700, exist_ok=False)
    try:
        receipts = slot / "receipts"
        receipts.mkdir(mode=0o700)
        files = ((T01_COLLECTOR, "receipt.php"), (T01_BROKER, "broker.php")) if case == "t01" else (
            (PROBE, "effect.php"), (COLLECTOR, "receipt.php"), (BROKER, "broker.php"))
        for original, name in files:
            destination = slot / name
            shutil.copyfile(original, destination)
            destination.chmod(0o600)
        database = receipts / "receipts.sqlite"
        with sqlite3.connect(database) as db:
            db.execute("CREATE TABLE receipts (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                       "peer TEXT NOT NULL, payload TEXT NOT NULL)")
        database.chmod(0o600)
        record = {"kind": "kanboard-t01-capture-stage-v1" if case == "t01" else
                  "kanboard-native-capture-stage-v1", "target": target,
                  "research_role": TARGET_TO_RESEARCH[target],
                  "source_manifest_sha256": T01_SOURCE_MANIFEST_SHA256 if case == "t01" else
                  SOURCE_MANIFEST_SHA256, "image_id": plan.get("target_image_id"),
                  "plan_sha256": _sha(root / "plan.json"),
                  "collector_sha256": _sha(slot / "receipt.php"),
                  "broker_sha256": _sha(slot / "broker.php")}
        if case == "s10":
            record.update({"ids": {"s": s, "q": q, "t": t, "b": b},
                           "controller_sha256": CONTROLLER_SHA256,
                           "probe_sha256": _sha(slot / "effect.php")})
        _write_once(slot / "stage.json", record)
    except Exception:
        shutil.rmtree(slot)
        raise
    if case == "t01":
        return {"status": "staged_original_session_origin_held", "target": target,
                "observer_dir": str(slot), "network_role": "capture-net-" + target,
                "collector_role": "capture-" + target,
                "target_mount": {"source": str(slot / "broker.php"),
                                 "destination": "/observer/broker.php", "readonly": True},
                "collector_mounts": [
                    {"source": str(slot / "receipt.php"), "destination": "/collector/receipt.php", "readonly": True},
                    {"source": str(slot / "receipts"), "destination": "/receipts", "readonly": False}],
                "collector_db": str(database),
                "missing": ["native_original_session_origin_unqualified"]}
    return {"status": "staged_origin_and_credentials_held", "target": target,
            "observer_dir": str(slot),
            "network_role": "capture-net-" + target,
            "collector_role": "capture-" + target,
            "target_mount": {"source": str(slot / "effect.php"), "destination": "/observer/effect.php",
                             "readonly": True},
            "target_environment": {"NATIVE_EFFECT_COLLECTOR": "http://kanboard-effect-collector:8765/receipt.php",
                                   "NATIVE_EFFECT_SOURCE_DIR": "/target", "NATIVE_EFFECT_S": str(s),
                                   "NATIVE_EFFECT_Q": str(q), "NATIVE_EFFECT_T": str(t),
                                   "NATIVE_EFFECT_B": str(b), "DB_FILENAME": "/target/data/db.sqlite"},
            "target_php_option": "auto_prepend_file=/observer/effect.php",
            "collector_mounts": [
                {"source": str(slot / "receipt.php"), "destination": "/collector/receipt.php", "readonly": True},
                {"source": str(slot / "receipts"), "destination": "/receipts", "readonly": False}],
            "collector_db": str(database),
            "missing": ["native_credential_route_unavailable", "native_origin_unproven"]}


def _inspect(kind: str, identifier: str) -> dict:
    _need(bool(HEX64.fullmatch(identifier)), "docker_resource_id_invalid")
    _need(DOCKER_BINARY is not None, "capture_docker_binary_unset")
    try:
        result = subprocess.run([str(DOCKER_BINARY), kind, "inspect", identifier], check=False,
                                stdin=subprocess.DEVNULL, capture_output=True, timeout=20,
                                env={key: value for key, value in os.environ.items()
                                     if key in ("HOME", "PATH", "DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_CONFIG")})
        value = json.loads(result.stdout) if result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired, UnicodeError, ValueError) as error:
        raise CaptureHold("docker_inspect_unavailable") from error
    _need(isinstance(value, list) and len(value) == 1 and isinstance(value[0], dict),
          "docker_inspect_unavailable")
    return value[0]


def _docker(*arguments: str) -> str:
    _need(DOCKER_BINARY is not None, "capture_docker_binary_unset")
    try:
        result = subprocess.run([str(DOCKER_BINARY), *arguments], check=False, stdin=subprocess.DEVNULL,
                                capture_output=True, timeout=30,
                                env={key: value for key, value in os.environ.items()
                                     if key in ("HOME", "PATH", "DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_CONFIG")})
    except (OSError, subprocess.TimeoutExpired) as error:
        raise CaptureHold("capture_docker_operation_unknown") from error
    _need(result.returncode == 0 and len(result.stdout) < 65536,
          "capture_docker_operation_unknown")
    return result.stdout.decode("utf-8", errors="strict").strip()


def activate(run_root: Path, target: str) -> dict:
    """Start a separately owned collector before the target producer starts.

    Call after target `_create` and before the eight-producer NativeRun seal.
    The observer ledger is predeclared before Docker; a failed operation leaves
    an explicit unknown state for exact-ID recovery, never a silent retry.
    """
    root = _private_dir(run_root)
    _need(target in TARGET_TO_RESEARCH, "capture_target_invalid")
    slot = _private_dir(root / "controls/observer" / target)
    stage_record = _json(slot / "stage.json", root)
    plan = _json(root / "plan.json", root)
    case = _case(plan)
    _approved_capture(plan)
    _set_docker(plan)
    resources = _json(root / "controls/resources.json", root)
    rows = resources.get("resources")
    _need(isinstance(rows, list) and stage_record.get("target") == target,
          "capture_resources_invalid")
    apps = [row for row in rows if isinstance(row, dict) and row.get("role") == target and
            row.get("kind") == "container"]
    _need(len(apps) == 1 and isinstance(apps[0].get("id"), str) and
          HEX64.fullmatch(apps[0]["id"]), "capture_target_not_created")
    app_id = apps[0]["id"]
    app = _inspect("container", app_id)
    required_mounts = ({(str(slot / "broker.php"), "/observer/broker.php", False)}
                       if case == "t01" else
                       {(str(slot / "effect.php"), "/observer/effect.php", False),
                        (str(slot / "broker.php"), "/observer/broker.php", False),
                        (str(slot / "actors.json"), "/observer/actors.json", False)})
    _need(app.get("Id") == app_id and app.get("State", {}).get("Status") == "created" and
          app.get("Config", {}).get("Labels", {}).get("io.lrh.native-research") == resources.get("nonce") and
          app.get("Image") == plan.get("target_image_id") and
          required_mounts <= _mounts(app),
          "capture_target_create_mismatch")
    nonce = resources["nonce"]
    _need(isinstance(nonce, str) and re.fullmatch(r"[0-9a-f]{24,64}", nonce),
          "capture_owner_nonce_invalid")
    prefix = "lrh-cap-" + nonce[:12] + "-" + target
    ledger_path = slot / "resources.json"
    ledger = {"kind": "kanboard-capture-resources-v1", "status": "declared",
              "nonce": nonce, "target": target, "app_id": app_id,
              "network_name": prefix + "-net", "network_id": None,
              "collector_name": prefix + "-collector", "collector_id": None}
    _write_once(ledger_path, ledger)
    try:
        network_id = _docker("network", "create", "--internal", "--label",
                             "io.lrh.kanboard-capture=" + nonce, ledger["network_name"])
        _need(bool(HEX64.fullmatch(network_id)), "capture_network_create_id_invalid")
        ledger["network_id"] = network_id
        _write_replace(ledger_path, ledger)
        network = _inspect("network", network_id)
        _need(network.get("Id") == network_id and network.get("Name") == ledger["network_name"] and
              network.get("Internal") is True and
              network.get("Labels", {}).get("io.lrh.kanboard-capture") == nonce,
              "capture_network_create_mismatch")
        config = (network.get("IPAM") or {}).get("Config") or []
        _need(len(config) == 1 and isinstance(config[0].get("Subnet"), str),
              "capture_network_subnet_unavailable")
        subnet = ipaddress.ip_network(config[0]["Subnet"], strict=True)
        _need(isinstance(subnet, ipaddress.IPv4Network) and subnet.num_addresses >= 32,
              "capture_network_subnet_invalid")
        app_ip = str(subnet.network_address + 10)
        _need(app_ip != config[0].get("Gateway"), "capture_network_app_ip_conflict")
        ledger["app_ip"] = app_ip
        _write_replace(ledger_path, ledger)
        _docker("network", "connect", "--ip", app_ip, network_id, app_id)
        app = _inspect("container", app_id)
        _need(ledger["network_name"] in app.get("NetworkSettings", {}).get("Networks", {}),
              "capture_app_network_attach_missing")
        attachment = app["NetworkSettings"]["Networks"][ledger["network_name"]]
        _need((attachment.get("IPAMConfig") or {}).get("IPv4Address") == app_ip or
              attachment.get("IPAddress") == app_ip, "capture_app_ip_not_reserved")
        uid = f"{os.getuid()}:{os.getgid()}"
        collector_id = _docker(
            "container", "create", "--name", ledger["collector_name"], "--pull", "never",
            "--network", network_id, "--network-alias", "kanboard-effect-collector",
            "--read-only", "--restart", "no", "--log-driver", "none", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges=true", "--user", uid,
            "--memory", "256m", "--cpus", "0.5", "--pids-limit", "32",
            "--tmpfs", "/tmp:rw,nosuid,nodev,size=32m",
            "--label", "io.lrh.kanboard-capture=" + nonce,
            "--mount", f"type=bind,src={slot / 'receipt.php'},dst=/collector/receipt.php,readonly",
            "--mount", f"type=bind,src={slot / 'receipts'},dst=/receipts",
            "--env", "EXPECTED_APP_IP=" + app_ip, "--workdir", "/collector",
            "--entrypoint", "php", plan["target_image_id"],
            "-d", "display_errors=0", "-S", "0.0.0.0:8765", "-t", "/collector")
        _need(bool(HEX64.fullmatch(collector_id)), "capture_collector_create_id_invalid")
        ledger["collector_id"] = collector_id
        _write_replace(ledger_path, ledger)
        collector = _inspect("container", collector_id)
        _need(collector.get("Id") == collector_id and
              collector.get("State", {}).get("Status") == "created" and
              collector.get("Name") == "/" + ledger["collector_name"] and
              collector.get("Image") == plan["target_image_id"] and
              collector.get("Config", {}).get("Labels", {}).get("io.lrh.kanboard-capture") == nonce,
              "capture_collector_create_mismatch")
        _docker("container", "start", collector_id)
        _need(_inspect("container", collector_id).get("State", {}).get("Status") == "running",
              "capture_collector_start_unknown")
        ledger["status"] = "active"
        _write_replace(ledger_path, ledger)
        return {"status": "collector_active_original_session_origin_held" if case == "t01" else
                "collector_active_origin_and_credentials_held", "target": target,
                "collector_id": collector_id, "network_id": network_id}
    except Exception:
        ledger["status"] = "activation_unknown"
        _write_replace(ledger_path, ledger)
        raise


def _mounts(info: dict) -> set[tuple[str, str, bool]]:
    return {(row.get("Source"), row.get("Destination"), row.get("RW"))
            for row in info.get("Mounts", [])}


def _t01_setup_readback(root: Path, slot: Path, app_ip: str) -> dict:
    database = _regular(slot / "receipts/receipts.sqlite", root)
    setup = None
    for _ in range(100):
        try:
            with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as db:
                row = db.execute("SELECT id,peer,payload FROM receipts ORDER BY id LIMIT 1").fetchone()
            if row is not None:
                setup = (row[0], row[1], json.loads(row[2]))
                break
        except (sqlite3.DatabaseError, UnicodeError, ValueError) as error:
            raise CaptureHold("t01_setup_receipt_invalid") from error
        time.sleep(.1)
    _need(setup is not None and setup[0] == 1 and setup[1] == app_ip and
          isinstance(setup[2], dict),
          "t01_setup_receipt_unavailable")
    receipt = setup[2]
    _need(receipt.get("kind") == "t01-kanboard-setup-v1" and
          receipt.get("source_manifest_sha256") == T01_SOURCE_MANIFEST_SHA256 and
          receipt.get("admin_default_revoked") is True and
          receipt.get("project_count") == receipt.get("swimlane_count") == 0 and
          isinstance(receipt.get("actor_ids"), dict) and
          set(receipt["actor_ids"]) == {"A", "B"} and
          all(type(value) is int and value > 0 for value in receipt["actor_ids"].values()) and
          receipt["actor_ids"]["A"] != receipt["actor_ids"]["B"] and
          isinstance(receipt.get("db_sha256"), str) and
          HEX64.fullmatch(receipt["db_sha256"]), "t01_setup_receipt_invalid")
    payload_sha = hashlib.sha256(row[2].encode()).hexdigest()
    readback_path = slot / "setup-readback.json"
    if not readback_path.exists():
        app_db = _regular(root / slot.name / "data/db.sqlite", root)
        _need(_sha(app_db) == receipt["db_sha256"], "t01_setup_db_changed_before_start")
        with sqlite3.connect(app_db.as_uri() + "?mode=ro", uri=True) as db:
            users = db.execute("SELECT id,username,role,is_active FROM users WHERE username IN ('alice','bob') ORDER BY username").fetchall()
            projects = db.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
            lanes = db.execute("SELECT COUNT(*) FROM swimlanes").fetchone()[0]
        _need(users == [(receipt["actor_ids"]["A"], "alice", "app-user", 1),
                        (receipt["actor_ids"]["B"], "bob", "app-user", 1)] and
              projects == lanes == 0, "t01_setup_state_mismatch")
        _write_once(readback_path, {"kind": "t01-setup-readback-v1", "receipt_sha256": payload_sha,
                                    "db_sha256": receipt["db_sha256"]})
    _need(_json(readback_path, root) ==
          {"kind": "t01-setup-readback-v1", "receipt_sha256": payload_sha,
           "db_sha256": receipt["db_sha256"]}, "t01_setup_readback_changed")
    return {"receipt_sha256": payload_sha, "actor_ids": receipt["actor_ids"]}


def attest(run_root: Path, target: str, native_role: str | None = None) -> dict:
    """Host-inspect actual Docker IDs, mounts, networks, and clean source."""
    root = _private_dir(run_root)
    _need(target in TARGET_TO_RESEARCH, "capture_target_invalid")
    plan = _json(root / "plan.json", root)
    case = _case(plan)
    _approved_capture(plan)
    _set_docker(plan)
    slot = _private_dir(root / "controls/observer" / target)
    stage_record = _json(slot / "stage.json", root)
    _need(stage_record.get("target") == target and stage_record.get("plan_sha256") == _sha(root / "plan.json")
          and stage_record.get("kind") == ("kanboard-t01-capture-stage-v1" if case == "t01" else
                                            "kanboard-native-capture-stage-v1")
          and (case == "t01" or stage_record.get("probe_sha256") == _sha(slot / "effect.php"))
          and stage_record.get("collector_sha256") == _sha(slot / "receipt.php")
          and stage_record.get("broker_sha256") == _sha(slot / "broker.php"),
          "capture_stage_changed")
    if case == "s10":
        actor_route = _json(slot / "actor-route.json", root)
        approval = _json(root / "controls/approval.json", root)
        _need(actor_route.get("kind") == "kanboard-native-actor-route-v1" and
              actor_route.get("target") == target and
              actor_route.get("map_sha256") == _sha(slot / "actors.json") and
              actor_route.get("baseline_db_sha256") ==
              (approval.get("capture_target_db_sha256") or {}).get(target),
              "capture_actor_route_changed")
    _source(root, plan, target)
    resources = _json(root / "controls/resources.json", root)
    rows = resources.get("resources")
    _need(isinstance(rows, list) and isinstance(resources.get("nonce"), str),
          "capture_resources_invalid")
    producers = [row for row in rows if isinstance(row, dict) and row.get("kind") == "container"]
    by_role = {row.get("role"): row for row in producers}
    _need(len(by_role) == len(producers), "capture_resource_roles_ambiguous")
    # Collector/network have their own host-owner ledger. They are not added to
    # NativeRun's fixed eight-producer manifest or to a producer writable mount.
    observer_resources = _json(slot / "resources.json", root)
    _need(observer_resources.get("kind") == "kanboard-capture-resources-v1" and
          observer_resources.get("nonce") == resources["nonce"] and
          observer_resources.get("status") == "active",
          "capture_observer_ownership_invalid")
    app_role = target
    producer = native_role or TARGET_TO_RESEARCH[target]
    _need(producer in ({"researcher", "resume"} if target == "target" else
                       {TARGET_TO_RESEARCH[target]}), "capture_native_role_invalid")
    _need(all(role in by_role for role in (app_role, producer)),
          "capture_resources_missing")
    ids = {role: by_role[role].get("id") for role in (app_role, producer)}
    ids["collector"] = observer_resources.get("collector_id")
    ids["network"] = observer_resources.get("network_id")
    _need(all(isinstance(value, str) and HEX64.fullmatch(value) for value in ids.values()),
          "capture_resource_id_invalid")
    app = _inspect("container", ids[app_role])
    agent = _inspect("container", ids[producer])
    collector = _inspect("container", ids["collector"])
    network = _inspect("network", ids["network"])
    _need(all(info.get("Id") == ids[role] for info, role in
              ((app, app_role), (agent, producer), (collector, "collector"), (network, "network"))),
          "capture_resource_identity_changed")
    label = "io.lrh.native-research"
    nonce = resources["nonce"]
    _need(all(info.get("Config", {}).get("Labels", {}).get(label) == nonce
              for info in (app, agent)) and
          collector.get("Config", {}).get("Labels", {}).get("io.lrh.kanboard-capture") == nonce and
          network.get("Labels", {}).get("io.lrh.kanboard-capture") == nonce,
          "capture_resource_owner_changed")
    _need(app.get("Image") == collector.get("Image") == plan.get("target_image_id") and
          agent.get("Image") == plan.get("image_id"), "capture_image_changed")
    _need(app.get("State", {}).get("Status") == "running" and
          collector.get("State", {}).get("Status") == "running",
          "capture_app_or_collector_not_running")
    app_networks = app.get("NetworkSettings", {}).get("Networks", {})
    agent_networks = agent.get("NetworkSettings", {}).get("Networks", {})
    collector_networks = collector.get("NetworkSettings", {}).get("Networks", {})
    observer_name = network.get("Name")
    _need(isinstance(observer_name, str) and observer_name in app_networks and
          set(collector_networks) == {observer_name} and observer_name not in agent_networks and
          network.get("Internal") is True and
          set((network.get("Containers") or {}).keys()) == {ids[app_role], ids["collector"]},
          "capture_network_isolation_invalid")
    shared = set(app_networks) & set(agent_networks)
    _need(len(shared) == 1 and observer_name not in shared,
          "capture_native_target_network_mismatch")
    client_network = next(iter(shared))
    client_ip = agent_networks[client_network].get("IPAddress")
    _need(isinstance(client_ip, str) and str(ipaddress.ip_address(client_ip)) == client_ip,
          "capture_native_client_ip_invalid")
    app_ip = app_networks[observer_name].get("IPAddress")
    _need(isinstance(app_ip, str) and str(ipaddress.ip_address(app_ip)) == app_ip,
          "capture_app_ip_invalid")
    _need(app_ip == observer_resources.get("app_ip"), "capture_app_ip_changed")
    source_mount = (str(root / target), "/target", True)
    broker_mount = (str(slot / "broker.php"), "/observer/broker.php", False)
    expected_app_mounts = ({source_mount, broker_mount} if case == "t01" else
                           {source_mount, (str(slot / "effect.php"), "/observer/effect.php", False),
                            broker_mount, (str(slot / "actors.json"), "/observer/actors.json", False)})
    _need(_mounts(app) == expected_app_mounts and
          _mounts(collector) == {(str(slot / "receipt.php"), "/collector/receipt.php", False),
                                 (str(slot / "receipts"), "/receipts", True)},
          "capture_mounts_invalid")
    observer_path = str(root / "controls/observer")
    for row in rows:
        if row.get("kind") != "container" or row.get("role") == app_role:
            continue
        info = _inspect("container", row.get("id"))
        _need(observer_name not in info.get("NetworkSettings", {}).get("Networks", {}),
              "capture_producer_observer_access")
        for mount in info.get("Mounts", []):
            source = str(mount.get("Source", ""))
            if source.startswith(observer_path + os.sep):
                other = row.get("role")
                _need(case == "s10" and other in TARGET_TO_RESEARCH and
                      source == str(root / "controls/observer" / other / "effect.php") and
                      mount.get("Destination") == "/observer/effect.php" and
                      mount.get("RW") is False,
                      "capture_producer_observer_access")
    env = dict(item.split("=", 1) for item in app.get("Config", {}).get("Env", []) if "=" in item)
    expected = ({"DB_FILENAME": "/target/data/db.sqlite"} if case == "t01" else
                {"NATIVE_EFFECT_COLLECTOR": "http://kanboard-effect-collector:8765/receipt.php",
                 "NATIVE_EFFECT_SOURCE_DIR": "/target", "NATIVE_EFFECT_S": str(stage_record["ids"]["s"]),
                 "NATIVE_EFFECT_Q": str(stage_record["ids"]["q"]),
                 "NATIVE_EFFECT_T": str(stage_record["ids"]["t"]),
                 "NATIVE_EFFECT_B": str(stage_record["ids"]["b"]),
                 "DB_FILENAME": "/target/data/db.sqlite"})
    command = (app.get("Config", {}).get("Entrypoint") or []) + (app.get("Config", {}).get("Cmd") or [])
    expected_command = ["php", "/observer/broker.php", str(plan["target_port"]), "/target",
                        "http://kanboard-effect-collector:8765/receipt.php"]
    _need(all(env.get(key) == value for key, value in expected.items()) and
          (command == expected_command if case == "t01" else
           "auto_prepend_file=/observer/effect.php" in command) and
          dict(item.split("=", 1) for item in collector.get("Config", {}).get("Env", [])
               if "=" in item).get("EXPECTED_APP_IP") == app_ip,
          "capture_hook_or_collector_not_loaded")
    setup = _t01_setup_readback(root, slot, app_ip) if case == "t01" else None
    _need(setup is None or setup["receipt_sha256"], "t01_setup_readback_invalid")
    return {"status": "topology_attested_original_session_origin_held" if case == "t01" else
            "topology_attested_origin_and_credentials_held", "target": target,
            "target_id": ids[app_role], "researcher_id": ids[producer],
            "collector_id": ids["collector"], "observer_network_id": ids["network"],
            "app_observer_ip": app_ip, "native_client_ip": client_ip,
            "native_target_network": client_network,
            "collector_db": str(slot / "receipts/receipts.sqlite"),
            "source_manifest_sha256": T01_SOURCE_MANIFEST_SHA256 if case == "t01" else
            SOURCE_MANIFEST_SHA256,
            "setup_receipt_sha256": setup["receipt_sha256"] if setup else None,
            "missing": ["native_original_session_origin_unqualified"] if case == "t01" else
            ["native_credential_route_unavailable", "native_origin_unproven"]}


def bind_dispatch(run_root: Path, target: str, dispatch_id: str) -> dict:
    """Seal a native turn to an attested app window, without claiming its origin."""
    root = _private_dir(run_root)
    _need(bool(re.fullmatch(r"[0-9a-f]{32}", dispatch_id)), "capture_dispatch_id_invalid")
    dispatch_path = root / "controls/dispatch" / (dispatch_id + ".json")
    dispatch = _json(dispatch_path, root)
    _need(dispatch.get("status") == "unknown_effect" and
          dispatch.get("role") in ({"researcher", "resume"} if target == "target" else
                                   {TARGET_TO_RESEARCH[target]}) and
          isinstance(dispatch.get("session_id"), str) and SESSION.fullmatch(dispatch["session_id"]),
          "capture_dispatch_not_open")
    topology = attest(root, target, dispatch["role"])
    case = _case(_json(root / "plan.json", root))
    database = _regular(Path(topology["collector_db"]), root)
    try:
        with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as db:
            count, maximum = db.execute("SELECT COUNT(*),COALESCE(MAX(id),0) FROM receipts").fetchone()
            _need(type(count) is int and 0 <= count <= 5000 and type(maximum) is int,
                  "capture_collector_state_invalid")
            rows = db.execute("SELECT id,peer,payload FROM receipts ORDER BY id").fetchall()
    except sqlite3.DatabaseError as error:
        raise CaptureHold("capture_collector_unavailable") from error
    window = {"kind": "kanboard-t01-window-v1" if case == "t01" else
              "kanboard-native-window-v1", "dispatch_id": dispatch_id,
              "dispatch_sha256": _sha(dispatch_path), "session_id": dispatch["session_id"],
              "role": dispatch["role"], "target": target, "topology": topology,
              "collector_count_before": count, "collector_max_id_before": maximum,
              "collector_prefix_sha256": hashlib.sha256(
                  json.dumps(rows, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest(),
              "credential_route": "brokered_identity_control" if case == "t01" else
              "unavailable", "native_origin": "unproven"}
    _write_once(root / "controls/observer" / target / ("window-" + dispatch_id + ".json"), window)
    return {"status": "held", "reason": "native_original_session_origin_unqualified" if case == "t01" else
            "native_credential_route_unavailable",
            "dispatch_id": dispatch_id, "target": target, "native_origin": "unproven",
            "window": str(root / "controls/observer" / target / ("window-" + dispatch_id + ".json"))}


def close_dispatch(run_root: Path, target: str, dispatch_id: str,
                   response_ids: list[str]) -> dict:
    """Close a T01 receipt window; correlation is evidence, never an origin pass."""
    root = _private_dir(run_root)
    _need(_case(_json(root / "plan.json", root)) == "t01" and
          bool(re.fullmatch(r"[0-9a-f]{32}", dispatch_id)) and
          isinstance(response_ids, list) and len(response_ids) <= 5000 and
          all(isinstance(item, str) and re.fullmatch(r"[0-9a-f]{32}", item)
              for item in response_ids), "t01_close_input_invalid")
    slot = _private_dir(root / "controls/observer" / target)
    window = _json(slot / ("window-" + dispatch_id + ".json"), root)
    _need(window.get("kind") == "kanboard-t01-window-v1" and
          window.get("dispatch_id") == dispatch_id and
          window.get("native_origin") == "unproven", "t01_window_invalid")
    topology = attest(root, target, window["role"])
    _need(topology == window.get("topology"), "t01_topology_changed")
    db_path = _regular(Path(topology["collector_db"]), root)
    try:
        with sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True) as db:
            prefix = db.execute("SELECT id,peer,payload FROM receipts WHERE id<=? ORDER BY id",
                                (window["collector_max_id_before"],)).fetchall()
            rows = db.execute("SELECT id,peer,payload FROM receipts WHERE id>? ORDER BY id",
                              (window["collector_max_id_before"],)).fetchall()
    except sqlite3.DatabaseError as error:
        raise CaptureHold("t01_collector_unavailable") from error
    _need(hashlib.sha256(json.dumps(prefix, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()
          == window["collector_prefix_sha256"] and len(rows) <= 5000,
          "t01_collector_prefix_changed")
    receipts = []
    for identifier, peer, payload in rows:
        try:
            record = json.loads(payload)
        except (UnicodeError, ValueError) as error:
            raise CaptureHold("t01_receipt_invalid") from error
        _need(peer == topology["app_observer_ip"] and
              isinstance(record, dict) and
              record.get("kind") == "t01-kanboard-jsonrpc-v1" and
              record.get("peer_ip") == topology["native_client_ip"] and
              isinstance(record.get("request_id"), str) and
              re.fullmatch(r"[0-9a-f]{32}", record["request_id"]),
              "t01_receipt_origin_invalid")
        receipts.append({"row_id": identifier, "request_id": record["request_id"],
                         "actor": record.get("actor"), "method": record.get("method"),
                         "result_class": record.get("result_class"),
                         "result_matches_db": record.get("result_matches_db")})
    _need(len({item["request_id"] for item in receipts}) == len(receipts),
          "t01_receipt_id_replayed")
    joined = sorted(set(response_ids) & {item["request_id"] for item in receipts})
    result = {"kind": "kanboard-t01-window-closed-v1", "dispatch_id": dispatch_id,
              "window_sha256": _sha(slot / ("window-" + dispatch_id + ".json")),
              "collector_count_after": len(prefix) + len(rows),
              "receipt_rows": receipts, "native_response_ids": sorted(set(response_ids)),
              "joined_request_ids": joined, "native_origin": "unproven",
              "status": "held", "reason": "native_original_session_origin_unqualified" if joined else
              "native_response_receipt_join_unavailable"}
    _write_once(slot / ("closed-" + dispatch_id + ".json"), result)
    return result


def _producer_binding(info: dict) -> str:
    """Recheck the exact NativeRun manifest binding on a startup close."""
    try:
        value = {key: info[key] for key in ("Id", "Image", "Config", "Mounts")}
        value["Mounts"] = sorted(info["Mounts"], key=lambda mount: mount["Destination"])
        value["networks"] = sorted(info["NetworkSettings"]["Networks"])
        value["host"] = {key: info["HostConfig"][key] for key in
                         ("ReadonlyRootfs", "Privileged", "RestartPolicy", "CapDrop", "SecurityOpt")}
        return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    except (KeyError, TypeError, ValueError) as error:
        raise CaptureHold("capture_startup_manifest_mismatch") from error


def _stop_proof(root: Path, ledger: dict, resources: dict, stop_kind: str,
                *, inspect_producers: bool) -> None:
    rows = resources.get("resources")
    _need(isinstance(rows, list), "capture_resources_invalid")
    producers = [row for row in rows if isinstance(row, dict) and row.get("kind") == "container"]
    ids = [row.get("id") for row in producers]
    _need(len(ids) == 8 and all(isinstance(identifier, str) and HEX64.fullmatch(identifier)
                                for identifier in ids) and ledger["app_id"] in ids,
          "capture_resources_invalid")
    state = root / "controls/native-state"
    if stop_kind == "REVOKED":
        proof = _json(state / "REVOKED", root)
        _need(proof.get("producers_verified_stopped") is True and proof.get("ids") == ids,
              "capture_native_stop_unverified")
        return
    _need(stop_kind == "STARTUP_CLOSED" and not any((state / name).exists()
          for name in ("RUN.json", "REVOKED", "UNSAFE")) and (state / "STOPPING").exists(),
          "capture_native_stop_unverified")
    stopping = _json(state / "STOPPING", root)
    proof = _json(state / "STARTUP_CLOSED", root)
    _need(isinstance(stopping.get("reason"), str) and
          proof.get("producers_verified_stopped") is True,
          "capture_native_stop_unverified")
    manifest = _json(root / "controls/producer-manifest.json", root)
    items = manifest.get("producers")
    _need(manifest.get("version") == 1 and manifest.get("nonce") == resources.get("nonce") and
          isinstance(items, list) and len(items) == 8 and
          all(isinstance(item, dict) for item in items) and
          [item.get("id") for item in items] == ids,
          "capture_startup_manifest_mismatch")
    if not inspect_producers:
        return
    for item in items:
        info = _inspect("container", item["id"])
        running = info.get("State", {})
        _need(info.get("Id") == item["id"] and
              info.get("Config", {}).get("Labels", {}).get("io.lrh.native-research") == resources["nonce"] and
              (running.get("Running") is False or running.get("Paused") is True),
              "capture_producer_not_stopped_or_owner_changed")
        _need(_producer_binding(info) == item.get("binding"),
              "capture_startup_manifest_mismatch")


def _freeze(run_root: Path, target: str, stop_kind: str) -> dict:
    """Freeze a stopped collector after one of NativeRun's terminal markers."""
    root = _private_dir(run_root)
    _need(target in TARGET_TO_RESEARCH, "capture_target_invalid")
    plan = _json(root / "plan.json", root)
    case = _case(plan)
    _approved_capture(plan)
    _source(root, plan, target)
    _set_docker(plan)
    slot = _private_dir(root / "controls/observer" / target)
    ledger_path = slot / "resources.json"
    ledger = _json(ledger_path, root)
    _need(ledger.get("kind") == "kanboard-capture-resources-v1" and
          ledger.get("target") == target and ledger.get("status") in
          ("active", "frozen", "cleanup_unknown") and
          all(isinstance(ledger.get(key), str) and HEX64.fullmatch(ledger[key])
              for key in ("app_id", "collector_id", "network_id")),
          "capture_not_active")
    resources = _json(root / "controls/resources.json", root)
    _need(ledger.get("nonce") == resources.get("nonce"), "capture_resource_owner_changed")
    active = ledger["status"] == "active"
    if active:
        _need(_listed("container", ledger["app_id"]), "capture_app_missing_before_freeze")
    _stop_proof(root, ledger, resources, stop_kind, inspect_producers=active)
    if active:
        app = _inspect("container", ledger["app_id"])
        state = app.get("State", {})
        _need(app.get("Id") == ledger["app_id"] and
              (state.get("Running") is False or state.get("Paused") is True) and
              app.get("Config", {}).get("Labels", {}).get("io.lrh.native-research") == ledger["nonce"],
              "capture_producer_not_stopped_or_owner_changed")
    collector_present = _listed("container", ledger["collector_id"])
    if active:
        _need(collector_present, "capture_collector_stop_unknown")
    collector = _inspect("container", ledger["collector_id"]) if collector_present else None
    if collector is not None:
        _need(collector.get("Id") == ledger["collector_id"] and
              collector.get("Name") == "/" + ledger["collector_name"] and
              collector.get("Image") == plan.get("target_image_id") and
              collector.get("Config", {}).get("Labels", {}).get("io.lrh.kanboard-capture") == ledger["nonce"],
              "capture_collector_owner_changed")
    if not active and _listed("network", ledger["network_id"]):
        network = _inspect("network", ledger["network_id"])
        _need(network.get("Id") == ledger["network_id"] and
              network.get("Name") == ledger["network_name"] and
              network.get("Labels", {}).get("io.lrh.kanboard-capture") == ledger["nonce"],
              "capture_network_owner_changed")
    frozen_path = slot / "frozen.json"
    if not active:
        _need(frozen_path.exists() and
              (collector is None or collector.get("State", {}).get("Status") in ("exited", "dead")),
              "capture_frozen_record_mismatch")
    if collector is not None and collector.get("State", {}).get("Status") == "running":
        _need(not frozen_path.exists(), "capture_frozen_record_mismatch")
        _docker("container", "stop", "--time", "10", ledger["collector_id"])
    if active:
        _need(_inspect("container", ledger["collector_id"]).get("State", {}).get("Status") in
              ("exited", "dead"), "capture_collector_stop_unknown")
    database = _regular(slot / "receipts/receipts.sqlite", root)
    try:
        with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as db:
            _need(db.execute("PRAGMA quick_check").fetchone() == ("ok",),
                  "capture_collector_sqlite_invalid")
            count, maximum = db.execute("SELECT COUNT(*),COALESCE(MAX(id),0) FROM receipts").fetchone()
            _need(type(count) is int and 0 <= count <= 5000 and type(maximum) is int,
                  "capture_collector_rows_invalid")
    except sqlite3.DatabaseError as error:
        raise CaptureHold("capture_collector_sqlite_invalid") from error
    result = {"kind": "kanboard-capture-frozen-v1", "target": target,
              "collector_id": ledger["collector_id"], "network_id": ledger["network_id"],
              "sqlite_sha256": _sha(database), "receipt_count": count, "last_receipt_id": maximum,
              "native_stop_kind": stop_kind,
              "native_stop_sha256": _sha(root / "controls/native-state" / stop_kind),
              "producer_manifest_sha256": _sha(root / "controls/producer-manifest.json"),
              "native_origin": "unproven", "credential_route":
              "brokered_identity_control" if case == "t01" else "unavailable"}
    if frozen_path.exists():
        _need(_json(frozen_path, root) == result, "capture_frozen_record_mismatch")
    else:
        _need(active, "capture_frozen_record_mismatch")
        _write_once(frozen_path, result)
    if active:
        ledger["status"] = "frozen"
        _write_replace(ledger_path, ledger)
    return {"status": ("startup_frozen_original_session_origin_held" if stop_kind == "STARTUP_CLOSED"
                       else "frozen_original_session_origin_held") if case == "t01" else
            ("startup_frozen_origin_and_credentials_held" if stop_kind == "STARTUP_CLOSED"
             else "frozen_origin_and_credentials_held"), "target": target,
            "receipt_count": count, "sqlite_sha256": result["sqlite_sha256"]}


def freeze(run_root: Path, target: str) -> dict:
    """Stop collector after NativeRun publishes REVOKED for eight producers."""
    return _freeze(run_root, target, "REVOKED")


def close_startup(run_root: Path, target: str) -> dict:
    """Freeze a partial-start collector only after verified STARTUP_CLOSED."""
    return _freeze(run_root, target, "STARTUP_CLOSED")


def _listed(kind: str, identifier: str) -> bool:
    _need(bool(HEX64.fullmatch(identifier)), "capture_resource_id_invalid")
    if kind == "container":
        output = _docker("container", "ls", "-a", "--no-trunc", "--filter", "id=" + identifier,
                         "--format", "{{.ID}}")
    else:
        output = _docker("network", "ls", "--no-trunc", "--filter", "id=" + identifier,
                         "--format", "{{.ID}}")
    _need(output in ("", identifier), "capture_resource_listing_ambiguous")
    return output == identifier


def _discover(kind: str, name: str, nonce: str, identifier: str | None) -> str | None:
    """Resolve an unsealed create by exact name and owner label before removal."""
    _need(bool(re.fullmatch(r"lrh-cap-[0-9a-f]{12}-(?:target|review-target-[12])-(?:net|collector)", name)),
          "capture_resource_name_invalid")
    if identifier is not None:
        _need(isinstance(identifier, str) and HEX64.fullmatch(identifier),
              "capture_resource_id_invalid")
        if not _listed(kind, identifier):
            return None
        candidate = identifier
    else:
        if kind == "container":
            output = _docker("container", "ls", "-a", "--no-trunc", "--filter", "name=^" + name + "$",
                             "--format", "{{.ID}}")
        else:
            output = _docker("network", "ls", "--no-trunc", "--filter", "name=^" + name + "$",
                             "--format", "{{.ID}}")
        matches = output.splitlines() if output else []
        _need(len(matches) <= 1 and all(HEX64.fullmatch(value) for value in matches),
              "capture_unsealed_resource_ambiguous")
        if not matches:
            return None
        candidate = matches[0]
    info = _inspect(kind, candidate)
    label = (info.get("Config", {}).get("Labels", {}) if kind == "container" else
             info.get("Labels", {})).get("io.lrh.kanboard-capture")
    actual_name = info.get("Name", "").lstrip("/")
    _need(info.get("Id") == candidate and actual_name == name and label == nonce,
          "capture_resource_owner_changed")
    return candidate


def abort_activation(run_root: Path, target: str) -> dict:
    """Unwind a pre-NativeRun collector failure; never remove the target app.

    This accepts only a still-created target producer. If it has started, use
    the normal owned stop/freeze path rather than tearing down capture mid-run.
    """
    root = _private_dir(run_root)
    _set_docker(_json(root / "plan.json", root))
    _need(target in TARGET_TO_RESEARCH, "capture_target_invalid")
    slot = _private_dir(root / "controls/observer" / target)
    path = slot / "resources.json"
    ledger = _json(path, root)
    _need(ledger.get("kind") == "kanboard-capture-resources-v1" and
          ledger.get("target") == target and ledger.get("status") in
          ("declared", "active", "activation_unknown", "abort_unknown"),
          "capture_not_preactivation_unknown")
    app_id = ledger.get("app_id")
    _need(isinstance(app_id, str) and HEX64.fullmatch(app_id), "capture_app_id_invalid")
    app = _inspect("container", app_id)
    _need(app.get("Id") == app_id and app.get("State", {}).get("Status") == "created" and
          app.get("Config", {}).get("Labels", {}).get("io.lrh.native-research") == ledger.get("nonce"),
          "capture_app_already_started_or_owner_changed")
    try:
        collector_id = _discover("container", ledger["collector_name"], ledger["nonce"],
                                 ledger.get("collector_id"))
        if collector_id is not None:
            _docker("container", "rm", "-f", collector_id)
            _need(not _listed("container", collector_id), "capture_collector_abort_unknown")
        network_id = _discover("network", ledger["network_name"], ledger["nonce"],
                               ledger.get("network_id"))
        if network_id is not None:
            networks = app.get("NetworkSettings", {}).get("Networks", {})
            if ledger["network_name"] in networks:
                _docker("network", "disconnect", network_id, app_id)
                app = _inspect("container", app_id)
                _need(ledger["network_name"] not in app.get("NetworkSettings", {}).get("Networks", {}),
                      "capture_app_network_abort_unknown")
            _docker("network", "rm", network_id)
            _need(not _listed("network", network_id), "capture_network_abort_unknown")
        ledger["status"] = "aborted"
        _write_replace(path, ledger)
        return {"status": "preactivation_aborted", "target": target,
                "app_preserved": True, "collector_absent": True, "network_absent": True}
    except Exception:
        ledger["status"] = "abort_unknown"
        _write_replace(path, ledger)
        raise


def cleanup(run_root: Path, target: str) -> dict:
    """Remove only this collector/network after NativeRun removes app producers."""
    root = _private_dir(run_root)
    _set_docker(_json(root / "plan.json", root))
    _need(target in TARGET_TO_RESEARCH, "capture_target_invalid")
    slot = _private_dir(root / "controls/observer" / target)
    ledger_path = slot / "resources.json"
    ledger = _json(ledger_path, root)
    _need(ledger.get("status") in ("frozen", "cleanup_unknown") and
          all(isinstance(ledger.get(key), str) and HEX64.fullmatch(ledger[key])
              for key in ("app_id", "collector_id", "network_id")),
          "capture_not_frozen")
    _need(not _listed("container", ledger["app_id"]), "capture_app_producer_still_present")
    try:
        if _listed("container", ledger["collector_id"]):
            collector = _inspect("container", ledger["collector_id"])
            _need(collector.get("Id") == ledger["collector_id"] and
                  collector.get("Name") == "/" + ledger["collector_name"] and
                  collector.get("Config", {}).get("Labels", {}).get("io.lrh.kanboard-capture") == ledger["nonce"],
                  "capture_collector_owner_changed")
            _docker("container", "rm", ledger["collector_id"])
        _need(not _listed("container", ledger["collector_id"]), "capture_collector_cleanup_unknown")
        if _listed("network", ledger["network_id"]):
            network = _inspect("network", ledger["network_id"])
            _need(network.get("Id") == ledger["network_id"] and
                  network.get("Name") == ledger["network_name"] and
                  network.get("Labels", {}).get("io.lrh.kanboard-capture") == ledger["nonce"],
                  "capture_network_owner_changed")
            _docker("network", "rm", ledger["network_id"])
        _need(not _listed("network", ledger["network_id"]), "capture_network_cleanup_unknown")
        ledger["status"] = "removed"
        _write_replace(ledger_path, ledger)
        return {"status": "removed", "target": target, "collector_absent": True,
                "network_absent": True}
    except Exception:
        ledger["status"] = "cleanup_unknown"
        _write_replace(ledger_path, ledger)
        raise
