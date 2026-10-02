#!/usr/bin/env python3
"""Campaign / candidate contract gate (GEPA Phase 1).

Stdlib-only. Enforces the manifest contracts (schemas/campaign-manifest.schema.json,
schemas/candidate-manifest.schema.json) BEFORE any optimizer output is trusted. This is the
tamper-detection and scope fence that lets a shadow campaign run without letting a candidate quietly
change what 'winning' means.

A candidate is BLOCKED if any of these hold:
  - it touches a file outside its single declared mutation_target (undeclared mutation);
  - it touches an immutable file (evaluator, oracle, routing gold, crosswalk, casebooks, corpora,
    hermetic targets, schemas, budgets) — the 'what winning means' set;
  - its declared budget differs from the campaign budget (no buying extra budget);
  - a frozen campaign input's sha256 has drifted (benchmark/evaluator tamper);
  - a diff, evidence bundle, or frozen input path escapes the repository root;
  - its diff hash does not match the diff file (candidate tamper);
  - its evidence bundle is missing;
  - it is a baseline but is not a no-op (a control must touch nothing).

A no-op baseline (is_baseline=true, touched_files empty) is ALLOWED — it is the retained control.

Usage:
  python3 tools/check-campaign.py --campaign <campaign.json> --candidate <candidate.json>
  python3 tools/check-campaign.py --self-test
"""

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile

from regular_file_io import load_json, read_regular_text

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Built-in immutable set: enforced regardless of what a campaign manifest declares. These are the
# files that define acceptance — a candidate that edits any of them is gaming the evaluator.
DEFAULT_IMMUTABLE = [
    "tools/score-routing.py",
    "tools/score-false-discovery.py",
    "tools/run-qualification.py",
    "tools/run-hermetic-bola.py",
    "tools/check-conformance.py",
    "tools/check-campaign.py",
    "tools/regular_file_io.py",
    "evals/routing/gold/",
    "evals/qualification/crosswalk.json",
    "evals/hermetic/targets/",
    "fixtures/false-discovery/",
    "fixtures/adversarial-candidates/",
    "casebooks/",
    "schemas/",
]
CANDIDATE_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z", re.ASCII)


def load(path):
    return load_json(path)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _under(path, prefix):
    """True if path is the prefix file, or sits under the prefix directory."""
    if prefix.endswith("/"):
        return path.startswith(prefix)
    return path == prefix or path.startswith(prefix + "/")


def immutable_paths(campaign):
    paths = list(DEFAULT_IMMUTABLE) + list(campaign.get("immutable", []))
    paths.extend(spec["path"] for spec in campaign.get("frozen_inputs", {}).values()
                 if isinstance(spec, dict) and isinstance(spec.get("path"), str) and spec["path"])
    return paths


def valid_candidate_id(candidate_id):
    return isinstance(candidate_id, str) and CANDIDATE_ID_RE.fullmatch(candidate_id) is not None


def candidate_dir(campaign_path, candidate_id):
    if not valid_candidate_id(candidate_id):
        raise ValueError("candidate_id must be a safe path component")
    return os.path.join(os.path.dirname(campaign_path), "candidates", candidate_id)


def candidate_manifest_path(root, campaign_path, entry):
    if not isinstance(entry, dict) or not valid_candidate_id(entry.get("candidate_id")):
        raise ValueError("candidate entry must have a safe candidate_id")
    manifest = entry.get("manifest")
    if not isinstance(manifest, str) or not manifest or os.path.isabs(manifest):
        raise ValueError("candidate manifest path must be repository-relative")
    root = os.path.realpath(root)
    campaign_path = os.path.realpath(os.path.abspath(campaign_path))
    expected = os.path.abspath(os.path.join(candidate_dir(campaign_path, entry["candidate_id"]), "candidate-manifest.json"))
    expected_rel = os.path.relpath(expected, root).replace(os.sep, "/")
    resolved = repo_file_path(root, manifest)
    try:
        expected_inside = os.path.commonpath((root, os.path.realpath(expected))) == root
    except ValueError:
        expected_inside = False
    if (manifest != expected_rel or resolved is None or not expected_inside or os.path.abspath(resolved) != expected
            or os.path.realpath(expected) != expected or not os.path.isfile(expected)):
        raise ValueError("candidate manifest must be a regular file at this campaign's candidates/<id>/candidate-manifest.json")
    return expected


def repo_file_path(root, relative_path):
    """Resolve a repository-relative artifact path, rejecting absolute and symlink escapes."""
    if not isinstance(relative_path, str) or not relative_path or os.path.isabs(relative_path):
        return None
    root = os.path.realpath(root)
    path = os.path.join(root, relative_path)
    resolved = os.path.realpath(path)
    try:
        return path if os.path.commonpath((root, resolved)) == root else None
    except ValueError:
        return None


def git_patch_analysis(diff_path, root):
    """Derive touched paths and detect UNSUPPORTED patch forms using git's own parser. The header-only
    parser missed mode-only, binary, rename, copy, and symlink patches — a candidate could change a
    file's mode (e.g. make the conformance checker executable) with a patch that has no ---/+++ headers
    and so derived no paths. Returns (paths, unsupported_reasons). Fail closed: callers must block on
    any unsupported reason and on a non-empty patch that yields no paths."""
    paths, unsupported = set(), []
    num = subprocess.run(["git", "-C", root, "apply", "--numstat", "-z", diff_path],
                         capture_output=True, text=True)
    if num.returncode == 0:
        for record in num.stdout.split("\0"):
            parts = record.split("\t", 2)
            if len(parts) == 3:
                added, removed, p = parts
                if added == "-" and removed == "-":
                    unsupported.append(f"binary patch: {p}")
                if p:
                    paths.add(p)
    else:
        unsupported.append(f"git could not parse the patch: {num.stderr.strip()[:120]}")
    summ = subprocess.run(["git", "-C", root, "apply", "--summary", diff_path], capture_output=True, text=True)
    for ln in summ.stdout.splitlines():
        t = ln.strip()
        if t.startswith("rename ") or t.startswith("copy ") or t.startswith("mode change"):
            unsupported.append(t)
        if "120000" in t:
            unsupported.append(f"symlink: {t}")
    try:
        text = read_regular_text(diff_path, encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        unsupported.append(f"diff cannot be read as UTF-8: {exc}")
        text = ""
    for ln in text.splitlines():
        m = re.match(r"diff --git a/(.+?) b/(.+)$", ln)
        if m:
            paths.add(m.group(1)); paths.add(m.group(2))
        if ln.startswith("--- ") or ln.startswith("+++ "):
            p = ln[4:].split("\t")[0].strip()
            if p not in ("/dev/null", ""):
                paths.add(p[2:] if p[:2] in ("a/", "b/") else p)
        if ln.startswith("old mode") or ln.startswith("new mode"):
            unsupported.append("mode change")
        if ln.startswith("rename from") or ln.startswith("rename to"):
            unsupported.append("rename")
        if ln.startswith("copy from") or ln.startswith("copy to"):
            unsupported.append("copy")
        if ln.startswith("GIT binary patch") or ln.startswith("Binary files"):
            unsupported.append("binary patch")
        if "120000" in ln:
            unsupported.append("symlink mode")
    return {p for p in paths if p and p != "/dev/null"}, sorted(set(unsupported))


def gate(campaign, candidate, root):
    """Return (verdict, reasons). verdict is 'allow' or 'block'."""
    reasons = []

    if not valid_candidate_id(candidate.get("candidate_id")):
        reasons.append("candidate_id must be a safe path component (1-128 ASCII letters, digits, '.', '_', or '-')")

    if candidate.get("campaign_id") != campaign.get("campaign_id"):
        reasons.append(f"campaign_id mismatch: candidate {candidate.get('campaign_id')} != {campaign.get('campaign_id')}")

    targets = {t["mutation_target"] for t in campaign.get("tracks", [])}
    mt = candidate.get("mutation_target")
    if mt not in targets:
        reasons.append(f"mutation_target '{mt}' is not a declared track target {sorted(targets)}")

    declared = set(candidate.get("touched_files", []))
    is_baseline = bool(candidate.get("is_baseline"))

    if is_baseline and declared:
        reasons.append("baseline candidate must be a no-op (touched_files must be empty)")

    # Derive the diff's ACTUAL paths and require the declaration matches exactly. Then run the
    # mutation-target / immutable checks against the UNION, so a file hidden from touched_files but
    # present in the diff still blocks.
    diff = candidate.get("diff")
    diff_path = repo_file_path(root, diff) if diff else None
    derived = set()
    if diff and diff_path is None:
        reasons.append("diff path must be repository-relative and remain inside the repository")
    elif not diff or not os.path.isfile(diff_path):
        if not is_baseline:
            reasons.append(f"diff missing: {diff}")
    else:
        if sha256_file(diff_path) != candidate.get("candidate_hash"):
            reasons.append("candidate_hash does not match diff contents (tamper)")
        size = os.path.getsize(diff_path)
        if is_baseline:
            if size != 0:
                reasons.append("baseline candidate diff must be byte-empty")
        else:
            if size == 0:
                reasons.append("non-baseline candidate diff is empty (fail closed)")
            derived, unsupported = git_patch_analysis(diff_path, root)
            if unsupported:
                reasons.append(f"unsupported patch form(s) — mode/binary/rename/copy/symlink rejected: {unsupported}")
            if not derived:
                reasons.append("diff derives no touched paths (fail closed)")
            if derived != declared:
                reasons.append(f"declared touched_files {sorted(declared)} do not match diff-derived paths "
                               f"{sorted(derived)} (a candidate cannot hide edits from the manifest)")

    effective = declared | derived
    if mt:
        stray = sorted(f for f in effective if not _under(f, mt))
        if stray:
            reasons.append(f"touches files outside mutation_target '{mt}': {stray}")

    immutable = immutable_paths(campaign)
    leaked = sorted(f for f in effective if any(_under(f, p) for p in immutable))
    if leaked:
        reasons.append(f"touches immutable (evaluator/gold/casebook/budget/schema) files: {leaked}")

    cb = candidate.get("budget")
    if cb is not None and cb != campaign.get("budgets"):
        reasons.append("candidate budget differs from campaign budget")

    eb = candidate.get("evidence_bundle")
    evidence_path = repo_file_path(root, eb) if eb else None
    if eb and evidence_path is None:
        reasons.append("evidence_bundle path must be repository-relative and remain inside the repository")
    elif not eb or not os.path.isfile(evidence_path):
        reasons.append(f"evidence bundle missing: {eb}")

    for name, spec in campaign.get("frozen_inputs", {}).items():
        frozen_path = spec.get("path", "")
        p = repo_file_path(root, frozen_path)
        if p is None:
            reasons.append(f"frozen input '{name}' path must be repository-relative and remain inside the repository: {frozen_path}")
            continue
        if not os.path.isfile(p):
            reasons.append(f"frozen input '{name}' missing: {spec.get('path')}")
        elif sha256_file(p) != spec.get("sha256"):
            reasons.append(f"frozen input '{name}' drifted ({spec.get('path')})")

    return ("block" if reasons else "allow"), reasons


def report(campaign, candidate, root):
    verdict, reasons = gate(campaign, candidate, root)
    cid = candidate.get("candidate_id", "?")
    print(f"candidate {cid}: {verdict.upper()}")
    for r in reasons:
        print(f"  - {r}")
    return verdict == "allow"


# ---- self-test: build a tmp workspace and assert each criterion blocks/allows ----

def _write(root, rel, text):
    p = os.path.join(root, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as fh:
        fh.write(text)
    return p


def _diff_for(paths):
    """A well-formed multi-file unified diff touching exactly `paths`."""
    out = []
    for p in paths:
        out += [f"--- a/{p}", f"+++ b/{p}", "@@ -1 +1,2 @@", " base", "+variant"]
    return ("\n".join(out) + "\n") if out else ""


CARD = "skills/techniques/task-reframing/SKILL.md"


def self_test():
    ok = True
    with tempfile.TemporaryDirectory() as root:
        subprocess.run(["git", "-C", root, "init", "-q"], check=False)   # git's patch parser needs a repo
        frozen_rel = "evals/routing/gold/case-x.gold.json"
        _write(root, frozen_rel, '{"case":"x"}\n')
        frozen_hash = sha256_file(os.path.join(root, frozen_rel))
        bundle = "evals/c/evidence-bundle.md"
        _write(root, bundle, "# why\n")

        def mkdiff(name, paths):
            rel = f"evals/c/{name}.diff"
            _write(root, rel, _diff_for(paths))
            return rel, sha256_file(os.path.join(root, rel))

        card_diff, card_h = mkdiff("card", [CARD])

        campaign = {
            "campaign_id": "camp-1", "created": "2026-06-26",
            "tracks": [{"name": "task-reframing", "mutation_target": "skills/techniques/task-reframing/", "kind": "existing-card-variant"}],
            "mutable_allowlist": ["skills/techniques/task-reframing/"], "immutable": [],
            "frozen_inputs": {"routing-gold-x": {"path": frozen_rel, "sha256": frozen_hash}},
            "budgets": {"model_calls": 10, "target_calls": 20, "tokens": None},
            "benchmark_set": ["routing:case-x"],
        }
        base = {
            "candidate_id": "cand-ok", "campaign_id": "camp-1", "parent": "baseline",
            "track": "task-reframing", "mutation_target": "skills/techniques/task-reframing/",
            "touched_files": [CARD], "diff": card_diff, "candidate_hash": card_h, "evidence_bundle": bundle,
        }

        campaign_file = _write(root, "evals/c/campaign.json", json.dumps(campaign))
        if hasattr(os, "mkfifo"):
            candidate_file = _write(root, "evals/c/candidate.json", json.dumps(base))
            for label, campaign_arg, candidate_arg in (
                ("FIFO campaign input", os.path.join(root, "evals/c/campaign.fifo"), candidate_file),
                ("FIFO candidate input", campaign_file, os.path.join(root, "evals/c/candidate.fifo")),
            ):
                fifo = campaign_arg if label == "FIFO campaign input" else candidate_arg
                os.mkfifo(fifo)
                try:
                    result = subprocess.run(
                        [sys.executable, os.path.abspath(__file__), "--campaign", campaign_arg,
                         "--candidate", candidate_arg],
                        capture_output=True, text=True, timeout=2,
                    )
                    rejected = result.returncode == 2 and "input error:" in result.stderr
                except subprocess.TimeoutExpired:
                    rejected = False
                if not rejected:
                    ok = False
                    print(f"[self-test] {label} was not rejected promptly")

        invalid_candidate = os.path.join(root, "evals/c/invalid-candidate.json")
        with open(invalid_candidate, "wb") as handle:
            handle.write(b"\xff")
        result = subprocess.run(
            [sys.executable, os.path.abspath(__file__), "--campaign", campaign_file,
             "--candidate", invalid_candidate],
            capture_output=True, text=True, timeout=2,
        )
        if result.returncode != 2 or "input error:" not in result.stderr or "Traceback" in result.stderr:
            ok = False
            print("[self-test] invalid UTF-8 candidate returned an unhandled error")

        def expect(label, cand, want, camp=campaign):
            nonlocal ok
            verdict, reasons = gate(camp, cand, root)
            good = verdict == want
            print(f"[self-test] {label}: {verdict} (want {want}) {'ok' if good else 'MISMATCH ' + str(reasons)}")
            if not good:
                ok = False

        expect("clean candidate allows", base, "allow")
        expect("candidate ID cannot escape the candidate directory",
               dict(base, candidate_id="../../outside"), "block")

        with tempfile.TemporaryDirectory(prefix="campaign-artifacts-outside-") as outside:
            outside_diff = os.path.join(outside, "candidate.diff")
            with open(outside_diff, "w") as handle:
                handle.write(_diff_for([CARD]))
            outside_hash = sha256_file(outside_diff)
            outside_rel = os.path.relpath(outside_diff, root)
            expect("candidate diff outside repository blocks",
                   dict(base, diff=outside_rel, candidate_hash=outside_hash), "block")
            expect("absolute candidate diff blocks",
                   dict(base, diff=outside_diff, candidate_hash=outside_hash), "block")

            symlink_diff = os.path.join(root, "evals/c/outside.diff")
            os.symlink(outside_diff, symlink_diff)
            expect("candidate diff symlink outside repository blocks",
                   dict(base, diff=os.path.relpath(symlink_diff, root), candidate_hash=outside_hash), "block")

            outside_evidence = os.path.join(outside, "evidence.md")
            with open(outside_evidence, "w") as handle:
                handle.write("# Evidence bundle\n\n- campaign: c\n- mutation target: x\n- eligibility: candidate\n")
            expect("evidence bundle outside repository blocks",
                   dict(base, evidence_bundle=os.path.relpath(outside_evidence, root)), "block")

            frozen_campaign = dict(campaign, frozen_inputs={"outside": {
                "path": outside_rel, "sha256": outside_hash,
            }})
            expect("frozen input outside repository blocks", base, "block", camp=frozen_campaign)

        arrow_campaign = dict(
            campaign,
            tracks=[{"name": "docs", "mutation_target": "docs/"}],
            mutable_allowlist=["docs/"], frozen_inputs={},
        )
        for name, arrow_path in (("plain-arrow", "docs/frozen=>input.txt"),
                                 ("spaced-arrow", "docs/frozen => input.txt")):
            arrow_diff, arrow_hash = mkdiff(name, [arrow_path])
            arrow_candidate = dict(
                base, candidate_id=f"cand-{name}", track="docs", mutation_target="docs/",
                touched_files=[arrow_path], diff=arrow_diff, candidate_hash=arrow_hash,
            )
            try:
                expect(f"literal arrow in '{arrow_path}' is preserved", arrow_candidate, "allow",
                       camp=arrow_campaign)
            except Exception as exc:
                ok = False
                print(f"[self-test] filename containing => crashed the gate: {type(exc).__name__}: {exc}")

        stray_diff, stray_h = mkdiff("stray", [CARD, "engine/routing.md"])
        expect("undeclared (out-of-target) file blocks",
               dict(base, candidate_id="cand-stray", touched_files=[CARD, "engine/routing.md"],
                    diff=stray_diff, candidate_hash=stray_h), "block")

        imm_diff, imm_h = mkdiff("imm", [CARD, frozen_rel])
        expect("declared immutable touch blocks",
               dict(base, candidate_id="cand-immutable", touched_files=[CARD, frozen_rel],
                    diff=imm_diff, candidate_hash=imm_h), "block")

        # P0: a candidate whose diff edits the conformance checker while declaring ONLY the card.
        p0_diff, p0_h = mkdiff("p0", [CARD, "tools/check-conformance.py"])
        expect("P0: diff edits an immutable checker but declares only the card -> block",
               dict(base, candidate_id="cand-p0-hidden", touched_files=[CARD],
                    diff=p0_diff, candidate_hash=p0_h), "block")

        reader_diff, reader_h = mkdiff("reader", ["tools/regular_file_io.py"])
        reader_campaign = dict(
            campaign,
            tracks=[{"name": "reader", "mutation_target": "tools/"}],
            mutable_allowlist=["tools/"],
        )
        reader_candidate = dict(
            base, candidate_id="cand-reader", mutation_target="tools/",
            touched_files=["tools/regular_file_io.py"], diff=reader_diff,
            candidate_hash=reader_h,
        )
        expect("P0: candidate cannot change the gate's file reader -> block",
               reader_candidate, "block", camp=reader_campaign)

        pinned_rel = "docs/frozen-input.txt"
        pinned_hash = sha256_file(_write(root, pinned_rel, "frozen\n"))
        pinned_campaign = dict(
            campaign,
            tracks=[{"name": "docs", "mutation_target": "docs/"}],
            mutable_allowlist=["docs/"],
            frozen_inputs={"frozen-doc": {"path": pinned_rel, "sha256": pinned_hash}},
        )
        pinned_diff, pinned_diff_hash = mkdiff("pinned", [pinned_rel])
        pinned_candidate = dict(
            base, candidate_id="cand-pinned-input", mutation_target="docs/",
            touched_files=[pinned_rel], diff=pinned_diff, candidate_hash=pinned_diff_hash,
        )
        expect("P0: candidate cannot change a frozen input -> block",
               pinned_candidate, "block", camp=pinned_campaign)

        # touched_files claims a file the diff does not actually touch.
        expect("declared != diff-derived paths blocks",
               dict(base, candidate_id="cand-overdeclare", touched_files=[CARD, "engine/routing.md"]), "block")

        expect("budget change blocks", dict(base, candidate_id="cand-budget",
               budget={"model_calls": 999, "target_calls": 20, "tokens": None}), "block")
        expect("missing evidence bundle blocks", dict(base, candidate_id="cand-nobundle",
               evidence_bundle="evals/c/missing.md"), "block")
        expect("diff hash tamper blocks", dict(base, candidate_id="cand-tamper", candidate_hash="deadbeef"), "block")

        empty_diff, empty_h = mkdiff("empty", [])
        baseline = {
            "candidate_id": "cand-baseline", "campaign_id": "camp-1", "parent": "baseline",
            "track": "task-reframing", "mutation_target": "skills/techniques/task-reframing/",
            "touched_files": [], "diff": empty_diff, "candidate_hash": empty_h,
            "evidence_bundle": bundle, "is_baseline": True,
        }
        expect("no-op baseline allows", baseline, "allow")
        expect("baseline that mutates blocks", dict(baseline, candidate_id="cand-baseline-dirty",
               touched_files=[CARD], diff=card_diff, candidate_hash=card_h), "block")

        drifted = dict(campaign, frozen_inputs={"routing-gold-x": {"path": frozen_rel, "sha256": "0" * 64}})
        expect("frozen-input drift blocks", base, "block", camp=drifted)

        # P0 (round 2): Git patch forms that a header-only parser misses.
        def mkraw(name, text):
            _write(root, f"evals/c/{name}.diff", text)
            return f"evals/c/{name}.diff", sha256_file(os.path.join(root, f"evals/c/{name}.diff"))

        mode_rel, mode_h = mkraw("mode", "diff --git a/tools/check-conformance.py b/tools/check-conformance.py\n"
                                 "old mode 100644\nnew mode 100755\n")
        expect("P0: mode-only patch declared as empty baseline -> block",
               dict(base, candidate_id="cand-mode-baseline", is_baseline=True, touched_files=[],
                    diff=mode_rel, candidate_hash=mode_h), "block")
        expect("P0: mode-only patch on the checker (non-baseline) -> block",
               dict(base, candidate_id="cand-mode", touched_files=["tools/check-conformance.py"],
                    diff=mode_rel, candidate_hash=mode_h), "block")

        bin_rel, bin_h = mkraw("bin", "diff --git a/skills/techniques/task-reframing/SKILL.md "
                               "b/skills/techniques/task-reframing/SKILL.md\nGIT binary patch\nliteral 3\nabc\n")
        expect("P0: binary patch -> block",
               dict(base, candidate_id="cand-bin", touched_files=[CARD], diff=bin_rel, candidate_hash=bin_h), "block")

        ren_rel, ren_h = mkraw("ren", "diff --git a/skills/techniques/task-reframing/SKILL.md b/skills/techniques/x.md\n"
                               "rename from skills/techniques/task-reframing/SKILL.md\nrename to skills/techniques/x.md\n")
        expect("P0: rename patch -> block",
               dict(base, candidate_id="cand-ren", touched_files=[CARD], diff=ren_rel, candidate_hash=ren_h), "block")

        invalid_rel = "evals/c/invalid-utf8.diff"
        invalid_path = os.path.join(root, invalid_rel)
        with open(invalid_path, "wb") as handle:
            handle.write(f"--- a/{CARD}\n+++ b/{CARD}\n@@ -1 +1,2 @@\n base\n+".encode() + b"\xff\n")
        invalid_hash = sha256_file(invalid_path)
        invalid_patch = dict(base, candidate_id="cand-invalid-utf8", touched_files=[CARD],
                             diff=invalid_rel, candidate_hash=invalid_hash)
        try:
            expect("non-UTF-8 patch blocks", invalid_patch, "block")
        except Exception as exc:
            ok = False
            print(f"[self-test] non-UTF-8 patch crashed the gate: {type(exc).__name__}: {exc}")

        expect("non-empty baseline diff blocks",
               dict(baseline, candidate_id="cand-baseline-nonempty", touched_files=[],
                    diff=card_diff, candidate_hash=card_h), "block")

    print("\nSELF-TEST:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main(argv):
    if len(argv) == 2 and argv[1] == "--self-test":
        return self_test()
    camp = cand = None
    i = 1
    try:
        while i < len(argv):
            if argv[i] == "--campaign":
                camp = load(argv[i + 1]); i += 2
            elif argv[i] == "--candidate":
                cand = load(argv[i + 1]); i += 2
            else:
                i += 1
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"input error: {exc}", file=sys.stderr)
        return 2
    if camp is None or cand is None:
        print(__doc__)
        return 2
    return 0 if report(camp, cand, ROOT) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
