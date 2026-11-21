"""Ajar: Autonomous security research engine (Dual-Mode Host + Standalone CLI).

Zero-LLM deterministic state, verification, and closeout-gate engine backed by
an external SQLite WAL database (`~/.ajar/runs/<run_id>/run.db`).
"""

from __future__ import annotations

__version__ = "3.3.0"

EXIT_OK = 0
EXIT_USER_ERROR = 2
EXIT_GATE_BLOCKED = 3
EXIT_STALLED_RELEASE = 4
