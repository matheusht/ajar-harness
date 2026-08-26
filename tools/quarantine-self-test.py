#!/usr/bin/env python3
"""Hermetic external-behavior regression suite for engagement quarantine."""

from __future__ import annotations

import argparse
import io
import json
import os
import runpy
import shutil
import socket
import subprocess
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

import ablation
import disposition_ledger
import engagement_quarantine
import kb
import ledger_health
import reachability_corpus
from engagement_quarantine import (
    MARKER_RELATIVE,
    canonical_marker,
    inspect_quarantine,
    quarantined_ancestor,
    require_safe_offline_output,
)
from engagement_records import RecordError, canonical_json_bytes, legacy_finding_inventory, sha256_file
from engagement_state import (
    append_ledger_record,
    base_event,
    compute_record_hash,
    initialize_engagement,
    read_ledger,
    reduce_engagement,
    repair_ledger_tail,
)


TOOLS = Path(__file__).resolve().parent
RUN_ENGAGEMENT = TOOLS / "run-engagement.py"
MARKER_SECRET = "diagnostic-secret-sentinel-should-never-echo"
INVALID_SECRET = "invalid-event-secret-sentinel-should-never-echo"


def _run(script: Path, *argv: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, str(script), *map(str, argv)]
    try:
        return subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            timeout=30,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(command, 124, "", "sanitized-timeout")


def _run_engagement(*argv: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return _run(RUN_ENGAGEMENT, *argv, env=env)


def _payload(result: subprocess.CompletedProcess[str]) -> dict:
    try:
        value = json.loads(result.stdout)
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        return {}


def _error_code(result: subprocess.CompletedProcess[str]) -> str | None:
    return _payload(result).get("error", {}).get("code")


def _scope(allowed_signers_digest: str) -> str:
    return f"""# Scope - synthetic quarantine test

## Surfaces in scope
- Local fixture only.
## Benign safe-objective set
- Deterministic quarantine test.
## Escalation ceiling
- Local records only.
## Impact-demo authorization
- impact_demo_authorized: `no`
## Accounts / fixtures
- None.
## Authorization
- Operator allowed signers SHA256: {allowed_signers_digest}
- Operator: fixture-operator
- Date: 2026-08-23
- Signed: [x]
- Record kernel: `decision-0006-v1`
"""


def _make_engagement(path: Path, allowed_signers_digest: str, recorded_at: str) -> Path:
    path.mkdir(parents=True)
    path.joinpath("scope.md").write_text(_scope(allowed_signers_digest), encoding="utf-8")
    initialize_engagement(path, recorded_at)
    return path


def _challenge_env(
    result: subprocess.CompletedProcess[str],
    *,
    label: str,
    root: Path,
    key: Path,
    allowed_signers: Path,
) -> dict[str, str]:
    prefix = "Operator signature challenge:\n"
    if prefix not in result.stderr:
        raise AssertionError("operator challenge was not emitted")
    challenge_line = result.stderr.split(prefix, 1)[1].splitlines()[0] + "\n"
    json.loads(challenge_line)
    challenge = root / f"{label}.json"
    challenge.write_text(challenge_line, encoding="utf-8")
    subprocess.run(
        [
            "/usr/bin/ssh-keygen", "-q", "-Y", "sign", "-f", str(key),
            "-n", "llm-redteam-harness-operator-v1", str(challenge),
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
    )
    return {
        **os.environ,
        "HARNESS_OPERATOR_SIGNATURE_FILE": str(challenge) + ".sig",
        "HARNESS_OPERATOR_ALLOWED_SIGNERS_FILE": str(allowed_signers),
    }


def _quarantine_args(engagement: Path, recorded_at: str) -> tuple[str, ...]:
    return (
        "quarantine-ledger", "--engagement", str(engagement),
        "--operator-id", "fixture-operator",
        "--reason", "operator-integrity-review",
        "--recorded-at", recorded_at,
    )


def _clear_args(engagement: Path, recorded_at: str) -> tuple[str, ...]:
    return (
        "clear-ledger-quarantine", "--engagement", str(engagement),
        "--operator-id", "fixture-operator",
        "--reason", "underlying-ledger-verified-healthy",
        "--recorded-at", recorded_at,
    )


def _tree_bytes(engagement: Path, *, omit_marker: bool = False) -> dict[str, bytes]:
    result: dict[str, bytes] = {}
    for path in sorted(engagement.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(engagement).as_posix()
        if omit_marker and relative == MARKER_RELATIVE:
            continue
        result[relative] = path.read_bytes()
    return result


def _fixture_marker() -> bytes:
    return canonical_marker(
        {
            "schema_version": 1,
            "status": "quarantined",
            "operator_id": "fixture-operator",
            "reason": "operator-integrity-review",
            "recorded_at": "2026-08-23T00:00:00Z",
            "authority_challenge_digest": "sha256:" + "1" * 64,
            "record_fingerprint": "sha256:" + "2" * 64,
        }
    )


def _install_fixture_marker(engagement: Path) -> Path:
    marker = engagement / MARKER_RELATIVE
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_bytes(_fixture_marker())
    return marker


def _sign_and_run(
    argv: tuple[str, ...],
    *,
    label: str,
    root: Path,
    key: Path,
    allowed_signers: Path,
) -> tuple[subprocess.CompletedProcess[str], subprocess.CompletedProcess[str]]:
    unsigned = _run_engagement(*argv)
    env = _challenge_env(
        unsigned, label=label, root=root, key=key, allowed_signers=allowed_signers
    )
    return unsigned, _run_engagement(*argv, env=env)


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    def check(label: str, condition: bool, detail: str = "") -> None:
        checks.append((label, bool(condition), detail))

    with tempfile.TemporaryDirectory(prefix="quarantine-self-test-") as temporary:
        root = Path(temporary).resolve()
        key = root / "operator-ed25519"
        subprocess.run(
            ["/usr/bin/ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )
        public_parts = key.with_suffix(".pub").read_text().split()
        allowed_signers = root / "allowed-signers"
        allowed_signers.write_text(
            f"fixture-operator {public_parts[0]} {public_parts[1]}\n", encoding="utf-8"
        )
        allowed_digest = sha256_file(allowed_signers)

        scope_independent_results: list[bool] = []
        for scope_kind in ("missing", "symlink", "directory"):
            scope_root = root / f"scope-independent-{scope_kind}"
            scope_root.mkdir()
            marker = _install_fixture_marker(scope_root)
            if scope_kind == "symlink":
                scope_root.joinpath("scope.md").symlink_to(root / "missing-scope-target")
            elif scope_kind == "directory":
                scope_root.joinpath("scope.md").mkdir()
            nested = scope_root / "nested" / "input.json"
            link = root / f"scope-independent-link-{scope_kind}"
            link.symlink_to(scope_root, target_is_directory=True)
            exact_blocked = nested_blocked = False
            try:
                require_safe_offline_output(marker)
            except ValueError:
                exact_blocked = True
            try:
                require_safe_offline_output(nested)
            except ValueError:
                nested_blocked = True
            scope_independent_results.append(
                inspect_quarantine(scope_root)["quarantined"]
                and quarantined_ancestor(nested)
                and quarantined_ancestor(link / "nested" / "input.json")
                and exact_blocked
                and nested_blocked
            )
        check(
            "marker ancestry and control reservation do not depend on mutable scope bytes",
            all(scope_independent_results),
            repr(scope_independent_results),
        )

        engagement = _make_engagement(
            root / "synthetic-quarantine-source", allowed_digest, "2026-08-23T00:00:00Z"
        )
        engagement.joinpath("unproven", "F-SYNTHETIC").mkdir(parents=True)
        engagement.joinpath("findings", "F-PROMOTED-SYNTHETIC").mkdir(parents=True)
        lifecycle_before = sorted(
            path.relative_to(engagement).as_posix() for path in engagement.rglob("*")
        )

        healthy = _run_engagement("ledger-health", "--engagement", str(engagement))
        healthy_resume = _run_engagement("check-resume", "--engagement", str(engagement))
        check(
            "health probe distinguishes a healthy ledger",
            healthy.returncode == 0 and _payload(healthy).get("status") == "healthy",
            healthy.stdout + healthy.stderr,
        )
        check(
            "fresh generated views remain current through a bound check-resume",
            healthy_resume.returncode == 0
            and _payload(healthy_resume).get("ok") is True,
            healthy_resume.stdout + healthy_resume.stderr,
        )

        create_args = _quarantine_args(engagement, "2026-08-23T00:01:00Z")
        unsigned_create = _run_engagement(*create_args)
        marker_path = engagement / MARKER_RELATIVE
        check(
            "unsigned marker creation is denied before marker mutation",
            unsigned_create.returncode != 0
            and _error_code(unsigned_create) == "operator_signature_required"
            and not marker_path.exists(),
            unsigned_create.stdout + unsigned_create.stderr,
        )
        create_env = _challenge_env(
            unsigned_create,
            label="concurrent-create",
            root=root,
            key=key,
            allowed_signers=allowed_signers,
        )
        processes = [
            subprocess.Popen(
                [sys.executable, str(RUN_ENGAGEMENT), *create_args],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=create_env,
            )
            for _ in range(2)
        ]
        create_results = []
        for process in processes:
            stdout, stderr = process.communicate(timeout=20)
            create_results.append((process.returncode, stdout, stderr))
        create_payloads = []
        for _, stdout, _ in create_results:
            try:
                create_payloads.append(json.loads(stdout))
            except json.JSONDecodeError:
                create_payloads.append({})
        check(
            "signed concurrent create publishes once and exact retry is idempotent",
            all(code == 0 for code, _, _ in create_results)
            and sorted(payload.get("created") for payload in create_payloads) == [False, True]
            and inspect_quarantine(engagement)["marker_status"] == "valid",
            repr(create_results),
        )

        marked_health = _run_engagement("ledger-health", "--engagement", str(engagement))
        marked_diagnostics = marked_health.stdout + marked_health.stderr
        check(
            "marker takes health precedence and diagnostics disclose no path or marker content",
            marked_health.returncode == 0
            and _payload(marked_health).get("status") == "quarantined"
            and _payload(marked_health).get("engagement_id") == engagement.name
            and _payload(marked_health).get("reducible") is False
            and _payload(marked_health).get("event_count") is None
            and _payload(marked_health).get("ledger_hash") is None
            and "operator-integrity-review" not in marked_diagnostics,
            marked_diagnostics,
        )

        original_inspect = ledger_health.inspect_quarantine
        original_reduce = ledger_health.reduce_engagement
        try:
            inspections = iter((
                {"quarantined": False},
                {"quarantined": True},
            ))
            ledger_health.inspect_quarantine = lambda _engagement: next(inspections)
            ledger_health.reduce_engagement = lambda _engagement: {
                "engagement_id": engagement.name,
                "event_count": 1,
                "ledger_hash": "sha256:" + "0" * 64,
            }
            final_inspection_wins = ledger_health.probe_ledger_health(engagement)
            ledger_health.inspect_quarantine = lambda _engagement: {"quarantined": False}
            def quarantine_during_reduce(_engagement: Path) -> dict:
                raise RecordError("engagement_quarantined", "sanitized")
            ledger_health.reduce_engagement = quarantine_during_reduce
            reducer_guard_wins = ledger_health.probe_ledger_health(engagement)
        finally:
            ledger_health.inspect_quarantine = original_inspect
            ledger_health.reduce_engagement = original_reduce
        check(
            "health probe preserves quarantine precedence at both reducer interleavings",
            final_inspection_wins.get("status") == "quarantined"
            and reducer_guard_wins.get("status") == "quarantined"
            and final_inspection_wins.get("engagement_id") == engagement.name
            and reducer_guard_wins.get("engagement_id") == engagement.name,
            repr((final_inspection_wins, reducer_guard_wins)),
        )

        before_refusals = _tree_bytes(engagement)
        direct_codes: list[str] = []
        for operation in (
            lambda: reduce_engagement(engagement),
            lambda: append_ledger_record(engagement, "event", {}),
            lambda: initialize_engagement(engagement, "2026-08-23T00:02:00Z"),
            lambda: repair_ledger_tail(
                engagement,
                "event",
                "fixture-operator",
                "synthetic repair attempt",
                "2026-08-23T00:02:00Z",
            ),
        ):
            try:
                operation()
                direct_codes.append("accepted")
            except RecordError as exc:
                direct_codes.append(exc.code)
        reduce_cli = _run_engagement("reduce", "--engagement", str(engagement))
        render_cli = _run_engagement("render", "--engagement", str(engagement))
        check(
            "reducer, append, init, repair, render refuse with every byte unchanged",
            direct_codes == ["engagement_quarantined"] * 4
            and _error_code(reduce_cli) == "engagement_quarantined"
            and _error_code(render_cli) == "engagement_quarantined"
            and _tree_bytes(engagement) == before_refusals,
            f"codes={direct_codes}; reduce={reduce_cli.stdout}; render={render_cli.stdout}",
        )

        copied = root / "copied-quarantined-directory"
        shutil.copytree(engagement, copied)
        copied_health = _run_engagement("ledger-health", "--engagement", str(copied))
        copied_reduce = _run_engagement("reduce", "--engagement", str(copied))
        check(
            "copying the whole directory preserves quarantine and write refusal",
            _payload(copied_health).get("status") == "quarantined"
            and _error_code(copied_reduce) == "engagement_quarantined",
            copied_health.stdout + copied_health.stderr + copied_reduce.stdout + copied_reduce.stderr,
        )

        promote = _run(
            TOOLS / "finding_lifecycle.py",
            "promote", str(engagement / "unproven" / "F-SYNTHETIC"),
            "--engagement", str(engagement), "--actor", "fixture-orchestrator", "--json",
        )
        demote = _run(
            TOOLS / "finding_lifecycle.py",
            "demote", "F-PROMOTED-SYNTHETIC",
            "--engagement", str(engagement), "--actor", "fixture-reviewer",
            "--reason", "synthetic quarantine check",
        )
        inferred_gates = _run(
            TOOLS / "finding_lifecycle.py",
            "gates", str(engagement / "unproven" / "F-SYNTHETIC"), "--json",
        )
        lifecycle_after = sorted(
            path.relative_to(engagement).as_posix() for path in engagement.rglob("*")
        )
        lifecycle_output = (
            promote.stdout + promote.stderr + demote.stdout + demote.stderr
            + inferred_gates.stdout + inferred_gates.stderr
        )
        check(
            "finding promotion and demotion refuse before move or lifecycle log",
            promote.returncode != 0
            and demote.returncode != 0
            and inferred_gates.returncode != 0
            and any(row.get("gate") == "GQ" for row in _payload(inferred_gates).get("gates", []))
            and set(lifecycle_after) == set(lifecycle_before) | {
                "legacy/quarantine", "legacy/quarantine/ledger-quarantined.json"
            }
            and str(engagement) not in lifecycle_output,
            lifecycle_output,
        )

        gate_audit = _run(
            TOOLS / "gate_block_audit.py", "--engagement", str(engagement), "--json"
        )
        q02 = _run(TOOLS / "q02_compare.py", "measure", "--engagement", str(engagement))
        adjudication = _run(
            TOOLS / "adjudication_audit.py", str(engagement / "reviews"), "--json"
        )
        sensor_output = (
            gate_audit.stdout + gate_audit.stderr + q02.stdout + q02.stderr
            + adjudication.stdout + adjudication.stderr
        )
        check(
            "raw-read measurement tools fail closed on a quarantined engagement",
            gate_audit.returncode != 0
            and q02.returncode != 0
            and adjudication.returncode != 0
            and MARKER_SECRET not in sensor_output
            and str(engagement) not in sensor_output,
            sensor_output,
        )

        disposition_before = engagement.joinpath("dispositions.jsonl").read_bytes() if engagement.joinpath("dispositions.jsonl").exists() else None
        disposition = _run(
            TOOLS / "disposition_ledger.py",
            "record", "--engagement", str(engagement), "--finding", "F-SYNTHETIC",
            "--program", "fixture-program", "--our", "low", "--outcome", "pending",
        )
        disposition_after = engagement.joinpath("dispositions.jsonl").read_bytes() if engagement.joinpath("dispositions.jsonl").exists() else None
        check(
            "disposition recording refuses before append",
            disposition.returncode != 0
            and disposition_before == disposition_after
            and str(engagement) not in disposition.stdout + disposition.stderr,
            disposition.stdout + disposition.stderr,
        )

        kb_path = root / "portable-kb.jsonl"
        entry_path = root / "kb-entry.json"
        entry_path.write_bytes(canonical_json_bytes(kb._loser()))
        kb_blocked = _run(
            TOOLS / "kb.py", "add", "--kb", str(kb_path), "--file", str(entry_path),
            "--no-fixture", "--source-engagement", str(engagement),
        )
        kb_bytes_after_block = kb_path.read_bytes() if kb_path.exists() else b""
        kb_synthetic = _run(
            TOOLS / "kb.py", "add", "--kb", str(kb_path), "--file", str(entry_path),
            "--no-fixture", "--source-kind", "synthetic",
        )
        portable_kb = kb_path.read_bytes() if kb_path.exists() else b""
        check(
            "KB promotion rejects quarantined engagement source and keeps explicit synthetic mode",
            kb_blocked.returncode != 0
            and kb_bytes_after_block == b""
            and kb_synthetic.returncode == 0
            and engagement.name.encode() not in portable_kb
            and str(engagement).encode() not in portable_kb,
            kb_blocked.stdout + kb_blocked.stderr + kb_synthetic.stdout + kb_synthetic.stderr,
        )

        kb_private_identity = "E-PRIVATE-KB-IDENTITY-SENTINEL"
        kb_local_source = _make_engagement(
            root / "kb-local-source", allowed_digest, "2026-08-23T00:03:30Z"
        )
        kb_local_path = root / "portable-kb-local.jsonl"
        kb_identity_entry = {
            **kb._loser(),
            "id": "KB-20260823-private-identity",
            "engagement": kb_private_identity,
        }
        kb_identity_entry_path = root / "kb-private-identity-entry.json"
        kb_identity_entry_path.write_bytes(canonical_json_bytes(kb_identity_entry))
        kb_identity_result = _run(
            TOOLS / "kb.py", "add",
            "--kb", str(kb_local_path),
            "--file", str(kb_identity_entry_path),
            "--no-fixture",
            "--source-engagement", str(kb_local_source),
        )
        kb_path_entry = {
            **kb._loser(),
            "id": "KB-20260823-private-fixture",
            "ablation_fixture": f"engagements/{kb_private_identity}/fixture.json",
        }
        kb_path_entry_path = root / "kb-private-path-entry.json"
        kb_path_entry_path.write_bytes(canonical_json_bytes(kb_path_entry))
        kb_path_result = _run(
            TOOLS / "kb.py", "add",
            "--kb", str(kb_local_path),
            "--file", str(kb_path_entry_path),
            "--no-fixture",
            "--source-engagement", str(kb_local_source),
        )
        kb_local_bytes = kb_local_path.read_bytes() if kb_local_path.exists() else b""
        kb_local_diagnostics = (
            kb_identity_result.stdout + kb_identity_result.stderr
            + kb_path_result.stdout + kb_path_result.stderr
        )
        check(
            "local-source KB admission rejects explicit identity and unverified path provenance",
            kb_identity_result.returncode != 0
            and kb_path_result.returncode != 0
            and kb_local_bytes == b""
            and kb_private_identity not in kb_local_diagnostics
            and str(kb_local_source) not in kb_local_diagnostics,
            kb_local_diagnostics,
        )

        kb_aba_source = _make_engagement(
            root / "kb-aba-source", allowed_digest, "2026-08-23T00:04:00Z"
        )
        _install_fixture_marker(kb_aba_source)
        kb_aba_replacement = _make_engagement(
            root / "kb-aba-replacement", allowed_digest, "2026-08-23T00:04:01Z"
        )
        kb_aba_moved = root / "kb-aba-original-moved"
        kb_aba_path = root / "portable-kb-aba.jsonl"
        original_kb_probe = kb.probe_ledger_health

        def swap_path_during_kb_probe(source_path: Path) -> dict:
            kb_aba_source.rename(kb_aba_moved)
            kb_aba_replacement.rename(kb_aba_source)
            try:
                return original_kb_probe(source_path)
            finally:
                kb_aba_source.rename(kb_aba_replacement)
                kb_aba_moved.rename(kb_aba_source)

        kb.probe_ledger_health = swap_path_during_kb_probe
        try:
            with redirect_stdout(io.StringIO()) as kb_aba_output:
                kb_aba_result = kb.cmd_add(
                    SimpleNamespace(
                        source_engagement=str(kb_aba_source),
                        source_kind=None,
                        file=str(entry_path),
                        kb=str(kb_aba_path),
                        fixture=None,
                        no_fixture=True,
                    )
                )
        finally:
            kb.probe_ledger_health = original_kb_probe
        check(
            "KB source authorization is inode-bound across a pathname ABA swap",
            kb_aba_result != 0
            and (not kb_aba_path.exists() or kb_aba_path.read_bytes() == b"")
            and "kb-aba" not in kb_aba_output.getvalue(),
            kb_aba_output.getvalue(),
        )

        measurement_root = root / "measurement-root"
        good = measurement_root / "engagements" / "admissible-fixture"
        bad = measurement_root / "engagements" / "quarantined-fixture"
        for candidate in (good, bad):
            finding = candidate / "findings" / "F-ONE" / "finding.json"
            finding.parent.mkdir(parents=True)
            finding.write_text(
                json.dumps({"source": "fixture input", "sink": "fixture output"}) + "\n",
                encoding="utf-8",
            )
            candidate.joinpath("dispositions.jsonl").write_text(
                json.dumps(
                    {
                        "engagement": candidate.name,
                        "finding_ref": "F-ONE",
                        "our_severity": "low",
                        "their_severity": "low",
                        "outcome": "accepted",
                    }
                ) + "\n",
                encoding="utf-8",
            )
            memory = candidate / "memory" / "memory-disposition-one.json"
            memory.parent.mkdir()
            memory.write_text(
                json.dumps({"disposition_id": f"disp-{candidate.name}", "disposition": "promote"}) + "\n",
                encoding="utf-8",
            )
        _install_fixture_marker(bad)
        reach_rows = reachability_corpus.scan(measurement_root)
        disposition_rows = disposition_ledger.load_all(measurement_root / "engagements")
        promoted_rows = ablation.promote_dispositions(measurement_root)
        legacy_rows = legacy_finding_inventory(measurement_root)
        migration_module = runpy.run_path(str(TOOLS / "migrate-decision5.py"))
        migration = migration_module["inventory"](measurement_root)
        check(
            "corpus, disposition, ablation, legacy, and migration measurements exclude marked sources",
            reach_rows
            and {row["engagement"] for row in reach_rows} == {good.name}
            and disposition_rows
            and {row["engagement"] for row in disposition_rows} == {good.name}
            and promoted_rows
            and all(bad.name not in relative for relative, _ in promoted_rows)
            and legacy_rows["counts"]["total"] == 1
            and all(entry["engagement_id"] == good.name for entry in migration["entries"]),
            f"reach={reach_rows}; dispositions={disposition_rows}; promoted={promoted_rows}; legacy={legacy_rows['counts']}; migration={migration['counts']}",
        )

        race_measurement_root = root / "measurement-race-root"
        race_engagement = race_measurement_root / "engagements" / "marker-wins-fixture"
        race_finding = race_engagement / "findings" / "F-RACE" / "finding.json"
        race_finding.parent.mkdir(parents=True)
        race_finding.write_text(
            json.dumps({"source": "fixture input", "sink": "fixture output"}) + "\n",
            encoding="utf-8",
        )
        original_reachability_quarantine = reachability_corpus.is_quarantined
        reachability_checks = 0

        def mark_before_reachability_admission(candidate: Path) -> bool:
            nonlocal reachability_checks
            reachability_checks += 1
            if reachability_checks == 2:
                _install_fixture_marker(race_engagement)
            return original_reachability_quarantine(candidate)

        reachability_corpus.is_quarantined = mark_before_reachability_admission
        try:
            raced_rows = reachability_corpus.scan(race_measurement_root)
        finally:
            reachability_corpus.is_quarantined = original_reachability_quarantine
        check(
            "measurement buffers an engagement and lets a marker win before admission",
            reachability_checks >= 2 and raced_rows == [],
            repr(raced_rows),
        )

        reverse_race_root = root / "measurement-reverse-race-root"
        reverse_race_engagement = (
            reverse_race_root / "engagements" / "reverse-marker-wins-fixture"
        )
        reverse_race_finding = (
            reverse_race_engagement / "findings" / "F-REVERSE" / "finding.json"
        )
        reverse_race_finding.parent.mkdir(parents=True)
        reverse_race_finding.write_text(
            json.dumps({"source": "reverse fixture", "sink": "reverse fixture"}) + "\n",
            encoding="utf-8",
        )
        reverse_race_aside = root / "measurement-reverse-race-aside"
        original_reachability_files = reachability_corpus._relative_regular_files
        reverse_race_swapped = False

        def replace_public_source_during_bound_scan(bound: Path):
            nonlocal reverse_race_swapped
            if not reverse_race_swapped:
                reverse_race_swapped = True
                reverse_race_engagement.rename(reverse_race_aside)
                shutil.copytree(reverse_race_aside, reverse_race_engagement)
                _install_fixture_marker(reverse_race_engagement)
            return original_reachability_files(bound)

        reachability_corpus._relative_regular_files = replace_public_source_during_bound_scan
        try:
            reverse_race_rows = reachability_corpus.scan(reverse_race_root)
        finally:
            reachability_corpus._relative_regular_files = original_reachability_files
        check(
            "governed scanner binds one source inode and rejects a marked public-path replacement",
            reverse_race_swapped and reverse_race_rows == [],
            repr(reverse_race_rows),
        )

        migration_race_root = root / "migration-inventory-race-root"
        migration_race_source = migration_race_root / "engagements" / "migration-race-source"
        migration_race_source.mkdir(parents=True)
        migration_race_source.joinpath("source.txt").write_text(
            "migration-inventory-aba-sentinel\n", encoding="utf-8"
        )
        migration_race_aside = root / "migration-inventory-race-aside"
        inventory_function = migration_module["inventory"]
        original_migration_snapshot = inventory_function.__globals__["_snapshot_bound_engagement"]
        migration_inventory_swapped = False

        def swap_migration_source_during_snapshot(source_fd, destination):
            nonlocal migration_inventory_swapped
            if not migration_inventory_swapped:
                migration_inventory_swapped = True
                migration_race_source.rename(migration_race_aside)
                shutil.copytree(migration_race_aside, migration_race_source)
                _install_fixture_marker(migration_race_source)
            return original_migration_snapshot(source_fd, destination)

        inventory_function.__globals__["_snapshot_bound_engagement"] = swap_migration_source_during_snapshot
        try:
            migration_race_result = inventory_function(migration_race_root)
        finally:
            inventory_function.__globals__["_snapshot_bound_engagement"] = original_migration_snapshot
        check(
            "migration inventory binds each source inode and discards a public-path quarantine swap",
            migration_inventory_swapped
            and migration_race_result["entries"] == []
            and migration_race_result["counts"]["total"] == 0,
            repr(migration_race_result),
        )

        corpus_source = root / "quarantined-corpus-source"
        corpus_source.mkdir()
        corpus_pins = corpus_source / "pins.tsv"
        corpus_pins.write_text(
            "status\tpackage\tversion\tdist.shasum\n", encoding="utf-8"
        )
        corpus_tarballs = corpus_source / "tarballs"
        corpus_tarballs.mkdir()
        corpus_freeze_source = corpus_source / "freeze.json"
        corpus_freeze_source.write_text("{}\n", encoding="utf-8")
        _install_fixture_marker(corpus_source)
        corpus_output_root = root / "external-corpus-output"
        corpus_output_root.mkdir()
        corpus_artifact = corpus_output_root / "enumeration.tsv"
        corpus_freeze = corpus_output_root / "freeze.json"
        corpus_build = _run(
            TOOLS / "corpus_enumeration.py",
            "build",
            "--pins", str(corpus_pins),
            "--tarballs", str(corpus_tarballs),
            "--output", str(corpus_artifact),
            "--freeze", str(corpus_freeze),
        )
        corpus_freeze_link = corpus_output_root / "quarantined-freeze-link.json"
        corpus_freeze_link.symlink_to(corpus_freeze_source)
        corpus_verify = _run(
            TOOLS / "corpus_enumeration.py", "verify", "--freeze", str(corpus_freeze_source)
        )
        corpus_verify_link = _run(
            TOOLS / "corpus_enumeration.py", "verify", "--freeze", str(corpus_freeze_link)
        )
        check(
            "corpus build and verify refuse direct or symlinked quarantined source evidence",
            corpus_build.returncode != 0
            and corpus_verify.returncode != 0
            and corpus_verify_link.returncode != 0
            and not corpus_artifact.exists()
            and not corpus_freeze.exists(),
            corpus_build.stdout + corpus_build.stderr
            + corpus_verify.stdout + corpus_verify.stderr
            + corpus_verify_link.stdout + corpus_verify_link.stderr,
        )

        q02_external = root / "q02-external"
        q02_external.mkdir()
        q02_measurements = q02_external / "measurements.json"
        q02_measurements.write_text(
            json.dumps(
                {
                    "arm_a": {"M1_findings": [], "M5_subagents": 1},
                    "arm_b": {"M1_findings": [], "M5_subagents": 1},
                }
            ) + "\n",
            encoding="utf-8",
        )
        q02_worksheet = q02_external / "worksheet.json"
        q02_worksheet.write_text(
            json.dumps(
                {
                    "blinding_held": True,
                    "run_record": {
                        "ran_concurrently": True,
                        "cross_arm_read_occurred": False,
                        "limit_truncated_an_arm": False,
                    },
                    "M6_overlap": {"both_arms": 0, "arm_a_only": 0, "arm_b_only": 0},
                    "M7_waste": {"waste_class_a_avoided_that_b_hit": None},
                }
            ) + "\n",
            encoding="utf-8",
        )
        q02_prereg_root = root / "quarantined-q02-prereg"
        q02_prereg_root.mkdir()
        q02_prereg = q02_prereg_root / "prereg.json"
        q02_prereg.write_text(
            json.dumps(
                {
                    "preregistration_id": "secret-q02-preregistration-id",
                    "decision_rule": {
                        "prompt_earns_its_keep_if": "M1(A) - M1(B) >= 2",
                        "what_this_can_and_cannot_license": "synthetic fixture only",
                    },
                }
            ) + "\n",
            encoding="utf-8",
        )
        _install_fixture_marker(q02_prereg_root)
        q02_direct = _run(
            TOOLS / "q02_compare.py",
            "verdict",
            "--measurements", str(q02_measurements),
            "--worksheet", str(q02_worksheet),
            "--prereg", str(q02_prereg),
        )

        q02_race_root = root / "q02-race-prereg"
        q02_race_root.mkdir()
        q02_race_prereg = q02_race_root / "prereg.json"
        q02_race_prereg.write_bytes(
            (TOOLS.parent / "fixtures" / "preregistration" /
             "phase5-q02-prompt-ablation-portable.json").read_bytes()
        )
        q02_module = runpy.run_path(str(TOOLS / "q02_compare.py"), run_name="q02_quarantine_test")
        q02_original_ancestor = q02_module["cmd_verdict"].__globals__["quarantined_ancestor"]
        q02_race_checks = 0

        def mark_between_q02_read_and_emit(candidate: Path) -> bool:
            nonlocal q02_race_checks
            q02_race_checks += 1
            if q02_race_checks == 4:
                _install_fixture_marker(q02_race_root)
            return q02_original_ancestor(candidate)

        q02_module["cmd_verdict"].__globals__["quarantined_ancestor"] = mark_between_q02_read_and_emit
        q02_race_output = io.StringIO()
        q02_race_blocked = False
        try:
            with redirect_stdout(q02_race_output):
                q02_module["cmd_verdict"](
                    SimpleNamespace(
                        measurements=str(q02_measurements),
                        worksheet=str(q02_worksheet),
                        prereg=str(q02_race_prereg),
                    )
                )
        except SystemExit:
            q02_race_blocked = True
        finally:
            q02_module["cmd_verdict"].__globals__["quarantined_ancestor"] = q02_original_ancestor
        q02_diagnostics = q02_direct.stdout + q02_direct.stderr + q02_race_output.getvalue()
        check(
            "Q-02 verdict gates the preregistration source and lets a marker win before emission",
            q02_direct.returncode != 0
            and q02_race_blocked
            and q02_race_checks >= 6
            and "secret-q02-preregistration-id" not in q02_diagnostics
            and "VERDICT:" not in q02_diagnostics,
            q02_diagnostics,
        )

        q02_measure_root = _make_engagement(
            root / "q02-bound-measurement", allowed_digest, "2026-08-23T00:02:05Z"
        )
        q02_arm_a = _make_engagement(
            q02_measure_root / "arm-a", allowed_digest, "2026-08-23T00:02:06Z"
        )
        _make_engagement(
            q02_measure_root / "arm-b", allowed_digest, "2026-08-23T00:02:07Z"
        )
        q02_finding = q02_arm_a / "findings" / "q02-aba-sentinel" / "finding.json"
        q02_finding.parent.mkdir(parents=True)
        q02_finding.write_text(json.dumps({"severity": {"band": "low"}}) + "\n")
        q02_measure_aside = root / "q02-bound-measurement-aside"
        q02_original_snapshot = q02_module["cmd_measure"].__globals__["_snapshot_bound_tree"]
        q02_measure_swapped = False

        def swap_q02_root_during_bound_snapshot(fd):
            nonlocal q02_measure_swapped
            if not q02_measure_swapped:
                q02_measure_swapped = True
                q02_measure_root.rename(q02_measure_aside)
                shutil.copytree(q02_measure_aside, q02_measure_root)
                _install_fixture_marker(q02_measure_root)
            return q02_original_snapshot(fd)

        q02_module["cmd_measure"].__globals__["_snapshot_bound_tree"] = swap_q02_root_during_bound_snapshot
        q02_measure_output = io.StringIO()
        q02_measure_blocked = False
        try:
            with redirect_stdout(q02_measure_output):
                q02_module["cmd_measure"](
                    SimpleNamespace(engagement=str(q02_measure_root), worksheet=None, force=False)
                )
        except SystemExit:
            q02_measure_blocked = True
        finally:
            q02_module["cmd_measure"].__globals__["_snapshot_bound_tree"] = q02_original_snapshot
        check(
            "Q-02 measurement binds one engagement inode and refuses a public-path rename swap",
            q02_measure_swapped
            and q02_measure_blocked
            and "q02-aba-sentinel" not in q02_measure_output.getvalue()
            and "computed_only" not in q02_measure_output.getvalue(),
            q02_measure_output.getvalue(),
        )

        q02_emit_root = _make_engagement(
            root / "q02-marker-before-emit", allowed_digest, "2026-08-23T00:02:08Z"
        )
        q02_emit_arm_a = _make_engagement(
            q02_emit_root / "arm-a", allowed_digest, "2026-08-23T00:02:09Z"
        )
        _make_engagement(
            q02_emit_root / "arm-b", allowed_digest, "2026-08-23T00:02:10Z"
        )
        q02_emit_finding = q02_emit_arm_a / "findings" / "F-Q02-EMIT-LEAK" / "finding.json"
        q02_emit_finding.parent.mkdir(parents=True)
        q02_emit_finding.write_text(json.dumps({"severity": {"band": "low"}}) + "\n")
        q02_emit_worksheet = root / "q02-marker-before-emit-worksheet.json"
        q02_original_require = q02_module["cmd_measure"].__globals__["require_not_quarantined"]
        q02_emit_identity = q02_emit_root.stat()
        q02_emit_root_checks = 0
        q02_emit_marker_installed = False

        def install_marker_at_q02_final_admission(bound):
            nonlocal q02_emit_root_checks, q02_emit_marker_installed
            identity = os.fstat(int(Path(bound).name))
            if (identity.st_dev, identity.st_ino) == (
                q02_emit_identity.st_dev, q02_emit_identity.st_ino
            ):
                q02_emit_root_checks += 1
                if q02_emit_root_checks == 2:
                    _install_fixture_marker(q02_emit_root)
                    q02_emit_marker_installed = True
            return q02_original_require(bound)

        q02_module["cmd_measure"].__globals__["require_not_quarantined"] = (
            install_marker_at_q02_final_admission
        )
        q02_emit_output = io.StringIO()
        q02_emit_blocked = False
        try:
            with redirect_stdout(q02_emit_output):
                q02_module["cmd_measure"](
                    SimpleNamespace(
                        engagement=str(q02_emit_root),
                        worksheet=str(q02_emit_worksheet),
                        force=False,
                    )
                )
        except SystemExit:
            q02_emit_blocked = True
        finally:
            q02_module["cmd_measure"].__globals__["require_not_quarantined"] = (
                q02_original_require
            )
        check(
            "Q-02 measurement lets quarantine win at final admission before every emission",
            q02_emit_marker_installed
            and q02_emit_blocked
            and "F-Q02-EMIT-LEAK" not in q02_emit_output.getvalue()
            and "computed_only" not in q02_emit_output.getvalue()
            and not q02_emit_worksheet.exists(),
            q02_emit_output.getvalue(),
        )

        migration_input_root = root / "quarantined-migration-authority-inputs"
        migration_input_root.mkdir()
        quarantined_proposal = migration_input_root / "proposal.json"
        quarantined_proposal.write_text(
            json.dumps({"secret": "quarantined-proposal-sentinel"}) + "\n",
            encoding="utf-8",
        )
        quarantined_review = migration_input_root / "review.json"
        quarantined_review.write_text(
            json.dumps({"secret": "quarantined-review-sentinel"}) + "\n",
            encoding="utf-8",
        )
        _install_fixture_marker(migration_input_root)
        external_proposal = q02_external / "migration-proposal.json"
        external_proposal.write_text("{}\n", encoding="utf-8")
        broker_id = f"local-uid-{os.getuid()}:broker"
        broker_session = f"session-posix-{os.getuid()}-{os.getsid(0)}"

        def migration_apply_with(proposal: Path, review: Path | None = None):
            arguments = [
                "migrate",
                "--root", str(root / "unused-migration-root"),
                "--apply-proposal", str(proposal),
                "--destination", str(root / "unused-migration-destination"),
                "--operator-id", "fixture-operator",
                "--recorded-at", "2026-08-23T00:02:10Z",
                "--authority-engagement", str(root / "unused-migration-control"),
                "--authority-request-id", "fixture-migration-authority",
                "--lane-id", "fixture-lane",
                "--executor-id", broker_id,
                "--session-id", broker_session,
            ]
            if review is not None:
                arguments.extend(("--artifact-review", str(review)))
            return _run_engagement(*arguments)

        quarantined_proposal_apply = migration_apply_with(quarantined_proposal)
        quarantined_review_apply = migration_apply_with(external_proposal, quarantined_review)
        migration_input_diagnostics = (
            quarantined_proposal_apply.stdout + quarantined_proposal_apply.stderr
            + quarantined_review_apply.stdout + quarantined_review_apply.stderr
        )
        check(
            "migration proposal and artifact-review authority inputs refuse quarantined sources",
            _error_code(quarantined_proposal_apply) == "migration_authority_input_quarantined"
            and _error_code(quarantined_review_apply) == "migration_authority_input_quarantined"
            and "quarantined-proposal-sentinel" not in migration_input_diagnostics
            and "quarantined-review-sentinel" not in migration_input_diagnostics
            and str(migration_input_root) not in migration_input_diagnostics,
            migration_input_diagnostics,
        )

        lifecycle_malformed = _make_engagement(
            root / "synthetic-lifecycle-malformed", allowed_digest, "2026-08-23T00:02:20Z"
        )
        lifecycle_malformed_marker = lifecycle_malformed / MARKER_RELATIVE
        lifecycle_malformed_marker.parent.mkdir(parents=True, exist_ok=True)
        lifecycle_malformed_marker.write_text(
            json.dumps({"secret": MARKER_SECRET}) + "\n", encoding="utf-8"
        )
        lifecycle_valid_status = _run(
            TOOLS / "finding_lifecycle.py", "status", "--engagement", str(engagement), "--json"
        )
        lifecycle_malformed_status = _run(
            TOOLS / "finding_lifecycle.py",
            "status", "--engagement", str(lifecycle_malformed), "--json",
        )
        expected_lifecycle_status = {"status": "quarantined", "findings": []}
        lifecycle_diagnostics = (
            lifecycle_valid_status.stdout + lifecycle_valid_status.stderr
            + lifecycle_malformed_status.stdout + lifecycle_malformed_status.stderr
        )
        check(
            "lifecycle status maps valid and malformed markers to distinct sanitized quarantine JSON",
            lifecycle_valid_status.returncode == 1
            and lifecycle_malformed_status.returncode == 1
            and _payload(lifecycle_valid_status) == expected_lifecycle_status
            and _payload(lifecycle_malformed_status) == expected_lifecycle_status
            and "Traceback" not in lifecycle_diagnostics
            and MARKER_SECRET not in lifecycle_diagnostics
            and str(engagement) not in lifecycle_diagnostics
            and str(lifecycle_malformed) not in lifecycle_diagnostics,
            lifecycle_diagnostics,
        )

        quarantined_ledger_before = engagement.joinpath("events.jsonl").read_bytes()
        governed_output = _run_engagement(
            "validate", "--legacy-root", str(measurement_root),
            "--output", str(engagement / "events.jsonl"),
        )
        marker_sink = _make_engagement(
            root / "unsigned-marker-output-sink", allowed_digest, "2026-08-23T00:02:30Z"
        )
        unsigned_marker_output = marker_sink / MARKER_RELATIVE
        exact_marker_output = _run_engagement(
            "validate", "--legacy-root", str(measurement_root),
            "--output", str(unsigned_marker_output),
        )
        safe_outputs = root / "safe-output-links"
        safe_outputs.mkdir()
        leaf_link = safe_outputs / "leaf.json"
        leaf_link.symlink_to(engagement / "events.jsonl")
        leaf_output = _run_engagement(
            "validate", "--legacy-root", str(measurement_root),
            "--output", str(leaf_link),
        )
        parent_link = safe_outputs / "parent-link"
        parent_link.symlink_to(engagement, target_is_directory=True)
        parent_output = _run_engagement(
            "validate", "--legacy-root", str(measurement_root),
            "--output", str(parent_link / "events.jsonl"),
        )
        output_diagnostics = "".join(
            result.stdout + result.stderr
            for result in (governed_output, exact_marker_output, leaf_output, parent_output)
        )
        check(
            "offline output sinks cannot overwrite quarantine, create an unsigned marker, or follow symlinks",
            all(
                result.returncode != 0
                and _error_code(result) == "offline_output_forbidden"
                for result in (governed_output, exact_marker_output, leaf_output, parent_output)
            )
            and engagement.joinpath("events.jsonl").read_bytes() == quarantined_ledger_before
            and not unsigned_marker_output.exists()
            and leaf_link.is_symlink()
            and parent_link.is_symlink()
            and str(engagement) not in output_diagnostics,
            output_diagnostics,
        )

        atomic_safe_parent = root / "atomic-safe-parent"
        atomic_safe_parent.mkdir()
        atomic_destination = atomic_safe_parent / "portable.json"
        atomic_destination.write_bytes(b"original-portable-bytes\n")
        atomic_governed = _make_engagement(
            root / "atomic-parent-aba-governed", allowed_digest, "2026-08-23T00:02:40Z"
        )
        _install_fixture_marker(atomic_governed)
        atomic_moved_parent = atomic_governed / "moved-safe-parent"
        original_parent_check = engagement_quarantine._require_bound_parent_safe
        atomic_parent_checks = 0

        def move_atomic_parent_before_publication(*args, **kwargs):
            nonlocal atomic_parent_checks
            atomic_parent_checks += 1
            if atomic_parent_checks == 3:
                atomic_safe_parent.rename(atomic_moved_parent)
                atomic_safe_parent.mkdir()
            return original_parent_check(*args, **kwargs)

        engagement_quarantine._require_bound_parent_safe = move_atomic_parent_before_publication
        atomic_parent_blocked = False
        try:
            engagement_quarantine.atomic_write_offline(
                atomic_destination, b"replacement-must-not-survive\n"
            )
        except ValueError:
            atomic_parent_blocked = True
        finally:
            engagement_quarantine._require_bound_parent_safe = original_parent_check
        check(
            "offline publication rolls back an overwritten leaf when its bound parent moves under quarantine",
            atomic_parent_blocked
            and atomic_moved_parent.joinpath("portable.json").read_bytes()
            == b"original-portable-bytes\n"
            and not any(path.name.startswith(".portable.json.") for path in atomic_moved_parent.iterdir())
            and not atomic_safe_parent.joinpath("portable.json").exists(),
            repr(sorted(path.name for path in atomic_moved_parent.iterdir())),
        )

        tree_output_parent = root / "tree-output-safe-parent"
        tree_output_parent.mkdir()
        tree_output = tree_output_parent / "migration-bundle"
        tree_output_governed = _make_engagement(
            root / "tree-output-parent-aba-governed",
            allowed_digest,
            "2026-08-23T00:02:42Z",
        )
        _install_fixture_marker(tree_output_governed)
        tree_output_moved_parent = tree_output_governed / "moved-tree-output-parent"
        tree_output_parent_checks = 0

        def move_tree_output_parent_after_publish(*args, **kwargs):
            nonlocal tree_output_parent_checks
            tree_output_parent_checks += 1
            if tree_output_parent_checks == 3:
                tree_output_parent.rename(tree_output_moved_parent)
                tree_output_parent.mkdir()
            return original_parent_check(*args, **kwargs)

        engagement_quarantine._require_bound_parent_safe = move_tree_output_parent_after_publish
        tree_output_blocked = False
        try:
            engagement_quarantine.atomic_publish_offline_tree(
                tree_output,
                {
                    "inventory.json": b"{}\n",
                    "proposed-finding-revisions/F-ONE/rev-1.json": b"{}\n",
                },
            )
        except ValueError:
            tree_output_blocked = True
        finally:
            engagement_quarantine._require_bound_parent_safe = original_parent_check
        check(
            "offline tree publication rolls back when its bound parent moves under quarantine",
            tree_output_blocked
            and not tree_output_moved_parent.joinpath("migration-bundle").exists()
            and not any(
                path.name.startswith(".migration-bundle.")
                for path in tree_output_moved_parent.iterdir()
            )
            and not tree_output.exists(),
            repr(sorted(path.name for path in tree_output_moved_parent.iterdir())),
        )

        input_safe_parent = root / "input-safe-parent"
        input_safe_parent.mkdir()
        input_source = input_safe_parent / "input.json"
        input_source.write_text("input-parent-aba-sentinel\n", encoding="utf-8")
        input_governed = _make_engagement(
            root / "input-parent-aba-governed", allowed_digest, "2026-08-23T00:02:45Z"
        )
        _install_fixture_marker(input_governed)
        input_moved_parent = input_governed / "moved-input-parent"
        input_parent_checks = 0

        def move_input_parent_before_read(*args, **kwargs):
            nonlocal input_parent_checks
            input_parent_checks += 1
            if input_parent_checks == 1:
                input_safe_parent.rename(input_moved_parent)
                input_safe_parent.mkdir()
            return original_parent_check(*args, **kwargs)

        engagement_quarantine._require_bound_parent_safe = move_input_parent_before_read
        input_parent_blocked = False
        try:
            engagement_quarantine.read_safe_offline_file(input_source)
        except ValueError:
            input_parent_blocked = True
        finally:
            engagement_quarantine._require_bound_parent_safe = original_parent_check

        tree_safe_root = root / "tree-safe-root"
        tree_child = tree_safe_root / "nested"
        tree_child.mkdir(parents=True)
        tree_child.joinpath("fixture.tgz").write_bytes(b"tree-parent-aba-sentinel")
        tree_governed = _make_engagement(
            root / "tree-parent-aba-governed", allowed_digest, "2026-08-23T00:02:50Z"
        )
        _install_fixture_marker(tree_governed)
        tree_moved_child = tree_governed / "moved-tree-child"
        tree_parent_checks = 0

        def move_nested_tree_before_read(*args, **kwargs):
            nonlocal tree_parent_checks
            tree_parent_checks += 1
            if tree_parent_checks == 3:
                tree_child.rename(tree_moved_child)
                tree_child.mkdir()
            return original_parent_check(*args, **kwargs)

        engagement_quarantine._require_bound_parent_safe = move_nested_tree_before_read
        tree_parent_blocked = False
        try:
            engagement_quarantine.read_safe_offline_tree(tree_safe_root)
        except ValueError:
            tree_parent_blocked = True
        finally:
            engagement_quarantine._require_bound_parent_safe = original_parent_check
        check(
            "portable input reads bind both leaf parents and every nested directory across rename ABA",
            input_parent_blocked
            and tree_parent_blocked
            and input_moved_parent.joinpath("input.json").read_text(encoding="utf-8")
            == "input-parent-aba-sentinel\n"
            and tree_moved_child.joinpath("fixture.tgz").read_bytes()
            == b"tree-parent-aba-sentinel",
        )

        casebook = _run(TOOLS / "casebook-provenance-test.py")
        check(
            "casebook import and every reuse enforce dynamic source quarantine",
            casebook.returncode == 0 and "CASEBOOK-PROVENANCE: PASS" in casebook.stdout,
            casebook.stdout + casebook.stderr,
        )

        lock_race = _run(TOOLS / "engagement-lock-race-test.py")
        check(
            "engagement locks bind one inode and recheck marker state after flock",
            lock_race.returncode == 0 and "ENGAGEMENT-LOCK-RACE: PASS" in lock_race.stdout,
            lock_race.stdout + lock_race.stderr,
        )

        source_admission = _run(TOOLS / "source-admission-race-test.py")
        check(
            "read-only source adapters bind one inode through final admission",
            source_admission.returncode == 0
            and "SOURCE ADMISSION RACE SELF-TEST: PASS" in source_admission.stdout,
            source_admission.stdout + source_admission.stderr,
        )

        clear_args = _clear_args(engagement, "2026-08-23T00:03:00Z")
        unsigned_clear = _run_engagement(*clear_args)
        marker_before_clear = marker_path.read_bytes()
        unsigned_marker_preserved = (
            marker_path.is_file() and marker_path.read_bytes() == marker_before_clear
        )
        clear_env = _challenge_env(
            unsigned_clear,
            label="healthy-clear",
            root=root,
            key=key,
            allowed_signers=allowed_signers,
        )
        governed_before_clear = _tree_bytes(engagement, omit_marker=True)
        signed_clear = _run_engagement(*clear_args, env=clear_env)
        after_clear_health = _run_engagement("ledger-health", "--engagement", str(engagement))
        check(
            "unsigned clear is denied; signed clear succeeds only on a healthy underlying ledger",
            unsigned_clear.returncode != 0
            and _error_code(unsigned_clear) == "operator_signature_required"
            and unsigned_marker_preserved,
            unsigned_clear.stdout + unsigned_clear.stderr,
        )
        # Keep the signed-clear assertions separate so the boolean above cannot hide a failure by
        # operator precedence in a compound expression.
        check(
            "signed healthy clear removes only the exact marker and changes no governed byte",
            signed_clear.returncode == 0
            and not marker_path.exists()
            and _payload(after_clear_health).get("status") == "healthy"
            and _tree_bytes(engagement, omit_marker=True) == governed_before_clear,
            signed_clear.stdout + signed_clear.stderr + after_clear_health.stdout + after_clear_health.stderr,
        )

        clear_race = _make_engagement(
            root / "synthetic-clear-race", allowed_digest, "2026-08-23T00:04:00Z"
        )
        clear_race_marker = _install_fixture_marker(clear_race)
        clear_race_args = _clear_args(clear_race, "2026-08-23T00:04:30Z")
        clear_race_unsigned = _run_engagement(*clear_race_args)
        clear_race_env = _challenge_env(
            clear_race_unsigned,
            label="clear-race",
            root=root,
            key=key,
            allowed_signers=allowed_signers,
        )
        clear_race_hook = root / "clear-race-hook"
        clear_race_hook.mkdir()
        clear_race_hook.joinpath("sitecustomize.py").write_text(
            """
import os
import subprocess

_ledger = os.environ["CLEAR_RACE_LEDGER"]
_real_run = subprocess.run
_fired = False

def _run(*args, **kwargs):
    global _fired
    command = args[0] if args else kwargs.get("args", [])
    if not _fired and isinstance(command, (list, tuple)) and "-Y" in command and "verify" in command:
        _fired = True
        with open(_ledger, "ab") as handle:
            handle.write(b'{"synthetic-interrupted-attempt"')
            handle.flush()
            os.fsync(handle.fileno())
    return _real_run(*args, **kwargs)

subprocess.run = _run
""".lstrip(),
            encoding="utf-8",
        )
        clear_race_env.update({
            "CLEAR_RACE_LEDGER": str(clear_race / "attempts.jsonl"),
            "PYTHONPATH": str(clear_race_hook)
            + (os.pathsep + clear_race_env["PYTHONPATH"] if clear_race_env.get("PYTHONPATH") else ""),
        })
        clear_race_result = _run_engagement(*clear_race_args, env=clear_race_env)
        check(
            "signed clear re-reduces all governed sources after signature verification",
            clear_race_result.returncode != 0
            and _error_code(clear_race_result) == "quarantine_underlying_ledger_unhealthy"
            and clear_race_marker.is_file(),
            clear_race_result.stdout + clear_race_result.stderr,
        )

        invalid = _make_engagement(
            root / "synthetic-invalid-ledger", allowed_digest, "2026-08-23T00:10:00Z"
        )
        observation = base_event(
            event_id="event-invalid-second",
            engagement_id=invalid.name,
            recorded_at="2026-08-23T00:10:01Z",
            actor_role="orchestrator",
            actor_id="fixture-orchestrator",
            event_type="observation.recorded",
            rationale="Create a second committed row before a synthetic corruption.",
            payload={"entity_id": "fixture-observation", "entity_type": "observation", "status": "recorded"},
            session_id="fixture-session",
            operation_class="notebook",
        )
        append_ledger_record(invalid, "event", observation)
        valid_events = read_ledger(invalid, "event")
        corrupted = dict(valid_events[1])
        corrupted["event_type"] = INVALID_SECRET
        corrupted["record_hash"] = compute_record_hash(corrupted)
        invalid.joinpath("events.jsonl").write_bytes(
            b"".join(canonical_json_bytes(row) for row in (valid_events[0], corrupted))
        )
        invalid_health = _run_engagement("ledger-health", "--engagement", str(invalid))
        invalid_create_args = _quarantine_args(invalid, "2026-08-23T00:11:00Z")
        invalid_unsigned = _run_engagement(*invalid_create_args)
        invalid_env = _challenge_env(
            invalid_unsigned,
            label="invalid-create",
            root=root,
            key=key,
            allowed_signers=allowed_signers,
        )
        invalid_created = _run_engagement(*invalid_create_args, env=invalid_env)
        invalid_marked_health = _run_engagement("ledger-health", "--engagement", str(invalid))
        invalid_marker = invalid / MARKER_RELATIVE
        invalid_marker_bytes = invalid_marker.read_bytes()
        invalid_clear = _run_engagement(*_clear_args(invalid, "2026-08-23T00:12:00Z"))
        invalid_diagnostics = (
            invalid_health.stdout + invalid_health.stderr
            + invalid_marked_health.stdout + invalid_marked_health.stderr
            + invalid_clear.stdout + invalid_clear.stderr
        )
        check(
            "invalid ledger is distinct, marker precedence is quarantined, and unhealthy clear is denied",
            _payload(invalid_health).get("status") == "invalid"
            and invalid_created.returncode == 0
            and _payload(invalid_marked_health).get("status") == "quarantined"
            and _error_code(invalid_clear) == "quarantine_underlying_ledger_unhealthy"
            and invalid_marker.read_bytes() == invalid_marker_bytes
            and INVALID_SECRET not in invalid_diagnostics,
            invalid_diagnostics,
        )

        missing_name = "missing-unreadable-synthetic-id"
        unreadable = _run_engagement(
            "ledger-health", "--engagement", str(root / missing_name)
        )
        check(
            "health probe distinguishes unreadable while preserving the health API identity field",
            _payload(unreadable).get("status") == "unreadable"
            and _payload(unreadable).get("engagement_id") == missing_name,
            unreadable.stdout + unreadable.stderr,
        )

        for marker_kind in ("regular", "symlink", "directory", "fifo", "socket"):
            malformed = _make_engagement(
                root / f"synthetic-malformed-{marker_kind}",
                allowed_digest,
                f"2026-08-23T00:2{len(checks) % 10}:00Z",
            )
            malformed_marker = malformed / MARKER_RELATIVE
            malformed_marker.parent.mkdir(parents=True, exist_ok=True)
            outside = root / f"outside-{marker_kind}"
            held_socket = None
            if marker_kind == "regular":
                malformed_marker.write_text(
                    json.dumps({"raw": MARKER_SECRET}) + "\n", encoding="utf-8"
                )
            elif marker_kind == "symlink":
                outside.write_text(MARKER_SECRET, encoding="utf-8")
                malformed_marker.symlink_to(outside)
            elif marker_kind == "directory":
                malformed_marker.mkdir()
                malformed_marker.joinpath("retained.txt").write_text(MARKER_SECRET, encoding="utf-8")
            elif marker_kind == "fifo":
                os.mkfifo(malformed_marker)
            else:
                held_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                prior_cwd = os.getcwd()
                try:
                    os.chdir(malformed_marker.parent)
                    held_socket.bind(malformed_marker.name)
                finally:
                    os.chdir(prior_cwd)
            malformed_health = _run_engagement(
                "ledger-health", "--engagement", str(malformed)
            )
            clear_argv = _clear_args(
                malformed, f"2026-08-23T00:3{len(checks) % 10}:00Z"
            )
            unsigned_malformed, signed_malformed = _sign_and_run(
                clear_argv,
                label=f"clear-{marker_kind}",
                root=root,
                key=key,
                allowed_signers=allowed_signers,
            )
            recovered_dirs = list(
                malformed_marker.parent.glob(".ledger-quarantined.cleared-*")
            )
            post_malformed = _run_engagement(
                "ledger-health", "--engagement", str(malformed)
            )
            outputs = (
                malformed_health.stdout + malformed_health.stderr
                + unsigned_malformed.stdout + unsigned_malformed.stderr
                + signed_malformed.stdout + signed_malformed.stderr
                + post_malformed.stdout + post_malformed.stderr
            )
            retained = (
                outside.read_text() == MARKER_SECRET
                if marker_kind == "symlink"
                else marker_kind != "directory"
                or bool(recovered_dirs)
                and recovered_dirs[0].joinpath("retained.txt").read_text() == MARKER_SECRET
            )
            if held_socket is not None:
                held_socket.close()
            check(
                f"malformed {marker_kind} marker fails closed and exact signed recovery is safe",
                _payload(malformed_health).get("status") == "quarantined"
                and unsigned_malformed.returncode != 0
                and _error_code(unsigned_malformed) == "operator_signature_required"
                and signed_malformed.returncode == 0
                and not malformed_marker.exists()
                and not malformed_marker.is_symlink()
                and _payload(post_malformed).get("status") == "healthy"
                and retained
                and MARKER_SECRET not in outputs,
                outputs,
            )

        for component, marker_kind in (
            ("legacy", "regular"),
            ("legacy", "symlink"),
            ("quarantine", "regular"),
            ("quarantine", "symlink"),
        ):
            malformed_parent = _make_engagement(
                root / f"synthetic-malformed-parent-{component}-{marker_kind}",
                allowed_digest,
                f"2026-08-23T00:4{len(checks) % 10}:00Z",
            )
            legacy = malformed_parent / "legacy"
            if component == "legacy":
                legacy.rmdir()
                unsafe_entry = legacy
                recovery_parent = malformed_parent
                recovery_pattern = ".legacy.quarantine-cleared-*"
            else:
                unsafe_entry = legacy / "quarantine"
                recovery_parent = legacy
                recovery_pattern = ".quarantine.quarantine-cleared-*"
            outside_parent = root / f"outside-parent-{component}-{marker_kind}"
            if marker_kind == "regular":
                unsafe_entry.write_text(MARKER_SECRET, encoding="utf-8")
            else:
                outside_parent.mkdir()
                outside_parent.joinpath("retained.txt").write_text(MARKER_SECRET, encoding="utf-8")
                unsafe_entry.symlink_to(outside_parent, target_is_directory=True)
            governed_ledger = malformed_parent / "events.jsonl"
            governed_ledger_before = governed_ledger.read_bytes()
            governed_scope = malformed_parent / "scope.md"
            held_scope = root / f"held-scope-{component}-{marker_kind}.md"
            governed_scope.rename(held_scope)
            ancestor_without_scope = quarantined_ancestor(governed_ledger)
            malformed_parent_output = _run_engagement(
                "validate",
                "--legacy-root", str(measurement_root),
                "--output", str(governed_ledger),
            )
            governed_ledger_after = governed_ledger.read_bytes()
            held_scope.rename(governed_scope)
            if governed_ledger_after != governed_ledger_before:
                # Restore the synthetic fixture so the recovery assertions below remain
                # independent when this regression is deliberately run against old code.
                governed_ledger.write_bytes(governed_ledger_before)
            check(
                f"malformed {marker_kind} {component} parent blocks offline ledger overwrite",
                inspect_quarantine(malformed_parent)["quarantined"]
                and ancestor_without_scope
                and quarantined_ancestor(governed_ledger)
                and malformed_parent_output.returncode != 0
                and _error_code(malformed_parent_output) == "offline_output_forbidden"
                and governed_ledger_after == governed_ledger_before
                and str(malformed_parent) not in (
                    malformed_parent_output.stdout + malformed_parent_output.stderr
                ),
                malformed_parent_output.stdout + malformed_parent_output.stderr,
            )
            malformed_parent_health = _run_engagement(
                "ledger-health", "--engagement", str(malformed_parent)
            )
            parent_clear_args = _clear_args(
                malformed_parent, f"2026-08-23T00:5{len(checks) % 10}:00Z"
            )
            parent_unsigned, parent_signed = _sign_and_run(
                parent_clear_args,
                label=f"clear-parent-{component}-{marker_kind}",
                root=root,
                key=key,
                allowed_signers=allowed_signers,
            )
            recovered = list(recovery_parent.glob(recovery_pattern))
            parent_post_health = _run_engagement(
                "ledger-health", "--engagement", str(malformed_parent)
            )
            parent_outputs = (
                malformed_parent_health.stdout + malformed_parent_health.stderr
                + parent_unsigned.stdout + parent_unsigned.stderr
                + parent_signed.stdout + parent_signed.stderr
                + parent_post_health.stdout + parent_post_health.stderr
            )
            recovered_exact = len(recovered) == 1 and (
                recovered[0].read_text(encoding="utf-8") == MARKER_SECRET
                if marker_kind == "regular"
                else recovered[0].is_symlink()
                and recovered[0].readlink() == outside_parent
                and outside_parent.joinpath("retained.txt").read_text(encoding="utf-8") == MARKER_SECRET
            )
            check(
                f"malformed {marker_kind} {component} parent fails closed and signed clear preserves it",
                _payload(malformed_parent_health).get("status") == "quarantined"
                and parent_unsigned.returncode != 0
                and parent_signed.returncode == 0
                and not unsafe_entry.exists()
                and not unsafe_entry.is_symlink()
                and recovered_exact
                and _payload(parent_post_health).get("status") == "healthy"
                and MARKER_SECRET not in parent_outputs,
                parent_outputs,
            )

    ok = True
    for label, passed, detail in checks:
        ok &= passed
        print(f"  {'ok  ' if passed else 'FAIL'} {label}")
        if not passed and detail:
            print("       " + detail.strip().replace("\n", " ")[:700])
    print("QUARANTINE SELF-TEST: " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
