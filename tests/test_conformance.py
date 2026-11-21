from __future__ import annotations

import os
import pathlib
import re
import subprocess
import sys
import unittest

from ajar.redact import scan_file_secret_classes

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

# Complete 33-rule Banned-Jargon Gate (#1..#31 from Round-2 audit + DEC-0118 retired OSLit / Platform nouns)
BANNED_JARGON_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("01_llm_redteam_harness", re.compile(r"\bllm-redteam-harness\b", re.IGNORECASE)),
    ("02_inner_outer_research", re.compile(r"\b(?:inner research|outer wrapper|outer driver)\b", re.IGNORECASE)),
    (
        "03_candidate_native_route",
        re.compile(r"\b(?:candidate native|native local research|native source SDK)\b", re.IGNORECASE),
    ),
    (
        "04_record_kernel",
        re.compile(r"\b(?:legacy local research|record kernel|admitted reader|Decision 0005/0006 kernel)\b", re.IGNORECASE),
    ),
    ("05_plane_123", re.compile(r"\bPlane[- ](?:1|2|3)\b")),
    ("06_zone_123", re.compile(r"\bZone-(?:1|2|3)\b")),
    ("07_scope_fence", re.compile(r"\bscope fence\b", re.IGNORECASE)),
    ("08_safe_signal", re.compile(r"\bsafe_signal\b", re.IGNORECASE)),
    (
        "09_escalation_rung",
        re.compile(r"\b(?:escalation rung|ceiling-requests\.md|impact_escalation|impact_demo_authorized)\b", re.IGNORECASE),
    ),
    ("10_queue_claim", re.compile(r"\b(?:queue-claim|completion_claims)\b", re.IGNORECASE)),
    (
        "11_attempt_ceremony",
        re.compile(r"\b(?:attempt-start|attempt-finish|record-negative|register-bundle)\b", re.IGNORECASE),
    ),
    ("12_covered_dry", re.compile(r"\b(?:coverage_dry|covered-dry|covered_dry)\b", re.IGNORECASE)),
    ("13_cleanup_obligation", re.compile(r"\bcleanup obligation\b", re.IGNORECASE)),
    ("14_adjudication", re.compile(r"\b(?:adjudication|adjudication-oracle|adjudicated)\b", re.IGNORECASE)),
    ("15_pocinator", re.compile(r"\bpocinator(?:-oracle)?\b", re.IGNORECASE)),
    (
        "16_markdown_oracles",
        re.compile(
            r"\b(?:signal-oracle|regrade-oracle|chainability-oracle|ghsa-fix-diff-oracle|severity-precedent-oracle)\b",
            re.IGNORECASE,
        ),
    ),
    ("17_regrade", re.compile(r"\bregrade\b", re.IGNORECASE)),
    ("18_casebooks", re.compile(r"\bcasebooks?\b", re.IGNORECASE)),
    ("19_dossier", re.compile(r"\bdossier\b", re.IGNORECASE)),
    ("20_disposition", re.compile(r"\b(?:disposition|disposition_ledger|memory_disposition)\b", re.IGNORECASE)),
    ("21_unproven_packet", re.compile(r"\bunproven packet\b", re.IGNORECASE)),
    ("22_exhausted_lane", re.compile(r"\b(?:exhausted lane|source lane)\b", re.IGNORECASE)),
    ("23_source_engagement_bootstrap", re.compile(r"\b(?:source-engagement-bootstrap|legacy-bootstrap)\b", re.IGNORECASE)),
    ("24_environment_preflight", re.compile(r"\b(?:environment preflight|preflight_holdout)\b", re.IGNORECASE)),
    ("25_routes_to_stub", re.compile(r'routes_to:\s*\[[^\]]*stub:', re.IGNORECASE)),
    ("26_grandfather_pins", re.compile(r"\bcompletion-claim-grandfather-pins\b", re.IGNORECASE)),
    ("27_quiescence", re.compile(r"\b(?:quiescence|session-end-backstop)\b", re.IGNORECASE)),
    ("28_gepa_dspy", re.compile(r"\b(?:gepa-shadow|GEPA|DSPy normalizer|framing-probe)\b")),
    (
        "29_etrack_stego",
        re.compile(r"\b(?:E-track|etrack|tollbooth|payload-proposal|p4rs3lt0ngv3|st3gg|glossopetrae)\b", re.IGNORECASE),
    ),
    ("30_personas", re.compile(r"\b(?:eni-novelist|persona-pressure|#muse)\b", re.IGNORECASE)),
    ("31_kanboard", re.compile(r"\b(?:kanboard|opencode-kanboard|t02-cloud-source)\b", re.IGNORECASE)),
    ("32_oslit_retired", re.compile(r"\bOSLit\b")),
    ("33_ajar_platform_retired", re.compile(r"\bAjar Platform\b")),
)

MD_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def _iter_active_text_files() -> list[pathlib.Path]:
    active: list[pathlib.Path] = []
    skip_dirs = {
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "__pycache__",
        "build",
        "dist",
        "node_modules",
        "target",
        ".venv",
    }
    for root, dirs, files in os.walk(REPO_ROOT, followlinks=False):
        rel_root = pathlib.Path(root).relative_to(REPO_ROOT)
        dirs[:] = sorted(
            d
            for d in dirs
            if d not in skip_dirs
            and not d.endswith(".egg-info")
            and not (rel_root == pathlib.Path(".") and d == "engagements")
            and not (rel_root == pathlib.Path("tools") and d == "legacy")
            and not (rel_root == pathlib.Path("docs") and d == "archive")
        )
        for fname in sorted(files):
            fpath = pathlib.Path(root) / fname
            rel = fpath.relative_to(REPO_ROOT)
            # Exclude historical ADRs 0001..0013 and ADR-0017 (which documents retired terms) and this test file.
            if rel.parts[:2] == ("docs", "decisions") and fname.startswith("00"):
                continue
            if rel == pathlib.Path("tests/test_conformance.py"):
                continue
            if fpath.suffix.lower() in {".md", ".py", ".toml", ".yml", ".yaml", ".json", ".c", ".go", ".rs", ".sol"} or rel == pathlib.Path("bin/ajar"):
                active.append(fpath)
    return active


class TestConformance(unittest.TestCase):
    def test_agents_and_claude_md_within_50_line_budget(self) -> None:
        contents: dict[str, str] = {}
        for doc_name in ("AGENTS.md", "CLAUDE.md"):
            p = REPO_ROOT / doc_name
            self.assertTrue(p.is_file(), f"Missing {doc_name}")
            txt = p.read_text(encoding="utf-8")
            contents[doc_name] = txt
            lines = txt.splitlines()
            self.assertLessEqual(len(lines), 50, f"{doc_name} has {len(lines)} lines (must be <= 50)")
        self.assertEqual(contents["AGENTS.md"], contents["CLAUDE.md"], "AGENTS.md and CLAUDE.md must be byte-identical")

    def test_zero_banned_jargon_across_active_code_docs_and_skills(self) -> None:
        violations: list[str] = []
        for fpath in _iter_active_text_files():
            rel = fpath.relative_to(REPO_ROOT)
            # docs/engineering/AGENTS.md is permitted a single historical archive pointer to tools/legacy/.
            text = fpath.read_text(encoding="utf-8", errors="ignore")
            for rule_name, pattern in BANNED_JARGON_RULES:
                for m in pattern.finditer(text):
                    line_no = text.count("\n", 0, m.start()) + 1
                    violations.append(f"{rel}:{line_no} matched {rule_name} ({m.group(0)!r})")
        self.assertEqual(violations, [], "Banned v1/v2 jargon found:\n" + "\n".join(violations[:40]))

    def test_markdown_relative_links_resolve(self) -> None:
        md_files: list[pathlib.Path] = [
            REPO_ROOT / "AGENTS.md",
            REPO_ROOT / "CLAUDE.md",
            REPO_ROOT / "README.md",
            REPO_ROOT / "docs" / "architecture.md",
            REPO_ROOT / "docs" / "decisions" / "README.md",
            REPO_ROOT / "docs" / "decisions" / "0017-ajar-v3-dual-mode-architecture.md",
            REPO_ROOT / "docs" / "decisions" / "0018-ajar-v3-1-bug-brain-and-platform-economics.md",
            REPO_ROOT / "docs" / "decisions" / "0019-ajar-v3-2-hooks-and-composable-repro.md",
            REPO_ROOT / "docs" / "decisions" / "0020-ajar-v3-2-2-swarm-wire-profiles-and-reopen.md",
            REPO_ROOT / "docs" / "decisions" / "0021-ajar-v3-2-3-exogenous-target-checks-and-retro-routing.md",
            REPO_ROOT / "docs" / "decisions" / "0022-ajar-v3-3-reactive-open-doors-and-phase-split.md",
            REPO_ROOT / "docs" / "engineering" / "AGENTS.md",
        ]
        md_files.extend(sorted((REPO_ROOT / "skills").rglob("*.md")))

        broken: list[str] = []
        for md in md_files:
            self.assertTrue(md.is_file(), f"Expected markdown file missing: {md}")
            content = md.read_text(encoding="utf-8")
            # Strip fenced code blocks before scanning links.
            stripped = re.sub(r"```[\s\S]*?```", "", content)
            for m in MD_LINK_RE.finditer(stripped):
                raw_target = m.group(1).strip()
                if (
                    not raw_target
                    or raw_target.startswith(("http://", "https://", "mailto:", "#", "file://", "ace://"))
                    or "<" in raw_target
                    or "{" in raw_target
                ):
                    continue
                path_part = raw_target.split("#", 1)[0].strip()
                if not path_part:
                    continue
                resolved = (md.parent / path_part).resolve()
                if not resolved.exists():
                    broken.append(f"{md.relative_to(REPO_ROOT)} -> {raw_target}")
        self.assertEqual(broken, [], "Broken relative Markdown links:\n" + "\n".join(broken))

    def test_reference_corpora_repairs_and_zero_truncated_cves(self) -> None:
        ref_dir = REPO_ROOT / "skills" / "references"
        self.assertTrue(ref_dir.is_dir())
        p0_corpus = (ref_dir / "project-zero-zdi-chain-corpus.md").read_text(encoding="utf-8")
        self.assertIn("CVE-2021-31207", p0_corpus, "ProxyShell stage 3 CVE-2021-31207 must be present")
        self.assertNotIn("CVSS:3.0/AV:N/AC:L/PR:N/U|", p0_corpus)

        trunc_re = re.compile(r"CVE-\d{4}-\d*…|[0-9a-f]{7,39}…")
        bad_hits: list[str] = []
        for md in sorted(ref_dir.glob("*.md")):
            txt = md.read_text(encoding="utf-8")
            for m in trunc_re.finditer(txt):
                line_no = txt.count("\n", 0, m.start()) + 1
                bad_hits.append(f"{md.name}:{line_no}: {m.group(0)}")
        self.assertEqual(bad_hits, [], "Truncated CVE/SHA tokens found:\n" + "\n".join(bad_hits))

    def test_zero_unredacted_secrets_in_active_repo_files(self) -> None:
        leaks: list[str] = []
        for fpath in _iter_active_text_files():
            rel = fpath.relative_to(REPO_ROOT)
            if rel == pathlib.Path("tests/test_redact.py"):
                continue
            classes = scan_file_secret_classes(fpath)
            if classes:
                leaks.append(f"{rel}: {classes}")
        self.assertEqual(leaks, [], "Unredacted secret patterns found:\n" + "\n".join(leaks))

    def test_archived_legacy_reader_closure_passes(self) -> None:
        import importlib.util

        if importlib.util.find_spec("jsonschema") is None:
            self.skipTest("Optional dev dependency `jsonschema==4.26.0` not installed in active interpreter.")
        proc = subprocess.run(
            [sys.executable, str(REPO_ROOT / "tools" / "legacy" / "dossier-inspector-test.py")],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + "\n" + proc.stderr)
        self.assertIn("23 public-command checks passed", proc.stdout)

    def test_cli_commands_in_docs_and_skills_match_parser(self) -> None:
        import argparse
        import shlex

        from ajar.cli import build_parser

        def _collect_parser_tree(
            p: argparse.ArgumentParser,
            prefix: tuple[str, ...] = (),
        ) -> dict[tuple[str, ...], dict[str, object]]:
            info: dict[tuple[str, ...], dict[str, object]] = {prefix: {"flags": set(), "choices": {}}}
            flags = info[prefix]["flags"]
            choices = info[prefix]["choices"]
            assert isinstance(flags, set) and isinstance(choices, dict)
            for act in p._actions:
                for opt in act.option_strings:
                    flags.add(opt)
                    if act.choices is not None:
                        choices[opt] = {str(c) for c in act.choices}
                if isinstance(act, argparse._SubParsersAction):
                    for name, subp in act.choices.items():
                        info.update(_collect_parser_tree(subp, prefix + (name,)))
            return info

        def _extract_commands(text: str) -> list[tuple[int, str]]:
            commands: list[tuple[int, str]] = []
            lines = text.splitlines()
            in_fence = False
            fence_lang = ""
            buf_start = 0
            buf = ""
            inline_re = re.compile(r"`(ajar\s+[^`\n]+)`")

            for lineno, raw_line in enumerate(lines, 1):
                stripped = raw_line.strip()
                if stripped.startswith("```"):
                    if not in_fence:
                        in_fence = True
                        fence_lang = stripped[3:].strip().lower()
                        buf = ""
                    else:
                        if buf.strip():
                            commands.append((buf_start, buf.strip()))
                            buf = ""
                        in_fence = False
                        fence_lang = ""
                    continue
                if in_fence:
                    if fence_lang not in ("", "bash", "sh", "shell", "zsh"):
                        continue
                    if not stripped or stripped.startswith("#"):
                        if buf.strip():
                            commands.append((buf_start, buf.strip()))
                            buf = ""
                        continue
                    if not buf:
                        if not stripped.startswith("ajar "):
                            continue
                        buf_start = lineno
                    if stripped.endswith("\\"):
                        buf += " " + stripped[:-1].strip()
                    else:
                        buf += " " + stripped
                        commands.append((buf_start, buf.strip()))
                        buf = ""
                else:
                    for m in inline_re.finditer(raw_line):
                        commands.append((lineno, m.group(1).strip()))
            if buf.strip():
                commands.append((buf_start, buf.strip()))
            return commands

        def _tokenize(cmd: str) -> list[str]:
            try:
                return shlex.split(cmd)
            except ValueError:
                return cmd.split()

        def _check_choice_values(val: str, valid: set[str], rel: pathlib.Path, lineno: int, flag: str) -> list[str]:
            issues: list[str] = []
            cleaned = val.strip("[](),\"'")
            if not cleaned or cleaned.startswith(("-", "$", "{")):
                return issues
            if cleaned.startswith("<") and cleaned.endswith(">"):
                inner = cleaned[1:-1].strip()
                if "|" not in inner:
                    return issues
                candidates = [p.strip() for p in inner.split("|")]
            elif "|" in cleaned:
                candidates = [p.strip("[]<>") for p in cleaned.split("|")]
            elif cleaned.startswith("<"):
                return issues
            else:
                candidates = [cleaned]
            for opt_val in candidates:
                if opt_val and not opt_val.startswith("<") and opt_val not in valid:
                    issues.append(
                        f"{rel}:{lineno}: invalid choice `{opt_val}` for `{flag}` (valid: {sorted(valid)})"
                    )
            return issues

        ptree = _collect_parser_tree(build_parser())
        doc_files = [
            REPO_ROOT / "AGENTS.md",
            REPO_ROOT / "CLAUDE.md",
            REPO_ROOT / "docs" / "architecture.md",
            *sorted((REPO_ROOT / "skills").rglob("SKILL.md")),
        ]
        mismatches: list[str] = []
        for fpath in doc_files:
            rel = fpath.relative_to(REPO_ROOT)
            for lineno, cmd in _extract_commands(fpath.read_text(encoding="utf-8")):
                toks = _tokenize(cmd)[1:]
                if not toks or toks[0].startswith(("<", "[")):
                    continue
                prefix: tuple[str, ...] = ()
                idx = 0
                while idx < len(toks):
                    cand = prefix + (toks[idx],)
                    if cand in ptree:
                        prefix = cand
                        idx += 1
                    else:
                        break
                if not prefix:
                    mismatches.append(f"{rel}:{lineno}: unknown command `{toks[0]}` in `{cmd}`")
                    continue
                has_sub = any(k[: len(prefix)] == prefix and len(k) > len(prefix) for k in ptree)
                if has_sub and idx < len(toks) and not toks[idx].startswith(("-", "[", "<", "{")):
                    mismatches.append(
                        f"{rel}:{lineno}: unknown subcommand `{toks[idx]}` under `ajar {' '.join(prefix)}`"
                    )
                    continue
                spec = ptree[prefix]
                spec_flags = spec["flags"]
                spec_choices = spec["choices"]
                assert isinstance(spec_flags, set) and isinstance(spec_choices, dict)
                rest = toks[idx:]
                i = 0
                while i < len(rest):
                    raw_tok = rest[i]
                    clean_tok = raw_tok.strip("[](),")
                    if clean_tok in ("&&", "||", "|", ";"):
                        break
                    if clean_tok.startswith("--") and "<" not in clean_tok and "{" not in clean_tok:
                        if "=" in clean_tok:
                            flag_name, inline_val = clean_tok.split("=", 1)
                            if flag_name not in spec_flags:
                                mismatches.append(
                                    f"{rel}:{lineno}: unknown flag `{flag_name}` on `ajar {' '.join(prefix)}`"
                                )
                            elif flag_name in spec_choices:
                                mismatches.extend(
                                    _check_choice_values(inline_val, spec_choices[flag_name], rel, lineno, flag_name)
                                )
                        else:
                            if clean_tok not in spec_flags:
                                mismatches.append(
                                    f"{rel}:{lineno}: unknown flag `{clean_tok}` on `ajar {' '.join(prefix)}`"
                                )
                            elif clean_tok in spec_choices and i + 1 < len(rest):
                                mismatches.extend(
                                    _check_choice_values(rest[i + 1], spec_choices[clean_tok], rel, lineno, clean_tok)
                                )
                                i += 1
                    i += 1
        self.assertEqual(mismatches, [], "CLI-vs-Docs/Skills mismatches:\n" + "\n".join(mismatches))


if __name__ == "__main__":
    unittest.main()
