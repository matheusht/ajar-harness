#!/usr/bin/env python3
"""Validate synthetic packet data through study-report.py; never runs a candidate."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PACKET = ROOT / "docs/experiments/recovery-v1"
METRICS = ("human_active_seconds", "elapsed_seconds", "machine_seconds", "input_tokens", "output_tokens", "cost_usd")


def snapshot(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def main():
    original = snapshot(PACKET)
    definition = json.loads(original["definition.json"])
    observations = json.loads(original["observations.json"])
    expected = json.loads(original["expectations.json"])
    assert expected["execution_status"] == "UNSTARTED"
    assert expected["run_authorization"] is expected["effective_configuration"] is None
    assert expected["history_mode"] == "client-managed"
    assert expected["argument_items"]["lookup-v2"]["call_id"] == expected["argument_items"]["lookup-call-1"]["call_id"]
    assert expected["argument_items"]["lookup-v2"]["source_ref"] == "documents.md#lookup-v2"
    assert expected["candidate_pins"] == {
        "baseline": "ea3e5c69222c9a1a471915af56bf9485429b53ea",
        "sdk": "f1f35031d364f9f0d8e94dda0853c92abefdccff"}
    assert [(a["case_id"], a["arm_id"]) for a in definition["assignments"]] == [
        (case, arm) for case in expected["case_order"] for arm in expected["arm_order"]]
    assert len(definition["assignments"]) == 6 and expected["repeats"] == 1
    assert expected["access"]["grader"] == ["anonymized final account", "fixed current-case reference"]
    assert expected["access"]["grader_excludes"] == ["treatment labels", "peer material", "self-grades", "other-case answers"]
    assert "only released source" in expected["access"]["worker"]
    assert not expected["optional_diagnostic"]["required"] and not expected["optional_diagnostic"]["assigned"]
    assert definition["resource_ceilings"] == dict(zip(METRICS, [3600, 7200, 14400, 0, 0, 0]))
    for case in expected["cases"]:
        schedule, account = case["schedule"], case["expected_account"]
        assert [s["ordinal"] for s in schedule] == list(range(1, len(schedule) + 1))
        assert schedule[0]["source_ref"] == "documents.md#workshop-v1"
        assert schedule[2]["event"] == "record_result_without_supplying"
        assert schedule[3]["event"] == "release_late_correction"
        args = account["scripted_adapter_arguments"]
        assert args["expected_on_resume"]["input"] == ["workshop-v1", "lookup-call-1", "lookup-v2", "correction-c1"]
        assert set(args["expected_on_resume"]) == {"instructions", "input", "settings", "tools", "output_schema", "previous_response_id", "conversation_id"}
        assert account["local_admission"] == {"expected": True, "observed": False}
        assert args["observed"] is False and args["expected_on_resume"]["previous_response_id"] is None
        assert account["provider_receipt"] == {"status": "unobserved", "source_ref": None}
        assert account["source_revision"] == "workshop-v2" and account["exactly_once_artifact_work"] == "not_established"
        assert account["usage"]["measured"] and account["usage"]["unknown"]
    pause, loss = [c["expected_account"] for c in expected["cases"][1:]]
    assert not pause["result"]["supplied_at_checkpoint"] and pause["unfinished_work"]
    assert loss["flags"]["subtype"] == "success" and loss["flags"]["is_error"]
    assert loss["flags"]["terminal_reason"] == "aborted_tools" and loss["unfinished_work"]
    assert expected["cases"][2]["schedule"][5]["event"] == "simulate_artifact_write"
    assert expected["cases"][2]["schedule"][6]["event"] == "simulate_loss_before_write_receipt"
    documents = original["documents.md"].decode()
    assert "10:00 in Room Cedar" in documents and "11:00\nin Room Birch" in documents
    for case in expected["cases"]:
        for step in case["schedule"]:
            for key in ("source_ref", "result_ref", "artifact_ref", "releases_revision"):
                if key in step:
                    name, anchor = step[key].split("#")
                    assert name in original and "## " + anchor in original[name].decode()

    with tempfile.TemporaryDirectory(prefix="recovery-packet-") as directory:
        root = Path(directory)
        (root / "definition.json").write_bytes(original["definition.json"])
        calls = 0

        def run(value, invalid=False):
            nonlocal calls
            (root / "observations.json").write_text(json.dumps(value))
            before = snapshot(root)
            result = subprocess.run([sys.executable, str(ROOT / "tools/study-report.py"),
                                     "--study", str(root / "definition.json"), "--observations", str(root / "observations.json")],
                                    capture_output=True, text=True)
            assert result.returncode == int(invalid), result.stdout + result.stderr
            report = json.loads(result.stdout)
            assert report["valid"] is not invalid
            assert snapshot(root) == before
            if invalid:
                assert "cases" not in report
            else:
                assert report["data_kind"] == "synthetic"
                assert report["comparison_conclusion"] == "not_computed"
                assert report["independently_assessed_eligible_results"] == 0
            calls += 1
            return report

        assert observations["study_sha256"] == "sha256:" + hashlib.sha256(original["definition.json"]).hexdigest()
        report = run(observations)
        assert report == run(observations)
        assert report["case_coverage"] == {"assigned": 6, "observed": 6, "missing": 0}
        assert report["produced_inventory"] == 6
        assert {r["status"] for r in report["cases"]} == {"completed", "interrupted"}
        assert all("loading_unobserved" in r["limits"] for r in report["cases"])
        cost = report["accounting"]["study"]["cost_usd"]
        assert cost["measured"] == 1 and cost["unknown"] == 2 and cost["complete_total"] is None
        assert report["budget_adherence"]["cost_usd"] == "unknown"
        assert [o["source_ref"] for c in observations["cases"] for o in c["outputs"]] == [
            f"docs/experiments/recovery-v1/expectations.json#/cases/{i}/expected_account" for i in range(3) for _ in range(2)]

        missing = copy.deepcopy(observations)
        missing["cases"].pop()
        assert run(missing)["case_coverage"] == {"assigned": 6, "observed": 5, "missing": 1}
        adverse = copy.deepcopy(observations)
        adverse["cases"][0].update(status="failed", contaminated=True, deviations=["Synthetic schedule violation"])
        row = next(r for r in run(adverse)["cases"] if r["assignment_id"] == adverse["cases"][0]["assignment_id"])
        assert row["status"] == "failed" and row["contaminated"] and len(row["outputs"]) == 1
        # Entirely fictional, fully measured scope illustrates the same boundary's complete path.
        complete = copy.deepcopy(observations)
        complete["receipts"] = complete["receipts"][:1]
        complete["scope_completeness"] = [
            {"account": account, "metric": metric, "complete": True, "asserted_by": "synthetic illustrator",
             "source_ref": "synthetic closed-world variation in recovery-packet-test.py",
             "basis": "This variation defines all fictional activity, including overhead; no actual work claim."}
            for account in definition["accounting_scopes"] for metric in METRICS]
        assert run(complete)["accounting"]["study"]["human_active_seconds"]["complete_total"] == 60
        incomplete = copy.deepcopy(complete)
        incomplete["receipts"][0]["metrics"]["human_active_seconds"] = None
        assert run(incomplete)["accounting"]["study"]["human_active_seconds"]["complete_total"] is None
        malformed = copy.deepcopy(observations)
        malformed["study_sha256"] = "sha256:" + "0" * 64
        run(malformed, invalid=True)
        malformed = copy.deepcopy(observations)
        malformed["cases"][0]["recovery_trace"] = {}
        run(malformed, invalid=True)  # Extra metadata belongs in referenced data, not the reporter schema.
    assert snapshot(PACKET) == original
    print(f"recovery packet: schedule/access/trace controls and {calls} public-command checks passed; candidate execution UNSTARTED")


if __name__ == "__main__":
    main()
