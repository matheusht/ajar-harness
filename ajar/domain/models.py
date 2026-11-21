"""Frozen domain models and structured state-transition errors for Ajar."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from ajar import EXIT_GATE_BLOCKED, EXIT_USER_ERROR
from ajar.domain.enums import EvidenceState, ResearchState


class AjarError(Exception):
    """Structured error carrying an explicit CLI exit code."""

    def __init__(
        self,
        message: str,
        exit_code: int = EXIT_USER_ERROR,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.exit_code = exit_code
        self.details = details or {}


class InvalidTransitionError(AjarError):
    """Raised when a state-machine transition violates an architectural invariant.

    Subclasses `AjarError` with `exit_code = EXIT_GATE_BLOCKED` so all CLI, MCP, and
    caller `except AjarError` handlers catch invalid transitions uniformly.
    """

    def __init__(
        self,
        machine: str,
        current: str,
        target: str,
        *,
        entity_id: str = "",
        reason: str = "",
        allowed_targets: Sequence[str] = (),
        fix_hint: str = "",
        exit_code: int = EXIT_GATE_BLOCKED,
    ) -> None:
        self.machine = machine
        self.current = current
        self.target = target
        self.entity_id = entity_id
        self.reason = reason
        self.allowed_targets: tuple[str, ...] = tuple(str(x) for x in allowed_targets)
        self.fix_hint = fix_hint
        details: dict[str, Any] = {
            "machine": machine,
            "current": current,
            "target": target,
            "entity_id": entity_id,
            "allowed_targets": list(self.allowed_targets),
        }
        if fix_hint:
            details["fix_hint"] = fix_hint
        prefix = f"Invalid {machine} transition"
        who = f" for {entity_id}" if entity_id else ""
        detail = f": {reason}" if reason else ""
        allowed_s = f" (allowed: {', '.join(self.allowed_targets)})" if self.allowed_targets else ""
        hint_s = f". Hint: {fix_hint}" if fix_hint else ""
        super().__init__(
            f"{prefix}{who}: {current!r} -> {target!r}{detail}{allowed_s}{hint_s}",
            exit_code=exit_code,
            details=details,
        )


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
