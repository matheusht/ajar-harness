"""Allow running `python3 -m ajar.cli` directly."""

from __future__ import annotations

import sys

from ajar.cli import main

if __name__ == "__main__":
    sys.exit(main())
