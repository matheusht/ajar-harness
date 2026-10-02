#!/usr/bin/env python3
"""Offline, non-executing Decision 0005 historical evaluation."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from contextlib import ExitStack, contextmanager
from pathlib import Path

from engagement_records import _reject_duplicate_pairs, RecordError, canonical_json_bytes, sha256_bytes, validate_record
from engagement_quarantine import atomic_write_offline, read_safe_offline_file
from engagement_state import bound_engagement_source, find_engagement_root, read_governed_file


@contextmanager
def _bound_json_sources(paths: list[Path]):
    """Load all governed inputs while their source-root bindings remain live."""

    with ExitStack() as stack:
        bindings = {}
        values = []
        raw = []
        for source in (Path(path).absolute() for path in paths):
            located = find_engagement_root(source)
            if located is not None:
                engagement, relative = located
                key = str(engagement)
                if key not in bindings:
                    bindings[key] = stack.enter_context(
                        bound_engagement_source(engagement)
                    )
                if not relative:
                    raise RecordError(
                        "retrospective_source_unavailable",
                        "retrospective source is not a regular file",
                    )
                data = read_governed_file(bindings[key] / Path(*relative))
            else:
                try:
                    data = read_safe_offline_file(source)
                except ValueError as exc:
                    raise RecordError(
                        "retrospective_source_unavailable",
                        "retrospective source is governed or unavailable",
                    ) from exc
            try:
                value = json.loads(
                    data.decode("utf-8"), object_pairs_hook=_reject_duplicate_pairs
                )
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise RecordError(
                    "invalid_json", "retrospective source is invalid JSON"
                ) from exc
            values.append(value)
            raw.append(data)
        yield values, raw


def evaluate(inventory_path: Path, matrix_path: Path) -> dict:
    with _bound_json_sources([inventory_path, matrix_path]) as (values, raw):
        inventory, matrix = values
        matrix_errors = validate_record(matrix, "historical-case-manifest")
        if matrix_errors: raise RecordError("historical_case_matrix_invalid", "case matrix failed schema", matrix_errors)
        counts = inventory.get("counts", {})
        entries=inventory.get("entries", []); identities=[(entry.get("engagement_id"),entry.get("source_path")) for entry in entries];classifications=inventory.get("classifications", {})
        if inventory.get("mode") != "dry_run" or inventory.get("invented_attempts") != 0 or inventory.get("source_bytes_modified") is not False or counts.get("total") != len(entries) or len(identities)!=len(set(identities)) or sum(classifications.values())!=len(entries) or any(not entry.get("source_hash", "").startswith("sha256:") for entry in entries):
            raise RecordError("historical_inventory_invalid", "inventory is not a non-mutating, unique, fully classified dry run")
        root = Path(__file__).resolve().parents[1]
        checks = [subprocess.run([sys.executable, str(root / "tools/run-engagement.py"), "--self-test"], cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False), subprocess.run([sys.executable, str(root / "tools/migrate-decision5.py"), "--self-test"], cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)]
        conformance = all(result.returncode == 0 for result in checks)
        cases = matrix["cases"]; artifact = [case["artifact_replay"] for case in cases]; blinded = [case["blinded_rerun"] for case in cases]
        report = {
          "schema_version": 1, "evaluation_id": "decision5-retrospective-v1", "inventory_hash": inventory["inventory_hash"], "case_matrix_hash": sha256_bytes(raw[1]),
          "record_reconstruction": {"source_count": counts["total"], "representable": counts["representable"], "needs_review": counts["needs_review"], "invented_attempts": 0, "source_bytes_modified": False, "exact_resume": "not_run"},
          "artifact_replay": {"case_count": len(cases), "eligible": artifact.count("eligible"), "blocked": artifact.count("blocked"), "not_applicable": artifact.count("not_applicable"), "executed": 0, "status": "not_run"},
          "blinded_rerun": {"case_count": len(cases), "regression_only": blinded.count("regression_only"), "holdout_eligible": blinded.count("holdout_eligible"), "blocked": blinded.count("blocked"), "paired_runs_executed": 0, "status": "not_run"},
          "hard_gates": {"safety_violations": 0, "secrets_stored": 0, "known_clean_invalid_accepts": None, "report_link_violations": None, "artifact_integrity_violations": None, "unsupported_impact_regression": "not_measured"},
          "claims": {"architecture_conformance": "demonstrated" if conformance else "not_demonstrated", "historical_reconstruction": "not_demonstrated", "regression_parity": "not_demonstrated", "demonstrated_efficacy": "not_demonstrated", "prospective_release": "not_qualified"},
          "policy": {"target_contact": False, "artifact_execution": False, "zone2_creation": False, "invented_results": False}
        }
        errors = validate_record(report, "retrospective-evaluation")
        if errors: raise RecordError("retrospective_report_invalid", "retrospective report failed schema", errors)
        return report


def self_test() -> int:
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp); matrix={"schema_version":1,"matrix_id":"matrix-test","cases":[],"policy":{"target_contact":False,"artifact_execution":False,"zone2_creation":False,"historical_answers_exposed_to_runner":False}}; mp=root/'matrix.json';mp.write_bytes(canonical_json_bytes(matrix));inv={"schema_version":1,"mode":"dry_run","inventory_hash":"sha256:"+'0'*64,"counts":{"total":0,"representable":0,"needs_review":0},"entries":[],"classifications":{"structured_valid":0,"structured_drifted":0,"narrative_only":0,"artifact":0,"report":0,"submission_like":0,"unknown":0},"invented_attempts":0,"source_bytes_modified":False};ip=root/'inventory.json';ip.write_bytes(canonical_json_bytes(inv));report=evaluate(ip,mp);ok=report['artifact_replay']['executed']==0 and report['claims']['demonstrated_efficacy']=='not_demonstrated' and report['claims']['prospective_release']=='not_qualified'
    print(f"RETROSPECTIVE EVALUATION SELF-TEST: {'PASS' if ok else 'FAIL'}");return 0 if ok else 1


def main() -> int:
    parser=argparse.ArgumentParser();parser.add_argument('--inventory',type=Path);parser.add_argument('--case-matrix',type=Path);parser.add_argument('--output',type=Path);parser.add_argument('--self-test',action='store_true');args=parser.parse_args()
    if args.self_test:return self_test()
    if not args.inventory or not args.case_matrix:parser.error('--inventory and --case-matrix are required')
    report=evaluate(args.inventory,args.case_matrix);data=canonical_json_bytes(report)
    if args.output:
        try: atomic_write_offline(args.output, data)
        except ValueError as exc: raise RecordError("offline_output_forbidden", "offline output destination is governed or quarantined") from exc
    else:sys.stdout.buffer.write(data)
    return 0

if __name__=='__main__':
    try:raise SystemExit(main())
    except RecordError as exc:
        sys.stdout.buffer.write(canonical_json_bytes({"valid":False,"error":exc.as_dict()}));raise SystemExit(1)
