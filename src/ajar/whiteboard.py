"""Ring-1 lock-free stigmergic journal (.ajar/events.jsonl) and atomic WHITEBOARD.md projector."""

from __future__ import annotations

import json
import os
import time
from enum import StrEnum
from pathlib import Path
from typing import Any, Callable

CLAIM_TTL_SEC = 1200
MAX_EVENT_BYTES = 2048


class Section(StrEnum):
    """Canonical stigmergic whiteboard sections."""

    INSIGHT = "insight"
    BOUNTY = "bounty"
    CLAIM = "claim"
    INVARIANT = "invariant"
    DEAD_END = "dead_end"
    EFFECT = "effect"
    WISH = "wish"
    ENCODER = "encoder"


_RENDER_ORDER: tuple[Section, ...] = (
    Section.CLAIM,
    Section.BOUNTY,
    Section.INSIGHT,
    Section.INVARIANT,
    Section.EFFECT,
    Section.ENCODER,
    Section.WISH,
    Section.DEAD_END,
)


def _pack_jsonl_record(record: dict[str, Any]) -> bytes:
    item = dict(record)
    raw = (json.dumps(item, separators=(",", ":"), ensure_ascii=True) + "\n").encode("ascii")
    if len(raw) < MAX_EVENT_BYTES:
        return raw
    if item.get("meta"):
        item["meta"] = {}
        raw = (json.dumps(item, separators=(",", ":"), ensure_ascii=True) + "\n").encode("ascii")
    summary = str(item.get("summary", ""))
    while len(raw) >= MAX_EVENT_BYTES and summary:
        cut = max(1, (len(raw) - MAX_EVENT_BYTES) + 16)
        summary = summary[: max(0, len(summary) - cut)]
        item["summary"] = summary + "..."
        raw = (json.dumps(item, separators=(",", ":"), ensure_ascii=True) + "\n").encode("ascii")
    if len(raw) >= MAX_EVENT_BYTES:
        item["target"] = str(item.get("target", ""))[:64]
        item["summary"] = str(item.get("summary", ""))[:256]
        raw = (json.dumps(item, separators=(",", ":"), ensure_ascii=True) + "\n").encode("ascii")
    return raw[: MAX_EVENT_BYTES - 1]


def _append_lockfree(events_path: Path, payload: bytes) -> None:
    events_path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
    fd = os.open(os.fspath(events_path), flags, 0o644)
    try:
        os.write(fd, payload)
    finally:
        os.close(fd)


def _atomic_replace_text(target_path: Path, content: str) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    nonce = f"{os.getpid()}.{time.monotonic_ns()}"
    tmp_path = target_path.parent / f".{target_path.name}.{nonce}.tmp"
    tmp_path.write_text(content, encoding="utf-8")
    os.replace(tmp_path, target_path)


class StigmergicWhiteboard:
    """Append-only event journal with 20m claim TTL evaporation and Markdown projection."""

    def __init__(self, repo: Path, now_fn: Callable[[], float] = time.time) -> None:
        self.repo = Path(repo).resolve()
        self.ajar_dir = self.repo / ".ajar"
        self.events_path = self.ajar_dir / "events.jsonl"
        self.whiteboard_path = self.ajar_dir / "WHITEBOARD.md"
        self._now = now_fn
        self._last_explicit_now: float | None = None
        self._reader_cursors: dict[str, int] = {}

    def _effective_now(self, now: float | None = None) -> float:
        if now is not None:
            val = float(now)
            self._last_explicit_now = val
            return val
        if self._last_explicit_now is not None:
            return self._last_explicit_now
        return self._now()

    def _is_expired(self, record: dict[str, Any], now: float) -> bool:
        if record.get("section") != Section.CLAIM.value:
            return False
        raw_ttl = record.get("ttl_sec")
        ttl_sec = CLAIM_TTL_SEC if raw_ttl is None else float(raw_ttl)
        created = float(record.get("ts", 0.0))
        return (now - created) >= ttl_sec

    def _read_journal(self) -> list[dict[str, Any]]:
        if not self.events_path.exists():
            return []
        try:
            lines = self.events_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return []
        records: list[dict[str, Any]] = []
        seq = 0
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                item = json.loads(stripped)
            except ValueError:
                continue
            if not isinstance(item, dict):
                continue
            seq += 1
            item["seq"] = seq
            records.append(item)
        return records

    def _format_entry(self, rec: dict[str, Any], now: float) -> str:
        worker = rec.get("worker") or "main"
        target = f" `{rec['target']}`" if rec.get("target") else ""
        ttl_tag = ""
        if rec.get("section") == Section.CLAIM.value:
            ttl = CLAIM_TTL_SEC if rec.get("ttl_sec") is None else float(rec["ttl_sec"])
            rem = max(0, int(ttl - (now - float(rec.get("ts", now)))))
            ttl_tag = f" (ttl={rem}s)"
        summary = str(rec.get("summary", "")).replace("\n", " ").strip()
        return f"- [#{rec['seq']} {worker}]{target}{ttl_tag}: {summary}"

    def _render_markdown(self, records: list[dict[str, Any]], now: float) -> str:
        grouped: dict[str, list[dict[str, Any]]] = {sec.value: [] for sec in _RENDER_ORDER}
        expired_claims = 0
        for rec in records:
            sec = str(rec.get("section", ""))
            if sec not in grouped:
                continue
            if self._is_expired(rec, now):
                expired_claims += 1
                continue
            grouped[sec].append(rec)
        latest_seq = records[-1]["seq"] if records else 0
        out = [
            "# STIGMERGIC WHITEBOARD",
            f"Journal seq: {latest_seq} | Evaporated claims: {expired_claims}",
            "",
        ]
        for sec in _RENDER_ORDER:
            items = grouped[sec.value]
            out.append(f"## {sec.value}")
            if not items:
                out.append("- (empty)")
            else:
                for rec in items:
                    out.append(self._format_entry(rec, now))
            out.append("")
        return "\n".join(out)

    def try_claim(
        self,
        target: str,
        worker_id: str = "main",
        ttl_sec: float = CLAIM_TTL_SEC,
        now: float | None = None,
    ) -> dict[str, Any]:
        ts = self._effective_now(now)
        for rec in self._read_journal():
            if rec.get("section") != Section.CLAIM.value:
                continue
            if rec.get("target") != target or not rec.get("accepted", True):
                continue
            if not self._is_expired(rec, ts) and rec.get("worker") != worker_id:
                return {"accepted": False, "holder": rec.get("worker"), "target": target}
        posted = self.post(
            Section.CLAIM,
            summary=f"Claimed {target}",
            worker=worker_id,
            target=target,
            ttl_sec=ttl_sec,
            now=ts,
        )
        return {**posted, "accepted": True}

    def post(
        self,
        kind: Section | str = Section.INSIGHT,
        summary: str = "",
        worker: str = "main",
        target: str = "",
        ttl_sec: float | None = None,
        meta: dict[str, Any] | None = None,
        now: float | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        raw_sec = extra.pop("section", kind)
        sec = Section(str(raw_sec).strip().lower())
        worker_val = str(extra.pop("worker_id", worker) or "main")
        text = summary or str(extra.pop("text", "") or extra.pop("content", ""))
        ts = self._effective_now(now)
        if sec is Section.CLAIM and target:
            for rec in self._read_journal():
                if rec.get("section") == Section.CLAIM.value and rec.get("target") == target:
                    if not self._is_expired(rec, ts) and rec.get("worker") != worker_val:
                        return {"accepted": False, "holder": rec.get("worker"), "target": target}
        merged_meta = dict(meta) if meta else {}
        if extra:
            merged_meta.update(extra)
        eff_ttl = (CLAIM_TTL_SEC if ttl_sec is None else float(ttl_sec)) if sec is Section.CLAIM else ttl_sec
        event: dict[str, Any] = {
            "ts": round(ts, 3),
            "kind": sec.value.upper(),
            "section": sec.value,
            "worker": worker_val,
            "target": str(target or ""),
            "summary": " ".join(str(text).splitlines()).strip(),
            "ttl_sec": eff_ttl,
            "accepted": True,
            "meta": merged_meta,
        }
        _append_lockfree(self.events_path, _pack_jsonl_record(event))
        records = self._read_journal()
        board = self._render_markdown(records, ts)
        _atomic_replace_text(self.whiteboard_path, board)
        return records[-1] if records else {**event, "seq": 1}

    def read_snapshot(self) -> tuple[int, str]:
        now = self._effective_now()
        records = self._read_journal()
        board = self._render_markdown(records, now)
        _atomic_replace_text(self.whiteboard_path, board)
        latest_seq = records[-1]["seq"] if records else 0
        return latest_seq, board

    def read_delta(self, since_seq_or_worker: int | str = 0, exclude_worker: str = "") -> Any:
        now = self._effective_now()
        records = self._read_journal()
        latest_seq = records[-1]["seq"] if records else 0
        if isinstance(since_seq_or_worker, str):
            reader = since_seq_or_worker
            since_seq = self._reader_cursors.get(reader, 0)
            self._reader_cursors[reader] = latest_seq
            lines_w: list[str] = []
            for rec in records:
                if rec["seq"] <= since_seq or rec.get("worker") == reader or self._is_expired(rec, now):
                    continue
                sec = str(rec.get("section", "insight")).upper()
                lines_w.append(f"[{sec}] {self._format_entry(rec, now)[2:]}")
            return "\n".join(lines_w)
        since_seq = int(since_seq_or_worker)
        events_out: list[str] = []
        for rec in records:
            if rec["seq"] <= since_seq:
                continue
            if exclude_worker and rec.get("worker") == exclude_worker:
                continue
            if self._is_expired(rec, now):
                continue
            sec = str(rec.get("section", "insight")).upper()
            events_out.append(f"[{sec}] {self._format_entry(rec, now)[2:]}")
        return events_out, latest_seq

    def get_records(
        self,
        section: Section | str,
        include_expired: bool = False,
    ) -> list[dict[str, Any]]:
        sec_val = Section(str(section).strip().lower()).value
        now = self._now()
        records = self._read_journal()
        return [
            rec
            for rec in records
            if rec.get("section") == sec_val and (include_expired or not self._is_expired(rec, now))
        ]

    def stats(self) -> dict[str, Any]:
        now = self._now()
        records = self._read_journal()
        counts = {sec.value: 0 for sec in Section}
        active_claims = 0
        expired_claims = 0
        workers: set[str] = set()
        for rec in records:
            sec = str(rec.get("section", ""))
            if rec.get("worker"):
                workers.add(str(rec["worker"]))
            if self._is_expired(rec, now):
                expired_claims += 1
                continue
            if sec in counts:
                counts[sec] += 1
            if sec == Section.CLAIM.value:
                active_claims += 1
        return {
            "total_events": len(records),
            "latest_seq": records[-1]["seq"] if records else 0,
            "active_claims": active_claims,
            "expired_claims": expired_claims,
            "by_section": counts,
            "workers": sorted(workers),
        }


Whiteboard = StigmergicWhiteboard
