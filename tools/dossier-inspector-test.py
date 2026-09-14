#!/usr/bin/env python3
"""Static, harmless document metadata fixtures; no lifecycle or kernel setup calls."""
from pathlib import Path
import copy
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone

from engagement_records import canonical_json_bytes, sha256_bytes
from engagement_state import reduce_engagement
from engagement_views import render_views


def snapshot(root):
    return {str(p.relative_to(root)): ("directory" if p.is_dir() else p.read_bytes()) for p in root.rglob("*")}


def static_dossier(root):
    root.mkdir()
    scope = b"""# Synthetic document-review metadata only
- Record kernel: `decision-0005-v1`
## Surfaces in scope
Invented workshop document text in this disposable fixture.
## Benign safe-objective set
Explain existing document revision metadata only.
## Escalation ceiling
None. No target operation or lifecycle execution.
## Impact-demo authorization
No.
## Accounts / fixtures
No accounts; static local data only.
## Authorization
- Operator: synthetic-operator
- Date: 2026-09-05
- Signed: [x]
"""
    digest = sha256_bytes(scope)
    attestation = f"scope-attestations/{digest.removeprefix('sha256:')}.md"
    (root / "scope-attestations").mkdir()
    (root / "scope.md").write_bytes(scope)
    (root / attestation).write_bytes(scope)
    (root / ".record-kernel.lock").write_bytes(b"")
    actor = {"role": "operator", "id": "synthetic-operator"}
    event = {"schema_version": 1, "sequence": 1, "previous_hash": None,
             "event_id": "document-scope", "engagement_id": "synthetic-documents",
             "recorded_at": "2026-09-05T10:00:00Z", "actor": actor,
             "event_type": "scope.attested", "entity_refs": [],
             "rationale": "Invented scope row for read-only metadata validation; no operation authorized.",
             "evidence_refs": [], "review_refs": [], "provenance": {"actor": actor},
             "ex_ante": None, "state_changes": [
                 {"dimension": dimension, "entity_id": "synthetic-documents", "previous": None, "current": current}
                 for dimension, current in [("engagement", "active"), ("coverage", "active"), ("memory", "pending")]],
             "payload": {"scope_hash": digest, "operator_id": "synthetic-operator",
                         "signed_date": "2026-09-05", "record_kernel": "decision-0005-v1",
                         "supersedes_scope_hash": None, "scope_snapshot_path": attestation}}
    event["record_hash"] = sha256_bytes(canonical_json_bytes(event))
    (root / "events.jsonl").write_bytes(canonical_json_bytes(event))
    (root / "attempts.jsonl").write_bytes(b"")
    (root / "artifacts.jsonl").write_bytes(b"")


def rich_static_dossier(root):
    """Write synthetic records directly. No kernel builder, publisher or lifecycle operation."""
    static_dossier(root)
    events = [json.loads((root / "events.jsonl").read_text())]
    attempts, artifacts = [], []
    scope_hash = events[0]["payload"]["scope_hash"]
    owner = {"role": "operator", "id": "synthetic-operator"}
    reviewer = {"role": "reviewer", "id": "document-reviewer"}
    clock = 0

    def timestamp():
        nonlocal clock
        clock += 1
        return (datetime(2026, 9, 5, 10, tzinfo=timezone.utc) + timedelta(seconds=clock)).isoformat()

    def chain(rows, row):
        row.update(sequence=len(rows) + 1, previous_hash=rows[-1]["record_hash"] if rows else None)
        row["record_hash"] = sha256_bytes(canonical_json_bytes(row))
        rows.append(row)
        return row

    def fixture_event(identity, kind, payload, *, actor=owner, changes=None, refs=None, reviews=None, findings=None, reason="Static document metadata"):
        return chain(events, {"schema_version": 1, "event_id": identity, "engagement_id": "synthetic-documents",
                 "recorded_at": timestamp(), "actor": actor, "event_type": kind, "entity_refs": refs or [],
                 "rationale": reason, "evidence_refs": [], "review_refs": reviews or [], "finding_refs": findings or [],
                 "provenance": {"actor": actor, "session_id": "static-author", "model": "no-model"},
                 "ex_ante": None, "state_changes": changes or [], "payload": payload})

    def fixture_file(name, value):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        data = canonical_json_bytes(value) if isinstance(value, dict) else value.encode()
        path.write_bytes(data)
        return sha256_bytes(data)

    def commitment(name, value, kind, identity, revision=None):
        digest = fixture_file(name, value)
        fixture_event("commit-" + identity + ("-" + str(revision) if revision else ""), "record.committed",
                      {"record_path": name, "record_digest": digest, "record_type": kind,
                       "record_id": identity, "record_revision": revision})
        return digest

    empty = sha256_bytes(b"")
    environment = {"schema_version": 1, "preflight_id": "document-environment", "engagement_id": "synthetic-documents",
        "recorded_at": timestamp(), "scope_hash": scope_hash, "target_refs": [], "mode": "local_runtime", "status": "ready",
        "identity": {"source_identity": "synthetic documents", "expected_identity": "synthetic documents",
                     "git_commit": None, "dirty_tree_hash": None, "build_identity": "fixture", "runtime_identity": "no execution",
                     "runtime_digest": empty, "dependency_lock_hash": None, "configuration_hash": None,
                     "endpoint_identity": None, "account_role": None, "feature_flags": []},
        "fidelity_complete": True, "missing_fidelity": [],
        "collector": {"collector_version": "decision5-preflight-v1", "operation": "local_runtime_identity",
                      "reproduction_argv": ["synthetic-data-only"], "reproducible": True, "exit_code": 0,
                      "stdout_digest": empty, "stderr_digest": empty},
        "safety": {"scope_attested": True, "credentials_present": False, "account_labels": [], "cleanup_open_count": 0,
                   "advisory_zone": "clear_local", "zone2_authorization_granted": False, "secret_scan_status": "clean",
                   "secret_pattern_classes": [], "operator_redaction_attested": True}, "provenance": {"actor": owner}}
    environment["identity_hash"] = sha256_bytes(canonical_json_bytes(environment["identity"]))
    commitment("environment/preflight-documents.json", environment, "environment-preflight", "document-environment")
    fixture_event("environment-observed", "environment.preflight_recorded", {"environment_ref": "document-environment", "status": "ready", "identity_hash": environment["identity_hash"]})
    fixture_event("document-observed", "observation.recorded", {"entity_id": "workshop-document", "entity_type": "document", "status": "observed"})
    cost = dict.fromkeys(["wall_seconds", "model_seconds", "tool_seconds", "target_calls", "model_calls", "human_review_seconds"], 0)
    fixture_event("document-question", "hypothesis.created", {
        "hypothesis_id": "document-revision-question", "origin_type": "target_model", "origin_ref": "document-observed",
        "hypothesis_statement": "The source revision changed its start time.", "suspected_invariant": "Cite the supplied document revision.",
        "trust_boundary": "Document text and summary", "attacker_path": ["Not applicable: synthetic document review"],
        "impact_ceiling": "Document wording only", "bounded_space": "Two invented document versions", "lens_ids": [], "card_ids": [],
        "expected_confirming_evidence": [{"evidence_type": "trace", "description": "Compare document text", "required": True}],
        "decisive_falsifiers": ["Both documents state the same time"], "cost_estimate": cost, "constraints": ["No execution"],
        "next_experiment": "Read existing text", "completion_criteria": ["Account for revisions"], "status": "queued"},
        changes=[{"dimension": "search", "entity_id": "document-revision-question", "previous": None, "current": "queued"}])
    for version, time in [(1, "10:00"), (2, "11:00")]:
        name = f"evidence/workshop-v{version}.md"
        text = f"# Workshop source revision v{version}\n\nThe paper-folding workshop starts at {time}. Venue not supplied.\n"
        digest = fixture_file(name, text)
        chain(artifacts, {"schema_version": 1, "artifact_id": f"workshop-v{version}", "engagement_id": "synthetic-documents",
            "relative_path": name, "sha256": digest, "size": len(text.encode()), "media_type": "text/markdown",
            "created_at": timestamp(), "producer": owner, "acquisition_method": "source_inspection", "target_refs": [],
            "environment_ref": "document-environment", "sensitivity": "public", "redaction_status": "not_needed",
            "contains_executable_capability": False, "advisory_zone": "clear_local", "escalation_confirmation_event_ref": None,
            "cleanup_obligation_ref": None, "immutable": True, "supersedes_artifact_id": "workshop-v1" if version == 2 else None})
    for aid, kind, assessment in [("document-read", "primary", "suspected_signal"), ("document-control", "negative_control", "no_signal"), ("document-recheck", "replay", "suspected_signal")]:
        chain(attempts, {"schema_version": 2, "attempt_id": aid, "engagement_id": "synthetic-documents", "recorded_at": timestamp(),
            "actor": owner, "provenance": {"actor": owner}, "scope_hash": scope_hash, "environment_ref": "document-environment",
            "escalation_confirmation_event_ref": None, "hypothesis_ref": "document-revision-question", "experiment_ref": "document-question",
            "surface": "Invented workshop text", "action_summary": "Static account of document comparison, not an executed operation",
            "redaction_attestation": True, "observation": {"source": "source_inspection", "statement": "The v2 text says 11:00."},
            "evidence_refs": ["workshop-v2"], "kind": kind, "control_of": [] if kind == "primary" else ["document-read"],
            "assessment": assessment, "contamination": {"status": "none_observed", "sources": [], "note": "Synthetic fixture"}, "cost": cost})
    records = {r["attempt_id"]: r for r in attempts} | {r["artifact_id"]: r for r in artifacts}
    prior_finding = None
    for revision in [1, 2, 3]:
        review_id = f"document-review-{revision}"
        input_refs = ["document-read", "document-control", "document-recheck", "workshop-v2"] + (["document-claim"] if prior_finding else [])
        inputs = [{"ref": ref, "digest": sha256_bytes(canonical_json_bytes(prior_finding)) if ref == "document-claim" else records[ref]["record_hash"]} for ref in sorted(input_refs)]
        review = {"schema_version": 1, "review_id": review_id, "engagement_id": "synthetic-documents", "review_type": "claim_adjudication",
            "proposed_finding_id": "document-claim", "recorded_at": timestamp(), "entity_ref": "document-claim", "finding_revision": revision - 1 or None,
            "input_refs": input_refs, "input_hash": sha256_bytes(canonical_json_bytes(inputs)), "evidence_refs": ["workshop-v2"],
            "rationale": f"Independent static review of predecessor r{revision - 1}; retain source v2 and unknown venue.",
            "conflicting_evidence": [], "verdict": "supported", "corrections": ["Keep source revision separate from claim revision"],
            "required_next_actions": ["Retain the unknown venue"],
            "independence": {"reviewer_id": "document-reviewer", "reviewer_run_id": f"review-run-{revision}", "reviewer_model": "synthetic-reviewer",
                             "fresh_context": True, "prior_verdict_visible": False, "disconfirming_objective": "Check whether the source still says 10:00.", "originating_run_id": "document-observed"},
            "control_applicability": [{"attempt_ref": "document-control", "applicable": True, "rationale": "Check the unchanged part of the document"}]}
        review_digest = commitment(f"reviews/{review_id}.json", review, "review", review_id)
        adjudication = fixture_event(f"document-adjudication-{revision}", "claim.adjudicated",
            {"entity_id": "document-claim", "status": "supported", "review_ref": review_id, "review_digest": review_digest}, actor=reviewer,
            changes=[{"dimension": "claim", "entity_id": "document-claim", "previous": "supported" if prior_finding else None, "current": "supported"}], reviews=[review_id])
        finding = {"schema_version": 3, "finding_id": "document-claim", "engagement_id": "synthetic-documents", "revision": revision,
            "supersedes_revision": revision - 1 or None, "recorded_at": timestamp(),
            "change_reason": {1: "Initial document summary", 2: "Cite source v2 explicitly", 3: "Clarify unknown venue; preserve the unique paper-folding narrative"}[revision],
            "classification": {"domain": "synthetic document review", "weakness_identifiers": [], "severity": {"label": "informational", "system": "fixture", "rationale": "No security claim"}},
            "scope_provenance": {"scope_hash": scope_hash, "environment_ref": "document-environment", "target_refs": [], "provenance": {"actor": reviewer}},
            "claim_state": "supported", "claims": {"attacker_model": "Not applicable: document metadata", "preconditions": ["Read supplied source v2"],
                "mechanism": {"claim_id": "summary", "statement": "The attendee note cites source v2.", "evidence_refs": ["workshop-v2"]},
                "reachability": {"claim_id": "revision", "statement": "The supplied document revision is v2.", "causal_spine": ["Read workshop-v2"], "evidence_refs": ["workshop-v2"]},
                "impact_claims": [{"claim_id": "time", "statement": "The workshop begins at 11:00.", "status": "inferred", "evidence_refs": ["workshop-v2"]}],
                "uncertainty": ["Venue remains unknown; keep the paper-folding narrative."], "conflicting_evidence": []},
            "proof": {"primary_attempt_refs": ["document-read"], "negative_control_refs": ["document-control"], "positive_control_refs": [],
                "replay_refs": ["document-recheck"], "fresh_state_properties": ["Static source bytes"], "contamination_disposition": "not_applicable",
                "evidence_refs": ["workshop-v2"], "claim_proofs": [{"claim_id": cid, "attempt_refs": ["document-read"], "artifact_refs": ["workshop-v2"],
                    "control_refs": ["document-control"], "replay_refs": ["document-recheck"], "applicability_rationale": "Document source comparison"} for cid in ["summary", "revision", "time"]],
                "control_applicability": {"negative": "required", "positive": "not_applicable", "replay": "required", "rationale": "Document comparison only"}},
            "adjudication": {"review_ref": review_id, "justification": "Source v2 is separate from this claim record."},
            "search_linkage": {"candidate_refs": [], "hypothesis_refs": ["document-revision-question"]}}
        finding_digest = commitment(f"findings/document-claim/rev-{revision}.json", finding, "finding-v3", "document-claim", revision)
        fixture_event(f"document-revised-{revision}", "finding.revised", {"finding_id": "document-claim", "finding_revision": revision,
            "status": "supported", "finding_digest": finding_digest, "adjudication_review_ref": review_id, "adjudication_review_digest": review_digest,
            "adjudication_event_ref": adjudication["event_id"], "supersedes_revision": revision - 1 or None, "change_reason": finding["change_reason"]},
            reviews=[review_id], findings=["document-claim"], reason=finding["change_reason"])
        if revision >= 2:
            # Static Markdown template matching the admitted report format; no renderer is invoked.
            tuple_value = {k: finding[k] for k in ["finding_id", "revision", "claim_state", "classification", "claims"]}
            tuple_value["scope_provenance"] = {k: finding["scope_provenance"][k] for k in ["scope_hash", "environment_ref", "target_refs"]}
            tuple_digest = sha256_bytes(canonical_json_bytes(tuple_value))
            matrix = f"# Claim-to-proof matrix — document-claim revision {revision}\n\n- Claim state: `supported`\n- Claim tuple: `{tuple_digest}`\n- Renderer: `decision-0005-proof-v1`\n\n| Claim | Status | Statement | Primary attempts | Artifacts | Controls | Replays |\n| --- | --- | --- | --- | --- | --- | --- |\n| summary | mechanism_or_reachability | The attendee note cites source v2. | document-read | workshop-v2 | document-control | document-recheck |\n| revision | mechanism_or_reachability | The supplied document revision is v2. | document-read | workshop-v2 | document-control | document-recheck |\n| time | inferred | The workshop begins at 11:00. | document-read | workshop-v2 | document-control | document-recheck |\n\n## Uncertainty\n\n- Venue remains unknown; keep the paper-folding narrative.\n"
            report = f"# Internal advisory — document-claim revision {revision}\n\nClaim state: **supported**\n\n## Included claims\n\n### summary\n\nThe attendee note cites source v2.\n\nClaim status: mechanism_or_reachability\nEvidence: document-read, workshop-v2\nControls: document-control\nReplays: document-recheck\n\n## Intentionally omitted claims\n\n- `revision` — Covered by source citation\n- `time` — Keep uncertainty explicit\n\n## Structured claim-to-proof matrix\n\n" + matrix
            report_id = f"document-report-{revision}"
            report_path = f"reports/{report_id}.md"
            report_digest = fixture_file(report_path, report)
            manifest = {"schema_version": 1, "report_id": report_id, "engagement_id": "synthetic-documents", "generated_at": timestamp(),
                "finding_id": "document-claim", "finding_revision": revision, "finding_digest": finding_digest,
                "adjudication_review_ref": review_id, "adjudication_review_digest": review_digest, "template_version": "fixture-v1",
                "renderer_version": "decision-0005-proof-v1", "report_path": report_path, "report_digest": report_digest,
                "operator_status": "draft", "included_claim_ids": ["summary"], "omitted_claims": [{"claim_id": "revision", "rationale": "Covered by source citation"}, {"claim_id": "time", "rationale": "Keep uncertainty explicit"}],
                "claim_proof_matrix_hash": sha256_bytes(matrix.encode()), "generator_provenance": {"actor": owner}, "historical_reason": None}
            manifest_digest = commitment(f"reports/{report_id}.manifest.json", manifest, "report-manifest", report_id)
            fixture_event(f"report-row-{revision}", "report.generated", {"report_ref": report_id, "finding_id": "document-claim", "finding_revision": revision, "report_manifest_digest": manifest_digest},
                refs=[report_id], changes=[{"dimension": "report", "entity_id": report_id, "previous": None, "current": "draft"}])
            if revision == 3:
                acceptance = copy.deepcopy(review)
                acceptance.update(review_id="document-acceptance", review_type="operator", proposed_finding_id=None, recorded_at=timestamp(), entity_ref=report_id, finding_revision=3,
                    input_refs=[report_id], input_hash=sha256_bytes(canonical_json_bytes([{"ref": report_id, "digest": manifest_digest}])), verdict="accepted",
                    rationale="Accept only this revisioned document report; no remediation claim.", control_applicability=[])
                acceptance["independence"].update(reviewer_id="synthetic-operator", reviewer_run_id="operator-review-run")
                commitment("reviews/document-acceptance.json", acceptance, "review", "document-acceptance")
                fixture_event("document-report-accepted", "operator.review_recorded", {"report_ref": report_id, "review_ref": "document-acceptance", "status": "accepted", "reason": acceptance["rationale"]},
                    reviews=["document-acceptance"], changes=[{"dimension": "report", "entity_id": report_id, "previous": "draft", "current": "accepted"}])
        prior_finding = finding
    # An independently attributed, outstanding citation review; still static metadata only.
    pending = copy.deepcopy(review)
    pending.update(review_id="citation-review", review_type="regrade", proposed_finding_id="document-claim",
        recorded_at=timestamp(), finding_revision=3, input_refs=["document-claim"],
        input_hash=sha256_bytes(canonical_json_bytes([{"ref": "document-claim", "digest": finding_digest}])),
        verdict="needs_more_evidence", rationale="The venue citation is still missing from source v2.",
        claim_tuple_hash=tuple_digest, evidence_refs=[], control_applicability=[], replay_freshness=[], prior_review_run_ids=["review-run-3"], escalation_claims=[], blocked_reason=None)
    pending["independence"].update(reviewer_run_id="citation-review-run")
    commitment("reviews/citation-review.json", pending, "review", "citation-review")
    fixture_event("citation-review-needed", "review.regrade_completed",
        {"review_ref": "citation-review", "finding_id": "document-claim", "finding_revision": 3,
         "verdict": "needs_more_evidence", "claim_tuple_hash": tuple_digest}, actor=reviewer,
        reviews=["citation-review"], reason=pending["rationale"])
    fixture_file("cleanup.md", "# Human cleanup context\n\nKeep the hand-folded paper crane for the workshop display. No deletion was requested.\n")
    fixture_file("state.snapshot.json", {})
    fixture_file("progress.md", "# Stale projection\nOnly document claim revision 1 was displayed.\n")
    fixture_file("reviews/README.md", "# Stale reviews\n- document-review-2\n")
    fixture_file("views/report-index.md", "# Stale report list\n- document-report-2\n")
    for name, rows in [("events.jsonl", events), ("attempts.jsonl", attempts), ("artifacts.jsonl", artifacts)]:
        (root / name).write_bytes(b"".join(canonical_json_bytes(row) for row in rows))


def main():
    inspector = Path(__file__).with_name("inspect-dossier.py")
    with tempfile.TemporaryDirectory(prefix="document-inspector-") as directory:
        home = Path(directory)
        root = home / "dossier"
        rich_static_dossier(root)
        before = snapshot(root)
        state = reduce_engagement(root)
        assert state["findings"]["document-claim"]["revision"] == 3
        assert snapshot(root) == before
        artifact = [json.loads(line) for line in (root / "artifacts.jsonl").read_text().splitlines()][1]
        task = {"schema_version": 1, "source_ref": "synthetic task assignment", "recorded_at": "2026-09-05T11:00:00Z",
                "intent": "Explain the current workshop note and preserve unknown venue.",
                "configuration": {"runtime": "supplied synthetic label; no run", "model": None},
                "loading": {"status": "unknown", "source_ref": None}, "based_on_ledger_hash": state["ledger_hash"],
                "source_documents": [{"artifact_ref": "workshop-v2", "revision": "v2", "sha256": artifact["sha256"], "source_ref": "synthetic source manifest"}]}
        task_path, outcomes_path = home / "task.json", home / "outcomes.json"
        task_path.write_bytes(canonical_json_bytes(task))
        outcomes = {"schema_version": 1, "source_ref": "synthetic external decision log", "recorded_at": "2026-09-05T12:00:00Z", "rows": [
            {"external_report_id": "external-workshop-note", "decision": "received", "decision_at": "2026-09-05T11:10:00Z", "recorded_at": "2026-09-05T11:15:00Z", "confidence": "declared only", "source_ref": "external row A", "note": "Keep the earlier receipt"},
            {"external_report_id": "external-workshop-note", "decision": "needs clarification", "decision_at": "2026-09-05T11:20:00Z", "recorded_at": "2026-09-05T11:25:00Z", "confidence": None, "source_ref": "external row B"},
            {"external_report_id": "document-report-3", "decision": "received", "decision_at": None, "recorded_at": None, "source_ref": "same spelling is not internal identity"},
            {"external_report_id": "historical-external-note", "decision": "reviewed", "decision_at": None, "recorded_at": None, "source_ref": "external historical row", "revision_binding": {"finding_id": "document-claim", "revision": 2, "finding_digest": sha256_bytes((root / "findings/document-claim/rev-2.json").read_bytes())}}]}
        outcomes_path.write_bytes(canonical_json_bytes(outcomes))
        checks = 0

        def run(*args, invalid=False, wrapper=None, moved=False):
            nonlocal checks
            source_before = snapshot(root)
            supplements_before = {p.name: p.read_bytes() for p in (task_path, outcomes_path) if p.exists()}
            command = [sys.executable, str(wrapper or inspector), "--source", str(root), *map(str, args)]
            result = subprocess.run(command, capture_output=True, text=True)
            assert result.returncode == int(invalid), result.stdout + result.stderr
            assert "Traceback" not in result.stdout + result.stderr
            value = json.loads(result.stdout)
            assert value["valid"] is not invalid
            assert "/dev/fd/" not in result.stdout, "expired descriptor locator escaped"
            inspected = root.with_name("dossier-moved") if moved else root
            assert snapshot(inspected) == source_before, "inspector changed source bytes or inventory"
            assert supplements_before == {p.name: p.read_bytes() for p in (task_path, outcomes_path) if p.exists()}
            if invalid:
                assert value["status"] == "unavailable" and "claims" not in value
            checks += 1
            return value

        summary = run("--task-context", task_path, "--outcomes", outcomes_path)
        assert summary == run("--task-context", task_path, "--outcomes", outcomes_path)
        claim = summary["claims"][0]
        assert claim["current_state"]["revision"] == 3
        assert claim["current_state"]["change_reason"].startswith("Clarify unknown venue")
        assert claim["change_event"]["records"][0]["record"]["event_id"] == "document-revised-3"
        assert len(claim["revisions"]) == 3
        doc = next(d for d in summary["source_documents"] if d["artifact"]["reference"] == "workshop-v2")
        assert doc["source_revision_declarations"][0]["data"]["revision"] == "v2"
        assert doc["source_revision_declarations"][0]["status"] == "mapped"
        assert doc["content_source"]["path"] == str(root / "evidence/workshop-v2.md")
        review = next(r for r in summary["reviews"] if r["record"]["review_id"] == "document-review-3")
        assert review["relationship"] == {"kind": "predecessor_adjudication", "reviewed_revision": 2, "expected_filing_revision": 3}
        assert review["subject"]["records"][0]["record"]["revision"] == 2
        assert next(i for i in review["inputs"] if i["reference"] == "document-claim")["records"][0]["record"]["revision"] == 2
        assert review["record"]["rationale"] and review["record"]["independence"]["fresh_context"]
        latest = next(r for r in summary["reports"] if r["record"]["report_id"] == "document-report-3")
        previous = next(r for r in summary["reports"] if r["record"]["report_id"] == "document-report-2")
        assert latest["birth_status"] == "draft" and latest["current_state"]["status"] == "accepted"
        assert len(latest["history"]) == 2 and previous["current_state"]["status"] == "historical"
        assert previous["current_state"]["historical_reason"] == "superseded by finding revision 3"
        assert "paper-folding narrative" in latest["narrative"]["text"]
        assert "hand-folded paper crane" in summary["human_cleanup"]["text"]
        assert summary["last_recorded_event"]["reference"] == "citation-review-needed"
        obligation = summary["review_obligations"][0]
        assert obligation["recorded"]["reason"] == "The venue citation is still missing from source v2."
        assert obligation["recorded"]["status"] == "pending"
        assert obligation["subject"]["reference"] == "document-claim"
        assert obligation["opening_event"]["reference"] == "citation-review-needed"
        assert previous["supersession_event"]["reference"] == "document-revised-3"
        assert summary["active_environment"]["records"][0]["record"]["identity"]["source_identity"] == "synthetic documents"
        assert summary["source"]["ledger_hash"] == state["ledger_hash"]
        assert summary["task_context"]["ledger_basis_status"] == "current"
        assert summary["source"]["directory_identity"]["inode"] == root.stat().st_ino
        assert {p["status"] for p in summary["projections"]} == {"stale", "absent"}
        rows = summary["external_outcomes"]["rows"]
        assert [r["data"] for r in rows] == outcomes["rows"] and len(rows) == 4
        assert [r["revision_mapping"]["status"] for r in rows] == ["unmapped", "unmapped", "unmapped", "stale"]
        assert all(r["namespace"] == "external_report" for r in rows)
        absent = run()
        assert absent["task_context"]["status"] == "absent" and absent["task_context"]["data"] is None
        assert absent["loading"]["observation"] == {"status": "unknown", "source_ref": None}
        assert absent["external_outcomes"]["input"]["status"] == "absent"
        assert run("--task-context", home / "missing.json")["task_context"]["status"] == "absent"
        unreadable = home / "not-a-file"
        unreadable.mkdir()
        assert run("--task-context", unreadable)["task_context"]["status"] == "unreadable"
        task_path.write_text("{bad")
        assert run("--task-context", task_path)["task_context"]["status"] == "invalid"
        task_path.write_bytes(canonical_json_bytes(dict(task, based_on_ledger_hash="sha256:" + "0" * 64)))
        stale = run("--task-context", task_path)
        assert stale["task_context"]["status"] == "stale"
        assert stale["loading"]["context_status"] == "stale"
        assert next(d for d in stale["source_documents"] if d["artifact"]["reference"] == "workshop-v2")["source_revision_declarations"][0]["status"] == "stale"
        task_path.write_bytes(canonical_json_bytes(task))
        outcomes_path.write_text("{bad")
        assert run("--outcomes", outcomes_path)["external_outcomes"]["input"]["status"] == "invalid"
        outcomes_path.write_bytes(canonical_json_bytes(outcomes))
        for invalid_json in ['{"schema_version": 1, "schema_version": 1}', '{"cost": NaN}']:
            for path, option, section in [(task_path, "--task-context", "task_context"), (outcomes_path, "--outcomes", "external_outcomes")]:
                original = path.read_bytes()
                path.write_text(invalid_json)
                value = run(option, path)
                assert (value[section] if section == "task_context" else value[section]["input"])["status"] == "invalid"
                path.write_bytes(original)
        observed = copy.deepcopy(task)
        observed["loading"] = {"status": "observed", "source_ref": "synthetic adapter receipt; not verified"}
        observed["source_documents"][0]["sha256"] = "sha256:" + "0" * 64
        task_path.write_bytes(canonical_json_bytes(observed))
        value = run("--task-context", task_path)
        assert value["loading"]["observation"] == observed["loading"] and value["loading"]["source"]["path"] == str(task_path)
        assert next(d for d in value["source_documents"] if d["artifact"]["reference"] == "workshop-v2")["source_revision_declarations"][0]["status"] == "unmapped"
        task_path.write_bytes(canonical_json_bytes(task))
        mapped = copy.deepcopy(outcomes)
        mapped["rows"].append({"external_report_id": "current-external-note", "decision": "duplicate", "source_ref": "synthetic decision; not proof of validity",
            "revision_binding": {"finding_id": "document-claim", "revision": 3, "finding_digest": sha256_bytes((root / "findings/document-claim/rev-3.json").read_bytes())}})
        outcomes_path.write_bytes(canonical_json_bytes(mapped))
        value = run("--outcomes", outcomes_path)
        assert value["external_outcomes"]["rows"][-1]["revision_mapping"]["status"] == "mapped"
        assert value["claims"][0]["current_state"] == summary["claims"][0]["current_state"]
        mapped["rows"][-1]["revision_binding"]["finding_digest"] = "sha256:" + "0" * 64
        outcomes_path.write_bytes(canonical_json_bytes(mapped))
        assert run("--outcomes", outcomes_path)["external_outcomes"]["rows"][-1]["revision_mapping"]["status"] == "unmapped"
        outcomes_path.write_bytes(canonical_json_bytes(outcomes))
        indexed = root / "indexed-extra.json"
        indexed.write_text("{bad")
        assert run("--task-context", indexed, invalid=True)["error"]["code"] == "invalid_json"
        indexed.write_bytes(canonical_json_bytes({"artifact_id": "document-claim", "engagement_id": "synthetic-documents"}))
        assert run(invalid=True)["error"]["code"] == "cross_type_record_id_collision"
        indexed.unlink()
        marker = root / "legacy/quarantine/ledger-quarantined.json"
        marker.parent.mkdir(parents=True)
        marker.write_text("{invalid static marker")
        assert run(invalid=True)["error"]["code"] == "engagement_quarantined"
        marker.unlink()
        lock = root / ".record-kernel.lock"
        lock.unlink()
        assert run(invalid=True)["error"]["code"] == "engagement_coordination_unavailable"
        assert not lock.exists()
        lock.write_bytes(b"")
        (root / "state.snapshot.json").write_text("{bad")
        invalid_view = run()
        assert next(p for p in invalid_view["projections"] if p["path"].endswith("state.snapshot.json"))["status"] == "invalid"
        (root / "state.snapshot.json").write_text('{"event_count": 1, "event_count": 2}')
        assert next(p for p in run()["projections"] if p["path"].endswith("state.snapshot.json"))["status"] == "invalid"
        (root / "state.snapshot.json").write_bytes(canonical_json_bytes({}))
        # Materialize pure expected bytes directly in this disposable fixture; no writing renderer.
        for name, data in {"state.snapshot.json": canonical_json_bytes(state), **render_views(state)}.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        assert {p["status"] for p in run()["projections"]} == {"current"}
        # A process wrapper injects only a directory-identity race in this disposable source.
        # It invokes the same CLI main; there is no test-only hook in the inspector.
        wrapper = home / "identity-race.py"
        wrapper.write_text("import runpy, sys\nfrom pathlib import Path\nsys.dont_write_bytecode=True\n"
            + f"sys.path.insert(0, {str(inspector.parent)!r})\nnamespace=runpy.run_path({str(inspector)!r})\n"
            + "function=namespace['inspect_dossier']\noriginal=function.__globals__['summarize']\n"
            + "def rename_after_summary(*args):\n    result=original(*args)\n    args[1].rename(args[1].with_name('dossier-moved'))\n    return result\n"
            + "function.__globals__['summarize']=rename_after_summary\nraise SystemExit(namespace['main']())\n")
        rejected = run(invalid=True, wrapper=wrapper, moved=True)
        assert rejected["error"]["code"] == "engagement_source_changed"
    print(f"dossier inspector: static admission and {checks} public-command checks passed; no source mutation")


if __name__ == "__main__":
    main()
