"""Ring-1 local Phase-0 deterministic probes, 15-target benchmark suite, and rent scorer."""

from __future__ import annotations

import difflib
import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
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
from ajar.cli import AblationConfig, BuildRecipe, Candidate, scrub_subprocess_env
from ajar.llm import MockLLMClient
from ajar.repomap import build_repomap_and_reality, index_repo
from ajar.verify import verify_candidate
from ajar.whiteboard import StigmergicWhiteboard


@dataclass(frozen=True)
class PolyglotPatchSpec:
    filename: str
    expected_status: str


@dataclass(frozen=True)
class PolyglotTargetSpec:
    name: str
    build_cmd: str
    test_cmd: str
    repro_cmd: str
    failure_oracle: str
    patches: tuple[PolyglotPatchSpec, ...]


@dataclass(frozen=True)
class FoundryTargetSpec:
    name: str
    requires_rpc: bool


POLYGLOT_TARGETS: tuple[PolyglotTargetSpec, ...] = (
    PolyglotTargetSpec(
        name="c_parser",
        build_cmd="make clean && make",
        test_cmd="./parser --selftest",
        repro_cmd="./parser --hex 42144141414141414141414141414141414158585858",
        failure_oracle="FRAME_GUARD_CORRUPTED",
        patches=(
            PolyglotPatchSpec("valid_fix.patch", "VERIFIED"),
            PolyglotPatchSpec("bad_destructive.patch", "REJECTED"),
            PolyglotPatchSpec("wrong_locus.patch", "REJECTED"),
        ),
    ),
    PolyglotTargetSpec(
        name="go_ledger",
        build_cmd="go test -c . -o /dev/null",
        test_cmd="go test ./...",
        repro_cmd="RUN_POC=1 go test -count=1 -run TestPoCSelfTransferConservation ./...",
        failure_oracle="CONSERVATION_VIOLATED",
        patches=(
            PolyglotPatchSpec("valid_fix.patch", "VERIFIED"),
            PolyglotPatchSpec("bad_destructive.patch", "REJECTED"),
        ),
    ),
    PolyglotTargetSpec(
        name="py_live_service",
        build_cmd="",
        test_cmd="python3 app.py --selftest control",
        repro_cmd="python3 app.py --selftest poc",
        failure_oracle="IDOR_LEAKED",
        patches=(PolyglotPatchSpec("valid_fix.patch", "VERIFIED"),),
    ),
    PolyglotTargetSpec(
        name="rust_vault",
        build_cmd="cargo test --offline --no-run",
        test_cmd="cargo test --offline",
        repro_cmd="RUN_POC=1 cargo test --offline test_poc_rounding_drain",
        failure_oracle="ROUNDING_DRAIN",
        patches=(
            PolyglotPatchSpec("valid_fix.patch", "VERIFIED"),
            PolyglotPatchSpec("wrong_locus.patch", "REJECTED"),
        ),
    ),
)

FOUNDRY_TARGETS: tuple[FoundryTargetSpec, ...] = (
    FoundryTargetSpec(name="erc4626-first-depositor", requires_rpc=False),
    FoundryTargetSpec(name="jpegd-reentrancy", requires_rpc=False),
    FoundryTargetSpec(name="curve-readonly-reentrancy", requires_rpc=True),
)

_ACTIVE_HTML_RE = re.compile(
    r"<(?:script\b[^>]*>|[a-z]+\b[^>]*\bon[a-z]+\s*=)",
    re.IGNORECASE,
)


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


def _copy_isolated(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        src,
        dst,
        symlinks=True,
        ignore=shutil.ignore_patterns(".git", ".ajar", "target", "__pycache__", "out", "cache"),
    )


def run_polyglot_suite(
    suite_root: Path,
    out_dir: Path,
    ablation: AblationConfig | None = None,
) -> dict[str, Any]:
    poly_src_root = suite_root / "polyglot"
    poly_out_root = out_dir / "polyglot"
    poly_out_root.mkdir(parents=True, exist_ok=True)
    disable_repomap = bool(ablation.disable_repomap) if ablation is not None else False

    targets_report: dict[str, Any] = {}
    patches_total = 0
    patches_matched = 0
    valid_total = 0
    valid_verified = 0
    neg_total = 0
    neg_rejected = 0
    total_runtime_ms = 0.0
    total_cost_usd = 0.0

    for spec in POLYGLOT_TARGETS:
        t_start = time.perf_counter()
        src_dir = poly_src_root / spec.name
        work_repo = poly_out_root / spec.name
        if not src_dir.is_dir():
            targets_report[spec.name] = {
                "passed": False,
                "error": f"missing target directory: {spec.name}",
                "patches": [],
            }
            patches_total += len(spec.patches)
            continue

        _copy_isolated(src_dir, work_repo)
        repomap_files = 0
        if not disable_repomap:
            idx = index_repo(work_repo)
            repomap_files = len(idx.get("files", {}))

        recipe = BuildRecipe(
            profile="upstream",
            build_script=spec.build_cmd,
            test_cmd=spec.test_cmd,
        )
        patch_rows: list[dict[str, Any]] = []
        target_cost = 0.0
        for pspec in spec.patches:
            patches_total += 1
            if pspec.expected_status == "VERIFIED":
                valid_total += 1
            else:
                neg_total += 1

            p_start = time.perf_counter()
            patch_path = src_dir / "patches" / pspec.filename
            patch_diff = patch_path.read_text(encoding="utf-8") if patch_path.is_file() else ""
            cand_id = f"{spec.name}-{pspec.filename.removesuffix('.patch')}"
            cand = Candidate(
                id=cand_id,
                title=f"{spec.name} ({pspec.filename})",
                severity="high",
                repro_cmd=spec.repro_cmd,
                failure_oracle=spec.failure_oracle,
                patch_diff=patch_diff,
            )
            critic = MockLLMClient(["APPROVE: verified minimal fix"])
            verdict = verify_candidate(work_repo, cand, recipe=recipe, llm=critic, runs=1)
            p_ms = round((time.perf_counter() - p_start) * 1000.0, 2)
            p_cost = 0.0
            matched = verdict.status == pspec.expected_status
            if pspec.expected_status == "VERIFIED":
                matched = matched and verdict.truth_level == "C3"
                if matched:
                    valid_verified += 1
            elif matched:
                neg_rejected += 1
            if matched:
                patches_matched += 1
            target_cost += p_cost
            patch_rows.append({
                "patch": pspec.filename,
                "expected_status": pspec.expected_status,
                "actual_status": verdict.status,
                "matched": matched,
                "truth_level": verdict.truth_level,
                "repomap_files": repomap_files,
                "runtime_ms": p_ms,
                "cost_usd": p_cost,
                "notes": verdict.notes,
            })

        target_ms = round((time.perf_counter() - t_start) * 1000.0, 2)
        total_runtime_ms += target_ms
        total_cost_usd += target_cost
        targets_report[spec.name] = {
            "passed": all(bool(row["matched"]) for row in patch_rows),
            "repomap_files": repomap_files,
            "runtime_ms": target_ms,
            "cost_usd": round(target_cost, 6),
            "patches": patch_rows,
        }

    all_ok = (
        len(targets_report) == len(POLYGLOT_TARGETS)
        and patches_total > 0
        and patches_matched == patches_total
    )
    return {
        "targets_total": len(POLYGLOT_TARGETS),
        "patches_total": patches_total,
        "patches_matched": patches_matched,
        "valid_patches_total": valid_total,
        "valid_patches_verified": valid_verified,
        "neg_controls_total": neg_total,
        "neg_controls_rejected": neg_rejected,
        "all_passed": all_ok,
        "runtime_ms": round(total_runtime_ms, 2),
        "cost_usd": round(total_cost_usd, 6),
        "targets": targets_report,
    }


def run_foundry_suite(
    suite_root: Path,
    out_dir: Path,
    ablation: AblationConfig | None = None,
) -> dict[str, Any]:
    foundry_src_root = suite_root / "foundry"
    foundry_out_root = out_dir / "foundry"
    foundry_out_root.mkdir(parents=True, exist_ok=True)
    disable_repomap = bool(ablation.disable_repomap) if ablation is not None else False
    disable_autobuild = bool(ablation.disable_autobuild) if ablation is not None else False
    forge_bin = shutil.which("forge")

    targets_report: dict[str, Any] = {}
    static_ready_count = 0
    passed_count = 0
    total_runtime_ms = 0.0

    for spec in FOUNDRY_TARGETS:
        t_start = time.perf_counter()
        src_dir = foundry_src_root / spec.name
        work_repo = foundry_out_root / spec.name
        if not src_dir.is_dir():
            targets_report[spec.name] = {
                "requires_rpc": spec.requires_rpc,
                "execution_status": "missing_target",
                "static_ready": False,
                "passed": False,
                "runtime_ms": 0.0,
            }
            continue

        _copy_isolated(src_dir, work_repo)
        sol_files = 0
        symbol_count = 0
        sinks: list[str] = []
        if not disable_repomap:
            idx = index_repo(work_repo)
            files_map = idx.get("files", {})
            sol_files = sum(1 for rel in files_map if rel.endswith(".sol"))
            symbol_count = sum(len(info.get("symbols", [])) for info in files_map.values())
            sink_set = {
                s
                for info in files_map.values()
                for sym in info.get("symbols", [])
                for s in sym.get("sinks", [])
            }
            sinks = sorted(sink_set)

        build_system = "disabled"
        recipe_ok = True
        if not disable_autobuild:
            recipe = synthesize_build_recipe(work_repo, profile="upstream")
            build_system = recipe.build_system
            script_ok = (work_repo / ".ajar" / "build.sh").is_file()
            recipe_ok = (build_system == "foundry") and (not recipe.static_only) and script_ok

        repomap_ok = disable_repomap or (sol_files > 0 and symbol_count > 0)
        static_ready = repomap_ok and recipe_ok
        if static_ready:
            static_ready_count += 1

        entry: dict[str, Any] = {
            "requires_rpc": spec.requires_rpc,
            "static_ready": static_ready,
            "build_system": build_system,
            "sol_files": sol_files,
            "symbols": symbol_count,
            "sinks": sinks,
        }

        if spec.requires_rpc:
            entry["execution_status"] = "skipped_requires_rpc"
            target_passed = static_ready
        elif forge_bin is None:
            entry["execution_status"] = "skipped_missing_tool"
            entry["missing_tool"] = "forge"
            target_passed = static_ready
        else:
            proc = subprocess.run(
                [forge_bin, "test", "--offline", "-vv"],
                cwd=str(work_repo),
                env=scrub_subprocess_env(),
                capture_output=True,
                text=True,
                timeout=180,
                check=False,
            )
            exec_ok = proc.returncode == 0
            entry["execution_status"] = "passed" if exec_ok else "failed"
            entry["returncode"] = proc.returncode
            target_passed = static_ready and exec_ok

        target_ms = round((time.perf_counter() - t_start) * 1000.0, 2)
        total_runtime_ms += target_ms
        entry["runtime_ms"] = target_ms
        entry["passed"] = target_passed
        if target_passed:
            passed_count += 1
        targets_report[spec.name] = entry

    return {
        "targets_total": len(FOUNDRY_TARGETS),
        "targets_passed": passed_count,
        "static_ready_count": static_ready_count,
        "forge_available": forge_bin is not None,
        "all_passed": passed_count == len(FOUNDRY_TARGETS),
        "runtime_ms": round(total_runtime_ms, 2),
        "targets": targets_report,
    }


def _eval_bola_legacy_route(spec: dict[str, Any], req: dict[str, Any]) -> dict[str, Any]:
    routes = spec.get("routes") or {}
    route_key = str(req.get("route") or "")
    route_cfg = routes.get(route_key) if isinstance(routes, dict) else {}
    trusts_selector = bool(isinstance(route_cfg, dict) and route_cfg.get("trusts_owner_selector"))
    owner_selector = req.get("owner_selector")
    if owner_selector != "victim":
        return {"status": 404, "body_contains_canary": False}
    if trusts_selector:
        return {"status": 200, "body_contains_canary": True}
    return {"status": 403, "body_contains_canary": False}


def _eval_api_bola_state_change(req: dict[str, Any]) -> dict[str, Any]:
    is_foreign = req.get("selector") == "victim"
    status = int(req.get("status", 0))
    status_ok = 200 <= status < 300
    effect = is_foreign and status_ok and bool(req.get("foreign_canary_effect"))
    control_ok = is_foreign and status in (401, 403) and not bool(req.get("foreign_canary_effect"))
    return {"signal": effect, "effect": effect, "control_ok": control_ok}


def _eval_bopla_property_authz(req: dict[str, Any]) -> dict[str, Any]:
    operation = str(req.get("operation") or "")
    if operation == "read":
        effect = bool(req.get("guarded_property_present")) and bool(req.get("exposed_property_canary"))
    else:
        effect = bool(req.get("persisted_guarded_property")) and bool(req.get("effective_property_impact"))
    guard_result = str(req.get("guard_result") or "")
    control_ok = (not effect) and guard_result in ("stripped", "coerced", "rejected", "denied")
    return {"signal": effect, "effect": effect, "control_ok": control_ok}


def _eval_graphql_global_id(req: dict[str, Any]) -> dict[str, Any]:
    signal = bool(req.get("global_id_decoded")) and bool(req.get("resolver_called"))
    effect = signal and bool(req.get("foreign_canary_returned"))
    guard_result = str(req.get("guard_result") or "")
    control_ok = (not effect) and guard_result in ("resolver_denied", "field_filtered")
    return {"signal": signal, "effect": effect, "control_ok": control_ok}


def _eval_jwt_claim_validation(req: dict[str, Any]) -> dict[str, Any]:
    aud_bad = req.get("aud") != req.get("expected_aud")
    alg_bad = req.get("alg") != req.get("expected_alg")
    claim_mismatch = aud_bad or alg_bad
    accepted = bool(req.get("accepted"))
    priv_granted = bool(req.get("privilege_canary_granted"))
    effect = claim_mismatch and accepted and priv_granted
    control_ok = claim_mismatch and (not accepted) and (not priv_granted)
    return {"signal": effect, "effect": effect, "control_ok": control_ok}


def _eval_ssrf_redirect_follow(req: dict[str, Any]) -> dict[str, Any]:
    signal = bool(req.get("server_fetch_attempted"))
    effect = (
        signal
        and bool(req.get("followed_redirect"))
        and bool(req.get("fetch_reached_stand_in_canary"))
    )
    guard_result = str(req.get("guard_result") or "")
    control_ok = (not effect) and guard_result in ("redirect_blocked", "allowlist_denied")
    return {"signal": signal, "effect": effect, "control_ok": control_ok}


def _eval_render_escape(req: dict[str, Any]) -> dict[str, Any]:
    sink_active = str(req.get("sink") or "").lower() == "active"
    output = str(req.get("model_output") or "")
    has_active_markup = bool(_ACTIVE_HTML_RE.search(output))
    triggered = sink_active and has_active_markup and ("CANARY" in output)
    return {"signal": triggered, "leak": triggered}


def _eval_capability_dispatch(req: dict[str, Any]) -> dict[str, Any]:
    granted = {str(item) for item in (req.get("granted") or [])}
    dispatched = str(req.get("dispatched") or "")
    unauthorized = bool(dispatched) and (dispatched not in granted)
    return {"signal": unauthorized, "leak": unauthorized}


def evaluate_hermetic_request(spec: dict[str, Any], req: dict[str, Any]) -> dict[str, Any]:
    oracle = str(spec.get("oracle") or "")
    if not oracle and "routes" in spec:
        return _eval_bola_legacy_route(spec, req)
    if oracle == "api_bola_state_change":
        return _eval_api_bola_state_change(req)
    if oracle == "bopla_property_authz":
        return _eval_bopla_property_authz(req)
    if oracle == "graphql_global_id":
        return _eval_graphql_global_id(req)
    if oracle == "jwt_claim_validation":
        return _eval_jwt_claim_validation(req)
    if oracle == "ssrf_redirect_follow":
        return _eval_ssrf_redirect_follow(req)
    if oracle == "render_escape":
        return _eval_render_escape(req)
    if oracle == "capability_dispatch":
        return _eval_capability_dispatch(req)
    raise ValueError(f"Unsupported hermetic oracle: {oracle or spec.get('target')}")


def _is_hermetic_exploit_hit(actual: dict[str, Any]) -> bool:
    if "effect" in actual:
        return bool(actual["effect"])
    if "leak" in actual:
        return bool(actual["leak"])
    if "body_contains_canary" in actual:
        return bool(actual["body_contains_canary"])
    return bool(actual.get("signal", False))


def run_hermetic_suite(suite_root: Path) -> dict[str, Any]:
    t_start = time.perf_counter()
    targets_dir = suite_root / "hermetic" / "targets"
    spec_paths = sorted(targets_dir.glob("*/target.json")) if targets_dir.is_dir() else []

    targets_report: dict[str, Any] = {}
    targets_passed = 0
    primary_total = 0
    primary_confirmed = 0
    pos_total = 0
    pos_passed = 0
    neg_total = 0
    neg_rejected = 0
    fp_count = 0

    for spec_path in spec_paths:
        target_name = spec_path.parent.name
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        requests_list = spec.get("requests") or []

        t_primary_total = 0
        t_primary_confirmed = 0
        t_pos_total = 0
        t_pos_passed = 0
        t_neg_total = 0
        t_neg_rejected = 0
        t_fp_count = 0
        req_rows: list[dict[str, Any]] = []

        for req in requests_list:
            actual = evaluate_hermetic_request(spec, req)
            expected = dict(req.get("expect") or {})
            matched = actual == expected
            hit = _is_hermetic_exploit_hit(actual)
            kind = str(req.get("kind") or "")

            if kind == "primary":
                t_primary_total += 1
                if matched and hit:
                    t_primary_confirmed += 1
            elif kind == "positive_control":
                t_pos_total += 1
                if matched:
                    t_pos_passed += 1
            elif kind == "negative_control":
                t_neg_total += 1
                if hit:
                    t_fp_count += 1
                elif matched:
                    t_neg_rejected += 1

            req_rows.append({
                "id": str(req.get("id") or ""),
                "kind": kind,
                "actual": actual,
                "expected": expected,
                "matched": matched,
                "exploit_hit": hit,
            })

        target_ok = (
            bool(req_rows)
            and all(bool(r["matched"]) for r in req_rows)
            and t_primary_total > 0
            and t_primary_confirmed == t_primary_total
            and t_pos_passed == t_pos_total
            and t_neg_rejected == t_neg_total
            and t_fp_count == 0
        )
        if target_ok:
            targets_passed += 1

        primary_total += t_primary_total
        primary_confirmed += t_primary_confirmed
        pos_total += t_pos_total
        pos_passed += t_pos_passed
        neg_total += t_neg_total
        neg_rejected += t_neg_rejected
        fp_count += t_fp_count

        targets_report[target_name] = {
            "passed": target_ok,
            "oracle": str(spec.get("oracle") or "bola_legacy_route"),
            "primary_confirmed": t_primary_confirmed,
            "primary_total": t_primary_total,
            "positive_controls_passed": t_pos_passed,
            "positive_controls_total": t_pos_total,
            "negative_controls_rejected": t_neg_rejected,
            "negative_controls_total": t_neg_total,
            "fp_count": t_fp_count,
            "requests": req_rows,
        }

    targets_total = len(spec_paths)
    fp_rate = round(fp_count / max(1, neg_total), 4)
    all_ok = targets_total > 0 and targets_passed == targets_total and fp_count == 0
    return {
        "targets_total": targets_total,
        "targets_passed": targets_passed,
        "primary_total": primary_total,
        "primary_confirmed": primary_confirmed,
        "positive_controls_total": pos_total,
        "positive_controls_passed": pos_passed,
        "negative_controls_total": neg_total,
        "negative_controls_rejected": neg_rejected,
        "fp_count": fp_count,
        "fp_rate": fp_rate,
        "all_passed": all_ok,
        "runtime_ms": round((time.perf_counter() - t_start) * 1000.0, 2),
        "targets": targets_report,
    }


def run_bench(
    suite: Path,
    out_dir: Path,
    ablation: AblationConfig | None = None,
) -> dict[str, Any]:
    suite_root = Path(suite).resolve()
    out_path = Path(out_dir).resolve()
    out_path.mkdir(parents=True, exist_ok=True)

    t_total = time.perf_counter()
    phase0 = run_phase0_probes(out_path / "phase0")
    phase0_ok = all(bool(v.get("passed", False)) for v in phase0.values())
    polyglot = run_polyglot_suite(suite_root, out_path, ablation=ablation)
    foundry = run_foundry_suite(suite_root, out_path, ablation=ablation)
    hermetic = run_hermetic_suite(suite_root)

    total_runtime_ms = round((time.perf_counter() - t_total) * 1000.0, 2)
    suite_targets_total = (
        int(polyglot["targets_total"])
        + int(foundry["targets_total"])
        + int(hermetic["targets_total"])
    )
    scored_total = (
        int(polyglot["patches_total"])
        + int(foundry["targets_total"])
        + int(hermetic["targets_total"])
    )
    scored_passed = (
        int(polyglot["patches_matched"])
        + int(foundry["targets_passed"])
        + int(hermetic["targets_passed"])
    )
    valid_pass_rate = round(
        int(polyglot["valid_patches_verified"]) / max(1, int(polyglot["valid_patches_total"])),
        4,
    )
    neg_reject_rate = round(
        int(polyglot["neg_controls_rejected"]) / max(1, int(polyglot["neg_controls_total"])),
        4,
    )
    all_passed = bool(
        phase0_ok
        and polyglot["all_passed"]
        and foundry["all_passed"]
        and hermetic["all_passed"]
    )

    report_path = out_path / "bench_report.json"
    summary: dict[str, Any] = {
        "suite_targets_total": suite_targets_total,
        "phase0": phase0,
        "phase0_all_passed": phase0_ok,
        "polyglot": polyglot,
        "foundry": foundry,
        "hermetic": hermetic,
        "profile": {
            "accuracy": round(scored_passed / max(1, scored_total), 4),
            "valid_patch_pass_rate": valid_pass_rate,
            "neg_control_rejection_rate": neg_reject_rate,
            "fp_rate": float(hermetic["fp_rate"]),
            "total_runtime_ms": total_runtime_ms,
            "total_cost_usd": float(polyglot["cost_usd"]),
        },
        "ablation": vars(ablation) if ablation is not None else {},
        "report_path": str(report_path),
        "all_passed": all_passed,
    }
    report_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary

