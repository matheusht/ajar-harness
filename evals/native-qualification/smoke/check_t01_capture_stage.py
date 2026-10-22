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
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[3]
CLI = ROOT / "tools/native_research.py"
RELAY = (ROOT / "experiments/native-network-preflight/tcp-relay-host-override/"
         "cloud-linux-amd64-20261020a/tcp-relay-linux-amd64")
TARGETS = ("target", "review-target-1", "review-target-2")
WORKSPACE_BRIEF_SHA = "64b2b256fdc3285237bdf5c69f478ad680121e4a30284e1090819cff05b9cf09"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def call(environment, *parts):
    process = subprocess.run([sys.executable, str(CLI), *parts], cwd=ROOT,
                             env=environment, capture_output=True, text=True, timeout=90)
    return process.returncode, json.loads(process.stdout)


def workspace_runtime_checks(runner, workspace_run, api_run):
    """Exercise startup ordering with substituted Docker/server/API responses."""
    extensions = ["pdo_sqlite", "gd", "mbstring", "hash", "openssl", "json",
                  "ctype", "filter", "session", "dom", "SimpleXML", "xml"]
    valid = {"php_version": "8.4.16", "extensions": dict.fromkeys(extensions, True),
             "data_writable": True, "vendor_autoload_present": True}
    document = dict(runner.CONFIG, model={"providerID": "opencode",
                                         "model": "deepseek-v4.1-flash-free"}, fallback=None)
    endpoints = {
        "agent": [{"id": "build", "mode": "primary", "permissions": [{}] * 12}],
        "plugin": [{"id": "opencode.tool." + name} for name in ("edit", "write", "shell")],
        "config": [{"type": "document", "path": "/workspace/config/opencode/opencode.json",
                    "info": document}],
        "skill": [], "mcp": [], "reference": [], "command": [],
    }

    def surface(root, value, *, returncode=0, command_error=False):
        events, commands = [], []
        server = SimpleNamespace(stdout=io.StringIO("1234\nserver password fixture-only\n"),
                                 poll=lambda: None, wait=lambda **kwargs: 0, kill=lambda: None)

        def docker(*args, **kwargs):
            if args[3] == "php":
                events.append("php")
                commands.append(args)
                if command_error:
                    raise runner.NativeResearchError("docker_command_unavailable")
                return subprocess.CompletedProcess(args, returncode,
                    value if isinstance(value, bytes) else json.dumps(value).encode(), b"")
            if args[3:5] == ("/usr/local/bin/opencode", "--version"):
                events.append("version")
                body = runner.VERSION.encode()
            elif args[3:6] == ("/usr/local/bin/opencode", "debug", "paths"):
                body = b"/workspace/data/opencode/opencode.db"
            elif args[3] == "wget":
                body = json.dumps(endpoints[args[-1].rsplit("/", 1)[-1]]).encode()
            elif args[3] == "kill":
                body = b""
            else:
                raise AssertionError("unexpected substituted Docker command")
            return subprocess.CompletedProcess(args, 0, body, b"")

        def popen(*args, **kwargs):
            events.append("server")
            return server

        with patch.object(runner, "_docker", side_effect=docker), \
                patch.object(runner.subprocess, "Popen", side_effect=popen), \
                patch.object(runner.select, "select", return_value=([server.stdout], [], [])):
            try:
                inventory, error = runner._surface_probe(root, "fixture-researcher"), None
            except runner.NativeResearchError as problem:
                inventory, error = None, str(problem)
        return inventory, error, events, commands

    checks = {}
    expected = {"php_version": "8.4.16", "extensions": extensions,
                "data_writable": True, "vendor_autoload_present": True}
    inventory, error, events, commands = surface(workspace_run, valid)
    checks["workspace_runtime_inventory_and_startup_order"] = (
        error is None and inventory.get("workspace_runtime") == expected and
        events[:3] == ["php", "version", "server"] and len(commands) == 1 and
        commands[0][:5] == ("container", "exec", "fixture-researcher", "php", "-r") and
        all(word in commands[0][5] for word in ("PHP_VERSION", "extension_loaded", "is_writable")) and
        not any(word in commands[0][5] for word in ("require", "include", "/target")))
    inventory, error, events, commands = surface(api_run, b"PHP must not run")
    checks["api_mode_skips_workspace_runtime_probe"] = (
        error is None and "workspace_runtime" not in inventory and not commands and
        events == ["version", "server"])
    minimum, error, _, _ = surface(workspace_run, dict(valid, php_version="8.1.0"))
    checks["workspace_runtime_accepts_minimum_php"] = (
        error is None and minimum.get("workspace_runtime", {}).get("php_version") == "8.1.0")
    bad = [("missing_php", valid, {"returncode": 127}),
           ("command_failure", valid, {"command_error": True}),
           ("malformed_json", b"not JSON", {}), ("oversize", b"x" * 4097, {}),
           ("wrong_shape", [], {}), ("old_php", dict(valid, php_version="8.0.30"), {}),
           ("invalid_version", dict(valid, php_version=None), {}),
           ("prerelease_minimum", dict(valid, php_version="8.1.0RC1"), {}),
           ("unwritable_data", dict(valid, data_writable=False), {}),
           ("missing_vendor", dict(valid, vendor_autoload_present=False), {}),
           ("invalid_boolean", dict(valid, data_writable=1), {}),
           ("missing_fields", {"php_version": "8.4.16"}, {})]
    for extension in extensions:
        bad.append(("missing_" + extension,
                    dict(valid, extensions={name: True for name in extensions if name != extension}), {}))
    for label, value, options in bad:
        inventory, error, events, _ = surface(workspace_run, value, **options)
        checks["workspace_runtime_rejects_" + label] = (
            inventory is None and error == "workspace_php_runtime_unavailable" and events == ["php"])
    return checks


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
            "t01_research_mode" not in plan and
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

        def rejected_plan(run_root, changed, expected):
            path = run_root / "plan.json"
            original = path.read_bytes()
            try:
                path.write_text(json.dumps(changed))
                code, rejected = call(environment, "capture-stage", "--run-root",
                                      str(run_root), "--target", "target")
                return code == 2 and rejected.get("code") == expected
            finally:
                path.write_bytes(original)

        for label, mode in (("unknown", "other"), ("null", None),
                            ("list", []), ("object", {})):
            result["checks"]["reject_" + label + "_research_mode"] = rejected_plan(
                run, dict(plan, t01_research_mode=mode), "t01_capture_research_mode_invalid")
        result["checks"]["reject_workspace_mode_with_api_brief"] = rejected_plan(
            run, dict(plan, t01_research_mode="workspace_research"),
            "t01_capture_brief_pin_mismatch")
        outside_t01 = dict(plan, t01_research_mode="workspace_research")
        del outside_t01["t01_capture"]
        result["checks"]["reject_research_mode_without_t01"] = rejected_plan(
            run, outside_t01, "t01_capture_research_mode_invalid")

        runner._write_target_info(run, "researcher", "192.0.2.1", plan)
        old_info = json.loads((run / "researcher/project/target.json").read_text())
        result["checks"]["api_target_info_unchanged"] = old_info == {
            "url": "http://192.0.2.1:8080", "source_manifest_sha256": plan["source_manifest_sha256"],
            "role": "researcher", "synthetic_actor_route": {
                "header": "X-Native-Actor", "handles": ["A", "B"],
                "entrypoint": "POST /jsonrpc.php", "response_request_id_header": "X-LRH-Request-ID",
                "backend_identity_and_session": "target-owned; original same-operation origin held"}}

        workspace_brief = ROOT / "evals/native-qualification/RESEARCHER-BRIEF-T01-WORKSPACE.md"
        result["checks"]["workspace_brief_exact"] = sha(workspace_brief) == WORKSPACE_BRIEF_SHA
        altered_brief = output / "altered-workspace-brief.md"
        altered_brief.write_bytes(workspace_brief.read_bytes() + b"\nChanged setup.\n")
        altered_run = output / "altered-workspace-run"
        workspace_base = list(base)
        workspace_base[workspace_base.index("--run-root") + 1] = str(altered_run)
        workspace_base[workspace_base.index("--brief") + 1] = str(altered_brief)
        code, rejected = call(environment, *workspace_base, "--t01-capture")
        result["checks"]["altered_workspace_brief_rejected_before_root"] = (
            code == 2 and rejected.get("code") == "t01_capture_brief_pin_mismatch" and
            not altered_run.exists())
        workspace_run = output / "workspace-run"
        workspace_base[workspace_base.index("--run-root") + 1] = str(workspace_run)
        workspace_base[workspace_base.index("--brief") + 1] = str(workspace_brief)
        code, prepared = call(environment, *workspace_base, "--t01-capture")
        if code or prepared.get("status") != "prepared_provider_free":
            raise RuntimeError("workspace_prepare_failed:" + str(prepared))
        workspace_plan = json.loads((workspace_run / "plan.json").read_text())
        result["checks"]["workspace_prepare_frozen"] = (
            workspace_plan.get("t01_research_mode") == "workspace_research" and
            workspace_plan["t01_capture"] == plan["t01_capture"] and
            workspace_plan["brief_sha256"] == WORKSPACE_BRIEF_SHA and
            all(sha(workspace_run / path) == WORKSPACE_BRIEF_SHA for path in
                ("controls/BRIEF.md", "controls/research/BRIEF.md", "researcher/brief/BRIEF.md")))
        stages = {}
        for target in TARGETS:
            code, staged = call(environment, "capture-stage", "--run-root", str(workspace_run),
                                "--target", target)
            if code or staged.get("status") != "staged_original_session_origin_held":
                raise RuntimeError("workspace_stage_failed:" + str(staged))
            stages[target] = staged["stage_sha256"]
        result["checks"]["workspace_three_t01_stages_pinned"] = all(
            stages[target] == sha(workspace_run / "controls/observer" / target / "stage.json")
            for target in TARGETS)
        missing_mode = dict(workspace_plan)
        del missing_mode["t01_research_mode"]
        result["checks"]["reject_workspace_brief_without_mode"] = rejected_plan(
            workspace_run, missing_mode, "t01_capture_brief_pin_mismatch")
        result["checks"]["reject_workspace_mode_with_other_brief"] = rejected_plan(
            workspace_run, dict(workspace_plan, brief_sha256=sha(brief)),
            "t01_capture_brief_pin_mismatch")
        for role in ("researcher", "reviewer-1", "reviewer-2"):
            info_root = output / ("target-info-" + role)
            (info_root / role / "project").mkdir(parents=True)
            runner._write_target_info(info_root, role, "192.0.2.1", workspace_plan)
            info = json.loads((info_root / role / "project/target.json").read_text())
            result["checks"][role + "_protected_api_distinct"] = (
                info.get("url_role") == "protected_original_api_copy" and
                info["synthetic_actor_route"] == old_info["synthetic_actor_route"] and
                info.get("protected_api_limits") == [
                    "JSON-RPC only", "ordinary actors A and B only",
                    "response strings and dynamic keys redacted",
                    "no protected web or administrator access; effect coverage is case-specific"])
            if role == "researcher":
                # Resume mounts this same researcher workspace and target.json.
                result["checks"]["researcher_and_resume_own_copy_route"] = info.get("workspace_research") == {
                    "source": "/workspace/project", "service_bind": "127.0.0.1",
                    "entry_paths": ["web", "JSON-RPC"],
                    "setup": "researcher-controlled; separate from the supplied protected API copy"}
            else:
                result["checks"][role + "_no_researcher_path"] = (
                    "workspace_research" not in info and "/workspace/project" not in json.dumps(info))
        result["runtime_probe_evidence"] = "substituted Docker, native server and API; no runtime qualification"
        result["checks"].update(workspace_runtime_checks(runner, workspace_run, run))
        result["status"] = "pass" if all(result["checks"].values()) else "fail"
    except Exception as error:
        result["failure"] = str(error)
    result["checks"]["no_docker_started"] = not (output / "docker-calls").exists()
    if not result["checks"]["no_docker_started"]:
        result["status"] = "fail"
    (output / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": result["status"], "result": str(output / "result.json")},
                     sort_keys=True))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
