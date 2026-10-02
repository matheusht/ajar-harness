#!/usr/bin/env python3
"""The novelty mapper must reject FIFO hypotheses input instead of blocking."""

import os
import subprocess
import sys
import tempfile


def main():
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ideation.py")
    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, "hypotheses.json")
        os.mkfifo(path)
        try:
            result = subprocess.run([sys.executable, script, "map", "--hypotheses", path],
                                    capture_output=True, text=True, timeout=2)
        except subprocess.TimeoutExpired:
            raise AssertionError("ideation map blocked on FIFO hypotheses input")
        assert result.returncode == 2, (result.returncode, result.stderr)
        assert "regular file" in result.stderr, result.stderr
        source = os.path.join(directory, "source", "kvm", "vmhost", "vmhooks")
        os.makedirs(source)
        go_fifo = os.path.join(source, "blocked.go")
        os.mkfifo(go_fifo)
        try:
            result = subprocess.run([sys.executable, script, "fragment", "--source",
                                     os.path.join(directory, "source")],
                                    capture_output=True, text=True, timeout=2)
        except subprocess.TimeoutExpired:
            raise AssertionError("ideation fragment blocked on FIFO source input")
        assert result.returncode == 2, (result.returncode, result.stderr)
        assert "regular file" in result.stderr, result.stderr
    print("ideation mapper FIFO input check passed")


if __name__ == "__main__":
    main()
