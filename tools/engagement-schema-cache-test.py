#!/usr/bin/env python3
"""Failure-first checks for exact-content schema validation caching."""
from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import engagement_records as records  # noqa: E402


def require(condition: bool, detail: str) -> None:
    if not condition:
        raise AssertionError(detail)


def returned_error_code(record: dict, schema: str = "review") -> str | None:
    try:
        errors = records.validate_record(record, schema)
    except records.RecordError as error:
        return error.code
    return errors[0]["code"] if errors else None


def expect_exception(code: str, action) -> None:
    try:
        action()
    except records.RecordError as error:
        require(error.code == code, f"expected {code}; got {error.code}: {error.message}")
    else:
        raise AssertionError(f"expected RecordError {code}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--expect-cache",
        action="store_true",
        help="require one registry build across unchanged repeated validations",
    )
    args = parser.parse_args()

    suite = records.load_json(ROOT / "fixtures/engagement-records/suite.json")
    valid_review = next(
        copy.deepcopy(case["record"])
        for case in suite["cases"]
        if case.get("schema") == "review" and case.get("valid") is True
    )
    original_schema_dir = records.SCHEMA_DIR
    original_loader_defaults = records._load_schema_documents.__defaults__
    setup = {"registry_builds": 0, "dependency_checks": 0}
    original_build_registry = records.build_registry
    original_check_dependency_version = records.check_dependency_version
    checks: list[str] = []

    with tempfile.TemporaryDirectory(prefix="engagement-schema-cache-") as temporary:
        schema_dir = Path(temporary) / "schemas"
        shutil.copytree(original_schema_dir, schema_dir)
        records.SCHEMA_DIR = schema_dir
        records._load_schema_documents.__defaults__ = (schema_dir,)

        def observed_build_registry(documents=None):
            setup["registry_builds"] += 1
            return original_build_registry(documents)

        def observed_dependency_check():
            setup["dependency_checks"] += 1
            return original_check_dependency_version()

        try:
            with mock.patch.object(records, "build_registry", observed_build_registry), \
                    mock.patch.object(records, "check_dependency_version", observed_dependency_check):
                baseline_bytes = (schema_dir / "review.schema.json").read_bytes()
                one_character = copy.deepcopy(valid_review)
                one_character["rationale"] = "x"

                require(not records.validate_record(valid_review, "review"),
                        "valid fixture review was rejected")
                require(not records.validate_record(valid_review, "review"),
                        "second validation of the valid review was rejected")
                invalid_record = copy.deepcopy(valid_review)
                invalid_record.pop("verdict")
                require(returned_error_code(invalid_record, "review") is not None,
                        "invalid record passed after the schema cache warmed")
                unchanged_registry_builds = setup["registry_builds"]
                expected_builds = 1 if args.expect_cache else 3
                require(unchanged_registry_builds == expected_builds,
                        f"unchanged validations built {unchanged_registry_builds} registries; "
                        f"expected {expected_builds}")
                require(setup["dependency_checks"] >= 3,
                        "dependency version was not checked for every validation")
                checks.extend(("valid review", "invalid record rejected", "unchanged setup count"))

                require(not records.validate_record(one_character, "review"),
                        "one-character rationale should satisfy minLength 1")
                review_path = schema_dir / "review.schema.json"
                before = review_path.stat()
                changed = baseline_bytes.replace(
                    b'"rationale": {\n      "type": "string",\n      "minLength": 1',
                    b'"rationale": {\n      "type": "string",\n      "minLength": 9',
                    1,
                )
                require(changed != baseline_bytes and len(changed) == len(baseline_bytes),
                        "same-size schema mutation was not constructed")
                review_path.write_bytes(changed)
                os.utime(review_path, ns=(before.st_atime_ns, before.st_mtime_ns))
                after = review_path.stat()
                require(after.st_size == before.st_size and after.st_mtime_ns == before.st_mtime_ns,
                        "mutation did not preserve schema size and mtime")
                mutation_build_start = setup["registry_builds"]
                require(returned_error_code(one_character, "review") == "schema_minLength",
                        "same-size/mtime schema content change was not observed")
                require(returned_error_code(one_character, "review") == "schema_minLength",
                        "repeated validation did not preserve changed-schema rejection")
                mutation_builds = setup["registry_builds"] - mutation_build_start
                require(mutation_builds == (1 if args.expect_cache else 2),
                        f"changed-schema validations built {mutation_builds} registries")
                review_path.write_bytes(baseline_bytes)
                os.utime(review_path, ns=(before.st_atime_ns, before.st_mtime_ns))
                checks.append("same-size/mtime content mutation")

                extra_path = schema_dir / "added-duplicate.schema.json"
                review_document = json.loads(baseline_bytes)
                extra_path.write_text(json.dumps({
                    "$schema": review_document["$schema"],
                    "$id": review_document["$id"],
                    "type": "object",
                }), encoding="utf-8")
                require(returned_error_code(valid_review, "review") == "schema_resolution_failed",
                        "added duplicate schema id reused a stale registry")
                expect_exception("duplicate_schema_id", original_build_registry)
                extra_path.unlink()
                require(not records.validate_record(valid_review, "review"),
                        "removing added schema did not restore validation")
                checks.append("schema addition and duplicate id")

                review_path.unlink()
                require(returned_error_code(valid_review, "review") == "missing_schema",
                        "removed review schema was not reported missing")
                review_path.write_bytes(baseline_bytes)
                checks.append("schema removal and missing schema")

                unrelated_path = schema_dir / "historical-case-manifest.schema.json"
                unrelated_bytes = unrelated_path.read_bytes()
                unrelated_path.write_bytes(b'{"broken":')
                expect_exception("invalid_json", lambda: records.validate_record(valid_review, "review"))
                unrelated_path.write_bytes(unrelated_bytes)
                checks.append("malformed schema JSON")

                unrelated_path.write_bytes(b'{"$schema":"x","$schema":"x"}')
                expect_exception("duplicate_json_key", lambda: records.validate_record(valid_review, "review"))
                unrelated_path.write_bytes(unrelated_bytes)
                checks.append("duplicate JSON key")

                unrelated_path.unlink()
                unrelated_path.mkdir()
                expect_exception("invalid_json", lambda: records.validate_record(valid_review, "review"))
                unrelated_path.rmdir()
                unrelated_path.write_bytes(unrelated_bytes)
                checks.append("schema open failure after warm cache")

                with mock.patch.object(
                    records, "_read_bound_regular_file", side_effect=OSError("bound read refused")
                ), mock.patch.object(
                    Path, "read_bytes", side_effect=AssertionError("unsafe path fallback")
                ):
                    expect_exception("invalid_json", lambda: records.validate_record(valid_review, "review"))
                checks.append("bound schema reader refusal does not fall back to path read")

                common_path = schema_dir / "research-common.schema.json"
                common_bytes = common_path.read_bytes()
                common_document = json.loads(common_bytes)
                common_document["$schema"] = "https://example.invalid/unknown-schema"
                common_path.write_text(json.dumps(common_document), encoding="utf-8")
                require(returned_error_code(valid_review, "review") == "schema_resolution_failed",
                        "invalid schema resource did not fail closed")
                common_path.write_bytes(common_bytes)
                checks.append("invalid schema resource")

                warmed_registry_builds = setup["registry_builds"]
                with mock.patch.object(records.importlib.metadata, "version", return_value="0.0"):
                    expect_exception("validator_version_mismatch",
                                     lambda: records.validate_record(valid_review, "review"))
                require(setup["registry_builds"] == warmed_registry_builds,
                        "version mismatch should fail before registry construction")
                checks.append("dependency mismatch after warm cache")
        finally:
            records.SCHEMA_DIR = original_schema_dir
            records._load_schema_documents.__defaults__ = original_loader_defaults

    print(json.dumps({
        "status": "passed",
        "mode": "cache_expected" if args.expect_cache else "baseline_observation",
        "checks": checks,
        "unchanged_validations": 3,
        "unchanged_registry_builds": unchanged_registry_builds,
        "dependency_checks": setup["dependency_checks"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
