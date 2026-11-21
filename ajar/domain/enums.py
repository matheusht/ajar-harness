"""Canonical StrEnum definitions for all 18 Ajar state machines.

These enums are the single source of truth for SQL CHECK constraints, CLI choices,
MCP schemas, state-transition guards, and conformance contract checks.
"""

from __future__ import annotations

from enum import StrEnum


class TargetMode(StrEnum):
    SOURCE = "source"
    BINARY = "binary"
    LIVE = "live"


class WorkspaceMode(StrEnum):
    ENVELOPE = "envelope"
    IN_PLACE = "in_place"


class RunStatus(StrEnum):
    ACTIVE = "active"
    VERIFY_ONLY = "verify_only"
    FINISHED = "finished"
    BLOCKED = "blocked"


class CampaignPhase(StrEnum):
    HUNT = "hunt"
    REMEDIATE = "remediate"
    FULL = "full"


class StoppingCriterion(StrEnum):
    EXHAUSTIVE_HIGH = "exhaustive-high"
    FIRST_VERIFIED_HIGH = "first-verified-high"
    CROWN_JEWEL = "crown-jewel"


class PricingMode(StrEnum):
    COMMERCIAL_CODE = "commercial_code"
    CUSTOM_OR_BOUNTY = "custom_or_bounty"
    UNCAPPED_RESEARCH = "uncapped_research"


class Priority(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class TaskKind(StrEnum):
    MAP = "map"
    INVESTIGATE = "investigate"
    BRIDGE = "bridge"
    FALSIFY = "falsify"
    REPRODUCE = "reproduce"
    INSTRUMENT = "instrument"
    CHAIN = "chain"
    PATCH = "patch"
    ESCALATE = "escalate"


class TaskDirection(StrEnum):
    OUTSIDE_IN = "outside_in"
    INSIDE_OUT = "inside_out"
    NATIVE_FFI = "native_ffi"
    PEER_SYMMETRY = "peer_symmetry"


class TaskStatus(StrEnum):
    OPEN = "open"
    LEASED = "leased"
    DONE = "done"
    DRY = "dry"
    CONDITIONAL_BLOCKED = "conditional_blocked"


class SkillMode(StrEnum):
    DOMAIN = "domain"
    ZERO_SKILL = "zero_skill"


class ClaimStatus(StrEnum):
    PROPOSED = "proposed"
    SURVIVED_FALSIFY = "survived_falsify"
    FALSIFIED = "falsified"
    NEEDS_INSTRUMENTATION = "needs_instrumentation"
    REPRODUCED = "reproduced"
    REJECTED_REPRO = "rejected_repro"
    DUPLICATE_ROOT_CAUSE = "duplicate_root_cause"
    BLOCKED = "blocked"
    CONFIG_GATED = "config_gated"


class ResearchState(StrEnum):
    CANDIDATE = "candidate"
    REJECTED_DURING_RESEARCH = "rejected_during_research"
    CONFIRMED = "confirmed"


class EvidenceState(StrEnum):
    UNVERIFIED = "unverified"
    FALSIFIED = "falsified"
    REPRODUCED = "reproduced"


class CustomerState(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    DISPUTED = "disputed"


class RemediationState(StrEnum):
    UNPATCHED = "unpatched"
    MICROPATCHED = "micropatched"
    VERIFIED_LOCAL = "verified_local"
    MAINTAINER_PATCHED = "maintainer_patched"


class EnvBlockerKind(StrEnum):
    MISSING_HARDWARE = "missing_hardware"
    EXTERNAL_SERVICE = "external_service"
    PRIVILEGED_KERNEL = "privileged_kernel"
    LICENSE_OR_KEY = "license_or_key"
    HOST_OS_MISMATCH = "host_os_mismatch"


class ReproOutcome(StrEnum):
    CONFIRMED = "confirmed"
    TARGET_NEGATIVE = "target_negative"
    PREFLIGHT_ERROR = "preflight_error"
    BUILD_OR_ENV_ERROR = "build_or_env_error"


class UbDivergenceClass(StrEnum):
    NONE = ""
    CONSISTENT = "consistent"
    DEBUG_ASSERT_ONLY = "debug_assert_only"
    TRAP_DOS_ONLY = "trap_dos_only"
    SILENT_WRAP_ESCALATED = "silent_wrap_escalated"
    RELEASE_CONTROL_FAILED = "release_control_failed"


class PrimitiveRole(StrEnum):
    CAPABILITY = "capability"
    TRUST_GADGET = "trust_gadget"


class PrimitiveStatus(StrEnum):
    ACTIVE = "active"
    CHAINED = "chained"
    DRY = "dry"


class AnomalyStatus(StrEnum):
    UNEXPLAINED = "unexplained"
    BENIGN_EXPLAINED = "benign_explained"
    CONSUMED_BY_CLAIM = "consumed_by_claim"
    CONSUMED_BY_CHAIN = "consumed_by_chain"


class DoorDirection(StrEnum):
    SINK_TO_SOURCE = "sink_to_source"
    SOURCE_TO_SINK = "source_to_sink"
    BIDIRECTIONAL = "bidirectional"


class DoorStatus(StrEnum):
    PARKED = "parked"
    BRIDGING = "bridging"
    READY = "ready"
    CHAINED = "chained"
    EXHAUSTED_LOCKED = "exhausted_locked"


class ImpactClass(StrEnum):
    RCE = "rce"
    SANDBOX_ESCAPE = "sandbox_escape"
    FUND_DRAIN = "fund_drain"
    AUTH_BYPASS = "auth_bypass"
    STATE_TAKEOVER = "state_takeover"
    KEY_EXFIL = "key_exfil"
    ARBITRARY_WRITE = "arbitrary_write"
    MEM_CORRUPT = "mem_corrupt"


class JewelStatus(StrEnum):
    LOCKED = "locked"
    REACHED = "reached"
    EXHAUSTED_UNREACHABLE = "exhausted_unreachable"


class RealismTier(StrEnum):
    CROWN_JEWEL = "crown_jewel"
    HIGH_IMPACT = "high_impact"
    STEPPING_STONE = "stepping_stone"


class HookStatus(StrEnum):
    ACTIVE = "active"
    CONSUMED = "consumed"
    EXPIRED = "expired"


class HookCode(StrEnum):
    H1_GUARD_SYMMETRY = "H1_GUARD_SYMMETRY"
    H2_DIRTY_UNWIND = "H2_DIRTY_UNWIND"
    H3_INTRINSIC_AND_PEER_SINK = "H3_INTRINSIC_AND_PEER_SINK"
    H4_TYPED_STATE_BRIDGE = "H4_TYPED_STATE_BRIDGE"
    H5_POST_CONFIRM_ESCALATION = "H5_POST_CONFIRM_ESCALATION"
    H6_RELEASE_UB_DIFF = "H6_RELEASE_UB_DIFF"
    H7_TRUST_METADATA_AND_FSM_ORDER = "H7_TRUST_METADATA_AND_FSM_ORDER"
    H8_PROJECTION_UNDER_CONSTRAINT = "H8_PROJECTION_UNDER_CONSTRAINT"


class AssumptionStatus(StrEnum):
    ASSUMED = "assumed"
    VERIFIED_HOLDS = "verified_holds"
    VIOLATED = "violated"


class SwarmStage(StrEnum):
    INVESTIGATE = "investigate"
    BRIDGE = "bridge"
    FALSIFY = "falsify"
    REPRODUCE = "reproduce"
    CHAIN = "chain"
    PORTFOLIO = "portfolio"


class WireProfile(StrEnum):
    DIRECT = "direct"
    SWARM_PATCH_FIRST = "swarm_patch_first"
    REGRESSION_TDD = "regression_tdd"


class DispatchStatus(StrEnum):
    DISPATCHED = "dispatched"
    COMPLETED = "completed"
    FILTER_BLOCKED = "filter_blocked"
    IDLE_NO_RETURN = "idle_no_return"
    REFUSED = "refused"


class StopVerdict(StrEnum):
    APPROVE = "approve"
    BLOCK = "block"
    STALLED_RELEASE = "stalled_release"


class SteerScope(StrEnum):
    GLOBAL = "global"
    SUBSYSTEM = "subsystem"
    PATH = "path"


class TouchKind(StrEnum):
    SCOPE_AUTHORITY = "scope_authority"
    ENV_RESCUE = "env_rescue"
    RESEARCH_STEERING = "research_steering"
    POC_REPAIR = "poc_repair"
    REVIEW_SIGNOFF = "review_signoff"


class SpendPhase(StrEnum):
    EXPLORE = "explore"
    VERIFY = "verify"
