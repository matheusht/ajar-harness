"""AJAR Ring-0 shared dataclasses, crash-safe JSONL helpers, and CLI entrypoint."""

from __future__ import annotations

import argparse
import asyncio
import fcntl
import inspect
import json
import os
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any, TypeVar

T = TypeVar("T")

DISABLE_FLAGS = (
    ("--disable-repomap", "disable_repomap"),
    ("--disable-whiteboard", "disable_whiteboard"),
    ("--disable-epistemic", "disable_epistemic"),
    ("--disable-chain-weaver", "disable_chain_weaver"),
    ("--disable-autobuild", "disable_autobuild"),
    ("--disable-swarm", "disable_swarm"),
    ("--disable-microfuzz", "disable_microfuzz"),
)


@dataclass(unsafe_hash=True)
class Span:
    path: str
    start: int
    end: int

    def to_ref(self) -> str:
        return f"{self.path}:{self.start}-{self.end}"

    @classmethod
    def from_ref(cls, ref: str) -> Span:
        if ":" not in ref:
            return cls(path=ref.strip(), start=1, end=1)
        raw_path, line_spec = ref.rsplit(":", 1)
        if "-" in line_spec:
            lo_s, hi_s = line_spec.split("-", 1)
            lo = max(1, int(lo_s))
            hi = max(lo, int(hi_s))
        else:
            lo = max(1, int(line_spec))
            hi = lo
        return cls(path=raw_path.strip(), start=lo, end=hi)


@dataclass
class BuildRecipe:
    profile: str = "upstream"
    build_script: str = ""
    test_cmd: str = ""
    static_only: bool = False
    verified: bool = False
    build_system: str = "auto"
    last_error: str = ""
    env: dict[str, str] = field(default_factory=dict)


@dataclass
class CrashSignature:
    kind: str
    summary: str
    top_frames: list[str]
    stack_hash: str


@dataclass
class Candidate:
    id: str
    title: str
    severity: str
    category: str = "advisory"
    lens: str = "L1_PARSER_DIFFERENTIAL"
    entry_span: str = ""
    sink_symbol: str = ""
    repro_cmd: str = ""
    failure_oracle: str = ""
    patch_diff: str = ""
    root_cause: str = ""
    impact: str = ""
    build_profile: str = "upstream"
    chain_hops: list[str] = field(default_factory=list)
    withdrawn: bool = False
    control_cmd: str = ""


@dataclass
class Verdict:
    candidate_id: str
    status: str
    truth_level: str
    pre_runs_failed: int = 0
    post_runs_passed: int = 0
    crash_sig: dict[str, Any] | None = None
    critic_verdict: str = "PENDING"
    notes: str = ""


@dataclass
class AblationConfig:
    disable_repomap: bool = False
    disable_whiteboard: bool = False
    disable_epistemic: bool = False
    disable_chain_weaver: bool = False
    disable_autobuild: bool = False
    disable_swarm: bool = False
    disable_microfuzz: bool = False


@dataclass
class RunConfig:
    repo: Path
    workers: int = 8
    budget_usd: float = 50.0
    hours: float = 6.0
    profile: str = "upstream"
    ablation: AblationConfig = field(default_factory=AblationConfig)

    def __post_init__(self) -> None:
        if not isinstance(self.repo, Path):
            self.repo = Path(self.repo)


def dataclass_from_dict(cls: type[T], raw: dict[str, Any]) -> T:
    valid = {f.name for f in fields(cls)}  # type: ignore[arg-type]
    filtered = {k: v for k, v in raw.items() if k in valid}
    return cls(**filtered)


def ajar_dir(repo: Path) -> Path:
    target = Path(repo) / ".ajar"
    target.mkdir(parents=True, exist_ok=True)
    return target


SCRUB_ENV_TOKENS = ("KEY", "TOKEN", "SECRET", "PASSWORD", "AUTH", "CREDENTIAL")


def scrub_subprocess_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    clean = {
        k: v
        for k, v in os.environ.items()
        if not any(tok in k.upper() for tok in SCRUB_ENV_TOKENS)
    }
    if extra:
        clean.update(extra)
    return clean


def append_jsonl(path: Path, record: dict[str, Any] | Any) -> None:
    dst = Path(path)
    dst.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(record) if is_dataclass(record) and not isinstance(record, type) else record
    encoded = (json.dumps(payload, sort_keys=True, ensure_ascii=True) + "\n").encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
    fd = os.open(str(dst), flags, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        view = memoryview(encoded)
        while view:
            written = os.write(fd, view)
            view = view[written:]
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    src = Path(path)
    if not src.is_file():
        return []
    rows: list[dict[str, Any]] = []
    with src.open("r", encoding="utf-8", errors="replace") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_SH)
        try:
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(item, dict):
                    rows.append(item)
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    return rows


def _attach_ablation_args(parser: argparse.ArgumentParser, suppress: bool = False) -> None:
    default_val: Any = argparse.SUPPRESS if suppress else False
    for flag_str, dest_name in DISABLE_FLAGS:
        parser.add_argument(
            flag_str,
            dest=dest_name,
            action="store_true",
            default=default_val,
            help=f"Disable {dest_name} Ring-1 capability.",
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ajar", description="AJAR v3.6 Verification CLI")
    _attach_ablation_args(parser, suppress=False)
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="Run autonomous security swarm on a repository")
    p_run.add_argument("repo", nargs="?", type=Path, default=None)
    p_run.add_argument("--repo", dest="repo_opt", type=Path, default=None)
    p_run.add_argument("--workers", type=int, default=8)
    p_run.add_argument("--budget-usd", "--budget", dest="budget_usd", type=float, default=50.0)
    p_run.add_argument("--hours", type=float, default=6.0)
    p_run.add_argument("--profile", type=str, default="upstream")
    _attach_ablation_args(p_run, suppress=True)

    p_verify = sub.add_parser("verify", help="Mechanically verify candidate findings to C3")
    p_verify.add_argument("repo", nargs="?", type=Path, default=None)
    p_verify.add_argument("--repo", dest="repo_opt", type=Path, default=None)
    p_verify.add_argument("--candidate-id", type=str, default="")
    p_verify.add_argument("--runs", type=int, default=3)
    p_verify.add_argument("--profile", type=str, default="upstream")
    p_verify.add_argument("--offline", action="store_true", default=False)
    _attach_ablation_args(p_verify, suppress=True)

    p_bench = sub.add_parser("bench", help="Run local on-demand benchmark & ablation suite")
    p_bench.add_argument("suite", nargs="?", type=Path, default=None)
    p_bench.add_argument("--suite", dest="suite_opt", type=Path, default=None)
    p_bench.add_argument("--phase0", action="store_true", default=False)
    p_bench.add_argument("--out", type=Path, default=Path("bench-out"))
    p_bench.add_argument("--workers", type=int, default=4)
    p_bench.add_argument("--budget-usd", "--budget", dest="budget_usd", type=float, default=10.0)
    _attach_ablation_args(p_bench, suppress=True)

    p_report = sub.add_parser("report", help="Export verified C3 advisories and hardening notes")
    p_report.add_argument("repo", nargs="?", type=Path, default=None)
    p_report.add_argument("--repo", dest="repo_opt", type=Path, default=None)
    p_report.add_argument("--out", type=Path, default=None)
    _attach_ablation_args(p_report, suppress=True)

    return parser


def _parse_ablation(ns: argparse.Namespace) -> AblationConfig:
    kwargs = {dest: bool(getattr(ns, dest, False)) for _, dest in DISABLE_FLAGS}
    return AblationConfig(**kwargs)


def _load_recipe(repo: Path, profile: str) -> BuildRecipe:
    recipe_path = ajar_dir(repo) / "build_recipe.json"
    if recipe_path.is_file():
        data = json.loads(recipe_path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return dataclass_from_dict(BuildRecipe, data)
    build_sh = ajar_dir(repo) / "build.sh"
    if build_sh.is_file():
        return BuildRecipe(profile=profile, build_script="bash .ajar/build.sh")
    return BuildRecipe(profile=profile)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    ablation = _parse_ablation(args)

    if args.command == "run":
        repo = (args.repo_opt or args.repo or Path(".")).resolve()
        cfg = RunConfig(
            repo=repo,
            workers=args.workers,
            budget_usd=args.budget_usd,
            hours=args.hours,
            profile=args.profile,
            ablation=ablation,
        )
        from ajar import swarm

        outcome = swarm.run_swarm(cfg)
        if inspect.isawaitable(outcome):
            asyncio.run(outcome)
        return 0

    if args.command == "bench":
        from ajar import bench

        out_dir = Path(args.out).resolve()
        if args.phase0:
            probes = bench.run_phase0_probes(out_dir)
            print(json.dumps({"probes": probes}, sort_keys=True))
            return 0 if all(bool(v.get("passed", False)) for v in probes.values()) else 1
        suite = (args.suite_opt or args.suite or Path("benchmarks")).resolve()
        res = bench.run_bench(suite=suite, out_dir=out_dir, ablation=ablation)
        print(json.dumps(res, sort_keys=True))
        return 0 if res.get("all_passed", False) else 1

    if args.command == "verify":
        from ajar.llm import StdlibLLMClient, has_configured_api_key
        from ajar.verify import verify_candidate

        repo = (args.repo_opt or args.repo or Path(".")).resolve()
        recipe = _load_recipe(repo, args.profile)
        llm = None if args.offline or not has_configured_api_key() else StdlibLLMClient()
        cand_rows = read_jsonl(ajar_dir(repo) / "candidates.jsonl")
        verdicts_file = ajar_dir(repo) / "verdicts.jsonl"
        for row in cand_rows:
            cand = dataclass_from_dict(Candidate, row)
            if args.candidate_id and cand.id != args.candidate_id:
                continue
            verdict = verify_candidate(repo, cand, recipe, llm=llm, runs=args.runs)
            append_jsonl(verdicts_file, verdict)
        return 0

    if args.command == "report":
        import importlib.util

        rep_path = Path(__file__).resolve().parents[2] / "extra" / "report.py"
        spec = importlib.util.spec_from_file_location("ajar_extra_report", rep_path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Unable to load report exporter: {rep_path}")
        mod: Any = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        repo = (args.repo_opt or args.repo or Path(".")).resolve()
        out_dir = (args.out or (ajar_dir(repo) / "reports")).resolve()
        rep: dict[str, Any] = mod.export_reports(repo, out_dir)
        return 0 if rep.get("lint_passed", True) else 1

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
