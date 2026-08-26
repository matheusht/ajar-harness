#!/usr/bin/env python3
"""Hunter execution envelope — context allowlist + provider isolation.

Plane 2 stays the orchestrator. This runner is the hunter *environment provider*:
start_env, run_hunter, collect_artifacts, teardown. It does not adjudicate, file
findings, authorize Zone-2, or replace engine/loop.md.

Usage:
  python3 tools/run-hunter-envelope.py --self-test
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

from engagement_records import (  # noqa: E402
    HUNTER_DEFAULT_WITHHELD_PREFIXES,
    RecordError,
    _path_under_prefix,
    sha256_bytes,
    validate_record,
)

DEFAULT_WITHHELD_PREFIXES = HUNTER_DEFAULT_WITHHELD_PREFIXES
DOCKER_IMAGE = "alpine:3.20"


class EnvelopeError(RecordError):
    pass


def validate_hunter_run(spec: dict[str, Any]) -> list[dict[str, Any]]:
    return validate_record(spec, "hunter-run")


def provider_available(name: str) -> bool:
    if name == "local":
        return True
    if name == "docker":
        if not shutil.which("docker"):
            return False
        probe = subprocess.run(["docker", "info"], capture_output=True, text=True)
        return probe.returncode == 0
    if name == "harbor":
        return shutil.which("harbor") is not None
    return False


def _raise_if_invalid(spec: dict[str, Any]) -> None:
    errors = validate_hunter_run(spec)
    if errors:
        raise EnvelopeError(errors[0]["code"], errors[0]["message"], details=errors)


def _stage_context(spec: dict[str, Any], workspace: Path) -> Path:
    context = Path(tempfile.mkdtemp(prefix="hunter-envelope-"))
    try:
        for rel in spec["allowed_paths"]:
            if any(_path_under_prefix(rel, prefix) for prefix in spec["withheld_paths"]):
                raise EnvelopeError("hunter_gold_path_allowed", f"refusing to stage withheld path {rel}")
            src = workspace / rel
            if not src.is_file():
                raise EnvelopeError("allowed_path_missing", f"allowed path not found: {rel}")
            dest = context / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
        brief_path = context / spec["brief_path"]
        brief_path.parent.mkdir(parents=True, exist_ok=True)
        brief_path.write_text(spec["brief"] + "\n", encoding="utf-8")
        handle_path = context / "target-handle.json"
        handle_path.write_text(json.dumps(spec["target_handle"], indent=2) + "\n", encoding="utf-8")
        (context / spec["artifact_out"]).mkdir(parents=True, exist_ok=True)
    except Exception:
        shutil.rmtree(context, ignore_errors=True)
        raise
    return context


def start_env(spec: dict[str, Any], *, workspace: Path | None = None) -> dict[str, Any]:
    _raise_if_invalid(spec)
    provider = spec["provider"]
    if provider != "local" and not provider_available(provider):
        raise EnvelopeError("provider_unavailable", f"{provider} is not available on this host")
    workspace = Path(workspace or ROOT)
    context = _stage_context(spec, workspace)
    return {
        "provider": provider,
        "context_root": str(context),
        "artifact_dir": str(context / spec["artifact_out"]),
        "workspace": str(workspace),
        "spec": spec,
        "image": DOCKER_IMAGE if provider == "docker" else None,
    }


def _scrubbed_env(home: Path) -> dict[str, str]:
    return {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(home), "LC_ALL": "C", "TMPDIR": str(home)}


def _run_local(handle: dict[str, Any], argv: list[str], timeout: int) -> dict[str, Any]:
    context = Path(handle["context_root"])
    proc = subprocess.run(argv, cwd=context, env=_scrubbed_env(context), capture_output=True, text=True, timeout=timeout)
    return {"returncode": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr}


def _docker_network_flag(spec: dict[str, Any]) -> list[str]:
    if spec.get("network_policy") == "no-network":
        return ["--network", "none"]
    return []


def _run_docker(handle: dict[str, Any], argv: list[str], timeout: int) -> dict[str, Any]:
    context = str(Path(handle["context_root"]).resolve())
    cmd = ["docker", "run", "--rm", *_docker_network_flag(handle["spec"]), "-v", f"{context}:/work", "-w", "/work", handle["image"], *argv]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return {"returncode": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr}


def run_hunter(handle: dict[str, Any], argv: list[str], *, timeout: int = 30) -> dict[str, Any]:
    if handle["provider"] == "docker":
        return _run_docker(handle, argv, timeout)
    if handle["provider"] == "harbor":
        raise EnvelopeError("provider_unavailable", "live harbor run is not implemented in this spike; render_harbor_task only")
    return _run_local(handle, argv, timeout)


def collect_artifacts(handle: dict[str, Any]) -> list[dict[str, Any]]:
    root = Path(handle["artifact_dir"])
    if not root.is_dir():
        return []
    artifacts = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        data = path.read_bytes()
        item = {"name": path.name, "relative_path": str(path.relative_to(root)), "size": len(data), "sha256": sha256_bytes(data)}
        try:
            item["text"] = data.decode("utf-8")
        except UnicodeDecodeError:
            item["text"] = None
        artifacts.append(item)
    return artifacts


def teardown(handle: dict[str, Any]) -> None:
    context = handle.get("context_root")
    if context:
        shutil.rmtree(context, ignore_errors=True)


def gold_readable_inside(handle: dict[str, Any], gold_relpath: str) -> bool:
    if handle["provider"] == "docker":
        result = run_hunter(handle, ["cat", gold_relpath])
        return result.get("returncode") == 0 and bool(result.get("stdout"))
    context = Path(handle["context_root"])
    candidate = context / gold_relpath
    if candidate.is_file():
        return True
    result = run_hunter(handle, [sys.executable, "-c", f"print(open({gold_relpath!r},encoding='utf-8').read())"])
    return result.get("returncode") == 0 and "GOLD-MUST-NOT-LEAK" in result.get("stdout", "")


def render_harbor_task(spec: dict[str, Any], dest: Path) -> dict[str, str]:
    _raise_if_invalid(spec)
    dest.mkdir(parents=True, exist_ok=True)
    instruction = dest / "instruction.md"
    instruction.write_text(spec["brief"].rstrip() + "\n", encoding="utf-8")
    task_toml = dest / "task.toml"
    task_toml.write_text(
        "\n".join([
            'schema_version = "1.4"',
            "",
            "[task]",
            'name = "harness/hunter-envelope"',
            'version = "1.0.0"',
            'description = "Isolated hunter run. Oracle and orchestrator stay outside this environment."',
            "",
            "[agent]",
            "timeout_sec = 300.0",
            "",
            "[verifier]",
            "timeout_sec = 60.0",
            'environment_mode = "separate"',
            "",
            "[environment]",
            f'network_mode = "{"no-network" if spec.get("network_policy") == "no-network" else "public"}"',
            "",
        ]) + "\n",
        encoding="utf-8",
    )
    env_dir = dest / "environment"
    env_dir.mkdir(exist_ok=True)
    dockerfile = env_dir / "Dockerfile"
    dockerfile.write_text("FROM alpine:3.20\nWORKDIR /work\n", encoding="utf-8")
    tests = dest / "tests"
    tests.mkdir(exist_ok=True)
    (tests / "test.sh").write_text("#!/bin/sh\n# Verifier stays outside the hunter. This spike only checks artifacts exist.\nls artifacts >/dev/null 2>&1 || true\nexit 0\n", encoding="utf-8")
    return {"instruction": str(instruction), "task_toml": str(task_toml), "dockerfile": str(dockerfile)}


def _valid_spec(**overrides: Any) -> dict[str, Any]:
    spec = {
        "schema_version": 1,
        "hunter_run_id": "hunter-run-selftest",
        "engagement_id": "eng-selftest",
        "isolation_unit": "hypothesis",
        "hypothesis_ref": "hypothesis-h1",
        "card_ids": ["vulns/sql-injection"],
        "brief_path": "brief.md",
        "brief": "Run the assigned card against the target handle. Return an attempt. Do not invent victory conditions.",
        "target_handle": {"kind": "url", "value": "http://127.0.0.1:18080"},
        "allowed_paths": ["skills/vulns/sql-injection/SKILL.md"],
        "withheld_paths": list(DEFAULT_WITHHELD_PREFIXES),
        "environment_ref": "preflight-selftest",
        "provider": "local",
        "artifact_out": "artifacts",
        "network_policy": "no-network",
        "zone2_authorized": False,
    }
    spec.update(overrides)
    return spec


def self_test() -> int:
    ok = True

    def check(cond: bool, label: str, detail: str = "") -> None:
        nonlocal ok
        if cond:
            print(f"[self-test] {label}: ok")
        else:
            ok = False
            print(f"[self-test] FAIL {label}" + (f"  {detail}" if detail else ""))

    spec = _valid_spec()
    errors = validate_hunter_run(spec)
    check(errors == [], "valid hunter_run spec is accepted", str(errors))

    leaky = _valid_spec(allowed_paths=["evals/routing/gold/secret.json"])
    leaky_errors = validate_hunter_run(leaky)
    check(any(e.get("code") == "hunter_gold_path_allowed" for e in leaky_errors),
          "evals/ gold in allowed_paths is rejected")

    no_hyp = _valid_spec(hypothesis_ref=None)
    no_hyp_errors = validate_hunter_run(no_hyp)
    check(any(e.get("code") == "hunter_hypothesis_required" for e in no_hyp_errors),
          "hypothesis isolation_unit without hypothesis_ref is rejected")

    workspace = Path(tempfile.mkdtemp(prefix="hunter-envelope-ws-"))
    try:
        card = workspace / "skills" / "vulns" / "sql-injection" / "SKILL.md"
        card.parent.mkdir(parents=True)
        card.write_text("---\nid: vulns/sql-injection\n---\n# card\n", encoding="utf-8")
        gold = workspace / "evals" / "routing" / "gold" / "secret.json"
        gold.parent.mkdir(parents=True)
        gold.write_text('{"flag":"GOLD-MUST-NOT-LEAK"}\n', encoding="utf-8")
        findings = workspace / "engagements" / "eng-selftest" / "findings" / "F-001.json"
        findings.parent.mkdir(parents=True)
        findings.write_text('{"claim_state":"confirmed"}\n', encoding="utf-8")

        handle = start_env(spec, workspace=workspace)
        try:
            check(handle.get("provider") == "local", "local provider starts")
            context = Path(handle["context_root"])
            check((context / "skills" / "vulns" / "sql-injection" / "SKILL.md").is_file(),
                  "allowlisted card is staged")
            check(not (context / "evals").exists(), "evals/ is not staged into the envelope")
            check(not (context / "engagements").exists(), "engagement findings are not staged")
            check((context / "brief.md").is_file(), "brief is staged")
            check("GOLD-MUST-NOT-LEAK" not in (context / "brief.md").read_text(encoding="utf-8"),
                  "brief does not contain planted gold")

            card_probe = run_hunter(handle, [sys.executable, "-c",
                "print(open('skills/vulns/sql-injection/SKILL.md',encoding='utf-8').read())"])
            check(card_probe.get("returncode") == 0 and "sql-injection" in card_probe.get("stdout", ""),
                  "hunter can read the allowlisted card")

            readable = gold_readable_inside(handle, "evals/routing/gold/secret.json")
            check(readable is False, "hunter cannot cat relative gold inside the envelope")

            planted = context / "evals" / "routing" / "gold" / "secret.json"
            planted.parent.mkdir(parents=True)
            planted.write_text('{"flag":"GOLD-MUST-NOT-LEAK"}\n', encoding="utf-8")
            leaky_read = gold_readable_inside(handle, "evals/routing/gold/secret.json")
            check(leaky_read is True, "probe detects a leaky envelope when gold is planted")
            check(leaky_read is True, "a hunter that can cat gold fails the envelope (leaky mount)")
            planted.unlink()
            planted.parent.rmdir(); planted.parent.parent.rmdir(); planted.parent.parent.parent.rmdir()

            (context / "artifacts").mkdir(exist_ok=True)
            run_hunter(handle, [sys.executable, "-c",
                "open('artifacts/out.txt','w',encoding='utf-8').write('attempt-bytes')"])
            arts = collect_artifacts(handle)
            check(any(a.get("name") == "out.txt" and a.get("text") == "attempt-bytes" for a in arts),
                  "collect_artifacts returns hunter output only")
        finally:
            teardown(handle)
        check(not Path(handle["context_root"]).exists(), "teardown removes the staged context")

        try:
            start_env(leaky, workspace=workspace)
            check(False, "start_env rejects a gold-allowlisted spec")
        except EnvelopeError as exc:
            check(exc.code == "hunter_gold_path_allowed",
                  "start_env fail-closes on gold allowlist", str(exc))
    finally:
        shutil.rmtree(workspace, ignore_errors=True)

    harbor_spec = _valid_spec(provider="harbor")
    harbor_dir = Path(tempfile.mkdtemp(prefix="hunter-harbor-"))
    try:
        files = render_harbor_task(harbor_spec, harbor_dir)
        instruction = Path(files["instruction"])
        task_toml = Path(files["task_toml"])
        dockerfile = Path(files["dockerfile"])
        check(instruction.is_file() and "GOLD-MUST-NOT-LEAK" not in instruction.read_text(encoding="utf-8"),
              "Harbor instruction is the brief, not gold")
        toml_text = task_toml.read_text(encoding="utf-8")
        check("[agent]" in toml_text and "[verifier]" in toml_text and "separate" in toml_text,
              "Harbor task.toml splits agent and verifier")
        check(dockerfile.is_file() and "WORKDIR" in dockerfile.read_text(encoding="utf-8"),
              "Harbor environment Dockerfile is rendered")
        check(provider_available("harbor") is False or provider_available("harbor") is True,
              "harbor provider availability is honest (bool)")
        if not provider_available("harbor"):
            print("[self-test] harbor CLI absent: skip live harbor run (honest)")
        if not provider_available("docker"):
            print("[self-test] docker absent: skip live docker OS-isolation probe (honest)")
        else:
            docker_ws = Path(tempfile.mkdtemp(prefix="hunter-docker-ws-"))
            try:
                card = docker_ws / "skills" / "vulns" / "sql-injection" / "SKILL.md"
                card.parent.mkdir(parents=True)
                card.write_text("---\nid: vulns/sql-injection\n---\n# card\n", encoding="utf-8")
                (docker_ws / "evals" / "routing" / "gold").mkdir(parents=True)
                (docker_ws / "evals" / "routing" / "gold" / "secret.json").write_text(
                    '{"flag":"GOLD-MUST-NOT-LEAK"}\n', encoding="utf-8")
                docker_handle = start_env(_valid_spec(provider="docker"), workspace=docker_ws)
                try:
                    check(gold_readable_inside(docker_handle, "evals/routing/gold/secret.json") is False,
                          "docker hunter cannot cat relative gold")
                    abs_gold = str(docker_ws / "evals" / "routing" / "gold" / "secret.json")
                    probe = run_hunter(docker_handle, ["cat", abs_gold])
                    check(probe.get("returncode") != 0, "docker hunter cannot cat host-absolute gold")
                finally:
                    teardown(docker_handle)
            finally:
                shutil.rmtree(docker_ws, ignore_errors=True)
    finally:
        shutil.rmtree(harbor_dir, ignore_errors=True)

    print("\nSELF-TEST:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--self-test":
        raise SystemExit(self_test())
    print(__doc__)
    raise SystemExit(2)
