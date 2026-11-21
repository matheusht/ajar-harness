"""Explicit state-transition tables and pure axis-derivation rules for Ajar."""

from __future__ import annotations

from ajar.domain.enums import (
    AnomalyStatus,
    AssumptionStatus,
    CampaignPhase,
    ClaimStatus,
    DispatchStatus,
    DoorStatus,
    EvidenceState,
    PrimitiveStatus,
    ResearchState,
    RunStatus,
    TaskStatus,
)
from ajar.domain.models import ClaimAxes, InvalidTransitionError

ALLOWED_RUN_TRANSITIONS: dict[RunStatus, frozenset[RunStatus]] = {
    RunStatus.ACTIVE: frozenset({RunStatus.ACTIVE, RunStatus.VERIFY_ONLY, RunStatus.FINISHED, RunStatus.BLOCKED}),
    RunStatus.VERIFY_ONLY: frozenset({RunStatus.VERIFY_ONLY, RunStatus.ACTIVE, RunStatus.FINISHED, RunStatus.BLOCKED}),
    RunStatus.BLOCKED: frozenset({RunStatus.BLOCKED, RunStatus.ACTIVE, RunStatus.FINISHED}),
    RunStatus.FINISHED: frozenset({RunStatus.ACTIVE}),
}

ALLOWED_PHASE_TRANSITIONS: dict[CampaignPhase, frozenset[CampaignPhase]] = {
    CampaignPhase.HUNT: frozenset({CampaignPhase.HUNT, CampaignPhase.REMEDIATE, CampaignPhase.FULL}),
    CampaignPhase.REMEDIATE: frozenset({CampaignPhase.REMEDIATE, CampaignPhase.FULL}),
    CampaignPhase.FULL: frozenset({CampaignPhase.FULL}),
}

ALLOWED_TASK_TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.OPEN: frozenset(
        {TaskStatus.OPEN, TaskStatus.LEASED, TaskStatus.DONE, TaskStatus.DRY, TaskStatus.CONDITIONAL_BLOCKED}
    ),
    TaskStatus.LEASED: frozenset(
        {TaskStatus.OPEN, TaskStatus.LEASED, TaskStatus.DONE, TaskStatus.DRY, TaskStatus.CONDITIONAL_BLOCKED}
    ),
    TaskStatus.CONDITIONAL_BLOCKED: frozenset({TaskStatus.OPEN, TaskStatus.CONDITIONAL_BLOCKED}),
    TaskStatus.DONE: frozenset({TaskStatus.DONE}),
    TaskStatus.DRY: frozenset({TaskStatus.DRY}),
}

ALLOWED_CLAIM_TRANSITIONS: dict[ClaimStatus, frozenset[ClaimStatus]] = {
    ClaimStatus.PROPOSED: frozenset(
        {
            ClaimStatus.PROPOSED,
            ClaimStatus.SURVIVED_FALSIFY,
            ClaimStatus.FALSIFIED,
            ClaimStatus.CONFIG_GATED,
            ClaimStatus.BLOCKED,
            ClaimStatus.DUPLICATE_ROOT_CAUSE,
        }
    ),
    ClaimStatus.CONFIG_GATED: frozenset(
        {
            ClaimStatus.CONFIG_GATED,
            ClaimStatus.SURVIVED_FALSIFY,
            ClaimStatus.FALSIFIED,
            ClaimStatus.BLOCKED,
            ClaimStatus.DUPLICATE_ROOT_CAUSE,
        }
    ),
    ClaimStatus.SURVIVED_FALSIFY: frozenset(
        {
            ClaimStatus.SURVIVED_FALSIFY,
            ClaimStatus.NEEDS_INSTRUMENTATION,
            ClaimStatus.REPRODUCED,
            ClaimStatus.REJECTED_REPRO,
            ClaimStatus.FALSIFIED,
            ClaimStatus.CONFIG_GATED,
            ClaimStatus.BLOCKED,
            ClaimStatus.DUPLICATE_ROOT_CAUSE,
        }
    ),
    ClaimStatus.NEEDS_INSTRUMENTATION: frozenset(
        {
            ClaimStatus.NEEDS_INSTRUMENTATION,
            ClaimStatus.SURVIVED_FALSIFY,
            ClaimStatus.FALSIFIED,
            ClaimStatus.CONFIG_GATED,
            ClaimStatus.BLOCKED,
            ClaimStatus.DUPLICATE_ROOT_CAUSE,
        }
    ),
    ClaimStatus.REPRODUCED: frozenset({ClaimStatus.REPRODUCED}),
    ClaimStatus.FALSIFIED: frozenset({ClaimStatus.FALSIFIED}),
    ClaimStatus.REJECTED_REPRO: frozenset({ClaimStatus.REJECTED_REPRO, ClaimStatus.SURVIVED_FALSIFY}),
    ClaimStatus.DUPLICATE_ROOT_CAUSE: frozenset({ClaimStatus.DUPLICATE_ROOT_CAUSE}),
    ClaimStatus.BLOCKED: frozenset({ClaimStatus.BLOCKED}),
}

ALLOWED_PRIMITIVE_TRANSITIONS: dict[PrimitiveStatus, frozenset[PrimitiveStatus]] = {
    PrimitiveStatus.ACTIVE: frozenset({PrimitiveStatus.ACTIVE, PrimitiveStatus.CHAINED, PrimitiveStatus.DRY}),
    PrimitiveStatus.CHAINED: frozenset({PrimitiveStatus.CHAINED}),
    PrimitiveStatus.DRY: frozenset({PrimitiveStatus.DRY}),
}

ALLOWED_ANOMALY_TRANSITIONS: dict[AnomalyStatus, frozenset[AnomalyStatus]] = {
    AnomalyStatus.UNEXPLAINED: frozenset(
        {
            AnomalyStatus.UNEXPLAINED,
            AnomalyStatus.BENIGN_EXPLAINED,
            AnomalyStatus.CONSUMED_BY_CLAIM,
            AnomalyStatus.CONSUMED_BY_CHAIN,
        }
    ),
    AnomalyStatus.CONSUMED_BY_CLAIM: frozenset(
        {AnomalyStatus.UNEXPLAINED, AnomalyStatus.CONSUMED_BY_CLAIM, AnomalyStatus.CONSUMED_BY_CHAIN}
    ),
    AnomalyStatus.BENIGN_EXPLAINED: frozenset(
        {AnomalyStatus.BENIGN_EXPLAINED, AnomalyStatus.CONSUMED_BY_CLAIM, AnomalyStatus.CONSUMED_BY_CHAIN}
    ),
    AnomalyStatus.CONSUMED_BY_CHAIN: frozenset({AnomalyStatus.CONSUMED_BY_CHAIN}),
}

ALLOWED_DOOR_TRANSITIONS: dict[DoorStatus, frozenset[DoorStatus]] = {
    DoorStatus.PARKED: frozenset(
        {DoorStatus.PARKED, DoorStatus.BRIDGING, DoorStatus.READY, DoorStatus.CHAINED, DoorStatus.EXHAUSTED_LOCKED}
    ),
    DoorStatus.BRIDGING: frozenset(
        {DoorStatus.BRIDGING, DoorStatus.READY, DoorStatus.CHAINED, DoorStatus.EXHAUSTED_LOCKED}
    ),
    DoorStatus.EXHAUSTED_LOCKED: frozenset({DoorStatus.EXHAUSTED_LOCKED, DoorStatus.READY, DoorStatus.CHAINED}),
    DoorStatus.READY: frozenset({DoorStatus.READY, DoorStatus.CHAINED, DoorStatus.EXHAUSTED_LOCKED}),
    DoorStatus.CHAINED: frozenset({DoorStatus.CHAINED}),
}

ALLOWED_ASSUMPTION_TRANSITIONS: dict[AssumptionStatus, frozenset[AssumptionStatus]] = {
    AssumptionStatus.ASSUMED: frozenset(
        {AssumptionStatus.ASSUMED, AssumptionStatus.VERIFIED_HOLDS, AssumptionStatus.VIOLATED}
    ),
    AssumptionStatus.VERIFIED_HOLDS: frozenset({AssumptionStatus.VERIFIED_HOLDS, AssumptionStatus.VIOLATED}),
    AssumptionStatus.VIOLATED: frozenset({AssumptionStatus.VIOLATED}),
}

ALLOWED_DISPATCH_TRANSITIONS: dict[DispatchStatus, frozenset[DispatchStatus]] = {
    DispatchStatus.DISPATCHED: frozenset(
        {
            DispatchStatus.DISPATCHED,
            DispatchStatus.COMPLETED,
            DispatchStatus.FILTER_BLOCKED,
            DispatchStatus.IDLE_NO_RETURN,
            DispatchStatus.REFUSED,
        }
    ),
    DispatchStatus.COMPLETED: frozenset({DispatchStatus.COMPLETED}),
    DispatchStatus.FILTER_BLOCKED: frozenset({DispatchStatus.FILTER_BLOCKED}),
    DispatchStatus.IDLE_NO_RETURN: frozenset({DispatchStatus.IDLE_NO_RETURN}),
    DispatchStatus.REFUSED: frozenset({DispatchStatus.REFUSED}),
}


def derive_claim_axes(status: ClaimStatus | str) -> ClaimAxes:
    """Derive `(research_state, evidence_state)` mechanically from canonical `ClaimStatus`."""
    st = ClaimStatus(status)
    if st == ClaimStatus.REPRODUCED:
        return ClaimAxes(ResearchState.CONFIRMED, EvidenceState.REPRODUCED)
    if st == ClaimStatus.FALSIFIED:
        return ClaimAxes(ResearchState.REJECTED_DURING_RESEARCH, EvidenceState.FALSIFIED)
    if st in (ClaimStatus.REJECTED_REPRO, ClaimStatus.DUPLICATE_ROOT_CAUSE):
        return ClaimAxes(ResearchState.REJECTED_DURING_RESEARCH, EvidenceState.UNVERIFIED)
    return ClaimAxes(ResearchState.CANDIDATE, EvidenceState.UNVERIFIED)


def assert_valid_run_transition(current: str, target: str, *, run_id: str = "") -> RunStatus:
    cur, dst = RunStatus(current), RunStatus(target)
    if dst not in ALLOWED_RUN_TRANSITIONS[cur]:
        raise InvalidTransitionError("run.status", cur.value, dst.value, entity_id=run_id)
    return dst


def assert_valid_phase_transition(current: str, target: str, *, run_id: str = "") -> CampaignPhase:
    cur, dst = CampaignPhase(current), CampaignPhase(target)
    if dst not in ALLOWED_PHASE_TRANSITIONS[cur]:
        raise InvalidTransitionError(
            "campaign_phase",
            cur.value,
            dst.value,
            entity_id=run_id,
            reason="campaign_phase is monotonic (`hunt -> remediate -> full`); rewind is forbidden",
        )
    return dst


def assert_valid_task_transition(current: str, target: str, *, task_id: str = "") -> TaskStatus:
    cur, dst = TaskStatus(current), TaskStatus(target)
    if dst not in ALLOWED_TASK_TRANSITIONS[cur]:
        raise InvalidTransitionError(
            "task.status",
            cur.value,
            dst.value,
            entity_id=task_id,
            reason="terminal task states (`done`, `dry`) cannot be overwritten",
        )
    return dst


def assert_valid_claim_transition(
    current: str,
    target: str,
    *,
    claim_id: str = "",
    allow_reopen_blocked: bool = False,
) -> ClaimStatus:
    cur, dst = ClaimStatus(current), ClaimStatus(target)
    if allow_reopen_blocked and cur == ClaimStatus.BLOCKED and dst == ClaimStatus.SURVIVED_FALSIFY:
        return dst
    if dst not in ALLOWED_CLAIM_TRANSITIONS[cur]:
        raise InvalidTransitionError(
            "claim.status",
            cur.value,
            dst.value,
            entity_id=claim_id,
            reason=f"claim cannot transition from {cur.value!r} to {dst.value!r}",
        )
    return dst


def assert_valid_primitive_transition(current: str, target: str, *, primitive_id: str = "") -> PrimitiveStatus:
    cur, dst = PrimitiveStatus(current), PrimitiveStatus(target)
    if dst not in ALLOWED_PRIMITIVE_TRANSITIONS[cur]:
        raise InvalidTransitionError("primitive.status", cur.value, dst.value, entity_id=primitive_id)
    return dst


def assert_valid_anomaly_transition(current: str, target: str, *, anomaly_id: str = "") -> AnomalyStatus:
    cur, dst = AnomalyStatus(current), AnomalyStatus(target)
    if dst not in ALLOWED_ANOMALY_TRANSITIONS[cur]:
        raise InvalidTransitionError("anomaly.status", cur.value, dst.value, entity_id=anomaly_id)
    return dst


def assert_valid_door_transition(current: str, target: str, *, door_id: str = "") -> DoorStatus:
    cur, dst = DoorStatus(current), DoorStatus(target)
    if dst not in ALLOWED_DOOR_TRANSITIONS[cur]:
        raise InvalidTransitionError("parked_door.status", cur.value, dst.value, entity_id=door_id)
    return dst
