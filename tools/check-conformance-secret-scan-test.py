#!/usr/bin/env python3
"""E2E checks that conformance scans reject hostile filesystem entries."""
import contextlib
import io
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

CHECKER = Path(__file__).with_name("check-conformance.py")


def scan(root, mode):
    spec = importlib.util.spec_from_file_location("check_conformance", CHECKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.ROOT = str(root)
    rows = []
    module.record = lambda ok, label, detail="": rows.append((ok, label, detail))
    with contextlib.redirect_stdout(io.StringIO()):
        (module.check_secrets if mode == "secrets" else module.check_oracles)()
    print(json.dumps(rows))


def run_scan(root, mode="secrets"):
    result = subprocess.run(
        [sys.executable, __file__, "--scan", mode, str(root)],
        capture_output=True,
        text=True,
        timeout=2,
        check=False,
    )
    if result.returncode:
        raise AssertionError(result.stderr or result.stdout)
    return json.loads(result.stdout)


def main():
    if len(sys.argv) == 4 and sys.argv[1] == "--scan":
        scan(sys.argv[3], sys.argv[2])
        return

    with tempfile.TemporaryDirectory(prefix="secret-scan-e2e-") as tmp:
        root = Path(tmp) / "repo"
        for name in ("casebooks", "fixtures", "evals"):
            (root / name).mkdir(parents=True)

        fifo_root = root / "evals"
        os.mkfifo(fifo_root / "blocked.fifo")
        rows = run_scan(root)
        assert rows and not rows[0][0] and "blocked.fifo" in rows[0][2], rows

        (fifo_root / "blocked.fifo").unlink()
        outside = Path(tmp) / "outside.txt"
        outside.write_text("EVIDENCE-ABCDEF secret-shaped marker")
        (fifo_root / "outside-link.txt").symlink_to(outside)
        rows = run_scan(root)
        assert rows and not rows[0][0] and "outside-link.txt" in rows[0][2], rows
        assert "EVIDENCE-ABCDEF" not in rows[0][2], rows

        (fifo_root / "outside-link.txt").unlink()
        outside_dir = Path(tmp) / "outside-dir"
        outside_dir.mkdir()
        (outside_dir / "hidden.txt").write_text("EVIDENCE-ABCDEF")
        (fifo_root / "outside-dir").symlink_to(outside_dir, target_is_directory=True)
        rows = run_scan(root)
        assert rows and not rows[0][0] and "outside-dir" in rows[0][2], rows
        assert "EVIDENCE-ABCDEF" not in rows[0][2], rows

        (fifo_root / "outside-dir").unlink()
        (fifo_root / "ordinary.txt").write_text("EVIDENCE-ABCDEF")
        rows = run_scan(root)
        assert rows and not rows[0][0] and "EVIDENCE-ABCDEF" in rows[0][2], rows

    oracle_failures = []
    with tempfile.TemporaryDirectory(prefix="oracle-scan-e2e-") as tmp:
        root = Path(tmp) / "repo"
        oracle_dir = root / "skills" / "oracles"
        oracle_dir.mkdir(parents=True)

        fifo = oracle_dir / "blocked.md"
        os.mkfifo(fifo)
        try:
            rows = run_scan(root, "oracles")
            assert rows and any(not row[0] and "unsafe" in row[2] for row in rows), rows
        except Exception as exc:
            oracle_failures.append(f"FIFO: {exc}")
        fifo.unlink()

        oracle = "---\nid: oracle.test\ntype: oracle\n---\nRegular fixture.\n"
        outside = Path(tmp) / "outside.md"
        outside.write_text(oracle)
        link = oracle_dir / "outside.md"
        link.symlink_to(outside)
        try:
            rows = run_scan(root, "oracles")
            assert rows and any(not row[0] and "unsafe" in row[2] for row in rows), rows
        except Exception as exc:
            oracle_failures.append(f"file symlink: {exc}")
        link.unlink()

        (oracle_dir / "regular.md").write_text(oracle)
        try:
            rows = run_scan(root, "oracles")
            assert rows and all(row[0] for row in rows), rows
        except Exception as exc:
            oracle_failures.append(f"regular card: {exc}")

    assert not oracle_failures, "\n".join(oracle_failures)
    print("conformance filesystem E2E passed (secret and oracle scans)")


if __name__ == "__main__":
    main()
