#!/usr/bin/env python3
"""Focused contract tests for the registered frozen-corpus denominator."""

from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from corpus_enumeration import CAVEAT, COLUMNS
from engagement_records import RecordError, resolve_schema_name, sha256_bytes
from frozen_corpus import require_enumerated_count_matches, resolve_frozen_corpus_denominator


EVENT_TIME = "2026-08-28T12:00:00Z"
SCOPE_ATTESTED_AT = "2026-08-28T11:00:00Z"


def _artifact_record(
    artifact_id: str,
    relative_path: str,
    data: bytes,
    *,
    sequence: int,
    created_at: str = "2026-08-28T11:00:00Z",
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "sequence": sequence,
        "previous_hash": None if sequence == 1 else "sha256:" + "1" * 64,
        "record_hash": "sha256:" + str(sequence) * 64,
        "artifact_id": artifact_id,
        "engagement_id": "engagement-frozen-corpus-test",
        "relative_path": relative_path,
        "sha256": sha256_bytes(data),
        "size": len(data),
        "media_type": "application/json" if relative_path.endswith(".json") else "text/tab-separated-values",
        "created_at": created_at,
        "producer": {"role": "orchestrator", "id": "orchestrator-test"},
        "acquisition_method": "generated_local",
        "target_refs": [],
        "environment_ref": None,
        "sensitivity": "internal",
        "redaction_status": "not_needed",
        "contains_executable_capability": False,
        "advisory_zone": "clear_local",
        "escalation_confirmation_event_ref": None,
        "cleanup_obligation_ref": None,
        "immutable": True,
        "supersedes_artifact_id": None,
    }


def _tsv() -> bytes:
    rows = [
        ["enumerated", "alpha", "1.0.0", "a" * 40, "index.js", "declared", "1" * 64],
        ["enumerated", "alpha", "1.0.0", "a" * 40, "extra.js", "undeclared-published", "2" * 64],
        ["enumerated", "beta", "2.0.0", "b" * 40, "main.js", "declared", "3" * 64],
    ]
    lines = [CAVEAT, "\t".join(COLUMNS), *("\t".join(row) for row in rows)]
    return ("\n".join(lines) + "\n").encode("utf-8")


def _manifest(tsv: bytes) -> bytes:
    digest = hashlib.sha256(tsv).hexdigest()
    linked = {"path": "corpus-enumeration.tsv", "sha256": digest}
    document = {
        "schema_version": 1,
        "artifact_type": "corpus-enumeration",
        "frozen_at": "2026-08-28T10:00:00Z",
        "generated_by": {
            "tool": "tools/corpus_enumeration.py",
            "tool_sha256": "4" * 64,
            "mode": "syntactic",
            "model_involvement": False,
            "parser_versions": {
                "tree-sitter": "test",
                "tree-sitter-javascript": "test",
                "tree-sitter-typescript": "test",
            },
        },
        "granularity": ["package", "entrypoint"],
        "columns": COLUMNS,
        "coverage_semantics": {
            "closes_on": "visitation",
            "does_not_establish": "understanding",
            "necessary_for_coverage": True,
            "sufficient_for_coverage": False,
        },
        "artifact": {**linked, "row_count": 3, "package_count": 2},
        "source": {"pins_path": "package-pins.tsv", "tarballs_path": "tarballs"},
        "frozen_inputs_base": "manifest",
        "frozen_inputs": {
            "corpus-enumeration": linked,
            "package-pins": {"path": "package-pins.tsv", "sha256": "5" * 64},
            "enumerator": {"path": "../../tools/corpus_enumeration.py", "sha256": "4" * 64},
            "schema": {"path": "../../schemas/corpus-enumeration.schema.json", "sha256": "6" * 64},
            "tarball:0000": {"path": "tarballs/alpha.tgz", "sha256": "7" * 64},
        },
    }
    return (json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _signed_scope(pin: str | None, *, signed: bool = True, duplicate: bool = False) -> bytes:
    pin_line = "" if pin is None else f"- Frozen corpus enumeration SHA256: `{pin}`\n"
    if duplicate:
        pin_line += pin_line
    return (
        "# scope\n"
        f"{pin_line}"
        "- Operator: operator-test\n"
        "- Date: 2026-08-28\n"
        f"- Signed: [{'x' if signed else ' '}]\n"
    ).encode("utf-8")


class FrozenCorpusDenominatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.engagement = Path(self.temp.name) / "engagement"
        evidence = self.engagement / "evidence"
        evidence.mkdir(parents=True)
        self.tsv = _tsv()
        self.manifest = _manifest(self.tsv)
        (evidence / "corpus-enumeration.tsv").write_bytes(self.tsv)
        (evidence / "corpus-enumeration.freeze.json").write_bytes(self.manifest)
        self.artifacts = [
            _artifact_record(
                "artifact-corpus-manifest",
                "evidence/corpus-enumeration.freeze.json",
                self.manifest,
                sequence=1,
            ),
            _artifact_record(
                "artifact-corpus-tsv",
                "evidence/corpus-enumeration.tsv",
                self.tsv,
                sequence=2,
            ),
        ]
        self.scope_bytes = _signed_scope(sha256_bytes(self.manifest))

    def tearDown(self) -> None:
        self.temp.cleanup()

    def resolve(
        self,
        artifacts: list[dict[str, object]] | None = None,
        *,
        scope_bytes: bytes | None = None,
        scope_attested_at: str = SCOPE_ATTESTED_AT,
    ) -> dict[str, object]:
        return resolve_frozen_corpus_denominator(
            self.engagement,
            self.artifacts if artifacts is None else artifacts,
            "artifact-corpus-manifest",
            EVENT_TIME,
            self.scope_bytes if scope_bytes is None else scope_bytes,
            scope_attested_at,
        )

    def test_registered_freeze_returns_exact_row_denominator(self) -> None:
        denominator = self.resolve()
        self.assertEqual(resolve_schema_name(json.loads(self.manifest)), "corpus-enumeration")
        self.assertEqual(denominator["row_count"], 3)
        self.assertEqual(denominator["package_count"], 2)
        self.assertEqual(denominator["enumeration_artifact_ref"], "artifact-corpus-tsv")
        require_enumerated_count_matches(3, denominator)
        with self.assertRaisesRegex(RecordError, "enumerated_count=1; frozen row_count=3"):
            require_enumerated_count_matches(1, denominator)

    def test_manifest_and_linked_tsv_must_both_be_registered(self) -> None:
        with self.assertRaisesRegex(RecordError, "artifact-corpus-missing"):
            resolve_frozen_corpus_denominator(
                self.engagement,
                self.artifacts,
                "artifact-corpus-missing",
                EVENT_TIME,
                self.scope_bytes,
                SCOPE_ATTESTED_AT,
            )
        with self.assertRaisesRegex(RecordError, "evidence/corpus-enumeration.tsv"):
            self.resolve(self.artifacts[:1])

    def test_tampered_registered_bytes_fail_closed(self) -> None:
        path = self.engagement / "evidence" / "corpus-enumeration.tsv"
        tampered = bytearray(path.read_bytes())
        tampered[-2] = ord("4")
        path.write_bytes(tampered)
        with self.assertRaises(RecordError) as raised:
            self.resolve()
        self.assertEqual(raised.exception.code, "frozen_corpus_artifact_digest_mismatch")

    def test_registered_but_missing_file_fails_closed(self) -> None:
        (self.engagement / "evidence" / "corpus-enumeration.tsv").unlink()
        with self.assertRaises(RecordError) as raised:
            self.resolve()
        self.assertEqual(raised.exception.code, "frozen_corpus_artifact_unavailable")

    def test_future_manifest_or_tsv_registration_fails_closed(self) -> None:
        for index in (0, 1):
            with self.subTest(artifact=self.artifacts[index]["artifact_id"]):
                artifacts = copy.deepcopy(self.artifacts)
                artifacts[index]["created_at"] = "2026-08-28T12:00:01Z"
                with self.assertRaises(RecordError) as raised:
                    self.resolve(artifacts)
                self.assertEqual(raised.exception.code, "frozen_corpus_artifact_from_future")

    def test_manifest_must_be_frozen_before_genesis_scope_attestation(self) -> None:
        document = json.loads(self.manifest)
        document["frozen_at"] = "2026-08-28T11:00:01Z"
        late_manifest = (
            json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n"
        ).encode("utf-8")
        (self.engagement / "evidence/corpus-enumeration.freeze.json").write_bytes(
            late_manifest
        )
        artifacts = copy.deepcopy(self.artifacts)
        artifacts[0]["sha256"] = sha256_bytes(late_manifest)
        artifacts[0]["size"] = len(late_manifest)
        with self.assertRaises(RecordError) as raised:
            self.resolve(
                artifacts,
                scope_bytes=_signed_scope(sha256_bytes(late_manifest)),
            )
        self.assertEqual(
            raised.exception.code,
            "frozen_corpus_manifest_not_precommitted",
        )

    def test_scope_pin_is_required_and_must_match_registered_manifest(self) -> None:
        cases = (
            ("missing", _signed_scope(None), "frozen_corpus_scope_pin_missing"),
            ("none", _signed_scope("none"), "frozen_corpus_scope_pin_none"),
            (
                "mismatch",
                _signed_scope("sha256:" + "f" * 64),
                "frozen_corpus_scope_pin_mismatch",
            ),
            (
                "duplicate",
                _signed_scope(sha256_bytes(self.manifest), duplicate=True),
                "frozen_corpus_scope_pin_ambiguous",
            ),
        )
        for label, scope_bytes, expected_code in cases:
            with self.subTest(case=label):
                with self.assertRaises(RecordError) as raised:
                    self.resolve(scope_bytes=scope_bytes)
                self.assertEqual(raised.exception.code, expected_code)

    def test_scope_bytes_must_be_signed(self) -> None:
        with self.assertRaises(RecordError) as raised:
            self.resolve(scope_bytes=_signed_scope(sha256_bytes(self.manifest), signed=False))
        self.assertEqual(raised.exception.code, "frozen_corpus_scope_unsigned")


if __name__ == "__main__":
    unittest.main()
