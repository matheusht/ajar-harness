#!/usr/bin/env python3
"""Check concrete document bundles and the public reporter; never run agents or a board."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PACKET = ROOT / "docs/experiments/communication-v1"
METRICS = ("human_active_seconds", "elapsed_seconds", "machine_seconds", "input_tokens", "output_tokens", "cost_usd")


def snapshot(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def main():
    original = snapshot(PACKET)
    manifest = json.loads(original["manifest.json"])
    definition = json.loads(original["definition.json"])
    observations = json.loads(original["observations.json"])
    bundle_checks = 0

    def check_bundles(plan, destination):
        """Materialize fixed packet files for inspection only, without simulating a worker."""
        nonlocal bundle_checks
        assert plan["execution_status"] == "UNEXECUTED"
        assert plan["run_authorization"] is plan["effective_configuration"] is None
        assert plan["case_order"] == ["complete", "complementary", "late"]
        assert plan["arm_order"] == ["serial", "direct", "board"] and plan["repeats"] == 1
        assert [s["ordinal"] for s in plan["schedule"]] == list(range(1, 9))
        assert plan["schedule"][1]["event"] == "commit_independent_initial_observations"
        assert plan["schedule"][2]["event"] == "direct_handoffs_and_curated_packet_then_optional_board_notices"
        assert plan["schedule"][2]["recipients"] == plan["schedule"][4]["recipients"] == {"serial": "worker", "direct": "coordinator", "board": "coordinator"}
        assert plan["schedule"][6]["event"] == "commit_designated_final"
        assert plan["grading_excludes"] == ["treatment labels", "peer discussion", "worker self-grades", "other-case answers"]
        direct, board = copy.deepcopy(plan["arrangements"]["direct"]), copy.deepcopy(plan["arrangements"]["board"])
        assert direct.pop("board_notices") is False and board.pop("board_notices") is True
        assert direct == board
        assert plan["resource_limits_per_arm"] == {m: definition["resource_ceilings"][m] / 3 for m in METRICS}
        assert plan["notice_limit_per_packet"] == 5 and plan["notice_max_characters"] == 400
        for name, digest in plan["file_sha256"].items():
            assert digest == "sha256:" + hashlib.sha256(original[name]).hexdigest()

        def copy_files(names, target):
            for name in names:
                assert name in plan["file_sha256"]
                path = target / name
                path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(PACKET / name, path)
            assert snapshot(target) == {name: original[name] for name in names}

        for case in plan["cases"]:
            cid = case["case_id"]
            initial = case["initial_worker_files"]
            expected_sources = {name for name in original if name.startswith(f"inputs/{cid}/")}
            assert set(initial) == {"inputs/brief.md"} | expected_sources
            assert len(expected_sources) == 2
            assert case["external_release_ordinal"] == 5
            assert case["shared_observation_ordinal"] == 3
            assert case["shared_observation_files"] == [f"notices/{cid}-3.json"]
            assert case["external_release_files"] == [f"notices/{cid}-5.json"] + (["releases/late/binding-v2.md"] if cid == "late" else [])
            assert case["parallel_handoff_ref"] == f"coordination/{cid}.json"
            handoff = json.loads(original[case["parallel_handoff_ref"]])
            assert {r["author"] for r in handoff["independent_initial_observations"]} == {"worker-a", "worker-b"}
            assert all(r["committed_at_ordinal"] == 2 for r in handoff["independent_initial_observations"])
            assert handoff["curated_direct_packet"]["available_at_ordinal"] == 3
            assert all(r["source_version"] + ".md" in " ".join(initial) for r in handoff["independent_initial_observations"])
            all_notices = []
            assert case["board_notice_files"] == [f"notices/{cid}-3.json", f"notices/{cid}-5.json"]
            for name, ordinal in zip(case["board_notice_files"], [3, 5]):
                rows = json.loads(original[name])
                for row in rows:
                    assert row["task"] == cid and row["release_ordinal"] == ordinal
                    for field in ("author", "source_version", "observation", "applicability", "uncertainty"):
                        assert isinstance(row[field], str) and row[field].strip()
                    assert sum(len(row[k]) for k in ("observation", "applicability", "uncertainty")) <= 400
                    assert row["source_ref"] in set(initial + case["external_release_files"])
                all_notices.extend(rows)
            assert 0 < len(all_notices) <= 5
            ids = {n["notice_id"] for n in all_notices}
            assert len(ids) == len(all_notices)
            for row in all_notices:
                assert row["predecessor"] is None or row["predecessor"] in ids
            if cid == "late":
                assert all_notices[1]["predecessor"] == "late-n1"
                assert all_notices[0]["source_version"] == "binding-v1"
                assert all_notices[1]["source_version"] == "binding-v2"
            for arm in plan["arm_order"]:
                for role in plan["arrangements"][arm]["roles"]:
                    target = destination / cid / arm / role / "initial"
                    copy_files(initial, target)
                    assert not any(n.startswith(("grader/", "finals/", "coordination/", "notices/", "releases/")) for n in snapshot(target))
                recipient = plan["schedule"][4]["recipients"][arm]
                copy_files(case["shared_observation_files"], destination / cid / arm / recipient / "release-3")
                copy_files(case["external_release_files"], destination / cid / arm / recipient / "release-5")
                if arm != "serial":
                    copy_files([case["parallel_handoff_ref"]], destination / cid / arm / "shared-after-commit")
                if arm == "board":
                    for name, ordinal in zip(case["board_notice_files"], [3, 5]):
                        copy_files([name], destination / cid / arm / f"feed-release-{ordinal}")
            # The grader receives only one case's fixed reference and neutral designated finals.
            assert case["grader_reference_ref"] == f"grader/{cid}.md"
            assert case["final_ref"] == f"finals/{cid}.md"
            assert case["grader_output_names"] == ["output-a.md", "output-b.md", "output-c.md"]
            assert sorted(case["grader_arm_mapping"]) == ["board", "direct", "serial"]
            target = destination / cid / "grader"
            target.mkdir(parents=True)
            (target / "reference.md").write_bytes(original[case["grader_reference_ref"]])
            for name in case["grader_output_names"]:
                (target / name).write_bytes(original[case["final_ref"]])
            assert set(snapshot(target)) == {"reference.md", *case["grader_output_names"]}
            assert all(b"coordinator" not in data and b"worker-a" not in data and b"board" not in data for data in snapshot(target).values())
        for account in plan["notice_accounts"]:
            assert set(("retained", "delivered_read_opportunity", "used", "correct", "useful")) <= account.keys()
            assert account["useful"]["value"] is None and account["used"]["value"] is None
            assert account["source_check_timeline"] and "does not establish comprehension" in account["acknowledgment"]
        stale = next(a for a in plan["notice_accounts"] if a["notice_id"] == "late-n1")
        corrected = next(a for a in plan["notice_accounts"] if a["notice_id"] == "late-n2")
        assert stale["correct"]["value"] is False
        assert corrected["correction_timeline"][0]["predecessor"] == stale["notice_id"]
        bundle_checks += 1

    with tempfile.TemporaryDirectory(prefix="communication-packet-") as directory:
        root = Path(directory)
        check_bundles(manifest, root / "bundles")
        # Each bad manifest must fail the same bundle check, rather than merely declaring isolation.
        mutations = [
            lambda p: p["cases"][0]["initial_worker_files"].append("grader/complete.md"),
            lambda p: p["cases"][0]["initial_worker_files"].append("finals/late.md"),
            lambda p: p["cases"][2].update(external_release_ordinal=1),
            lambda p: p["cases"][2]["initial_worker_files"].append("releases/late/binding-v2.md"),
            lambda p: p["arrangements"]["board"]["initial_assignment"].update(**{"worker-a": "extra source set"}),
            lambda p: p["cases"][0].update(grader_reference_ref="grader/late.md"),
        ]
        for i, mutate in enumerate(mutations):
            bad = copy.deepcopy(manifest)
            mutate(bad)
            try:
                check_bundles(bad, root / f"rejected-{i}")
            except AssertionError:
                bundle_checks += 1
            else:
                raise AssertionError("unsafe or mismatched prepared bundle accepted")

        report_dir = root / "report"
        report_dir.mkdir()
        (report_dir / "definition.json").write_bytes(original["definition.json"])
        calls = 0

        def run(value, invalid=False):
            nonlocal calls
            (report_dir / "observations.json").write_text(json.dumps(value))
            before = snapshot(report_dir)
            result = subprocess.run([sys.executable, str(ROOT / "tools/study-report.py"),
                                     "--study", str(report_dir / "definition.json"), "--observations", str(report_dir / "observations.json")],
                                    capture_output=True, text=True)
            assert result.returncode == int(invalid), result.stdout + result.stderr
            report = json.loads(result.stdout)
            assert report["valid"] is not invalid and "Traceback" not in result.stdout + result.stderr
            assert snapshot(report_dir) == before
            if not invalid:
                assert report["data_kind"] == "synthetic" and report["comparison_conclusion"] == "not_computed"
                assert report["case_coverage"]["assigned"] == 9
            else:
                assert "cases" not in report
            calls += 1
            return report

        assert observations["study_sha256"] == "sha256:" + hashlib.sha256(original["definition.json"]).hexdigest()
        assert [(a["case_id"], a["arm_id"]) for a in definition["assignments"]] == [
            (c, a) for c in manifest["case_order"] for a in manifest["arm_order"]]
        assert len({json.dumps(a["configuration"], sort_keys=True) for a in definition["arms"]}) == 1
        assert definition["arms"][0]["configuration"]["instructions"] == [
            {"id": "document-brief", "sha256": manifest["file_sha256"]["inputs/brief.md"]}]
        control = run(observations)
        assert run(observations) == control
        assert control["case_coverage"] == {"assigned": 9, "observed": 9, "missing": 0}
        assert control["produced_inventory"] == control["independently_assessed_eligible_results"] == 9
        assert all(not row["limits"] for row in control["cases"])
        assert all(control["accounting"]["study"][m]["complete_total"] is not None for m in METRICS)
        for reason in ("cross-case answer leaked", "extra source access", "extra effective budget"):
            adverse = copy.deepcopy(observations)
            adverse["cases"][0].update(contaminated=True, deviations=[reason])
            report = run(adverse)
            row = next(r for r in report["cases"] if r["assignment_id"] == adverse["cases"][0]["assignment_id"])
            assert row["contaminated"] and reason in row["deviations"]
            assert row["independently_assessed_eligible_results"] == 1
            assert report["independently_assessed_eligible_results"] == 9
        partial = copy.deepcopy(observations)
        partial["cases"].pop()
        partial["cases"][0].update(status="failed", loading={"status": "unknown", "source_ref": None})
        partial["receipts"][0]["metrics"]["cost_usd"] = None
        report = run(partial)
        assert report["case_coverage"] == {"assigned": 9, "observed": 8, "missing": 1}
        assert {r["status"] for r in report["cases"]} == {"failed", "completed", "unobserved"}
        assert report["accounting"]["study"]["cost_usd"]["complete_total"] is None
        assert report["budget_adherence"]["cost_usd"] == "unknown"
        overrun = copy.deepcopy(observations)
        overrun["receipts"][0]["metrics"]["input_tokens"] = 1
        assert run(overrun)["budget_adherence"]["input_tokens"] == "overrun_in_measured_account"
        malformed = copy.deepcopy(observations)
        malformed["study_sha256"] = "sha256:" + "0" * 64
        run(malformed, invalid=True)
        malformed = copy.deepcopy(observations)
        malformed["cases"][0]["board_state"] = {}
        run(malformed, invalid=True)
    assert snapshot(PACKET) == original
    print(f"communication packet: {bundle_checks} bundle controls and {calls} public-command checks passed; agent experiment UNEXECUTED")


if __name__ == "__main__":
    main()
