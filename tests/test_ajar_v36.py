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


def test_sz_ajar_structural_and_anti_golf_gates(tmp_path: Path) -> None:
    sz_ajar = _load_sz_ajar()
    report = sz_ajar.audit_repo(REPO_ROOT)

    assert report["ok"] is True, f"sz_ajar violations: {report['violations']}"
    assert report["logic_module_count"] == 11
    assert 0 < report["ring0_sloc"] <= 1800
    assert 0 < report["epistemic_sloc"] <= 180
    assert report["upward_imports"] == []
    assert report["worktree_violations"] == []
    assert set(report["registered_disable_flags"]) == set(sz_ajar.REQUIRED_DISABLE_FLAGS)
    assert len(report["registered_disable_flags"]) == 7
    assert sz_ajar.main([str(REPO_ROOT), "--json"]) == 0

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
