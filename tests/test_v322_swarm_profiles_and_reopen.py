from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys

import pytest

from ajar.db import open_run_db
from ajar.gates import check_all_gates
from ajar.repro_source import (
    resolve_local_build_cache_dir,
    validate_entrypoint_fidelity,
    validate_no_static_source_cheat,
)
from ajar.swarm import (
    WIRE_PROFILE_LADDER,
    reopen_run,
    sync_run_to_shared_mirror,
)


def _run_ajar(
    args: list[str],
    *,
    ajar_home: pathlib.Path,
    run_id: str | None = None,
    shared_mirror: pathlib.Path | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["AJAR_HOME"] = str(ajar_home)
    env["AJAR_SHARED_MIRROR_DIR"] = str(shared_mirror) if shared_mirror is not None else "off"
    if run_id:
        env["AJAR_RUN_ID"] = run_id
    return subprocess.run(
        [sys.executable, "-m", "ajar.cli", *args],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def _init_c_repo(repo_dir: pathlib.Path) -> None:
    (repo_dir / "src").mkdir(parents=True, exist_ok=True)
    (repo_dir / "src" / "helper.c").write_text(
        "int helper_scale(int x) {\n    return x * 2;\n}\n",
        encoding="utf-8",
    )
    (repo_dir / "src" / "parser.c").write_text(
        "#include <stdio.h>\n"
        "#include <stdlib.h>\n"
        "#include <string.h>\n"
        "int helper_scale(int x);\n"
        "int parse_packet(const char *s) {\n"
        "    if (strncmp(s, \"TRIGGER\", 7) == 0) {\n"
        "        fprintf(stderr, \"BOUNDARY_VIOLATION\\n\");\n"
        "        return 42;\n"
        "    }\n"
        "    return helper_scale(1) - 2;\n"
        "}\n",
        encoding="utf-8",
    )
    (repo_dir / "src" / "main.c").write_text(
        "#include <stdio.h>\n"
        "int parse_packet(const char *s);\n"
        "int main(int argc, char **argv) {\n"
        "    const char *arg = (argc > 1) ? argv[1] : \"OK\";\n"
        "    return parse_packet(arg);\n"
        "}\n",
        encoding="utf-8",
    )
    (repo_dir / "Makefile").write_text(
        "CC ?= cc\n"
        "CFLAGS ?= -O1 -Wall\n"
        "OBJS = src/helper.o src/parser.o src/main.o\n\n"
        "cli_app: $(OBJS)\n"
        "\t$(CC) $(CFLAGS) -o cli_app $(OBJS)\n\n"
        "%.o: %.c\n"
        "\t$(CC) $(CFLAGS) -c $< -o $@\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "init", "-q"], cwd=str(repo_dir), check=True)
    subprocess.run(["git", "config", "user.email", "test@ajar.local"], cwd=str(repo_dir), check=True)
    subprocess.run(["git", "config", "user.name", "Ajar Test"], cwd=str(repo_dir), check=True)
    subprocess.run(["git", "add", "."], cwd=str(repo_dir), check=True)
    subprocess.run(["git", "commit", "-q", "-m", "initial c target"], cwd=str(repo_dir), check=True)


def test_swarm_packet_direct_default_and_fallback_ladder_batch_splitting(tmp_path: pathlib.Path) -> None:
    assert "qa_persona" not in WIRE_PROFILE_LADDER
    assert WIRE_PROFILE_LADDER == ("direct", "swarm_patch_first", "regression_tdd")

    repo = tmp_path / "target_repo"
    _init_c_repo(repo)
    home = tmp_path / "ajar_home"

    r_init = _run_ajar(
        ["init", str(repo), "--run-id", "swarm-ladder-run", "--goal", "Verify C parser boundaries", "--uncapped", "--json"],
        ajar_home=home,
    )
    assert r_init.returncode == 0, r_init.stderr

    r_surf = _run_ajar(
        [
            "surface",
            "add",
            "--name",
            "cli_entry",
            "--kind",
            "cli",
            "--locus",
            "src/main.c:3",
            "--priority",
            "high",
        ],
        ajar_home=home,
        run_id="swarm-ladder-run",
    )
    assert r_surf.returncode == 0, r_surf.stderr
    surf_id = json.loads(r_surf.stdout)["surface_id"]

    claim_ids: list[str] = []
    for idx in range(1, 5):
        rp = _run_ajar(
            [
                "claim",
                "propose",
                "--worker",
                "w-disc-1",
                "--surface",
                surf_id,
                "--title",
                f"Parser boundary defect #{idx}",
                "--locus",
                f"src/parser.c:{5 + idx}",
                "--mechanism",
                f"parse_packet skips length guard at branch {idx}, returning non-zero corrupted state",
                "--severity",
                "high",
                "--falsification-prediction",
                "main.c rejects inputs longer than 6 bytes before calling parse_packet",
                "--falsification-test",
                "inspect main.c argv length check",
            ],
            ajar_home=home,
            run_id="swarm-ladder-run",
        )
        assert rp.returncode == 0, rp.stderr
        cid = json.loads(rp.stdout)["claim_id"]
        claim_ids.append(cid)

        rs = _run_ajar(
            [
                "claim",
                "survive",
                cid,
                "--worker",
                "w-fals-1",
                "--notes",
                "main.c forwards argv[1] unchecked into parse_packet.",
            ],
            ajar_home=home,
            run_id="swarm-ladder-run",
        )
        assert rs.returncode == 0, rs.stderr

    # 1. Default `ajar swarm packet` uses `direct` ("Swarm Reproducer"), <= 45 lines, batch of 4.
    r_pkt = _run_ajar(
        ["swarm", "packet", "--stage", "reproduce", "--limit", "4", "--worker", "w-repro-1", "--json"],
        ajar_home=home,
        run_id="swarm-ladder-run",
    )
    assert r_pkt.returncode == 0, r_pkt.stderr
    pkt = json.loads(r_pkt.stdout)
    assert pkt["wire_profile"] == "direct"
    assert pkt["item_ids"] == claim_ids
    assert pkt["line_count"] <= 45
    assert "Swarm Reproducer" in pkt["packet_markdown"]
    assert "src/parser.c:" in pkt["packet_markdown"]

    # 2. First fallback steps down `direct -> swarm_patch_first` and splits [4] -> [2, 2].
    r_fb1 = _run_ajar(
        ["swarm", "fallback", pkt["dispatch_id"], "--reason", "filter_blocked"],
        ajar_home=home,
        run_id="swarm-ladder-run",
    )
    assert r_fb1.returncode == 0, r_fb1.stderr
    fb1 = json.loads(r_fb1.stdout)
    assert fb1["previous_profile"] == "direct"
    assert fb1["next_profile"] == "swarm_patch_first"
    assert len(fb1["recovery_packets"]) == 2
    assert len(fb1["recovery_packets"][0]["item_ids"]) == 2
    assert len(fb1["recovery_packets"][1]["item_ids"]) == 2

    # 3. Second fallback on first half steps down `swarm_patch_first -> regression_tdd` and splits [2] -> [1, 1].
    first_half_id = fb1["recovery_packets"][0]["dispatch_id"]
    r_fb2 = _run_ajar(
        ["swarm", "fallback", first_half_id, "--reason", "idle_no_return"],
        ajar_home=home,
        run_id="swarm-ladder-run",
    )
    assert r_fb2.returncode == 0, r_fb2.stderr
    fb2 = json.loads(r_fb2.stdout)
    assert fb2["previous_profile"] == "swarm_patch_first"
    assert fb2["next_profile"] == "regression_tdd"
    assert len(fb2["recovery_packets"]) == 2
    assert len(fb2["recovery_packets"][0]["item_ids"]) == 1
    assert len(fb2["recovery_packets"][1]["item_ids"]) == 1

    # 4. Mark a recovery dispatch completed and query status.
    leaf_id = fb2["recovery_packets"][0]["dispatch_id"]
    r_done = _run_ajar(
        ["swarm", "complete", leaf_id, "--notes", "4-arm verified"],
        ajar_home=home,
        run_id="swarm-ladder-run",
    )
    assert r_done.returncode == 0, r_done.stderr
    r_st = _run_ajar(["swarm", "status"], ajar_home=home, run_id="swarm-ladder-run")
    assert r_st.returncode == 0, r_st.stderr
    dispatches = json.loads(r_st.stdout)["swarm_dispatches"]
    assert any(d["dispatch_id"] == leaf_id and d["status"] == "completed" for d in dispatches)


def test_structural_claim_prose_and_policy_block_gates(tmp_path: pathlib.Path) -> None:
    repo = tmp_path / "target_repo"
    _init_c_repo(repo)
    home = tmp_path / "ajar_home"

    _run_ajar(
        ["init", str(repo), "--run-id", "prose-gate-run", "--goal", "Audit parser invariants", "--uncapped", "--json"],
        ajar_home=home,
    )
    r_surf = _run_ajar(
        ["surface", "add", "--name", "cli_entry", "--kind", "cli", "--locus", "src/main.c:3", "--priority", "high"],
        ajar_home=home,
        run_id="prose-gate-run",
    )
    assert r_surf.returncode == 0, r_surf.stderr
    surf_id = json.loads(r_surf.stdout)["surface_id"]

    # Weaponized `.git/hooks/post-checkout` / `#!/bin/sh` prose is rejected at `claim propose`.
    r_bad = _run_ajar(
        [
            "claim",
            "propose",
            "--worker",
            "w-disc-1",
            "--surface",
            surf_id,
            "--title",
            "Symlink write bypass",
            "--locus",
            "src/parser.c:6",
            "--mechanism",
            "Writes #!/bin/sh payload into .git/hooks/post-checkout for code execution",
            "--severity",
            "critical",
            "--falsification-prediction",
            "Path validator rejects .git symlink targets before write",
            "--falsification-test",
            "inspect path check",
        ],
        ajar_home=home,
        run_id="prose-gate-run",
    )
    assert r_bad.returncode != 0
    assert "structural_prose_gate" in (r_bad.stdout + r_bad.stderr)

    # Clean structural C prose succeeds.
    r_ok = _run_ajar(
        [
            "claim",
            "propose",
            "--worker",
            "w-disc-1",
            "--surface",
            surf_id,
            "--title",
            "prepare_symlink_changes old_mode == 0 registration skip",
            "--locus",
            "src/parser.c:6",
            "--mechanism",
            "prepare_symlink_changes skips SYMLINK_IN_RESULT when patch->old_mode == 0, permitting writes through a renamed intra-repo symlink",
            "--severity",
            "critical",
            "--falsification-prediction",
            "check_symcache rejects renamed symlink directories even when old_mode is omitted",
            "--falsification-test",
            "inspect apply.c symlink_changes lookup",
        ],
        ajar_home=home,
        run_id="prose-gate-run",
    )
    assert r_ok.returncode == 0, r_ok.stderr
    cid = json.loads(r_ok.stdout)["claim_id"]

    _run_ajar(
        ["claim", "survive", cid, "--worker", "w-fals-1", "--notes", "Confirmed old_mode == 0 skips registration."],
        ajar_home=home,
        run_id="prose-gate-run",
    )

    # Voluntary safety-policy refusal block is deterministically rejected.
    r_pol_blk = _run_ajar(
        [
            "claim",
            "block",
            cid,
            "--worker",
            "w-repro-1",
            "--env-blocker",
            "missing_hardware",
            "--reason",
            "Dynamic exploit/crash PoC execution intentionally withheld per defensive safety policy.",
        ],
        ajar_home=home,
        run_id="prose-gate-run",
    )
    assert r_pol_blk.returncode != 0
    assert "policy_refusal_block_rejected" in (r_pol_blk.stdout + r_pol_blk.stderr)

    # Zero-attempt `external_service` block on source target is rejected without a repro/instrument attempt.
    r_zero_blk = _run_ajar(
        [
            "claim",
            "block",
            cid,
            "--worker",
            "w-repro-1",
            "--env-blocker",
            "external_service",
            "--reason",
            "Requires upstream OAuth production tenant endpoint not reachable offline.",
        ],
        ajar_home=home,
        run_id="prose-gate-run",
    )
    assert r_zero_blk.returncode != 0
    assert "zero_attempt_block_rejected" in (r_zero_blk.stdout + r_zero_blk.stderr)

    # Also verify SQL gate G4 catches legacy DB rows with policy-refusal blocker_reason.
    conn = open_run_db("prose-gate-run", ajar_home=home)
    try:
        conn.execute(
            "UPDATE claims SET status = 'blocked', blocker_reason = 'PoC intentionally withheld per safety policy', env_blocker = '' WHERE claim_id = ?",
            (cid,),
        )
        gates = check_all_gates(conn)
        assert gates["gates"]["G4_zero_skill_and_dry_rigor"]["passed"] is False
        assert any(
            "policy" in b.lower() or "env-blocker" in b.lower()
            for b in gates["gates"]["G4_zero_skill_and_dry_rigor"]["issues"]
        )
    finally:
        conn.close()


def test_entrypoint_fidelity_anti_cheat_and_warm_object_cache(tmp_path: pathlib.Path) -> None:
    # 1. Local SSD build cache path check
    cache_dir = resolve_local_build_cache_dir("unit-cache-check", "slot-0")
    assert str(cache_dir).startswith("/tmp/")
    assert "unit-cache-check" in str(cache_dir)

    # 2. Direct unit checks on entrypoint fidelity & anti-static-source-cheat
    ok_cli, msg_cli = validate_entrypoint_fidelity("cc stub.c src/parser.o -o poc && ./poc", surface_kind="cli")
    assert not ok_cli and "entrypoint_fidelity_violation" in msg_cli
    ok_lib, _ = validate_entrypoint_fidelity("cc stub.c src/parser.o -o poc && ./poc", surface_kind="library_api")
    assert ok_lib

    ok_ph, msg_ph = validate_no_static_source_cheat(
        "./cli_app <conceptual_placeholder>",
        ["src/parser.c"],
    )
    assert not ok_ph and "placeholder" in msg_ph.lower()

    ok_grep, msg_grep = validate_no_static_source_cheat(
        "grep -q 'TRIGGER' src/parser.c",
        ["src/parser.c"],
    )
    assert not ok_grep and "static_source_cheat" in msg_grep

    ext_script = tmp_path / "cheat_check.py"
    ext_script.write_text(
        "import pathlib, sys\n"
        "txt = pathlib.Path('src/parser.c').read_text()\n"
        "sys.exit(1 if 'TRIGGER' in txt else 0)\n",
        encoding="utf-8",
    )
    ok_ext, msg_ext = validate_no_static_source_cheat(
        f"python3 {ext_script}",
        ["src/parser.c"],
        target_dir=tmp_path / "nonexistent_target",
    )
    assert not ok_ext and "static_source_cheat" in msg_ext

    # 3. Full 4-arm reproduction on C repo: rejects `<conceptual_placeholder>`, then passes real `./cli_app` while preserving `src/helper.o`!
    repo = tmp_path / "c_repo"
    _init_c_repo(repo)
    home = tmp_path / "ajar_home"

    _run_ajar(
        ["init", str(repo), "--in-place", "--run-id", "c-repro-run", "--goal", "Verify C CLI reproduction", "--uncapped", "--json"],
        ajar_home=home,
    )
    r_surf = _run_ajar(
        ["surface", "add", "--name", "cli_main", "--kind", "cli", "--locus", "src/main.c:3", "--priority", "high"],
        ajar_home=home,
        run_id="c-repro-run",
    )
    assert r_surf.returncode == 0, r_surf.stderr
    surf_id = json.loads(r_surf.stdout)["surface_id"]

    rp = _run_ajar(
        [
            "claim",
            "propose",
            "--worker",
            "w-disc-1",
            "--surface",
            surf_id,
            "--title",
            "TRIGGER prefix boundary violation in parse_packet",
            "--locus",
            "src/parser.c:6",
            "--mechanism",
            "parse_packet returns exit code 42 on TRIGGER prefix without rejecting malformed frame",
            "--severity",
            "high",
            "--falsification-prediction",
            "main.c filters TRIGGER prefix before calling parse_packet",
            "--falsification-test",
            "inspect main.c",
        ],
        ajar_home=home,
        run_id="c-repro-run",
    )
    assert rp.returncode == 0, rp.stderr
    cid = json.loads(rp.stdout)["claim_id"]
    _run_ajar(
        ["claim", "survive", cid, "--worker", "w-fals-1", "--notes", "Confirmed reachable from main.c."],
        ajar_home=home,
        run_id="c-repro-run",
    )

    patch_file = tmp_path / "fix_parser.diff"
    patch_file.write_text(
        "--- a/src/parser.c\n"
        "+++ b/src/parser.c\n"
        "@@ -4,6 +4,6 @@\n"
        " int helper_scale(int x);\n"
        " int parse_packet(const char *s) {\n"
        "-    if (strncmp(s, \"TRIGGER\", 7) == 0) {\n"
        "+    if (0 && strncmp(s, \"TRIGGER\", 7) == 0) {\n"
        "         fprintf(stderr, \"BOUNDARY_VIOLATION\\n\");\n"
        "         return 42;\n"
        "     }\n",
        encoding="utf-8",
    )

    # Attempt 1: cheating with `<conceptual_placeholder>` fails immediately without confirming finding.
    r_cheat = _run_ajar(
        [
            "claim",
            "reproduce",
            cid,
            "--worker",
            "w-repro-1",
            "--mode",
            "source",
            "--poc-cmd",
            "make -s cli_app && ./cli_app <conceptual_placeholder>",
            "--control-cmd",
            "make -s cli_app && ./cli_app OK",
            "--micropatch",
            str(patch_file),
        ],
        ajar_home=home,
        run_id="c-repro-run",
    )
    assert r_cheat.returncode != 0

    # Attempt 2: real compiled binary `./cli_app` passes all 4 arms AND keeps `src/helper.o` warm!
    r_pass = _run_ajar(
        [
            "claim",
            "reproduce",
            cid,
            "--worker",
            "w-repro-1",
            "--mode",
            "source",
            "--poc-cmd",
            "make -s cli_app && ./cli_app TRIGGER",
            "--control-cmd",
            "make -s cli_app && ./cli_app OK",
            "--micropatch",
            str(patch_file),
        ],
        ajar_home=home,
        run_id="c-repro-run",
    )
    assert r_pass.returncode == 0, r_pass.stdout + "\n" + r_pass.stderr
    res_json = json.loads(r_pass.stdout)
    assert res_json["finding_id"].startswith("fnd-")
    assert res_json["reproduction"]["passed"] is True
    slot_helper_obj = home / "runs" / "c-repro-run" / "repro" / "slot-0" / "src" / "helper.o"
    assert slot_helper_obj.is_file(), "Warm untouched object file src/helper.o should be preserved across 4-arm resets"


def test_shared_mirror_sync_and_cross_vm_reopen_reconstructs_missing_target(tmp_path: pathlib.Path) -> None:
    orig_target = tmp_path / "vm1_targets" / "demo_c"
    _init_c_repo(orig_target)
    home_vm1 = tmp_path / "home_vm1"
    shared_mirror = tmp_path / "shared_mirror"

    r_init = _run_ajar(
        ["init", str(orig_target), "--in-place", "--run-id", "cross-vm-run", "--goal", "Cross-VM reopen verification", "--uncapped", "--json"],
        ajar_home=home_vm1,
        shared_mirror=shared_mirror,
    )
    assert r_init.returncode == 0, r_init.stderr

    r_surf = _run_ajar(
        ["surface", "add", "--name", "cli_main", "--kind", "cli", "--locus", "src/main.c:3", "--priority", "high"],
        ajar_home=home_vm1,
        run_id="cross-vm-run",
        shared_mirror=shared_mirror,
    )
    assert r_surf.returncode == 0, r_surf.stderr
    surf_id = json.loads(r_surf.stdout)["surface_id"]

    # Insert a legacy finished state + zero-attempt policy-blocked claim + `.git/hooks/post-checkout` tail in VM1 DB, then sync mirror.
    conn1 = open_run_db("cross-vm-run", ajar_home=home_vm1)
    try:
        conn1.execute(
            """
            INSERT INTO claims(
                claim_id, surface_id, proposer_worker_id, falsifier_worker_id, seeded_by_human,
                title, subsystem, locus, mechanism, mechanism_key, severity,
                falsification_prediction, falsification_test, status,
                blocker_reason, failed_repro_count, instrumented_since_fail, created_at, updated_at
            ) VALUES (
                'clm-legacy01', ?, 'w-disc-1', 'w-fals-1', 0,
                'Symlink directory registration skip', 'src', 'src/parser.c:6',
                'prepare_symlink_changes skips SYMLINK_IN_RESULT when old_mode == 0. Attacker writes #!/bin/sh into .git/hooks/post-checkout.',
                'symlink_skip', 'critical',
                'check_symcache blocks write', 'inspect parser.c', 'blocked',
                'Dynamic exploit/crash PoC execution intentionally withheld per defensive safety policy.',
                0, 0, '2026-11-19T00:00:00Z', '2026-11-19T00:00:00Z'
            )
            """,
            (surf_id,),
        )
        conn1.execute("UPDATE runs SET status = 'finished', stop_reason = 'sealed' WHERE run_id = 'cross-vm-run'")
    finally:
        conn1.close()

    vm1_rdir = home_vm1 / "runs" / "cross-vm-run"
    if not (vm1_rdir / "repro" / "repo.git" / "HEAD").is_file():
        (vm1_rdir / "repro").mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", "--bare", "-q", str(orig_target), str(vm1_rdir / "repro" / "repo.git")], check=True)

    mirror_info = sync_run_to_shared_mirror("cross-vm-run", ajar_home=home_vm1, shared_root=shared_mirror)
    assert mirror_info is not None
    assert (shared_mirror / "cross-vm-run" / "run.db").is_file()
    assert (shared_mirror / "cross-vm-run" / "repro" / "repo.git" / "HEAD").is_file()

    # Simulate switching to a brand-new ephemeral VM: wipe BOTH `home_vm1` AND `orig_target`!
    for root, dirs, files in os.walk(home_vm1):
        os.chmod(root, 0o700)
        for d in dirs:
            os.chmod(os.path.join(root, d), 0o700)
        for f in files:
            os.chmod(os.path.join(root, f), 0o600)
    shutil.rmtree(home_vm1)
    shutil.rmtree(orig_target)
    assert not orig_target.exists()

    home_vm2 = tmp_path / "home_vm2"
    r_reopen = _run_ajar(
        ["reopen", "cross-vm-run", "--from-shared", str(shared_mirror), "--json"],
        ajar_home=home_vm2,
        shared_mirror=shared_mirror,
    )
    assert r_reopen.returncode == 0, r_reopen.stdout + "\n" + r_reopen.stderr
    reopened = json.loads(r_reopen.stdout)
    assert reopened["hydrated_from_shared_mirror"] is True
    assert reopened["target_reconstructed"] is True
    assert pathlib.Path(reopened["target_path"]).joinpath("src", "parser.c").is_file()
    assert reopened["unblocked_claim_ids"] == ["clm-legacy01"]
    assert reopened["scrubbed_claim_ids"] == ["clm-legacy01"]
    assert reopened["ready_reproduce_claims"] == ["clm-legacy01"]

    conn2 = open_run_db("cross-vm-run", ajar_home=home_vm2)
    try:
        clm_row = conn2.execute("SELECT status, mechanism, blocker_reason FROM claims WHERE claim_id = 'clm-legacy01'").fetchone()
        assert clm_row["status"] == "survived_falsify"
        assert clm_row["blocker_reason"] == ""
        assert ".git/hooks/post-checkout" not in clm_row["mechanism"]
        assert "SYMLINK_IN_RESULT" in clm_row["mechanism"]
    finally:
        conn2.close()


@pytest.mark.skipif(
    not pathlib.Path("/shared/user/.gemini/ajar/runs/git-wave1a/run.db").is_file(),
    reason="Real git-wave1a shared ledger not mounted in this test environment",
)
def test_real_git_wave1a_shared_ledger_reopen_dry_copy(tmp_path: pathlib.Path) -> None:
    """Read-only copy check against `/shared/user/.gemini/ajar/runs/git-wave1a` proving all 10 claims unblock cleanly."""
    real_src = pathlib.Path("/shared/user/.gemini/ajar/runs/git-wave1a")
    sandbox_shared = tmp_path / "shared_runs"
    sandbox_git_dir = sandbox_shared / "git-wave1a"
    sandbox_git_dir.mkdir(parents=True, exist_ok=True)

    # Copy ONLY compact `run.db` + `brief.md` (read-only from `/shared`, zero writes to `/shared`).
    shutil.copy2(real_src / "run.db", sandbox_git_dir / "run.db")
    if (real_src / "brief.md").is_file():
        shutil.copy2(real_src / "brief.md", sandbox_git_dir / "brief.md")

    sandbox_home = tmp_path / "fresh_vm_home"
    info = reopen_run("git-wave1a", shared_root=sandbox_shared, ajar_home=sandbox_home)
    assert info["hydrated_from_shared_mirror"] is True
    assert len(info["unblocked_claim_ids"]) == 10
    assert len(info["ready_reproduce_claims"]) == 10

    r_pkt = _run_ajar(
        ["swarm", "packet", "--stage", "reproduce", "--limit", "3", "--worker", "w-repro-1", "--json"],
        ajar_home=sandbox_home,
        run_id="git-wave1a",
    )
    assert r_pkt.returncode == 0, r_pkt.stderr
    pkt = json.loads(r_pkt.stdout)
    assert pkt["wire_profile"] == "direct"
    assert len(pkt["item_ids"]) == 3
    assert pkt["line_count"] <= 45


def test_scrubbed_env_preserves_rustup_without_leaking_cargo_credentials(tmp_path: pathlib.Path) -> None:
    """Ensure isolated reproduction `HOME` resolves `rustup` toolchains and offline `.cargo/registry` without `credentials.toml`."""
    from ajar.redact import scrubbed_subprocess_env

    fake_home = tmp_path / "runner_home"
    (fake_home / ".rustup" / "toolchains" / "stable-x86_64-unknown-linux-gnu").mkdir(parents=True)
    (fake_home / ".cargo" / "registry").mkdir(parents=True)
    (fake_home / ".cargo" / "credentials.toml").write_text('[registry]\ntoken = "secret"\n', encoding="utf-8")

    iso_tmp = tmp_path / "slot_tmp"
    iso_tmp.mkdir()
    env = scrubbed_subprocess_env(base_env={"HOME": str(fake_home), "PATH": "/usr/bin:/bin"}, tmp_dir=iso_tmp)

    assert env["HOME"] == str(iso_tmp.resolve())
    assert env["RUSTUP_HOME"] == str(fake_home / ".rustup")
    assert env["RUSTUP_TOOLCHAIN"] == "stable-x86_64-unknown-linux-gnu"
    assert (iso_tmp / ".cargo" / "registry").is_symlink()
    assert not (iso_tmp / ".cargo" / "credentials.toml").exists()

