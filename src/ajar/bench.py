"""Ring-1 local Phase-0 deterministic probes and Leave-One-Out empirical rent scorer."""

from __future__ import annotations

import difflib
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from ajar.autobuild import synthesize_build_recipe
from ajar.chain_weaver import (
    CarrierKind,
    EffectType,
    join_effects_and_wishes,
    post_effect,
    post_wish,
)
from ajar.cli import AblationConfig, BuildRecipe, Candidate
from ajar.llm import MockLLMClient
from ajar.repomap import build_repomap_and_reality, index_repo
from ajar.verify import verify_candidate
from ajar.whiteboard import StigmergicWhiteboard


def _probe_p0_a(work_dir: Path) -> dict[str, Any]:
    repo = work_dir / "p0_a"
    if repo.exists():
        shutil.rmtree(repo)
    repo.mkdir(parents=True)
    vault_sol = (
        "// SPDX-License-Identifier: MIT\n"
        "pragma solidity ^0.8.20;\n"
        "contract Vault {\n"
        "    mapping(address => uint256) public balances;\n"
        "    function withdraw(uint256 amt) external {\n"
        '        (bool ok, ) = msg.sender.call{value: amt}("");\n'
        "        require(ok);\n"
        "        balances[msg.sender] -= amt;\n"
        "    }\n"
        "    function execute(address target, bytes calldata data) external {\n"
        "        (bool ok, ) = target.delegatecall(data);\n"
        "        require(ok);\n"
        "    }\n"
        "}\n"
    )
    (repo / "Vault.sol").write_text(vault_sol, encoding="utf-8")
    idx = index_repo(repo)
    reality_md = build_repomap_and_reality(repo).read_text(encoding="utf-8")
    syms = idx.get("files", {}).get("Vault.sol", {}).get("symbols", [])
    sinks = {s for sym in syms for s in sym.get("sinks", [])}
    passed = ("Vault.sol" in reality_md) and (".call{" in sinks) and ("delegatecall" in sinks)
    return {"passed": passed, "sinks": sorted(sinks)}


def _probe_p0_b(work_dir: Path) -> dict[str, Any]:
    repo = work_dir / "p0_b"
    if repo.exists():
        shutil.rmtree(repo)
    repo.mkdir(parents=True)
    cmake_txt = (
        "cmake_minimum_required(VERSION 3.16)\n"
        "project(p0b_cxx CXX)\n"
        "add_executable(p0b main.cpp)\n"
    )
    (repo / "CMakeLists.txt").write_text(cmake_txt, encoding="utf-8")
    (repo / "main.cpp").write_text("int main() { return 0; }\n", encoding="utf-8")
    recipe = synthesize_build_recipe(repo, profile="upstream")
    script = repo / ".ajar" / "build.sh"
    if not script.is_file() or not os.access(script, os.X_OK):
        return {"passed": False, "reason": "missing executable .ajar/build.sh"}
    body = script.read_text(encoding="utf-8")
    checks = (
        "set -euo pipefail" in body,
        "CXXFLAGS=" in body,
        "LDFLAGS=" in body,
        "-fsanitize=address,undefined" in body,
        "-fno-omit-frame-pointer" in body,
        "-DCMAKE_CXX_FLAGS=" in body,
        "-DCMAKE_EXE_LINKER_FLAGS=" in body,
        "CMAKE_BUILD_PARALLEL_LEVEL=" in body,
        not recipe.static_only,
    )
    return {"passed": all(checks)}


def _probe_p0_c(work_dir: Path) -> dict[str, Any]:
    repo = work_dir / "p0_c"
    if repo.exists():
        shutil.rmtree(repo)
    (repo / ".ajar").mkdir(parents=True)

    cc_bin = shutil.which("cc") or shutil.which("gcc")
    if cc_bin is not None:
        orig_src = (
            "#include <stdio.h>\n"
            "#include <stdlib.h>\n"
            "#include <string.h>\n"
            "int decode_frame(const char *buf) {\n"
            "    if (strncmp(buf, \"BOOM\", 4) == 0) {\n"
            "        fprintf(stderr, \"ERROR: AddressSanitizer: heap-buffer-overflow\\n\");\n"
            "        fprintf(stderr, \"    #0 0x401122 in decode_frame vuln.c:7\\n\");\n"
            "        abort();\n"
            "    }\n"
            "    return 0;\n"
            "}\n"
            "int main(int argc, char **argv) {\n"
            "    return decode_frame(argc > 1 ? argv[1] : \"OK\");\n"
            "}\n"
        )
        stale_src = orig_src + "/* comment-only edit that leaves binary broken after rebuild */\n"
        fixed_src = orig_src.replace(
            "        fprintf(stderr, \"ERROR: AddressSanitizer: heap-buffer-overflow\\n\");\n"
            "        fprintf(stderr, \"    #0 0x401122 in decode_frame vuln.c:7\\n\");\n"
            "        abort();\n",
            "        return 0;\n",
        )
        src_name = "vuln.c"
        build_body = f"#!/usr/bin/env bash\nset -euo pipefail\n{cc_bin} -O1 -g vuln.c -o vuln\n"
        repro_cmd = "./vuln BOOM"
    else:
        orig_src = "MODE=CRASH_decode_frame\n"
        stale_src = "MODE=CRASH_decode_frame\n# noop\n"
        fixed_src = "MODE=SAFE\n"
        src_name = "vuln.src"
        build_body = (
            "#!/usr/bin/env bash\nset -euo pipefail\n"
            "python3 -c 'import pathlib; m=pathlib.Path(\"vuln.src\").read_text();"
            "p=pathlib.Path(\"vuln\");"
            "p.write_text(\"#!/usr/bin/env bash\\n\" + (\"echo ERROR: AddressSanitizer: decode_frame >&2; exit 134\\n\" if \"CRASH\" in m else \"exit 0\\n\"));"
            "p.chmod(0o755)'\n"
        )
        repro_cmd = "./vuln BOOM"

    (repo / src_name).write_text(orig_src, encoding="utf-8")
    build_sh = repo / ".ajar" / "build.sh"
    build_sh.write_text(build_body, encoding="utf-8")
    os.chmod(build_sh, 0o755)
    subprocess.run(["bash", str(build_sh)], cwd=str(repo), check=True)

    git_env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "ajar",
        "GIT_AUTHOR_EMAIL": "ajar@local",
        "GIT_COMMITTER_NAME": "ajar",
        "GIT_COMMITTER_EMAIL": "ajar@local",
    }
    subprocess.run(["git", "init", "-q"], cwd=str(repo), env=git_env, check=True)
    subprocess.run(["git", "add", "-f", "."], cwd=str(repo), env=git_env, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=str(repo), env=git_env, check=True)

    stale_diff = "".join(
        difflib.unified_diff(
            orig_src.splitlines(keepends=True),
            stale_src.splitlines(keepends=True),
            fromfile=f"a/{src_name}",
            tofile=f"b/{src_name}",
        )
    )
    valid_diff = "".join(
        difflib.unified_diff(
            orig_src.splitlines(keepends=True),
            fixed_src.splitlines(keepends=True),
            fromfile=f"a/{src_name}",
            tofile=f"b/{src_name}",
        )
    )
    recipe = BuildRecipe(profile="upstream", build_script="bash .ajar/build.sh")
    stale_cand = Candidate(
        id="P0C-STALE",
        title="Noop patch must fail post-patch rebuild check",
        severity="high",
        entry_span=f"{src_name}:4",
        sink_symbol="decode_frame",
        repro_cmd=repro_cmd,
        failure_oracle="AddressSanitizer",
        patch_diff=stale_diff,
    )
    valid_cand = Candidate(
        id="P0C-VALID",
        title="Fix decode_frame overflow",
        severity="high",
        entry_span=f"{src_name}:4",
        sink_symbol="decode_frame",
        repro_cmd=repro_cmd,
        failure_oracle="AddressSanitizer",
        patch_diff=valid_diff,
    )
    critic = MockLLMClient(["APPROVE: root-cause bounds check verified"])
    v_stale = verify_candidate(repo, stale_cand, recipe=recipe, llm=critic, runs=3)
    v_valid = verify_candidate(repo, valid_cand, recipe=recipe, llm=critic, runs=3)
    passed = (v_stale.status == "REJECTED") and (v_valid.status == "VERIFIED") and (v_valid.truth_level == "C3")
    return {
        "passed": passed,
        "stale_status": v_stale.status,
        "valid_truth_level": v_valid.truth_level,
    }


def _probe_p0_d(work_dir: Path) -> dict[str, Any]:
    repo = work_dir / "p0_d"
    if repo.exists():
        shutil.rmtree(repo)
    (repo / ".ajar").mkdir(parents=True)
    wb = StigmergicWhiteboard(repo)
    post_effect(
        wb,
        EffectType.REENTRANT_CALLBACK_WINDOW,
        CarrierKind.CROSS_CONTRACT_OR_IPC_CALL,
        span="contracts/Vault.sol:91-112",
        summary="External recipient hook fires prior to ledger decrement",
        worker_id="W0",
    )
    post_wish(
        wb,
        EffectType.STALE_CACHE_OR_ORACLE_READ,
        CarrierKind.CROSS_CONTRACT_OR_IPC_CALL,
        sink_span="modules/LendingMarket.sol:204-229",
        impact="Collateral check trusts spot exchange ratio during liquidation",
        worker_id="W1",
    )
    post_wish(
        wb,
        EffectType.CROSS_SESSION_KEY_REUSE,
        CarrierKind.WIRE_OR_CONTAINER_FRAME,
        sink_span="net/framing.c:40-55",
        impact="Ticket cache collides across virtual hosts",
        worker_id="W2",
    )
    joins = join_effects_and_wishes(wb)
    expected = ["contracts/Vault.sol:91-112", "modules/LendingMarket.sol:204-229"]
    passed = len(joins) == 1 and joins[0]["hops"] == expected
    return {"passed": passed, "matched_joins": len(joins)}


def run_phase0_probes(work_dir: Path | None = None) -> dict[str, dict[str, Any]]:
    root = Path(work_dir or Path("/tmp/ajar-phase0"))
    root.mkdir(parents=True, exist_ok=True)
    probes = (
        ("P0-A", _probe_p0_a),
        ("P0-B", _probe_p0_b),
        ("P0-C", _probe_p0_c),
        ("P0-D", _probe_p0_d),
    )
    results: dict[str, dict[str, Any]] = {}
    for name, fn in probes:
        try:
            results[name] = fn(root)
        except Exception as exc:
            results[name] = {"passed": False, "error": str(exc)}
    return results


def evaluate_rent_rule(
    baseline_metrics: dict[str, Any],
    module_metrics: dict[str, Any],
    loc_added: int,
) -> dict[str, Any]:
    b_rec = float(baseline_metrics.get("recall", 0.0))
    m_rec = float(module_metrics.get("recall", 0.0))
    delta_recall = m_rec - b_rec

    b_fp = float(baseline_metrics.get("fp_rate", 0.0))
    m_fp = float(module_metrics.get("fp_rate", 0.0))
    delta_fp_reduction = b_fp - m_fp

    b_hops = float(baseline_metrics.get("chain_hops", 1.0))
    m_hops = float(module_metrics.get("chain_hops", 1.0))
    delta_chain_hops = m_hops - b_hops

    b_cost = max(0.001, float(baseline_metrics.get("cost_usd", 1.0)))
    m_cost = float(module_metrics.get("cost_usd", b_cost))
    delta_cost_ratio = (m_cost - b_cost) / b_cost
    friction_rate = float(module_metrics.get("friction_rate", 0.0))

    pays_benefit = (
        delta_recall >= 0.05
        or (delta_fp_reduction >= 0.05 and delta_recall >= 0.0)
        or (delta_chain_hops >= 0.5 and delta_recall >= 0.0)
        or (delta_cost_ratio <= -0.15 and delta_recall >= 0.0)
    )
    reasons: list[str] = []
    if not pays_benefit:
        reasons.append("insufficient lift across recall, FP reduction, chain hops, or cost")
    if delta_recall < -0.01:
        reasons.append("recall regressed > 1%")
    if friction_rate > 0.05:
        reasons.append("worker friction exceeds 5% ceiling")
    if loc_added > 600:
        reasons.append("module exceeds 600 SLOC cap")

    verdict = "KEEP" if (pays_benefit and not reasons) else "EVICT"
    return {
        "verdict": verdict,
        "keep": verdict == "KEEP",
        "loc_added": int(loc_added),
        "delta_recall": round(delta_recall, 4),
        "delta_fp_reduction": round(delta_fp_reduction, 4),
        "delta_chain_hops": round(delta_chain_hops, 4),
        "delta_cost_ratio": round(delta_cost_ratio, 4),
        "friction_rate": round(friction_rate, 4),
        "reasons": reasons,
    }


def run_bench(
    suite: Path,
    out_dir: Path,
    ablation: AblationConfig | None = None,
) -> dict[str, Any]:
    del suite
    out_dir.mkdir(parents=True, exist_ok=True)
    phase0 = run_phase0_probes(out_dir / "phase0")
    return {
        "phase0": phase0,
        "phase0_all_passed": all(v.get("passed", False) for v in phase0.values()),
        "ablation": vars(ablation) if ablation is not None else {},
    }
