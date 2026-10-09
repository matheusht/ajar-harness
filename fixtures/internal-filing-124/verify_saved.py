#!/usr/bin/env python3
"""Check the saved internal filing result without trusting the test verdict."""

import argparse
import hashlib
import json
from pathlib import Path


def canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


def digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def ledger(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_bytes().splitlines() if line]


def chained(rows: list[dict]) -> bool:
    return all(row["sequence"] == index + 1
               and row["previous_hash"] == (rows[index - 1]["record_hash"] if index else None)
               and digest(canonical({key: value for key, value in row.items() if key != "record_hash"})) == row["record_hash"]
               for index, row in enumerate(rows))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    root = parser.parse_args().output.resolve()
    engagement = root / "engagement"
    result = json.loads((root / "result.json").read_bytes())
    events = ledger(engagement / "events.jsonl")
    attempts = ledger(engagement / "attempts.jsonl")
    artifacts = ledger(engagement / "artifacts.jsonl")
    state = json.loads((engagement / "state.snapshot.json").read_bytes())
    finding = json.loads((engagement / "findings/F-canonical-public/rev-1.json").read_bytes())
    proposal = (root / "finding-proposal.json").read_bytes()
    manifest_bytes = (engagement / "reports/F-canonical-public-r1.manifest.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    report = (engagement / manifest["report_path"]).read_bytes()
    approvals = [row for row in events if row["event_type"] == "authority.resolved" and row["actor"]["role"] == "broker"]
    revisions = [row for row in events if row["event_type"] == "finding.revised"]
    generated = [row for row in events if row["event_type"] == "report.generated"]
    checks = {
        "signed_v2_scope": "- Signed: [x]" in (engagement / "scope.md").read_text() and "decision-0006-v2" in (engagement / "scope.md").read_text(),
        "ledger_chains": chained(events) and chained(attempts) and chained(artifacts),
        "independent_confirmed_review": state["claim_adjudications"][finding["finding_id"]]["status"] == "confirmed" and len(list((engagement / "reviews").glob("review-*.json"))) == 2,
        "broker_internal_approvals_only": len(approvals) == 2 and {row["payload"]["request_id"] for row in approvals} == {"request-internal-finding", "request-internal-report"} and all(row["payload"].get("scope_derived") is True for row in approvals),
        "one_confirmed_finding": len(revisions) == 1 and state["findings"][finding["finding_id"]]["status"] == "confirmed" and digest(canonical(finding)) == state["findings"][finding["finding_id"]]["digest"] == digest(proposal),
        "one_draft_report": len(generated) == 1 and state["reports"][manifest["report_id"]]["status"] == "draft" and digest(canonical(manifest)) == generated[0]["payload"]["report_manifest_digest"] and digest(report) == manifest["report_digest"],
        "exact_authority_links": revisions[0]["payload"]["authority_request_ref"] == "request-internal-finding" and generated[0]["payload"]["authority_request_ref"] == "request-internal-report",
        "retries_idempotent": result["finding_replayed"] is True and result["report_replayed"] is True and len(revisions) == len(generated) == 1,
        "negative_cases": result["denials"] == {"unconfirmed_target": "revise_finding_v2_target_stale", "wrong_broker": "runtime_provenance_not_principal_bound", "incomplete_report": "internal_report_claim_partition_invalid", "external_accept": "internal_authority_action_forbidden", "changed_report_retry": "approved_authority_request_required", "unrequested_accept": "internal_authority_request_invalid"},
        "no_external_effect": not state["submission_refs"] and not any(row["event_type"] in {"report.accepted", "submission.recorded"} for row in events),
        "local_synthetic_only": result["provider"] == "none" and result["target_contact"] is False,
    }
    print(json.dumps({"valid": all(checks.values()), "checks": checks, "source_head": result["source_head"]}, sort_keys=True))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
