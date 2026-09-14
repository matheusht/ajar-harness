#!/usr/bin/env python3
"""Synthetic public-command acceptance for the offline study account; no models or targets."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
METRICS = ("human_active_seconds", "elapsed_seconds", "machine_seconds", "input_tokens", "output_tokens", "cost_usd")
CONFIG = {"runtime": "synthetic-adapter-v1", "model": "synthetic", "model_revision": "v1",
          "model_is_alias": False, "instructions": [{"id": "document-v1", "sha256": "sha256:" + "a" * 64}],
          "source_ref": "synthetic configuration declaration"}


def example():
    study = {"schema_version": 1, "study_id": "offline-example", "question": "Can the account retain every assigned case?",
             "permitted_conclusion": "Synthetic accounting behavior only.", "frozen_at": "2026-09-05T10:00:00Z",
             "freeze_source_ref": "synthetic pre-output declaration", "missing_data_policy": "Keep missing rows and unknown measurements.",
             "grading": {"procedure": "Assess designated output against fixed reference", "isolation": "Cold independent assessment",
                         "reference_ref": "synthetic answer key v1"},
             "source_families": [{"family_id": "documents", "split": "evaluation"}],
             "arms": [{"arm_id": "serial", "treatment": "complete-source serial", "configuration": copy.deepcopy(CONFIG)}],
             "assignments": [{"assignment_id": "case-serial-1", "case_id": "case", "arm_id": "serial", "repeat": 1, "family_id": "documents"}],
             "resource_ceilings": dict.fromkeys(METRICS, 100),
             "accounting_scopes": {account: {"description": f"All {account} work for this synthetic study",
                                             "allocation_rule": "Explicit per-receipt nonoverlapping allocation",
                                             "included_phases": ["execution", "preparation", "useful_assistance", "retry", "interruption", "recovery", "synthesis", "grading", "reporting", "cleanup", "accounting"] if account == "study" else [account]}
                                   for account in ("study", "development", "maintenance")}}
    receipt = {"receipt_id": "work-1", "assignment_id": "case-serial-1", "account": "study", "actor_id": "worker-1",
               "role": "document worker", "phase": "useful_assistance", "activity": "Prepare a correct document answer",
               "source_ref": "synthetic measurement 1", "interval": {"start": "2026-09-05T10:01:00Z", "end": "2026-09-05T10:01:10Z"},
               "parent_receipt_id": None, "metrics": dict.fromkeys(METRICS, 10), "not_applicable": {}}
    observed = {"schema_version": 1, "study_id": study["study_id"], "study_sha256": "BOUND_BY_TEST", "data_kind": "synthetic",
                "cases": [{"assignment_id": "case-serial-1", "recorded_at": "2026-09-05T10:02:00Z", "status": "completed",
                           "producer_id": "worker-1", "source_ref": "synthetic case outcome", "configuration": copy.deepcopy(CONFIG),
                           "loading": {"status": "observed", "source_ref": "synthetic adapter input trace"}, "deviations": [], "contaminated": False,
                           "outputs": [{"output_id": "output-1", "source_ref": "synthetic output 1", "produced_at": "2026-09-05T10:01:10Z",
                                        "assessment": {"assessment_id": "review-1", "assessor_id": "grader-1", "eligible": True,
                                                       "independent": True, "source_ref": "synthetic cold assessment"}}]}],
                "receipts": [receipt], "scope_completeness": [
                    {"account": account, "metric": metric, "complete": True, "asserted_by": "synthetic evaluator",
                     "source_ref": "synthetic full activity inventory", "basis": "The fixture defines all work, including failed and successful work."}
                    for account in ("study", "development", "maintenance") for metric in METRICS],
                "allocations": [], "unreconciled_imports": []}
    return study, observed


def main():
    with tempfile.TemporaryDirectory(prefix="study-report-") as directory:
        root = Path(directory)
        study_path, observed_path = root / "study.json", root / "observations.json"
        checks = 0

        def run(study, observed, *, invalid=False, bind=True):
            nonlocal checks
            study_path.write_text(json.dumps(study))
            observed = copy.deepcopy(observed)
            if bind:
                observed["study_sha256"] = "sha256:" + hashlib.sha256(study_path.read_bytes()).hexdigest()
            observed_path.write_text(json.dumps(observed))
            before = {p.name: p.read_bytes() for p in root.iterdir()}
            result = subprocess.run([sys.executable, str(ROOT / "tools/study-report.py"), "--study", str(study_path),
                                     "--observations", str(observed_path)], capture_output=True, text=True)
            assert result.returncode == (1 if invalid else 0), result.stdout + result.stderr
            assert "Traceback" not in result.stderr + result.stdout
            report = json.loads(result.stdout)
            assert report["valid"] is not invalid
            if invalid:
                assert "cases" not in report and "permitted_conclusion" not in report
            assert before == {p.name: p.read_bytes() for p in root.iterdir()}, "command wrote input or extra files"
            checks += 1
            return report

        study, observed = example()
        control = run(study, observed)
        assert control == run(study, observed), "report is not deterministic"
        assert control["case_coverage"] == {"assigned": 1, "observed": 1, "missing": 0}
        assert control["produced_inventory"] == control["independently_assessed_eligible_results"] == 1
        assert control["accounting"]["study"]["cost_usd"]["complete_total"] == 10
        assert control["budget_adherence"]["cost_usd"] == "within_declared_scope"
        assert control["comparison_conclusion"] == "not_computed"

        partial = copy.deepcopy(observed)
        partial["receipts"][0]["metrics"]["cost_usd"] = None
        report = run(study, partial)
        cost = report["accounting"]["study"]["cost_usd"]
        assert cost["complete_total"] is None and cost["unknown"] == 1 and cost["measured_subtotal"] is None
        assert report["accounting"]["study"]["human_active_seconds"]["complete_total"] == 10
        assert report["budget_adherence"]["cost_usd"] == "unknown"
        unknown_scope = copy.deepcopy(observed)
        unknown_scope["scope_completeness"] = []
        cost = run(study, unknown_scope)["accounting"]["study"]["cost_usd"]
        assert cost["measured_subtotal"] == 10 and cost["complete_total"] is None and "scope_completeness_unestablished" in cost["limits"]

        empty_study, outcomes = example()
        for index, status in enumerate(("failed", "interrupted", "blocked", "incomplete", "no_output"), 2):
            assignment = dict(empty_study["assignments"][0], assignment_id=f"case-{index}", case_id=f"case-{index}")
            empty_study["assignments"].append(assignment)
            outcomes["cases"].append(dict(copy.deepcopy(outcomes["cases"][0]), assignment_id=assignment["assignment_id"], status=status, outputs=[]))
        empty_study["assignments"].append(dict(empty_study["assignments"][0], assignment_id="missing", case_id="missing"))
        report = run(empty_study, outcomes)
        assert report["case_coverage"] == {"assigned": 7, "observed": 6, "missing": 1}
        assert {row["status"] for row in report["cases"]} == {"completed", "failed", "interrupted", "blocked", "incomplete", "no_output", "unobserved"}
        assert report["produced_inventory"] == 1

        duplicate = copy.deepcopy(observed)
        duplicate["receipts"].append(copy.deepcopy(duplicate["receipts"][0]))
        report = run(study, duplicate)
        assert report["receipt_delivery"] == {"received": 2, "unique": 1, "duplicates": 1}
        assert report["accounting"]["study"]["cost_usd"]["complete_total"] == 10
        duplicate["receipts"][1]["metrics"]["cost_usd"] = 11
        run(study, duplicate, invalid=True)

        overlap = copy.deepcopy(observed)
        overlap["receipts"].append(dict(copy.deepcopy(overlap["receipts"][0]), receipt_id="work-2"))
        report = run(study, overlap)
        assert report["receipt_delivery"]["unique"] == 2
        assert report["accounting"]["study"]["cost_usd"]["complete_total"] == 20
        assert report["accounting"]["study"]["human_active_seconds"]["complete_total"] is None
        assert report["accounting"]["study"]["elapsed_seconds"]["complete_total"] is None
        for metric in ("human_active_seconds", "elapsed_seconds", "machine_seconds"):
            overlap["allocations"].append({"account": "study", "metric": metric, "rule": study["accounting_scopes"]["study"]["allocation_rule"],
                                          "asserted_by": "fixture evaluator", "source_ref": "synthetic time allocation", "nonoverlapping": True,
                                          "values": {"work-1": 10, "work-2": 0}})
        assert run(study, overlap)["accounting"]["study"]["human_active_seconds"]["complete_total"] == 10
        nested = copy.deepcopy(overlap)
        nested["receipts"][1]["parent_receipt_id"] = "work-1"
        assert run(study, nested)["accounting"]["study"]["cost_usd"]["complete_total"] is None

        no_interval = copy.deepcopy(observed)
        no_interval["receipts"][0]["interval"] = None
        assert run(study, no_interval)["accounting"]["study"]["human_active_seconds"]["complete_total"] is None
        not_applicable = copy.deepcopy(observed)
        not_applicable["receipts"][0]["metrics"]["machine_seconds"] = None
        not_applicable["receipts"][0]["not_applicable"] = {"machine_seconds": "Human-only activity in this fixture"}
        metric = run(study, not_applicable)["accounting"]["study"]["machine_seconds"]
        assert metric["not_applicable"] == 1 and metric["unknown"] == 0 and metric["complete_total"] == 0

        for account in ("development", "maintenance"):
            separate = copy.deepcopy(observed)
            separate["receipts"].append(dict(copy.deepcopy(separate["receipts"][0]), receipt_id=account, account=account, phase=account, assignment_id=None))
            report = run(study, separate)
            assert report["accounting"][account]["cost_usd"]["complete_total"] == 10
            assert report["accounting"]["study"]["cost_usd"]["complete_total"] == 10
        imported = copy.deepcopy(observed)
        imported["unreconciled_imports"] = [{"import_id": "raw-source", "account": None, "source_ref": "unattributed synthetic import",
                                              "reason": "Identity and allocation unavailable", "metrics": dict.fromkeys(METRICS, 99)}]
        report = run(study, imported)
        assert report["accounting"]["study"]["cost_usd"]["measured_subtotal"] == 10
        assert report["accounting"]["study"]["cost_usd"]["complete_total"] is None
        assert report["unreconciled_imports"] == imported["unreconciled_imports"]

        qualified = copy.deepcopy(observed)
        qualified["cases"][0]["configuration"]["model_is_alias"] = True
        qualified["cases"][0]["configuration"]["model_revision"] = None
        qualified["cases"][0]["loading"] = {"status": "unknown", "source_ref": None}
        qualified["cases"][0]["contaminated"] = True
        qualified["cases"][0]["deviations"] = ["Late correction was delivered after grading"]
        report = run(study, qualified)
        assert report["produced_inventory"] == 1 and report["cases"][0]["contaminated"] is True
        assert "loading_unobserved" in report["cases"][0]["limits"] and "floating_model_alias" in report["cases"][0]["limits"]
        over_budget = copy.deepcopy(study)
        over_budget["resource_ceilings"]["cost_usd"] = 5
        assert run(over_budget, unknown_scope)["budget_adherence"]["cost_usd"] == "overrun_in_measured_account"

        # Direct case work, ordinary overhead, decimal costs and observed provenance remain explicit.
        execution = copy.deepcopy(observed)
        execution["receipts"][0]["phase"] = "execution"
        execution["cases"][0]["configuration"]["source_ref"] = "separate observed configuration receipt"
        report = run(study, execution)
        assert "configuration_deviation" not in report["cases"][0]["limits"]
        assert report["receipts"][0]["phase"] == "execution"
        fractional = copy.deepcopy(overlap)
        fractional["receipts"][0]["metrics"]["cost_usd"] = 0.1
        fractional["receipts"][1]["metrics"]["cost_usd"] = 0.2
        decimal_ceiling = copy.deepcopy(study)
        decimal_ceiling["resource_ceilings"]["cost_usd"] = 0.3
        report = run(decimal_ceiling, fractional)
        assert report["accounting"]["study"]["cost_usd"]["complete_total"] == 0.3
        assert report["budget_adherence"]["cost_usd"] == "within_declared_scope"
        assert run(over_budget, nested)["budget_adherence"]["cost_usd"] == "overrun_in_measured_account"
        late_freeze = copy.deepcopy(study)
        late_freeze["frozen_at"] = "2026-09-05T10:02:00Z"
        assert "output_predates_declared_freeze" in run(late_freeze, observed)["cases"][0]["limits"]
        nonindependent = copy.deepcopy(observed)
        nonindependent["cases"][0]["outputs"][0]["assessment"]["independent"] = False
        assert run(study, nonindependent)["independently_assessed_eligible_results"] == 0
        no_source = copy.deepcopy(study)
        no_source["freeze_source_ref"] = None
        assert "pre_output_freeze_provenance_unavailable" in run(no_source, observed)["limits"]

        allocation_unestablished = copy.deepcopy(overlap)
        allocation_unestablished["allocations"][0]["nonoverlapping"] = False
        assert run(study, allocation_unestablished)["accounting"]["study"]["human_active_seconds"]["complete_total"] is None
        paired = copy.deepcopy(study)
        paired["arms"].append(dict(copy.deepcopy(paired["arms"][0]), arm_id="handoff", treatment="direct handoff"))
        paired["assignments"].extend([
            dict(paired["assignments"][0], assignment_id="repeat-2", repeat=2),
            dict(paired["assignments"][0], assignment_id="other-arm", arm_id="handoff"),
        ])
        paired_report = run(paired, observed)
        assert paired_report["case_coverage"] == {"assigned": 3, "observed": 1, "missing": 2}
        assert {(row["arm_id"], row["repeat"]) for row in paired_report["cases"]} == {("serial", 1), ("serial", 2), ("handoff", 1)}
        cross_case = copy.deepcopy(observed)
        cross_case["cases"].append(dict(copy.deepcopy(cross_case["cases"][0]), assignment_id="other-arm"))
        run(paired, cross_case, invalid=True)
        cross_parent = copy.deepcopy(observed)
        cross_parent["receipts"].append(dict(copy.deepcopy(cross_parent["receipts"][0]), receipt_id="cross-case", assignment_id="other-arm", parent_receipt_id="work-1"))
        run(paired, cross_parent, invalid=True)

        # Malformed identities, binding and measurements fail before a report is emitted.
        mutations = [
            lambda x: x.update(study_id="other"),
            lambda x: x["cases"][0].update(assignment_id="extra"),
            lambda x: x["cases"].append(copy.deepcopy(x["cases"][0])),
            lambda x: x["cases"][0]["outputs"].append(copy.deepcopy(x["cases"][0]["outputs"][0])),
            lambda x: x["receipts"][0].update(assignment_id="extra"),
            lambda x: x["receipts"][0].update(case_id="smuggled-extra-field"),
            lambda x: x["receipts"][0].update(receipt_id="  "),
            lambda x: x["receipts"][0]["metrics"].update(cost_usd=-1),
            lambda x: x["receipts"][0]["metrics"].update(input_tokens=1.5),
            lambda x: x["receipts"][0]["metrics"].update(cost_usd=True),
            lambda x: x["receipts"][0]["metrics"].update(cost_usd=float("nan")),
            lambda x: x["cases"][0]["outputs"][0]["assessment"].update(assessor_id="worker-1"),
            lambda x: x["receipts"][0]["metrics"].update(human_active_seconds=11),
            lambda x: x["receipts"][0]["metrics"].pop("cost_usd"),
            lambda x: x["receipts"][0].update(source_ref="\ud800"),
            lambda x: x["receipts"][0].update(parent_receipt_id="work-1"),
            lambda x: x["receipts"][0]["interval"].update(end="2026-09-05T10:00:00Z"),
        ]
        for mutate in mutations:
            invalid = copy.deepcopy(observed)
            mutate(invalid)
            run(study, invalid, invalid=True)
        run(study, observed, invalid=True, bind=False)
        bad_allocation = copy.deepcopy(overlap)
        bad_allocation["allocations"][0]["values"]["extra"] = 0
        run(study, bad_allocation, invalid=True)
        bad_assignment = copy.deepcopy(study)
        bad_assignment["assignments"].append(dict(study["assignments"][0], assignment_id="same-tuple"))
        run(bad_assignment, observed, invalid=True)
        incomplete_scope = copy.deepcopy(study)
        incomplete_scope["accounting_scopes"]["study"]["included_phases"].remove("execution")
        run(incomplete_scope, observed, invalid=True)
        unknown = copy.deepcopy(observed)
        unknown["receipts"][0]["metrics"]["human_active_seconds"] = None
        unknown["allocations"] = [copy.deepcopy(overlap["allocations"][0])]
        unknown["allocations"][0]["values"] = {"work-1": 0}
        run(study, unknown, invalid=True)
        # Duplicate keys must not collapse before identity validation.
        study_path.write_text(json.dumps(study))
        bound = copy.deepcopy(observed)
        bound["study_sha256"] = "sha256:" + hashlib.sha256(study_path.read_bytes()).hexdigest()
        observed_path.write_text(json.dumps(bound).replace('"study_id":', '"study_id":"hidden", "study_id":', 1))
        before = {p.name: p.read_bytes() for p in root.iterdir()}
        result = subprocess.run([sys.executable, str(ROOT / "tools/study-report.py"), "--study", str(study_path), "--observations", str(observed_path)], capture_output=True, text=True)
        assert result.returncode == 1 and json.loads(result.stdout)["valid"] is False and "Traceback" not in result.stderr
        assert before == {p.name: p.read_bytes() for p in root.iterdir()}
        checks += 1
        print(f"study report: {checks} synthetic public-command checks passed")


if __name__ == "__main__":
    main()
