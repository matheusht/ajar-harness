#!/usr/bin/env python3
"""Provider-free CLI rehearsal of T01 prepare, stage, and source-drift hold.

Run with the retained v1.2.49 source and a fresh private output path::

  python3 evals/native-qualification/smoke/check_t01_capture_stage.py \
    --source /tmp/native-qualification-researcher-20261019-final/source \
    --output /private/tmp/t01-capture-stage-NEW

No Docker daemon, application, native agent, or provider is started.
"""

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[3]
CLI = ROOT / "tools/native_research.py"
RELAY = (ROOT / "experiments/native-network-preflight/tcp-relay-host-override/"
         "cloud-linux-amd64-20261020a/tcp-relay-linux-amd64")
TARGETS = ("target", "review-target-1", "review-target-2")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def call(environment, *parts):
    process = subprocess.run([sys.executable, str(CLI), *parts], cwd=ROOT,
                             env=environment, capture_output=True, text=True, timeout=90)
    return process.returncode, json.loads(process.stdout)


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    source = args.source.resolve(strict=True)
    output = args.output.resolve()
    output.mkdir(mode=0o700, exist_ok=False)
    result = {"kind": "t01_capture_stage_provider_free", "status": "fail",
              "checks": {}, "provider_calls": 0, "docker_calls": 0, "target_calls": 0}
    try:
        fake_docker = output / "docker"
        fake_docker.write_text('#!/bin/sh\nprintf x >> "$NATIVE_FAKE_DOCKER_LOG"\nexit 99\n')
        fake_docker.chmod(0o700)
        environment = dict(os.environ)
        environment["PATH"] = str(output) + os.pathsep + environment["PATH"]
        environment["NATIVE_FAKE_DOCKER_LOG"] = str(output / "docker-calls")
        brief = ROOT / "evals/native-qualification/RESEARCHER-BRIEF-T01-API.md"
        scope = output / "scope.md"
        scope.write_text("Provider-free staging rehearsal; no live target authority.\n")
        relay = output / "relay"
        shutil.copy2(RELAY, relay)
        relay.chmod(0o700)
        ca = output / "ca.pem"
        key = output / "ca.key"
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-noenc",
                        "-days", "1", "-subj", "/CN=owned T01 staging fixture",
                        "-keyout", str(key), "-out", str(ca)], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
        key.unlink()
        command = output / "target-command.json"
        command.write_text(json.dumps(["php", "-S", "0.0.0.0:8080", "-t", "/target"]))
        run = output / "run"
        base = ("prepare", "--run-root", str(run), "--source", str(source),
                "--brief", str(brief), "--scope-file", str(scope), "--scope-sha256", sha(scope),
                "--relay", str(relay), "--relay-sha256", sha(relay),
                "--runtime-ca", str(ca), "--runtime-ca-sha256", sha(ca),
                "--target-command", str(command), "--target-port", "8080",
                "--image-id", "sha256:" + "1" * 64,
                "--target-image-id", "sha256:" + "2" * 64,
                "--platform", "linux/amd64", "--mutable-path", "data")
        wrong_mode = list(base)
        wrong_mode[wrong_mode.index("--run-root") + 1] = str(output / "wrong-mode")
        code, rejected = call(environment, *wrong_mode, "--kanboard-capture")
        result["checks"]["s10_mode_rejects_t01_source"] = (
            code == 2 and rejected.get("code") ==
            "kanboard_capture_source_or_command_unqualified" and
            not (output / "wrong-mode").exists())
        wrong_brief = output / "wrong-brief.md"
        wrong_brief.write_text("Inspect this application.\n")
        wrong_brief_run = output / "wrong-brief-run"
        wrong_brief_base = list(base)
        wrong_brief_base[wrong_brief_base.index("--run-root") + 1] = str(wrong_brief_run)
        wrong_brief_base[wrong_brief_base.index("--brief") + 1] = str(wrong_brief)
        code, rejected = call(environment, *wrong_brief_base, "--t01-capture")
        result["checks"]["t01_wrong_brief_rejected"] = (
            code == 2 and rejected.get("code") == "t01_capture_brief_pin_mismatch" and
            not wrong_brief_run.exists())
        code, prepared = call(environment, *base, "--t01-capture")
        if code or prepared.get("status") != "prepared_provider_free":
            raise RuntimeError("t01_prepare_failed:" + str(prepared))
        plan = json.loads((run / "plan.json").read_text())
        result["checks"]["public_prepare_pins_t01"] = (
            "t01_capture" in plan and "kanboard_capture" not in plan and
            plan["brief_sha256"] == sha(brief) and
            sha(run / "controls/BRIEF.md") == sha(brief) and
            plan["source_manifest_sha256"] ==
            "5d49c3f485f555f3118b0afb983997e29a5ddaad4b0ed6f9cf19d855c2e4f884")
        code, rejected = call(environment, "capture-stage", "--run-root", str(run),
                              "--target", "target", "--s", "1", "--q", "2", "--t", "3", "--b", "4")
        result["checks"]["s10_seed_ids_rejected"] = (code == 2 and
            rejected.get("code") == "t01_seed_ids_forbidden" and
            not (run / "controls/observer/target").exists())
        stages = {}
        for target in TARGETS:
            code, staged = call(environment, "capture-stage", "--run-root", str(run),
                                "--target", target)
            if code or staged.get("status") != "staged_original_session_origin_held":
                raise RuntimeError("t01_stage_failed:" + str(staged))
            stages[target] = staged["stage_sha256"]
        result["checks"]["three_t01_stages_pinned"] = all(
            stages[target] == sha(run / "controls/observer" / target / "stage.json")
            for target in TARGETS)
        approval = run / "controls/approval.json"
        approval.write_text(json.dumps({"capture_stage_sha256": stages}))
        approval.chmod(0o600)
        spec = importlib.util.spec_from_file_location("t01_stage_runner", CLI)
        runner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runner)
        runner._capture_approved_specs(run, plan,
            ["php", "-S", "0.0.0.0:8080", "-t", "/target"], verify_source=True)
        result["checks"]["approved_specs_provider_free"] = True
        drift = run / "target/app/Api/Middleware/AuthenticationMiddleware.php"
        original = drift.read_bytes()
        drift.write_bytes(original + b"\n// synthetic drift\n")
        try:
            runner._capture_approved_specs(run, plan,
                ["php", "-S", "0.0.0.0:8080", "-t", "/target"], verify_source=True)
        except runner.NativeResearchError as error:
            result["checks"]["post_stage_source_drift_held"] = (
                str(error) == "target_source_or_state_changed")
        else:
            result["checks"]["post_stage_source_drift_held"] = False
        drift.write_bytes(original)
        result["checks"]["no_docker_started"] = not (output / "docker-calls").exists()
        result["status"] = "pass" if all(result["checks"].values()) else "fail"
    except Exception as error:
        result["failure"] = str(error)
    (output / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": result["status"], "result": str(output / "result.json")},
                     sort_keys=True))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
