#!/usr/bin/env python3
"""Provider-free E2E of Kanboard capture terminal close and crash retry.

Requires the clean Kanboard v1.2.36 source. Makes no real Docker, provider,
OpenCode, or target calls; all Docker inspections use a private fake executable.
"""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sqlite3
import sys


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ROLES = ("relay", "target", "review-target-1", "review-target-2",
         "researcher", "reviewer-1", "reviewer-2", "resume")


def module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, sort_keys=True) + "\n")
    path.chmod(0o600)


def binding(info: dict) -> str:
    value = {key: info[key] for key in ("Id", "Image", "Config", "Mounts")}
    value["Mounts"] = sorted(info["Mounts"], key=lambda mount: mount["Destination"])
    value["networks"] = sorted(info["NetworkSettings"]["Networks"])
    value["host"] = {key: info["HostConfig"][key] for key in
                     ("ReadonlyRootfs", "Privileged", "RestartPolicy", "CapDrop", "SecurityOpt")}
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def expect_hold(action, capture, code: str) -> None:
    try:
        action()
    except capture.CaptureHold as error:
        if str(error) != code:
            raise RuntimeError("unexpected_hold_" + str(error)) from error
    else:
        raise RuntimeError("expected_hold_missing_" + code)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output = args.output.expanduser().resolve()
    output.mkdir(mode=0o700, exist_ok=False)
    result = {"kind": "kanboard_capture_terminal_close_provider_free", "status": "fail",
              "checks": {}, "real_docker_calls": 0, "provider_calls": 0}
    try:
        s10 = module(ROOT / "evals/native-qualification/s10_observer_case.py", "capture_close_s10")
        capture = module(ROOT / "evals/native-qualification/kanboard_native_capture.py", "capture_close_adapter")
        source = args.source.resolve(strict=True)
        if (s10.git(source, "rev-parse", "HEAD") != s10.SOURCE_HEAD or
                s10.git(source, "status", "--porcelain", "--untracked-files=all") != ""):
            raise RuntimeError("source_not_clean_pinned")
        app_source = output / "source"
        app_source.mkdir(mode=0o700)
        s10.archive_source(source, app_source)
        files = {path.relative_to(app_source).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                 for path in sorted(app_source.rglob("*")) if path.is_file()}
        manifest_sha = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
        if manifest_sha != capture.SOURCE_MANIFEST_SHA256:
            raise RuntimeError("source_manifest_mismatch")
        fake_docker = output / "fake-docker"
        shutil.copy2(HERE / "kanboard_capture_fake_docker.py", fake_docker)
        fake_docker.chmod(0o700)
        fake_state_path = output / "fake-docker-state.json"

        def fixture(name: str) -> tuple[Path, Path, dict, dict]:
            run = output / name
            run.mkdir(mode=0o700)
            for part in ("original", "target"):
                shutil.copytree(app_source, run / part)
            controls = run / "controls"
            controls.mkdir(mode=0o700)
            plan = {"source_sha256": files, "source_manifest_sha256": manifest_sha,
                    "target_image_id": "sha256:" + "8" * 64,
                    "docker_binary": str(fake_docker),
                    "docker_sha256": hashlib.sha256(fake_docker.read_bytes()).hexdigest(),
                    "kanboard_capture": {"adapter_sha256": hashlib.sha256(
                        (ROOT / "evals/native-qualification/kanboard_native_capture.py").read_bytes()).hexdigest(),
                        "probe_sha256": capture.PROBE_SHA256,
                        "collector_sha256": capture.COLLECTOR_SHA256,
                        "source_manifest_sha256": capture.SOURCE_MANIFEST_SHA256,
                        "controller_sha256": capture.CONTROLLER_SHA256}}
            write(run / "plan.json", plan)
            capture.stage(run, "target", s=4, q=5, t=6, b=7)
            slot = controls / "observer/target"
            nonce = "9" * 32
            ids = {role: format(index + 1, "x") * 64 for index, role in enumerate(ROLES)}
            collector_id = "a" * 64
            network_id = "b" * 64
            rows = [{"kind": "container", "role": role, "id": ids[role]} for role in ROLES]
            write(controls / "resources.json", {"nonce": nonce, "resources": rows})
            write(slot / "resources.json", {
                "kind": "kanboard-capture-resources-v1", "status": "active", "nonce": nonce,
                "target": "target", "app_id": ids["target"], "collector_id": collector_id,
                "network_id": network_id, "collector_name": "lrh-cap-" + nonce[:12] + "-target-collector",
                "network_name": "lrh-cap-" + nonce[:12] + "-target-net"})
            containers = {}
            for role in ROLES:
                identifier = ids[role]
                containers[identifier] = {
                    "Id": identifier, "Image": plan["target_image_id"],
                    "State": {"Status": "exited", "Running": False, "Paused": False},
                    "Config": {"Labels": {"io.lrh.native-research": nonce}},
                    "Mounts": [], "NetworkSettings": {"Networks": {"research": {}}},
                    "HostConfig": {"ReadonlyRootfs": True, "Privileged": False,
                                   "RestartPolicy": {"Name": "no"}, "CapDrop": ["ALL"],
                                   "SecurityOpt": ["no-new-privileges=true"]}}
            containers[collector_id] = {
                "Id": collector_id, "Name": "/lrh-cap-" + nonce[:12] + "-target-collector",
                "Image": plan["target_image_id"],
                "State": {"Status": "running", "Running": True, "Paused": False},
                "Config": {"Labels": {"io.lrh.kanboard-capture": nonce}},
                "Mounts": [], "NetworkSettings": {"Networks": {}}}
            state = {"mode": "freeze", "containers": containers, "collector_id": collector_id,
                     "network_id": network_id,
                     "network": {"Id": network_id, "Name": "lrh-cap-" + nonce[:12] + "-target-net",
                                 "Labels": {"io.lrh.kanboard-capture": nonce}},
                     "stop_calls": 0}
            write(fake_state_path, state)
            manifest = {"version": 1, "nonce": nonce,
                        "producers": [{"id": ids[role], "binding": binding(containers[ids[role]])}
                                      for role in ROLES]}
            write(controls / "producer-manifest.json", manifest)
            (controls / "native-state").mkdir(mode=0o700)
            return run, slot, state, manifest

        run, slot, state, manifest = fixture("startup-run")
        marker = run / "controls/native-state/STARTUP_CLOSED"
        expect_hold(lambda: capture.close_startup(run, "target"), capture,
                    "capture_native_stop_unverified")
        write(marker, {"producers_verified_stopped": False, "monotonic": 1.0})
        expect_hold(lambda: capture.close_startup(run, "target"), capture,
                    "capture_native_stop_unverified")
        write(marker, {"producers_verified_stopped": True, "monotonic": 1.0})
        expect_hold(lambda: capture.close_startup(run, "target"), capture,
                    "capture_native_stop_unverified")
        write(marker.parent / "STOPPING", {"reason": "child_exited_before_prepare", "monotonic": 0.5})
        write(marker.parent / "RUN.json", {"ids": [row["id"] for row in manifest["producers"]]})
        expect_hold(lambda: capture.close_startup(run, "target"), capture,
                    "capture_native_stop_unverified")
        (marker.parent / "RUN.json").unlink()
        write(marker.parent / "UNSAFE", {"producers_verified_stopped": False})
        expect_hold(lambda: capture.close_startup(run, "target"), capture,
                    "capture_native_stop_unverified")
        (marker.parent / "UNSAFE").unlink()
        manifest["producers"][0]["binding"] = "0" * 64
        write(run / "controls/producer-manifest.json", manifest)
        expect_hold(lambda: capture.close_startup(run, "target"), capture,
                    "capture_startup_manifest_mismatch")
        manifest["producers"][0]["binding"] = binding(state["containers"][manifest["producers"][0]["id"]])
        write(run / "controls/producer-manifest.json", manifest)
        first = manifest["producers"][0]["id"]
        state["containers"][first]["State"] = {"Status": "running", "Running": True, "Paused": False}
        write(fake_state_path, state)
        expect_hold(lambda: capture.close_startup(run, "target"), capture,
                    "capture_producer_not_stopped_or_owner_changed")
        state["containers"][first]["State"] = {"Status": "exited", "Running": False, "Paused": False}
        write(fake_state_path, state)
        controller = run / "target" / capture.CONTROLLER
        original_controller = controller.read_bytes()
        controller.write_bytes(original_controller + b"\n// drift\n")
        expect_hold(lambda: capture.close_startup(run, "target"), capture,
                    "kanboard_source_copy_changed")
        controller.write_bytes(original_controller)
        closed = capture.close_startup(run, "target")
        if closed["status"] != "startup_frozen_origin_and_credentials_held":
            raise RuntimeError("startup_close_status_invalid")
        frozen_path = slot / "frozen.json"
        frozen = json.loads(frozen_path.read_text())
        original_frozen = dict(frozen)
        if frozen.get("native_stop_kind") != "STARTUP_CLOSED":
            raise RuntimeError("startup_stop_kind_missing")
        result["checks"]["startup_marker_and_manifest_fail_closed"] = True
        result["checks"]["startup_collector_frozen"] = True
        ledger_path = slot / "resources.json"
        ledger = json.loads(ledger_path.read_text())
        ledger["status"] = "active"  # kill after frozen.json, before ledger transition
        write(ledger_path, ledger)
        retried = capture.close_startup(run, "target")
        if retried != closed or json.loads(fake_state_path.read_text())["stop_calls"] != 1:
            raise RuntimeError("startup_close_retry_changed_result")
        result["checks"]["startup_crash_retry_completed"] = True
        state = json.loads(fake_state_path.read_text())
        state["containers"].pop(json.loads(ledger_path.read_text())["app_id"])
        write(fake_state_path, state)
        if capture.close_startup(run, "target") != closed:
            raise RuntimeError("startup_owner_loss_after_app_removal_unrecovered")
        result["checks"]["startup_frozen_after_app_removal"] = True
        ledger["status"] = "active"
        write(ledger_path, ledger)
        expect_hold(lambda: capture.close_startup(run, "target"), capture,
                    "capture_app_missing_before_freeze")
        ledger["status"] = "frozen"
        write(ledger_path, ledger)
        frozen["sqlite_sha256"] = "0" * 64
        write(frozen_path, frozen)
        expect_hold(lambda: capture.close_startup(run, "target"), capture,
                    "capture_frozen_record_mismatch")
        result["checks"]["changed_frozen_record_rejected"] = True
        write(frozen_path, original_frozen)
        with sqlite3.connect(slot / "receipts/receipts.sqlite") as db:
            db.execute("INSERT INTO receipts(peer,payload) VALUES(?,?)", ("synthetic", "{}"))
        expect_hold(lambda: capture.close_startup(run, "target"), capture,
                    "capture_frozen_record_mismatch")
        result["checks"]["changed_collector_db_rejected"] = True

        run, slot, state, manifest = fixture("revoked-run")
        write(run / "controls/native-state/REVOKED", {
            "producers_verified_stopped": True,
            "ids": [row["id"] for row in manifest["producers"]]})
        closed = capture.freeze(run, "target")
        if closed["status"] != "frozen_origin_and_credentials_held":
            raise RuntimeError("revoked_close_status_invalid")
        ledger_path = slot / "resources.json"
        ledger = json.loads(ledger_path.read_text())
        ledger["status"] = "active"
        write(ledger_path, ledger)
        if capture.freeze(run, "target") != closed or json.loads(fake_state_path.read_text())["stop_calls"] != 1:
            raise RuntimeError("revoked_close_retry_changed_result")
        result["checks"]["revoked_crash_retry_completed"] = True
        state = json.loads(fake_state_path.read_text())
        state["containers"].pop(json.loads(ledger_path.read_text())["app_id"])
        write(fake_state_path, state)
        if capture.freeze(run, "target") != closed:
            raise RuntimeError("revoked_owner_loss_after_app_removal_unrecovered")
        ledger = json.loads(ledger_path.read_text())
        ledger["status"] = "cleanup_unknown"
        write(ledger_path, ledger)
        state = json.loads(fake_state_path.read_text())
        state["containers"].pop(state["collector_id"])
        write(fake_state_path, state)
        if capture.freeze(run, "target") != closed:
            raise RuntimeError("cleanup_unknown_frozen_recheck_failed")
        removed = capture.cleanup(run, "target")
        final_state = json.loads(fake_state_path.read_text())
        if (removed["status"] != "removed" or
                final_state["collector_id"] in final_state["containers"] or
                final_state["network"] is not None):
            raise RuntimeError("observer_cleanup_after_owner_loss_incomplete")
        result["checks"]["revoked_frozen_after_app_removal_and_observer_cleanup"] = True
        result["status"] = "pass"
        result["source_manifest_sha256"] = manifest_sha
    except Exception as error:
        result["failure"] = str(error) if isinstance(error, RuntimeError) else type(error).__name__
    write(output / "result.json", result)
    print(result["status"] + ": " + str(output / "result.json"))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
