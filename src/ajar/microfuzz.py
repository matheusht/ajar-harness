"""In-slot boundary + STITCH-inspired stateful micro-fuzzer with mandatory clean-worktree entrypoint replay."""

from __future__ import annotations

import random
import shlex
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

from ajar.schemas import ajar_dir, append_jsonl, utc_now
from ajar.worktree import clean_worktree, run_hermetic

BOUNDARY_PAYLOADS: tuple[bytes, ...] = (
    b"",
    b"\x00",
    b"\n%!PS-Adobe-3.0\n",
    b"\xc5\xd0\xd3\xc6" + b"\x00" * 24 + b"%!PS",
    b"-" + b"1",
    str(2**31 - 1).encode(),
    str(2**31).encode(),
    str(2**64 - 1).encode(),
    b"A" * 4097,
    b"../../etc/passwd\x00",
)

STATEFUL_OPS: tuple[str, ...] = (
    "init",
    "configure_boundary",
    "feed_partial",
    "trigger_error_recover",
    "reuse_after_error",
    "reset",
)


@dataclass
class MicrofuzzHit:
    mode: str  # "boundary" | "stateful"
    seed_repr: str
    in_process_signal: str
    entrypoint_verified: bool
    entrypoint_rc: int
    entrypoint_stderr: str
    created_at: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def generate_stateful_sequences(iterations: int = 64, seed: int = 1337) -> list[tuple[str, ...]]:
    """Generate STITCH-inspired multi-call API state sequences in-memory (`0` fork overhead)."""
    rng = random.Random(seed)
    sequences: list[tuple[str, ...]] = [
        ("init", "feed_partial", "trigger_error_recover", "reuse_after_error"),
        ("init", "configure_boundary", "feed_partial", "reset", "reuse_after_error"),
    ]
    for _ in range(max(0, iterations - len(sequences))):
        length = rng.randint(2, 6)
        seq = ("init", *[rng.choice(STATEFUL_OPS[1:]) for _ in range(length - 1)])
        sequences.append(seq)
    return sequences


def replay_against_entrypoint(
    repo: Path,
    entrypoint_cmd_template: str,
    payload: bytes,
    profile: str = "upstream",
) -> tuple[bool, int, str]:
    """Replay an in-process candidate crash through the real public CLI/entrypoint in a clean worktree.

    `entrypoint_cmd_template` receives `{input}` pointing to the materialized payload file inside the clean worktree.
    Eliminates STITCH's 869-fake-crash harness-misuse failure mode (`0%` harness-only FPs).
    """
    with clean_worktree(repo) as (wt, dep_env):
        inp = wt / ".ajar-fuzz-input.bin"
        inp.write_bytes(payload)
        cmd = entrypoint_cmd_template.replace("{input}", shlex.quote(str(inp)))
        res = run_hermetic(cmd, cwd=wt, timeout=30, profile=profile, extra_env=dep_env)
        crashed = res.returncode != 0 and res.returncode != 124
        return crashed, res.returncode, (res.stderr or res.stdout)[-400:]


def run_microfuzz(
    repo: Path,
    entrypoint_cmd_template: str,
    in_process_probe: Callable[[bytes, tuple[str, ...] | None], bytes | None] | None = None,
    mode: str = "both",
    iterations: int = 32,
    seed: int = 1337,
    profile: str = "upstream",
) -> list[MicrofuzzHit]:
    """Run boundary and/or stateful in-process probes and promote ONLY entrypoint-reproducible hits."""
    if mode not in {"boundary", "stateful", "both"}:
        raise ValueError(f"Invalid microfuzz mode: {mode!r}")
    candidates: list[tuple[str, str, bytes]] = []

    if mode in {"boundary", "both"}:
        for raw in BOUNDARY_PAYLOADS:
            if in_process_probe is None:
                candidates.append(("boundary", repr(raw[:32]), raw))
            else:
                witness = in_process_probe(raw, None)
                if witness is not None:
                    candidates.append(("boundary", repr(raw[:32]), witness))

    if mode in {"stateful", "both"}:
        for seq in generate_stateful_sequences(iterations=iterations, seed=seed):
            encoded_seq = ("SEQ:" + "->".join(seq)).encode("utf-8")
            if in_process_probe is None:
                candidates.append(("stateful", "->".join(seq), encoded_seq))
            else:
                witness = in_process_probe(encoded_seq, seq)
                if witness is not None:
                    candidates.append(("stateful", "->".join(seq), witness))

    verified_hits: list[MicrofuzzHit] = []
    log_path = ajar_dir(repo) / "microfuzz.jsonl"
    for cand_mode, seed_repr, witness_bytes in candidates:
        ok, rc, err = replay_against_entrypoint(repo, entrypoint_cmd_template, witness_bytes, profile=profile)
        hit = MicrofuzzHit(
            mode=cand_mode,
            seed_repr=seed_repr,
            in_process_signal="candidate_witness",
            entrypoint_verified=ok,
            entrypoint_rc=rc,
            entrypoint_stderr=err,
            created_at=utc_now(),
        )
        append_jsonl(log_path, hit.to_dict())
        if ok:
            verified_hits.append(hit)
    return verified_hits
