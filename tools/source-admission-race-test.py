#!/usr/bin/env python3
"""Deterministic directory-swap regressions for read-only source admission."""

from __future__ import annotations

import argparse
import io
import json
import os
import runpy
import shutil
import subprocess
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import engagement_records
import engagement_state
import finding_lifecycle
import ledger_health
import research_telemetry
from engagement_records import RecordError, canonical_json_bytes


SCOPE = """# Scope

## Surfaces in scope
- Local fixture only.
## Benign safe-objective set
- Deterministic read-only validation.
## Escalation ceiling
- None.
## Impact-demo authorization
- No.
## Accounts / fixtures
- None.
## Authorization
- Operator: operator-source-test
- Date: 2026-07-10
- Signed: [x]
- Record kernel: `decision-0005-v1`
"""


def _initialized(path: Path) -> None:
    path.mkdir()
    path.joinpath("scope.md").write_text(SCOPE, encoding="utf-8")
    engagement_state.initialize_engagement(path, "2026-07-10T00:00:00Z")


def _mark(path: Path) -> None:
    marker = path / "legacy" / "quarantine" / "ledger-quarantined.json"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("{}", encoding="utf-8")


def _marked_initialized(path: Path) -> None:
    _initialized(path)
    path.joinpath(".record-kernel.lock").unlink()
    _mark(path)


def _swap(source: Path, replacement: Path, moved: Path) -> None:
    os.rename(source, moved)
    os.rename(replacement, source)


def _restore(source: Path, replacement: Path, moved: Path) -> None:
    os.rename(source, replacement)
    os.rename(moved, source)


def _central_and_health_transient_swap(root: Path) -> bool:
    source = root / "central-source"
    replacement = root / "central-marked-replacement"
    moved = root / "central-moved"
    _initialized(source)
    _marked_initialized(replacement)

    original_reduce = engagement_state._reduce_engagement_unchecked

    def transient_reduce(bound: Path, **kwargs):
        _swap(source, replacement, moved)
        try:
            return original_reduce(bound, **kwargs)
        finally:
            _restore(source, replacement, moved)

    engagement_state._reduce_engagement_unchecked = transient_reduce
    try:
        state = engagement_state.reduce_engagement(source)
    finally:
        engagement_state._reduce_engagement_unchecked = original_reduce

    original_health_reduce = ledger_health.reduce_engagement

    def transient_health(bound: Path):
        _swap(source, replacement, moved)
        try:
            return original_health_reduce(bound)
        finally:
            _restore(source, replacement, moved)

    ledger_health.reduce_engagement = transient_health
    try:
        health = ledger_health.probe_ledger_health(source)
    finally:
        ledger_health.reduce_engagement = original_health_reduce
    return (
        state["engagement_id"] == source.name
        and health["status"] == "healthy"
        and health["engagement_id"] == source.name
        and not replacement.joinpath(".record-kernel.lock").exists()
    )


def _legacy_inventory_persistent_swap(root: Path) -> bool:
    corpus = root / "legacy-corpus"
    source = corpus / "engagements" / "legacy-source"
    replacement = root / "legacy-marked-replacement"
    moved = root / "legacy-moved"
    source.joinpath("findings").mkdir(parents=True)
    shutil.copy2(
        ROOT / "fixtures" / "findings" / "example-legacy-finding.json",
        source / "findings" / "finding.json",
    )
    replacement.mkdir()
    _mark(replacement)
    original_validate = engagement_records.validate_record
    swapped = False

    def swap_after_validation(*args, **kwargs):
        nonlocal swapped
        result = original_validate(*args, **kwargs)
        if not swapped:
            _swap(source, replacement, moved)
            swapped = True
        return result

    engagement_records.validate_record = swap_after_validation
    try:
        inventory = engagement_records.legacy_finding_inventory(corpus)
    finally:
        engagement_records.validate_record = original_validate
    return (
        swapped
        and inventory["counts"]["total"] == 0
        and inventory["files"] == []
        and not source.joinpath(".record-kernel.lock").exists()
    )


def _telemetry_publication_swap(root: Path) -> bool:
    source = root / "export-source"
    replacement = root / "export-marked-replacement"
    moved = root / "export-moved"
    output = root / "export.json"
    _initialized(source)
    _marked_initialized(replacement)
    original_write = research_telemetry.atomic_write_offline
    swapped = False

    def publish_then_swap(path: Path, data: bytes, **kwargs) -> None:
        nonlocal swapped
        original_write(path, data, **kwargs)
        _swap(source, replacement, moved)
        swapped = True

    research_telemetry.atomic_write_offline = publish_then_swap
    refused = False
    try:
        research_telemetry.export_telemetry(source, output)
    except RecordError:
        refused = True
    finally:
        research_telemetry.atomic_write_offline = original_write
        if swapped:
            _restore(source, replacement, moved)
    return (
        refused
        and not output.exists()
        and not replacement.joinpath(".record-kernel.lock").exists()
    )


def _telemetry_rollback_fifo_swap(root: Path) -> bool:
    output = root / "rollback-output.json"
    marker = root / "rollback-fifo-hook-fired"
    output.write_bytes(b"published bytes\n")
    probe = (
        "import os, sys\n"
        "sys.path.insert(0, sys.argv[1])\n"
        "import research_telemetry as telemetry\n"
        "original_open = os.open\n"
        "def race_open(path, flags, mode=0o777, *, dir_fd=None):\n"
        "    if path == os.path.basename(sys.argv[2]) and sys._getframe(1).f_code.co_name == '_remove_published_output':\n"
        "        with open(sys.argv[3], 'w', encoding='utf-8') as handle: handle.write('reached')\n"
        "        os.unlink(path, dir_fd=dir_fd)\n"
        "        os.mkfifo(path, dir_fd=dir_fd)\n"
        "    return original_open(path, flags, mode, dir_fd=dir_fd)\n"
        "os.open = race_open\n"
        "telemetry._remove_published_output(__import__('pathlib').Path(sys.argv[2]), b'published bytes\\n')\n"
    )
    try:
        result = subprocess.run(
            [sys.executable, "-c", probe, str(ROOT / "tools"), str(output), str(marker)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=2,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False
    return result.returncode == 0 and marker.is_file() and output.is_fifo()


def _score_pre_emit_swap(root: Path) -> bool:
    source = root / "score-source"
    replacement = root / "score-marked-replacement"
    moved = root / "score-moved"
    _initialized(source)
    exported = research_telemetry.export_telemetry(source)
    telemetry = source / "telemetry.json"
    telemetry.write_bytes(canonical_json_bytes(exported))
    _marked_initialized(replacement)

    namespace = runpy.run_path(
        str(ROOT / "tools" / "run-engagement.py"), run_name="source_admission_test"
    )
    command = namespace["command_score_telemetry"]
    command_globals = command.__globals__
    original_score = command_globals["score_telemetry"]
    emitted: list[object] = []
    swapped = False

    def score_then_swap(value):
        nonlocal swapped
        result = original_score(value)
        _swap(source, replacement, moved)
        swapped = True
        return result

    command_globals["score_telemetry"] = score_then_swap
    command_globals["emit"] = emitted.append
    refused = False
    try:
        command(argparse.Namespace(file=telemetry))
    except RecordError:
        refused = True
    finally:
        if swapped:
            _restore(source, replacement, moved)
    return (
        refused
        and emitted == []
        and not replacement.joinpath(".record-kernel.lock").exists()
    )


def _standalone_gate_source_swap(root: Path) -> bool:
    source = root / "portable-package"
    replacement = root / "portable-replacement"
    moved = root / "portable-moved"
    shutil.copytree(
        ROOT / "fixtures" / "lifecycle-corpus" / "unproven" / "F-CORP",
        source,
    )
    shutil.copytree(source, replacement)
    original_run = finding_lifecycle._run_gates_snapshot
    swapped = False

    def mark_after_gate_read(*args, **kwargs):
        nonlocal swapped
        result = original_run(*args, **kwargs)
        if not swapped:
            _swap(source, replacement, moved)
            _mark(moved)
            swapped = True
        return result

    finding_lifecycle._run_gates_snapshot = mark_after_gate_read
    try:
        gates, finding = finding_lifecycle.run_gates(source)
    finally:
        finding_lifecycle._run_gates_snapshot = original_run
    package_only_refused = (
        swapped
        and finding == {}
        and len(gates.rows) == 1
        and gates.rows[0]["gate"] == "GQ"
        and not moved.joinpath(".record-kernel.lock").exists()
    )

    engagement = root / "portable-engagement"
    engagement_replacement = root / "portable-engagement-replacement"
    engagement_moved = root / "portable-engagement-moved"
    shutil.copytree(ROOT / "fixtures" / "lifecycle-corpus", engagement)
    shutil.copytree(engagement, engagement_replacement)
    explicit_swapped = False

    def mark_explicit_engagement(*args, **kwargs):
        nonlocal explicit_swapped
        result = original_run(*args, **kwargs)
        if not explicit_swapped:
            _swap(engagement, engagement_replacement, engagement_moved)
            _mark(engagement_moved)
            explicit_swapped = True
        return result

    finding_lifecycle._run_gates_snapshot = mark_explicit_engagement
    try:
        explicit_gates, explicit_finding = finding_lifecycle.run_gates(
            engagement / "unproven" / "F-CORP", engagement
        )
    finally:
        finding_lifecycle._run_gates_snapshot = original_run
    explicit_refused = (
        explicit_swapped
        and explicit_finding == {}
        and len(explicit_gates.rows) == 1
        and explicit_gates.rows[0]["gate"] == "GQ"
        and not engagement_moved.joinpath(".record-kernel.lock").exists()
    )
    return package_only_refused and explicit_refused


def _explicit_cli_gate_source_swap(root: Path) -> bool:
    source = root / "cli-engagement"
    replacement = root / "cli-marked-replacement"
    moved = root / "cli-moved"
    _initialized(source)
    source.joinpath("unproven").mkdir()
    package = source / "unproven" / "F-CLI"
    shutil.copytree(
        ROOT / "fixtures" / "lifecycle-corpus" / "unproven" / "F-CORP",
        package,
    )
    _marked_initialized(replacement)
    original_run = finding_lifecycle._run_gates_snapshot
    swapped = False

    def replace_after_snapshot(*args, **kwargs):
        nonlocal swapped
        result = original_run(*args, **kwargs)
        if not swapped:
            _swap(source, replacement, moved)
            swapped = True
        return result

    finding_lifecycle._run_gates_snapshot = replace_after_snapshot
    output = io.StringIO()
    try:
        with redirect_stdout(output):
            code = finding_lifecycle.cmd_gates(
                argparse.Namespace(
                    package=str(package),
                    engagement=str(source),
                    json=True,
                )
            )
    finally:
        finding_lifecycle._run_gates_snapshot = original_run
        if swapped:
            _restore(source, replacement, moved)
    try:
        payload = json.loads(output.getvalue())
    except json.JSONDecodeError:
        return False
    return (
        code == 1
        and payload.get("decision") == "blocked"
        and len(payload.get("gates", [])) == 1
        and payload["gates"][0].get("gate") == "GQ"
        and "package" not in payload
        and "moved_to" not in payload
        and not replacement.joinpath(".record-kernel.lock").exists()
    )


def _preflight_pre_emit_swap(root: Path) -> bool:
    source = root / "preflight-engagement"
    replacement = root / "preflight-marked-replacement"
    moved = root / "preflight-moved"
    _initialized(source)
    _marked_initialized(replacement)
    original_kernel_state = finding_lifecycle.kernel_state
    swapped = False

    def replace_after_kernel_read(engagement, snapshot=None):
        nonlocal swapped
        result = original_kernel_state(engagement, snapshot)
        if not swapped:
            _swap(source, replacement, moved)
            swapped = True
        return result

    finding_lifecycle.kernel_state = replace_after_kernel_read
    output = io.StringIO()
    try:
        with redirect_stdout(output):
            code = finding_lifecycle.cmd_preflight(
                argparse.Namespace(engagement=str(source))
            )
    finally:
        finding_lifecycle.kernel_state = original_kernel_state
        if swapped:
            _restore(source, replacement, moved)
    rendered = output.getvalue()
    return (
        code == 1
        and rendered.strip()
        == "PREFLIGHT: REFUSED  -- engagement evidence is quarantined"
        and "PREFLIGHT: OK" not in rendered
        and source.name not in rendered
        and not replacement.joinpath(".record-kernel.lock").exists()
    )


def _status_pre_emit_swap(root: Path) -> bool:
    source = root / "status-engagement"
    replacement = root / "status-marked-replacement"
    moved = root / "status-moved"
    finding_id = "finding-detail-must-not-leak"
    _initialized(source)
    source.joinpath("unproven", finding_id).mkdir(parents=True)
    _marked_initialized(replacement)
    original_rows = finding_lifecycle._bound_finding_rows
    swapped = False

    def replace_after_row_read(engagement):
        nonlocal swapped
        result = original_rows(engagement)
        if not swapped:
            _swap(source, replacement, moved)
            swapped = True
        return result

    finding_lifecycle._bound_finding_rows = replace_after_row_read
    output = io.StringIO()
    try:
        with redirect_stdout(output):
            code = finding_lifecycle.cmd_status(
                argparse.Namespace(engagement=str(source), json=True)
            )
    finally:
        finding_lifecycle._bound_finding_rows = original_rows
        if swapped:
            _restore(source, replacement, moved)
    try:
        payload = json.loads(output.getvalue())
    except json.JSONDecodeError:
        return False
    rendered = output.getvalue()
    return (
        code == 1
        and payload == {"status": "quarantined", "findings": []}
        and finding_id not in rendered
        and source.name not in rendered
        and not replacement.joinpath(".record-kernel.lock").exists()
    )


def _check_resume_pre_emit_swap(root: Path) -> bool:
    source = root / "resume-engagement"
    replacement = root / "resume-marked-replacement"
    moved = root / "resume-moved"
    _initialized(source)
    _marked_initialized(replacement)
    namespace = runpy.run_path(
        str(ROOT / "tools" / "run-engagement.py"), run_name="resume_admission_test"
    )
    command = namespace["command_check_resume"]
    command_globals = command.__globals__
    original_assert = command_globals["assert_resume_current"]
    emitted: list[object] = []
    swapped = False

    def replace_after_resume_check(engagement):
        nonlocal swapped
        result = original_assert(engagement)
        _swap(source, replacement, moved)
        swapped = True
        return result

    command_globals["assert_resume_current"] = replace_after_resume_check
    command_globals["emit"] = emitted.append
    refused = False
    try:
        command(argparse.Namespace(engagement=source))
    except RecordError:
        refused = True
    finally:
        if swapped:
            _restore(source, replacement, moved)
    return (
        refused
        and emitted == []
        and not replacement.joinpath(".record-kernel.lock").exists()
    )


def _validate_marked_entry(root: Path) -> bool:
    source = root / "validate-marked-engagement"
    _marked_initialized(source)
    namespace = runpy.run_path(
        str(ROOT / "tools" / "run-engagement.py"), run_name="validate_admission_test"
    )
    command = namespace["command_validate"]
    emitted: list[object] = []
    command.__globals__["emit"] = emitted.append
    refused = False
    try:
        command(
            argparse.Namespace(
                schema_documents=False,
                fixture_suite=None,
                legacy_root=None,
                output=None,
                file=ROOT / "fixtures" / "findings" / "example-legacy-finding.json",
                engagement=source,
                schema="finding-v2-legacy",
                schema_only=False,
            )
        )
    except RecordError:
        refused = True
    return refused and emitted == [] and not source.joinpath(".record-kernel.lock").exists()


def _migration_publication_swaps(root: Path) -> bool:
    migration_root = root / "migration-root"
    source = migration_root / "engagements" / "migration-source"
    replacement = root / "migration-marked-replacement"
    moved = root / "migration-moved"
    source.parent.mkdir(parents=True)
    source.mkdir()
    source.joinpath("scope.md").write_text(
        SCOPE.replace("decision-0005-v1", "decision-0006-v1"), encoding="utf-8"
    )
    engagement_state.initialize_engagement(source, "2026-07-10T00:00:00Z")
    _marked_initialized(replacement)
    namespace = runpy.run_path(
        str(ROOT / "tools" / "run-engagement.py"), run_name="migration_admission_test"
    )
    command = namespace["command_migrate"]
    command_globals = command.__globals__
    command_globals["_require_local_provenance"] = lambda *args, **kwargs: None
    command_globals["emit"] = lambda _value: None
    common = {
        "root": migration_root,
        "apply_proposal": None,
        "destination": None,
        "artifact_review": None,
        "authority_engagement": None,
        "authority_request_id": None,
        "lane_id": None,
        "executor_id": "broker-source-test",
        "session_id": "session-source-test",
        "operator_id": "operator-source-test",
        "recorded_at": "2026-07-10T00:01:00Z",
    }

    proposal_output = root / "migration-proposal.json"
    prior = b"prior-proposal-output\n"
    proposal_output.write_bytes(prior)
    original_file_write = command_globals["atomic_write_offline"]
    file_swapped = False

    def publish_file_then_swap(path, data, **kwargs):
        nonlocal file_swapped
        original_file_write(path, data, **kwargs)
        if not file_swapped:
            _swap(source, replacement, moved)
            file_swapped = True

    command_globals["atomic_write_offline"] = publish_file_then_swap
    proposal_refused = False
    try:
        command(
            argparse.Namespace(
                **common,
                output=proposal_output,
                migration_dir=None,
                propose_engagement=source.name,
                dry_run_engagement=None,
            )
        )
    except (RecordError, ValueError):
        proposal_refused = True
    finally:
        command_globals["atomic_write_offline"] = original_file_write
        if file_swapped:
            _restore(source, replacement, moved)
    proposal_ok = proposal_refused and proposal_output.read_bytes() == prior

    bundle_output = root / "migration-bundle"
    original_tree_write = command_globals["atomic_publish_offline_tree"]
    tree_swapped = False

    def publish_tree_then_swap(path, files):
        nonlocal tree_swapped
        original_tree_write(path, files)
        if not tree_swapped:
            _swap(source, replacement, moved)
            tree_swapped = True

    command_globals["atomic_publish_offline_tree"] = publish_tree_then_swap
    bundle_refused = False
    try:
        command(
            argparse.Namespace(
                **common,
                output=None,
                migration_dir=bundle_output,
                propose_engagement=None,
                dry_run_engagement=source.name,
            )
        )
    except (RecordError, ValueError):
        bundle_refused = True
    finally:
        command_globals["atomic_publish_offline_tree"] = original_tree_write
        if tree_swapped:
            _restore(source, replacement, moved)
    bundle_ok = bundle_refused and not bundle_output.exists()

    prior_tree = root / "migration-prior-tree"
    prior_tree.mkdir()
    prior_tree.joinpath("keep.txt").write_bytes(b"prior-tree-output\n")
    prior_tree_before = {"keep.txt": b"prior-tree-output\n"}
    prior_refused = False
    try:
        command(
            argparse.Namespace(
                **common,
                output=None,
                migration_dir=prior_tree,
                propose_engagement=None,
                dry_run_engagement=source.name,
            )
        )
    except (RecordError, ValueError):
        prior_refused = True
    prior_ok = (
        prior_refused
        and command_globals["read_safe_offline_tree"](prior_tree) == prior_tree_before
    )
    return (
        proposal_ok
        and bundle_ok
        and prior_ok
        and not replacement.joinpath(".record-kernel.lock").exists()
    )


def _render_proof_pre_emit_swap(root: Path) -> bool:
    source = root / "proof-engagement"
    replacement = root / "proof-marked-replacement"
    moved = root / "proof-moved"
    _initialized(source)
    _marked_initialized(replacement)
    namespace = runpy.run_path(
        str(ROOT / "tools" / "run-engagement.py"), run_name="proof_admission_test"
    )
    command = namespace["command_render_proof"]
    command_globals = command.__globals__
    emitted: list[object] = []
    finding_id = "finding-proof-sentinel"
    command_globals["build_reference_index"] = lambda _engagement: {
        finding_id: [{"type": "finding", "revision": 1, "path": "finding.json"}]
    }
    swapped = False

    def load_then_swap(_path):
        nonlocal swapped
        _swap(source, replacement, moved)
        swapped = True
        return {}

    command_globals["load_json"] = load_then_swap
    command_globals["claim_tuple_hash"] = lambda _finding: "claim-hash-sentinel"
    command_globals["render_claim_proof"] = lambda _finding: "proof-markdown-sentinel"
    command_globals["emit"] = emitted.append
    refused = False
    try:
        command(
            argparse.Namespace(
                engagement=source, finding_id=finding_id, revision=1
            )
        )
    except RecordError:
        refused = True
    finally:
        if swapped:
            _restore(source, replacement, moved)
    return (
        refused
        and emitted == []
        and not replacement.joinpath(".record-kernel.lock").exists()
    )


def main() -> int:
    checks = []
    with tempfile.TemporaryDirectory(prefix="source-admission-race-") as tmp:
        root = Path(tmp).resolve()
        checks.extend(
            (
                ("central reducer and health retain one bound source across transient marked replacement", _central_and_health_transient_swap(root)),
                ("legacy inventory discards buffered rows after a persistent source replacement", _legacy_inventory_persistent_swap(root)),
                ("telemetry export rolls back publication when source admission fails", _telemetry_publication_swap(root)),
                ("telemetry rollback rejects a FIFO replacement without blocking", _telemetry_rollback_fifo_swap(root)),
                ("telemetry scoring emits nothing after a governed source replacement", _score_pre_emit_swap(root)),
                ("direct standalone gates with or without explicit engagement disclose no finding detail after source quarantine", _standalone_gate_source_swap(root)),
                ("explicit-engagement gate CLI emits only sanitized GQ after public source replacement", _explicit_cli_gate_source_swap(root)),
                ("preflight emits no OK or engagement detail after public source replacement", _preflight_pre_emit_swap(root)),
                ("status emits no finding IDs or engagement path after public source replacement", _status_pre_emit_swap(root)),
                ("check-resume emits no count or hash after public source replacement", _check_resume_pre_emit_swap(root)),
                ("reference validation rejects a marked engagement without creating coordination state", _validate_marked_entry(root)),
                ("migration proposal and dry-run outputs roll back exactly after source replacement", _migration_publication_swaps(root)),
                ("render-proof emits no finding proof detail after public source replacement", _render_proof_pre_emit_swap(root)),
            )
        )
    for label, passed in checks:
        print(f"  {'ok  ' if passed else 'FAIL'} {label}")
    if all(passed for _, passed in checks):
        print("SOURCE ADMISSION RACE SELF-TEST: PASS")
        return 0
    print("SOURCE ADMISSION RACE SELF-TEST: FAIL")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
