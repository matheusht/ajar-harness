#!/usr/bin/env python3
"""Issue #85 contract checks for the canonical filing evidence predicate."""

from __future__ import annotations

import copy
import subprocess
import sys
from pathlib import Path

from engagement_records import RecordError
from engagement_state import require_filing_corpus_quality, validate_filing_evidence


ROOT = Path(__file__).resolve().parents[1]


def expect(code: str | None, finding: dict, attempts: list[dict]) -> None:
    try:
        validate_filing_evidence(finding, attempts=attempts, artifacts=[])
    except RecordError as exc:
        assert exc.code == code, (exc.code, code)
    else:
        assert code is None, f"expected {code}"


def main() -> int:
    synthetic_corpus = [
        {"review_id": f"review-{index}", "review_type": "claim_adjudication", "proposed_finding_id": f"F-{index}", "entity_ref": f"F-{index}", "recorded_at": "2026-09-22T00:00:00Z", "input_hash": "sha256:" + "a" * 64, "verdict": "supported", "rationale": "Generated support.", "corrections": [], "conflicting_evidence": [], "independence": {"reviewer_id": "same-reviewer"}}
        for index in range(3)
    ]
    require_filing_corpus_quality(2, synthetic_corpus, "historical-v2-replay")
    try:
        require_filing_corpus_quality(3, synthetic_corpus, "new-v3-activation")
    except RecordError as exc:
        assert exc.code == "filing_review_corpus_quality_invalid"
    else:
        raise AssertionError("new v3 activation accepted a synthetic committed review corpus")
    primary = {
        "attempt_id": "attempt-primary",
        "kind": "primary",
        "assessment": "suspected_signal",
        "observation": {"source": "runtime"},
        "scope_hash": "sha256:" + "a" * 64,
        "environment_ref": "env-1",
        "contamination": {"status": "none_observed"},
        "control_of": [],
        "execution_context": {"privilege_position": "authenticated-user", "impact_state": {"mode": "real-path", "synthesized_setup": []}},
    }
    base = {
        "claim_state": "supported",
        "classification": {"severity": {"label": "medium", "system": "cvss:3.1", "vector": "CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:U/C:L/I:L/A:N", "score": 5.4}},
        "scope_provenance": {"scope_hash": primary["scope_hash"], "environment_ref": "env-1"},
        "proof": {"primary_attempt_refs": ["attempt-primary"]},
        "adjudication": {"review_ref": "review-independent"},
        "privilege_context": {"claimed_position": "authenticated-user", "execution_position": "authenticated-user", "evidence_refs": ["attempt-primary"]},
        "state_provenance": {"mode": "real-path", "evidence_refs": ["attempt-primary"], "synthesized_setup": []},
    }
    expect(None, base, [primary])
    missing_privilege = copy.deepcopy(base); missing_privilege.pop("privilege_context")
    expect("filing_privilege_context_invalid", missing_privilege, [primary])
    elevated = copy.deepcopy(base); elevated["privilege_context"]["execution_position"] = "admin"
    expect("filing_privilege_context_invalid", elevated, [primary])
    contradictory = copy.deepcopy(base); contradictory_attempt = copy.deepcopy(primary); contradictory_attempt["attempt_id"] = "attempt-root"; contradictory_attempt["execution_context"]["privilege_position"] = "root"; contradictory["proof"]["primary_attempt_refs"].append("attempt-root"); contradictory["privilege_context"]["evidence_refs"].append("attempt-root")
    expect("filing_privilege_context_invalid", contradictory, [primary, contradictory_attempt])
    unrelated = copy.deepcopy(base); unrelated["privilege_context"]["evidence_refs"] = ["attempt-other"]; other = copy.deepcopy(primary); other["attempt_id"] = "attempt-other"
    expect("filing_privilege_context_invalid", unrelated, [primary, other])
    synthesized = copy.deepcopy(base); synthesized["state_provenance"]["mode"] = "synthesized"
    expect("filing_state_provenance_invalid", synthesized, [primary])
    forged_none = copy.deepcopy(base); forged_none["state_provenance"]["mode"] = "none-required"
    expect("filing_state_provenance_invalid", forged_none, [primary])
    seeded = copy.deepcopy(base); seeded["state_provenance"]["synthesized_setup"] = [{"element": "ordinary fixture account", "reachability_basis": "created through the normal account flow"}]
    expect("filing_state_provenance_invalid", seeded, [primary])
    bad_score = copy.deepcopy(base); bad_score["classification"]["severity"]["score"] = 9.9
    expect("filing_severity_invalid", bad_score, [primary])
    for state in ("refuted", "contaminated"):
        negative = copy.deepcopy(base)
        negative["claim_state"] = state
        negative["classification"]["severity"] = {"label": "informational", "system": "none", "vector": None, "score": None}
        negative["privilege_context"] = {"claimed_position": "not-established", "execution_position": "not-established", "evidence_refs": []}
        negative["state_provenance"] = {"mode": "not-established", "evidence_refs": [], "synthesized_setup": []}
        expect(None, negative, [primary])

    help_text = subprocess.run(
        [sys.executable, str(ROOT / "tools/finding_lifecycle.py"), "promote", "--help"],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout
    assert "inspection-only" in help_text.lower()
    print("filing activation checks: 14 passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
