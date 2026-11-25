"""Ring-1 12-type EffectType ontology, backward WISH abduction, and LLM Chain Weaver."""

from __future__ import annotations

import hashlib
import inspect
import json
import re
from enum import StrEnum
from pathlib import Path
from typing import Any

from ajar.cli import Candidate
from ajar.llm import LLMClient
from ajar.whiteboard import Section, StigmergicWhiteboard


class EffectType(StrEnum):
    PARSER_OFFSET_DISAGREEMENT = "parser_offset_disagreement"
    BUFFER_GEOMETRY_MISMATCH = "buffer_geometry_mismatch"
    LIFETIME_ESCAPE = "lifetime_escape"
    RESIDUAL_ERROR_STATE = "residual_error_state"
    UNINITIALIZED_OR_SENTINEL_PROPAGATION = "uninitialized_or_sentinel_propagation"
    POLICY_ALIAS_DIVERGENCE = "policy_alias_divergence"
    CROSS_SESSION_KEY_REUSE = "cross_session_key_reuse"
    REENTRANT_CALLBACK_WINDOW = "reentrant_callback_window"
    ACCOUNTING_ROUNDING_DELTA = "accounting_rounding_delta"
    STALE_CACHE_OR_ORACLE_READ = "stale_cache_or_oracle_read"
    PRIVILEGE_OR_CAPABILITY_SMUGGLING = "privilege_or_capability_smuggling"
    SCHEMA_OR_ENCODING_MALLEABILITY = "schema_or_encoding_malleability"


class CarrierKind(StrEnum):
    CALL_ARG_RETURN = "call_arg_return"
    SHARED_STRUCT_FIELD = "shared_struct_field"
    PERSISTENT_OR_CACHE_STORE = "persistent_or_cache_store"
    WIRE_OR_CONTAINER_FRAME = "wire_or_container_frame"
    CALLBACK_OR_ASYNC_YIELD = "callback_or_async_yield"
    CROSS_CONTRACT_OR_IPC_CALL = "cross_contract_or_ipc_call"


EFFECT_COMPAT: dict[str, set[str]] = {
    "parser_offset_disagreement": {
        "parser_offset_disagreement",
        "policy_alias_divergence",
        "buffer_geometry_mismatch",
    },
    "buffer_geometry_mismatch": {
        "buffer_geometry_mismatch",
        "lifetime_escape",
    },
    "lifetime_escape": {
        "lifetime_escape",
        "uninitialized_or_sentinel_propagation",
    },
    "residual_error_state": {
        "residual_error_state",
        "uninitialized_or_sentinel_propagation",
        "stale_cache_or_oracle_read",
    },
    "uninitialized_or_sentinel_propagation": {
        "uninitialized_or_sentinel_propagation",
        "privilege_or_capability_smuggling",
    },
    "policy_alias_divergence": {
        "policy_alias_divergence",
        "privilege_or_capability_smuggling",
    },
    "cross_session_key_reuse": {
        "cross_session_key_reuse",
        "stale_cache_or_oracle_read",
        "privilege_or_capability_smuggling",
    },
    "reentrant_callback_window": {
        "reentrant_callback_window",
        "stale_cache_or_oracle_read",
        "accounting_rounding_delta",
    },
    "accounting_rounding_delta": {
        "accounting_rounding_delta",
        "buffer_geometry_mismatch",
    },
    "stale_cache_or_oracle_read": {
        "stale_cache_or_oracle_read",
        "accounting_rounding_delta",
    },
    "privilege_or_capability_smuggling": {
        "privilege_or_capability_smuggling",
    },
    "schema_or_encoding_malleability": {
        "schema_or_encoding_malleability",
        "parser_offset_disagreement",
        "policy_alias_divergence",
        "cross_session_key_reuse",
    },
}

CARRIER_COMPAT: dict[str, set[str]] = {
    "call_arg_return": {"call_arg_return", "shared_struct_field"},
    "shared_struct_field": {"shared_struct_field", "persistent_or_cache_store", "call_arg_return"},
    "persistent_or_cache_store": {"persistent_or_cache_store", "shared_struct_field"},
    "wire_or_container_frame": {
        "wire_or_container_frame",
        "call_arg_return",
        "cross_contract_or_ipc_call",
    },
    "callback_or_async_yield": {
        "callback_or_async_yield",
        "cross_contract_or_ipc_call",
        "shared_struct_field",
    },
    "cross_contract_or_ipc_call": {"cross_contract_or_ipc_call", "callback_or_async_yield"},
}


def _extract_payload(item: dict[str, Any]) -> dict[str, Any] | None:
    if "effect_type" in item or "desired_effect" in item:
        return item
    meta = item.get("meta")
    if isinstance(meta, dict):
        if "effect_type" in meta or "desired_effect" in meta:
            return meta
        sub = meta.get("payload")
        if isinstance(sub, dict) and ("effect_type" in sub or "desired_effect" in sub):
            return sub
    return None


def post_effect(
    wb: StigmergicWhiteboard,
    effect_type: EffectType | str,
    carrier: CarrierKind | str = CarrierKind.SHARED_STRUCT_FIELD,
    span: str = "",
    summary: str = "",
    *,
    worker_id: str = "W0",
    preconditions: list[str] | None = None,
    confidence: float = 0.75,
) -> dict[str, Any]:
    eff = EffectType(str(effect_type)).value
    car = CarrierKind(str(carrier)).value
    record: dict[str, Any] = {
        "kind": "effect",
        "effect_type": eff,
        "carrier": car,
        "span": span,
        "summary": summary,
        "preconditions": list(preconditions or []),
        "worker_id": worker_id,
        "confidence": float(confidence),
    }
    wb.post(Section.EFFECT, summary=summary or eff, worker=worker_id, target=span, meta=record)
    return record


def post_wish(
    wb: StigmergicWhiteboard,
    desired_effect: EffectType | str,
    carrier: CarrierKind | str = CarrierKind.SHARED_STRUCT_FIELD,
    span: str = "",
    summary: str = "",
    *,
    sink_span: str = "",
    impact: str = "",
    worker_id: str = "W1",
    constraints: list[str] | None = None,
    priority: float = 0.8,
) -> dict[str, Any]:
    des = EffectType(str(desired_effect)).value
    car = CarrierKind(str(carrier)).value
    resolved_span = sink_span or span
    resolved_impact = impact or summary
    record: dict[str, Any] = {
        "kind": "wish",
        "desired_effect": des,
        "carrier": car,
        "span": resolved_span,
        "sink_span": resolved_span,
        "summary": resolved_impact,
        "impact": resolved_impact,
        "constraints": list(constraints or []),
        "worker_id": worker_id,
        "priority": float(priority),
    }
    wb.post(
        Section.WISH,
        summary=resolved_impact or des,
        worker=worker_id,
        target=resolved_span,
        meta=record,
    )
    return record


def _read_typed(wb: StigmergicWhiteboard, sec: Section) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in wb.get_records(sec):
        rec = _extract_payload(raw)
        if rec is None:
            continue
        digest = hashlib.sha256(json.dumps(rec, sort_keys=True).encode("utf-8")).hexdigest()[:16]
        if digest not in seen:
            seen.add(digest)
            out.append(rec)
    return out


def join_effects_and_wishes(wb: StigmergicWhiteboard) -> list[dict[str, Any]]:
    effects = _read_typed(wb, Section.EFFECT)
    wishes = _read_typed(wb, Section.WISH)
    joined: list[dict[str, Any]] = []
    seen_pairs: set[tuple[str, str, str, str]] = set()
    for eff in effects:
        eff_type = str(eff.get("effect_type", ""))
        eff_carrier = str(eff.get("carrier", ""))
        allowed_effects = EFFECT_COMPAT.get(eff_type, set())
        allowed_carriers = CARRIER_COMPAT.get(eff_carrier, {eff_carrier})
        for wish in wishes:
            wish_type = str(wish.get("desired_effect", ""))
            wish_carrier = str(wish.get("carrier", ""))
            if wish_type not in allowed_effects or wish_carrier not in allowed_carriers:
                continue
            src_span = str(eff.get("span", ""))
            dst_span = str(wish.get("sink_span") or wish.get("span", ""))
            key = (src_span, dst_span, eff_type, wish_type)
            if key in seen_pairs:
                continue
            seen_pairs.add(key)
            base = 1.0 if eff_type == wish_type else 0.9
            carrier_bonus = 0.2 if eff_carrier == wish_carrier else 0.1
            cross_bonus = 0.15 if src_span != dst_span else 0.0
            worker_bonus = 0.1 if eff.get("worker_id") != wish.get("worker_id") else 0.0
            weight = float(eff.get("confidence", 0.75)) * float(wish.get("priority", 0.8))
            score = round((base + carrier_bonus + cross_bonus + worker_bonus) * weight, 4)
            join_id = hashlib.sha256(
                f"{src_span}|{dst_span}|{eff_type}|{wish_type}".encode("utf-8")
            ).hexdigest()[:12]
            joined.append({
                "join_id": join_id,
                "effect": eff,
                "wish": wish,
                "effect_type": eff_type,
                "desired_effect": wish_type,
                "carrier": eff_carrier,
                "hops": [s for s in (src_span, dst_span) if s],
                "entailment": "identity" if eff_type == wish_type else "cross_effect",
                "score": score,
            })
    joined.sort(key=lambda item: item["score"], reverse=True)
    return joined


def _read_span_context(repo: Path, span_ref: str, radius: int = 20) -> str:
    if not span_ref:
        return ""
    parts = span_ref.split(":")
    rel_path = parts[0]
    try:
        full_path = (repo / rel_path).resolve()
        full_path.relative_to(repo.resolve())
    except ValueError:
        return ""
    if not full_path.is_file():
        return ""
    lines = full_path.read_text(encoding="utf-8", errors="replace").splitlines()
    start = 1
    end = min(len(lines), 40)
    if len(parts) >= 2:
        nums = [int(x) for x in re.findall(r"\d+", parts[1])]
        if nums:
            start = max(1, nums[0] - radius)
            end = min(len(lines), nums[-1] + radius)
    return "\n".join(f"{idx}: {lines[idx - 1]}" for idx in range(start, end + 1))


async def weave_candidates(
    repo: Path,
    wb: StigmergicWhiteboard,
    llm: LLMClient | None,
) -> list[Candidate]:
    if llm is None:
        return []
    repo_path = Path(repo)
    joins = join_effects_and_wishes(wb)
    candidates: list[Candidate] = []
    sys_msg = (
        "You are Ring-1 Chain Weaver. Emit JSON with keys: "
        "feasible, title, severity, sink_symbol, repro_cmd, failure_oracle, patch_diff."
    )
    for pair in joins[:8]:
        hops = list(pair["hops"])
        src_ctx = _read_span_context(repo_path, hops[0] if hops else "")
        dst_ctx = _read_span_context(repo_path, hops[1] if len(hops) > 1 else "")
        prompt = (
            f"Join {pair['join_id']}: {pair['effect_type']} -> {pair['desired_effect']}\n"
            f"Source ({hops[0] if hops else 'n/a'}):\n{src_ctx}\n\n"
            f"Sink ({hops[1] if len(hops) > 1 else 'n/a'}):\n{dst_ctx}\n"
        )
        res = llm.complete([{"role": "user", "content": prompt}], role="weaver", system=sys_msg)
        resp = await res if inspect.isawaitable(res) else res
        raw = resp.content.strip()
        if not raw:
            continue
        match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
        if not match:
            continue
        try:
            parsed = json.loads(match.group(0))
        except ValueError:
            continue
        if not isinstance(parsed, dict) or parsed.get("feasible") is False:
            continue
        candidates.append(
            Candidate(
                id=f"WEAVE-{pair['join_id']}",
                title=str(parsed.get("title") or f"{pair['effect_type']} -> {pair['desired_effect']}"),
                severity=str(parsed.get("severity") or "high"),
                entry_span=hops[0] if hops else "",
                sink_symbol=str(parsed.get("sink_symbol") or ""),
                repro_cmd=str(parsed.get("repro_cmd") or ""),
                failure_oracle=str(parsed.get("failure_oracle") or ""),
                patch_diff=str(parsed.get("patch_diff") or ""),
                chain_hops=hops,
            )
        )
    return candidates
