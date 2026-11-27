"""AJAR v3.6 — Three-Ring Earned-Mass Autonomous Verification Engine."""

from __future__ import annotations

__version__ = "3.6.0"

RING0_MODULES = (
    "cli.py",
    "llm.py",
    "agent.py",
    "verify.py",
)

RING1_MODULES = (
    "repomap.py",
    "whiteboard.py",
    "epistemic.py",
    "chain_weaver.py",
    "autobuild.py",
    "swarm.py",
    "bench.py",
)

__all__ = [
    "__version__",
    "RING0_MODULES",
    "RING1_MODULES",
]
