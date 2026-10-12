#!/usr/bin/env python3
"""Offline end-to-end contract for one-use Go dependency staging.

The fixture creates a disposable signed engagement and a disposable Git source.
Its transport is in-memory. It must never contact a real host or run target code.
Run: python3 tools/dependency-stage-e2e.py --output /tmp/dependency-stage-e2e
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from engagement_records import canonical_json_bytes, sha256_bytes, sha256_file
from engagement_state import read_ledger, reduce_engagement
from operator_signature import operator_challenge_bytes


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "tools/run-engagement.py"
BROKER = f"local-uid-{os.getuid()}:broker"
SESSION = f"session-posix-{os.getuid()}-{os.getsid(0)}"
OPERATOR = "operator-synthetic"
EMPTY_HASH = "sha256:" + hashlib.sha256(b"").hexdigest()
SYNTHETIC_MOD = b"module synthetic\n"
SYNTHETIC_MOD_H1 = "h1:" + base64.b64encode(hashlib.sha256(
    (hashlib.sha256(SYNTHETIC_MOD).hexdigest() + "  go.mod\n").encode()
).digest()).decode()


def utc(offset_seconds: int = 0) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=offset_seconds)).isoformat(
        timespec="seconds"
    ).replace("+00:00", "Z")


def cli(*args: str, env: dict[str, str] | None = None) -> dict:
    result = subprocess.run(
        [sys.executable, str(CLI), *args], cwd=ROOT, env=env,
        capture_output=True, text=True, check=False,
    )
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError((args, result.returncode, result.stdout, result.stderr)) from exc
    if result.returncode:
        raise AssertionError((args, data, result.stderr))
    return data


class FakeTransport:
    """Return exact synthetic responses, without opening any socket."""

    def __init__(self, responses: dict[str, tuple[int, dict[str, str], bytes]]) -> None:
        self.responses = responses
        self.calls: list[str] = []

    def open(self, url: str, timeout: float):
        self.calls.append(url)
        status, headers, body = self.responses[url]
        return status, headers, [body]


def setup(root: Path, *, synthetic_grant: bool = True) -> tuple[Path, Path, Path, Path]:
    key = root / "synthetic-operator-key"
    subprocess.run(
        ["/usr/bin/ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    signers = root / "allowed-signers"
    signers.write_text(f"{OPERATOR} {key.with_suffix('.pub').read_text().strip()}\n")
    source = root / "synthetic-source"
    source.mkdir()
    subprocess.run(["git", "init", "-q", str(source)], check=True)
    (source / "README.md").write_text("synthetic source identity only\n")
    subprocess.run(["git", "-C", str(source), "add", "README.md"], check=True)
    subprocess.run(
        ["git", "-C", str(source), "-c", "user.name=Synthetic", "-c",
         "user.email=synthetic@example.invalid", "commit", "-qm", "synthetic source"],
        check=True,
    )
    engagement = root / "seed" / "synthetic"
    engagement.mkdir(parents=True)
    (engagement / "sandbox").mkdir(mode=0o700)
    scope = engagement / "scope.md"
    scope.write_text(
        "# Signed synthetic scope\n"
        "## Surfaces in scope\n- Synthetic source Git identity only.\n"
        f"- **harness revision required:** `{subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()}`\n"
        "## Benign safe-objective set\n- Offline dependency staging control test.\n"
        "## Escalation ceiling\n- Disposable local synthetic files only.\n"
        "## Impact-demo authorization\n- impact_demo_authorized: `no`\n"
        "## Accounts / fixtures\n- No real host, target, account or asset.\n"
        + ("- Synthetic dependency-stage fixture: `yes`.\n" if synthetic_grant else "")
        +
        "## Authorization\n"
        f"- Operator allowed signers SHA256: {sha256_file(signers)}\n"
        f"- Operator: {OPERATOR}\n- Date: 2026-10-12\n- Signed: [x]\n"
        "- Record kernel: `decision-0006-v2`\n"
    )
    at = utc()
    challenge = operator_challenge_bytes(
        engagement_id=engagement.name, scope_hash=sha256_file(scope), ledger_hash=None,
        operation=f"initialize-engagement:{at}", operator_id=OPERATOR,
    )
    challenge_path = root / "init-challenge.json"
    challenge_path.write_bytes(challenge)
    subprocess.run(
        ["/usr/bin/ssh-keygen", "-q", "-Y", "sign", "-f", str(key), "-n",
         "llm-redteam-harness-operator-v1", str(challenge_path)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    env = {**os.environ, "HARNESS_OPERATOR_SIGNATURE_FILE": str(challenge_path) + ".sig",
           "HARNESS_OPERATOR_ALLOWED_SIGNERS_FILE": str(signers)}
    cli("init", "--engagement", str(engagement), "--recorded-at", at, env=env)
    git = shutil.which("git")
    assert git is not None
    head = subprocess.check_output([git, "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    cli(
        "preflight", "--engagement", str(engagement), "--preflight-id", "preflight-synthetic-git",
        "--mode", "git", "--target", str(source), "--expected-identity", head,
        "--runtime", str(Path(git).resolve()),
        "--reproduction-argv", json.dumps([str(Path(git).resolve()), "-C", str(source), "status", "--short"]),
        "--actor-role", "broker", "--actor-id", BROKER, "--session-id", SESSION,
        "--recorded-at", utc(),
    )
    assert reduce_engagement(engagement)["active_environment_ref"] is not None
    return engagement, source, key, signers


def approve(engagement: Path, source: Path, key: Path, signers: Path, *,
            name: str, resolution: str = "approved", requests: list[dict] | None = None,
            max_requests: int = 2, max_bytes: int = 64, deadline_seconds: int = 30,
            harness_override: str | None = None, environment_override: str | None = None,
            session_override: str | None = None) -> tuple[str, dict]:
    state = reduce_engagement(engagement)
    head = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    action = {
        "schema_version": 1, "action_kind": "stage-go-dependencies", "lane_id": "lane-dependency-stage",
        "engagement_id": state["engagement_id"], "executor_id": BROKER,
        "session_id": session_override or SESSION,
        "operator_id": OPERATOR, "scope_hash": state["scope_hash"],
        "environment_ref": environment_override or state["active_environment_ref"], "source_repo": str(source),
        "source_commit": head, "harness_commit": subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip() if harness_override is None else harness_override,
        "capability_sha256": hashlib.sha256((ROOT / "tools/dependency_stage.py").read_bytes()).hexdigest(),
        "go_version": "go1.23.0", "destination": "sandbox/dependency-retrieval",
        "max_requests": max_requests, "max_total_bytes": max_bytes,
        "deadline_seconds": deadline_seconds,
        "synthetic_fixture": True,
        "requests": requests or [{
            "url": "https://proxy.golang.org/example.invalid/synthetic/@v/v1.0.0.mod", "redirects": [],
            "kind": "module_mod", "max_bytes": 64,
            "sha256": hashlib.sha256(SYNTHETIC_MOD).hexdigest(), "go_h1": SYNTHETIC_MOD_H1,
        }],
    }
    request_id = f"request-{name}"
    action_path = engagement.parent / f"{name}.action.json"
    action_path.write_bytes(canonical_json_bytes(action))
    cli(
        "request-authority", "--engagement", str(engagement), "--request-id", request_id,
        "--action-kind", "stage-go-dependencies", "--action-file", str(action_path),
        "--lane-id", action["lane_id"], "--actor-role", "broker", "--actor-id", BROKER,
        "--session-id", SESSION, "--recorded-at", utc(), "--expires-at", utc(3600),
        "--reason", "Synthetic offline dependency-staging fixture only.",
    )
    if resolution == "pending":
        return request_id, action
    events = read_ledger(engagement, "event")
    recorded_at = utc()
    operation = (
        f"resolve-authority:{request_id}:{sha256_bytes(canonical_json_bytes(action))}:"
        f"{resolution}:{recorded_at}"
    )
    challenge = operator_challenge_bytes(
        engagement_id=engagement.name, scope_hash=state["scope_hash"],
        ledger_hash=events[-1]["record_hash"], operation=operation, operator_id=OPERATOR,
    )
    challenge_path = engagement.parent / f"{name}.challenge.json"
    challenge_path.write_bytes(challenge)
    subprocess.run(
        ["/usr/bin/ssh-keygen", "-q", "-Y", "sign", "-f", str(key), "-n",
         "llm-redteam-harness-operator-v1", str(challenge_path)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    env = {**os.environ, "HARNESS_OPERATOR_SIGNATURE_FILE": str(challenge_path) + ".sig",
           "HARNESS_OPERATOR_ALLOWED_SIGNERS_FILE": str(signers)}
    cli(
        "resolve-authority", "--engagement", str(engagement), "--request-id", request_id,
        "--resolution", resolution, "--operator-id", OPERATOR, "--session-id", SESSION,
        "--recorded-at", recorded_at, "--reason", "Synthetic fixture resolution.", env=env,
    )
    return request_id, action


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = (args.output or Path(tempfile.mkdtemp(prefix="dependency-stage-e2e-results-"))).resolve()
    output.mkdir(parents=True, exist_ok=False) if args.output else None
    # This import is intentionally after fixture creation in the source timeline.
    # The E2E file must exist before the implementation module is added.
    import dependency_stage

    results: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix="dependency-stage-e2e-") as temporary:
        root = Path(temporary)
        seed, source, key, signers = setup(root)
        no_grant_root = root / "no-grant-root"
        no_grant_root.mkdir()
        no_grant_seed, no_grant_source, no_grant_key, no_grant_signers = setup(
            no_grant_root, synthetic_grant=False)

        def case(name: str, *, resolution: str = "approved", action_changes: dict | None = None,
                 scope_change: str | None = None, source_change: bool = False,
                 mutate_approved_action: bool = False, now_offset: int = 0,
                 responses: dict | None = None, expected: str, repeat: bool = False,
                 clock=None, no_grant: bool = False, expected_bytes: int | None = None) -> None:
            selected_seed, selected_source, selected_key, selected_signers = (
                (no_grant_seed, no_grant_source, no_grant_key, no_grant_signers)
                if no_grant else (seed, source, key, signers))
            engagement = root / name / "synthetic"
            engagement.parent.mkdir()
            shutil.copytree(selected_seed, engagement)
            request_id, action = approve(engagement, selected_source, selected_key, selected_signers, name=name,
                                         resolution=resolution, **(action_changes or {}))
            if scope_change == "absent":
                (engagement / "scope.md").unlink()
            elif scope_change == "changed":
                (engagement / "scope.md").write_text("changed synthetic scope\n")
            if mutate_approved_action:
                (engagement / "authority/requests" / f"{request_id}.action.json").write_text(
                    '{"changed":"synthetic action drift"}\n'
                )
            if source_change:
                (selected_source / "README.md").write_text("synthetic source drift\n")
            transport = FakeTransport(responses or {action["requests"][0]["url"]: (
                200, {}, b"module synthetic\n")})
            before = len(read_ledger(engagement, "event"))
            try:
                result = dependency_stage.run_stage(
                    engagement, request_id, BROKER, SESSION, transport=transport,
                    now=datetime.now(timezone.utc) + timedelta(seconds=now_offset),
                    monotonic=clock or (lambda: 0.0),
                )
                code = "ok"
            except dependency_stage.StageError as exc:
                result = None
                code = exc.code
                detail = str(exc)
            finally:
                if source_change:
                    (selected_source / "README.md").write_text("synthetic source identity only\n")
            assert code == expected, (name, code, expected, locals().get("detail"))
            if code != "ok" and expected in {
                "scope_missing", "scope_grant_missing", "scope_drift", "authority_not_current",
                "action_binding_mismatch", "scope_harness_mismatch", "source_identity_mismatch",
            }:
                assert not transport.calls, (name, transport.calls)
                assert len(read_ledger(engagement, "event")) == before
            if code != "ok" and len(read_ledger(engagement, "event")) > before:
                manifest_path = engagement / "sandbox/dependency-retrieval" / request_id / "manifest.json"
                manifest = json.loads(manifest_path.read_text())
                assert stat.S_IMODE(manifest_path.stat().st_mode) == 0o600
                assert manifest["result"] == "stopped" and manifest["stop_reason"] == code
                if expected_bytes is not None:
                    assert manifest["response_bytes"] == expected_bytes
                assert len(read_ledger(engagement, "event")) == before + 2
            if repeat:
                try:
                    dependency_stage.run_stage(
                        engagement, request_id, BROKER, SESSION, transport=transport,
                        now=datetime.now(timezone.utc), monotonic=lambda: 0.0,
                    )
                except dependency_stage.StageError as exc:
                    assert exc.code == "action_already_spent", exc.code
                else:
                    raise AssertionError("duplicate run succeeded")
                manifest_path = (Path(result["manifest_path"]) if result is not None else
                                 engagement / "sandbox/dependency-retrieval" / request_id / "manifest.json")
                manifest = json.loads(manifest_path.read_text())
                assert stat.S_IMODE(manifest_path.stat().st_mode) == 0o600
                assert "proxy.golang.org" in manifest_path.read_text()
                assert "example.invalid/synthetic" not in manifest_path.read_text()
                assert manifest["request_count"] == 1
                assert any(e["event_type"] == "dependency.stage_spent" for e in read_ledger(engagement, "event"))
            results.append({"case": name, "result": code, "requests": len(transport.calls),
                            "event_delta": len(read_ledger(engagement, "event")) - before})

        case("missing-scope", scope_change="absent", expected="scope_missing")
        case("missing-grant", no_grant=True, expected="scope_grant_missing")
        case("changed-scope", scope_change="changed", expected="scope_drift")
        case("pending", resolution="pending", expected="authority_not_current")
        case("rejected", resolution="rejected", expected="authority_not_current")
        case("expired", now_offset=7200, expected="authority_not_current")
        case("changed-action", mutate_approved_action=True, expected="action_binding_mismatch")
        case("environment-binding", action_changes={"environment_override": "wrong-environment"},
             expected="action_binding_mismatch")
        case("session-binding", action_changes={"session_override": "wrong-session"},
             expected="action_binding_mismatch")
        case("scope-harness-pin", action_changes={"harness_override": "0" * 40},
             expected="scope_harness_mismatch")
        case("source-drift", source_change=True, expected="source_identity_mismatch")
        case("success-and-repeat", expected="ok", repeat=True)
        case("unlisted-redirect", responses={
            "https://proxy.golang.org/example.invalid/synthetic/@v/v1.0.0.mod": (
                302, {"Location": "https://unlisted.invalid/synthetic"}, b"redirect-body")},
             expected="redirect_not_admitted", repeat=True, expected_bytes=len(b"redirect-body"))
        case("raw-checksum", responses={
            "https://proxy.golang.org/example.invalid/synthetic/@v/v1.0.0.mod": (
                200, {}, b"different synthetic module\n")}, expected="checksum_mismatch")
        second_url = "https://proxy.golang.org/example.invalid/synthetic/@v/v1.0.0.info"
        two_requests = [
            {"url": "https://proxy.golang.org/example.invalid/synthetic/@v/v1.0.0.mod",
             "redirects": [], "kind": "module_mod", "max_bytes": 64,
             "sha256": hashlib.sha256(SYNTHETIC_MOD).hexdigest(), "go_h1": SYNTHETIC_MOD_H1},
            {"url": second_url, "redirects": [], "kind": "module_info", "max_bytes": 64,
             "sha256": hashlib.sha256(b"{}").hexdigest()},
        ]
        case("request-limit", action_changes={"max_requests": 1, "requests": two_requests},
             responses={two_requests[0]["url"]: (200, {}, b"module synthetic\n"),
                        second_url: (200, {}, b"{}")}, expected="request_limit")
        case("byte-limit", action_changes={"max_bytes": 2}, expected="byte_limit")
        case("object-limit", action_changes={"requests": [
            {"url": "https://proxy.golang.org/example.invalid/synthetic/@v/v1.0.0.mod",
             "redirects": [], "kind": "module_mod", "max_bytes": 2,
             "sha256": hashlib.sha256(SYNTHETIC_MOD).hexdigest(), "go_h1": SYNTHETIC_MOD_H1}]},
             expected="object_limit")
        ticks = iter([0.0, 0.0, 31.0, 31.0])
        case("deadline", clock=lambda: next(ticks, 31.0), expected="deadline_exceeded")
        invalid_archive = root / "invalid-go.tar.gz"
        with tarfile.open(invalid_archive, "w:gz") as archive:
            entry = tarfile.TarInfo("go/../../escape")
            entry.size = 1
            archive.addfile(entry, io.BytesIO(b"x"))
        (root / "invalid-go-destination").mkdir()
        try:
            dependency_stage._safe_go_archive(invalid_archive, root / "invalid-go-destination")
        except dependency_stage.StageError as exc:
            assert exc.code == "archive_path_invalid"
        else:
            raise AssertionError("archive path escape was accepted")
        results.append({"case": "archive-path-escape", "result": "archive_path_invalid",
                        "requests": 0, "event_delta": 0})
        mod_destination = root / "bad-mod-h1"
        (mod_destination / "downloads").mkdir(parents=True)
        (mod_destination / "downloads/000-module_mod").write_bytes(SYNTHETIC_MOD)
        bad_mod_action = {"requests": [{"kind": "module_mod", "go_h1": "h1:" + "A" * 43 + "=",
                                        "url": "https://proxy.golang.org/example.invalid/synthetic/@v/v1.0.0.mod"}]}
        try:
            dependency_stage._materialize_offline_cache(
                bad_mod_action, mod_destination,
                [{"status": 200, "relative_file": "downloads/000-module_mod"}])
        except dependency_stage.StageError as exc:
            assert exc.code == "go_h1_mismatch"
        else:
            raise AssertionError("module H1 mismatch was accepted")
        results.append({"case": "module-h1-mismatch", "result": "go_h1_mismatch",
                        "requests": 0, "event_delta": 0})
        release_data = json.dumps([{"version": "go1.23.0", "files": [{
            "filename": "go1.23.0.linux-amd64.tar.gz", "sha256": "f" * 64,
            "size": 10}]}]).encode()
        metadata_url = "https://go.dev/dl/?mode=json&include=all"
        archive_url = "https://go.dev/dl/go1.23.0.linux-amd64.tar.gz"
        metadata_action = {"synthetic_fixture": False, "deadline_seconds": 30,
                           "max_requests": 2, "max_total_bytes": 4096,
                           "requests": [
                               {"url": metadata_url, "redirects": [], "kind": "release_metadata",
                                "max_bytes": 4096, "sha256": hashlib.sha256(release_data).hexdigest()},
                               {"url": archive_url, "redirects": [], "kind": "go_archive",
                                "max_bytes": 100, "sha256": "0" * 64}]}
        metadata_transport = FakeTransport({metadata_url: (200, {}, release_data)})
        metadata_destination = root / "official-metadata-check"
        metadata_destination.mkdir()
        metadata_meter = {"responses": [], "request_count": 0, "response_bytes": 0}
        try:
            dependency_stage._download(metadata_action, metadata_destination, metadata_transport,
                                       lambda: 0.0, lambda: None, metadata_meter)
        except dependency_stage.StageError as exc:
            assert exc.code == "official_checksum_mismatch"
        else:
            raise AssertionError("archive GET was admitted with mismatched official metadata")
        assert metadata_transport.calls == [metadata_url]
        results.append({"case": "official-archive-checksum", "result": "official_checksum_mismatch",
                        "requests": 1, "event_delta": 0})
        assert dependency_stage.probe_offline_socket_denial(), "offline child could open a socket"
        results.append({"case": "offline-socket-denial", "result": "ok", "requests": 0,
                        "event_delta": 0})
    output.joinpath("results.json").write_bytes(canonical_json_bytes({"cases": results}))
    print(json.dumps({"passed": len(results), "failed": 0, "output": str(output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
