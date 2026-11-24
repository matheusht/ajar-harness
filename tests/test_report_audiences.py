"""Tests for audience-scoped report rendering, path sanitization, and calibration truth."""

from __future__ import annotations

import io
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from ajar import EXIT_OK, EXIT_USER_ERROR
from ajar.cli import main as cli_main
from ajar.db import immediate_tx, open_run_db
from ajar.workspace import unlock_run_dir_permissions


def _run_cli(argv: list[str], ajar_home: pathlib.Path) -> tuple[int, str, str]:
    out = io.StringIO()
    err = io.StringIO()
    with (
        patch.dict(os.environ, {"AJAR_HOME": str(ajar_home)}, clear=False),
        redirect_stdout(out),
        redirect_stderr(err),
    ):
        rc = cli_main(argv)
    return rc, out.getvalue(), err.getvalue()


def _create_synthetic_repo(root: pathlib.Path) -> pathlib.Path:
    repo = root / "acme-http"
    (repo / "src").mkdir(parents=True, exist_ok=True)
    (repo / "src" / "acme_parser.c").write_text(
        "#include <limits.h>\n"
        "#include <stddef.h>\n"
        "int parse_chunk_length(int raw_len, int max_frame) {\n"
        "    if (raw_len > max_frame) return -1;\n"
        "    return raw_len;\n"
        "}\n",
        encoding="utf-8",
    )
    (repo / "src" / "http_router.py").write_text(
        "def dispatch_route(role: str) -> bool:\n"
        "    return role.startswith('admin')\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "ci@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "CI"], cwd=repo, check=True)
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "Initial synthetic acme-http fixture"], cwd=repo, check=True)
    return repo


class TestReportAudiences(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.base = pathlib.Path(self._tmp.name)
        self.ajar_home = self.base / "ajar-home"
        self.ajar_home.mkdir(parents=True, exist_ok=True)
        self.repo = _create_synthetic_repo(self.base)

    def tearDown(self) -> None:
        runs_dir = self.ajar_home / "runs"
        if runs_dir.is_dir():
            for child in runs_dir.iterdir():
                unlock_run_dir_permissions(child)
        self._tmp.cleanup()

    def _seed_contaminated_run(self, run_id: str = "run-report-aud") -> None:
        rc, _, err = _run_cli(["init", str(self.repo), "--run-id", run_id, "--uncapped", "--json"], self.ajar_home)
        self.assertEqual(rc, EXIT_OK, err)

        fake_macos_user = "/" + "Users/" + "alice"
        fake_linux_user = "/" + "home/" + "builder"
        leaked_artifact_script = (
            f"{fake_macos_user}/.ajar/runs/{run_id}/artifacts/worker-w-repro-7/repro_chunk_wrap.sh"
        )
        leaked_slot_file = (
            f"{fake_linux_user}/.ajar/runs/{run_id}/repro/slot-0/src/acme_parser.c:4"
        )
        leaked_ctrl_cmd = f"python3 {self.repo}/src/http_router.py --valid"
        raw_diff = (
            f"--- {self.repo}/src/acme_parser.c\n"
            f"+++ {self.repo}/src/acme_parser.c\n"
            "@@ -2,4 +2,4 @@\n"
            " int parse_chunk_length(int raw_len, int max_frame) {\n"
            "-    if (raw_len > max_frame) return -1;\n"
            "+    if (raw_len < 0 || raw_len > max_frame) return -1;\n"
            "     return raw_len;\n"
        )
        verified_fix_diff = (
            "--- a/src/acme_parser.c\n"
            "+++ b/src/acme_parser.c\n"
            "@@ -2,5 +2,6 @@\n"
            " int parse_chunk_length(int raw_len, int max_frame) {\n"
            "+    if (raw_len < 0) return -1;\n"
            "     if (raw_len > max_frame) return -1;\n"
            "     return raw_len;\n"
            " }\n"
        )

        conn = open_run_db(run_id, ajar_home=self.ajar_home)
        try:
            with immediate_tx(conn):
                conn.execute(
                    """
                    INSERT INTO surfaces(surface_id, name, kind, subsystem, locus, priority, trust_boundary, created_at)
                    VALUES ('surf-http1', 'chunk-decoder', 'network_parser', 'src', 'src/acme_parser.c:3', 'high', 'untrusted HTTP client framing', '2026-11-21T10:00:00Z')
                    """
                )
                conn.execute(
                    """
                    INSERT INTO steers(steer_id, scope, target_filter, rule_text, author, touch_kind, active, created_at)
                    VALUES ('str-internal1', 'global', '', 'Internal swarm prompt hygiene rule: skip slow fuzz loops.', 'operator', 'scope_authority', 1, '2026-11-21T10:01:00Z')
                    """
                )
                conn.execute(
                    """
                    INSERT INTO tasks(task_id, surface_id, kind, direction, skill_mode, subsystem, title, locus, priority, salience_score, status, dry_control_locus, dry_control_reason, created_at, updated_at)
                    VALUES ('tsk-dry1', 'surf-http1', 'investigate', 'outside_in', 'zero_skill', 'src', 'Check router guard', ?, 'medium', 50.0, 'dry', ?, 'Exact token equality check in upstream middleware blocks unauthenticated callers.', '2026-11-21T10:02:00Z', '2026-11-21T10:05:00Z')
                    """,
                    (f"{self.repo}/src/http_router.py:2", f"{self.repo}/src/http_router.py:2"),
                )
                conn.execute(
                    """
                    INSERT INTO claims(
                        claim_id, surface_id, proposer_worker_id, falsifier_worker_id, title, subsystem, locus,
                        mechanism, mechanism_key, severity, falsification_prediction, falsification_test,
                        status, research_state, evidence_state, remediation_state, created_at, updated_at
                    ) VALUES (
                        'clm-88aa11bb', 'surf-http1', 'w-hunt-1', 'w-falsifier-2',
                        'STALE UNCALIBRATED CRITICAL RCE TITLE', 'src', ?,
                        'STALE UNCALIBRATED PROSE claiming single-packet RCE via fnd-99cc00dd and 4-arm primitive sink.',
                        'parse_chunk_length:neg', 'critical',
                        'Rejecting negative raw_len values in parse_chunk_length prevents negative length bypass.',
                        'cc src/acme_parser.c', 'reproduced', 'confirmed', 'reproduced', 'maintainer_patched',
                        '2026-11-21T10:10:00Z', '2026-11-21T10:15:00Z'
                    )
                    """,
                    (leaked_slot_file,),
                )
                conn.execute(
                    """
                    INSERT INTO findings(
                        finding_id, claim_id, title, severity, locus, root_cause, poc_cmd, control_cmd,
                        build_cmd, micropatch_path, micropatch_diff,
                        arm1_clean_poc_json, arm2_clean_ctrl_json, arm3_patch_poc_json, arm4_patch_ctrl_json,
                        ub_divergence_class, realism_tier, attribution, created_at
                    ) VALUES (
                        'fnd-99cc00dd', 'clm-88aa11bb',
                        'STALE UNCALIBRATED CRITICAL RCE TITLE (fnd-99cc00dd)',
                        'critical', ?,
                        'STALE UNCALIBRATED PROSE claiming single-packet RCE.',
                        ?, ?,
                        'cc -O1 -fsanitize=address,undefined src/acme_parser.c -o acme_parser',
                        ?, ?,
                        '{"exit_code": 1, "arm_passed": true}',
                        '{"exit_code": 0, "arm_passed": true}',
                        '{"exit_code": 0, "arm_passed": true}',
                        '{"exit_code": 0, "arm_passed": true}',
                        'confirmed_release_impact', 'stepping_stone', 'found_autonomously_by_ajar',
                        '2026-11-21T10:20:00Z'
                    )
                    """,
                    (
                        leaked_slot_file,
                        f"sh {leaked_artifact_script}",
                        leaked_ctrl_cmd,
                        f"{fake_macos_user}/.ajar/runs/{run_id}/artifacts/micro.diff",
                        raw_diff,
                    ),
                )
                # Insert post-hoc finding_corrections record calibrating severity, title, locus, and root_cause prose
                correction_payload = {
                    "severity": "medium",
                    "title": "Negative chunk length bypasses upper-bound check in parse_chunk_length",
                    "locus": f"{self.repo}/src/acme_parser.c:4",
                    "root_cause": (
                        "Furthermore, `parse_chunk_length()` in `src/acme_parser.c:4` utilizes a signed `int`\n"
                        "comparison against `max_frame` (`clm-88aa11bb`) — allowing negative `raw_len` values from\n"
                        "the 4-arm stepping stone primitive sink to pass validation, causing bounded out-of-bounds "
                        "reads when callers forward the signed length into downstream buffer slices."
                    ),
                }
                conn.execute(
                    """
                    INSERT INTO finding_corrections(correction_id, finding_id, claim_id, payload_json, reason, actor, created_at)
                    VALUES (
                        'cor-77ee22ff', 'fnd-99cc00dd', 'clm-88aa11bb', ?,
                        'Requires chunked transfer framing enabled on HTTP/1.1 listeners; HTTP/2 framing rejects negative lengths upstream.',
                        'operator', '2026-11-21T14:00:00Z'
                    )
                    """,
                    (json.dumps(correction_payload),),
                )
                conn.execute(
                    """
                    INSERT INTO patch_verifications(
                        verification_id, finding_id, claim_id, patch_path, patch_diff, suite_cmd,
                        variant_cmds_json, caller_audit, sibling_audit, arms_json, passed, created_at
                    ) VALUES (
                        'pvf-11223344', 'fnd-99cc00dd', 'clm-88aa11bb',
                        ?, ?, 'pytest -q',
                        '["./acme_parser -1", "./acme_parser -4096", "./acme_parser -2147483648"]',
                        'All callers in connection loop treat -1 return values from parse_chunk_length as framing errors.',
                        'Checked header length parser in src/http_router.py and confirmed unsigned parsing.',
                        '{"arm1": {"arm_passed": true}}', 1, '2026-11-21T15:00:00Z'
                    )
                    """,
                    (f"{fake_macos_user}/patches/0001-fix.patch", verified_fix_diff),
                )
        finally:
            conn.close()

    def test_maintainer_audience_strips_jargon_paths_and_stale_prose(self) -> None:
        import importlib.util

        lint_spec = importlib.util.spec_from_file_location(
            "report_voice_lint_maint",
            pathlib.Path(__file__).resolve().parents[1] / "skills" / "security-advisory-report" / "scripts" / "report_voice_lint.py",
        )
        assert lint_spec is not None and lint_spec.loader is not None
        voice_lint = importlib.util.module_from_spec(lint_spec)
        sys.modules[lint_spec.name] = voice_lint
        lint_spec.loader.exec_module(voice_lint)

        self._seed_contaminated_run("run-maint")
        rc, md, err = _run_cli(
            ["report", "--run", "run-maint", "--format", "md", "--audience", "maintainer"],
            self.ajar_home,
        )
        self.assertEqual(rc, EXIT_OK, err)

        maint_md_path = self.base / "maint.md"
        maint_md_path.write_text(md, encoding="utf-8")
        maint_lint = voice_lint.lint_file(maint_md_path, tier="S", channel="ghsa")
        self.assertEqual(maint_lint.hard_wrapped_prose_lines, 0, f"Hard wraps in maintainer report:\n{md}")
        self.assertTrue(maint_lint.passed, f"Maintainer report failed voice lint: {maint_lint.issues}")

        # Required human-grade section headings
        for heading in ("## Summary", "## Root Cause", "## Reproduction", "## Impact", "## Suggested Fix"):
            self.assertIn(heading, md)

        # Calibrated title/prose/severity applied; stale pre-calibration text absent
        self.assertIn("Negative chunk length bypasses upper-bound check in parse_chunk_length", md)
        self.assertIn("medium-severity", md)
        self.assertNotIn("STALE UNCALIBRATED", md)
        self.assertIn("HTTP/1.1 listeners", md)

        # Verified production patch diff preferred over raw micropatch
        self.assertIn("+    if (raw_len < 0) return -1;", md)

        # Repo-relative locus normalized; zero host filesystem path leaks
        self.assertIn("`src/acme_parser.c:4`", md)
        self.assertNotIn("Users/", md)
        self.assertNotIn("/home/", md)
        self.assertNotIn(".ajar/runs", md)
        self.assertNotIn("slot-0", md)
        self.assertNotIn("worker-w-", md)
        self.assertNotIn(str(self.repo), md)

        # Zero internal harness IDs, multi-arm labels, micropatch/maintainer_patched enums, COGS headers, or bullet walls
        banned_tokens = (
            "clm-88aa11bb",
            "fnd-99cc00dd",
            "cor-77ee22ff",
            "pvf-11223344",
            "w-falsifier-2",
            "w-hunt-1",
            "4-arm",
            "8-arm",
            "9-arm",
            "Arm 1",
            "Arms 3 & 4",
            "micropatch",
            "Micro-Patch",
            "maintainer_patched",
            "found_autonomously_by_ajar",
            "COGS cap",
            "uncapped_research",
            "Measured Compute Spend",
            "Closeout gates",
            "stepping stone",
            "Furthermore",
            "utilizes",
            "—",
        )
        for tok in banned_tokens:
            self.assertNotIn(tok, md, f"Leaked banned token {tok!r} in maintainer Markdown:\n{md}")

        bold_bullets = [ln for ln in md.splitlines() if re.match(r"^[-*]\s+\*\*[^*]+:\*\*", ln.strip())]
        self.assertEqual(bold_bullets, [], f"Unexpected bold-label bullets in maintainer report: {bold_bullets}")

        # Maintainer JSON projection also omits internal IDs, economics, and host paths
        rc_j, js_raw, err_j = _run_cli(
            ["report", "--run", "run-maint", "--format", "json", "--audience", "maintainer"],
            self.ajar_home,
        )
        self.assertEqual(rc_j, EXIT_OK, err_j)
        payload = json.loads(js_raw)
        self.assertEqual(payload["schema"], "ajar-maintainer-report/1")
        self.assertEqual(payload["target"], "acme-http")
        self.assertNotIn("economics", payload)
        self.assertNotIn("clm-88aa11bb", js_raw)
        self.assertNotIn("fnd-99cc00dd", js_raw)
        self.assertNotIn("Users/", js_raw)
        self.assertEqual(payload["findings"][0]["location"], "src/acme_parser.c:4")
        self.assertEqual(payload["findings"][0]["severity"], "medium")

    def test_customer_default_and_internal_audiences_plus_calibrate_root_cause(self) -> None:
        import importlib.util

        lint_spec = importlib.util.spec_from_file_location(
            "report_voice_lint_cust",
            pathlib.Path(__file__).resolve().parents[1] / "skills" / "security-advisory-report" / "scripts" / "report_voice_lint.py",
        )
        assert lint_spec is not None and lint_spec.loader is not None
        voice_lint = importlib.util.module_from_spec(lint_spec)
        sys.modules[lint_spec.name] = voice_lint
        lint_spec.loader.exec_module(voice_lint)

        self._seed_contaminated_run("run-cust")

        # Default `--audience` is `customer`: Markdown strips host paths, COGS headers, and internal IDs
        rc_md, cust_md, err_md = _run_cli(["report", "--run", "run-cust", "--format", "md"], self.ajar_home)
        self.assertEqual(rc_md, EXIT_OK, err_md)
        cust_md_path = self.base / "cust.md"
        cust_md_path.write_text(cust_md, encoding="utf-8")
        cust_lint = voice_lint.lint_file(cust_md_path, tier="audit", channel="customer")
        self.assertEqual(cust_lint.hard_wrapped_prose_lines, 0, f"Hard wraps in customer report:\n{cust_md}")
        self.assertTrue(cust_lint.passed, f"Customer report failed voice lint: {cust_lint.issues}")
        self.assertIn("# Security Review Report: acme-http", cust_md)
        self.assertIn("## Scope and Inspected Controls", cust_md)
        self.assertIn("`src/http_router.py:2`", cust_md)
        self.assertNotIn("tsk-dry1", cust_md)
        self.assertNotIn("str-internal1", cust_md)
        self.assertNotIn("COGS cap", cust_md)
        self.assertNotIn("Users/", cust_md)
        self.assertNotIn(".ajar/runs", cust_md)
        self.assertNotIn("fnd-99cc00dd", cust_md)

        # Default JSON preserves backward-compatible structure while sanitizing local paths
        rc_cj, cust_js_raw, _ = _run_cli(["report", "--run", "run-cust", "--format", "json"], self.ajar_home)
        self.assertEqual(rc_cj, EXIT_OK)
        cust_js = json.loads(cust_js_raw)
        self.assertEqual(cust_js["schema"], "ajar-report/3")
        self.assertEqual(cust_js["audience"], "customer")
        self.assertEqual(cust_js["target_path"], "acme-http")
        self.assertEqual(cust_js["distinct_root_causes_count"], 1)
        self.assertIn("harness_integrity", cust_js)
        self.assertEqual(cust_js["findings"][0]["finding_id"], "fnd-99cc00dd")
        self.assertEqual(cust_js["findings"][0]["locus"], "src/acme_parser.c:4")
        self.assertNotIn("cogs_cap_usd", json.dumps(cust_js["economics"]))
        self.assertNotIn("Users/", cust_js_raw)

        # `--audience internal` retains full internal ledger telemetry
        rc_int, int_md, _ = _run_cli(
            ["report", "--run", "run-cust", "--format", "md", "--audience", "internal"],
            self.ajar_home,
        )
        self.assertEqual(rc_int, EXIT_OK)
        self.assertIn("COGS cap", int_md)
        self.assertIn("fnd-99cc00dd", int_md)
        self.assertIn("Workspace Steers Applied", int_md)
        self.assertNotIn("STALE UNCALIBRATED", int_md)

        # Operator `ajar finding calibrate --root-cause` supersedes earlier correction cleanly
        rc_cal, _, err_cal = _run_cli(
            [
                "finding",
                "calibrate",
                "fnd-99cc00dd",
                "--run",
                "run-cust",
                "--severity",
                "low",
                "--title",
                "Signed negative chunk length bypasses max_frame guard",
                "--root-cause",
                "In `src/acme_parser.c:4`, `parse_chunk_length()` compares signed `raw_len` only against `max_frame`, letting negative values return unchecked.",
                "--reason",
                "Downstream caller clamps negative slices unless legacy framing mode is enabled.",
            ],
            self.ajar_home,
        )
        self.assertEqual(rc_cal, EXIT_OK, err_cal)

        rc_m2, maint_md2, _ = _run_cli(
            [
                "report",
                "--run",
                "run-cust",
                "--audience",
                "maintainer",
                "--finding",
                "fnd-99cc00dd",
            ],
            self.ajar_home,
        )
        self.assertEqual(rc_m2, EXIT_OK)
        self.assertIn("# Signed negative chunk length bypasses max_frame guard", maint_md2)
        self.assertIn("low-severity", maint_md2)
        self.assertIn("legacy framing mode", maint_md2)

        # Unknown `--finding` fails closed with EXIT_USER_ERROR
        rc_bad, _, err_bad = _run_cli(
            ["report", "--run", "run-cust", "--audience", "maintainer", "--finding", "fnd-nonexistent"],
            self.ajar_home,
        )
        self.assertEqual(rc_bad, EXIT_USER_ERROR, err_bad)
        self.assertIn("fnd-nonexistent", err_bad)

    def test_multi_finding_and_chain_rendering_without_raw_json_or_id_leaks(self) -> None:
        self._seed_contaminated_run("run-chain")
        fake_home = "/" + "home/" + "runner"
        conn = open_run_db("run-chain", ajar_home=self.ajar_home)
        try:
            with immediate_tx(conn):
                conn.execute(
                    """
                    INSERT INTO primitives(
                        primitive_id, subsystem, locus, kind, role, preconditions, postconditions,
                        evidence_cmd, chained, status, created_at
                    ) VALUES (
                        'prim-aa11bb22', 'src', ?, 'prefix_role_token', 'capability',
                        'Unauthenticated HTTP request', 'Attacker obtains admin_guest role string',
                        'python3 src/http_router.py', 1, 'chained', '2026-11-21T11:00:00Z'
                    )
                    """,
                    (f"{self.repo}/src/http_router.py:2",),
                )
                conn.execute(
                    """
                    INSERT INTO claims(
                        claim_id, proposer_worker_id, falsifier_worker_id, title, subsystem, locus,
                        mechanism, mechanism_key, severity, falsification_prediction, falsification_test,
                        status, research_state, evidence_state, remediation_state, created_at, updated_at
                    ) VALUES (
                        'clm-22334455', 'w-1', 'w-2', 'Prefix role match in dispatch_route',
                        'src', 'src/http_router.py:2',
                        '`dispatch_route()` checks `role.startswith(\"admin\")`, accepting `admin_guest` tokens.',
                        'dispatch_route:prefix', 'high',
                        'Exact string equality rejects `admin_guest`.', 'python3 src/http_router.py',
                        'reproduced', 'confirmed', 'reproduced', 'micropatched',
                        '2026-11-21T11:05:00Z', '2026-11-21T11:10:00Z'
                    )
                    """
                )
                conn.execute(
                    """
                    INSERT INTO findings(
                        finding_id, claim_id, title, severity, locus, root_cause, poc_cmd, control_cmd,
                        micropatch_diff, arm1_clean_poc_json, arm2_clean_ctrl_json, arm3_patch_poc_json, arm4_patch_ctrl_json,
                        realism_tier, attribution, created_at
                    ) VALUES (
                        'fnd-66778899', 'clm-22334455', 'Prefix role match in dispatch_route',
                        'high', 'src/http_router.py:2',
                        '`dispatch_route()` checks `role.startswith(\"admin\")`, accepting `admin_guest` tokens.',
                        'python3 src/http_router.py admin_guest', 'python3 src/http_router.py admin',
                        '--- a/src/http_router.py\n+++ b/src/http_router.py\n@@ -1,2 +1,2 @@\n def dispatch_route(role: str) -> bool:\n-    return role.startswith(\"admin\")\n+    return role == \"admin\"\n',
                        '{"exit_code": 1, "arm_passed": true}', '{"exit_code": 0, "arm_passed": true}',
                        '{"exit_code": 0, "arm_passed": true}', '{"exit_code": 0, "arm_passed": true}',
                        'high_impact', 'found_autonomously_by_ajar', '2026-11-21T11:15:00Z'
                    )
                    """
                )
                conn.execute(
                    """
                    INSERT INTO chains(
                        chain_id, title, severity, step_ids_json, e2e_poc_cmd, control_cmd,
                        verified, ablation_matrix_json, realism_tier, created_at
                    ) VALUES (
                        'chn-deadbeef', 'Prefix role bypass into negative chunk frame read', 'high',
                        '["prim-aa11bb22", "fnd-99cc00dd"]',
                        ?, 'python3 src/http_router.py admin',
                        1, '[{"step": "prim-aa11bb22", "ablated_via": "stage_context_env"}]',
                        'high_impact', '2026-11-21T12:00:00Z'
                    )
                    """,
                    (f"sh {fake_home}/.ajar/runs/run-chain/artifacts/e2e_chain.sh",),
                )
        finally:
            conn.close()

        for aud in ("maintainer", "customer"):
            rc, md, err = _run_cli(["report", "--run", "run-chain", "--audience", aud], self.ajar_home)
            self.assertEqual(rc, EXIT_OK, err)
            self.assertIn("Multi-Step Attack Chains", md)
            self.assertIn("./e2e_chain.sh", md)
            self.assertNotIn("chn-deadbeef", md)
            self.assertNotIn("prim-aa11bb22", md)
            self.assertNotIn("stage_context_env", md)
            self.assertNotIn("/home/", md)


if __name__ == "__main__":
    unittest.main()
