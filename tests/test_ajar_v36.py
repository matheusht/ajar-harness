"""Hermetic $0 regression and structural suite for Ajar v3.6."""
from __future__ import annotations

import asyncio
import importlib.util
import json
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


def _load_sz_ajar() -> Any:
    sz_path = REPO_ROOT / "extra" / "sz_ajar.py"
    spec = importlib.util.spec_from_file_location("sz_ajar", sz_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_extra_report() -> Any:
    rep_path = REPO_ROOT / "extra" / "report.py"
    spec = importlib.util.spec_from_file_location("ajar_extra_report", rep_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_sz_ajar_structural_and_anti_golf_gates(tmp_path: Path) -> None:
    sz_ajar = _load_sz_ajar()
    report = sz_ajar.audit_repo(REPO_ROOT)

    assert report["ok"] is True, f"sz_ajar violations: {report['violations']}"
    assert report["logic_module_count"] == 11
    assert report["ring0_sloc"] > 0
    assert report["epistemic_sloc"] > 0
    assert report["upward_imports"] == []
    assert report["worktree_violations"] == []
    assert set(report["registered_disable_flags"]) == set(sz_ajar.REQUIRED_DISABLE_FLAGS)
    assert len(report["registered_disable_flags"]) == 7
    assert sz_ajar.main([str(REPO_ROOT), "--json"]) == 0

    pruned_root = tmp_path / "pruned_repo"
    shutil.copytree(REPO_ROOT / "src", pruned_root / "src")
    (pruned_root / "src" / "ajar" / "epistemic.py").unlink()
    (pruned_root / "src" / "ajar" / "chain_weaver.py").unlink()
    pruned_report = sz_ajar.audit_repo(pruned_root)
    assert pruned_report["ok"] is True, f"Pro-deletion failed: {pruned_report['violations']}"
    assert pruned_report["ring1_module_count"] == 5

    fake_root = tmp_path / "broken_repo"
    shutil.copytree(REPO_ROOT / "src", fake_root / "src")
    agent_py = fake_root / "src" / "ajar" / "agent.py"
    agent_py.write_text("from . import repomap\n" + agent_py.read_text(encoding="utf-8"), encoding="utf-8")
    llm_py = fake_root / "src" / "ajar" / "llm.py"
    llm_py.write_text(llm_py.read_text(encoding="utf-8") + "\n_A = 1; _B = 2\n", encoding="utf-8")
    swarm_py = fake_root / "src" / "ajar" / "swarm.py"
    swarm_py.write_text(
        swarm_py.read_text(encoding="utf-8") + '\n_WT_CMD = ["git", "worktree", "list"]\n',
        encoding="utf-8",
    )

    bad_report = sz_ajar.audit_repo(fake_root)
    assert bad_report["ok"] is False
    assert bad_report["upward_imports"] != []
    assert bad_report["worktree_violations"] != []
    assert bad_report["files"]["llm.py"]["semicolons"] >= 1
    assert sz_ajar.main([str(fake_root), "--json"]) == 1


def test_phase0_all_four_mechanical_regressions_fixed(tmp_path: Path) -> None:
    from ajar import bench

    probes = bench.run_phase0_probes(tmp_path)
    for probe_id in ("P0-A", "P0-B", "P0-C", "P0-D"):
        assert probe_id in probes, f"Missing probe {probe_id}"
        assert probes[probe_id]["passed"] is True, f"{probe_id} failed: {probes[probe_id]}"
    assert probes["P0-C"]["valid_truth_level"] == "C3"


def test_whiteboard_lockfree_journal_and_atomic_projection(tmp_path: Path) -> None:
    from ajar.whiteboard import Whiteboard

    wb = Whiteboard(tmp_path)
    wb.post("INSIGHT", summary="Length field is attacker-controlled uint16", worker="w1")
    wb.post("BOUNTY", summary="Inspect guard bounds in decode_header", worker="w1", target="src/pkt.c:decode_header")

    c1 = wb.try_claim("src/pkt.c:decode_header", worker_id="w1", ttl_sec=10.0, now=100.0)
    c_conflict = wb.try_claim("src/pkt.c:decode_header", worker_id="w2", ttl_sec=10.0, now=104.0)
    c_reclaim = wb.try_claim("src/pkt.c:decode_header", worker_id="w2", ttl_sec=10.0, now=115.0)
    assert c1["accepted"] is True
    assert c_conflict["accepted"] is False
    assert c_reclaim["accepted"] is True

    wb.post("INVARIANT", summary="hdr->cap >= 64 holds after init_ring()", worker="w2")

    events1, cursor1 = wb.read_delta(0)
    assert len(events1) >= 4
    events2, cursor2 = wb.read_delta(cursor1)
    assert events2 == []
    wb.post("DEAD_END", summary="Integer overflow rejected by upstream clamp", worker="w2")
    events3, _ = wb.read_delta(cursor2)
    assert len(events3) == 1 and "DEAD_END" in events3[0]

    journal_path = tmp_path / ".ajar" / "events.jsonl"
    board_path = tmp_path / ".ajar" / "WHITEBOARD.md"
    assert journal_path.is_file()
    assert board_path.is_file()
    rows = [json.loads(line) for line in journal_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    kinds = {r["kind"] for r in rows}
    assert {"INSIGHT", "BOUNTY", "CLAIM", "INVARIANT", "DEAD_END"}.issubset(kinds)
    assert "init_ring" in board_path.read_text(encoding="utf-8")
    assert list((tmp_path / ".ajar").glob("*.tmp")) == []


def test_epistemic_seen_spans_sink_counterfactual_and_jaccard_rut() -> None:
    from ajar.epistemic import EpistemicGate, SpanTracker

    tracker = SpanTracker()
    tracker.record("src/entry.c", 10, 45)
    tracker.record("src/sink.c", 50, 80)

    assert tracker.is_observed("src/entry.c", 15, 30) is True
    assert tracker.is_observed("src/guard.c", 1, 25) is False

    gate = EpistemicGate(tracker=tracker)
    first_cf = gate.check_sink_counterfactual(
        sink="src/sink.c:60",
        guard_callees=["check_bounds"],
        guard_defs={"check_bounds": ("src/guard.c", 1, 25)},
        tracker=tracker,
    )
    second_cf = gate.check_sink_counterfactual(
        sink="src/sink.c:60",
        guard_callees=["check_bounds"],
        guard_defs={"check_bounds": ("src/guard.c", 1, 25)},
        tracker=tracker,
    )
    assert first_cf is not None
    assert second_cf is None

    distinct_hops = [f"src/hop{i}.c:10" for i in range(1, 6)]
    for hop in distinct_hops:
        assert gate.check_rut(hop) is False
    assert any(gate.check_rut(hop) for hop in distinct_hops * 2) is True

    assert gate.check_pre_prove(
        tracker=tracker,
        entrypoint=("src/entry.c", 15, 30),
        guard=[("src/guard.c", 1, 25)],
    ) is False
    tracker.record("src/guard.c", 1, 25)
    assert gate.check_pre_prove(
        tracker=tracker,
        entrypoint=("src/entry.c", 15, 30),
        guard=[("src/guard.c", 1, 25)],
    ) is True


def test_write_jailed_build_doctor_blocks_source_edits(tmp_path: Path) -> None:
    from ajar.agent import WorkspaceTools

    (tmp_path / ".ajar").mkdir(parents=True, exist_ok=True)
    (tmp_path / "src").mkdir(parents=True, exist_ok=True)
    build_sh = tmp_path / ".ajar" / "build.sh"
    vuln_c = tmp_path / "src" / "vuln.c"
    orig_c = "int vuln(int x) {\n    return x;\n}\n"
    build_sh.write_text("#!/usr/bin/env bash\nexit 1\n", encoding="utf-8")
    vuln_c.write_text(orig_c, encoding="utf-8")

    jailed = WorkspaceTools(tmp_path, write_allowlist={".ajar/build.sh"})
    jailed.write_file(".ajar/build.sh", "#!/usr/bin/env bash\nset -eu\nexit 0\n")
    assert "exit 0" in build_sh.read_text(encoding="utf-8")
    jailed.edit_file(".ajar/build.sh", "exit 0", "echo ok")
    assert "echo ok" in build_sh.read_text(encoding="utf-8")

    with pytest.raises(PermissionError):
        jailed.write_file("src/vuln.c", "int vuln(int x) { return 0; }\n")
    with pytest.raises(PermissionError):
        jailed.write_file(".ajar/../src/vuln.c", "int vuln(int x) { return 0; }\n")
    with pytest.raises(PermissionError):
        jailed.edit_file("src/vuln.c", "return x;", "return 0;")
    assert vuln_c.read_text(encoding="utf-8") == orig_c


def test_live_async_swarm_with_mock_llm_and_ablation_flags(tmp_path: Path) -> None:
    from ajar.cli import build_parser
    from ajar.llm import MockLLMClient
    from ajar.swarm import LiveSwarm, should_drain

    proj = tmp_path / "swarm_target"
    (proj / "src").mkdir(parents=True, exist_ok=True)
    (proj / ".ajar").mkdir(parents=True, exist_ok=True)
    (proj / "src" / "target.c").write_text("int parse(char *p, int n) { return p[n]; }\n", encoding="utf-8")
    build_sh = proj / ".ajar" / "build.sh"
    build_sh.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    build_sh.chmod(0o755)

    runner = LiveSwarm(proj, MockLLMClient(), workers=3, budget_usd=1.0)
    res = asyncio.run(runner.run())
    assert (proj / ".ajar" / "STATUS.md").is_file()
    assert res["workers"] == 3

    assert should_drain(0.50, 1.0) is False
    assert should_drain(0.93, 1.0) is True

    drained = LiveSwarm(proj, MockLLMClient(), workers=3, budget_usd=1.0, spent_usd=0.95)
    res_drained = asyncio.run(drained.run())
    assert res_drained["exploration_frozen"] is True

    parsed = build_parser().parse_args(["run", "--disable-swarm", "--workers", "4", str(proj)])
    assert parsed.disable_swarm is True

    solo = LiveSwarm(proj, MockLLMClient(), workers=4, disable_swarm=True)
    assert solo.workers == 1


def test_scrub_subprocess_env_strips_secrets_across_verify_agent_and_autobuild(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ajar import autobuild, verify
    from ajar.agent import WorkspaceTools
    from ajar.cli import scrub_subprocess_env

    secret_vars = {
        "OPENAI_API_KEY": "sk-test-openai-secret-key",
        "GITHUB_TOKEN": "ghp_test_token_value",
        "AWS_SECRET_ACCESS_KEY": "aws-secret-value",
        "DB_PASSWORD": "db-password-value",
        "BASIC_AUTH_HEADER": "basic-auth-value",
        "GOOGLE_APPLICATION_CREDENTIALS": "/tmp/fake-cred.json",
    }
    for k, v in secret_vars.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("AJAR_SAFE_TEST_MARKER", "visible_non_secret_value")

    cleaned = scrub_subprocess_env({"AJAR_EXTRA_FLAG": "1"})
    for k in secret_vars:
        assert k not in cleaned
    assert cleaned["AJAR_SAFE_TEST_MARKER"] == "visible_non_secret_value"
    assert cleaned["AJAR_EXTRA_FLAG"] == "1"

    rc_v, out_v = verify._run_proc("env", cwd=tmp_path)
    assert rc_v == 0
    assert "AJAR_SAFE_TEST_MARKER=visible_non_secret_value" in out_v
    for k, v in secret_vars.items():
        assert k not in out_v and v not in out_v

    res_a = WorkspaceTools(tmp_path).exec_cmd("env")
    assert res_a.returncode == 0
    assert "AJAR_SAFE_TEST_MARKER=visible_non_secret_value" in res_a.output
    for k, v in secret_vars.items():
        assert k not in res_a.output and v not in res_a.output

    build_sh = tmp_path / ".ajar" / "build.sh"
    build_sh.parent.mkdir(parents=True, exist_ok=True)
    build_sh.write_text("#!/usr/bin/env bash\nset -euo pipefail\nenv\n", encoding="utf-8")
    build_sh.chmod(0o755)
    rc_b, out_b = autobuild._run_build_script(tmp_path, profile="upstream")
    assert rc_b == 0
    assert "AJAR_SAFE_TEST_MARKER=visible_non_secret_value" in out_b
    for k, v in secret_vars.items():
        assert k not in out_b and v not in out_b


def test_cli_bench_phase0_exit_code_reflects_probe_pass_and_fail(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ajar import bench, cli

    monkeypatch.setattr(
        bench,
        "run_phase0_probes",
        lambda _out: {"P0-A": {"passed": True}, "P0-B": {"passed": False}},
    )
    assert cli.main(["bench", "--phase0", "--out", str(tmp_path / "fail")]) == 1

    monkeypatch.setattr(
        bench,
        "run_phase0_probes",
        lambda _out: {
            "P0-A": {"passed": True},
            "P0-B": {"passed": True},
            "P0-C": {"passed": True},
            "P0-D": {"passed": True},
        },
    )
    assert cli.main(["bench", "--phase0", "--out", str(tmp_path / "pass")]) == 0


def test_export_reports_enforces_c3_voice_lint_and_omits_withdrawn_or_rejected(
    tmp_path: Path,
) -> None:
    from ajar import cli
    from ajar.cli import Candidate, Verdict, ajar_dir, append_jsonl

    export_reports = _load_extra_report().export_reports

    clean_repo = tmp_path / "clean_repo"
    clean_repo.mkdir()
    sd = ajar_dir(clean_repo)

    c3_clean = Candidate(
        id="ADV-CLEAN",
        title="Cross-tenant note disclosure in get_note",
        severity="high",
        entry_span="app.py:17",
        sink_symbol="get_note",
        repro_cmd="python3 app.py --selftest poc",
        root_cause=(
            "In `app.py:17`, `get_note()` checks authentication (`not requester`) but omits "
            "the tenant ownership check (`requester != tenant`), allowing an authenticated "
            "caller in `tenant_a` to read notes owned by `tenant_b`."
        ),
        impact=(
            "Any authenticated tenant can read arbitrary private notes belonging to another "
            "tenant by passing the victim tenant identifier in the request path."
        ),
        patch_diff=(
            "--- a/app.py\n+++ b/app.py\n@@ -17,6 +17,8 @@\n"
            " def get_note(tenant: str, note_id: str, requester: str):\n"
            "     if not requester:\n"
            "         return 401, {'error': 'unauthenticated'}\n"
            "+    if requester != tenant:\n"
            "+        return 403, {'error': 'forbidden'}\n"
        ),
    )
    c2_note = Candidate(
        id="NOTE-C2",
        title="Unconfirmed timing side channel",
        severity="medium",
        entry_span="app.py:21",
        sink_symbol="get_note",
        repro_cmd="python3 app.py --selftest control",
    )
    withdrawn_cand = Candidate(
        id="WD-001",
        title="Withdrawn draft must be omitted",
        severity="high",
        withdrawn=True,
    )
    rejected_cand = Candidate(
        id="REJ-001",
        title="Rejected draft must be omitted",
        severity="high",
    )
    for cand in (c3_clean, c2_note, withdrawn_cand, rejected_cand):
        append_jsonl(sd / "candidates.jsonl", cand)
    for verd in (
        Verdict("ADV-CLEAN", "VERIFIED", "C3", 3, 3, critic_verdict="APPROVED"),
        Verdict("NOTE-C2", "VERIFIED", "C2", 3, 3, critic_verdict="SKIPPED"),
        Verdict("WD-001", "WITHDRAWN", "C0", 0, 0, critic_verdict="SKIPPED"),
        Verdict("REJ-001", "REJECTED", "C0", 0, 0, critic_verdict="REJECTED"),
    ):
        append_jsonl(sd / "verdicts.jsonl", verd)

    out_clean = tmp_path / "out_clean"
    rep_clean = export_reports(clean_repo, out_clean)
    assert rep_clean["lint_passed"] is True, f"Unexpected lint issues: {rep_clean['lint_issues']}"
    assert rep_clean["lint_score"] == 100
    assert [p.name for p in rep_clean["advisories"]] == ["ADV-CLEAN.md"]
    assert [p.name for p in rep_clean["hardening_notes"]] == ["NOTE-C2.md"]
    assert not (out_clean / "advisories" / "WD-001.md").exists()
    assert not (out_clean / "hardening-notes" / "WD-001.md").exists()
    assert not (out_clean / "advisories" / "REJ-001.md").exists()
    assert not (out_clean / "hardening-notes" / "REJ-001.md").exists()
    assert cli.main(["report", str(clean_repo), "--out", str(tmp_path / "cli_clean")]) == 0

    jargon_repo = tmp_path / "jargon_repo"
    jargon_repo.mkdir()
    j_sd = ajar_dir(jargon_repo)
    jargon_cand = Candidate(
        id="ADV-SLOP",
        title="Cross-tenant note disclosure tracked as clm-abcdef12",
        severity="high",
        entry_span="app.py:17",
        sink_symbol="get_note",
        repro_cmd="python3 app.py --selftest poc",
        root_cause=(
            "This finding was found_autonomously_by_ajar via ajar-investigate as clm-abcdef12 "
            "and verified_local in our harness."
        ),
        impact="Unauthorized cross-tenant note read via missing authorization check.",
        patch_diff=c3_clean.patch_diff,
    )
    append_jsonl(j_sd / "candidates.jsonl", jargon_cand)
    append_jsonl(
        j_sd / "verdicts.jsonl",
        Verdict("ADV-SLOP", "VERIFIED", "C3", 3, 3, critic_verdict="APPROVED"),
    )
    rep_jargon = export_reports(jargon_repo, tmp_path / "out_jargon")
    assert rep_jargon["lint_passed"] is False
    assert "ADV-SLOP" in rep_jargon["lint_issues"]
    assert cli.main(["report", str(jargon_repo), "--out", str(tmp_path / "cli_jargon")]) == 1


def test_verify_candidate_critic_leading_token_precedence(tmp_path: Path) -> None:
    from ajar.cli import BuildRecipe, Candidate
    from ajar.llm import MockLLMClient
    from ajar.verify import verify_candidate

    repo = tmp_path / "critic_repo"
    repo.mkdir()
    (repo / "check.py").write_text(
        "import sys\n"
        "def check_len(n: int) -> int:\n"
        "    if n > 32:\n"
        "        return -1\n"
        "    if n > 16:\n"
        "        print('BOUNDS_CORRUPTED')\n"
        "        return 1\n"
        "    return 0\n"
        "sys.exit(check_len(20))\n",
        encoding="utf-8",
    )
    patch = (
        "--- a/check.py\n"
        "+++ b/check.py\n"
        "@@ -1,8 +1,8 @@\n"
        " import sys\n"
        " def check_len(n: int) -> int:\n"
        "-    if n > 32:\n"
        "-        return -1\n"
        "+    if n > 16:\n"
        "+        return 0\n"
        "     if n > 16:\n"
        "         print('BOUNDS_CORRUPTED')\n"
        "         return 1\n"
    )
    cand = Candidate(
        id="CRITIC-PREC-1",
        title="Bounds check off-by-limit",
        severity="high",
        repro_cmd="python3 check.py",
        failure_oracle="BOUNDS_CORRUPTED",
        patch_diff=patch,
    )
    recipe = BuildRecipe(profile="upstream", build_script="")
    approve_critic = MockLLMClient(["APPROVE: rejects invalid length and is not a false positive"])
    v_ok = verify_candidate(repo, cand, recipe=recipe, llm=approve_critic, runs=1)
    assert v_ok.status == "VERIFIED"
    assert v_ok.truth_level == "C3"
    assert v_ok.critic_verdict == "APPROVED"

    reject_critic = MockLLMClient(["REJECT: false positive with no real boundary violation"])
    v_rej = verify_candidate(repo, cand, recipe=recipe, llm=reject_critic, runs=1)
    assert v_rej.status == "REJECTED"
    assert v_rej.critic_verdict == "REJECTED"


def test_run_bench_executes_all_fifteen_targets(tmp_path: Path) -> None:
    from ajar import bench

    res = bench.run_bench(REPO_ROOT / "benchmarks", tmp_path)
    assert res["all_passed"] is True
    assert res["suite_targets_total"] == 15
    assert (tmp_path / "bench_report.json").is_file()

    poly = res["polyglot"]
    assert poly["targets_total"] == 4
    assert poly["patches_total"] == 8
    assert poly["patches_matched"] == 8
    assert poly["valid_patches_verified"] == 4
    assert poly["neg_controls_rejected"] == 4
    assert res["profile"]["valid_patch_pass_rate"] == 1.0
    assert res["profile"]["neg_control_rejection_rate"] == 1.0

    herm = res["hermetic"]
    assert herm["targets_total"] == 8
    assert herm["targets_passed"] == 8
    assert herm["fp_count"] == 0
    assert herm["fp_rate"] == 0.0
    trap_eval = bench.evaluate_hermetic_request(
        {"oracle": "bopla_property_authz"},
        {
            "operation": "write",
            "echoed_guarded_property": True,
            "persisted_guarded_property": False,
            "effective_property_impact": False,
        },
    )
    assert trap_eval == {"signal": False, "effect": False, "control_ok": False}

    fnd = res["foundry"]
    assert fnd["targets_total"] == 3
    assert fnd["static_ready_count"] == 3
    assert fnd["targets"]["curve-readonly-reentrancy"]["execution_status"] == "skipped_requires_rpc"
    for offline_name in ("erc4626-first-depositor", "jpegd-reentrancy"):
        entry = fnd["targets"][offline_name]
        assert entry["static_ready"] is True
        assert entry["build_system"] == "foundry"
        if fnd["forge_available"]:
            assert entry["execution_status"] == "passed"
        else:
            assert entry["execution_status"] == "skipped_missing_tool"
            assert entry["missing_tool"] == "forge"



def test_verify_v361_anti_gaming_blocks_attacks_and_surfaces_full_critic_evidence(
    tmp_path: Path,
) -> None:
    from ajar.cli import BuildRecipe, Candidate
    from ajar.llm import MockLLMClient
    from ajar.verify import verify_candidate

    src_c = REPO_ROOT / "benchmarks" / "polyglot" / "c_parser"
    repo = tmp_path / "c_parser"
    shutil.copytree(src_c, repo)
    valid_patch = (repo / "patches" / "valid_fix.patch").read_text(encoding="utf-8")
    recipe = BuildRecipe(profile="upstream", build_script="make", test_cmd="./parser --selftest")

    # G1: python3 -c with import os reading source file
    g1 = Candidate(
        id="G1",
        title="Static import os source grep",
        severity="high",
        repro_cmd="python3 -c \"import os,sys; sys.exit(1 if 'decl_len > 32' in open('parser.c').read() else 0)\"",
        patch_diff=valid_patch,
    )
    assert verify_candidate(repo, g1, recipe=recipe, llm=None, runs=1).status == "REJECTED"

    # EV2: decoy subprocess + open() on tracked source file
    ev2 = Candidate(
        id="EV2",
        title="Decoy subprocess plus source read",
        severity="high",
        repro_cmd="python3 -c \"import subprocess,sys; subprocess.run(['true']); sys.exit(1 if 'decl_len > 32' in open('parser.c').read() else 0)\"",
        patch_diff=valid_patch,
    )
    assert verify_candidate(repo, ev2, recipe=recipe, llm=None, runs=1).status == "REJECTED"

    # G2: patch modifying Makefile instead of parser.c
    makefile_patch = (
        "--- a/Makefile\n+++ b/Makefile\n@@ -1,3 +1,3 @@\n"
        "-all: parser\n+all: parser\n+# noop\n"
    )
    g2 = Candidate(
        id="G2",
        title="Patch edits Makefile",
        severity="high",
        repro_cmd="./parser --hex 42144141414141414141414141414141414158585858",
        patch_diff=makefile_patch,
    )
    assert verify_candidate(repo, g2, recipe=recipe, llm=None, runs=1).status == "REJECTED"

    # G3: hardcoded single-input crash-frame bandaid defeated by mutated PoV
    bandaid_patch = (
        "--- a/parser.c\n+++ b/parser.c\n@@ -35,6 +35,8 @@ int parse_packet(const uint8_t *buf, size_t total_len, char *out, size_t out_cap\n"
        "     } else if (tag == 0x42) {\n"
        "+        if (decl_len == 20 && buf[2] == 0x41) return -3;\n"
        "         /* BUG: checks 32 instead of sizeof(frame.payload) (16). */\n"
        "         if (decl_len > 32) {\n"
    )
    g3 = Candidate(
        id="G3",
        title="Crash-frame bandaid",
        severity="high",
        repro_cmd="./parser --hex 42144141414141414141414141414141414158585858",
        patch_diff=bandaid_patch,
    )
    assert verify_candidate(repo, g3, recipe=recipe, llm=None, runs=1).status == "REJECTED"

    # G4: hidden local script grepping source
    (repo / ".ajar").mkdir(exist_ok=True)
    (repo / ".ajar" / "repro.sh").write_text(
        "#!/bin/sh\ngrep -q 'decl_len > 32' parser.c && exit 1 || exit 0\n",
        encoding="utf-8",
    )
    g4 = Candidate(
        id="G4",
        title="Hidden repro script grep",
        severity="high",
        repro_cmd="sh .ajar/repro.sh",
        patch_diff=valid_patch,
    )
    assert verify_candidate(repo, g4, recipe=recipe, llm=None, runs=1).status == "REJECTED"

    # L1: legitimate c_parser fix passes C3 and Critic receives full evidence packet
    (repo / ".ajar" / "REALITY.md").write_text("# Target Reality\nC packet parser\n", encoding="utf-8")
    critic = MockLLMClient(["APPROVE: verified root-cause bounds fix"])
    l1 = Candidate(
        id="L1",
        title="Stack buffer overflow in parse_packet",
        severity="high",
        repro_cmd="./parser --hex 42144141414141414141414141414141414158585858",
        control_cmd="./parser --selftest",
        patch_diff=valid_patch,
    )
    v_ok = verify_candidate(repo, l1, recipe=recipe, llm=critic, runs=1)
    assert v_ok.status == "VERIFIED"
    assert v_ok.truth_level == "C3"
    assert critic.calls, "Critic must be invoked"
    critic_user_msg = critic.calls[-1]["messages"][0]["content"]
    assert "Pre-patch Output:" in critic_user_msg
    assert "Post-patch Output:" in critic_user_msg
    assert "Patch Diff:" in critic_user_msg


def test_swarm_v361_live_build_doctor_8_worker_fanout_and_drain_reserve(
    tmp_path: Path,
) -> None:
    from ajar.chain_weaver import EffectType, post_effect, post_wish, weave_candidates
    from ajar.cli import AblationConfig, RunConfig
    from ajar.llm import MockLLMClient
    from ajar.swarm import LiveSwarm
    from ajar.whiteboard import Whiteboard

    # 1. Broken Makefile triggers Wave-0 Build Doctor; 8 workers execute 8 slots with default 24 steps
    repo = tmp_path / "broken_c"
    repo.mkdir()
    (repo / "Makefile").write_text("all:\n\tfalse\n", encoding="utf-8")
    (repo / "app.c").write_text("int main(void) { return 0; }\n", encoding="utf-8")

    doctor_fix = json.dumps({
        "path": ".ajar/build.sh",
        "content": "#!/usr/bin/env bash\nset -euo pipefail\necho DOCTOR_OK\n",
    })
    llm = MockLLMClient([doctor_fix] + ["DONE"] * 12)
    cfg = RunConfig(
        repo=repo,
        workers=8,
        budget_usd=25.0,
        ablation=AblationConfig(disable_repomap=True, disable_chain_weaver=True),
    )
    swarm = LiveSwarm(cfg, llm=llm)
    assert swarm.workers == 8
    assert swarm.worker_max_steps == 24
    res = asyncio.run(swarm.run())
    assert res["build_doctor_invoked"] is True
    assert res["build_verified"] is True
    assert res["slots_executed"] == 8

    # 2. Drain-phase chain_weaver passes allow_drain_reserve=True
    wb_repo = tmp_path / "wb_repo"
    wb_repo.mkdir()
    wb = Whiteboard(wb_repo)
    post_effect(
        wb,
        EffectType.PRIVILEGE_OR_CAPABILITY_SMUGGLING,
        span="app.py:10",
        summary="Smuggle admin role",
        worker_id="W0",
    )
    post_wish(
        wb,
        EffectType.PRIVILEGE_OR_CAPABILITY_SMUGGLING,
        sink_span="app.py:50",
        impact="Admin command execution",
        worker_id="W1",
    )
    weaver_llm = MockLLMClient([
        json.dumps({
            "id": "CH-1",
            "title": "Role smuggling to admin_exec",
            "severity": "high",
            "entry_span": "app.py:10",
            "sink_symbol": "admin_exec",
            "repro_cmd": "python3 app.py",
            "patch_diff": "",
            "root_cause": "Missing auth check",
            "impact": "Admin action",
        })
    ])
    woven = asyncio.run(weave_candidates(wb_repo, wb, weaver_llm))
    assert len(woven) == 1
    assert weaver_llm.calls[-1]["allow_drain_reserve"] is True
