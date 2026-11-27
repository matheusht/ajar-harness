"""AJAR Ring-0 LLM protocol, model routing, reservation cost meter, and stdlib HTTP client."""

from __future__ import annotations

import asyncio
import email.utils
import functools
import json
import os
import random
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol, runtime_checkable

DRAIN_RESERVE_RATIO = 0.92
HARD_CEILING_RATIO = 0.99
DEFAULT_HTTP_CONCURRENCY = 64
LONG_PREFIX_CACHE_CHARS = 1024


class BudgetExhaustedError(RuntimeError):
    """Raised when CostMeter denies a reservation above the allowed budget band."""


@dataclass(frozen=True)
class ModelSpec:
    model_id: str
    family: str
    input_usd_1m: float
    output_usd_1m: float
    context_limit: int = 200_000
    cached_input_usd_1m: float | None = None

    def estimate_cost(
        self,
        input_tokens: int,
        output_tokens: int,
        cached_input_tokens: int = 0,
    ) -> float:
        total_in = max(0, int(input_tokens))
        cached = max(0, min(int(cached_input_tokens), total_in))
        uncached = total_in - cached
        cached_rate = (
            self.cached_input_usd_1m
            if self.cached_input_usd_1m is not None
            else (self.input_usd_1m * 0.1)
        )
        in_cost = (uncached * self.input_usd_1m) + (cached * cached_rate)
        out_cost = max(0, int(output_tokens)) * self.output_usd_1m
        return (in_cost + out_cost) / 1_000_000.0


GLM_FLASH_SPEC = ModelSpec("glm-5.3-flash", "zhipu-glm", 0.15, 0.50, 200_000)
GLM_PRO_SPEC = ModelSpec("glm-5.3", "zhipu-glm", 1.00, 4.00, 200_000)
CLAUDE_CRITIC_SPEC = ModelSpec("claude-sonnet-4-6", "anthropic-claude", 3.00, 15.00, 200_000)

ROLE_MODEL_MAP: dict[str, ModelSpec] = {
    "scout": GLM_FLASH_SPEC,
    "auditor": GLM_PRO_SPEC,
    "weaver": GLM_PRO_SPEC,
    "doctor": GLM_FLASH_SPEC,
    "critic": CLAUDE_CRITIC_SPEC,
}

MODEL_REGISTRY: dict[str, ModelSpec] = {
    s.model_id: s for s in (GLM_FLASH_SPEC, GLM_PRO_SPEC, CLAUDE_CRITIC_SPEC)
}

CRITIC_FALLBACK_SPECS: tuple[ModelSpec, ...] = (CLAUDE_CRITIC_SPEC, GLM_PRO_SPEC)


def _infer_model_family(model_id: str) -> str:
    low = model_id.lower().strip()
    if low in MODEL_REGISTRY:
        return MODEL_REGISTRY[low].family
    if "claude" in low or low.startswith("anthropic/"):
        return "anthropic-claude"
    if "glm" in low or "zhipu" in low or low.startswith("z-ai/"):
        return "zhipu-glm"
    if "gemini" in low or low.startswith("google/"):
        return "google-gemini"
    if "deepseek" in low:
        return "deepseek"
    if any(k in low for k in ("gpt-", "o1-", "o3-", "o4-", "openai/")):
        return "openai"
    return low.split("/", 1)[0] if "/" in low else "custom"


def resolve_role_model(
    role: str,
    override: ModelSpec | str | None = None,
    role_map: Mapping[str, ModelSpec] = ROLE_MODEL_MAP,
    hunter_model: ModelSpec | str | None = None,
) -> ModelSpec:
    if isinstance(override, ModelSpec):
        spec = override
    elif isinstance(override, str) and override:
        spec = MODEL_REGISTRY.get(
            override,
            ModelSpec(override, _infer_model_family(override), 1.0, 4.0),
        )
    else:
        if role not in role_map:
            raise KeyError(f"Unknown agent role: {role}")
        spec = role_map[role]

    if role == "critic":
        if isinstance(hunter_model, ModelSpec):
            hunter_family = hunter_model.family
        elif isinstance(hunter_model, str) and hunter_model:
            hunter_family = _infer_model_family(hunter_model)
        else:
            hunter_spec = role_map.get("auditor", ROLE_MODEL_MAP["auditor"])
            hunter_family = hunter_spec.family
        if spec.family == hunter_family:
            if override is None and role_map is ROLE_MODEL_MAP:
                for alt in CRITIC_FALLBACK_SPECS:
                    if alt.family != hunter_family:
                        return alt
            raise ValueError(
                f"Cross-family critic role must differ from hunter family "
                f"'{hunter_family}' (got '{spec.family}')"
            )
    return spec


class CostMeter:
    """Thread-safe reservation-aware budget meter with 92% drain and 99% hard ceiling."""

    def __init__(self, budget_usd: float) -> None:
        self.budget_usd = float(budget_usd)
        self.spent_usd = 0.0
        self.reserved_usd = 0.0
        self.by_model_usd: dict[str, float] = {}
        self._lock = threading.Lock()

    @property
    def committed_usd(self) -> float:
        with self._lock:
            return self.spent_usd + self.reserved_usd

    @property
    def hard_ceiling_usd(self) -> float:
        return max(0.0, self.budget_usd * HARD_CEILING_RATIO)

    @property
    def drain_triggered(self) -> bool:
        with self._lock:
            if self.budget_usd <= 0.0:
                return True
            return self.spent_usd >= (self.budget_usd * DRAIN_RESERVE_RATIO)

    def reserve(self, est_usd: float, allow_drain_reserve: bool = False) -> bool:
        est = max(0.0, float(est_usd))
        with self._lock:
            if self.budget_usd <= 0.0:
                return False
            drain_cap = self.budget_usd * DRAIN_RESERVE_RATIO
            hard_cap = self.budget_usd * HARD_CEILING_RATIO
            if not allow_drain_reserve and self.spent_usd >= drain_cap:
                return False
            committed = self.spent_usd + self.reserved_usd
            limit = hard_cap if allow_drain_reserve else drain_cap
            if committed + est > limit + 1e-12:
                return False
            self.reserved_usd += est
            return True

    def settle(self, est_usd: float, actual_usd: float, model_id: str) -> None:
        est = max(0.0, float(est_usd))
        act = max(0.0, float(actual_usd))
        with self._lock:
            self.reserved_usd = max(0.0, self.reserved_usd - est)
            self.spent_usd += act
            self.by_model_usd[model_id] = self.by_model_usd.get(model_id, 0.0) + act

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "budget_usd": self.budget_usd,
                "spent_usd": round(self.spent_usd, 6),
                "reserved_usd": round(self.reserved_usd, 6),
                "by_model_usd": dict(self.by_model_usd),
            }


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)

    def __getitem__(self, key: str) -> Any:
        return asdict(self)[key]


@dataclass
class LLMResponse:
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    model_id: str = ""
    cost_usd: float = 0.0
    raw: dict[str, Any] = field(default_factory=dict)
    cached_input_tokens: int = 0

    def __getitem__(self, key: str) -> Any:
        return asdict(self)[key]


@runtime_checkable
class LLMClient(Protocol):
    async def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        role: str = "auditor",
        model: ModelSpec | str | None = None,
        tools: list[dict[str, Any]] | None = None,
        system: str = "",
        max_tokens: int = 4096,
        temperature: float = 0.0,
        allow_drain_reserve: bool = False,
    ) -> LLMResponse: ...

    def complete_sync(
        self,
        messages: list[dict[str, Any]],
        *,
        role: str = "auditor",
        model: ModelSpec | str | None = None,
        tools: list[dict[str, Any]] | None = None,
        system: str = "",
        max_tokens: int = 4096,
        temperature: float = 0.0,
        allow_drain_reserve: bool = False,
    ) -> LLMResponse: ...


def has_configured_api_key() -> bool:
    for env_key in ("OPENROUTER_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        if os.environ.get(env_key, "").strip():
            return True
    return False


def _normalize_openai_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in tools:
        if item.get("type") == "function" and "function" in item:
            normalized.append(item)
        else:
            normalized.append(
                {
                    "type": "function",
                    "function": {
                        "name": item["name"],
                        "description": item.get("description", ""),
                        "parameters": item.get("parameters") or item.get("input_schema", {}),
                    },
                }
            )
    return normalized


def _parse_retry_after(raw: str | None) -> float | None:
    if not raw:
        return None
    cleaned = raw.strip()
    if not cleaned:
        return None
    try:
        return max(0.0, float(cleaned))
    except ValueError:
        pass
    try:
        dt = email.utils.parsedate_to_datetime(cleaned)
        return max(0.0, dt.timestamp() - time.time())
    except (TypeError, ValueError, OverflowError):
        return None


def _compute_retry_delay(
    attempt: int,
    base_backoff_s: float,
    retry_after: str | None = None,
) -> float:
    ra_sec = _parse_retry_after(retry_after)
    if ra_sec is not None:
        jitter_cap = min(0.25, max(0.01, base_backoff_s * 0.25))
        return float(ra_sec + random.uniform(0.0, jitter_cap))
    exp = max(0.0, float(base_backoff_s)) * float(1 << max(0, int(attempt)))
    return float(exp * (0.5 + 0.5 * random.random()))


def _with_prefix_cache_control(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    marked = False
    for msg in messages:
        content = msg.get("content")
        if (
            not marked
            and msg.get("role") == "user"
            and isinstance(content, str)
            and len(content) >= LONG_PREFIX_CACHE_CHARS
        ):
            copied = dict(msg)
            copied["content"] = [
                {
                    "type": "text",
                    "text": content,
                    "cache_control": {"type": "ephemeral"},
                }
            ]
            out.append(copied)
            marked = True
        else:
            out.append(msg)
    return out


class StdlibLLMClient:
    """OpenRouter, OpenAI, and Anthropic compatible stdlib HTTP client."""

    def __init__(
        self,
        cost_meter: CostMeter | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout_s: float = 90.0,
        max_retries: int = 4,
        base_backoff_s: float = 0.5,
        max_concurrency: int | None = None,
    ) -> None:
        self.cost_meter = cost_meter
        self.api_key = (
            api_key
            or os.environ.get("OPENROUTER_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
            or os.environ.get("ANTHROPIC_API_KEY")
            or ""
        )
        default_url = "https://openrouter.ai/api/v1/chat/completions"
        if not os.environ.get("OPENROUTER_API_KEY") and not os.environ.get("OPENAI_API_KEY"):
            if os.environ.get("ANTHROPIC_API_KEY"):
                default_url = "https://api.anthropic.com/v1/messages"
        self.base_url = base_url or os.environ.get("AJAR_LLM_BASE_URL") or default_url
        self.timeout_s = timeout_s
        self.max_retries = max_retries
        self.base_backoff_s = base_backoff_s
        env_conc = os.environ.get("AJAR_LLM_MAX_CONCURRENCY", "").strip()
        raw_conc = (
            max_concurrency
            if max_concurrency is not None
            else (int(env_conc) if env_conc.isdigit() else DEFAULT_HTTP_CONCURRENCY)
        )
        self.max_concurrency = max(1, int(raw_conc))
        self._http_executor: ThreadPoolExecutor | None = None
        self._exec_lock = threading.Lock()

    def _get_http_executor(self) -> ThreadPoolExecutor:
        if self._http_executor is None:
            with self._exec_lock:
                if self._http_executor is None:
                    self._http_executor = ThreadPoolExecutor(
                        max_workers=self.max_concurrency,
                        thread_name_prefix="ajar-http",
                    )
        return self._http_executor

    def _is_anthropic_native(self) -> bool:
        return "api.anthropic.com" in self.base_url or self.base_url.endswith("/v1/messages")

    def _build_http_payload(
        self,
        spec: ModelSpec,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        system: str,
        max_tokens: int,
        temperature: float,
    ) -> tuple[dict[str, str], bytes]:
        headers = {
            "Content-Type": "application/json",
            "anthropic-beta": "prompt-caching-2024-07-31",
            "X-Prompt-Cache": "ephemeral",
        }
        cached_msgs = _with_prefix_cache_control(messages)
        if self._is_anthropic_native():
            headers["x-api-key"] = self.api_key
            headers["anthropic-version"] = "2023-06-01"
            body: dict[str, Any] = {
                "model": spec.model_id,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": cached_msgs,
            }
            if system:
                body["system"] = [
                    {
                        "type": "text",
                        "text": system,
                        "cache_control": {"type": "ephemeral"},
                    }
                ]
            if tools:
                body["tools"] = [
                    {
                        "name": t.get("name") or t["function"]["name"],
                        "description": t.get("description") or t["function"].get("description", ""),
                        "input_schema": t.get("parameters")
                        or t.get("input_schema")
                        or t["function"].get("parameters", {}),
                    }
                    for t in tools
                ]
        else:
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            headers["HTTP-Referer"] = "https://ajar.local"
            headers["X-Title"] = "ajar-ring0"
            wire_msgs: list[dict[str, Any]] = []
            if system:
                wire_msgs.append(
                    {
                        "role": "system",
                        "content": [
                            {
                                "type": "text",
                                "text": system,
                                "cache_control": {"type": "ephemeral"},
                            }
                        ],
                    }
                )
            wire_msgs.extend(cached_msgs)
            body = {
                "model": spec.model_id,
                "messages": wire_msgs,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
            if tools:
                body["tools"] = _normalize_openai_tools(tools)
        return headers, json.dumps(body).encode("utf-8")

    def _parse_payload(self, data: dict[str, Any], spec: ModelSpec) -> LLMResponse:
        tool_calls: list[ToolCall] = []
        text_parts: list[str] = []
        cached_tok = 0
        if "choices" in data:
            msg = (data.get("choices") or [{}])[0].get("message") or {}
            if isinstance(msg.get("content"), str):
                text_parts.append(msg["content"])
            for idx, raw_tc in enumerate(msg.get("tool_calls") or []):
                fn = raw_tc.get("function") or {}
                raw_args = fn.get("arguments", "{}")
                try:
                    parsed_args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                except json.JSONDecodeError:
                    parsed_args = {}
                tool_calls.append(
                    ToolCall(
                        id=str(raw_tc.get("id") or f"tc_{idx}"),
                        name=str(fn.get("name") or ""),
                        arguments=parsed_args if isinstance(parsed_args, dict) else {},
                    )
                )
            usage = data.get("usage") or {}
            in_tok = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
            out_tok = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
            details = usage.get("prompt_tokens_details") or {}
            cached_tok = int(
                details.get("cached_tokens") or usage.get("cache_read_input_tokens") or 0
            )
        else:
            for idx, block in enumerate(data.get("content") or []):
                btype = block.get("type")
                if btype == "text":
                    text_parts.append(str(block.get("text") or ""))
                elif btype == "tool_use":
                    inp = block.get("input")
                    tool_calls.append(
                        ToolCall(
                            id=str(block.get("id") or f"tc_{idx}"),
                            name=str(block.get("name") or ""),
                            arguments=inp if isinstance(inp, dict) else {},
                        )
                    )
            usage = data.get("usage") or {}
            cached_tok = int(usage.get("cache_read_input_tokens") or 0)
            in_tok = int(usage.get("input_tokens") or 0) + cached_tok
            out_tok = int(usage.get("output_tokens") or 0)
        cost = spec.estimate_cost(in_tok, out_tok, cached_input_tokens=cached_tok)
        return LLMResponse(
            content="\n".join(p for p in text_parts if p),
            tool_calls=tool_calls,
            input_tokens=in_tok,
            output_tokens=out_tok,
            model_id=spec.model_id,
            cost_usd=cost,
            raw=data,
            cached_input_tokens=cached_tok,
        )

    def complete_sync(
        self,
        messages: list[dict[str, Any]],
        *,
        role: str = "auditor",
        model: ModelSpec | str | None = None,
        tools: list[dict[str, Any]] | None = None,
        system: str = "",
        max_tokens: int = 4096,
        temperature: float = 0.0,
        allow_drain_reserve: bool = False,
    ) -> LLMResponse:
        spec = resolve_role_model(role, model)
        headers, raw_body = self._build_http_payload(
            spec, messages, tools, system, max_tokens, temperature
        )
        est_in = max(1, len(raw_body) // 4)
        est_out = min(max(64, max_tokens // 8), 512)
        est_usd = spec.estimate_cost(est_in, est_out)
        if self.cost_meter is not None:
            if not self.cost_meter.reserve(est_usd, allow_drain_reserve=allow_drain_reserve):
                raise BudgetExhaustedError(f"Budget cap reached for role={role}")
        actual_usd = 0.0
        try:
            last_err: Exception | None = None
            for attempt in range(self.max_retries + 1):
                req = urllib.request.Request(
                    self.base_url, data=raw_body, headers=headers, method="POST"
                )
                retry_after: str | None = None
                try:
                    with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                        decoded = json.loads(resp.read().decode("utf-8"))
                    parsed = self._parse_payload(decoded, spec)
                    actual_usd = parsed.cost_usd
                    return parsed
                except urllib.error.HTTPError as exc:
                    last_err = exc
                    retryable = exc.code == 429 or (500 <= exc.code < 600)
                    if not retryable or attempt >= self.max_retries:
                        raise
                    if exc.headers is not None:
                        retry_after = exc.headers.get("Retry-After")
                except urllib.error.URLError as exc:
                    last_err = exc
                    if attempt >= self.max_retries:
                        raise
                time.sleep(_compute_retry_delay(attempt, self.base_backoff_s, retry_after))
            raise RuntimeError(f"LLM request failed: {last_err}")
        finally:
            if self.cost_meter is not None:
                self.cost_meter.settle(est_usd, actual_usd, spec.model_id)

    async def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        role: str = "auditor",
        model: ModelSpec | str | None = None,
        tools: list[dict[str, Any]] | None = None,
        system: str = "",
        max_tokens: int = 4096,
        temperature: float = 0.0,
        allow_drain_reserve: bool = False,
    ) -> LLMResponse:
        loop = asyncio.get_running_loop()
        fn = functools.partial(
            self.complete_sync,
            messages,
            role=role,
            model=model,
            tools=tools,
            system=system,
            max_tokens=max_tokens,
            temperature=temperature,
            allow_drain_reserve=allow_drain_reserve,
        )
        return await loop.run_in_executor(self._get_http_executor(), fn)


class MockLLMClient:
    """Deterministic $0 scripted LLM client for unit and integration testing."""

    def __init__(
        self,
        scripted_responses: Sequence[str | dict[str, Any] | LLMResponse | Callable[..., Any]]
        | None = None,
    ) -> None:
        self._queue = list(scripted_responses or [])
        self.calls: list[dict[str, Any]] = []
        self.spent_usd: float = 0.0
        self.total_tokens: int = 0
        self._lock = threading.Lock()

    def _coerce(self, item: Any, spec: ModelSpec, messages: list[dict[str, Any]]) -> LLMResponse:
        if callable(item):
            item = item(messages)
        if isinstance(item, LLMResponse):
            return LLMResponse(
                content=item.content,
                tool_calls=list(item.tool_calls),
                input_tokens=item.input_tokens,
                output_tokens=item.output_tokens,
                model_id=item.model_id or spec.model_id,
                cost_usd=0.0,
                raw=dict(item.raw),
                cached_input_tokens=item.cached_input_tokens,
            )
        if isinstance(item, dict):
            tcs = [
                tc
                if isinstance(tc, ToolCall)
                else ToolCall(
                    id=str(tc.get("id", f"mock_{idx}")),
                    name=str(tc.get("name", "")),
                    arguments=dict(tc.get("arguments", {})),
                )
                for idx, tc in enumerate(item.get("tool_calls") or [])
            ]
            return LLMResponse(
                content=str(item.get("content", "")),
                tool_calls=tcs,
                input_tokens=int(item.get("input_tokens", 0)),
                output_tokens=int(item.get("output_tokens", 0)),
                model_id=spec.model_id,
                cost_usd=0.0,
                raw=item,
            )
        return LLMResponse(content=str(item), model_id=spec.model_id, cost_usd=0.0)

    def complete_sync(
        self,
        messages: list[dict[str, Any]],
        *,
        role: str = "auditor",
        model: ModelSpec | str | None = None,
        tools: list[dict[str, Any]] | None = None,
        system: str = "",
        max_tokens: int = 4096,
        temperature: float = 0.0,
        allow_drain_reserve: bool = False,
    ) -> LLMResponse:
        spec = resolve_role_model(role, model)
        with self._lock:
            self.calls.append(
                {
                    "role": role,
                    "model_id": spec.model_id,
                    "messages": list(messages),
                    "system": system,
                    "tools": tools,
                    "allow_drain_reserve": allow_drain_reserve,
                }
            )
            nxt = self._queue.pop(0) if self._queue else ""
        return self._coerce(nxt, spec, messages)

    async def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        role: str = "auditor",
        model: ModelSpec | str | None = None,
        tools: list[dict[str, Any]] | None = None,
        system: str = "",
        max_tokens: int = 4096,
        temperature: float = 0.0,
        allow_drain_reserve: bool = False,
    ) -> LLMResponse:
        return self.complete_sync(
            messages,
            role=role,
            model=model,
            tools=tools,
            system=system,
            max_tokens=max_tokens,
            temperature=temperature,
            allow_drain_reserve=allow_drain_reserve,
        )
