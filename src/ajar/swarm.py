"""Ring-1 live 8-worker async swarm orchestrator, 45m pivot, 65%/70% relay, & 92% drain guard."""

from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ajar.agent import NullHooks, SpanTracker, WorkspaceTools, run_worker_loop
from ajar.autobuild import run_build_doctor, synthesize_build_recipe
from ajar.chain_weaver import join_effects_and_wishes, weave_candidates
from ajar.cli import (
    AblationConfig,
    BuildRecipe,
    Candidate,
    RunConfig,
    Verdict,
    ajar_dir,
    append_jsonl,
)
from ajar.epistemic import EpistemicGuard
from ajar.llm import CostMeter, LLMClient, StdlibLLMClient, has_configured_api_key
from ajar.repomap import build_repomap_and_reality, index_repo
from ajar.verify import verify_candidate
from ajar.whiteboard import StigmergicWhiteboard

WAVE_ROLES: tuple[str, ...] = (
    "build_cartographer",
    "surface_scout",
    "deep_auditor",
    "bounty_resolver",
    "downstream_prover",
)

ROLE_TO_LLM_TIER: dict[str, str] = {
    "build_cartographer": "scout",
    "surface_scout": "scout",
    "deep_auditor": "auditor",
    "bounty_resolver": "auditor",
    "downstream_prover": "auditor",
}

STAGNATION_WINDOW_SEC: float = 45.0 * 60.0
HEARTBEAT_INTERVAL_SEC: float = 30.0 * 60.0
SOFT_CONTEXT_RATIO: float = 0.65
HARD_CONTEXT_RATIO: float = 0.70
DRAIN_THRESHOLD: float = 0.92


def should_drain(spent_usd: float, budget_usd: float) -> bool:
    if budget_usd <= 0.0:
        return True
    return (spent_usd / budget_usd) >= DRAIN_THRESHOLD


def _atomic_write_text(target: Path, content: str) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.parent / f".{target.name}.{os.getpid()}.tmp"
    with tmp.open("w", encoding="utf-8") as fh:
        fh.write(content)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, target)
    return target


class LiveSwarm:
    """Unified async 1..8 worker orchestrator with stigmergic coordination and C3 drain reserve."""

    DRAIN_THRESHOLD = DRAIN_THRESHOLD

    def __init__(
        self,
        root: RunConfig | Path | str,
        llm: LLMClient | None = None,
        *,
        workers: int | None = None,
        budget_usd: float | None = None,
        spent_usd: float = 0.0,
        disable_swarm: bool = False,
    ) -> None:
        if isinstance(root, RunConfig):
            self.config = root
        else:
            ablation = AblationConfig(disable_swarm=disable_swarm)
            self.config = RunConfig(
                repo=Path(root),
                workers=workers if workers is not None else 4,
                budget_usd=budget_usd if budget_usd is not None else 50.0,
                ablation=ablation,
            )
        self.repo = self.config.repo.resolve()
        self.disable_swarm = bool(disable_swarm or self.config.ablation.disable_swarm)
        req_workers = workers if workers is not None else self.config.workers
        self.workers = 1 if self.disable_swarm else max(1, min(8, int(req_workers)))
        self.budget_usd = float(budget_usd if budget_usd is not None else self.config.budget_usd)
        self.spent_usd = float(spent_usd)
        self.cost_meter = CostMeter(self.budget_usd)
        if self.spent_usd > 0.0:
            self.cost_meter.settle(0.0, self.spent_usd, "initial")
        if llm is not None:
            self.llm: LLMClient | None = llm
        elif has_configured_api_key():
            self.llm = StdlibLLMClient(cost_meter=self.cost_meter)
        else:
            self.llm = None

        self.recipe: BuildRecipe = BuildRecipe(profile=self.config.profile)
        self.reality_md_text: str = ""
        self.whiteboard: StigmergicWhiteboard | None = None
        self.indexed_spans: list[str] = []
        self.coverage_spans: set[str] = set()
        self.candidate_queue: list[Candidate] = []
        self.c3_proved: list[Verdict] = []
        self.worker_tokens: dict[int, int] = {}
        self.worker_notes: dict[int, str] = {}
        self.exploration_frozen: bool = False
        self.pivot_count: int = 0
        self.relay_count: int = 0
        self.strategy_mode: str = "audit"
        self._start_mono = time.monotonic()
        self._last_progress_mono = self._start_mono
        self._last_heartbeat_mono = 0.0
        self._last_signal: tuple[int, int, int] = (0, 0, 0)

    def should_drain(self, spent: float | None = None, budget: float | None = None) -> bool:
        s_val = self.effective_spent_usd() if spent is None else float(spent)
        b_val = self.budget_usd if budget is None else float(budget)
        return should_drain(s_val, b_val)

    def effective_spent_usd(self) -> float:
        llm_spent = float(getattr(self.llm, "spent_usd", 0.0)) if self.llm is not None else 0.0
        return max(self.spent_usd, self.cost_meter.committed_usd, llm_spent)

    async def bootstrap(self) -> None:
        (ajar_dir(self.repo) / "workers").mkdir(parents=True, exist_ok=True)
        ab = self.config.ablation
        if not ab.disable_repomap:
            r_path = build_repomap_and_reality(self.repo, profiles=(self.config.profile,))
            self.reality_md_text = r_path.read_text(encoding="utf-8", errors="replace")
            f_map = index_repo(self.repo).get("files", {})
            for rel, meta in sorted(f_map.items()):
                for sym in meta.get("symbols", []):
                    self.indexed_spans.append(f"{rel}:{sym['line']}")
        if not ab.disable_autobuild:
            self.recipe = synthesize_build_recipe(self.repo, profile=self.config.profile)
            if self.llm is not None and not (self.repo / ".ajar" / "build.sh").is_file():
                self.recipe = await run_build_doctor(self.repo, self.recipe, self.llm)
        if not ab.disable_whiteboard:
            self.whiteboard = StigmergicWhiteboard(self.repo)
        self._last_signal = self.physical_signal()
        self.write_status_heartbeat(force=True)

    def _whiteboard_effect_count(self) -> int:
        if self.whiteboard is None:
            return 0
        stats = self.whiteboard.stats()
        return int(stats.get("total_events", 0)) + len(join_effects_and_wishes(self.whiteboard))

    def physical_signal(self) -> tuple[int, int, int]:
        return (
            len(self.coverage_spans),
            self._whiteboard_effect_count(),
            len(self.c3_proved),
        )

    def check_stagnation(self, now_mono: float | None = None) -> bool:
        now = time.monotonic() if now_mono is None else now_mono
        sig = self.physical_signal()
        if sig != self._last_signal:
            self._last_signal = sig
            self._last_progress_mono = now
            return False
        if (now - self._last_progress_mono) < STAGNATION_WINDOW_SEC:
            return False
        self.pivot_count += 1
        self.strategy_mode = "microfuzz" if self.strategy_mode == "audit" else "audit"
        self.indexed_spans = list(reversed(self.indexed_spans))
        self._last_progress_mono = now
        self.write_status_heartbeat(force=True, now_mono=now)
        return True

    def check_worker_context(
        self,
        worker_id: int,
        used_tokens: int,
        max_tokens: int = 128_000,
        summary: str = "",
    ) -> str:
        limit = max(1, max_tokens)
        self.worker_tokens[worker_id] = used_tokens
        ratio = used_tokens / limit
        if ratio < SOFT_CONTEXT_RATIO:
            return "ok"
        notes_path = ajar_dir(self.repo) / "workers" / f"W{worker_id}" / "notes.md"
        mode = "HARD_RELAY" if ratio >= HARD_CONTEXT_RATIO else "SOFT_CAPSULE"
        capsule = (
            f"# Worker W{worker_id} {mode}\n\n"
            f"- Context ratio: `{ratio:.2%}` (`{used_tokens}/{limit}`)\n"
            f"- Strategy: `{self.strategy_mode}`\n"
            f"- Covered spans: `{len(self.coverage_spans)}`\n"
            f"- Handoff notes: {summary or 'Continue from uncovered Crown-Jewel sinks.'}\n"
        )
        _atomic_write_text(notes_path, capsule)
        self.worker_notes[worker_id] = capsule
        if ratio >= HARD_CONTEXT_RATIO:
            self.relay_count += 1
            self.worker_tokens[worker_id] = max(64, len(capsule) // 4)
            return "hard_relay"
        return "soft_capsule"

    def write_status_heartbeat(self, force: bool = False, now_mono: float | None = None) -> Path:
        now = time.monotonic() if now_mono is None else now_mono
        status_path = ajar_dir(self.repo) / "STATUS.md"
        if (
            not force
            and self._last_heartbeat_mono > 0.0
            and (now - self._last_heartbeat_mono) < HEARTBEAT_INTERVAL_SEC
        ):
            return status_path
        cov, effs, c3 = self.physical_signal()
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        spent = self.effective_spent_usd()
        pct = (spent / self.budget_usd) if self.budget_usd > 0.0 else 1.0
        body = (
            "# AJAR Swarm Status\n\n"
            f"- Updated: `{stamp}`\n"
            f"- Workers: `{self.workers}` (swarm_disabled=`{self.disable_swarm}`)\n"
            f"- Budget used: `${spent:.2f} / ${self.budget_usd:.2f}` (`{pct:.1%}`)\n"
            f"- Exploration frozen (92% drain): `{self.exploration_frozen}`\n"
            f"- Strategy mode: `{self.strategy_mode}`\n"
            f"- Physical signal: coverage=`{cov}`, whiteboard=`{effs}`, c3=`{c3}`\n"
            f"- Stagnation pivots: `{self.pivot_count}` | Relays: `{self.relay_count}`\n"
        )
        _atomic_write_text(status_path, body)
        self._last_heartbeat_mono = now
        return status_path

    async def _run_drain_proving(self) -> None:
        self.exploration_frozen = True
        ab = self.config.ablation
        if not ab.disable_chain_weaver and self.whiteboard is not None and self.llm is not None:
            woven = await weave_candidates(self.repo, self.whiteboard, self.llm)
            self.candidate_queue.extend(woven)
        pending = list(self.candidate_queue)
        self.candidate_queue.clear()
        for cand in pending:
            append_jsonl(ajar_dir(self.repo) / "candidates.jsonl", cand)
            verdict = verify_candidate(self.repo, cand, self.recipe, llm=self.llm, runs=3)
            append_jsonl(ajar_dir(self.repo) / "verdicts.jsonl", verdict)
            if verdict.status == "VERIFIED" and verdict.truth_level == "C3":
                self.c3_proved.append(verdict)

    async def _execute_worker_slot(self, worker_id: int, role: str) -> None:
        if self.should_drain():
            self.exploration_frozen = True
            return
        spans_slice = self.indexed_spans[worker_id :: max(1, self.workers)][:6]
        for sp in spans_slice:
            self.coverage_spans.add(sp)
        if self.llm is None:
            return

        tracker = SpanTracker()
        tools = WorkspaceTools(self.repo, spans=tracker)
        hooks = NullHooks() if self.config.ablation.disable_epistemic else EpistemicGuard(tracker)
        wb_text = self.whiteboard.read_snapshot()[1] if self.whiteboard is not None else ""
        sys_prompt = (
            f"AJAR Worker W{worker_id} | Role: {role}\n\n"
            f"{self.reality_md_text[:4000]}\n\n{wb_text[:3000]}"
        )
        task_prompt = (
            f"Audit assigned slice spans: {', '.join(spans_slice) or 'repository entrypoints'}. "
            "Verify real boundaries and submit concrete C3 candidates."
        )
        llm_tier = ROLE_TO_LLM_TIER.get(role, "auditor")
        outcome = await run_worker_loop(
            self.llm,
            tools,
            sys_prompt,
            task_prompt,
            role=llm_tier,
            hooks=hooks,
            cost_meter=self.cost_meter,
            max_steps=8,
        )
        for cand in outcome.get("candidates", []):
            self.candidate_queue.append(cand)
        for vf in outcome.get("viewed_files", []):
            self.coverage_spans.add(vf)
        self.check_worker_context(worker_id, int(outcome.get("steps", 1)) * 512)
        self.check_stagnation()
        self.write_status_heartbeat(force=False)

    async def run(self) -> dict[str, Any]:
        await self.bootstrap()
        if not self.should_drain():
            sem = asyncio.Semaphore(self.workers)

            async def _slot_task(idx: int, role_name: str) -> None:
                async with sem:
                    await self._execute_worker_slot(idx % self.workers, role_name)

            roles = WAVE_ROLES[: max(self.workers, len(WAVE_ROLES))]
            async with asyncio.TaskGroup() as tg:
                for idx, role_name in enumerate(roles):
                    if self.should_drain():
                        self.exploration_frozen = True
                        break
                    tg.create_task(_slot_task(idx, role_name))

        await self._run_drain_proving()
        status_path = self.write_status_heartbeat(force=True)
        return {
            "workers": self.workers,
            "c3_proved": [v.candidate_id for v in self.c3_proved],
            "physical_signal": self.physical_signal(),
            "pivots": self.pivot_count,
            "relays": self.relay_count,
            "exploration_frozen": self.exploration_frozen,
            "status_path": str(status_path),
            "summary_json": json.dumps({"signal": self.physical_signal()}),
        }


async def run_swarm(config: RunConfig, llm: LLMClient | None = None) -> dict[str, Any]:
    runner = LiveSwarm(config, llm=llm)
    return await runner.run()
