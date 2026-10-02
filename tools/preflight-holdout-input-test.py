#!/usr/bin/env python3
"""Holdout preflight must reject FIFO preregistration input instead of blocking."""

import os
import subprocess
import sys
import tempfile
import importlib.util
import json
from pathlib import Path


SCRIPT = Path(__file__).with_name("preflight_holdout.py")


def scan(root):
    spec = importlib.util.spec_from_file_location("preflight_holdout", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.ROOT = str(root)
    print(json.dumps(module.check_not_quoted("holdout.md", set())))


def run_scan(root):
    result = subprocess.run(
        [sys.executable, __file__, "--scan", str(root)],
        capture_output=True,
        text=True,
        timeout=2,
        check=False,
    )
    if result.returncode:
        raise AssertionError(result.stderr or result.stdout)
    return json.loads(result.stdout)


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--scan":
        scan(sys.argv[2])
        return

    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, "prereg.json")
        os.mkfifo(path)
        try:
            result = subprocess.run([sys.executable, str(SCRIPT), "--prereg", path],
                                    capture_output=True, text=True, timeout=2)
        except subprocess.TimeoutExpired:
            raise AssertionError("preflight blocked on FIFO preregistration input")
        assert result.returncode == 2, (result.returncode, result.stderr)
        assert "regular file" in result.stderr, result.stderr

    failures = []
    with tempfile.TemporaryDirectory(prefix="holdout-scan-e2e-") as directory:
        root = Path(directory) / "repo"
        docs = root / "docs"
        docs.mkdir(parents=True)

        fifo = docs / "blocked.md"
        os.mkfifo(fifo)
        try:
            rows = run_scan(root)
            assert rows and rows[0][1].startswith("unsafe:"), rows
        except Exception as exc:
            failures.append(f"FIFO: {exc}")
        fifo.unlink()

        outside = Path(directory) / "outside.md"
        outside.write_text("holdout OUTSIDE-MARKER")
        link = docs / "outside.md"
        link.symlink_to(outside)
        try:
            rows = run_scan(root)
            assert rows and rows[0][1].startswith("unsafe:"), rows
            assert "OUTSIDE-MARKER" not in repr(rows), rows
        except Exception as exc:
            failures.append(f"file symlink: {exc}")
        link.unlink()

        outside_dir = Path(directory) / "outside-dir"
        outside_dir.mkdir()
        (outside_dir / "hidden.md").write_text("holdout OUTSIDE-MARKER")
        link_dir = docs / "linked-dir"
        link_dir.symlink_to(outside_dir, target_is_directory=True)
        try:
            rows = run_scan(root)
            assert rows and rows[0][1].startswith("unsafe:"), rows
            assert "OUTSIDE-MARKER" not in repr(rows), rows
        except Exception as exc:
            failures.append(f"directory symlink: {exc}")
        link_dir.unlink()

        (docs / "leak.md").write_text("holdout")
        try:
            rows = run_scan(root)
            assert ("docs/leak.md", "holdout") in [tuple(row) for row in rows], rows
        except Exception as exc:
            failures.append(f"regular leak: {exc}")

    assert not failures, "\n".join(failures)
    print("holdout preflight E2E passed (input FIFO, scan FIFO, file/dir symlink, regular leak)")


if __name__ == "__main__":
    main()
