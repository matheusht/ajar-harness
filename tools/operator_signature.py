#!/usr/bin/env python3
"""Canonical operator-signature proof helpers for replay-verifiable authority events."""

from __future__ import annotations

import base64
import copy
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from engagement_records import RecordError, canonical_json_bytes, detect_secret_classes, sha256_bytes


OPERATOR_NAMESPACE = "llm-redteam-harness-operator-v1"
OPERATOR_SIGNATURE_MAX_BYTES = 256 * 1024
OPERATOR_ALLOWED_SIGNERS_MAX_BYTES = 1024 * 1024
SSH_VERIFY_TIMEOUT_SECONDS = 5.0


def operator_challenge_bytes(
    *,
    engagement_id: str,
    scope_hash: str,
    ledger_hash: str | None,
    operation: str,
    operator_id: str,
) -> bytes:
    return canonical_json_bytes({
        "schema_version": 1,
        "namespace": OPERATOR_NAMESPACE,
        "engagement_id": engagement_id,
        "scope_hash": scope_hash,
        "ledger_hash": ledger_hash,
        "operation": operation,
        "operator_id": operator_id,
    })


def ending_override_action(
    *,
    engagement_id: str,
    recorded_at: str,
    actor: dict[str, Any],
    payload: dict[str, Any],
    entity_refs: list[str],
    evidence_refs: list[str],
    state_changes: list[dict[str, Any]],
    session_id: str,
) -> dict[str, Any]:
    """Return every authority-relevant override field, excluding only its proof bytes."""

    unsigned_payload = copy.deepcopy(payload)
    unsigned_payload.pop("operator_signature", None)
    return {
        "command": "override-ending",
        "event_type": "engagement.ending_overridden",
        "operation_class": "authority",
        "engagement_id": engagement_id,
        "recorded_at": recorded_at,
        "actor": copy.deepcopy(actor),
        "session_id": session_id,
        "payload": unsigned_payload,
        "entity_refs": copy.deepcopy(entity_refs),
        "evidence_refs": copy.deepcopy(evidence_refs),
        "state_changes": copy.deepcopy(state_changes),
    }


def _scope_signer_pin(scope_bytes: bytes) -> str:
    matches = re.findall(
        rb"^\s*-\s*Operator allowed signers SHA256:\s*(sha256:[0-9a-f]{64})\s*$",
        scope_bytes,
        re.MULTILINE,
    )
    if len(matches) != 1:
        raise RecordError("operator_signature_invalid", "scope operator signer pin is unavailable")
    return matches[0].decode("ascii")


def verify_operator_signature_bytes(
    *,
    scope_bytes: bytes,
    operator_id: str,
    challenge_bytes: bytes,
    signature_bytes: bytes,
    allowed_signers_bytes: bytes,
    timeout_seconds: float = SSH_VERIFY_TIMEOUT_SECONDS,
) -> str:
    """Verify exact bytes and return the signing key fingerprint as a hex SHA-256."""

    if (
        not isinstance(scope_bytes, bytes)
        or not isinstance(challenge_bytes, bytes)
        or not isinstance(signature_bytes, bytes)
        or not isinstance(allowed_signers_bytes, bytes)
        or not signature_bytes
        or not allowed_signers_bytes
        or len(signature_bytes) > OPERATOR_SIGNATURE_MAX_BYTES
        or len(allowed_signers_bytes) > OPERATOR_ALLOWED_SIGNERS_MAX_BYTES
        or bool(detect_secret_classes(signature_bytes))
        or bool(detect_secret_classes(allowed_signers_bytes))
        or not isinstance(timeout_seconds, (int, float))
        or isinstance(timeout_seconds, bool)
        or timeout_seconds <= 0
        or sha256_bytes(allowed_signers_bytes) != _scope_signer_pin(scope_bytes)
    ):
        raise RecordError("operator_signature_invalid", sha256_bytes(challenge_bytes))
    with tempfile.TemporaryDirectory(prefix="operator-signature-proof-") as temporary:
        root = Path(temporary)
        signature = root / "operator.sig"
        signers = root / "allowed_signers"
        signature.write_bytes(signature_bytes)
        signers.write_bytes(allowed_signers_bytes)
        try:
            result = subprocess.run(
                [
                    "/usr/bin/ssh-keygen",
                    "-Y",
                    "verify",
                    "-f",
                    str(signers),
                    "-I",
                    operator_id,
                    "-n",
                    OPERATOR_NAMESPACE,
                    "-s",
                    str(signature),
                ],
                input=challenge_bytes,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"},
                check=False,
                timeout=timeout_seconds,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RecordError("operator_signature_invalid", sha256_bytes(challenge_bytes)) from exc
    if result.returncode != 0:
        raise RecordError("operator_signature_invalid", sha256_bytes(challenge_bytes))
    fingerprint = re.search(rb"\bkey\s+SHA256:([A-Za-z0-9+/=]+)\s*$", result.stdout.strip())
    if fingerprint is None:
        raise RecordError("operator_signature_identity_unavailable", operator_id)
    try:
        digest = base64.b64decode(
            fingerprint.group(1) + b"=" * (-len(fingerprint.group(1)) % 4),
            validate=True,
        )
    except ValueError as exc:
        raise RecordError("operator_signature_identity_unavailable", operator_id) from exc
    if len(digest) != 32:
        raise RecordError("operator_signature_identity_unavailable", operator_id)
    return "sha256:" + digest.hex()


def encode_operator_signature_proof(
    *,
    challenge_bytes: bytes,
    signature_bytes: bytes,
    allowed_signers_bytes: bytes,
    signer_fingerprint: str,
) -> dict[str, str]:
    return {
        "challenge_digest": sha256_bytes(challenge_bytes),
        "signature_base64": base64.b64encode(signature_bytes).decode("ascii"),
        "allowed_signers_base64": base64.b64encode(allowed_signers_bytes).decode("ascii"),
        "signer_fingerprint": signer_fingerprint,
    }


def verify_embedded_operator_signature(
    *,
    proof: Any,
    scope_bytes: bytes,
    operator_id: str,
    challenge_bytes: bytes,
) -> str:
    if not isinstance(proof, dict) or set(proof) != {
        "challenge_digest",
        "signature_base64",
        "allowed_signers_base64",
        "signer_fingerprint",
    }:
        raise RecordError("operator_signature_invalid", sha256_bytes(challenge_bytes))
    try:
        signature_bytes = base64.b64decode(proof["signature_base64"], validate=True)
        allowed_signers_bytes = base64.b64decode(proof["allowed_signers_base64"], validate=True)
    except (TypeError, ValueError) as exc:
        raise RecordError("operator_signature_invalid", sha256_bytes(challenge_bytes)) from exc
    if proof.get("challenge_digest") != sha256_bytes(challenge_bytes):
        raise RecordError("operator_signature_invalid", sha256_bytes(challenge_bytes))
    fingerprint = verify_operator_signature_bytes(
        scope_bytes=scope_bytes,
        operator_id=operator_id,
        challenge_bytes=challenge_bytes,
        signature_bytes=signature_bytes,
        allowed_signers_bytes=allowed_signers_bytes,
    )
    if proof.get("signer_fingerprint") != fingerprint:
        raise RecordError("operator_signature_identity_mismatch", operator_id)
    return fingerprint
