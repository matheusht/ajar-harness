"""Ajar v3.5 8-Verb CLI (`reality`, `microfuzz`, `prove`, `chain`, `critique`, `campaign`, `bench`, `report`)."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Sequence

from ajar import MAX_PYTHON_LOC, __version__
from ajar.campaign import CampaignSentinel
from ajar.chain_cmd import discover_candidate_chains, prove_chain
from ajar.microfuzz import run_microfuzz
from ajar.reality import build_reality_model
from ajar.schemas import ChainCandidate, Finding, ajar_dir, read_jsonl
from ajar.verify import critique_finding, prove_finding

BANNED_VOICE_TERMS: tuple[str, ...] = (
    "sprt",
    "rmst",
    "map-elites",
    "lyapunov",
    "ah-puct",
    "macaroon",
    "catastrophic",
    "apocalyptic",
    "devastating",
    "earth-shattering",
)


def count_ajar_python_loc() -> tuple[int, dict[str, int]]:
    pkg_dir = Path(__file__).resolve().parent
    per_file: dict[str, int] = {}
    for py_file in sorted(pkg_dir.glob("*.py")):
        per_file[py_file.name] = sum(1 for _ in py_file.open(encoding="utf-8"))
    return sum(per_file.values()), per_file


def lint_report_text(text: str) -> tuple[int, list[str]]:
    """Score engineering clarity 0..100 (enforces 3-Second Human Test + required technical sections)."""
    issues: list[str] = []
    lower = text.lower()
    for term in BANNED_VOICE_TERMS:
        if re.search(rf"\b{re.escape(term)}\b", lower):
            issues.append(f"banned_jargon_or_hype:{term}")
    for section in ("## Root Cause", "## Minimal Reproduction", "## Impact", "## Minimal Patch"):
        if section not in text:
            issues.append(f"missing_section:{section}")
    score = max(0, 100 - 25 * len(issues))
    return score, issues


def render_finding_markdown(record: dict[str, object]) -> str:
    patch_body = str(record.get("patch_diff") or "No code patch required (conformance / hardening note).").strip()
    raw_path = record.get("entry_to_sink")
    entry_path = " -> ".join(str(x) for x in raw_path) if isinstance(raw_path, list) else ""
    return "\n".join(
        [
            f"# {record['id']}: {record['title']}",
            "",
            f"- **Severity:** `{record['severity']}`",
            f"- **Build Profile:** `{record.get('build_profile', 'upstream')}`",
            f"- **Cross-Seam Lens:** `{record.get('lens', 'L1_PARSER_DIFFERENTIAL')}`",
            f"- **Entry -> Sink:** `{entry_path}` (`{record.get('sink_symbol', '')}`)",
            "",
            "## Root Cause",
            str(record.get("root_cause") or record.get("notes") or "Deterministic boundary violation verified in clean worktree."),
            "",
            "## Minimal Reproduction",
            "```bash",
            str(record.get("repro_script", "")).strip(),
            "```",
            "",
            "## Impact",
            str(record.get("impact") or f"Verified `{record['severity']}` boundary impact on `{record.get('build_profile', 'upstream')}`."),
            "",
            "## Minimal Patch",
            "```diff",
            patch_body,
            "```",
            "",
        ]
    )


def export_reports(repo: Path, out_dir: Path) -> dict[str, list[Path]]:
    """Export clean reports: omit withdrawn drafts (`DEC-0139`) & split advisories vs hardening-notes (`D7`)."""
    raw_findings = read_jsonl(ajar_dir(repo) / "findings.jsonl")
    latest_by_id: dict[str, dict[str, object]] = {}
    for item in raw_findings:
        fid = str(item.get("id", ""))
        if fid:
            latest_by_id[fid] = item

    written: dict[str, list[Path]] = {"advisories": [], "hardening_notes": []}
    for fid, rec in sorted(latest_by_id.items()):
        if rec.get("withdrawn", False):
            continue
        category = str(rec.get("category", "advisory"))
        status = str(rec.get("status", ""))
        if category == "advisory":
            if status != "PROVED":
                continue
            dest = out_dir / "advisories" / f"{fid}.md"
            bucket = "advisories"
        elif category == "hardening":
            if status not in {"PROVED", "HARDENING_NOTE"}:
                continue
            dest = out_dir / "hardening-notes" / f"{fid}.md"
            bucket = "hardening_notes"
        else:
            continue

        md = render_finding_markdown(rec)
        score, issues = lint_report_text(md)
        if score < 100:
            raise ValueError(f"Report {fid} failed voice lint ({score}/100): {issues}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(md, encoding="utf-8")
        written[bucket].append(dest)
    return written


def run_local_bench(check_loc: bool = True, with_log: Path | None = None, without_log: Path | None = None) -> dict[str, object]:
    """Local-only CLI yardstick (`0` CI gates): enforces `< 1,800` LoC ceiling and compares With/Without runs."""
    total_loc, per_file = count_ajar_python_loc()
    summary: dict[str, object] = {
        "version": __version__,
        "total_python_loc": total_loc,
        "max_python_loc": MAX_PYTHON_LOC,
        "loc_ok": total_loc <= MAX_PYTHON_LOC,
        "files": per_file,
    }
    if check_loc and total_loc > MAX_PYTHON_LOC:
        raise SystemExit(f"Elon Deletion Gate failed: {total_loc} LoC > {MAX_PYTHON_LOC} ceiling")
    if with_log and without_log:
        w_proved = sum(1 for r in read_jsonl(with_log) if r.get("status") == "PROVED")
        wo_proved = sum(1 for r in read_jsonl(without_log) if r.get("status") == "PROVED")
        summary["ablation_delta_proved"] = w_proved - wo_proved
        summary["with_proved"] = w_proved
        summary["without_proved"] = wo_proved
    return summary


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ajar", description="Ajar v3.5 First-Principles Security Harness")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_real = sub.add_parser("reality", help="Build or refresh .ajar/REALITY.md")
    p_real.add_argument("repo", type=Path)
    p_real.add_argument("--profiles", default="upstream", help="Comma-separated build profiles")

    p_fuzz = sub.add_parser("microfuzz", help="Run boundary + stateful microfuzz with entrypoint replay")
    p_fuzz.add_argument("repo", type=Path)
    p_fuzz.add_argument("--entrypoint", required=True, help="Command template containing {input}")
    p_fuzz.add_argument("--mode", default="both", choices=("boundary", "stateful", "both"))
    p_fuzz.add_argument("--iterations", type=int, default=32)

    p_prove = sub.add_parser("prove", help="Prove a candidate finding JSON in a clean worktree")
    p_prove.add_argument("repo", type=Path)
    p_prove.add_argument("--finding-json", type=Path, required=True)
    p_prove.add_argument("--test-cmd", default=None)
    p_prove.add_argument("--concurrency-mode", default=None, choices=("deterministic", "statistical"))

    p_chain = sub.add_parser("chain", help="Discover or prove CAN -> Bridge -> WISH chains")
    p_chain.add_argument("repo", type=Path)
    p_chain.add_argument("--e2e-script", default=None)
    p_chain.add_argument("--chain-id", default=None)

    p_crit = sub.add_parser("critique", help="Run 4x3 Diagonal Kill Matrix + Cross-Family Critic")
    p_crit.add_argument("repo", type=Path)
    p_crit.add_argument("--finding-json", type=Path, required=True)
    p_crit.add_argument("--critic-cmd", default=None)

    p_camp = sub.add_parser("campaign", help="Bootstrap 8-worker stigmergic campaign sentinel")
    p_camp.add_argument("repo", type=Path)
    p_camp.add_argument("--workers", type=int, default=8)
    p_camp.add_argument("--budget-usd", type=float, default=100.0)
    p_camp.add_argument("--seams", default="L1_PARSER_DIFFERENTIAL,L2_POLICY_ALIAS_GAP,L3_WRAPPER_ENGINE_SEAM")

    p_bench = sub.add_parser("bench", help="Local-only LoC & With-vs-Without ablation yardstick (0 CI gates)")
    p_bench.add_argument("--check-loc", action="store_true", default=True)
    p_bench.add_argument("--with-log", type=Path, default=None)
    p_bench.add_argument("--without-log", type=Path, default=None)

    p_rep = sub.add_parser("report", help="Export 100/100 linted advisories vs hardening-notes")
    p_rep.add_argument("repo", type=Path)
    p_rep.add_argument("--out", type=Path, required=True)
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd == "reality":
        profs = tuple(s.strip() for s in args.profiles.split(",") if s.strip())
        out = build_reality_model(args.repo, profiles=profs)
        print(json.dumps({"reality_md": str(out)}))
        return 0
    if args.cmd == "microfuzz":
        hits = run_microfuzz(args.repo, args.entrypoint, mode=args.mode, iterations=args.iterations)
        print(json.dumps({"verified_hits": [h.to_dict() for h in hits]}))
        return 0
    if args.cmd == "prove":
        f_obj = Finding(**json.loads(args.finding_json.read_text(encoding="utf-8")))
        res = prove_finding(args.repo, f_obj, test_cmd=args.test_cmd, concurrency_mode=args.concurrency_mode)
        print(json.dumps(res.to_dict()))
        return 0 if res.status == "PROVED" else 1
    if args.cmd == "chain":
        discovered = discover_candidate_chains(args.repo)
        if args.chain_id and args.e2e_script:
            target = next((c for c in discovered if c.id == args.chain_id), None) or ChainCandidate(
                id=args.chain_id, can_id="CAN", wish_id="WISH", bridge_feature="cli_bridge", seam_tag="cli"
            )
            target.e2e_repro_script = args.e2e_script
            proved = prove_chain(args.repo, target)
            print(json.dumps(proved.to_dict()))
            return 0 if proved.status == "PROVED" else 1
        print(json.dumps({"discovered": [c.to_dict() for c in discovered]}))
        return 0
    if args.cmd == "critique":
        f_obj = Finding(**json.loads(args.finding_json.read_text(encoding="utf-8")))
        res = critique_finding(args.repo, f_obj, critic_cmd=args.critic_cmd)
        print(json.dumps(res.to_dict()))
        return 0 if res.critic_verdict == "VERIFIED" else 1
    if args.cmd == "campaign":
        seams = [s.strip() for s in args.seams.split(",") if s.strip()]
        sentinel = CampaignSentinel(args.repo, seams=seams, max_workers=args.workers, budget_usd=args.budget_usd)
        slots = sentinel.bootstrap_slots()
        print(json.dumps({"bootstrapped_slots": len(slots), "max_cogs_usd": sentinel.max_cogs_usd}))
        return 0
    if args.cmd == "bench":
        print(json.dumps(run_local_bench(args.check_loc, args.with_log, args.without_log)))
        return 0
    if args.cmd == "report":
        exported = export_reports(args.repo, args.out)
        print(json.dumps({k: [str(p) for p in v] for k, v in exported.items()}))
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
