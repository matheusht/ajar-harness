"""Module execution entrypoint (`python3 -m ajar`)."""

from __future__ import annotations

import sys

from ajar.cli import main

if __name__ == "__main__":
    sys.exit(main())
