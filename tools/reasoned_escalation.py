"""Fail-closed admission for a proposed higher-impact hypothesis route."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from engagement_records import RecordError, canonical_json_bytes, sha256_bytes, sha256_file


RUNGS = ("self", "stored/persistent", "cross-user")


def _moment(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def route_digest(route: dict[str, Any]) -> str:
    return sha256_bytes(canonical_json_bytes(route))


def _scope_section(text: str, title: str) -> str:
    match = re.search(rf"^## {re.escape(title)}\s*$([\s\S]*?)(?=^## |\Z)", text, re.MULTILINE)
    return match.group(1) if match else ""


def _checked(section: str, value: str) -> bool:
    return bool(value and re.search(rf"^- \[[xX]\] {re.escape(value)}\s*$", section, re.MULTILINE))


def _snapshot_has_safe_signal(card_id: str, digest: str, snapshot: str) -> bool:
    if not isinstance(snapshot, str) or sha256_bytes(snapshot.encode("utf-8")) != digest:
        return False
    front = snapshot.split("---", 2)
    return bool(len(front) >= 3 and re.search(rf"^id:\s*{re.escape(card_id)}\s*$", front[1], re.MULTILINE) and re.search(r"^safe_signal:\s*\n(?:[ \t]+[^\n]*\n)*[ \t]+proxy:\s*>?\s*\n[ \t]+\S", front[1], re.MULTILINE))


def current_card_matches(route: dict[str, Any]) -> bool:
    """Bind a new proposal to the installed card before any ledger write."""

    card_id, digest, snapshot = route.get("safe_signal_card_id"), route.get("safe_signal_card_digest"), route.get("safe_signal_card_snapshot")
    if not isinstance(card_id, str) or not isinstance(digest, str) or not _snapshot_has_safe_signal(card_id, digest, snapshot):
        return False
    root = Path(__file__).resolve().parents[1] / "skills" / "vulns"
    for path in root.glob("*/SKILL.md"):
        try:
            if sha256_file(path) == digest and path.read_text(encoding="utf-8") == snapshot:
                return True
        except (OSError, UnicodeDecodeError, RecordError):
            continue
    return False


def route_holds(
    engagement: Path,
    route: dict[str, Any],
    state: dict[str, Any],
    evidence: dict[str, dict[str, Any]],
    *,
    proposed_at: str,
) -> list[str]:
    """Return machine-readable reasons why the proposed route cannot be dispatched."""

    reasons: list[str] = []
    scope_hash = state.get("scope_hash")
    environment_ref = state.get("active_environment_ref")
    if route.get("scope_hash") != scope_hash or route.get("environment_ref") != environment_ref or not environment_ref:
        reasons.append("higher_impact_authority_stale")
    snapshot = engagement / "scope-attestations" / f"{str(scope_hash).removeprefix('sha256:')}.md"
    try:
        # Reducer mutations use /dev/fd/N as a bound root. The governed reader
        # resolves that root without following an attacker-controlled path.
        from engagement_state import read_governed_file
        data = read_governed_file(snapshot)
        if sha256_bytes(data) != scope_hash:
            raise ValueError("scope snapshot digest")
        scope = data.decode("utf-8")
    except (OSError, UnicodeDecodeError, ValueError, RecordError):
        scope = ""
        reasons.append("higher_impact_scope_snapshot_invalid")

    surfaces = _scope_section(scope, "Surfaces in scope")
    objectives = _scope_section(scope, "Benign safe-objective set")
    escalation = _scope_section(scope, "Escalation ceiling")
    ceiling_matches = re.findall(r"^- self → stored/persistent → cross-user: ceiling = `([^`]+)`\s*$", escalation, re.MULTILINE)
    ceiling = ceiling_matches[0] if len(ceiling_matches) == 1 else None
    rung = route.get("effect_rung")
    if ceiling not in RUNGS or rung not in RUNGS or RUNGS.index(rung) > RUNGS.index(ceiling):
        reasons.append("higher_impact_effect_ceiling_exceeded")
    if not _checked(surfaces, str(route.get("surface", ""))):
        reasons.append("higher_impact_surface_out_of_scope")
    if not _checked(objectives, str(route.get("safe_signal_objective", ""))):
        reasons.append("higher_impact_safe_objective_out_of_scope")

    card_id, card_digest, card_snapshot = route.get("safe_signal_card_id"), route.get("safe_signal_card_digest"), route.get("safe_signal_card_snapshot")
    if not isinstance(card_id, str) or not isinstance(card_digest, str) or not _snapshot_has_safe_signal(card_id, card_digest, card_snapshot):
        reasons.append("higher_impact_safe_signal_missing")
    for field, code in (("source_output", "higher_impact_source_output_missing"), ("target_precondition", "higher_impact_target_precondition_missing"), ("discriminating_test", "higher_impact_discriminating_test_missing"), ("control_plan", "higher_impact_control_plan_missing")):
        if not isinstance(route.get(field), str) or not route[field].strip():
            reasons.append(code)

    refs = route.get("evidence_refs")
    if not isinstance(refs, list) or not refs or len(refs) != len(set(refs)):
        reasons.append("higher_impact_evidence_missing")
    else:
        for ref in refs:
            row = evidence.get(ref)
            if not isinstance(row, dict) or _moment(row["recorded_at"]) > _moment(proposed_at) or row.get("scope_hash") != scope_hash or row.get("environment_ref") != environment_ref:
                reasons.append("higher_impact_evidence_stale")
                break
    return sorted(set(reasons))
