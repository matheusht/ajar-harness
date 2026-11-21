"""Tests for startup proof helpers (`ajar/services/proof.py`) and `scripts/verify-repo.sh`."""

from __future__ import annotations

import io
import json
import os
import pathlib
import stat
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from ajar.cli import main as cli_main
from ajar.db import open_run_db, utc_now_iso
from ajar.domain import AjarError
from ajar.services import (
    build_commit_preimage,
    export_run_economics,
    verify_commit_preimage,
    write_restricted_json,
)
from ajar.store import immediate_tx

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


def _run_cli(argv: list[str]) -> tuple[int, dict[str, object]]:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        rc = cli_main(argv)
    raw = out.getvalue().strip()
    data: dict[str, object] = json.loads(raw) if raw.startswith("{") else {"raw": raw}
    if err.getvalue().strip():
        data["_stderr"] = err.getvalue().strip()
    return rc, data


def _seed_run_with_finding(
    ajar_home: pathlib.Path,
    *,
    run_id: str = "proof-run-1",
    finding_title: str = "Auth bypass on empty nonce",
    spend_usd: float = 20.0,
    code_quote_usd: float = 100.0,
    head_sha: str = "abc1234567890def",
) -> str:
    with mock.patch.dict(os.environ, {"AJAR_HOME": str(ajar_home)}):
        conn = open_run_db(run_id, create=True)
        now = utc_now_iso()
        try:
            with immediate_tx(conn):
                conn.execute(
                    """
                    INSERT INTO runs(
                        run_id, target_path, workspace_path, target_mode, workspace_mode,
                        goal, stopping_criterion, campaign_phase, status,
                        in_scope_loc, code_quote_usd, cogs_cap_usd, commitment_hash, head_sha, created_at
                    ) VALUES (?, '/tmp/demo-target', '/tmp/demo-target', 'source', 'in_place',
                              'proof test', 'exhaustive-high', 'hunt', 'active',
                              2000, ?, 35.0, 'deadbeefcafe', ?, ?)
                    """,
                    (run_id, code_quote_usd, head_sha, now),
                )
                conn.execute(
                    """
                    INSERT INTO spend_ledger(
                        entry_id, worker_id, phase, model, tokens_in, tokens_out, cost_usd, created_at
                    ) VALUES ('spd-1', 'w1', 'explore', 'host-model', 4000, 1200, ?, ?)
                    """,
                    (spend_usd, now),
                )
                conn.execute(
                    """
                    INSERT INTO claims(
                        claim_id, proposer_worker_id, falsifier_worker_id, title, subsystem, locus,
                        mechanism, mechanism_key, severity, falsification_prediction, falsification_test,
                        status, research_state, evidence_state, created_at, updated_at
                    ) VALUES (
                        'clm-proof1', 'w-prop', 'w-fals', ?, 'auth', 'src/auth.py:42',
                        'Empty nonce skips signature check', 'empty_nonce', 'high',
                        'Empty nonce authenticates', 'python3 -c "print(1)"',
                        'reproduced', 'confirmed', 'reproduced', ?, ?
                    )
                    """,
                    (finding_title, now, now),
                )
                conn.execute(
                    """
                    INSERT INTO findings(
                        finding_id, claim_id, title, severity, locus, root_cause,
                        poc_cmd, control_cmd,
                        arm1_clean_poc_json, arm2_clean_ctrl_json,
                        arm3_patch_poc_json, arm4_patch_ctrl_json,
                        attribution, created_at
                    ) VALUES (
                        'fnd-proof1', 'clm-proof1', ?, 'high', 'src/auth.py:42',
                        'Empty nonce skips signature verification',
                        'exit 1', 'exit 0',
                        '{}', '{}', '{}', '{}',
                        'found_autonomously_by_ajar', ?
                    )
                    """,
                    (finding_title, now),
                )
        finally:
            conn.close()
    return run_id


class ProofHelpersAndDriverTests(unittest.TestCase):
    def test_economics_export_service_and_cli_are_read_only_and_advisory(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            ajar_home = base / "ajar_home"
            out_file = base / "out" / "econ.json"
            run_id = _seed_run_with_finding(ajar_home, spend_usd=20.0, code_quote_usd=100.0)

            with mock.patch.dict(os.environ, {"AJAR_HOME": str(ajar_home)}):
                conn = open_run_db(run_id)
                try:
                    econ = export_run_economics(conn)
                    self.assertEqual(econ["schema_version"], "ajar-economics-calibration/1")
                    self.assertTrue(econ["host_mode_advisory"])
                    self.assertEqual(econ["in_scope_loc"], 2000)
                    self.assertEqual(econ["code_quote_usd"], 100.0)
                    self.assertEqual(econ["cogs_cap_usd"], 35.0)
                    self.assertEqual(econ["total_spend_usd"], 20.0)
                    self.assertEqual(econ["cost_usd_per_kloc"], 10.0)
                    self.assertEqual(econ["implied_gross_margin_pct"], 80.0)
                    self.assertTrue(econ["gross_margin_floor_pass"])
                    self.assertEqual(econ["findings_count"], 1)
                    self.assertEqual(econ["high_or_critical_findings"], 1)
                    self.assertTrue(econ["research_independence_pass"])
                finally:
                    conn.close()

                rc, cli_res = _run_cli(["economics", "export", "--run", run_id, "--output", str(out_file)])
                self.assertEqual(rc, 0)
                self.assertEqual(cli_res["run_id"], run_id)
                self.assertTrue(out_file.is_file())
                written = json.loads(out_file.read_text(encoding="utf-8"))
                self.assertEqual(written["implied_gross_margin_pct"], 80.0)

                # Over-cap run: gross_margin_floor_pass=False, yet runs.status remains strictly untouched ('active')
                over_id = _seed_run_with_finding(ajar_home, run_id="proof-over", spend_usd=60.0, code_quote_usd=100.0)
                conn_over = open_run_db(over_id)
                try:
                    over_econ = export_run_economics(conn_over)
                    self.assertFalse(over_econ["gross_margin_floor_pass"])
                    self.assertEqual(over_econ["implied_gross_margin_pct"], 40.0)
                    st = str(conn_over.execute("SELECT status FROM runs LIMIT 1").fetchone()["status"])
                    self.assertEqual(st, "active")
                finally:
                    conn_over.close()

                # Zero-quote edge case & missing runs row edge case
                zero_id = _seed_run_with_finding(ajar_home, run_id="proof-zero", spend_usd=5.0, code_quote_usd=0.0)
                conn_z = open_run_db(zero_id)
                try:
                    z_econ = export_run_economics(conn_z)
                    self.assertIsNone(z_econ["implied_gross_margin_pct"])
                    with immediate_tx(conn_z):
                        conn_z.execute("DELETE FROM runs")
                    with self.assertRaises(AjarError):
                        export_run_economics(conn_z)
                finally:
                    conn_z.close()

    def test_commit_preimage_determinism_redaction_security_and_stdout_isolation(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            ajar_home = base / "ajar_home"
            pub_path = base / "ledger" / "public.json"
            priv_path = base / "ledger" / "preimage.json"
            # Construct fake secret dynamically so conformance secret scan stays clean.
            fake_secret = "ghp_" + ("A1b2C3d4E5" * 4)
            run_id = _seed_run_with_finding(
                ajar_home,
                finding_title=f"Token leak exposes {fake_secret} in error response",
                head_sha="cafebabe12345678",
            )

            with mock.patch.dict(os.environ, {"AJAR_HOME": str(ajar_home)}):
                conn = open_run_db(run_id)
                try:
                    # Cross-call determinism even if wall clock advances between calls
                    with mock.patch("ajar.services.proof.utc_now_iso", side_effect=["2026-11-21T00:00:01Z", "2026-11-21T00:09:59Z"]):
                        res1 = build_commit_preimage(
                            conn,
                            finding_id="fnd-proof1",
                            target_slug="acme/gateway",
                            salt="0011223344556677",
                        )
                        res2 = build_commit_preimage(
                            conn,
                            finding_id="fnd-proof1",
                            target_slug="acme/gateway",
                            salt="0011223344556677",
                        )
                    self.assertEqual(res1["commitment_sha256"], res2["commitment_sha256"])
                    self.assertEqual(res1["private_preimage"]["commit_sha"], "cafebabe12345678")
                    self.assertEqual(len(str(res1["commitment_sha256"])), 64)
                    self.assertTrue(verify_commit_preimage(res1["private_preimage"], str(res1["commitment_sha256"])))
                    # Tampering or non-ASCII commitment MUST return False (never TypeError)
                    tampered = dict(res1["private_preimage"])
                    tampered["severity"] = "critical"
                    self.assertFalse(verify_commit_preimage(tampered, str(res1["commitment_sha256"])))
                    self.assertFalse(verify_commit_preimage(res1["private_preimage"], "🔥" * 64))
                    self.assertFalse(verify_commit_preimage(res1["private_preimage"], "not-a-hex-digest"))
                    # Raw secret MUST be scrubbed from preimage and public record
                    self.assertNotIn(fake_secret, json.dumps(res1))
                    self.assertIn("<REDACTED>", str(res1["private_preimage"]["title"]))
                    # Invalid salt or unknown finding raises AjarError
                    with self.assertRaises(AjarError):
                        build_commit_preimage(conn, finding_id="fnd-proof1", salt="too-short!")
                    with self.assertRaises(AjarError):
                        build_commit_preimage(conn, finding_id="fnd-does-not-exist")
                finally:
                    conn.close()

                # Pre-create a world-readable file at priv_path; atomic replacement MUST yield strict 0o600
                priv_path.parent.mkdir(parents=True, exist_ok=True)
                priv_path.write_text("stale", encoding="utf-8")
                os.chmod(priv_path, 0o644)

                rc, cli_res = _run_cli(
                    [
                        "ledger",
                        "commit-preimage",
                        "fnd-proof1",
                        "--run",
                        run_id,
                        "--target-slug",
                        "acme/gateway",
                        "--salt",
                        "0011223344556677",
                        "--public-out",
                        str(pub_path),
                        "--preimage-out",
                        str(priv_path),
                    ]
                )
                self.assertEqual(rc, 0)
                # When --preimage-out is passed, stdout MUST NOT leak private_preimage!
                self.assertNotIn("private_preimage", cli_res)
                self.assertEqual(cli_res["preimage_out"], str(priv_path))
                self.assertTrue(pub_path.is_file())
                self.assertTrue(priv_path.is_file())
                priv_mode = stat.S_IMODE(priv_path.stat().st_mode)
                self.assertEqual(priv_mode, 0o600)
                pub_obj = json.loads(pub_path.read_text(encoding="utf-8"))
                priv_obj = json.loads(priv_path.read_text(encoding="utf-8"))
                self.assertEqual(pub_obj["commitment_sha256"], cli_res["commitment_sha256"])
                self.assertTrue(verify_commit_preimage(priv_obj, pub_obj["commitment_sha256"]))
                self.assertNotIn(fake_secret, priv_path.read_text(encoding="utf-8"))

                # Symlink target at --preimage-out MUST be refused cleanly without modifying symlink target
                victim = base / "victim.txt"
                victim.write_text("untouched", encoding="utf-8")
                sym = base / "symlink_out.json"
                sym.symlink_to(victim)
                with self.assertRaises(AjarError):
                    write_restricted_json(sym, {"secret": "x"})
                self.assertEqual(victim.read_text(encoding="utf-8"), "untouched")

    def test_verify_repo_driver_syntax_help_and_option_validation(self) -> None:
        driver = REPO_ROOT / "scripts" / "verify-repo.sh"
        self.assertTrue(driver.is_file())
        syn = subprocess.run(["bash", "-n", str(driver)], capture_output=True, text=True, check=False)
        self.assertEqual(syn.returncode, 0, syn.stderr)
        hlp = subprocess.run(["bash", str(driver), "--help"], capture_output=True, text=True, check=False)
        self.assertEqual(hlp.returncode, 0, hlp.stderr)
        self.assertIn("--fast", hlp.stdout)
        self.assertIn("--full", hlp.stdout)
        self.assertNotIn("set -euo pipefail", hlp.stdout)
        bad = subprocess.run(["bash", str(driver), "--bogus-flag"], capture_output=True, text=True, check=False)
        self.assertEqual(bad.returncode, 2)
        bad_combo = subprocess.run(
            ["bash", str(driver), "--fast", "--strict-legacy"], capture_output=True, text=True, check=False
        )
        self.assertEqual(bad_combo.returncode, 2)


if __name__ == "__main__":
    unittest.main()
