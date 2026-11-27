"""Ring-1 SQLite WAL stigmergic whiteboard, FTS5 search, atomic claims, and <=8KB hot index."""

from __future__ import annotations

import contextlib
import json
import os
import re
import sqlite3
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from enum import StrEnum
from pathlib import Path
from typing import Any

CLAIM_TTL_SEC = 1200
MAX_EVENT_BYTES = 2048
MAX_SNAPSHOT_BYTES = 8000
UNVERIFIED_PROSE_TAG = "[UNVERIFIED_PROSE — DO NOT TRUST WITHOUT EXEC EVIDENCE]"
EXEC_VERIFIED_TAG = "[EXEC_VERIFIED]"

_EVIDENCE_KEYS: tuple[str, ...] = (
    "exec_evidence",
    "evidence",
    "reopen_witness",
    "witness",
    "exit_code",
    "cmd",
    "command",
    "trace",
    "stdout",
    "stderr",
    "verified",
)
_FTS_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")


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


_HIGH_SIGNAL_ORDER: tuple[Section, ...] = (
    Section.EFFECT,
    Section.WISH,
    Section.INVARIANT,
    Section.ENCODER,
    Section.INSIGHT,
    Section.BOUNTY,
    Section.DEAD_END,
)
_RENDER_ORDER: tuple[Section, ...] = (*_HIGH_SIGNAL_ORDER, Section.CLAIM)


@contextmanager
def immediate_tx(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Acquire an explicit BEGIN IMMEDIATE transaction with busy retry and no .commit()."""
    for attempt in range(25):
        try:
            conn.execute("BEGIN IMMEDIATE")
            break
        except sqlite3.OperationalError as exc:
            msg = str(exc).lower()
            if ("locked" not in msg and "busy" not in msg) or attempt == 24:
                raise
            time.sleep(0.002 * (attempt + 1))
    try:
        yield conn
    except BaseException:
        with contextlib.suppress(sqlite3.Error):
            conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


def _has_exec_evidence(meta: dict[str, Any]) -> bool:
    for key in _EVIDENCE_KEYS:
        if key in meta:
            val = meta[key]
            if val is not None and val is not False and val != "":
                return True
    return False


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


def _atomic_replace_text(target_path: Path, content: str, ensure_dir: bool = False) -> None:
    if ensure_dir:
        target_path.parent.mkdir(parents=True, exist_ok=True)
    parent = os.fspath(target_path.parent)
    tmp_name = f".{target_path.name}.{os.getpid()}.{threading.get_ident()}.{time.monotonic_ns()}.tmp"
    tmp_path = os.path.join(parent, tmp_name)
    data = content.encode("utf-8")
    fd = os.open(tmp_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    try:
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            view = view[written:]
    finally:
        os.close(fd)
    os.replace(tmp_path, os.fspath(target_path))


def _row_to_record(row: tuple[Any, ...]) -> dict[str, Any]:
    seq, ts, kind, section, worker, target, summary, ttl_sec, accepted, meta_json = row
    try:
        meta = json.loads(meta_json) if meta_json else {}
    except ValueError:
        meta = {}
    if not isinstance(meta, dict):
        meta = {}
    return {
        "seq": int(seq),
        "ts": float(ts),
        "kind": str(kind),
        "section": str(section),
        "worker": str(worker),
        "target": str(target),
        "summary": str(summary),
        "ttl_sec": None if ttl_sec is None else float(ttl_sec),
        "accepted": bool(accepted),
        "meta": meta,
    }


class StigmergicWhiteboard:
    """SQLite WAL stigmergic whiteboard with FTS5 search, atomic claims, and <=8KB snapshot."""

    def __init__(self, repo: Path, now_fn: Callable[[], float] = time.time) -> None:
        self.repo = Path(repo).resolve()
        self.ajar_dir = self.repo / ".ajar"
        self.db_path = self.ajar_dir / "whiteboard.sqlite"
        self.events_path = self.ajar_dir / "events.jsonl"
        self.whiteboard_path = self.ajar_dir / "WHITEBOARD.md"
        self._now = now_fn
        self._last_explicit_now: float | None = None
        self._reader_cursors: dict[str, int] = {}
        self._write_lock = threading.Lock()
        self._conn_shared: sqlite3.Connection | None = None
        self._audit_fd: int | None = None
        self._ensure_initialized()

    def _open_conn(self, set_wal: bool = False) -> sqlite3.Connection:
        conn = sqlite3.connect(
            str(self.db_path),
            timeout=10.0,
            isolation_level=None,
            check_same_thread=False,
        )
        if set_wal:
            conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=10000")
        conn.execute("PRAGMA temp_store=MEMORY")
        conn.execute("PRAGMA cache_size=-4000")
        return conn

    def _conn(self) -> sqlite3.Connection:
        if self._conn_shared is None:
            self._ensure_initialized()
        assert self._conn_shared is not None
        return self._conn_shared

    def _ensure_initialized(self) -> None:
        with self._write_lock:
            if self._conn_shared is not None:
                return
            self.ajar_dir.mkdir(parents=True, exist_ok=True)
            conn = self._open_conn(set_wal=True)
            with immediate_tx(conn):
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS events ("
                    "seq INTEGER PRIMARY KEY AUTOINCREMENT, "
                    "ts REAL NOT NULL, "
                    "kind TEXT NOT NULL, "
                    "section TEXT NOT NULL, "
                    "worker TEXT NOT NULL, "
                    "target TEXT NOT NULL, "
                    "summary TEXT NOT NULL, "
                    "ttl_sec REAL, "
                    "accepted INTEGER NOT NULL DEFAULT 1, "
                    "meta_json TEXT NOT NULL DEFAULT '{}')"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_events_section_seq "
                    "ON events(section, seq DESC)"
                )
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS claims ("
                    "target TEXT PRIMARY KEY, "
                    "worker TEXT NOT NULL, "
                    "expires_at REAL NOT NULL, "
                    "seq INTEGER NOT NULL)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_claims_expires ON claims(expires_at)"
                )
                conn.execute(
                    "CREATE VIRTUAL TABLE IF NOT EXISTS events_fts USING fts5("
                    "section, worker, target, summary, "
                    "content='events', content_rowid='seq')"
                )
                conn.execute(
                    "CREATE TRIGGER IF NOT EXISTS trg_events_ai AFTER INSERT ON events "
                    "BEGIN "
                    "INSERT INTO events_fts(rowid, section, worker, target, summary) "
                    "VALUES (new.seq, new.section, new.worker, new.target, new.summary); "
                    "END"
                )
            self._hydrate_legacy_jsonl(conn)
            self._conn_shared = conn

    def _hydrate_legacy_jsonl(self, conn: sqlite3.Connection) -> None:
        row = conn.execute("SELECT COUNT(*) FROM events").fetchone()
        if (row and int(row[0]) > 0) or not self.events_path.is_file():
            return
        lines = self.events_path.read_text(encoding="utf-8", errors="replace").splitlines()
        with immediate_tx(conn):
            for raw in lines:
                line = raw.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(item, dict):
                    continue
                sec = str(item.get("section", "insight")).strip().lower()
                ts = float(item.get("ts", 0.0))
                worker = str(item.get("worker", "main"))
                target = str(item.get("target", ""))
                summary = str(item.get("summary", ""))
                ttl = item.get("ttl_sec")
                ttl_val = None if ttl is None else float(ttl)
                meta_json = json.dumps(item.get("meta") or {}, separators=(",", ":"))
                cur = conn.execute(
                    "INSERT INTO events(ts, kind, section, worker, target, summary, "
                    "ttl_sec, accepted, meta_json) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)",
                    (ts, sec.upper(), sec, worker, target, summary, ttl_val, meta_json),
                )
                if sec == Section.CLAIM.value and target:
                    eff_ttl = CLAIM_TTL_SEC if ttl_val is None else ttl_val
                    conn.execute(
                        "INSERT OR REPLACE INTO claims(target, worker, expires_at, seq) "
                        "VALUES (?, ?, ?, ?)",
                        (target, worker, ts + eff_ttl, int(cur.lastrowid or 0)),
                    )

    def close(self) -> None:
        with self._write_lock:
            if self._audit_fd is not None:
                with contextlib.suppress(OSError):
                    os.close(self._audit_fd)
                self._audit_fd = None
            if self._conn_shared is not None:
                with contextlib.suppress(sqlite3.Error):
                    self._conn_shared.close()
                self._conn_shared = None

    def __del__(self) -> None:
        with contextlib.suppress(Exception):
            self.close()

    def _append_audit_locked(self, event: dict[str, Any]) -> None:
        payload = _pack_jsonl_record(event)
        if self._audit_fd is None:
            flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
            self._audit_fd = os.open(os.fspath(self.events_path), flags, 0o644)
        os.write(self._audit_fd, payload)

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

    def _format_entry(self, rec: dict[str, Any], now: float, max_summary: int = 180) -> str:
        worker = rec.get("worker") or "main"
        target = f" `{rec['target']}`" if rec.get("target") else ""
        extra_tag = ""
        sec = rec.get("section")
        if sec == Section.CLAIM.value:
            ttl = CLAIM_TTL_SEC if rec.get("ttl_sec") is None else float(rec["ttl_sec"])
            rem = max(0, int(ttl - (now - float(rec.get("ts", now)))))
            extra_tag = f" (ttl={rem}s)"
        elif sec == Section.DEAD_END.value:
            raw_meta = rec.get("meta")
            meta_dict: dict[str, Any] = raw_meta if isinstance(raw_meta, dict) else {}
            tag = EXEC_VERIFIED_TAG if _has_exec_evidence(meta_dict) else UNVERIFIED_PROSE_TAG
            extra_tag = f" {tag}"
        summary = " ".join(str(rec.get("summary", "")).splitlines()).strip()
        if max_summary > 0 and len(summary) > max_summary:
            summary = summary[: max_summary - 3] + "..."
        return f"- [#{rec['seq']} {worker}]{target}{extra_tag}: {summary}"

    def _render_hot_snapshot(self, conn: sqlite3.Connection, now: float) -> tuple[int, str]:
        seq_row = conn.execute("SELECT COALESCE(MAX(seq), 0) FROM events").fetchone()
        latest_seq = int(seq_row[0]) if seq_row else 0
        c_row = conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(CASE WHEN expires_at > ? THEN 1 ELSE 0 END), 0) "
            "FROM claims",
            (now,),
        ).fetchone()
        total_claims = int(c_row[0]) if c_row else 0
        active_claims_total = int(c_row[1]) if c_row else 0
        expired_claims = max(0, total_claims - active_claims_total)

        header = [
            "# STIGMERGIC WHITEBOARD",
            (
                f"Journal seq: {latest_seq} | Active claims: {active_claims_total} "
                f"| Evaporated claims: {expired_claims}"
            ),
            "",
        ]
        blocks: list[str] = ["\n".join(header)]
        used_bytes = len(blocks[0].encode("utf-8"))
        high_signal_cap = MAX_SNAPSHOT_BYTES - 900

        for sec in _HIGH_SIGNAL_ORDER:
            rows = conn.execute(
                "SELECT seq, ts, kind, section, worker, target, summary, ttl_sec, "
                "accepted, meta_json FROM events WHERE section = ? "
                "ORDER BY seq DESC LIMIT 8",
                (sec.value,),
            ).fetchall()
            sec_lines = [f"## {sec.value}"]
            if not rows:
                sec_lines.append("- (empty)")
            else:
                for raw in reversed(rows):
                    sec_lines.append(self._format_entry(_row_to_record(raw), now, max_summary=140))
            sec_lines.append("")
            chunk = "\n".join(sec_lines)
            chunk_bytes = len(chunk.encode("utf-8")) + 1
            if used_bytes + chunk_bytes > high_signal_cap and rows:
                trimmed = [f"## {sec.value}"]
                for raw in reversed(rows[:2]):
                    trimmed.append(self._format_entry(_row_to_record(raw), now, max_summary=100))
                if len(rows) > 2:
                    trimmed.append(f"- ... (+{len(rows) - 2} more; use search())")
                trimmed.append("")
                chunk = "\n".join(trimmed)
                chunk_bytes = len(chunk.encode("utf-8")) + 1
            blocks.append(chunk)
            used_bytes += chunk_bytes

        claim_rows = conn.execute(
            "SELECT seq, worker, target, expires_at FROM claims "
            "WHERE expires_at > ? ORDER BY seq DESC LIMIT 8",
            (now,),
        ).fetchall()
        claim_lines = ["## claim"]
        if not claim_rows:
            claim_lines.append("- (empty)")
        else:
            shown = 0
            for seq, worker, target, expires_at in reversed(claim_rows):
                rem = max(0, int(float(expires_at) - now))
                line = f"- [#{int(seq)} {worker}] `{target}` (ttl={rem}s): Claimed {target}"
                cand_bytes = len(("\n".join(claim_lines + [line, ""])).encode("utf-8"))
                if used_bytes + cand_bytes + 64 > MAX_SNAPSHOT_BYTES:
                    break
                claim_lines.append(line)
                shown += 1
            hidden = max(0, active_claims_total - shown)
            if hidden > 0:
                claim_lines.append(f"- ... (+{hidden} more active claims)")
        claim_lines.append("")
        blocks.append("\n".join(claim_lines))

        board = "\n".join(blocks)
        if len(board.encode("utf-8")) > MAX_SNAPSHOT_BYTES:
            board = board.encode("utf-8")[:MAX_SNAPSHOT_BYTES].decode("utf-8", errors="ignore")
        return latest_seq, board

    def try_claim(
        self,
        target: str,
        worker_id: str = "main",
        ttl_sec: float = CLAIM_TTL_SEC,
        now: float | None = None,
    ) -> dict[str, Any]:
        return self.post(
            Section.CLAIM,
            summary=f"Claimed {target}",
            worker=worker_id,
            target=target,
            ttl_sec=ttl_sec,
            now=now,
        )

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
        merged_meta = dict(meta) if meta else {}
        if extra:
            merged_meta.update(extra)
        eff_ttl = (
            (CLAIM_TTL_SEC if ttl_sec is None else float(ttl_sec))
            if sec is Section.CLAIM
            else ttl_sec
        )
        clean_summary = " ".join(str(text).splitlines()).strip()
        meta_json = json.dumps(merged_meta, separators=(",", ":"), ensure_ascii=True)
        conn = self._conn()
        with self._write_lock:
            with immediate_tx(conn):
                if sec is Section.CLAIM and target:
                    existing = conn.execute(
                        "SELECT worker, expires_at FROM claims WHERE target = ?",
                        (target,),
                    ).fetchone()
                    if existing is not None:
                        holder = str(existing[0])
                        expires_at = float(existing[1])
                        if ts < expires_at and holder != worker_val:
                            return {"accepted": False, "holder": holder, "target": target}
                cur = conn.execute(
                    "INSERT INTO events(ts, kind, section, worker, target, summary, "
                    "ttl_sec, accepted, meta_json) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)",
                    (
                        round(ts, 3),
                        sec.value.upper(),
                        sec.value,
                        worker_val,
                        str(target or ""),
                        clean_summary,
                        eff_ttl,
                        meta_json,
                    ),
                )
                seq = int(cur.lastrowid or 0)
                if sec is Section.CLAIM and target:
                    ttl_val = float(eff_ttl if eff_ttl is not None else CLAIM_TTL_SEC)
                    conn.execute(
                        "INSERT OR REPLACE INTO claims(target, worker, expires_at, seq) "
                        "VALUES (?, ?, ?, ?)",
                        (str(target), worker_val, ts + ttl_val, seq),
                    )
            event: dict[str, Any] = {
                "seq": seq,
                "ts": round(ts, 3),
                "kind": sec.value.upper(),
                "section": sec.value,
                "worker": worker_val,
                "target": str(target or ""),
                "summary": clean_summary,
                "ttl_sec": eff_ttl,
                "accepted": True,
                "meta": merged_meta,
            }
            self._append_audit_locked(event)
            _, board = self._render_hot_snapshot(conn, ts)
            _atomic_replace_text(self.whiteboard_path, board)
            return event

    def read_snapshot(self) -> tuple[int, str]:
        now = self._effective_now()
        conn = self._conn()
        with self._write_lock:
            latest_seq, board = self._render_hot_snapshot(conn, now)
            _atomic_replace_text(self.whiteboard_path, board)
        return latest_seq, board

    def read_delta(self, since_seq_or_worker: int | str = 0, exclude_worker: str = "") -> Any:
        now = self._effective_now()
        conn = self._conn()
        with self._write_lock:
            seq_row = conn.execute("SELECT COALESCE(MAX(seq), 0) FROM events").fetchone()
            latest_seq = int(seq_row[0]) if seq_row else 0
            if isinstance(since_seq_or_worker, str):
                reader = since_seq_or_worker
                since_seq = self._reader_cursors.get(reader, 0)
                self._reader_cursors[reader] = latest_seq
                rows = conn.execute(
                    "SELECT seq, ts, kind, section, worker, target, summary, ttl_sec, "
                    "accepted, meta_json FROM events WHERE seq > ? AND worker != ? "
                    "ORDER BY seq ASC",
                    (since_seq, reader),
                ).fetchall()
                lines_w: list[str] = []
                for raw in rows:
                    rec = _row_to_record(raw)
                    if self._is_expired(rec, now):
                        continue
                    sec = str(rec.get("section", "insight")).upper()
                    lines_w.append(f"[{sec}] {self._format_entry(rec, now, max_summary=0)[2:]}")
                return "\n".join(lines_w)

            since_seq = int(since_seq_or_worker)
            if exclude_worker:
                rows = conn.execute(
                    "SELECT seq, ts, kind, section, worker, target, summary, ttl_sec, "
                    "accepted, meta_json FROM events WHERE seq > ? AND worker != ? "
                    "ORDER BY seq ASC",
                    (since_seq, exclude_worker),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT seq, ts, kind, section, worker, target, summary, ttl_sec, "
                    "accepted, meta_json FROM events WHERE seq > ? ORDER BY seq ASC",
                    (since_seq,),
                ).fetchall()
        events_out: list[str] = []
        for raw in rows:
            rec = _row_to_record(raw)
            if self._is_expired(rec, now):
                continue
            sec = str(rec.get("section", "insight")).upper()
            events_out.append(f"[{sec}] {self._format_entry(rec, now, max_summary=0)[2:]}")
        return events_out, latest_seq

    def search(
        self,
        query: str,
        *,
        section: Section | str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        tokens = _FTS_TOKEN_RE.findall(query or "")
        if not tokens:
            return []
        fts_query = " ".join(f'"{tok}"' for tok in tokens)
        conn = self._conn()
        cap = max(1, int(limit))
        with self._write_lock:
            if section is not None:
                sec_val = Section(str(section).strip().lower()).value
                rows = conn.execute(
                    "SELECT e.seq, e.ts, e.kind, e.section, e.worker, e.target, e.summary, "
                    "e.ttl_sec, e.accepted, e.meta_json "
                    "FROM events_fts f JOIN events e ON e.seq = f.rowid "
                    "WHERE events_fts MATCH ? AND e.section = ? "
                    "ORDER BY bm25(events_fts), e.seq DESC LIMIT ?",
                    (fts_query, sec_val, cap),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT e.seq, e.ts, e.kind, e.section, e.worker, e.target, e.summary, "
                    "e.ttl_sec, e.accepted, e.meta_json "
                    "FROM events_fts f JOIN events e ON e.seq = f.rowid "
                    "WHERE events_fts MATCH ? "
                    "ORDER BY bm25(events_fts), e.seq DESC LIMIT ?",
                    (fts_query, cap),
                ).fetchall()
        return [_row_to_record(r) for r in rows]

    def active_claims(self, now: float | None = None) -> list[dict[str, Any]]:
        ts = self._effective_now(now)
        conn = self._conn()
        with self._write_lock:
            rows = conn.execute(
                "SELECT target, worker, expires_at, seq FROM claims "
                "WHERE expires_at > ? ORDER BY seq ASC",
                (ts,),
            ).fetchall()
        return [
            {
                "target": str(t),
                "worker": str(w),
                "expires_at": float(exp),
                "seq": int(seq),
            }
            for t, w, exp, seq in rows
        ]

    def get_records(
        self,
        section: Section | str,
        include_expired: bool = False,
    ) -> list[dict[str, Any]]:
        sec_val = Section(str(section).strip().lower()).value
        now = self._effective_now()
        conn = self._conn()
        with self._write_lock:
            rows = conn.execute(
                "SELECT seq, ts, kind, section, worker, target, summary, ttl_sec, "
                "accepted, meta_json FROM events WHERE section = ? ORDER BY seq ASC",
                (sec_val,),
            ).fetchall()
        out: list[dict[str, Any]] = []
        for raw in rows:
            rec = _row_to_record(raw)
            if include_expired or not self._is_expired(rec, now):
                out.append(rec)
        return out

    def stats(self) -> dict[str, Any]:
        now = self._effective_now()
        conn = self._conn()
        counts = {sec.value: 0 for sec in Section}
        total = 0
        latest_seq = 0
        with self._write_lock:
            for sec, cnt, max_seq in conn.execute(
                "SELECT section, COUNT(*), MAX(seq) FROM events GROUP BY section"
            ).fetchall():
                n = int(cnt)
                total += n
                if max_seq is not None:
                    latest_seq = max(latest_seq, int(max_seq))
                if str(sec) in counts:
                    counts[str(sec)] = n
            c_row = conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(CASE WHEN expires_at > ? THEN 1 ELSE 0 END), 0) "
                "FROM claims",
                (now,),
            ).fetchone()
            total_claims = int(c_row[0]) if c_row else 0
            active_claims = int(c_row[1]) if c_row else 0
            expired_claims = max(0, total_claims - active_claims)
            counts[Section.CLAIM.value] = active_claims
            workers = [
                str(r[0])
                for r in conn.execute(
                    "SELECT DISTINCT worker FROM events WHERE worker != '' ORDER BY worker"
                ).fetchall()
            ]
        return {
            "total_events": total,
            "latest_seq": latest_seq,
            "active_claims": active_claims,
            "expired_claims": expired_claims,
            "by_section": counts,
            "workers": workers,
        }


Whiteboard = StigmergicWhiteboard
