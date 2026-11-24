"""Stigmergic `CAN <-> [Normal Feature Bridge] <-> WISH` matcher and clean-worktree E2E chain prover."""

from __future__ import annotations

from pathlib import Path

from ajar.reality import record_falsified_hypothesis
from ajar.schemas import ChainCandidate, Primitive, ajar_dir, append_jsonl, read_jsonl
from ajar.worktree import clean_worktree, run_hermetic


def post_primitive(repo: Path, primitive: Primitive) -> Path:
    if primitive.kind not in {"CAN", "WISH"}:
        raise ValueError(f"Primitive kind must be 'CAN' or 'WISH', got {primitive.kind!r}")
    path = ajar_dir(repo) / "primitives.jsonl"
    append_jsonl(path, primitive.to_dict())
    return path


def discover_candidate_chains(repo: Path) -> list[ChainCandidate]:
    """Pair `CAN` primitives with matching `WISH` preconditions bridged by normal product features."""
    raw = read_jsonl(ajar_dir(repo) / "primitives.jsonl")
    cans = [r for r in raw if r.get("kind") == "CAN"]
    wishes = [r for r in raw if r.get("kind") == "WISH"]
    existing_ids = {c.get("id") for c in read_jsonl(ajar_dir(repo) / "chains.jsonl")}

    discovered: list[ChainCandidate] = []
    for can in cans:
        can_cap = str(can.get("capability", "")).strip().lower()
        can_seam = str(can.get("seam_tag", "")).strip().lower()
        for wish in wishes:
            preconds = {str(p).strip().lower() for p in wish.get("preconditions", [])}
            wish_cap = str(wish.get("capability", "")).strip().lower()
            wish_seam = str(wish.get("seam_tag", "")).strip().lower()
            cap_match = bool(can_cap) and (can_cap in preconds or can_cap == wish_cap)
            seam_match = bool(can_seam) and can_seam == wish_seam
            if not (cap_match or seam_match):
                continue
            chain_id = f"CHAIN-{can['id']}-TO-{wish['id']}"
            if chain_id in existing_ids:
                continue
            bridge = (
                can.get("bridge_hint")
                or wish.get("bridge_hint")
                or "normal_product_feature_bridge"
            )
            cand = ChainCandidate(
                id=chain_id,
                can_id=str(can["id"]),
                wish_id=str(wish["id"]),
                bridge_feature=str(bridge),
                seam_tag=str(can.get("seam_tag") or wish.get("seam_tag") or "cross_seam"),
            )
            append_jsonl(ajar_dir(repo) / "chains.jsonl", cand.to_dict())
            existing_ids.add(chain_id)
            discovered.append(cand)
    return discovered


def prove_chain(
    repo: Path,
    chain: ChainCandidate,
    sink_symbol: str = "",
    mount_deps: list[Path] | None = None,
) -> ChainCandidate:
    """Require a single clean-worktree end-to-end script executing Hop 1 -> Bridge -> Hop N."""
    if not chain.e2e_repro_script.strip():
        chain.status = "KILLED"
        chain.notes = "Missing end-to-end clean-worktree reproduction script."
        append_jsonl(ajar_dir(repo) / "chains.jsonl", chain.to_dict())
        return chain

    with clean_worktree(repo, mount_deps=mount_deps) as (wt, dep_env):
        res = run_hermetic(
            chain.e2e_repro_script,
            cwd=wt,
            profile=chain.build_profile,
            extra_env=dep_env,
        )
        trace = res.stderr + "\n" + res.stdout
        if res.returncode in (0, 124):
            chain.status = "KILLED"
            chain.notes = f"E2E chain script did not trigger oracle on clean HEAD (rc={res.returncode})."
            record_falsified_hypothesis(
                repo, f"`{chain.id}` (`{chain.can_id} -> {chain.bridge_feature} -> {chain.wish_id}`) failed clean E2E replay."
            )
        elif sink_symbol and sink_symbol not in trace:
            chain.status = "KILLED"
            chain.notes = f"E2E chain triggered outside target sink {sink_symbol!r}."
        else:
            chain.status = "PROVED"
            chain.notes = f"Clean-worktree E2E multi-hop chain verified via `{chain.bridge_feature}`."

    append_jsonl(ajar_dir(repo) / "chains.jsonl", chain.to_dict())
    return chain
