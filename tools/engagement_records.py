#!/usr/bin/env python3
"""Trusted record primitives for the Decision 0005 engagement kernel.

This module owns JSON loading, Draft 2020-12 schema validation, canonical bytes,
and read-only legacy inventory. It does not drive targets or adjudicate claims.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import re
import stat
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

class RecordError(ValueError):
    """A stable, operator-facing record validation failure."""

    def __init__(self, code: str, message: str, details: list[dict[str, Any]] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or []

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "details": self.details}


_JSONSCHEMA_IMPORT_ERROR: ImportError | None = None
try:
    from jsonschema import Draft202012Validator, FormatChecker
    from referencing import Registry, Resource
except ImportError as exc:  # imported lazily enough for the CLI to emit a structured failure
    _JSONSCHEMA_IMPORT_ERROR = exc
    Draft202012Validator = FormatChecker = Registry = Resource = None  # type: ignore[assignment]

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "schemas"
REQUIRED_JSONSCHEMA_VERSION = "4.26.0"
NEW_SCHEMA_FILES = (
    "research-common.schema.json",
    "finding-v3.schema.json",
    "attempt-v2.schema.json",
    "artifact.schema.json",
    "corpus-enumeration.schema.json",
    "review.schema.json",
    "engagement-event.schema.json",
    "state-snapshot.schema.json",
    "environment-preflight.schema.json",
    "environment-preflight-v2.schema.json",
    "report-manifest.schema.json",
    "memory-disposition.schema.json",
    "migration-manifest.schema.json",
    "research-telemetry.schema.json",
    "historical-case-manifest.schema.json",
    "retrospective-evaluation.schema.json",
    "ab-preregistration.schema.json",
    "ab-readiness-report.schema.json",
    "ab-study-evidence.schema.json",
    "migration-artifact-review.schema.json",
    "flow-telemetry.schema.json",
    "work-queue-driver.schema.json",
    "research-lifecycle.schema.json",
    "negative-result.schema.json",
)
SECRET_PATTERNS = {
    "authorization_header": re.compile(rb"authorization\s*:\s*(?:bearer|basic)\s+[A-Za-z0-9._~+/=-]{8,}", re.IGNORECASE),
    "jwt": re.compile(rb"eyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),
    "private_key": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "signed_url": re.compile(rb"[?&](?:x-amz-signature|signature|sig)=[A-Fa-f0-9%]{16,}", re.IGNORECASE),
    "password_assignment": re.compile(rb"(?:password|passwd|pwd)[\"']?\s*[:=]\s*[\"']?(?!/)[^\s,;\"']{8,}", re.IGNORECASE),
    "provider_token": re.compile(rb"(?:gh[pousr]_[A-Za-z0-9]{20,}|AKIA[A-Z0-9]{16}|sk-[A-Za-z0-9_-]{20,})"),
}


def detect_secret_classes(data: bytes) -> list[str]:
    return sorted(name for name, pattern in SECRET_PATTERNS.items() if pattern.search(data))


def scan_file_secret_classes(path: Path) -> list[str]:
    found: set[str] = set(); overlap = b""
    with open(path, "rb") as handle:
        while chunk := handle.read(1024 * 1024):
            sample = overlap + chunk
            found.update(detect_secret_classes(sample)); overlap = sample[-4096:]
    return sorted(found)


RECORD_SCHEMA_FILES = {
    "finding-v3": "finding-v3.schema.json",
    "attempt-v2": "attempt-v2.schema.json",
    "artifact": "artifact.schema.json",
    "corpus-enumeration": "corpus-enumeration.schema.json",
    "review": "review.schema.json",
    "engagement-event": "engagement-event.schema.json",
    "state-snapshot": "state-snapshot.schema.json",
    "environment-preflight": "environment-preflight.schema.json",
    "environment-preflight-v2": "environment-preflight-v2.schema.json",
    "report-manifest": "report-manifest.schema.json",
    "memory-disposition": "memory-disposition.schema.json",
    "migration-manifest": "migration-manifest.schema.json",
    "research-telemetry": "research-telemetry.schema.json",
    "historical-case-manifest": "historical-case-manifest.schema.json",
    "retrospective-evaluation": "retrospective-evaluation.schema.json",
    "ab-preregistration": "ab-preregistration.schema.json",
    "ab-readiness-report": "ab-readiness-report.schema.json",
    "ab-study-evidence": "ab-study-evidence.schema.json",
    "migration-artifact-review": "migration-artifact-review.schema.json",
    "flow-telemetry": "flow-telemetry.schema.json",
    "work-queue-driver": "work-queue-driver.schema.json",
    "negative-result": "negative-result.schema.json",
    "finding-v2-legacy": "finding.schema.json",
}


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise RecordError("duplicate_json_key", f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def _read_bound_regular_file(path: os.PathLike[str] | str) -> bytes | None:
    """Read ``/dev/fd/N/<relative>`` with openat on macOS.

    macOS exposes the directory descriptor itself at ``/dev/fd/N`` but ordinary pathname
    traversal below it returns ENOENT. Transaction callers intentionally use this alias to prevent
    directory ABA; dropping back to the original pathname would undo that protection.
    """

    absolute = Path(os.path.abspath(path))
    parts = absolute.parts
    if not (
        len(parts) >= 5
        and parts[1:3] == ("dev", "fd")
        and parts[3].isdigit()
    ):
        return None
    relative = parts[4:]
    if any(part in {"", ".", ".."} for part in relative):
        raise OSError("unsafe bound relative path")
    directory_fd = os.dup(int(parts[3]))
    directory_flags = (
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        if not stat.S_ISDIR(os.fstat(directory_fd).st_mode):
            raise OSError("bound root is not a directory")
        for component in relative[:-1]:
            child = os.open(component, directory_flags, dir_fd=directory_fd)
            os.close(directory_fd)
            directory_fd = child
        fd = os.open(
            relative[-1],
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=directory_fd,
        )
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode):
                raise OSError("bound input is not a regular file")
            chunks: list[bytes] = []
            while True:
                chunk = os.read(fd, 1024 * 1024)
                if not chunk:
                    break
                chunks.append(chunk)
            after = os.fstat(fd)
            if (
                before.st_dev,
                before.st_ino,
                before.st_size,
                before.st_mtime_ns,
            ) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
                raise OSError("bound input changed during read")
            return b"".join(chunks)
        finally:
            os.close(fd)
    finally:
        os.close(directory_fd)


def load_json(path: os.PathLike[str] | str) -> Any:
    try:
        bound = _read_bound_regular_file(path)
        if bound is not None:
            return json.loads(bound.decode("utf-8"), object_pairs_hook=_reject_duplicate_pairs)
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle, object_pairs_hook=_reject_duplicate_pairs)
    except RecordError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RecordError("invalid_json", f"cannot load JSON {path}: {exc}") from exc


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def sha256_file(path: os.PathLike[str] | str) -> str:
    bound = _read_bound_regular_file(path)
    if bound is not None:
        return sha256_bytes(bound)
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def check_dependency_version() -> None:
    if _JSONSCHEMA_IMPORT_ERROR is not None:
        raise RecordError("validator_unavailable", "jsonschema==4.26.0 and its referencing dependency are not importable") from _JSONSCHEMA_IMPORT_ERROR
    try:
        actual = importlib.metadata.version("jsonschema")
    except importlib.metadata.PackageNotFoundError as exc:
        raise RecordError("validator_unavailable", "jsonschema distribution is not installed") from exc
    if actual != REQUIRED_JSONSCHEMA_VERSION:
        raise RecordError(
            "validator_version_mismatch",
            f"jsonschema {REQUIRED_JSONSCHEMA_VERSION} required, found {actual}",
        )


def _load_schema_documents(schema_dir: Path = SCHEMA_DIR) -> dict[str, dict[str, Any]]:
    documents: dict[str, dict[str, Any]] = {}
    for path in sorted(schema_dir.glob("*.schema.json")):
        document = load_json(path)
        if not isinstance(document, dict):
            raise RecordError("invalid_schema_document", f"schema is not an object: {path}")
        documents[path.name] = document
    return documents


def build_registry(documents: dict[str, dict[str, Any]] | None = None) -> Registry:
    check_dependency_version()
    documents = documents or _load_schema_documents()
    registry = Registry()
    seen: dict[str, str] = {}
    for name, document in sorted(documents.items()):
        schema_id = document.get("$id")
        if schema_id:
            if schema_id in seen:
                raise RecordError("duplicate_schema_id", f"{name} and {seen[schema_id]} declare {schema_id}")
            seen[schema_id] = name
            try:
                registry = registry.with_resource(schema_id, Resource.from_contents(document))
            except Exception as exc:
                raise RecordError("invalid_schema_resource", f"cannot register {name}: {exc}") from exc
    return registry


def _reference_problems(name: str, document: dict[str, Any], documents: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {value.get("$id"): value for value in documents.values() if value.get("$id")}
    problems: list[dict[str, Any]] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            ref = value.get("$ref")
            if isinstance(ref, str):
                if ref.startswith("#"):
                    target = document
                    fragment = ref[1:]
                else:
                    base, marker, fragment = ref.partition("#")
                    target = by_id.get(base)
                    if target is None:
                        problems.append({"schema": name, "code": "unresolved_ref", "ref": ref})
                        target = None
                    fragment = fragment if marker else ""
                if target is not None and fragment.startswith("/"):
                    current: Any = target
                    try:
                        for token in fragment[1:].split("/"):
                            token = token.replace("~1", "/").replace("~0", "~")
                            current = current[token]
                    except (KeyError, TypeError):
                        problems.append({"schema": name, "code": "unresolved_ref_fragment", "ref": ref})
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(document)
    return problems


def validate_schema_documents() -> list[dict[str, Any]]:
    check_dependency_version()
    documents = _load_schema_documents()
    registry = build_registry(documents)
    problems: list[dict[str, Any]] = []
    for name in NEW_SCHEMA_FILES:
        document = documents.get(name)
        if document is None:
            problems.append({"schema": name, "code": "missing_schema"})
            continue
        if document.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
            problems.append({"schema": name, "code": "wrong_metaschema"})
            continue
        problems.extend(_reference_problems(name, document, documents))
        try:
            Draft202012Validator.check_schema(document)
            Draft202012Validator(document, registry=registry, format_checker=FormatChecker())
        except Exception as exc:
            problems.append({"schema": name, "code": "invalid_schema", "message": str(exc)})
    return problems


def _error_detail(error: Any) -> dict[str, Any]:
    instance_path = "/" + "/".join(str(part) for part in error.absolute_path)
    schema_path = "/" + "/".join(str(part) for part in error.absolute_schema_path)
    validator = str(error.validator or "schema")
    return {
        "code": f"schema_{validator}",
        "instance_path": instance_path,
        "schema_path": schema_path,
        "message": error.message,
    }


def _semantic_record_errors(record: Any, schema_name: str) -> list[dict[str, Any]]:
    if not isinstance(record, dict):
        return []
    errors: list[dict[str, Any]] = []
    if schema_name == "review":
        independence = record.get("independence", {})
        if independence.get("reviewer_run_id") == independence.get("originating_run_id"):
            errors.append({"code": "review_not_independent", "instance_path": "/independence", "schema_path": "/semantic", "message": "reviewer and originating runs must differ"})
        if record.get("review_type") in {"claim_adjudication", "coverage", "regrade", "pocinator", "candidate_outcome"} and independence.get("fresh_context") is not True:
            errors.append({"code": "fresh_review_required", "instance_path": "/independence/fresh_context", "schema_path": "/semantic", "message": "this review type requires fresh context"})
        return errors
    if schema_name == "historical-case-manifest":
        cases=record.get("cases",[]);case_ids=[item.get("case_id") for item in cases]
        if len(case_ids)!=len(set(case_ids)) or any(item.get("decision5_informed") and item.get("blinded_rerun")!="regression_only" for item in cases):
            errors.append({"code":"historical_case_classification_invalid","instance_path":"/cases","schema_path":"/semantic","message":"case IDs must be unique and decision-informing cases are regression-only"})
        return errors
    if schema_name == "retrospective-evaluation":
        reconstruction=record.get("record_reconstruction",{});artifact=record.get("artifact_replay",{});blinded=record.get("blinded_rerun",{});claims=record.get("claims",{})
        invalid=(reconstruction.get("representable",0)+reconstruction.get("needs_review",0)!=reconstruction.get("source_count",0) or artifact.get("eligible",0)+artifact.get("blocked",0)+artifact.get("not_applicable",0)!=artifact.get("case_count",0) or blinded.get("regression_only",0)+blinded.get("holdout_eligible",0)+blinded.get("blocked",0)!=blinded.get("case_count",0) or (blinded.get("paired_runs_executed",0)==0 and claims.get("regression_parity")!="not_demonstrated") or (claims.get("prospective_release")=="qualified" and (artifact.get("status")!="complete" or blinded.get("status")!="complete")))
        if invalid:errors.append({"code":"retrospective_denominator_or_claim_invalid","instance_path":"/","schema_path":"/semantic","message":"layer denominators and bounded claims must agree with executed work"})
        return errors
    if schema_name == "ab-preregistration":
        arms=record.get("arms",[]);labels=[item.get("blind_label") for item in arms];treatments=[item.get("treatment") for item in arms]
        commitments=[item.get("source",{}) for item in arms]+[record.get("common_safety_overlay",{})]
        hashes_valid=all(commitment.get("tree_hash")==sha256_bytes(canonical_json_bytes(commitment.get("files",[]))) for commitment in commitments)
        evidence_refs=[record.get("study_evidence_ref"),record.get("case_isolation_plan_ref"),record.get("withheld_material_manifest_ref"),record.get("adjudication",{}).get("evidence_ref")];bound_refs=[item for item in evidence_refs if item is not None];refs_consistent=not bound_refs or (len(bound_refs)==4 and all(item==bound_refs[0] for item in bound_refs))
        pilot_bound=record.get("power_basis")=="pilot_bound"
        if len(set(labels))!=2 or len(set(treatments))!=2 or not hashes_valid or not refs_consistent or (pilot_bound and (record.get("minimum_practical_effect") is None or record.get("sample_size") is None or record.get("matching",{}).get("model_runtime_hash") is None or record.get("matching",{}).get("tool_runtime_hash") is None)) or (record.get("exploratory") is False and not pilot_bound):
            errors.append({"code":"ab_preregistration_semantic_invalid","instance_path":"/","schema_path":"/semantic","message":"arms, frozen source hashes, and confirmatory design fields must be complete"})
        return errors
    if schema_name == "ab-study-evidence":
        holdouts=record.get("holdouts",[]);isolation=record.get("isolation",[]);holdout_ids=[item.get("case_id") for item in holdouts];isolation_ids=[item.get("case_id") for item in isolation]
        separated=all(item.get("arm_x_target_copy")!=item.get("arm_y_target_copy") and item.get("arm_x_filesystem")!=item.get("arm_y_filesystem") and item.get("arm_x_account_label")!=item.get("arm_y_account_label") for item in isolation)
        if len(holdout_ids)!=len(set(holdout_ids)) or set(holdout_ids)!=set(isolation_ids) or len(isolation_ids)!=len(set(isolation_ids)) or not separated:
            errors.append({"code":"ab_study_evidence_invalid","instance_path":"/isolation","schema_path":"/semantic","message":"every unique holdout needs distinct paired target, filesystem, and account isolation"})
        return errors
    if schema_name == "ab-readiness-report":
        ready=record.get("status")=="ready_for_operator_authorization";checks=record.get("checks",{})
        if ready!=(not record.get("blockers") and all(checks.values())) or (ready and record.get("claims",{}).get("ab_readiness")!="contract_ready"):
            errors.append({"code":"ab_readiness_claim_invalid","instance_path":"/status","schema_path":"/semantic","message":"readiness status must exactly follow blockers and checks"})
        return errors
    if schema_name == "research-telemetry":
        rows = record.get("candidates", []); denominator = record.get("denominator", {}); eligibility = record.get("calibration_eligibility", {})
        errors: list[dict[str, Any]] = []; candidate_ids = [row.get("candidate_id") for row in rows]
        complete = denominator.get("eligible_count") == denominator.get("exported_count") == len(rows) == len(set(candidate_ids))
        derived_reasons: set[str] = set()
        if not rows or not complete: derived_reasons.add("missing_denominator")
        if any(row.get("ex_ante", {}).get("probability") is None for row in rows): derived_reasons.add("missing_ex_ante_probability")
        post_outcome = False
        for row in rows:
            ex_ante = row.get("ex_ante", {}); outcome = row.get("outcome", {})
            if ex_ante.get("recorded_before_outcome") is not True: post_outcome = True
            if outcome.get("recorded_at") and ex_ante.get("recorded_at"):
                post_outcome = post_outcome or datetime.fromisoformat(ex_ante["recorded_at"].replace("Z", "+00:00")) >= datetime.fromisoformat(outcome["recorded_at"].replace("Z", "+00:00"))
        if post_outcome: derived_reasons.add("post_outcome_confidence")
        if any(row.get("outcome", {}).get("independent") is not True for row in rows): derived_reasons.add("missing_independent_outcome")
        if any(row.get("outcome", {}).get("label") == "unresolved" for row in rows): derived_reasons.add("unresolved_outcome")
        if len(rows) < 30: derived_reasons.add("small_sample")
        core_eligible = not derived_reasons
        if denominator.get("complete") != complete or set(eligibility.get("reasons", [])) != derived_reasons or eligibility.get("eligible") != core_eligible or record.get("classification") != ("calibration" if core_eligible else "telemetry"):
            errors.append({"code": "telemetry_classification_mismatch", "instance_path": "/calibration_eligibility", "schema_path": "/semantic", "message": "classification, denominator, and derived calibration traps must agree"})
        if len(candidate_ids) != len(set(candidate_ids)) or any("eligible" not in row.get("funnel_states", []) for row in rows):
            errors.append({"code": "telemetry_denominator_invalid", "instance_path": "/candidates", "schema_path": "/semantic", "message": "each eligible candidate must appear exactly once"})
        funnel_order = ("eligible", "selected", "skipped", "overridden", "held", "deferred", "contaminated", "reopened", "refuted", "confirmed")
        for index_number, row in enumerate(rows):
            history = row.get("funnel_history", []); history_states = {item.get("state") for item in history}; expected_states = [value for value in funnel_order if value in history_states]
            kind_order = {"event": 0, "attempt": 1, "finding": 2, "review": 3}
            history_keys = [(datetime.fromisoformat(item["recorded_at"].replace("Z", "+00:00")), kind_order.get(item.get("source_kind"), 99), item.get("source_sequence", -1), item.get("source_ref", ""), funnel_order.index(item["state"])) for item in history]
            source_revision_valid = all((item.get("source_revision") is not None) == (item.get("source_kind") == "finding") for item in history)
            outcome = row.get("outcome", {}); expected_terminal = "confirmed" if outcome.get("label") == "positive" else ("refuted" if outcome.get("label") == "negative" else None)
            if row.get("funnel_states") != expected_states or not history or history[0].get("state") != "eligible" or history[0].get("recorded_at") != row.get("eligible_at") or history_keys != sorted(history_keys) or not source_revision_valid or (outcome.get("independent") is True and expected_terminal and expected_terminal not in history_states):
                errors.append({"code": "telemetry_history_invalid", "instance_path": f"/candidates/{index_number}/funnel_history", "schema_path": "/semantic", "message": "ordered history must exactly support aggregate funnel states and independent outcome"})
        dimension_coverage = record.get("cost_dimension_coverage", {}); totals = record.get("cost_totals", {})
        invalid_cost = any((coverage.get("measured", 0) < coverage.get("records", 0) and totals.get(field) is not None) or (coverage.get("records", 0) > 0 and coverage.get("measured") == coverage.get("records") and totals.get(field) is None) or coverage.get("measured", 0) > coverage.get("records", 0) for field, coverage in dimension_coverage.items())
        if invalid_cost:
            errors.append({"code": "telemetry_missing_cost_imputed", "instance_path": "/cost_totals", "schema_path": "/semantic", "message": "each cost dimension must remain null unless measured for every contributing record"})
        return errors
    if schema_name != "finding-v3":
        return []
    claims = record.get("claims", {})
    proof = record.get("proof", {})
    claim_ids: list[str] = []
    mechanism = claims.get("mechanism", {})
    reachability = claims.get("reachability", {})
    for value in (mechanism.get("claim_id"), reachability.get("claim_id")):
        if isinstance(value, str):
            claim_ids.append(value)
    for impact in claims.get("impact_claims", []):
        if isinstance(impact, dict) and isinstance(impact.get("claim_id"), str):
            claim_ids.append(impact["claim_id"])
    mapped = [item.get("claim_id") for item in proof.get("claim_proofs", []) if isinstance(item, dict)]
    errors: list[dict[str, Any]] = []
    if len(claim_ids) != len(set(claim_ids)):
        errors.append({"code": "duplicate_claim_id", "instance_path": "/claims", "schema_path": "/semantic", "message": "atomic claim IDs must be unique"})
    if sorted(claim_ids) != sorted(mapped) or len(mapped) != len(set(mapped)):
        errors.append({"code": "claim_proof_mapping_mismatch", "instance_path": "/proof/claim_proofs", "schema_path": "/semantic", "message": "claim_proofs must map every atomic claim exactly once"})
    applicability = proof.get("control_applicability", {})
    requirements = (("negative", "negative_control_refs"), ("positive", "positive_control_refs"), ("replay", "replay_refs"))
    for policy, refs in requirements:
        if applicability.get(policy) == "required" and not proof.get(refs):
            errors.append({"code": "required_control_missing", "instance_path": f"/proof/{refs}", "schema_path": "/semantic", "message": f"{policy} control is required but has no reference"})
    for index_number, mapping in enumerate(proof.get("claim_proofs", [])):
        if not isinstance(mapping, dict):
            continue
        if not mapping.get("attempt_refs") and not mapping.get("artifact_refs"):
            errors.append({"code": "claim_proof_evidence_missing", "instance_path": f"/proof/claim_proofs/{index_number}", "schema_path": "/semantic", "message": "each atomic claim needs an attempt or artifact reference"})
        if (applicability.get("negative") == "required" or applicability.get("positive") == "required") and not mapping.get("control_refs"):
            errors.append({"code": "claim_proof_control_missing", "instance_path": f"/proof/claim_proofs/{index_number}/control_refs", "schema_path": "/semantic", "message": "each atomic claim needs its applicable control binding"})
        if applicability.get("replay") == "required" and not mapping.get("replay_refs"):
            errors.append({"code": "claim_proof_replay_missing", "instance_path": f"/proof/claim_proofs/{index_number}/replay_refs", "schema_path": "/semantic", "message": "each atomic claim needs its applicable replay binding"})
    return errors


def validate_record(record: Any, schema_name: str) -> list[dict[str, Any]]:
    check_dependency_version()
    filename = RECORD_SCHEMA_FILES.get(schema_name)
    if filename is None:
        return [{"code": "unknown_schema", "instance_path": "/", "schema_path": "/", "message": schema_name}]
    documents = _load_schema_documents()
    schema = documents.get(filename)
    if schema is None:
        return [{"code": "missing_schema", "instance_path": "/", "schema_path": "/", "message": filename}]
    try:
        validator = Draft202012Validator(schema, registry=build_registry(documents), format_checker=FormatChecker())
        errors = sorted(validator.iter_errors(record), key=lambda item: (list(item.absolute_path), item.message))
    except Exception as exc:
        return [{"code": "schema_resolution_failed", "instance_path": "/", "schema_path": "/", "message": str(exc)}]
    return [_error_detail(error) for error in errors] + _semantic_record_errors(record, schema_name)


def infer_schema_name(record: Any) -> str | None:
    if not isinstance(record, dict):
        return None
    version = record.get("schema_version")
    if record.get("artifact_type") == "corpus-enumeration" and version == 1:
        return "corpus-enumeration"
    if record.get("document_type") in {"runtime_observation", "flow_export"} and version == 1:
        return "flow-telemetry"
    if "finding_id" in record and version == 3:
        return "finding-v3"
    if "id" in record and "engagement" in record and version in (None, 2):
        return "finding-v2-legacy"
    if "attempt_id" in record and version == 2:
        return "attempt-v2"
    if "negative_result_id" in record:
        return "negative-result"
    if "artifact_id" in record and version == 1:
        return "artifact"
    if "review_id" in record and "inventory_hash" in record and "redaction_attested" in record and version == 1:
        return "migration-artifact-review"
    if "review_id" in record and version == 1:
        return "review"
    if "event_id" in record and version == 1:
        return "engagement-event"
    if "last_event_id" in record and "ledger_hash" in record and version == 1:
        return "state-snapshot"
    if "preflight_id" in record and version == 1:
        return "environment-preflight"
    if "preflight_id" in record and version == 2:
        return "environment-preflight-v2"
    if "report_id" in record and "finding_revision" in record and version == 1:
        return "report-manifest"
    if "disposition_id" in record and version == 1:
        return "memory-disposition"
    if "migration_id" in record and version == 1:
        return "migration-manifest"
    if "export_id" in record and version == 1:
        return "research-telemetry"
    if "matrix_id" in record and version == 1:
        return "historical-case-manifest"
    if "evaluation_id" in record and version == 1:
        return "retrospective-evaluation"
    if "study_id" in record and "arms" in record and version == 1:
        return "ab-preregistration"
    if "report_id" in record and "preregistration_hash" in record and version == 1:
        return "ab-readiness-report"
    if "evidence_id" in record and "holdouts" in record and version == 1:
        return "ab-study-evidence"
    if "id" in record and version in (None, 2):
        return "finding-v2-legacy"
    return None


def resolve_schema_name(record: Any, explicit: str | None = None) -> str:
    inferred = infer_schema_name(record)
    if inferred is None:
        raise RecordError("unknown_record_version", "record identity/schema_version is unknown or ambiguous")
    if explicit and explicit != inferred:
        raise RecordError("schema_dispatch_mismatch", f"record dispatches to {inferred}, not {explicit}")
    return inferred


def _record_identity(record: dict[str, Any]) -> tuple[str, str, int | None] | None:
    identities = (
        ("attempt_id", "attempt"), ("artifact_id", "artifact"), ("review_id", "review"),
        ("preflight_id", "environment"), ("environment_id", "environment"), ("report_id", "report"),
        ("finding_id", "finding"), ("event_id", "event"), ("target_id", "target"), ("disposition_id", "memory-disposition"), ("migration_id", "migration"),
    )
    for key, kind in identities:
        value = record.get(key)
        if isinstance(value, str):
            return value, kind, record.get("revision") if isinstance(record.get("revision"), int) else None
    return None


def build_reference_index(engagement_dir: os.PathLike[str] | str) -> dict[str, list[dict[str, Any]]]:
    root = Path(os.path.abspath(engagement_dir))
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    if len(root.parts) == 4 and root.parts[1:3] == ("dev", "fd") and root.parts[3].isdigit():
        root_fd = os.dup(int(root.parts[3]))
    else:
        try:
            terminal = root.lstat()
            if stat.S_ISLNK(terminal.st_mode) or not stat.S_ISDIR(terminal.st_mode):
                raise RecordError("unsafe_engagement_path", "engagement root must be a directory")
            parent = root.parent.resolve(strict=True)
            root_fd = os.open(parent / root.name, flags)
        except OSError as exc:
            raise RecordError("unsafe_engagement_path", "engagement root could not be opened") from exc

    def read_relative(relative: str) -> bytes:
        parts = Path(relative).parts
        if not parts or any(part in {"", ".", ".."} for part in parts):
            raise RecordError("unsafe_governed_path", relative)
        parent_fd = os.dup(root_fd)
        try:
            for component in parts[:-1]:
                child = os.open(component, flags, dir_fd=parent_fd)
                os.close(parent_fd)
                parent_fd = child
            fd = os.open(parts[-1], os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=parent_fd)
            try:
                before = os.fstat(fd)
                if not stat.S_ISREG(before.st_mode):
                    raise RecordError("unsafe_governed_path", relative)
                chunks: list[bytes] = []
                while True:
                    chunk = os.read(fd, 1024 * 1024)
                    if not chunk:
                        break
                    chunks.append(chunk)
                after = os.fstat(fd)
                if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
                    after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns
                ):
                    raise RecordError("governed_file_changed_during_read", relative)
                return b"".join(chunks)
            finally:
                os.close(fd)
        finally:
            os.close(parent_fd)

    paths: list[str] = []

    def enumerate_records(directory_fd: int, prefix: tuple[str, ...]) -> None:
        """Walk one opened tree with *at syscalls.

        macOS exposes an opened directory as ``/dev/fd/N`` but does not support traversing
        children through that pathname (``os.fwalk`` therefore returns no rows). Keep every
        descent bound to directory descriptors instead of silently producing an empty index.
        """

        for name in sorted(os.listdir(directory_fd)):
            try:
                entry = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            except OSError:
                continue
            relative_parts = (*prefix, name)
            if stat.S_ISDIR(entry.st_mode) and not stat.S_ISLNK(entry.st_mode):
                child_fd = os.open(name, flags, dir_fd=directory_fd)
                try:
                    enumerate_records(child_fd, relative_parts)
                finally:
                    os.close(child_fd)
                continue
            if not stat.S_ISREG(entry.st_mode) or stat.S_ISLNK(entry.st_mode):
                continue
            relative = Path(*relative_parts)
            if relative.suffix == ".json" or (len(prefix) == 0 and relative.suffix == ".jsonl"):
                paths.append(relative.as_posix())

    try:
        enumerate_records(root_fd, ())
    except Exception:
        os.close(root_fd)
        raise

    index: dict[str, list[dict[str, Any]]] = {}
    try:
        for relative in sorted(set(paths)):
            relative_path = Path(relative)
            relative_parts = relative_path.parts
            if (
                relative_path.name in {"state.snapshot.json", "records.index.json", "lifecycle.jsonl"}
                or relative_parts[:1] == ("upstream",)
                or relative_parts[:2] == ("legacy", "zone2-pending")
                or relative_parts[:3] == ("legacy", "quarantine", "ledger-quarantined.json")
                or (relative_path.name.endswith(".action.json") and "authority" in relative_parts and "requests" in relative_parts)
            ):
                continue
            try:
                data = read_relative(relative)
                text = data.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise RecordError("invalid_json", relative) from exc
            records: list[Any]
            if relative_path.suffix == ".jsonl":
                records = []
                for line_number, line in enumerate(text.splitlines(), 1):
                    if not line.strip():
                        continue
                    try:
                        records.append(json.loads(line, object_pairs_hook=_reject_duplicate_pairs))
                    except (json.JSONDecodeError, RecordError) as exc:
                        raise RecordError("invalid_jsonl", f"{relative}:{line_number}: {exc}") from exc
            else:
                try:
                    records = [json.loads(text, object_pairs_hook=_reject_duplicate_pairs)]
                except (json.JSONDecodeError, RecordError) as exc:
                    raise RecordError("invalid_json", relative) from exc
            for record in records:
                if not isinstance(record, dict):
                    continue
                identity = _record_identity(record)
                if identity:
                    entity_id, kind, revision = identity
                    entry = {"type": kind, "engagement_id": record.get("engagement_id") or record.get("engagement"), "revision": revision, "path": relative, "recorded_at": record.get("recorded_at") or record.get("created_at")}
                    index.setdefault(entity_id, []).append(entry)
                if record.get("event_type") == "scope.attested" and isinstance(record.get("engagement_id"), str):
                    entries = index.setdefault(record["engagement_id"], [])
                    if not any(entry["type"] == "engagement" for entry in entries):
                        entries.append({"type": "engagement", "engagement_id": record["engagement_id"], "revision": None, "path": relative, "recorded_at": record.get("recorded_at")})
                if record.get("event_type") == "authority.requested":
                    request_id = record.get("payload", {}).get("request_id")
                    if isinstance(request_id, str):
                        index.setdefault(request_id, []).append({"type": "authority-request", "engagement_id": record.get("engagement_id"), "revision": None, "path": relative, "recorded_at": record.get("recorded_at")})
                if record.get("event_type") in {"candidate.proposed", "hypothesis.created"}:
                    payload = record.get("payload", {})
                    key = "candidate_id" if record["event_type"] == "candidate.proposed" else "hypothesis_id"
                    entity_id = payload.get(key) if isinstance(payload, dict) else None
                    if isinstance(entity_id, str):
                        kind = "candidate" if record["event_type"] == "candidate.proposed" else "hypothesis"
                        index.setdefault(entity_id, []).append({"type": kind, "engagement_id": record.get("engagement_id"), "revision": None, "path": relative, "recorded_at": record.get("recorded_at")})
    finally:
        os.close(root_fd)
    for entity_id, entries in index.items():
        types = {entry["type"] for entry in entries}
        if len(types) > 1:
            raise RecordError("cross_type_record_id_collision", f"ID reused across record types: {entity_id}:{sorted(types)}")
        seen: set[tuple[str, int | None]] = set()
        for entry in entries:
            key = (entry["type"], entry["revision"])
            if key in seen:
                raise RecordError("duplicate_record_id", f"duplicate {entry['type']} ID/revision: {entity_id}")
            seen.add(key)
    return index


def _at(record: dict[str, Any], path: tuple[str, ...]) -> Any:
    current: Any = record
    for part in path:
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def validate_record_references(record: Any, schema_name: str, index: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    if not isinstance(record, dict):
        return []
    engagement_id = record.get("engagement_id") or record.get("engagement")
    specs: dict[str, list[tuple[tuple[str, ...], set[str]]]] = {
        "finding-v3": [
            (("scope_provenance", "environment_ref"), {"environment"}), (("scope_provenance", "target_refs"), {"target"}),
            (("proof", "primary_attempt_refs"), {"attempt"}), (("proof", "negative_control_refs"), {"attempt"}),
            (("proof", "positive_control_refs"), {"attempt"}), (("proof", "replay_refs"), {"attempt"}),
            (("proof", "evidence_refs"), {"attempt", "artifact"}), (("claims", "conflicting_evidence"), {"attempt", "artifact"}),
            (("adjudication", "review_ref"), {"review"}), (("search_linkage", "candidate_refs"), {"candidate"}),
            (("search_linkage", "hypothesis_refs"), {"hypothesis"}),
            (("filing_contract", "privilege_context", "evidence_refs"), {"attempt"}),
            (("filing_contract", "state_provenance", "evidence_refs"), {"attempt"}),
        ],
        "attempt-v2": [
            (("environment_ref",), {"environment"}), (("escalation_confirmation_event_ref",), {"event"}),
            (("hypothesis_ref",), {"hypothesis"}), (("experiment_ref",), {"event", "experiment"}),
            (("start_ref",), {"event"}),
            (("evidence_refs",), {"artifact"}), (("control_of",), {"attempt"}),
        ],
        "negative-result": [
            (("hypothesis_refs",), {"hypothesis"}), (("attempt_refs",), {"attempt"}),
            (("evidence_bundle_ref",), {"artifact"}), (("coverage_ref",), {"event"}),
            (("provenance_ref",), {"event"}), (("reproducibility_ref",), {"event"}),
            (("review_ref",), {"review"}),
        ],
        "artifact": [
            (("target_refs",), {"target"}), (("environment_ref",), {"environment"}),
            (("escalation_confirmation_event_ref",), {"event"}), (("cleanup_obligation_ref",), {"event", "cleanup"}),
            (("precreation_classification_event_ref",), {"event"}), (("supersedes_artifact_id",), {"artifact"}),
        ],
        "review": [
            (("input_refs",), {"attempt", "finding", "artifact", "review", "environment", "report", "event"}),
            (("evidence_refs",), {"attempt", "artifact"}), (("conflicting_evidence",), {"attempt", "artifact"}),
        ],
        "engagement-event": [
            (("evidence_refs",), {"attempt", "artifact"}), (("review_refs",), {"review"}), (("finding_refs",), {"finding"}),
        ],
        "report-manifest": [
            (("finding_id",), {"finding"}), (("adjudication_review_ref",), {"review"}),
        ],
        "environment-preflight": [(("target_refs",), {"target"})],
        "environment-preflight-v2": [(("target_refs",), {"target"})],
        "memory-disposition": [],
    }
    dynamic_specs: list[tuple[tuple[str, ...], Any, set[str]]] = []
    if schema_name == "finding-v3":
        claims = record.get("claims", {})
        for name in ("mechanism", "reachability"):
            dynamic_specs.append((("claims", name, "evidence_refs"), claims.get(name, {}).get("evidence_refs", []), {"attempt", "artifact"}))
        for index_number, impact in enumerate(claims.get("impact_claims", [])):
            dynamic_specs.append((("claims", "impact_claims", str(index_number), "evidence_refs"), impact.get("evidence_refs", []), {"attempt", "artifact"}))
        for index_number, mapping in enumerate(record.get("proof", {}).get("claim_proofs", [])):
            for field, allowed in (("attempt_refs", {"attempt"}), ("artifact_refs", {"artifact"}), ("control_refs", {"attempt"}), ("replay_refs", {"attempt"})):
                dynamic_specs.append((("proof", "claim_proofs", str(index_number), field), mapping.get(field, []), allowed))
        for number, setup in enumerate(record.get("filing_contract", {}).get("state_provenance", {}).get("synthesized_setup", [])):
            dynamic_specs.append((("filing_contract", "state_provenance", "synthesized_setup", str(number), "evidence_refs"), setup.get("evidence_refs", []), {"attempt", "artifact"}))
        legacy = record.get("legacy_import")
        if isinstance(legacy, dict):
            dynamic_specs.append((("legacy_import", "source_artifact_ref"), legacy.get("source_artifact_ref"), {"artifact"}))
    elif schema_name == "review":
        if not (record.get("review_type") == "claim_adjudication" and record.get("entity_ref") == record.get("proposed_finding_id")):
            dynamic_specs.append((("entity_ref",), record.get("entity_ref"), {"attempt", "finding", "artifact", "hypothesis", "candidate", "engagement", "report", "environment"}))
        dynamic_specs.append((("proof_profile_ref",), record.get("proof_profile_ref"), {"artifact"}))
        for index_number, control in enumerate(record.get("control_applicability", [])):
            dynamic_specs.append((("control_applicability", str(index_number), "attempt_ref"), control.get("attempt_ref"), {"attempt"}))
        for index_number, replay in enumerate(record.get("replay_freshness", [])):
            dynamic_specs.append((("replay_freshness", str(index_number), "attempt_ref"), replay.get("attempt_ref"), {"attempt"}))
        for index_number, disposition in enumerate(record.get("hypothesis_dispositions", [])):
            dynamic_specs.append((("hypothesis_dispositions", str(index_number), "hypothesis_ref"), disposition.get("hypothesis_ref"), {"hypothesis"}))
    elif schema_name == "memory-disposition":
        source_types = {"event_refs": {"event"}, "candidate_refs": {"candidate"}, "hypothesis_refs": {"hypothesis"}, "attempt_refs": {"attempt"}, "artifact_refs": {"artifact"}, "review_refs": {"review"}, "finding_refs": {"finding"}, "environment_refs": {"environment"}}
        for field, allowed in source_types.items():
            dynamic_specs.append((("source_refs", field), record.get("source_refs", {}).get(field, []), allowed))
        dynamic_specs.append((("candidate_refs",), record.get("candidate_refs", []), {"candidate", "hypothesis", "review"}))
    elif schema_name == "migration-manifest":
        for index_number, entry in enumerate(record.get("entries", [])):
            dynamic_specs.extend([
                (("entries", str(index_number), "source_artifact_ref"), entry.get("source_artifact_ref"), {"artifact"}),
                (("entries", str(index_number), "imported_finding_id"), entry.get("imported_finding_id"), {"finding"}),
            ])
    elif schema_name == "engagement-event":
        payload = record.get("payload", {})
        dynamic_specs.extend([
            (("payload", "environment_ref"), payload.get("environment_ref"), {"environment"}),
            (("payload", "source_observation_ref"), payload.get("source_observation_ref"), {"event", "attempt"}),
            (("payload", "routing_review_ref"), payload.get("routing_review_ref"), {"event", "review"}),
            (("payload", "candidate_ref"), payload.get("candidate_ref"), {"candidate"}),
            (("payload", "origin_ref"), payload.get("origin_ref"), {"candidate", "event", "review", "finding", "hypothesis"}),
            (("payload", "coverage_review_ref"), payload.get("coverage_review_ref"), {"event"}),
            (("payload", "review_ref"), payload.get("review_ref"), {"review"}),
            (("payload", "adjudication_review_ref"), payload.get("adjudication_review_ref"), {"review"}),
            (("payload", "adjudication_event_ref"), payload.get("adjudication_event_ref"), {"event"}),
            (("payload", "authority_request_ref"), payload.get("authority_request_ref"), {"authority-request"}),
            (("payload", "experiment_refs"), payload.get("experiment_refs", []), {"event", "attempt"}),
            (("payload", "control_refs"), payload.get("control_refs", []), {"attempt"}),
            (("payload", "supporting_evidence_refs"), payload.get("supporting_evidence_refs", []), {"attempt", "artifact"}),
            (("payload", "conflicting_evidence_refs"), payload.get("conflicting_evidence_refs", []), {"attempt", "artifact"}),
            (("payload", "resolves_review_refs"), payload.get("resolves_review_refs", []), {"event"}),
        ])
        negative = payload.get("negative_result")
        if isinstance(negative, dict):
            for field, allowed in (
                ("hypothesis_refs", {"hypothesis"}),
                ("attempt_refs", {"attempt"}),
                ("evidence_bundle_ref", {"artifact"}),
                ("coverage_ref", {"event"}),
                ("provenance_ref", {"event"}),
                ("reproducibility_ref", {"event"}),
                ("review_ref", {"review"}),
            ):
                dynamic_specs.append((("payload", "negative_result", field), negative.get(field), allowed))
        started = payload.get("attempt")
        if isinstance(started, dict):
            dynamic_specs.append((("payload", "attempt", "hypothesis_ref"), started.get("hypothesis_ref"), {"hypothesis"}))
            dynamic_specs.append((("payload", "attempt", "environment_ref"), started.get("environment_ref"), {"environment"}))

    errors: list[dict[str, Any]] = []
    combined = [(path, _at(record, path), allowed) for path, allowed in specs.get(schema_name, [])] + dynamic_specs
    for path, value, allowed in combined:
        refs = value if isinstance(value, list) else ([] if value is None else [value])
        for ref in refs:
            if not isinstance(ref, str):
                continue
            if ref == engagement_id and "engagement" in allowed:
                continue
            candidates = index.get(ref, [])
            same = [item for item in candidates if engagement_id is None or item.get("engagement_id") == engagement_id]
            if not candidates:
                code, message = "unresolved_record_ref", f"reference does not exist: {ref}"
            elif not same:
                code, message = "cross_engagement_ref", f"reference belongs to another engagement: {ref}"
            elif not any(item["type"] in allowed for item in same):
                code, message = "wrong_record_ref_type", f"reference {ref} is not one of {sorted(allowed)}"
            elif schema_name == "review" and path == ("entity_ref",) and record.get("finding_revision") is not None and any(item["type"] == "finding" for item in same) and not any(item["type"] == "finding" and item.get("revision") == record["finding_revision"] for item in same):
                code, message = "stale_finding_revision_ref", f"finding revision does not exist: {ref}@{record['finding_revision']}"
            else:
                continue
            errors.append({"code": code, "instance_path": "/" + "/".join(path), "schema_path": "/references", "message": message})
    return errors


def validate_record_with_references(record: Any, schema_name: str, engagement_dir: os.PathLike[str] | str) -> list[dict[str, Any]]:
    errors = validate_record(record, schema_name)
    if errors:
        return errors
    return validate_record_references(record, schema_name, build_reference_index(engagement_dir))


def validate_fixture_suite(path: Path | None = None) -> dict[str, Any]:
    path = path or ROOT / "fixtures" / "engagement-records" / "suite.json"
    suite = load_json(path)
    if not isinstance(suite, dict) or not isinstance(suite.get("cases"), list):
        raise RecordError("invalid_fixture_suite", f"fixture suite malformed: {path}")
    results = []
    failures = []
    for case in suite["cases"]:
        case_id = case.get("id", "unknown")
        errors = validate_record(case.get("record"), case.get("schema", ""))
        expected_valid = case.get("valid") is True
        passed = (not errors) == expected_valid
        result = {"id": case_id, "passed": passed, "error_codes": sorted({e["code"] for e in errors})}
        results.append(result)
        if not passed:
            failures.append(result)
    return {"case_count": len(results), "failures": failures, "results": results}


def validate_reference_fixture_suite(path: Path | None = None) -> dict[str, Any]:
    path = path or ROOT / "fixtures" / "engagement-records" / "reference-cases.json"
    suite = load_json(path)
    results = []
    failures = []
    for case in suite.get("cases", []):
        errors = validate_record_references(case.get("record"), case.get("schema", ""), case.get("index", {}))
        passed = (not errors) == (case.get("valid") is True)
        result = {"id": case.get("id", "unknown"), "passed": passed, "error_codes": sorted({error["code"] for error in errors})}
        results.append(result)
        if not passed:
            failures.append(result)
    return {"case_count": len(results), "failures": failures, "results": results}


def _legacy_violation_codes(record: Any, schema_errors: list[dict[str, Any]]) -> list[str]:
    codes: set[str] = set()
    if not isinstance(record, dict):
        return ["not_object"]
    if "base_model" in record:
        codes.add("forbidden_base_model")
    if record.get("scope_class") not in ("proxy_safe", "operator_only", "forbidden"):
        codes.add("unsupported_scope_class")
    if record.get("schema_version") != 2:
        codes.add("unexpected_schema_version")
    if schema_errors:
        codes.add("legacy_schema_invalid")
    return sorted(codes)


@contextmanager
def _bound_legacy_inventory_source(engagement: Path):
    """Bind one legacy inventory root without manufacturing coordination state.

    Initialized roots take their existing kernel lock in no-create mode.  The tracked pre-kernel
    benchmark corpus is the explicit compatibility class: it has a regular scope but no lock, so it
    is scanned through one root FD with bound GQ, public-name identity, and no-midscan-lock checks.
    """

    # Delayed imports avoid the engagement_records <-> engagement_state module cycle.
    from engagement_quarantine import inspect_quarantine
    from engagement_state import _open_absolute_directory, bound_engagement_lock

    logical = Path(os.path.abspath(engagement))
    root_fd = _open_absolute_directory(logical)
    bound = Path(f"/dev/fd/{root_fd}")
    opened = os.fstat(root_fd)

    def require_public_identity() -> None:
        try:
            named = os.stat(logical, follow_symlinks=False)
        except OSError as exc:
            raise RecordError(
                "engagement_source_changed", "inventory source directory changed"
            ) from exc
        if (opened.st_dev, opened.st_ino) != (named.st_dev, named.st_ino):
            raise RecordError(
                "engagement_source_changed", "inventory source directory changed"
            )

    try:
        if inspect_quarantine(bound)["quarantined"]:
            raise RecordError(
                "engagement_quarantined", "engagement evidence is quarantined"
            )
        require_public_identity()
        try:
            lock_entry = os.stat(
                ".record-kernel.lock", dir_fd=root_fd, follow_symlinks=False
            )
        except FileNotFoundError:
            lock_entry = None
        if lock_entry is not None and (
            stat.S_ISLNK(lock_entry.st_mode) or not stat.S_ISREG(lock_entry.st_mode)
        ):
            raise RecordError(
                "unsafe_governed_path", "inventory coordination entry is unsafe"
            )

        if lock_entry is not None:
            with bound_engagement_lock(root_fd, create=False) as locked:
                yield locked
                if inspect_quarantine(locked)["quarantined"]:
                    raise RecordError(
                        "engagement_quarantined", "engagement evidence is quarantined"
                    )
                current_lock = os.stat(
                    ".record-kernel.lock", dir_fd=root_fd, follow_symlinks=False
                )
                if (lock_entry.st_dev, lock_entry.st_ino) != (
                    current_lock.st_dev,
                    current_lock.st_ino,
                ):
                    raise RecordError(
                        "engagement_source_changed",
                        "inventory coordination changed during scan",
                    )
                require_public_identity()
            return

        # No-lock legacy compatibility: a newly appearing coordination file means the source
        # changed class during the scan and none of its buffered rows are admissible.
        yield bound
        if inspect_quarantine(bound)["quarantined"]:
            raise RecordError(
                "engagement_quarantined", "engagement evidence is quarantined"
            )
        try:
            os.stat(".record-kernel.lock", dir_fd=root_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise RecordError(
                "engagement_coordination_changed",
                "inventory source acquired coordination during scan",
            )
        require_public_identity()
    finally:
        os.close(root_fd)


def legacy_finding_inventory(root: os.PathLike[str] | str) -> dict[str, Any]:
    """Read and hash local Plane-3 findings without modifying or importing them."""
    from engagement_state import _relative_regular_files, read_governed_file

    root_path = Path(root).resolve()
    engagement_root = root_path / "engagements"
    files: list[dict[str, Any]] = []
    counts = {
        "total": 0,
        "schema_version_2": 0,
        "forbidden_base_model": 0,
        "unsupported_scope_class": 0,
        "legacy_schema_invalid": 0,
        "parse_error": 0,
    }
    for engagement in sorted(path for path in engagement_root.iterdir() if path.is_dir()):
        if engagement.name == "_TEMPLATE":
            continue
        try:
            with _bound_legacy_inventory_source(engagement) as bound:
                engagement_files: list[dict[str, Any]] = []
                engagement_counts = {key: 0 for key in counts}
                for relative in sorted(_relative_regular_files(bound)):
                    parts = Path(relative).parts
                    if (
                        len(parts) < 2
                        or parts[0] != "findings"
                        or Path(relative).suffix.lower() != ".json"
                    ):
                        continue
                    data = read_governed_file(bound / relative)
                    rel = (Path("engagements") / engagement.name / relative).as_posix()
                    item: dict[str, Any] = {
                        "path": rel,
                        "sha256": sha256_bytes(data),
                        "size": len(data),
                    }
                    engagement_counts["total"] += 1
                    try:
                        record = json.loads(
                            data.decode("utf-8"),
                            object_pairs_hook=_reject_duplicate_pairs,
                        )
                        errors = validate_record(record, "finding-v2-legacy")
                        violations = _legacy_violation_codes(record, errors)
                        if isinstance(record, dict) and record.get("schema_version") == 2:
                            engagement_counts["schema_version_2"] += 1
                        for key in ("forbidden_base_model", "unsupported_scope_class", "legacy_schema_invalid"):
                            if key in violations:
                                engagement_counts[key] += 1
                        item["schema_version"] = record.get("schema_version") if isinstance(record, dict) else None
                        item["violations"] = violations
                    except (UnicodeDecodeError, json.JSONDecodeError, RecordError):
                        engagement_counts["parse_error"] += 1
                        item["violations"] = ["parse_error"]
                        item["error"] = "legacy finding is invalid JSON"
                    engagement_files.append(item)
        except (OSError, RecordError):
            continue
        # The source context's final public-identity/GQ check is the admission point.
        files.extend(engagement_files)
        for key, value in engagement_counts.items():
            counts[key] += value
    corpus_material = b"".join(
        f"{item['path']}\0{item['sha256']}\0{item['size']}\n".encode("utf-8") for item in files
    )
    return {
        "schema_version": 1,
        "inventory_kind": "legacy_finding_read_only",
        "source_root_hash": sha256_bytes(corpus_material),
        "counts": counts,
        "files": files,
    }


def write_canonical_json(path: os.PathLike[str] | str, value: Any) -> None:
    from engagement_quarantine import atomic_write_offline

    atomic_write_offline(Path(path), canonical_json_bytes(value))


def summarize_errors(errors: Iterable[dict[str, Any]]) -> str:
    return "; ".join(f"{error['code']} {error.get('instance_path', '/')}: {error['message']}" for error in errors)
