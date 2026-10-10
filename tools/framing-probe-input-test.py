#!/usr/bin/env python3
"""CLI inputs must reject FIFOs instead of waiting forever for a writer."""

import os
import subprocess
import sys
import tempfile


def main():
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "framing_probe.py")
    commands = (
        ("verify", ["verify", "--packet"]),
        ("brief", ["brief", "--framing", "neutral", "--packet"]),
        ("score", ["score", "--results"]),
    )
    with tempfile.TemporaryDirectory() as directory:
        for name, args in commands:
            path = os.path.join(directory, name + ".fifo")
            os.mkfifo(path)
            try:
                result = subprocess.run([sys.executable, script, *args, path],
                                        capture_output=True, text=True, timeout=2)
            except subprocess.TimeoutExpired:
                raise AssertionError(f"{name} blocked on FIFO")
            assert result.returncode == 2, (name, result.returncode, result.stderr)
            assert "regular file" in result.stderr, (name, result.stderr)
    print("framing probe FIFO input checks passed (3)")


if __name__ == "__main__":
    main()
