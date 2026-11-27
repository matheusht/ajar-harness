"""Ring-1 Erlang one_for_one async swarm, streaming C3 verifier pool, CONWIP, & resume."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ajar.agent import NullHooks, SpanTracker, WorkspaceTools, run_worker_loop
from ajar.autobuild import probe_build_script, run_build_doctor, synthesize_build_recipe
from ajar.chain_weaver import join_effects_and_wishes, weave_candidates
from ajar.cli import (
    AblationConfig,
    BuildRecipe,
    Candidate,
    RunConfig,
    Verdict,
    ajar_dir,
    append_jsonl,
    read_jsonl,
)
from ajar.epistemic import EpistemicGuard
from ajar.llm import CostMeter, LLMClient, StdlibLLMClient, has_configured_api_key
from ajar.repomap import build_repomap_and_reality, index_repo
from ajar.verify import verify_candidate
from ajar.whiteboard import Section, StigmergicWhiteboard

WAVE_ROLES: tuple[str, ...] = (
    "build_cartographer",
    "surface_scout",
    "deep_auditor",
    "bounty_resolver",
    "downstream_prover",
)

OVERFLOW_ROLES: tuple[str, ...] = (
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
DEFAULT_VERIFIER_CONCURRENCY: int = 2
DEFAULT_CONWIP_LIMIT: int = 2
WB_PROMPT_MAX_CHARS: int = 8000


def _build_worker_roles(workers: int) -> list[str]:
    count = max(1, int(workers))
    if count <= len(WAVE_ROLES):
        return list(WAVE_ROLES[:count])
    roles = list(WAVE_ROLES)
    for extra_idx in range(count - len(WAVE_ROLES)):
        roles.append(OVERFLOW_ROLES[extra_idx % len(OVERFLOW_ROLES)])
    return roles


def deal_disjoint_slices(
    spans: Sequence[str],
    workers: int,
    claimed: set[str] | None = None,
    max_per_worker: int = 6,
) -> list[list[str]]:
    """Deal unique, unclaimed spans round-robin into disjoint per-worker slices."""
    n_workers = max(1, int(workers))
    skip = claimed or set()
    buckets: list[list[str]] = [[] for _ in range(n_workers)]
    seen: set[str] = set()
    dealt = 0
    for span in spans:
        if not span or span in seen or span in skip:
            continue
        seen.add(span)
        slot = dealt % n_workers
        if max_per_worker <= 0 or len(buckets[slot]) < max_per_worker:
            buckets[slot].append(span)
        dealt += 1
    return buckets


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
    """Async swarm with Erlang one_for_one supervision, streaming C3 pool, & CONWIP."""

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
        worker_max_steps: int = 24,
        verifier_concurrency: int = DEFAULT_VERIFIER_CONCURRENCY,
        conwip_limit: int = DEFAULT_CONWIP_LIMIT,
        wave_stagger_s: float = 0.0,
        resume: bool | None = None,
    ) -> None:
        if isinstance(root, RunConfig):
            self.config = root
        else:
            ablation = AblationConfig(disable_swarm=disable_swarm)
            self.config = RunConfig(
                repo=Path(root),
                workers=workers if workers is not None else 4,
                budget_usd=budget_usd if budget_usd is not None else 50.0,
                resume=bool(resume),
                ablation=ablation,
            )
        self.repo = self.config.repo.resolve()
        self.disable_swarm = bool(disable_swarm or self.config.ablation.disable_swarm)
        req_workers = workers if workers is not None else self.config.workers
        self.workers = 1 if self.disable_swarm else max(1, int(req_workers))
        self.worker_max_steps: int = max(1, int(worker_max_steps))
        self.verifier_concurrency: int = max(2, int(verifier_concurrency))
        self.conwip_limit: int = max(1, int(conwip_limit))
        self.wave_stagger_s: float = max(0.0, float(wave_stagger_s))
        self.resume: bool = bool(self.config.resume if resume is None else resume)

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
        self.build_verified: bool = False
        self.build_doctor_invoked: bool = False
        self.slots_executed: int = 0
        self.slots_succeeded: int = 0
        self.worker_errors: list[dict[str, Any]] = []
        self.reality_md_text: str = ""
        self.whiteboard: StigmergicWhiteboard | None = None
        self.indexed_spans: list[str] = []
        self.worker_slices: list[list[str]] = []
        self.coverage_spans: set[str] = set()
        self.resumed_claimed_targets: set[str] = set()
        self.resumed_events: int = 0
        self.candidate_queue: list[Candidate] = []
        self.c3_proved: list[Verdict] = []
        self.verified_before_drain: int = 0
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
        self._verify_queue: asyncio.Queue[tuple[str, Candidate] | None] | None = None
        self._verifier_tasks: list[asyncio.Task[None]] = []
        self._hunter_conwip: dict[str, asyncio.Semaphore] = {}
        self._seen_candidate_ids: set[str] = set()

    def should_drain(self, spent: float | None = None, budget: float | None = None) -> bool:
        s_val = self.effective_spent_usd() if spent is None else float(spent)
        b_val = self.budget_usd if budget is None else float(budget)
        return should_drain(s_val, b_val)

    def effective_spent_usd(self) -> float:
        llm_spent = float(getattr(self.llm, "spent_usd", 0.0)) if self.llm is not None else 0.0
        return max(self.spent_usd, self.cost_meter.spent_usd, llm_spent)

    def _hydrate_resume_state(self) -> None:
        if self.whiteboard is not None:
            wb_stats = self.whiteboard.stats()
            self.resumed_events = int(wb_stats.get("total_events", 0))
            for claim in self.whiteboard.active_claims():
                target = str(claim.get("target", ""))
                if target:
                    self.resumed_claimed_targets.add(target)
                    self.coverage_spans.add(target)
            for rec in self.whiteboard.get_records(Section.DEAD_END):
                target = str(rec.get("target", ""))
                if target:
                    self.coverage_spans.add(target)
        for row in read_jsonl(ajar_dir(self.repo) / "verdicts.jsonl"):
            cid = str(row.get("candidate_id", ""))
            if cid:
                self._seen_candidate_ids.add(cid)

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
            self.build_verified = False
            self.build_doctor_invoked = False
            self.recipe = synthesize_build_recipe(self.repo, profile=self.config.profile)
            if self.recipe.build_system == "static":
                build_ok, probe_tail = False, "No Tier-0 build recipe detected"
            else:
                build_ok, probe_tail = probe_build_script(self.repo, self.recipe)
            if build_ok:
                bsh = self.repo / ".ajar" / "build.sh"
                digest = (
                    hashlib.sha256(bsh.read_bytes()).hexdigest()
                    if bsh.is_file() and not bsh.is_symlink()
                    else self.recipe.build_script_sha256
                )
                self.recipe = replace(
                    self.recipe,
                    build_script="bash .ajar/build.sh",
                    build_script_sha256=digest,
                    static_only=False,
                    verified=True,
                    last_error="",
                )
            else:
                self.recipe = replace(self.recipe, verified=False, last_error=probe_tail)
            if self.llm is not None and (not build_ok or self.recipe.build_system == "static"):
                self.build_doctor_invoked = True
                self.recipe = await run_build_doctor(self.repo, self.recipe, self.llm)
            self.build_verified = bool(self.recipe.verified)
        if not ab.disable_whiteboard:
            self.whiteboard = StigmergicWhiteboard(self.repo)
        if self.resume:
            self._hydrate_resume_state()
        self.worker_slices = deal_disjoint_slices(
            self.indexed_spans,
            self.workers,
            claimed=self.resumed_claimed_targets,
        )
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
            f"- Build verified: `{self.build_verified}` (doctor_invoked=`{self.build_doctor_invoked}`)\n"
            f"- Budget used: `${spent:.2f} / ${self.budget_usd:.2f}` (`{pct:.1%}`)\n"
            f"- Exploration frozen (92% drain): `{self.exploration_frozen}`\n"
            f"- Strategy mode: `{self.strategy_mode}`\n"
            f"- Physical signal: coverage=`{cov}`, whiteboard=`{effs}`, c3=`{c3}`\n"
            f"- Stagnation pivots: `{self.pivot_count}` | Relays: `{self.relay_count}`\n"
            f"- Worker errors isolated: `{len(self.worker_errors)}` | "
            f"Streaming verifiers: `{self.verifier_concurrency}`\n"
        )
        _atomic_write_text(status_path, body)
        self._last_heartbeat_mono = now
        return status_path

    def _ensure_verifier_pool(self) -> None:
        if self._verify_queue is None:
            self._verify_queue = asyncio.Queue()
        if not self._verifier_tasks:
            for _ in range(self.verifier_concurrency):
                self._verifier_tasks.append(asyncio.create_task(self._verifier_worker()))

    async def _submit_for_verification(self, hunter_key: str, cand: Candidate) -> None:
        if cand.id and cand.id in self._seen_candidate_ids:
            return
        if cand.id:
            self._seen_candidate_ids.add(cand.id)
        self._ensure_verifier_pool()
        assert self._verify_queue is not None
        sem = self._hunter_conwip.setdefault(hunter_key, asyncio.Semaphore(self.conwip_limit))
        await sem.acquire()
        await self._verify_queue.put((hunter_key, cand))

    async def _verifier_worker(self) -> None:
        assert self._verify_queue is not None
        while True:
            item = await self._verify_queue.get()
            if item is None:
                self._verify_queue.task_done()
                return
            hunter_key, cand = item
            try:
                append_jsonl(ajar_dir(self.repo) / "candidates.jsonl", cand)
                verdict = await asyncio.to_thread(
                    verify_candidate, self.repo, cand, self.recipe, self.llm, 3
                )
                append_jsonl(ajar_dir(self.repo) / "verdicts.jsonl", verdict)
                if verdict.status == "VERIFIED" and verdict.truth_level == "C3":
                    self.c3_proved.append(verdict)
                if not self.exploration_frozen:
                    self.verified_before_drain += 1
            except Exception as exc:
                self.worker_errors.append(
                    {
                        "worker": f"verifier:{hunter_key}",
                        "role": "verifier",
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
            finally:
                sem = self._hunter_conwip.get(hunter_key)
                if sem is not None:
                    sem.release()
                self._verify_queue.task_done()

    async def _shutdown_verifier_pool(self) -> None:
        if self._verify_queue is None or not self._verifier_tasks:
            return
        await self._verify_queue.join()
        for _ in self._verifier_tasks:
            await self._verify_queue.put(None)
        await asyncio.gather(*self._verifier_tasks, return_exceptions=True)
        self._verifier_tasks.clear()
        self._verify_queue = None

    async def _run_drain_proving(self) -> None:
        self.exploration_frozen = True
        ab = self.config.ablation
        if not ab.disable_chain_weaver and self.whiteboard is not None and self.llm is not None:
            woven = await weave_candidates(self.repo, self.whiteboard, self.llm)
            self.candidate_queue.extend(woven)
        pending = list(self.candidate_queue)
        self.candidate_queue.clear()
        for cand in pending:
            await self._submit_for_verification("drain", cand)
        await self._shutdown_verifier_pool()

    async def _execute_worker_slot(self, worker_id: int, role: str) -> None:
        if self.should_drain():
            self.exploration_frozen = True
            return
        self.slots_executed += 1
        spans_slice = (
            self.worker_slices[worker_id]
            if worker_id < len(self.worker_slices)
            else self.indexed_spans[worker_id :: max(1, self.workers)][:6]
        )
        for sp in spans_slice:
            self.coverage_spans.add(sp)
        if self.whiteboard is not None and spans_slice:
            self.whiteboard.try_claim(spans_slice[0], worker_id=f"W{worker_id}")
        if self.llm is None:
            return

        tracker = SpanTracker()
        tools = WorkspaceTools(self.repo, spans=tracker)
        hooks = NullHooks() if self.config.ablation.disable_epistemic else EpistemicGuard(tracker)
        wb_text = self.whiteboard.read_snapshot()[1] if self.whiteboard is not None else ""
        sys_prompt = (
            f"AJAR Worker W{worker_id} | Role: {role}\n\n"
            f"{self.reality_md_text[:4000]}\n\n{wb_text[:WB_PROMPT_MAX_CHARS]}"
        )
        task_prompt = (
            f"Audit assigned slice spans: {', '.join(spans_slice) or 'repository entrypoints'}. "
            "Verify real boundaries and submit concrete C3 candidates."
        )
        llm_tier = ROLE_TO_LLM_TIER.get(role, "auditor")
        hunter_key = f"W{worker_id}"

        async def _on_cand(cand: Candidate) -> None:
            await self._submit_for_verification(hunter_key, cand)

        outcome = await run_worker_loop(
            self.llm,
            tools,
            sys_prompt,
            task_prompt,
            role=llm_tier,
            hooks=hooks,
            cost_meter=self.cost_meter,
            max_steps=self.worker_max_steps,
            on_candidate=_on_cand,
        )
        for cand in outcome.get("candidates", []):
            await self._submit_for_verification(hunter_key, cand)
        for vf in outcome.get("viewed_files", []):
            self.coverage_spans.add(vf)
        self.check_worker_context(worker_id, int(outcome.get("steps", 1)) * 512)
        self.check_stagnation()
        self.write_status_heartbeat(force=False)

    async def _supervised_worker_slot(
        self,
        sem: asyncio.Semaphore,
        slot_idx: int,
        role_name: str,
        wave_idx: int,
    ) -> None:
        if self.wave_stagger_s > 0.0 and wave_idx > 0:
            await asyncio.sleep(self.wave_stagger_s * wave_idx)
        async with sem:
            try:
                await self._execute_worker_slot(slot_idx, role_name)
                self.slots_succeeded += 1
            except Exception as exc:
                self.worker_errors.append(
                    {
                        "worker": slot_idx,
                        "role": role_name,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )

    async def run(self) -> dict[str, Any]:
        self.slots_executed = 0
        self.slots_succeeded = 0
        self.worker_errors.clear()
        self.verified_before_drain = 0
        await self.bootstrap()
        if not self.should_drain():
            sem = asyncio.Semaphore(self.workers)
            roles = _build_worker_roles(self.workers)
            wave_size = max(1, len(WAVE_ROLES))
            tasks: list[asyncio.Task[None]] = []
            for slot_idx, role_name in enumerate(roles):
                if self.should_drain():
                    self.exploration_frozen = True
                    break
                wave_idx = slot_idx // wave_size
                tasks.append(
                    asyncio.create_task(
                        self._supervised_worker_slot(sem, slot_idx, role_name, wave_idx)
                    )
                )
            if tasks:
                await asyncio.gather(*tasks)

        await self._run_drain_proving()
        status_path = self.write_status_heartbeat(force=True)
        return {
            "workers": self.workers,
            "slots_executed": self.slots_executed,
            "slots_succeeded": self.slots_succeeded,
            "worker_errors": list(self.worker_errors),
            "verifier_concurrency": self.verifier_concurrency,
            "verified_before_drain": self.verified_before_drain,
            "resumed_events": self.resumed_events,
            "build_verified": self.build_verified,
            "build_doctor_invoked": self.build_doctor_invoked,
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
