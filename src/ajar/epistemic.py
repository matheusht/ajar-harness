"""Ring-1 mechanical epistemic guard (provenance, sink closure, rut, pre-prove)."""

from __future__ import annotations

import re
from collections import deque
from typing import Any, Iterable

from ajar.agent import AgentHooks, SpanTracker
from ajar.cli import Candidate

_SPAN_REF_RE = re.compile(r"(?<![:/\w])([A-Za-z0-9_./-]+\.[A-Za-z0-9_]+):(\d+)(?:-(\d+))?\b")
_CONCRETE_ORACLE_RE = re.compile(
    r"\b(asan|addresssanitizer|ubsan|undefinedbehaviorsanitizer|msan|memorysanitizer|"
    r"tsan|threadsanitizer|lsan|leaksanitizer|sigsegv|segfault|sigabrt|sigbus|sigfpe|"
    r"buffer-overflow|use-after-free|double-free|out-of-bounds|oob|uaf|assert|"
    r"assertionerror|panic|revert|unreachable|invariant|solvency|overflow|underflow|"
    r"differential|mismatch|race)\b",
    re.IGNORECASE,
)
_PLACEHOLDERS = frozenset({
    "",
    "todo",
    "tbd",
    "n/a",
    "na",
    "none",
    "null",
    "true",
    "false",
    "pass",
    "...",
    "placeholder",
})
_SEARCH_TOOLS = frozenset({"search", "grep", "ripgrep", "rg"})
_READ_TOOLS = frozenset({"read_file", "read", "view_file"})
_EXEC_TOOLS = frozenset({"exec_cmd", "bash", "shell", "run_cmd"})


def _parse_span_ref(ref: Any) -> tuple[str, int] | None:
    if isinstance(ref, tuple) and len(ref) >= 2:
        return (str(ref[0]), max(1, int(ref[1])))
    match = _SPAN_REF_RE.search(str(ref).strip())
    if not match:
        return None
    return (match.group(1), max(1, int(match.group(2))))


def _span_observed(spans: SpanTracker, path: str, line_no: int) -> bool:
    if spans.contains(path, line_no):
        return True
    trimmed = path.lstrip("./")
    return trimmed != path and spans.contains(trimmed, line_no)


def _fingerprint_step(action_or_text: str) -> frozenset[tuple[str, int]]:
    buckets = {
        (m.group(1).lstrip("./"), int(m.group(2)) // 32)
        for m in _SPAN_REF_RE.finditer(action_or_text)
    }
    if buckets:
        return frozenset(buckets)
    cleaned = action_or_text.strip()
    return frozenset({(cleaned[:48], 0)}) if cleaned else frozenset()


def _window_jaccard(window: deque[frozenset[tuple[str, int]]]) -> float:
    items = [entry for entry in window if entry]
    if len(items) < 2:
        return 0.0
    score = 0.0
    pairs = 0
    for idx in range(len(items)):
        for jdx in range(idx + 1, len(items)):
            union = items[idx] | items[jdx]
            score += len(items[idx] & items[jdx]) / len(union)
            pairs += 1
    return score / pairs if pairs else 0.0


def _valid_repro_cmd(cmd: str) -> bool:
    cleaned = cmd.strip()
    lowered = cleaned.lower()
    if len(cleaned) < 3 or lowered in _PLACEHOLDERS:
        return False
    if lowered.startswith(("todo", "tbd", "placeholder", "echo ")):
        return False
    return not bool(re.search(r"<[A-Za-z0-9_-]+>", cleaned))


class EpistemicGuard(AgentHooks):
    """Mechanical 4-inflection epistemic guard with zero pre-bash blocking."""

    def __init__(self, tracker: SpanTracker | None = None) -> None:
        self.tracker = tracker if tracker is not None else SpanTracker()
        self._closed_sinks: set[str] = set()
        self._window: deque[frozenset[tuple[str, int]]] = deque(maxlen=5)
        self._recent_steps: deque[frozenset[tuple[str, int]]] = deque(maxlen=6)

    def check_sink_counterfactual(
        self,
        sink: str,
        guard_callees: Iterable[str] = (),
        guard_defs: dict[str, tuple[str, int, int]] | None = None,
        tracker: SpanTracker | None = None,
        **_: Any,
    ) -> str | None:
        if sink in self._closed_sinks:
            return None
        active = tracker if tracker is not None else self.tracker
        unopened: list[str] = []
        defs = guard_defs or {}
        for callee in guard_callees:
            target_ref: Any = defs.get(callee, callee)
            parsed = _parse_span_ref(target_ref)
            if parsed and not _span_observed(active, parsed[0], parsed[1]):
                unopened.append(f"{parsed[0]}:{parsed[1]}")
        if not unopened:
            return None
        self._closed_sinks.add(sink)
        return f"Sink '{sink}' closed with unopened guard callees: {', '.join(unopened)}"

    def check_rut(self, action: str = "", **_: Any) -> bool:
        fp = _fingerprint_step(action)
        prior_matches = sum(1 for item in self._recent_steps if item == fp and bool(fp))
        self._recent_steps.append(fp)
        self._window.append(fp)
        if prior_matches >= 1 and len(self._recent_steps) >= 6:
            self._window.clear()
            return True
        if len(self._window) < 5:
            return False
        empty_hits = sum(1 for item in self._window if not item)
        jaccard = _window_jaccard(self._window)
        if empty_hits < 4 and jaccard < 0.80:
            return False
        self._window.clear()
        return True

    def check_pre_prove(
        self,
        tracker: SpanTracker | None = None,
        entrypoint: Any = None,
        guard: Iterable[Any] = (),
        cand: Candidate | None = None,
        **_kwargs: Any,
    ) -> bool:
        active = tracker if tracker is not None else self.tracker
        if cand is not None:
            ok, _reason = self.on_pre_prove(cand, active)
            return ok
        ep = _parse_span_ref(entrypoint)
        if ep is None or not _span_observed(active, ep[0], ep[1]):
            return False
        for g_item in guard:
            gp = _parse_span_ref(g_item)
            if gp is not None and not _span_observed(active, gp[0], gp[1]):
                return False
        return True

    def on_post_tool(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        tool_output: str,
        spans: SpanTracker,
    ) -> str | None:
        del spans
        name = tool_name.lower()
        if name in _EXEC_TOOLS:
            self._window.clear()
            self._recent_steps.clear()
            return None
        if name not in _SEARCH_TOOLS and name not in _READ_TOOLS:
            return None
        path_hint = str(tool_args.get("path", ""))
        key = f"{path_hint}:1" if path_hint and ":" not in tool_output else tool_output[:512]
        if self.check_rut(key):
            return "Rut detected (high span overlap without exec_cmd). Pivot seam or run exec_cmd."
        return None

    def on_slice_close(
        self,
        summary: str,
        relay_capsule: Iterable[str] = (),
        spans: SpanTracker | None = None,
    ) -> str | None:
        callees = relay_capsule if isinstance(relay_capsule, (list, tuple, set)) else ()
        return self.check_sink_counterfactual(summary, callees, tracker=spans)

    def on_pre_prove(self, candidate: Candidate, spans: SpanTracker) -> tuple[bool, str]:
        errors: list[str] = []
        parsed = _parse_span_ref(candidate.entry_span)
        if parsed is None or not _span_observed(spans, parsed[0], parsed[1]):
            errors.append("entry_span not observed")
        if not _valid_repro_cmd(candidate.repro_cmd):
            errors.append("repro_cmd missing or placeholder")
        if not _CONCRETE_ORACLE_RE.search(candidate.failure_oracle.strip()):
            errors.append("failure_oracle lacks concrete sanitizer/assertion/invariant")
        if errors:
            return False, "Pre-prove failed: " + " | ".join(errors)
        return True, ""


EpistemicGate = EpistemicGuard
