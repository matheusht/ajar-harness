"""Frozen domain models and structured state-transition errors for Ajar."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ajar import EXIT_GATE_BLOCKED
from ajar.domain.enums import EvidenceState, ResearchState


class InvalidTransitionError(Exception):
    """Raised when a state-machine transition violates an architectural invariant.

    Carries `exit_code = EXIT_GATE_BLOCKED` so CLI/MCP dispatch treats it uniformly
    alongside `AjarError`.
    """

    def __init__(
        self,
        machine: str,
        current: str,
        target: str,
        *,
        entity_id: str = "",
        reason: str = "",
        exit_code: int = EXIT_GATE_BLOCKED,
    ) -> None:
        self.machine = machine
        self.current = current
        self.target = target
        self.entity_id = entity_id
        self.reason = reason
        self.exit_code = exit_code
        self.details: dict[str, Any] = {
            "machine": machine,
            "current": current,
            "target": target,
            "entity_id": entity_id,
        }
        prefix = f"Invalid {machine} transition"
        who = f" for {entity_id}" if entity_id else ""
        detail = f": {reason}" if reason else ""
        super().__init__(f"{prefix}{who}: {current!r} -> {target!r}{detail}")


@dataclass(frozen=True, slots=True)
class ClaimAxes:
    """Orthogonal truth axes mechanically derived from canonical `ClaimStatus`."""

    research_state: ResearchState
    evidence_state: EvidenceState


@dataclass(frozen=True, slots=True)
class ArmResult:
    """Typed receipt for a single causal reproduction or patch-verification arm."""

    exit_code: int
    arm_passed: bool
    timed_out: bool = False
    stdout: str = ""
    stderr: str = ""
    defect_hits: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "exit_code": self.exit_code,
            "arm_passed": self.arm_passed,
            "timed_out": self.timed_out,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "defect_hits": self.defect_hits,
        }
