"""AJAR Ring-0 workspace tools, span tracking, hook protocol, and worker loop."""

from __future__ import annotations

import inspect
import json
import os
import shutil
import signal
import subprocess
from pathlib import Path
from typing import Any, NamedTuple, Protocol, runtime_checkable

from ajar.cli import Candidate, Span, dataclass_from_dict, scrub_subprocess_env
from ajar.llm import ROLE_MODEL_MAP, BudgetExhaustedError, CostMeter, LLMClient, ToolCall

SOFT_CAPSULE_RATIO = 0.65
HARD_RECYCLE_RATIO = 0.70
TOKEN_WINDOW_GUARD_RATIO = 0.92


def _normalize_rel_path(raw_path: str) -> str:
    cleaned = raw_path.replace("\\", "/").strip()
    while cleaned.startswith("./"):
        cleaned = cleaned[2:]
    cleaned = cleaned.lstrip("/")
    return cleaned or "."


class ExecResult(NamedTuple):
    returncode: int
    output: str

    @property
    def rc(self) -> int:
        return self.returncode

    @property
    def stdout(self) -> str:
        return self.output


class SpanTracker:
    """Tracks viewed (rel_path, start, end) 1-indexed line intervals."""

    def __init__(self) -> None:
        self._intervals: dict[str, list[tuple[int, int]]] = {}

    def record(self, rel_path: str, start: int, end: int) -> Span:
        norm = _normalize_rel_path(rel_path)
        lo = max(1, min(int(start), int(end)))
        hi = max(lo, int(start), int(end))
        merged: list[tuple[int, int]] = []
        placed = False
        for cur_lo, cur_hi in self._intervals.get(norm, []):
            if cur_hi + 1 < lo:
                merged.append((cur_lo, cur_hi))
            elif hi + 1 < cur_lo:
                if not placed:
                    merged.append((lo, hi))
                    placed = True
                merged.append((cur_lo, cur_hi))
            else:
                lo = min(lo, cur_lo)
                hi = max(hi, cur_hi)
        if not placed:
            merged.append((lo, hi))
        self._intervals[norm] = merged
        return Span(path=norm, start=lo, end=hi)

    def contains(self, rel_path: str, line: int) -> bool:
        norm = _normalize_rel_path(rel_path)
        target_line = int(line)
        for lo, hi in self._intervals.get(norm, []):
            if lo <= target_line <= hi:
                return True
        return False

    def is_observed(self, path: str, start: int = 1, end: int | None = None) -> bool:
        norm = _normalize_rel_path(path)
        lo = max(1, int(start))
        hi = max(lo, int(end if end is not None else lo))
        for cur_lo, cur_hi in self._intervals.get(norm, []):
            if cur_lo <= lo and hi <= cur_hi:
                return True
        return False

    def files(self) -> list[str]:
        return sorted(self._intervals.keys())


class WorkspaceTools:
    """Sandboxed file and process tools with optional write-allowlist jail."""

    def __init__(
        self,
        root: Path,
        spans: SpanTracker | None = None,
        write_allowlist: set[str] | None = None,
    ) -> None:
        self.root = Path(root).resolve()
        self.spans = spans if isinstance(spans, SpanTracker) else SpanTracker()
        self.write_allowlist = (
            {_normalize_rel_path(p) for p in write_allowlist}
            if write_allowlist is not None
            else None
        )

    def _resolve_safe(self, raw_path: str) -> tuple[Path, str]:
        candidate = (self.root / raw_path).resolve()
        if candidate != self.root and self.root not in candidate.parents:
            raise PermissionError(f"Path escapes workspace root: {raw_path}")
        rel = "." if candidate == self.root else candidate.relative_to(self.root).as_posix()
        return candidate, rel

    def _enforce_write_allowed(self, rel: str) -> None:
        if self.write_allowlist is not None and rel not in self.write_allowlist:
            raise PermissionError(f"Write denied by allowlist for path: {rel}")

    def read_file(self, path: str, start: int = 1, end: int = 200) -> str:
        target, rel = self._resolve_safe(path)
        if not target.is_file():
            raise FileNotFoundError(f"File not found: {rel}")
        lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
        if not lines:
            self.spans.record(rel, 1, 1)
            return ""
        lo = max(1, min(int(start), len(lines)))
        hi = max(lo, min(int(end), len(lines)))
        self.spans.record(rel, lo, hi)
        rendered = [f"{idx}: {lines[idx - 1]}" for idx in range(lo, hi + 1)]
        return "\n".join(rendered)

    def search(self, pattern: str, path: str = ".") -> str:
        _, rel = self._resolve_safe(path)
        rg_bin = shutil.which("rg")
        if rg_bin is not None:
            cmd = [rg_bin, "-n", "--no-heading", "--color", "never", "--", pattern, rel]
        else:
            cmd = ["grep", "-rn", "--", pattern, rel]
        proc = subprocess.run(
            cmd,
            cwd=str(self.root),
            env=scrub_subprocess_env(),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
            timeout=30,
            check=False,
        )
        out_lines = proc.stdout.splitlines()[:200]
        return "\n".join(out_lines)

    def write_file(self, path: str, content: str) -> str:
        target, rel = self._resolve_safe(path)
        self._enforce_write_allowed(rel)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        if rel.endswith(".sh"):
            os.chmod(target, 0o755)
        return f"wrote {rel}"

    def edit_file(self, path: str, old: str, new: str | None = None) -> str:
        if new is None:
            return self.write_file(path, old)
        target, rel = self._resolve_safe(path)
        self._enforce_write_allowed(rel)
        if not target.exists():
            if old != "":
                raise FileNotFoundError(f"Cannot match non-empty old text in missing file: {rel}")
            return self.write_file(path, new)
        current = target.read_text(encoding="utf-8", errors="replace")
        if old == "":
            updated = new
        else:
            occurrences = current.count(old)
            if occurrences == 0:
                raise ValueError(f"Target snippet not found in {rel}")
            if occurrences > 1:
                raise ValueError(f"Target snippet matches {occurrences} locations in {rel}")
            updated = current.replace(old, new, 1)
        target.write_text(updated, encoding="utf-8")
        if rel.endswith(".sh"):
            os.chmod(target, 0o755)
        return f"updated {rel}"

    def exec_cmd(self, cmd: str, timeout: int = 60) -> ExecResult:
        proc = subprocess.Popen(
            ["/bin/sh", "-c", cmd],
            cwd=str(self.root),
            env=scrub_subprocess_env(),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
            start_new_session=True,
        )
        try:
            out, _ = proc.communicate(timeout=max(1, int(timeout)))
            rc = proc.returncode if proc.returncode is not None else -1
            return ExecResult(rc, out or "")
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except OSError:
                pass
            partial, _ = proc.communicate()
            return ExecResult(124, f"{partial or ''}\n[TIMEOUT after {timeout}s]")
        finally:
            if proc.poll() is None:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except OSError:
                    pass
                proc.wait()

    def tool_schemas(self, allow_candidates: bool = True) -> list[dict[str, Any]]:
        schemas: list[dict[str, Any]] = [
            {
                "name": "read_file",
                "description": "Read numbered lines from a workspace file.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "start": {"type": "integer"},
                        "end": {"type": "integer"},
                    },
                    "required": ["path"],
                },
            },
            {
                "name": "search",
                "description": "Search workspace files with regex pattern.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "pattern": {"type": "string"},
                        "path": {"type": "string"},
                    },
                    "required": ["pattern"],
                },
            },
            {
                "name": "exec_cmd",
                "description": "Execute a shell command inside workspace root.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "cmd": {"type": "string"},
                        "timeout": {"type": "integer"},
                    },
                    "required": ["cmd"],
                },
            },
        ]
        if self.write_allowlist is None or len(self.write_allowlist) > 0:
            schemas.append(
                {
                    "name": "edit_file",
                    "description": "Edit or create a permitted workspace file.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "old": {"type": "string"},
                            "new": {"type": "string"},
                        },
                        "required": ["path", "old", "new"],
                    },
                }
            )
        if allow_candidates:
            schemas.append(
                {
                    "name": "submit_candidate",
                    "description": "Submit a vulnerability candidate for C3 verification.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "title": {"type": "string"},
                            "severity": {"type": "string"},
                            "entry_span": {"type": "string"},
                            "sink_symbol": {"type": "string"},
                            "repro_cmd": {"type": "string"},
                            "failure_oracle": {"type": "string"},
                            "patch_diff": {"type": "string"},
                            "root_cause": {"type": "string"},
                            "impact": {"type": "string"},
                        },
                        "required": ["id", "title", "severity"],
                    },
                }
            )
        return schemas


@runtime_checkable
class AgentHooks(Protocol):
    def on_post_tool(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        tool_output: str,
        spans: SpanTracker,
    ) -> str | None: ...

    def on_slice_close(
        self,
        summary: str,
        relay_capsule: Any,
        spans: SpanTracker,
    ) -> Any: ...

    def on_pre_prove(
        self,
        candidate: Candidate,
        spans: SpanTracker,
    ) -> tuple[bool, str] | str | None: ...


class NullHooks:
    def on_post_tool(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        tool_output: str,
        spans: SpanTracker,
    ) -> str | None:
        return None

    def on_slice_close(self, summary: str, relay_capsule: Any, spans: SpanTracker) -> None:
        return None

    def on_pre_prove(self, candidate: Candidate, spans: SpanTracker) -> tuple[bool, str]:
        return True, ""


def estimate_tokens(messages: list[dict[str, Any]], system_prompt: str = "") -> int:
    total_chars = len(system_prompt) + len(json.dumps(messages, ensure_ascii=True))
    return max(1, total_chars // 4)


def _extract_capsule(text: str, spans: SpanTracker, fallback: str) -> str:
    if "RELAY_CAPSULE:" in text:
        return text.split("RELAY_CAPSULE:", 1)[1].strip()
    viewed = ", ".join(spans.files()[:12]) or "none"
    base = text.strip()[:400] or fallback[:400]
    return f"Viewed files: {viewed}\nNotes: {base}"


def _recycled_messages(task_prompt: str, capsule: str) -> list[dict[str, Any]]:
    return [
        {"role": "user", "content": task_prompt},
        {
            "role": "user",
            "content": f"[CONTEXT RECYCLED - RELAY CAPSULE]\n{capsule}",
        },
    ]


async def _maybe_await(val: Any) -> Any:
    if inspect.isawaitable(val):
        return await val
    return val


def _run_tool_call(tools: WorkspaceTools, tc: ToolCall) -> str:
    args = tc.arguments
    try:
        if tc.name == "read_file":
            return tools.read_file(
                str(args["path"]),
                int(args.get("start", 1)),
                int(args.get("end", 200)),
            )
        if tc.name == "search":
            return tools.search(str(args["pattern"]), str(args.get("path", ".")))
        if tc.name == "edit_file":
            return tools.edit_file(
                str(args["path"]),
                str(args.get("old", "")),
                str(args.get("new", "")),
            )
        if tc.name == "exec_cmd":
            res = tools.exec_cmd(str(args["cmd"]), int(args.get("timeout", 60)))
            return f"exit_code={res.returncode}\n{res.output}"
        return f"ERROR: unknown tool '{tc.name}'"
    except Exception as exc:
        return f"ERROR: {type(exc).__name__}: {exc}"


async def run_worker_loop(
    llm: LLMClient,
    tools: WorkspaceTools,
    system_prompt: str,
    task_prompt: str,
    *,
    role: str = "auditor",
    hooks: AgentHooks | None = None,
    cost_meter: CostMeter | None = None,
    max_steps: int = 32,
    context_limit: int | None = None,
) -> dict[str, Any]:
    active_hooks: AgentHooks = hooks if hooks is not None else NullHooks()
    spec = ROLE_MODEL_MAP.get(role, ROLE_MODEL_MAP["auditor"])
    limit = max(256, int(context_limit or spec.context_limit))
    messages: list[dict[str, Any]] = [{"role": "user", "content": task_prompt}]
    schemas = tools.tool_schemas()
    candidates: list[Candidate] = []
    relay_capsule = f"Viewed files: none\nTask: {task_prompt[:240]}"
    soft_flushed = False
    soft_flushes = 0
    recycles = 0
    window_guard_hits = 0
    final_text = ""
    status = "max_steps"
    step = 0

    for step in range(1, max_steps + 1):  # noqa: B007
        if cost_meter is not None and cost_meter.drain_triggered:
            status = "budget_drain"
            break

        used = estimate_tokens(messages, system_prompt)
        if used >= int(limit * TOKEN_WINDOW_GUARD_RATIO):
            window_guard_hits += 1
            recycles += 1
            await _maybe_await(
                active_hooks.on_slice_close("window_guard_92pct", [], tools.spans)
            )
            messages = _recycled_messages(task_prompt, relay_capsule)
            soft_flushed = False
        elif used >= int(limit * HARD_RECYCLE_RATIO):
            recycles += 1
            await _maybe_await(
                active_hooks.on_slice_close("hard_recycle_70pct", [], tools.spans)
            )
            messages = _recycled_messages(task_prompt, relay_capsule)
            soft_flushed = False
        elif used >= int(limit * SOFT_CAPSULE_RATIO) and not soft_flushed:
            soft_flushed = True
            soft_flushes += 1
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "Context reached 65%. Emit RELAY_CAPSULE: with verified spans, "
                        "eliminated paths, and active hypotheses."
                    ),
                }
            )

        used_now = estimate_tokens(messages, system_prompt)
        remaining_window = max(128, int(limit * TOKEN_WINDOW_GUARD_RATIO) - used_now)
        try:
            resp = await llm.complete(
                messages,
                role=role,
                tools=schemas,
                system=system_prompt,
                max_tokens=min(4096, remaining_window),
            )
        except BudgetExhaustedError:
            status = "budget_drain"
            break

        final_text = resp.content or final_text
        if resp.content:
            relay_capsule = _extract_capsule(resp.content, tools.spans, relay_capsule)

        if not resp.tool_calls:
            status = "completed"
            messages.append({"role": "assistant", "content": resp.content})
            break

        messages.append(
            {
                "role": "assistant",
                "content": resp.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
                    }
                    for tc in resp.tool_calls
                ],
            }
        )

        tail_notes: list[str] = []
        max_tool_chars = max(256, int(limit * 0.25) * 4)
        for tc in resp.tool_calls:
            if tc.name in ("submit_candidate", "prove_candidate"):
                raw_cand = dict(tc.arguments)
                raw_cand.setdefault("id", f"CAND-{len(candidates) + 1}")
                raw_cand.setdefault("title", "Untitled candidate")
                raw_cand.setdefault("severity", "medium")
                cand = dataclass_from_dict(Candidate, raw_cand)
                raw_verdict = await _maybe_await(active_hooks.on_pre_prove(cand, tools.spans))
                if isinstance(raw_verdict, tuple):
                    allowed, reason = raw_verdict
                elif isinstance(raw_verdict, str):
                    allowed, reason = (False, raw_verdict)
                else:
                    allowed, reason = (True, "")
                if allowed:
                    candidates.append(cand)
                    tool_out = f"ACCEPTED: {cand.id}"
                else:
                    tool_out = f"REJECTED_PRE_PROVE: {reason}"
            else:
                tool_out = _run_tool_call(tools, tc)

            if len(tool_out) > max_tool_chars:
                window_guard_hits += 1
                tool_out = tool_out[:max_tool_chars] + "\n...[truncated by 92% token-window guard]"

            hook_note = await _maybe_await(
                active_hooks.on_post_tool(tc.name, tc.arguments, tool_out, tools.spans)
            )
            if isinstance(hook_note, str) and hook_note.strip():
                tail_notes.append(hook_note.strip())

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": tool_out,
                }
            )

        if tail_notes:
            messages.append({"role": "user", "content": "\n".join(tail_notes)})

    await _maybe_await(active_hooks.on_slice_close("slice_exit", [], tools.spans))
    return {
        "status": status,
        "final_text": final_text,
        "candidates": candidates,
        "relay_capsule": relay_capsule,
        "steps": step,
        "soft_flushes": soft_flushes,
        "recycles": recycles,
        "window_guard_hits": window_guard_hits,
        "viewed_files": tools.spans.files(),
        "messages": messages,
    }
