"""Zero-touch 6h–48h 8-worker stigmergic campaign sentinel (D3 45m pivot, D4 65%/70% relay, <35% COGS guard)."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ajar.reality import build_reality_model, record_falsified_hypothesis
from ajar.schemas import ajar_dir, append_jsonl, read_jsonl, utc_now

PIVOT_WINDOW_SECONDS = 45 * 60
WARN_CONTEXT_RATIO = 0.65
RELAY_CONTEXT_RATIO = 0.70


@dataclass
class PhysicalSignal:
    coverage_edges: int = 0
    disk_cans: int = 0
    proved_count: int = 0

    def delta_from(self, baseline: "PhysicalSignal") -> tuple[int, int, int]:
        return (
            self.coverage_edges - baseline.coverage_edges,
            self.disk_cans - baseline.disk_cans,
            self.proved_count - baseline.proved_count,
        )


@dataclass
class WorkerSlot:
    slot_id: int
    focus_seam: str
    profile: str = "upstream"
    generation: int = 1
    started_at_s: float = field(default_factory=time.monotonic)
    baseline_signal: PhysicalSignal = field(default_factory=PhysicalSignal)
    context_ratio: float = 0.0
    active_leads: list[str] = field(default_factory=list)
    dead_ends: list[str] = field(default_factory=list)

    def notes_path(self, repo: Path) -> Path:
        slot_dir = ajar_dir(repo) / "workers" / f"slot-{self.slot_id}"
        slot_dir.mkdir(parents=True, exist_ok=True)
        return slot_dir / "notes.md"


class CampaignSentinel:
    """Lightweight stigmergic coordinator keeping up to 8 workers productive on 6h–48h campaigns."""

    def __init__(
        self,
        repo: Path,
        seams: list[str],
        max_workers: int = 8,
        budget_usd: float = 100.0,
        cogs_cap_ratio: float = 0.35,
        pivot_window_s: float = PIVOT_WINDOW_SECONDS,
    ) -> None:
        if not (1 <= max_workers <= 8):
            raise ValueError("max_workers must be between 1 and 8")
        self.repo = repo.resolve()
        self.queue = list(seams) or ["default_crown_jewel_seam"]
        self.max_workers = max_workers
        self.budget_usd = budget_usd
        self.cogs_cap_ratio = cogs_cap_ratio
        self.pivot_window_s = pivot_window_s
        self.spend_usd = 0.0
        self.slots: dict[int, WorkerSlot] = {}

        if not (ajar_dir(self.repo) / "REALITY.md").exists():
            build_reality_model(self.repo)

    @property
    def max_cogs_usd(self) -> float:
        return round(self.budget_usd * self.cogs_cap_ratio, 4)

    def can_dispatch(self) -> bool:
        return self.spend_usd < self.max_cogs_usd

    def snapshot_repo_signal(self, coverage_edges: int = 0) -> PhysicalSignal:
        root = ajar_dir(self.repo)
        prims = read_jsonl(root / "primitives.jsonl")
        findings = read_jsonl(root / "findings.jsonl")
        chains = read_jsonl(root / "chains.jsonl")
        proved = sum(1 for f in findings if f.get("status") == "PROVED") + sum(
            1 for c in chains if c.get("status") == "PROVED"
        )
        return PhysicalSignal(
            coverage_edges=coverage_edges,
            disk_cans=len(prims),
            proved_count=proved,
        )

    def bootstrap_slots(self) -> list[WorkerSlot]:
        sig = self.snapshot_repo_signal()
        count = min(self.max_workers, max(1, len(self.queue)))
        for slot_id in range(count):
            if not self.can_dispatch():
                break
            seam = self.queue.pop(0)
            self.queue.append(seam)
            self.slots[slot_id] = WorkerSlot(slot_id=slot_id, focus_seam=seam, baseline_signal=sig)
        return list(self.slots.values())

    def flush_worker_notes(self, slot: WorkerSlot) -> Path:
        """D4: Persist structured handoff state before context compaction hits 70%."""
        path = slot.notes_path(self.repo)
        lines = [
            f"# Worker Slot {slot.slot_id} Relay Notes (Generation {slot.generation})",
            f"- **Focus Seam:** `{slot.focus_seam}` (`{slot.profile}`)",
            f"- **Context Ratio:** `{slot.context_ratio:.2f}`",
            f"- **Updated:** `{utc_now()}`",
            "",
            "## Active CAN/WISH Leads",
            *([f"- {item}" for item in slot.active_leads] or ["- None yet"]),
            "",
            "## Falsified Dead Ends",
            *([f"- {item}" for item in slot.dead_ends] or ["- None recorded"]),
            "",
        ]
        path.write_text("\n".join(lines), encoding="utf-8")
        return path

    def evaluate_slot(
        self,
        slot_id: int,
        now_s: float,
        coverage_edges: int = 0,
        context_ratio: float = 0.0,
        step_cost_usd: float = 0.0,
    ) -> str:
        """Evaluate D3 (45m physical-signal pivot), D4 (65%/70% relay), and <35% COGS cap."""
        self.spend_usd = round(self.spend_usd + max(0.0, step_cost_usd), 6)
        slot = self.slots[slot_id]
        slot.context_ratio = context_ratio
        current_sig = self.snapshot_repo_signal(coverage_edges=coverage_edges)

        if not self.can_dispatch():
            self.flush_worker_notes(slot)
            self._log_event("COGS_CAP_HALT", slot, current_sig)
            return "HALT_COGS_CAP"

        if context_ratio >= WARN_CONTEXT_RATIO:
            self.flush_worker_notes(slot)
        if context_ratio >= RELAY_CONTEXT_RATIO:
            slot.generation += 1
            slot.context_ratio = 0.0
            slot.started_at_s = now_s
            slot.baseline_signal = current_sig
            self._log_event("COMPACTION_RELAY", slot, current_sig)
            return "RELAYED_FRESH_WORKER"

        elapsed = now_s - slot.started_at_s
        delta = current_sig.delta_from(slot.baseline_signal)
        if elapsed >= self.pivot_window_s and all(v <= 0 for v in delta):
            stalled_seam = slot.focus_seam
            slot.dead_ends.append(f"45m zero physical delta on `{stalled_seam}`")
            record_falsified_hypothesis(
                self.repo, f"Slot {slot.slot_id} pivoted off `{stalled_seam}` after 45m with `(0 edges, 0 CANs, 0 PROVED)`."
            )
            next_seam = self.queue.pop(0)
            self.queue.append(next_seam)
            slot.focus_seam = next_seam
            slot.generation += 1
            slot.started_at_s = now_s
            slot.baseline_signal = current_sig
            self.flush_worker_notes(slot)
            self._log_event("PIVOT_STALLED_SLOT", slot, current_sig)
            return "PIVOTED_NEW_SEAM"

        return "CONTINUE"

    def _log_event(self, event: str, slot: WorkerSlot, sig: PhysicalSignal) -> None:
        append_jsonl(
            ajar_dir(self.repo) / "campaign_events.jsonl",
            {
                "event": event,
                "slot_id": slot.slot_id,
                "focus_seam": slot.focus_seam,
                "generation": slot.generation,
                "spend_usd": self.spend_usd,
                "signal": asdict(sig),
                "ts": utc_now(),
            },
        )
