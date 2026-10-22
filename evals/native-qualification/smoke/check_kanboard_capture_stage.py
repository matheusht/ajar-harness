#!/usr/bin/env python3
"""Provider-free E2E of the pinned Kanboard observer staging seam.

Run with the clean v1.2.36 source and a fresh private output directory::

  python3 evals/native-qualification/smoke/check_kanboard_capture_stage.py \
    --source /private/tmp/kanboard-source-644ad391 \
    --output /private/tmp/kanboard-capture-stage-NEW

The result records staged mount inputs and source-drift rejection. It does not
start Docker, OpenCode, a provider, or the application.
"""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output = args.output.expanduser().resolve()
    output.mkdir(mode=0o700, exist_ok=False)
    result = {"kind": "kanboard_capture_stage_provider_free", "status": "fail", "checks": {},
              "provider_calls": 0, "docker_calls": 0}
    try:
        s10 = module(ROOT / "evals/native-qualification/s10_observer_case.py", "capture_stage_s10")
        capture = module(ROOT / "evals/native-qualification/kanboard_native_capture.py", "capture_stage_adapter")
        source = args.source.resolve(strict=True)
        if (s10.git(source, "rev-parse", "HEAD") != s10.SOURCE_HEAD or
                s10.git(source, "status", "--porcelain", "--untracked-files=all") != ""):
            raise RuntimeError("source_not_clean_pinned")
        app = output / "source"
        app.mkdir(mode=0o700)
        s10.archive_source(source, app)
        files = {str(path.relative_to(app)): hashlib.sha256(path.read_bytes()).hexdigest()
                 for path in sorted(app.rglob("*")) if path.is_file()}
        manifest = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
        if manifest != capture.SOURCE_MANIFEST_SHA256:
            raise RuntimeError("source_manifest_mismatch")
        run = output / "run"
        run.mkdir(mode=0o700)
        for name in ("original", "target"):
            shutil.copytree(app, run / name)
        controls = run / "controls"
        controls.mkdir(mode=0o700)
        fake_docker = output / "fake-docker"
        shutil.copy2(HERE / "kanboard_capture_fake_docker.py", fake_docker)
        fake_docker.chmod(0o700)
        plan = {"source_sha256": files, "source_manifest_sha256": manifest,
                "target_image_id": "sha256:76bd7fcb18d052bd7bd744db6ce0db324c78210de8c5c52433bce6f27aecb513",
                "docker_binary": str(fake_docker),
                "docker_sha256": hashlib.sha256(fake_docker.read_bytes()).hexdigest(),
                "kanboard_capture": {"adapter_sha256": hashlib.sha256(
                    (ROOT / "evals/native-qualification/kanboard_native_capture.py").read_bytes()).hexdigest(),
                    "probe_sha256": capture.PROBE_SHA256,
                    "collector_sha256": capture.COLLECTOR_SHA256,
                    "source_manifest_sha256": capture.SOURCE_MANIFEST_SHA256,
                    "controller_sha256": capture.CONTROLLER_SHA256}}
        (run / "plan.json").write_text(json.dumps(plan, sort_keys=True))
        (run / "plan.json").chmod(0o600)
        staged = capture.stage(run, "target", s=4, q=5, t=6, b=7)
        if (staged["status"] != "staged_origin_and_credentials_held" or
                staged["target_mount"]["readonly"] is not True or
                staged["collector_mounts"][1]["source"].startswith(str(run / "target")) or
                staged["missing"] != ["native_credential_route_unavailable", "native_origin_unproven"]):
            raise RuntimeError("stage_contract_mismatch")
        result["checks"]["host_only_stage_and_hold"] = True
        result["checks"]["observer_outside_target_mount"] = True
        hook = run / "controls/observer/target/effect.php"
        if hashlib.sha256(hook.read_bytes()).hexdigest() != hashlib.sha256(capture.PROBE.read_bytes()).hexdigest():
            raise RuntimeError("hook_copy_mismatch")
        result["checks"]["hook_hash_pinned"] = True
        nonce = "a" * 32
        app_id = "c" * 64
        (controls / "resources.json").write_text(json.dumps({
            "nonce": nonce,
            "resources": [{"kind": "container", "role": "target", "id": app_id}]}))
        (controls / "resources.json").chmod(0o600)
        fake_state_path = output / "fake-docker-state.json"
        fake_state_path.write_text(json.dumps({"app": {
            "Id": app_id, "Image": plan["target_image_id"],
            "State": {"Status": "created"},
            "Config": {"Labels": {"io.lrh.native-research": nonce}},
            "Mounts": [{"Source": str(hook), "Destination": "/observer/effect.php", "RW": False}],
            "NetworkSettings": {"Networks": {"research": {"IPAddress": "172.29.0.11"}}}}}))
        try:
            capture.activate(run, "target")
        except capture.CaptureHold as error:
            if str(error) != "capture_docker_operation_unknown":
                raise
        else:
            raise RuntimeError("injected_collector_failure_was_accepted")
        # A killed owner can lose the returned ID after Docker created the
        # network. Recover only the exact predeclared name and owner label.
        sidecar = run / "controls/observer/target/resources.json"
        unknown = json.loads(sidecar.read_text())
        unknown["network_id"] = None
        sidecar.write_text(json.dumps(unknown))
        aborted = capture.abort_activation(run, "target")
        fake_state = json.loads(fake_state_path.read_text())
        if (aborted["status"] != "preactivation_aborted" or fake_state.get("network") is not None or
                "lrh-cap-" + nonce[:12] + "-target-net" in
                fake_state["app"]["NetworkSettings"]["Networks"] or
                not fake_state.get("injected_collector_create_failure")):
            raise RuntimeError("preactivation_abort_incomplete")
        result["checks"]["collector_create_failure_aborted_exact_resources"] = True
        drift = output / "drift-run"
        drift.mkdir(mode=0o700)
        shutil.copytree(app, drift / "original")
        shutil.copytree(app, drift / "target")
        (drift / "controls").mkdir(mode=0o700)
        shutil.copy2(run / "plan.json", drift / "plan.json")
        with (drift / "target" / capture.CONTROLLER).open("ab") as stream:
            stream.write(b"\n// synthetic source drift\n")
        try:
            capture.stage(drift, "target", s=4, q=5, t=6, b=7)
        except capture.CaptureHold as error:
            if str(error) != "kanboard_source_copy_changed":
                raise
        else:
            raise RuntimeError("source_drift_was_accepted")
        result["checks"]["source_drift_rejected"] = True
        result["status"] = "pass"
        result["source_manifest_sha256"] = manifest
        result["probe_sha256"] = hashlib.sha256(capture.PROBE.read_bytes()).hexdigest()
    except Exception as error:
        result["failure"] = str(error) if isinstance(error, (RuntimeError,)) else type(error).__name__
    (output / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(result["status"] + ": " + str(output / "result.json"))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
