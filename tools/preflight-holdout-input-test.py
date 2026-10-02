#!/usr/bin/env python3
"""Holdout preflight must reject FIFO preregistration input instead of blocking."""

import os
import subprocess
import sys
import tempfile


def main():
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "preflight_holdout.py")
    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, "prereg.json")
        os.mkfifo(path)
        try:
            result = subprocess.run([sys.executable, script, "--prereg", path],
                                    capture_output=True, text=True, timeout=2)
        except subprocess.TimeoutExpired:
            raise AssertionError("preflight blocked on FIFO preregistration input")
        assert result.returncode == 2, (result.returncode, result.stderr)
        assert "regular file" in result.stderr, result.stderr
    print("holdout preflight FIFO input check passed")


if __name__ == "__main__":
    main()
