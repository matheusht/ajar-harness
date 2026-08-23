#!/usr/bin/env python3
"""Conformance checker for the llm-redteam-harness.

The approved, pinned Draft 2020-12 validator checks governed JSON records; the existing lightweight
parsers continue to check Markdown/YAML-like structural contracts. This validates contracts, NOT
security semantics:

  - every card has a delimited front-matter block with id + type
  - pattern cards declare activation.strong / .weak / .negative
  - vuln cards declare safe_signal
  - routes_to: non-stub ids resolve (pattern.<id> or vulns/<dir>); stub: ids are quoted + skipped
  - casebooks reference only pattern ids that exist
  - no live-secret shapes leaked into any casebook / fixture / eval file
  - finding fixtures honor the evidence-contract migration gate (Phase 2.5A)
  - the false-discovery corpus has a zero invalid-accept rate
  - the adversarial-candidate corpus is well-formed (>=1 retain, all immutable-touching = block)
  - AGENTS.md stays byte-identical to CLAUDE.md (a preregistration pins its sha256)
  - every evals/ fixture directory a card cites exists, or the card declares fixture_status: planned
  - every intervention record carries an auditable quote and declares its provenance
  - score_finding.py blocks every trap package and passes every control package
  - every promoted lesson has an ablation fixture proving it changes a verdict
  - the novelty mapper separates a card restatement from an unrelated idea

Structural only: a green run means the evidence CONTRACT is present and well-formed (necessary), NOT
that any finding is true (the model oracle still adjudicates that). Do not read green as "confirmed".

Usage:  python3 tools/check-conformance.py        (exit 0 = clean, 1 = failures)
"""

import hashlib
import io
import json
import os
import re
import subprocess
import sys

from engagement_records import (
    legacy_finding_inventory,
    validate_fixture_suite,
    validate_record,
    validate_reference_fixture_suite,
    validate_schema_documents,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FAILS = []
CHECKS = 0


def record(ok, label, detail=""):
    global CHECKS
    CHECKS += 1
    if ok:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label}  {detail}")
        FAILS.append(f"{label}  {detail}")


def front_matter(text):
    if not text.startswith("---"):
        return None
    parts = text.split("\n---", 2)
    if len(parts) < 2:
        return None
    return parts[0].lstrip("-\n")


def get_key(fm, key):
    m = re.search(rf"^{re.escape(key)}:\s*(.*)$", fm, re.MULTILINE)
    return m.group(1).strip() if m else None


def list_cards(subdir):
    base = os.path.join(ROOT, "skills", subdir)
    if not os.path.isdir(base):
        return []
    out = []
    for name in sorted(os.listdir(base)):
        path = os.path.join(base, name, "SKILL.md")
        if os.path.isfile(path):
            out.append((name, path))
    return out


def collect_pattern_ids():
    ids = {}
    for name, path in list_cards("patterns"):
        fm = front_matter(open(path).read()) or ""
        cid = get_key(fm, "id")
        if cid:
            ids[cid] = name
    return ids


def check_cards(subdir, pattern_ids, cap_ids):
    print(f"\n[cards] skills/{subdir}/")
    for name, path in list_cards(subdir):
        text = open(path).read()
        fm = front_matter(text)
        record(fm is not None, f"{subdir}/{name}: front-matter present")
        if fm is None:
            continue
        record(get_key(fm, "id") is not None, f"{subdir}/{name}: has id")
        record(get_key(fm, "type") is not None, f"{subdir}/{name}: has type")

        if subdir == "vulns":
            record("safe_signal:" in fm, f"{subdir}/{name}: vuln has safe_signal")

        if subdir == "patterns":
            has_act = re.search(r"^activation:", fm, re.MULTILINE)
            record(bool(has_act), f"{subdir}/{name}: has activation block")
            for tier in ("strong", "weak", "negative"):
                record(bool(re.search(rf"^\s+{tier}:", fm, re.MULTILINE)),
                       f"{subdir}/{name}: activation.{tier}")

        check_routes_to(name, subdir, fm, pattern_ids)
        check_optional_capabilities(name, subdir, fm, cap_ids)


def check_routes_to(name, subdir, fm, pattern_ids):
    line = re.search(r"^routes_to:\s*(\[[^\]]*\])", fm, re.MULTILINE)
    if not line:
        return
    raw = line.group(1)

    unquoted_stub = re.search(r'(?<!")stub:', raw)
    record(unquoted_stub is None, f"{subdir}/{name}: stub ids are quoted",
           "found unquoted stub: in routes_to" if unquoted_stub else "")

    entries = [e.strip().strip('"').strip("'") for e in raw[1:-1].split(",") if e.strip()]
    for e in entries:
        if e.startswith("stub:"):
            continue
        if e.startswith("pattern."):
            record(e in pattern_ids, f"{subdir}/{name}: route resolves {e}",
                   "no such pattern id" if e not in pattern_ids else "")
        elif e.startswith("vulns/"):
            p = os.path.join(ROOT, "skills", e, "SKILL.md")
            record(os.path.isfile(p), f"{subdir}/{name}: route resolves {e}",
                   "no such vuln card" if not os.path.isfile(p) else "")
        else:
            record(False, f"{subdir}/{name}: route form {e}", "unknown route form (use stub: / pattern. / vulns/)")


def collect_capability_ids():
    ids = set()
    path = os.path.join(ROOT, "capabilities", "registry.yaml")
    if os.path.isfile(path):
        for m in re.finditer(r"^\s*-\s*id:\s*([A-Za-z0-9._-]+)", open(path).read(), re.MULTILINE):
            ids.add(m.group(1))
    return ids


def _capability_blocks(text):
    return [(m.group(1), m.group(2)) for m in re.finditer(
        r"^\s*-\s*id:\s*([A-Za-z0-9._-]+)\s*\n(.*?)(?=^\s*-\s*id:|\Z)", text, re.MULTILINE | re.DOTALL)]


# actions that may NEVER appear in a capability's allowed_actions (payload generators / agent modes /
# raw-offense). The keyhole must exclude these mechanically, not by convention.
DANGEROUS_ACTIONS = {
    "agent", "promptcraft", "anticlassifier", "injector", "tokenade", "fuzzer",
    "embed_arbitrary_payload", "conceal_agent", "jailbreak_templates", "raw_payload_promotion",
    "semantic_stego_raw", "token_exploit_raw", "harmful_probe_sets", "offense_modules",
}


def _cap_list(body, key):
    m = re.search(rf"^\s*{key}:\s*\[([^\]]*)\]", body, re.MULTILINE)
    return [x.strip().strip('"').strip("'") for x in m.group(1).split(",") if x.strip()] if m else []


def _get_field(body, key):
    m = re.search(rf"^\s*{key}:\s*(\S+)", body, re.MULTILINE)
    return m.group(1).strip() if m else None


def _payload_generator_problems(body):
    """A payload_generator entry: proposal-only, gated, never a judge or executor."""
    p = []
    auth = _get_field(body, "authority")
    if auth != "proposal_only":
        p.append("payload_generator authority must be proposal_only")
    if auth in ("oracle", "judge", "verdict", "confirmed", "allow", "success"):
        p.append(f"payload_generator claims forbidden authority: {auth}")
    if re.search(r"^\s*default:\s*disabled\s*$", body, re.MULTILINE) is None:
        p.append("payload_generator not default: disabled")
    if re.search(r"^\s*forbidden_actions:\s*\[", body, re.MULTILINE) is None:
        p.append("no forbidden_actions")
    for gate in ("scope_allows_payload_generation", "containment_plan", "oracle_separation"):
        if gate not in body:
            p.append(f"payload_generator missing required gate: {gate}")
    if _get_field(body, "payload_class") is None and "declared_payload_class" not in body:
        p.append("payload_generator missing declared payload_class")
    bad_emit = sorted(set(_cap_list(body, "emits")) & {"confirmed", "allow", "verdict", "success"})
    if bad_emit:
        p.append(f"payload_generator emits forbidden verdict tokens: {bad_emit}")
    return p


def capability_entry_problems(body):
    """Pure predicate — reasons a single registry entry violates its class contract (empty = clean).
    Class-aware: payload_generator -> proposal-only + gated; everything else -> the sensor_only keyhole.
    The single source of truth reused by check_capabilities and the _must_reject corpus."""
    if _get_field(body, "class") == "payload_generator":
        return _payload_generator_problems(body)
    p = []
    if re.search(r"^\s*authority:\s*sensor_only\s*$", body, re.MULTILINE) is None:
        p.append("authority not sensor_only")
    if re.search(r"^\s*authority:\s*(oracle|judge|authoritative|verdict)\b", body, re.MULTILINE):
        p.append("claims oracle/judge authority")
    if re.search(r"^\s*forbidden_actions:\s*\[", body, re.MULTILINE) is None:
        p.append("no forbidden_actions")
    if re.search(r"^\s*source:\s*\S+", body, re.MULTILINE) is None:
        p.append("no source")
    if re.search(r"^\s*license:\s*\S+", body, re.MULTILINE) is None:
        p.append("no license")
    allowed = set(_cap_list(body, "allowed_actions"))
    forbidden = set(_cap_list(body, "forbidden_actions"))
    if allowed & DANGEROUS_ACTIONS:
        p.append(f"dangerous in allowed_actions: {sorted(allowed & DANGEROUS_ACTIONS)}")
    if allowed & forbidden:
        p.append(f"allowed/forbidden overlap: {sorted(allowed & forbidden)}")
    return p


def check_capability_classes():
    """Validate capabilities/classes.yaml — the authority model. payload_generator must be proposal-only,
    default-disabled, gated, and forbidden from oracle/judge/verdict authority; only `oracle` may judge."""
    print("\n[capabilities] capability classes (authority model)")
    path = os.path.join(ROOT, "capabilities", "classes.yaml")
    if not os.path.isfile(path):
        return
    blocks = _capability_blocks(open(path).read())
    record(len(blocks) > 0, "classes: non-empty")
    by_id = {cid: body for cid, body in blocks}
    for cid, body in blocks:
        record(_get_field(body, "authority") is not None, f"classes/{cid}: declares authority")
        if cid != "oracle":
            record(_get_field(body, "authority") not in ("oracle", "judge", "verdict"),
                   f"classes/{cid}: non-oracle class doesn't claim oracle/judge authority")
    pg = by_id.get("payload_generator")
    if pg is not None:
        record(_get_field(pg, "authority") == "proposal_only",
               "classes/payload_generator: authority is proposal_only")
        record(re.search(r"^\s*default:\s*disabled\s*$", pg, re.MULTILINE) is not None,
               "classes/payload_generator: default disabled")
        for gate in ("signed_scope", "scope_allows_payload_generation", "declared_payload_class",
                     "containment_plan", "cleanup_plan", "oracle_separation"):
            record(gate in pg, f"classes/payload_generator: requires {gate}")
        for forb in ("oracle", "judge", "verdict", "confirmed", "allow"):
            record(forb in pg, f"classes/payload_generator: forbids {forb} authority")


def check_capabilities():
    """The narrow keyhole: every external capability must be sensor_only and declare its fences."""
    print("\n[capabilities] external capability registry")
    path = os.path.join(ROOT, "capabilities", "registry.yaml")
    if not os.path.isfile(path):
        return
    text = open(path).read()
    blocks = _capability_blocks(text)
    record(len(blocks) > 0, "capabilities: registry non-empty")
    for cid, body in blocks:
        problems = capability_entry_problems(body)
        record(not problems, f"capabilities/{cid}: sensor-only entry within the keyhole",
               "; ".join(problems) if problems else "")
    bad = re.findall(r"^\s*authority:\s*(oracle|judge|authoritative|verdict)\b", text, re.MULTILINE)
    record(not bad, "capabilities: no entry claims oracle/judge authority", f"found {bad}" if bad else "")


def scope_flag_problems(registry_text, template_text):
    """Pure predicate — scope_allows_* flags a registry requires that the scope template doesn't declare."""
    flags = sorted(set(re.findall(r"\bscope_allows_[a-z0-9_]+", registry_text)))
    return [f"undeclared scope flag: {f}" for f in flags if f not in template_text]


def check_capability_scope_flags():
    tmpl = os.path.join(ROOT, "engagements", "_TEMPLATE", "scope.md")
    if not os.path.isfile(tmpl):
        return
    src = ""
    for fn in ("registry.yaml", "classes.yaml"):
        fp = os.path.join(ROOT, "capabilities", fn)
        if os.path.isfile(fp):
            src += open(fp).read() + "\n"
    problems = scope_flag_problems(src, open(tmpl).read())
    record(not problems, "capabilities: every required scope flag is declared in _TEMPLATE/scope.md",
           "; ".join(problems) if problems else "")


def _card_capability_refs(fm):
    line = re.search(r"^optional_capabilities:\s*(\[[^\]]*\])", fm, re.MULTILINE)
    if not line:
        return []
    return [e.strip().strip('"').strip("'") for e in line.group(1)[1:-1].split(",") if e.strip()]


def card_capability_problems(fm, cap_ids):
    """Pure predicate — optional_capabilities ids in a card that don't resolve to a registry id."""
    return [f"unresolved: {e}" for e in _card_capability_refs(fm) if e not in cap_ids]


def check_optional_capabilities(name, subdir, fm, cap_ids):
    for e in _card_capability_refs(fm):
        record(e in cap_ids, f"{subdir}/{name}: optional_capability resolves {e}",
               "no such capability id" if e not in cap_ids else "")


def check_capability_must_reject():
    """Permanent negative tests: every fixture MUST be rejected by the SAME validation predicates.
    Converts the manual gate-bites into CI-enforced regressions (mirrors fixtures/findings/_must_reject)."""
    base = os.path.join(ROOT, "fixtures", "capabilities", "_must_reject")
    if not os.path.isdir(base):
        return
    print("\n[capabilities] _must_reject corpus (the keyhole must fail closed)")
    cap_ids = collect_capability_ids()
    tmpl = os.path.join(ROOT, "engagements", "_TEMPLATE", "scope.md")
    tmpl_text = open(tmpl).read() if os.path.isfile(tmpl) else ""
    for fn in sorted(os.listdir(base)):
        fp = os.path.join(base, fn)
        if not os.path.isfile(fp):
            continue
        content = open(fp).read()
        if fn.endswith(".md"):
            problems = card_capability_problems(front_matter(content) or "", cap_ids)
        elif "scope-flag" in fn:
            problems = scope_flag_problems(content, tmpl_text)
        else:  # registry-entry yaml
            problems = [p for _, body in _capability_blocks(content) for p in capability_entry_problems(body)]
        record(bool(problems), f"_must_reject/{fn}: rejected by the keyhole [{'; '.join(problems) or 'NONE'}]",
               "fixture should be rejected but passed all checks" if not problems else "")


# --- tool-family manifests (docs/tool-family-adapter-architecture.md) ---------------------------
# A family manifest owns the authority contract for an external toolkit. Detection is exposed; every
# advanced surface (embed/extract/injector/conceal/network/multi-layer/executor) stays in scope but is
# listed under blocked_until with its gate. The manifest fails closed: an action not explicitly allowed,
# or a staged entry missing its gates, must be rejected.

TF_FORBIDDEN_AUTHORITY = {"oracle", "judge", "authoritative", "verdict", "confirmed", "allow", "success"}


def _yaml_section(text, key):
    """Indented block under a top-level `key:` (until the next col-0 line or EOF)."""
    m = re.search(rf"^{key}:\s*\n(.*?)(?=^\S|\Z)", text, re.MULTILINE | re.DOTALL)
    return m.group(1) if m else ""


def tool_family_blocked_entry_problems(body):
    """Pure predicate — reasons a single blocked_until entry is unsafe (empty = clean). Each staged
    surface (incl. injector/template/conceal) must declare its gate, risk, scope gates, redaction, and
    non-authority language, or it does not get to sit in the manifest."""
    p = []
    if _get_field(body, "blocked_until") is None:
        p.append("missing blocked_until gate")
    if _get_field(body, "risk_tier") is None:
        p.append("missing risk_tier")
    if not _cap_list(body, "requires"):
        p.append("missing scope-gate requires[]")
    if re.search(r"^\s*redaction:\s*\S+", body, re.MULTILINE) is None:
        p.append("missing redaction rule")
    auth = _get_field(body, "authority")
    if auth is None:
        p.append("missing non-authority language (authority)")
    elif auth in TF_FORBIDDEN_AUTHORITY:
        p.append(f"claims forbidden authority: {auth}")
    if re.search(r"^\s*evidence_role:\s*\S+", body, re.MULTILINE) is None:
        p.append("missing evidence_role")
    return p


def tool_family_manifest_problems(text):
    """Pure predicate — reasons a family manifest violates the contract (empty = clean). Single source
    of truth reused by check_tool_family_manifests and the _must_reject corpus."""
    p = []
    if re.search(r"^family_id:\s*\S+", text, re.MULTILINE) is None:
        p.append("missing family_id")
    if re.search(r"^\s*reviewed_commit:\s*\S+", text, re.MULTILINE) is None:
        p.append("missing upstream.reviewed_commit")
    if re.search(r"^\s*license:\s*\S+", text, re.MULTILINE) is None:
        p.append("missing upstream.license")
    if re.search(r"^integration:\s*\S+", text, re.MULTILINE) is None:
        p.append("missing integration")
    top_auth = re.search(r"^authority:\s*(\S+)", text, re.MULTILINE)
    if top_auth and top_auth.group(1).strip() in TF_FORBIDDEN_AUTHORITY:
        p.append(f"top-level authority claims forbidden role: {top_auth.group(1).strip()}")
    allowed = set(_cap_list(text, "allowed_actions"))
    if not allowed:
        p.append("missing allowed_actions")
    if allowed & DANGEROUS_ACTIONS:
        p.append(f"dangerous in allowed_actions: {sorted(allowed & DANGEROUS_ACTIONS)}")
    for cid, body in _capability_blocks(_yaml_section(text, "blocked_until")):
        for prob in tool_family_blocked_entry_problems(body):
            p.append(f"blocked_until/{cid}: {prob}")
    return p


# Families whose manifest follows THIS contract shape (flat allowed_actions[] + a blocked_until: section
# of `- id:` blocks). p4rs3lt0ngv3 adopts this shared contract (its converter/catalog outputs get
# additional schema validation in its own selftest.py).
#
# glossopetrae is intentionally EXCLUDED (documented temporary exclusion). It lives in the `-gloss`
# worktree on a different, more-evolved contract: a single `actions:` list (per-action class + status)
# with top-level evidence_role / forbidden_authority / output_schema, validated by its OWN checker
# variant that REQUIRES `authority: sensor_only` and additionally scans adapter-evidence JSON for verdict
# keys. The two manifest shapes are not interchangeable, so converging them is a deliberate design merge
# (pick ONE contract shape), NOT done in this reconciliation slice. When merged, the unified checker MUST
# preserve BOTH guards: this branch's full TF_FORBIDDEN_AUTHORITY top-level reject AND GLOSS's
# require-sensor_only + evidence_role + forbidden_authority + adapter-evidence-JSON scan.
TOOL_FAMILY_CONTRACT_OWNED = {"st3gg", "p4rs3lt0ngv3", "foundry-slither"}


def check_tool_family_manifests():
    """Family manifests: detection-first, machine-checkable, staged authority. Fail closed."""
    base = os.path.join(ROOT, "tool-families")
    if not os.path.isdir(base):
        return
    print("\n[tool-families] family manifests (manifest holds authority; advanced surfaces gated)")
    for fam in sorted(os.listdir(base)):
        if fam not in TOOL_FAMILY_CONTRACT_OWNED:
            continue
        mpath = os.path.join(base, fam, "manifest.yaml")
        if os.path.isfile(mpath):
            problems = tool_family_manifest_problems(open(mpath).read())
            record(not problems, f"tool-families/{fam}/manifest.yaml: detection-first + staged authority",
                   "; ".join(problems) if problems else "")
        apath = os.path.join(base, fam, "AGENT.md")
        if os.path.isfile(apath):
            atext = open(apath).read().lower()
            record("plane 1/2" in atext and "raw" in atext,
                   f"tool-families/{fam}/AGENT.md: states raw payloads not stored in Plane 1/2")


def check_tool_family_must_reject():
    """Permanent negatives: a malformed family manifest MUST be rejected by the same predicate."""
    base = os.path.join(ROOT, "fixtures", "tool-families", "_must_reject")
    if not os.path.isdir(base):
        return
    print("\n[tool-families] _must_reject corpus (the manifest must fail closed)")
    for fn in sorted(os.listdir(base)):
        fp = os.path.join(base, fn)
        if not os.path.isfile(fp):
            continue
        problems = tool_family_manifest_problems(open(fp).read())
        record(bool(problems), f"_must_reject/{fn}: rejected [{'; '.join(problems) or 'NONE'}]",
               "fixture should be rejected but passed all checks" if not problems else "")


PAYLOAD_PROPOSAL_REQUIRED = ["objective_id", "payload_class", "risk_tier", "approved_objective_ref",
                             "generator_capability_id", "artifact_metadata", "required_controls",
                             "containment_plan", "cleanup_plan", "non_authority_attestation"]
PAYLOAD_CLASSES = {"text_prompt", "encoded_prompt", "multimodal_artifact", "stego_carrier",
                   "exploit_poc", "chain_candidate"}
RISK_TIERS = {"benign_canary", "local_poc", "zone2_review_required"}
ZONE2_PAYLOAD_CLASSES = {"exploit_poc", "chain_candidate"}
FORBIDDEN_PROPOSAL_KEYS = ("verdict", "confirmed", "allow", "success")


def payload_proposal_problems(obj):
    """Pure predicate — reasons a payload proposal is malformed (an INERT proposal, never a verdict)."""
    if not isinstance(obj, dict):
        return ["not an object"]
    p = [f"missing {k}" for k in PAYLOAD_PROPOSAL_REQUIRED if k not in obj]
    p += [f"carries forbidden verdict key {k}" for k in FORBIDDEN_PROPOSAL_KEYS if k in obj]
    pc = obj.get("payload_class")
    if pc is not None and pc not in PAYLOAD_CLASSES:
        p.append(f"payload_class not in enum: {pc}")
    if "required_controls" in obj and not (isinstance(obj["required_controls"], list) and obj["required_controls"]):
        p.append("required_controls must be a non-empty list")
    if "non_authority_attestation" in obj:
        att = obj["non_authority_attestation"]
        if not isinstance(att, dict):
            p.append("non_authority_attestation must be an object")
        else:
            for k in ("proposal_only", "executes_nothing", "emits_no_verdict"):
                if att.get(k) is not True:
                    p.append(f"non_authority_attestation.{k} must be true")
    rt = obj.get("risk_tier")
    if rt is not None and rt not in RISK_TIERS:
        p.append(f"risk_tier not in enum: {rt}")
    # zone-2 tiers / exploit classes require operator confirmation + an impact-demo reference, never auto-run
    if pc in ZONE2_PAYLOAD_CLASSES or rt == "zone2_review_required":
        if obj.get("operator_confirmation_required") is not True:
            p.append("zone2 payload_class/risk_tier requires operator_confirmation_required: true")
        if not (isinstance(obj.get("impact_demo_ref"), str) and obj["impact_demo_ref"].strip()):
            p.append("zone2 payload_class/risk_tier requires an impact_demo_ref")
    return p


def check_payload_proposals():
    """PG-2: the inert payload-proposal schema gate. Valid example passes; malformed ones must reject."""
    base = os.path.join(ROOT, "fixtures", "payload-proposals")
    if not os.path.isdir(base):
        return
    print("\n[payload-proposals] inert proposal schema gate (PG-2)")
    for fn in sorted(os.listdir(base)):
        fp = os.path.join(base, fn)
        if not (fn.endswith(".json") and os.path.isfile(fp)):
            continue
        problems = payload_proposal_problems(load_json(fp))
        record(not problems, f"payload-proposals/{fn}: valid proposal",
               "; ".join(problems) if problems else "")
    mr = os.path.join(base, "_must_reject")
    if os.path.isdir(mr):
        for fn in sorted(os.listdir(mr)):
            if not fn.endswith(".json"):
                continue
            problems = payload_proposal_problems(load_json(os.path.join(mr, fn)))
            record(bool(problems), f"payload-proposals/_must_reject/{fn}: rejected [{'; '.join(problems) or 'NONE'}]",
                   "malformed proposal should be rejected but passed" if not problems else "")


def check_oracles():
    print("\n[oracles] skills/oracles/")
    base = os.path.join(ROOT, "skills", "oracles")
    if not os.path.isdir(base):
        return
    for fn in sorted(os.listdir(base)):
        if not fn.endswith(".md"):
            continue
        fm = front_matter(open(os.path.join(base, fn)).read())
        record(fm is not None, f"oracles/{fn}: front-matter present")
        if fm is not None:
            record(get_key(fm, "id") is not None, f"oracles/{fn}: has id")
            record(get_key(fm, "type") is not None, f"oracles/{fn}: has type")


def check_casebooks(pattern_ids):
    print("\n[casebooks] pattern-id references")
    base = os.path.join(ROOT, "casebooks")
    if not os.path.isdir(base):
        return
    for name in sorted(os.listdir(base)):
        cdir = os.path.join(base, name)
        if name.startswith("_") or not os.path.isdir(cdir):
            continue
        refs = set()
        for fn in os.listdir(cdir):
            fp = os.path.join(cdir, fn)
            if os.path.isfile(fp):
                refs |= set(re.findall(r"pattern\.[a-z0-9-]+", open(fp).read()))
        unknown = sorted(r for r in refs if r not in pattern_ids)
        record(not unknown, f"casebooks/{name}: pattern refs resolve",
               f"unknown: {unknown}" if unknown else "")


SECRET_PATTERNS = [
    (r"user_[A-Za-z0-9]{20,}", "clerk-style user id"),
    (r"\b019[0-9a-f]{2}-[0-9a-f]{4}-[0-9a-f]{4}", "uuidv7-style id"),
    (r"eyJ[A-Za-z0-9_-]{10,}", "jwt"),
    (r"[Bb]earer\s+[A-Za-z0-9._-]{12,}", "bearer token value"),
    (r"XTENANT|EVIDENCE-[0-9A-F]{6,}", "engagement canary token"),
]


def check_secrets():
    print("\n[secrets] casebook + fixture + eval scan")
    hits = []
    for sub in ("casebooks", "fixtures", "evals"):
        base = os.path.join(ROOT, sub)
        if not os.path.isdir(base):
            continue
        for dirpath, _, files in os.walk(base):
            for fn in files:
                fp = os.path.join(dirpath, fn)
                text = open(fp, errors="ignore").read()
                for pat, desc in SECRET_PATTERNS:
                    for m in re.finditer(pat, text):
                        hits.append(f"{os.path.relpath(fp, ROOT)}: {desc} :: {m.group(0)[:24]}")
    record(not hits, "casebooks/fixtures/evals contain no live-secret shapes",
           "; ".join(hits) if hits else "")


# ---- Phase 2.5A: evidence-contract gate + evaluator corpora ----

POLICY_CUTOFF = "2026-06-25"
FINDING_BASE_REQUIRED = [
    "id", "engagement", "owasp", "surface", "objective", "scope_class", "severity",
    "confidence", "attempt_id", "control_attempt_id", "oracle_verdict", "dedup_key", "status",
]


def load_json(path):
    with open(path) as fh:
        return json.load(fh)


def finding_is_new(f):
    d = f.get("recorded_date")
    return bool(d) and d >= POLICY_CUTOFF


def check_finding_fixtures():
    print("\n[findings] evidence-contract gate (necessary, not sufficient)")
    base = os.path.join(ROOT, "fixtures", "findings")
    if not os.path.isdir(base):
        return
    for fn in sorted(os.listdir(base)):
        fp = os.path.join(base, fn)
        if not fn.endswith(".json") or not os.path.isfile(fp):
            continue
        f = load_json(fp)
        missing = [k for k in FINDING_BASE_REQUIRED if k not in f]
        record(not missing, f"findings/{fn}: base required fields", f"missing {missing}" if missing else "")
        record("recorded_date" in f, f"findings/{fn}: recorded_date present (drives the migration gate)",
               "every finding must carry recorded_date so the cutoff is explicit, never defaulted" if "recorded_date" not in f else "")
        schema_errors = validate_record(f, "finding-v2-legacy")
        if finding_is_new(f):
            problems = (["evidence_contract missing"] if "evidence_contract" not in f else []) + schema_errors
            record(not problems, f"findings/{fn}: new finding carries complete, schema-valid evidence contract",
                   f"recorded >= {POLICY_CUTOFF} but: {problems}" if problems else "")
        else:
            if schema_errors:
                print(f"  warn findings/{fn}: legacy finding schema gaps {schema_errors} — advisory, not gated")
            record(True, f"findings/{fn}: legacy finding advisory-only")

    mr = os.path.join(base, "_must_reject")
    if os.path.isdir(mr):
        for fn in sorted(os.listdir(mr)):
            fp = os.path.join(mr, fn)
            if not fn.endswith(".json"):
                continue
            f = load_json(fp)
            schema_errors = validate_record(f, "finding-v2-legacy")
            caught = finding_is_new(f) and ("evidence_contract" not in f or bool(schema_errors))
            record(caught, f"findings/_must_reject/{fn}: caught by full schema + policy gate (invalid-accept guard)",
                   "a new finding without a complete, well-formed contract slipped through" if not caught else "")


def check_decision5_record_schemas():
    print("\n[decision-0005] full Draft 2020-12 record validation")
    schema_problems = validate_schema_documents()
    record(not schema_problems, "Decision-0005 schemas pass metaschema + closed local refs",
           str(schema_problems) if schema_problems else "")
    suite = validate_fixture_suite()
    record(not suite["failures"], f"engagement record fixtures: {suite['case_count']} expected outcomes",
           str(suite["failures"]) if suite["failures"] else "")
    ref_suite = validate_reference_fixture_suite()
    record(not ref_suite["failures"], f"record-reference fixtures: {ref_suite['case_count']} expected outcomes",
           str(ref_suite["failures"]) if ref_suite["failures"] else "")
    corpus_root = os.path.join(ROOT, "fixtures", "engagement-records", "legacy-corpus")
    produced = legacy_finding_inventory(corpus_root)
    corpus_expected = load_json(os.path.join(ROOT, "fixtures", "engagement-records", "legacy-corpus-expected.json"))
    record(produced == corpus_expected, "synthetic legacy corpus inventory matches exact counts, hashes, and root digest",
           "regenerate only after intentional fixture review" if produced != corpus_expected else "")
    expected = load_json(os.path.join(ROOT, "fixtures", "engagement-records", "legacy-drift-expected.json"))
    counts = expected.get("expected_counts", {})
    record(counts.get("total") == 124 and counts.get("schema_version_2") == 124,
           "legacy inventory baseline exposes 124 version-2 findings")
    record(counts.get("forbidden_base_model") == 116,
           "legacy inventory baseline exposes 116 forbidden base_model fields")
    record(counts.get("unsupported_scope_class") == 5,
           "legacy inventory baseline exposes five unsupported scope_class values")


def check_false_discovery_corpus():
    print("\n[false-discovery] invalid-accept guard")
    fp = os.path.join(ROOT, "fixtures", "false-discovery", "corpus.json")
    if not os.path.isfile(fp):
        return
    entries = load_json(fp).get("entries", [])
    record(len(entries) > 0, "false-discovery: corpus non-empty")
    confirmable = [e.get("id", "?") for e in entries if e.get("correct_verdict") == "confirmed"]
    record(not confirmable, "false-discovery: invalid_accept_rate == 0 (no trap's correct verdict is 'confirmed')",
           f"wrongly confirmable: {confirmable}" if confirmable else "")
    req = ["id", "trap_class", "observation", "correct_verdict", "missing_control", "why"]
    for e in entries:
        miss = [k for k in req if k not in e]
        record(not miss, f"false-discovery/{e.get('id', '?')}: well-formed", f"missing {miss}" if miss else "")


def check_adversarial_candidates():
    print("\n[adversarial-candidates] Phase-3 gate fixture (staged, not launched)")
    fp = os.path.join(ROOT, "fixtures", "adversarial-candidates", "corpus.json")
    if not os.path.isfile(fp):
        return
    entries = load_json(fp).get("entries", [])
    retain = [e.get("id", "?") for e in entries if e.get("expected_disposition") == "retain"]
    block = [e.get("id", "?") for e in entries if e.get("expected_disposition") == "block"]
    record(len(retain) >= 1, "adversarial: at least one valid additive candidate to retain",
           "no retain candidate" if not retain else "")
    record(len(block) >= 1, "adversarial: at least one gaming candidate to block",
           "no block candidate" if not block else "")
    for e in entries:
        d = e.get("expected_disposition")
        record(d in ("retain", "block"), f"adversarial/{e.get('id', '?')}: disposition in vocab", f"got {d}")
    leaks = [e.get("id", "?") for e in entries if e.get("touches_immutable") and e.get("expected_disposition") != "block"]
    record(not leaks, "adversarial: every immutable-touching candidate is blocked", f"leaky: {leaks}" if leaks else "")


def check_ideation_mapper():
    """The novelty mapper must separate a restatement from an unrelated idea.

    A mapper that calls everything novel is as useless as one that calls everything known. This
    runs its own selftest: every card must map to itself as a rediscovery, and prose from an
    unrelated domain must land as a novelty-candidate."""
    print("\n[ideation] novelty mapper separation")
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    try:
        from ideation import load_cards, idf_table, nearest, classify
    except ImportError as exc:
        record(False, "ideation: module is importable", str(exc))
        return
    cards = load_cards()
    if not cards:
        return
    idf, dflt = idf_table(cards)
    TH = 0.60
    hits = sum(1 for c in cards
               if nearest(" ".join(sorted(c["tokens"])), cards, idf, dflt)[1] >= TH)
    record(hits == len(cards), "ideation: every card maps to itself as a rediscovery",
           f"{hits}/{len(cards)}")
    unrelated = ["the sourdough starter must be fed twice daily with equal parts flour and water",
                 "migratory geese navigate using the earth magnetic field during autumn",
                 "concrete cures more slowly at low ambient temperature and retains moisture"]
    bad = [u for u in unrelated
           if classify(nearest(u, cards, idf, dflt)[1], TH) != "novelty-candidate"]
    record(not bad, "ideation: unrelated prose lands as novelty-candidate",
           f"{len(bad)} misclassified")


def check_kernel_precondition():
    """GK must block a kernel-less engagement, and preflight must refuse before work starts.

    A gate that has never said no is unproven (`docs/decisions/0011`), so this asserts BOTH
    directions rather than only the happy path.
    """
    print("\n[kernel] GK blocks a kernel-less engagement; preflight refuses at Round 0")
    import tempfile, shutil
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    try:
        import finding_lifecycle as fl
    except Exception as exc:
        record(False, "kernel: finding_lifecycle importable", str(exc))
        return
    src = os.path.join(ROOT, "fixtures", "lifecycle-corpus")
    with tempfile.TemporaryDirectory(prefix="kernel-precondition-") as tmp:
        eng = os.path.join(tmp, "eng")
        shutil.copytree(src, eng)
        os.remove(os.path.join(eng, "events.jsonl"))          # a run that never started its kernel
        ok, _ = fl.kernel_state(eng)
        record(ok is False, "kernel: a missing events.jsonl is detected")
        g, _ = fl.run_gates(os.path.join(eng, "unproven", "F-CORP"), eng)
        blocked = [r["gate"] for r in g.rows if not r["ok"]]
        record("GK" in blocked, "kernel: GK blocks when the kernel never ran", str(blocked))
        ok2, _ = fl.kernel_state(src)
        record(ok2 is True, "kernel: an initialized engagement passes")
        g2, _ = fl.run_gates(os.path.join(src, "unproven", "F-CORP"), src)
        blocked2 = [r["gate"] for r in g2.rows if not r["ok"]]
        record("GK" not in blocked2, "kernel: GK does not fire on an initialized engagement",
               str(blocked2))


def check_kb_entries():
    """Phase 8 / Workstream B. Every KB entry obeys the four rules and carries a live ablation proof.

    B.3 is the load-bearing one: an entry that changes no routing decision is noise. This re-runs
    the gate rather than trusting the `ablation_fixture` field the entry wrote about itself --
    self-attestation is not evidence, and this is the same lesson the promotion gates learned.
    """
    print("\n[kb] cross-engagement entries obey the four rules and still change a decision")
    try:
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        import kb as kbmod
    except Exception as exc:
        record(False, "kb: module is importable", str(exc))
        return
    entries = kbmod.load_kb()
    ids = [e.get("id") for e in entries]
    record(len(ids) == len(set(ids)), "kb: entry ids are unique (append-only)")
    for e in entries:
        eid = e.get("id", "<no id>")
        record(not kbmod.validate(e), f"kb/{eid}: schema and the four rules",
               "; ".join(kbmod.validate(e))[:200])
        fx_rel = e.get("ablation_fixture")
        if not fx_rel:
            record(False, f"kb/{eid}: carries an ablation fixture",
                   "B.3: a promoted entry must prove it changes a routing decision")
            continue
        fx_path = os.path.join(ROOT, fx_rel)
        if not os.path.isfile(fx_path):
            record(False, f"kb/{eid}: ablation fixture exists", fx_rel)
            continue
        with open(fx_path) as fh:
            fx = json.load(fh)
        changed, detail = kbmod.ablate(e, fx, entries)
        record(changed, f"kb/{eid}: still changes a routing decision",
               f"{detail['without']} == {detail['with']}")
        rows = kbmod.route(fx["base"], fx["context"], entries)
        record({r["route"] for r in rows} == {r["route"] for r in fx["base"]},
               f"kb/{eid}: routing removed no route (D-09, rule 4)")
    rc = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "kb.py"), "--self-test"],
                        capture_output=True, text=True)
    record(rc.returncode == 0, "kb: tool self-test", rc.stdout[-300:])
    rc2 = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "q02_compare.py"), "--self-test"],
                         capture_output=True, text=True)
    record(rc2.returncode == 0, "q02: prompt-ablation adjudicator self-test", rc2.stdout[-300:])


def check_ablation_fixtures():
    """Every promoted lesson must demonstrate a changed verdict.

    One `promote` disposition existed across ~25 engagements. It was valid, reviewed and passed
    every gate, and its winners.md still read `(none yet)`. The promote step had no next step. A
    promotion that cannot show a decision changing is prose, so this gate refuses it."""
    print("\n[ablation] promoted lessons demonstrate a changed verdict")
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    try:
        from ablation import fixture_index, promote_dispositions, run_fixture
    except ImportError as exc:
        record(False, "ablation: module is importable", str(exc))
        return
    idx = fixture_index()
    for name, d in sorted(idx.items()):
        ok, _ = run_fixture(d)
        record(ok, f"ablation/{os.path.basename(d)}: lesson changes a verdict and keeps a control")
    for rel, doc in promote_dispositions():
        did = doc.get("disposition_id", "(no id)")
        record(did in idx, f"{rel}: promote has an ablation fixture",
               "a promotion without a demonstrated verdict change is prose")


def check_finding_traps():
    """Run tools/score_finding.py against the trap corpus and assert every decision.

    A grader that blocks everything is useless, so this gates on both directions: every trap must
    block and every control must pass. Package names carry the expectation — `control-*` must pass,
    everything else must block. This mirrors fixtures/false-discovery/corpus.json, which gates on
    invalid_accept_rate == 0."""
    print("\n[finding-traps] score_finding.py decisions")
    base = os.path.join(ROOT, "fixtures", "finding-traps")
    if not os.path.isdir(base):
        return
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    try:
        from score_finding import score
    except ImportError as exc:
        record(False, "finding-traps: score_finding is importable", str(exc))
        return
    for name in sorted(os.listdir(base)):
        pkg = os.path.join(base, name)
        if not os.path.isdir(pkg):
            continue
        attest_path = os.path.join(pkg, "attest.json")
        attest = load_json(attest_path) if os.path.isfile(attest_path) else None
        res, _ = score(pkg, attest)
        blocked = bool(res.failures)
        want_block = not name.startswith("control-")
        detail = ""
        if blocked != want_block:
            detail = ("blocked but should pass: " + "; ".join(
                f"{c['family']}: {c['detail'] or c['label']}" for c in res.failures)
                if blocked else "passed but should block")
        record(blocked == want_block,
               f"finding-traps/{name}: decision is {'block' if want_block else 'pass'}", detail)


def check_finding_lifecycle():
    """Run the promotion gates against the lifecycle fixtures and assert both directions.

    Package names carry the expectation: `promote-*` must clear every gate, `block-*` must be
    blocked, and each block fixture must be blocked by the ONE gate its name identifies. Testing the
    specific gate matters — a fixture that blocks for the wrong reason would pass a naive both-
    directions check while the gate it was built for silently does nothing.

    Grounded in spotify-backstage-2026-07 (2026-08-09): findings were written straight into
    findings/ with a self-set status. See engine/finding-lifecycle.md."""
    print("\n[finding-lifecycle] promotion gates")
    base = os.path.join(ROOT, "fixtures", "lifecycle")
    if not os.path.isdir(base):
        return
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    try:
        from finding_lifecycle import run_gates
    except ImportError as exc:
        record(False, "finding-lifecycle: module is importable", str(exc))
        return
    # fixture name suffix -> the gate that must be the blocker
    expected_gate = {"privilege-mismatch": "G3", "privilege-not-established": "G3",
                     "synthetic-review": "G4", "no-control": "G2", "no-cvss": "G5",
                     "synthesized-state": "G6"}
    seen_clear = 0
    for name in sorted(os.listdir(base)):
        pkg = os.path.join(base, name)
        if not os.path.isdir(pkg):
            continue
        g, _ = run_gates(pkg)
        blocked = [r["gate"] for r in g.blocked]
        want_block = not name.startswith("promote-")
        record(bool(blocked) == want_block,
               f"lifecycle/{name}: decision is {'block' if want_block else 'promote'}",
               f"blocked_by={blocked}")
        if not want_block:
            seen_clear += 1
            continue
        suffix = name.split("block-", 1)[-1]
        want_gate = expected_gate.get(suffix)
        if want_gate:
            record(blocked == [want_gate],
                   f"lifecycle/{name}: blocked by {want_gate} and nothing else",
                   f"blocked_by={blocked}")
    record(seen_clear >= 1, "lifecycle: at least one fixture promotes cleanly",
           "a gate set that blocks everything is useless")

    # G4 regression: the synthetic signature lives in the review CORPUS, not in one review.
    # A package carrying a single plausible review is indistinguishable on its own, so G4 must also
    # audit the engagement's whole claim_adjudication set. Running the gates over the eleven spotify
    # findings on 2026-08-10 passed G4 on all eleven while the engagement corpus audited synthetic.
    #
    # The fixture keeps reviews at `unproven/<id>/reviews/`, which is where real engagements put
    # them. It used to keep them in a top-level `reviews/` dir — a layout no engagement has ever
    # had. The fixture was shaped to the code, so this check passed for a month while the corpus arm
    # of G4 silently found nothing on every real engagement. Reshaped 2026-08-11. If this fixture is
    # ever restructured again, restructure it toward what engagements actually look like.
    corp = os.path.join(ROOT, "fixtures", "lifecycle-corpus")
    pkg = os.path.join(corp, "unproven", "F-CORP")
    if os.path.isdir(pkg):
        alone, _ = run_gates(pkg)
        with_corpus, _ = run_gates(pkg, corp)
        record([r["gate"] for r in alone.blocked] == [],
               "lifecycle-corpus: the package alone shows nothing",
               f"blocked_by={[r['gate'] for r in alone.blocked]}")
        record([r["gate"] for r in with_corpus.blocked] == ["G4"],
               "lifecycle-corpus: the engagement corpus is what blocks G4",
               f"blocked_by={[r['gate'] for r in with_corpus.blocked]}")

    # G2 regression: a declaration cannot turn a replay into a negative control. These cases vary
    # only the ref used in proof.negative_control_refs and exercise the production G2 function
    # against a synthetic attempt ledger.
    control_fixture = os.path.join(ROOT, "fixtures", "lifecycle-control-kind")
    if os.path.isdir(control_fixture):
        from finding_lifecycle import Gates, g2_control

        def control_case(name):
            case = os.path.join(control_fixture, "cases", name)
            finding = load_json(os.path.join(case, "finding.json"))
            attest = load_json(os.path.join(case, "attest.json"))
            gate = Gates()
            g2_control(finding, attest, gate, control_fixture)
            return gate.rows[0]

        replay = control_case("replay-as-control")
        matched = control_case("matched-control")
        record(not replay["ok"], "lifecycle-control-kind: replay-as-control blocks G2",
               replay["detail"])
        record(matched["ok"], "lifecycle-control-kind: matched control clears G2",
               matched["detail"])


def check_g1_g6_attempt_resolution():
    """G1 resolves the primary attempt against the ledger — Phase 9's other half.

    G1 used to check that a ref existed and a boolean was set. Both are strings the package writes
    about itself, so it could be satisfied by naming an attempt that never ran. It now resolves the
    ref and requires a non-control record with a signalling outcome — the mirror of G2, which
    requires the control to resolve to held/no_signal.

    Three paths, all asserted, because the first version got the legacy case wrong: it blocked both
    already-promoted obyte findings, whose attempts.jsonl is a pre-lifecycle research journal with
    no addressable records at all. An empty ledger is a format gap; a populated ledger missing one
    ref is a dangling reference. Only the second is a defect."""
    print("\n[finding-lifecycle] G1 + G6 attempt resolution")
    base = os.path.join(ROOT, "fixtures", "lifecycle-attempts")
    if not os.path.isdir(base):
        return
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    try:
        from finding_lifecycle import run_gates
    except ImportError as exc:
        record(False, "g1: module is importable", str(exc))
        return
    for name, want_block in (("F-G1-OK", False), ("F-G1-DANGLING", True), ("F-G1-HELD", True)):
        pkg = os.path.join(base, "unproven", name)
        if not os.path.isdir(pkg):
            record(False, f"g1/{name}: fixture present", "missing")
            continue
        g, _ = run_gates(pkg, base)
        g1 = [r for r in g.rows if r["gate"] == "G1"]
        blocked = bool(g1) and not g1[0]["ok"]
        record(blocked == want_block,
               f"g1/{name}: {'blocks' if want_block else 'clears'}",
               g1[0]["detail"] if g1 else "no G1 row")

    # G6 resolution — Phase 9's last conversion. G6 was a pure string check, so obyte-2026-08-004,
    # the finding it exists to catch, passed if you relabelled one dict value. It now resolves
    # `established_by` when that value is an attempt ref. Two declaration shapes are legitimate in
    # the wild — an attempt id (angular-cli) and an evidence path with prose (obyte) — so the prose
    # case must still PASS, or the conversion would false-alarm on every legacy package.
    # G2's legacy carve-out, added 2026-08-16. G1 and G6 already skipped resolution when the ledger
    # holds no addressable records; G2 did not, so both promoted obyte findings went from clear to
    # blocked on G2 alone. The empty-ledger case must PASS and the dangling-ref case must still
    # BLOCK — asserting only the first would re-open the gate entirely.
    for name, want_block in (("F-G2-DANGLING", True),):
        pkg = os.path.join(base, "unproven", name)
        if os.path.isdir(pkg):
            g, _ = run_gates(pkg, base)
            g2 = [r for r in g.rows if r["gate"] == "G2"]
            record((bool(g2) and not g2[0]["ok"]) == want_block,
                   f"g2/{name}: blocks a dangling control ref in a populated ledger",
                   g2[0]["detail"] if g2 else "no G2 row")
    eng_legacy = os.path.join(ROOT, "engagements", "obyte-ocore-2026-08")
    pkg = os.path.join(eng_legacy, "findings", "obyte-2026-08-001")
    if os.path.isdir(pkg):
        g, _ = run_gates(pkg, eng_legacy)
        g2 = [r for r in g.rows if r["gate"] == "G2"]
        record(bool(g2) and g2[0]["ok"],
               "g2/legacy-ledger: a pre-lifecycle attempts.jsonl does not block",
               g2[0]["detail"] if g2 else "no G2 row")

    for name, want_block in (("F-G6-OK", False), ("F-G6-DANGLING", True), ("F-G6-CONTROL", True),
                             ("F-G6-HELD", True), ("F-G6-PROSE", False)):
        pkg = os.path.join(base, "unproven", name)
        if not os.path.isdir(pkg):
            record(False, f"g6/{name}: fixture present", "missing")
            continue
        g, _ = run_gates(pkg, base)
        g6 = [r for r in g.rows if r["gate"] == "G6"]
        blocked = bool(g6) and not g6[0]["ok"]
        record(blocked == want_block,
               f"g6/{name}: {'blocks' if want_block else 'clears'}",
               g6[0]["detail"] if g6 else "no G6 row")

    # The legacy path: a ledger with no addressable records must NOT block. Regression guard for
    # the false alarm this gate produced on its first run against obyte-ocore-2026-08.
    eng = os.path.join(ROOT, "engagements", "obyte-ocore-2026-08")
    pkg = os.path.join(eng, "findings", "obyte-2026-08-001")
    if os.path.isdir(pkg):
        g, _ = run_gates(pkg, eng)
        g1 = [r for r in g.rows if r["gate"] == "G1"]
        record(bool(g1) and g1[0]["ok"],
               "g1/legacy-ledger: a pre-lifecycle attempts.jsonl does not block",
               g1[0]["detail"] if g1 else "no G1 row")


def check_gates_on_real_data():
    """Run the gates and the corpus audit against REAL engagement directories.

    Why this exists. Every gate fixture in this repo was authored by the same person who wrote the
    gates. On 2026-08-11 that cost us: `adjudication_audit.load_reviews` was not recursive and G4's
    corpus arm looked for `<engagement>/reviews/`, a directory no engagement has ever had. Both
    failed OPEN — the audit printed CLEAR over zero reviews — and the fixture hid it because the
    fixture had been shaped to the code. The synthetic suite was green the whole time.

    So the suite now also runs on directories nobody authored to satisfy it, with outcomes already
    adjudicated by hand. These are records of known outcomes, not rules. If a package below is ever
    repaired or re-adjudicated, update the expectation and say so in the OUTCOME document."""
    print("\n[real-data] gates against adjudicated engagement packages")
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    try:
        from finding_lifecycle import run_gates
        from adjudication_audit import load_reviews, audit
    except ImportError as exc:
        record(False, "real-data: modules are importable", str(exc))
        return

    # obyte-ocore-2026-08, adjudicated 2026-08-11. 004 is the gate-validation miss: it passed all six
    # earlier gates and promoted, and its impact rested on a fee window the PoC wrote itself.
    # Assert only the gates this check is a regression test FOR — the adjudication gates whose
    # verdicts were hand-adjudicated. G0 is deliberately excluded: it reads whatever files the
    # package currently cites, so a live engagement that is still being worked moves it. On
    # 2026-08-11 a concurrent escalation added ER5-independent-poc-review.md to the 001 package,
    # citing four evidence paths that live in the ENGAGEMENT but were never copied into the
    # PACKAGE, and G0 went red. That is a genuine packaging defect and it is reported to the
    # operator — but it is not a regression in the gate machinery, and pinning it here would couple
    # this suite to someone else's in-flight work. Narrowing the claim is not the same as weakening
    # it: what is asserted below is exactly what was adjudicated.
    eng = os.path.join(ROOT, "engagements", "obyte-ocore-2026-08")
    expect = [("findings/obyte-2026-08-001", set()),
              ("findings/obyte-2026-08-003", set()),
              ("unproven/obyte-2026-08-004", {"G6"})]
    if os.path.isdir(eng):
        for rel, want in expect:
            pkg = os.path.join(eng, rel)
            if not os.path.isdir(pkg):
                record(False, f"real-data: {rel} is present", "package missing")
                continue
            g, _ = run_gates(pkg, eng)
            got = {r["gate"] for r in g.blocked} & {"G4", "G6"}
            record(got == want,
                   f"real-data/{os.path.basename(rel)}: adjudication gates blocked == {sorted(want) or '[]'}",
                   f"G4/G6 blocked={sorted(got)}; all blocked={[r['gate'] for r in g.blocked]}")

    # G4 corpus arm on real data. spotify-backstage's fifteen reviews were generated by a script that
    # hardcoded `"verdict": "supported"` (2026-08-09). The package's single review is unremarkable on
    # its own; only the corpus convicts. This is the check that was silently dead.
    spot = os.path.join(ROOT, "engagements", "spotify-backstage-2026-07")
    if os.path.isdir(spot):
        rv = load_reviews(spot)
        record(len(rv) >= 10, "real-data: the recursive walker finds the spotify corpus",
               f"found {len(rv)} review(s) — a non-recursive walker finds 0 here")
        if rv:
            verdict, _, _ = audit(rv)
            record(verdict == "synthetic",
                   "real-data: the known-fabricated spotify corpus audits synthetic",
                   f"verdict={verdict}")
        pkg = os.path.join(spot, "unproven", "F-OIDC3")
        if os.path.isdir(pkg):
            alone, _ = run_gates(pkg)
            with_corpus, _ = run_gates(pkg, spot)
            record("G4" not in [r["gate"] for r in alone.blocked],
                   "real-data/F-OIDC3: the package's own review shows nothing alone",
                   f"blocked_by={[r['gate'] for r in alone.blocked]}")
            record("G4" in [r["gate"] for r in with_corpus.blocked],
                   "real-data/F-OIDC3: the engagement corpus is what blocks G4",
                   f"blocked_by={[r['gate'] for r in with_corpus.blocked]}")

    # gemini-cli: three reviews the OPERATOR wrote by hand in one sitting to mark earlier stubs
    # non_compliant. Identical timestamps, one reviewer, one template, one verdict — structurally
    # indistinguishable from generation. It must not be convicted as `synthetic` (nothing promotes
    # on a rejection), and it must not be called `clear` either, because a batch of unreviewed kills
    # is exactly how a real finding disappears quietly.
    gem = os.path.join(ROOT, "engagements", "gemini-cli")
    if os.path.isdir(gem):
        rv = load_reviews(gem)
        if rv:
            verdict, sig, _ = audit(rv)
            record(verdict == "rejections-unreviewed",
                   "real-data/gemini-cli: an all-rejecting corpus is flagged, not convicted",
                   f"verdict={verdict}")

    # The rejecting branch must not become an escape hatch. An identically fabricated corpus has to
    # be distinguishable from an honest one in BOTH directions. The first version of the rejecting
    # rule zeroed every signal and returned `clear`, so a corpus firing all seven signals — fatal
    # ones included — passed purely because its verdicts rejected. Found 2026-08-11 by a reviewer
    # auditing the harness for downward bias, which is precisely the bias that hole would hide.
    def _fab(i, verdict):
        return {"review_id": f"fab-{i}", "review_type": "claim_adjudication",
                "recorded_at": "2026-08-11T00:00:00Z", "input_hash": "sha256:" + "a" * 64,
                "proposed_finding_id": f"F-{i}", "verdict": verdict, "corrections": [],
                "rationale": "Reviewed and found non-compliant per policy.",
                "conflicting_evidence": [], "independence": {"reviewer_id": "solo-reviewer"}}
    rej, _, _ = audit([_fab(i, "refuted") for i in range(5)])
    conf, _, _ = audit([_fab(i, "confirmed") for i in range(5)])
    record(conf == "synthetic", "fabrication/confirming corpus audits synthetic", f"verdict={conf}")
    record(rej == "rejections-unreviewed",
           "fabrication/rejecting corpus is flagged, never clear",
           f"verdict={rej} — a fabricated set of kills must stay visible")


def check_disposition_ledger():
    """The calibration arithmetic, and the floor that stops it speaking too early.

    Built 2026-08-12. Four reviewers had just read every engagement record and concluded almost
    nothing had ever been filed; the operator then said findings HAD been filed and adjudicated
    across four programs. Both were right — the repository did not know. This ledger is the only
    place external verdicts can live, so its arithmetic is worth a regression test."""
    print("\n[disposition-ledger] calibration against external verdicts")
    base = os.path.join(ROOT, "fixtures", "dispositions")
    if not os.path.isdir(base):
        return
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    try:
        import disposition_ledger as DL
    except ImportError as exc:
        record(False, "disposition-ledger: module is importable", str(exc))
        return

    class A:
        pass

    for case, want in (("under-calling", "under-calling"), ("over-calling", "over-calling"),
                       ("calibrated", "calibrated")):
        d = os.path.join(base, case)
        if not os.path.isdir(d):
            continue
        a = A(); a.root = d; a.json = True; a.min = 5
        buf = io.StringIO()
        old, sys.stdout = sys.stdout, buf
        try:
            DL.cmd_calibrate(a)
        finally:
            sys.stdout = old
        got = json.loads(buf.getvalue())
        record(got["verdict"] == want, f"dispositions/{case}: verdict is {want}",
               f"got {got['verdict']}, deltas under={got['under_called']} "
               f"agree={got['agreed']} over={got['over_called']}")

    # `not-assigned` must contribute NO delta. Folding an ungraded closure in as a zero would claim
    # an agreement that never happened — the calibrated fixture carries 7 records and 5 gradings.
    d = os.path.join(base, "calibrated")
    if os.path.isdir(d):
        a = A(); a.root = d; a.json = True; a.min = 5
        buf = io.StringIO()
        old, sys.stdout = sys.stdout, buf
        try:
            DL.cmd_calibrate(a)
        finally:
            sys.stdout = old
        got = json.loads(buf.getvalue())
        record(got["dispositions"] > got["both_graded"],
               "dispositions: an ungraded closure contributes no delta",
               f"{got['dispositions']} records, {got['both_graded']} graded")

    # A thin ledger must refuse to issue a verdict. The harness's recurring failure is a confident
    # answer over too little input; this is the one place that would be most tempting.
    a = A(); a.root = os.path.join(base, "calibrated"); a.json = True; a.min = 99
    buf = io.StringIO()
    old, sys.stdout = sys.stdout, buf
    try:
        DL.cmd_calibrate(a)
    finally:
        sys.stdout = old
    record(json.loads(buf.getvalue())["verdict"] == "insufficient-data",
           "dispositions: below the floor, no verdict is issued",
           "a lopsided two-record ledger is noise, not a finding")


def check_framing_probe():
    """Every packet handed to a grader must carry zero severity signals.

    A grader who can see the band already assigned is not grading, they are agreeing. The scrub is
    what makes the experiment an experiment, so it is asserted here rather than trusted. The
    verifier earned its keep immediately: on the first real packet (F-F1) it caught a leak the
    scrubber missed — `CVSS: S:C 8.5`, a partial vector and a score with text between them, which
    none of the three vector patterns matched."""
    print("\n[framing-probe] evidence packets carry no severity signal")
    pk = os.path.join(ROOT, "fixtures", "framing-probe", "packets-v2")
    if not os.path.isdir(pk):
        return
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    try:
        import framing_probe as FP
    except ImportError as exc:
        record(False, "framing-probe: module is importable", str(exc))
        return

    packets = sorted(f for f in os.listdir(pk) if f.endswith(".packet.json"))
    record(len(packets) >= 3, "framing-probe: packets exist", f"{len(packets)} packet(s)")
    for name in packets:
        p = json.load(open(os.path.join(pk, name)))
        leaked = FP.leaks(p["body"])
        record(not leaked, f"framing-probe/{p['finding_id']}: zero severity signals survive",
               f"{len(leaked)} leak(s): {[t for _, t in leaked[:3]]}")
        import hashlib
        record(hashlib.sha256(p["body"].encode()).hexdigest() == p["body_sha256"],
               f"framing-probe/{p['finding_id']}: body matches its recorded hash",
               "an edited packet invalidates the run it was used in")

    # The scrubber must actually remove what the detector looks for, including the F-F1 shape.
    probe = ("This is CRITICAL. CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H base score 9.8 High. "
             "Rated CVSS: S:C 8.5 and considered Medium overall, arguably Low.")
    record(not FP.leaks(FP.scrub(probe)),
           "framing-probe: the scrubber removes every signal the verifier detects",
           f"residual after scrub: {FP.leaks(FP.scrub(probe))}")

    # Three framings, one packet: the evidence must be byte-identical across them.
    if packets:
        p = json.load(open(os.path.join(pk, packets[0])))
        record(len(set(FP.FRAMINGS.values())) == 3,
               "framing-probe: the three framings are distinct texts")
        record(all(p["body"] not in v for v in FP.FRAMINGS.values()),
               "framing-probe: no framing text embeds the evidence",
               "the packet must be the only shared content")


def check_adjudication_audit():
    """Run tools/adjudication_audit.py against the fixture pair and assert both directions.

    A detector that flags every review set is useless, so this gates both ways: the synthetic case
    must be called synthetic and the independent control must stay clear. Same shape as
    check_finding_traps. The corpus is a fixture rather than a live engagement because engagements are
    untracked Plane-3 — conformance proves the detector still works, and the operator points the CLI
    at a real reviews/ directory.

    Grounded in spotify-backstage-2026-07 (2026-08-09): seven findings registered on fifteen
    claim_adjudication reviews that a script generated with the verdict hardcoded. One reviewer id,
    zero corrections, zero conflicting evidence, three rationales. See engine/autonomy.md §4."""
    print("\n[adjudication-audit] synthetic-adjudication detector")
    base = os.path.join(ROOT, "fixtures", "adjudication")
    if not os.path.isdir(base):
        return
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    try:
        from adjudication_audit import audit, load_reviews
    except ImportError as exc:
        record(False, "adjudication-audit: module is importable", str(exc))
        return
    seen = 0
    for name in sorted(os.listdir(base)):
        d = os.path.join(base, name)
        if not os.path.isdir(d):
            continue
        seen += 1
        reviews = load_reviews(d)
        verdict, signals, stats = audit(reviews)
        want = "clear" if name.startswith("independent-") else "synthetic"
        fired = sorted(s["signal"] for s in signals if s["fired"])
        record(verdict == want,
               f"adjudication/{name}: verdict is {want}",
               f"got {verdict!r} over {stats['reviews']} reviews; fired={fired}")
        record(stats["reviews"] >= 3,
               f"adjudication/{name}: corpus reaches the set-level minimum",
               f"only {stats['reviews']} reviews")
    record(seen >= 2, "adjudication: both a synthetic case and a control exist",
           f"found {seen} fixture directories")


def check_intervention_corpus():
    """Every intervention record must carry a quote, and live and backfilled must stay separable.

    The corpus is the baseline for CLM-0001 and the source of the regression corpus for
    score-finding.py. A record with no quote cannot be audited, so it must not count toward either.
    Absent corpus is not a failure; the check returns early."""
    print("\n[interventions] operator-intervention ledger")
    base = os.path.join(ROOT, "fixtures", "interventions")
    if not os.path.isdir(base):
        return
    files = sorted(f for f in os.listdir(base) if f.endswith(".json"))
    if not files:
        return
    seen = {}
    for fn in files:
        doc = load_json(os.path.join(base, fn))
        entries = doc.get("entries", [])
        record(len(entries) > 0, f"interventions/{fn}: corpus non-empty")
        record(bool(doc.get("method")), f"interventions/{fn}: declares its method",
               "add a `method` field saying how the entries were produced")
        for e in entries:
            eid = e.get("intervention_id", "?")
            refs = e.get("source_refs") or []
            record(any(r.get("quote") for r in refs),
                   f"interventions/{eid}: carries an auditable quote",
                   "no source_ref has a quote")
            record(e.get("provenance") in ("live", "backfilled"),
                   f"interventions/{eid}: provenance declared", f"got {e.get('provenance')!r}")
            dup = eid in seen
            record(not dup, f"interventions/{eid}: id is unique",
                   f"also in {seen.get(eid)}" if dup else "")
            seen[eid] = fn
            if e.get("machine_checkable"):
                record(bool(e.get("check_shape")),
                       f"interventions/{eid}: machine_checkable names its check_shape",
                       "machine_checkable is true but check_shape is absent")


def check_doctrine_mirror():
    """AGENTS.md must stay byte-identical to CLAUDE.md.

    docs/agents/domain.md documents the mirror ("edit both together") and
    evals/research-kernel/ab-readiness/preregistration.json pins a sha256 of AGENTS.md. A silent
    divergence breaks the documented convention and invalidates a frozen preregistration record.
    The convention was prose only until now; this makes it a machine check."""
    print("\n[doctrine] CLAUDE.md / AGENTS.md mirror")
    a = os.path.join(ROOT, "CLAUDE.md")
    b = os.path.join(ROOT, "AGENTS.md")
    if not (os.path.isfile(a) and os.path.isfile(b)):
        record(False, "doctrine mirror: both CLAUDE.md and AGENTS.md are present")
        return
    da = hashlib.sha256(open(a, "rb").read()).hexdigest()
    db = hashlib.sha256(open(b, "rb").read()).hexdigest()
    record(da == db, "AGENTS.md is byte-identical to CLAUDE.md",
           f"CLAUDE.md {da[:12]} != AGENTS.md {db[:12]} — edit both together")


def check_cited_fixtures():
    """Every fixture directory a card cites must exist, or the card must declare it as planned.

    A card that names a fixture path that was never built reads as calibrated evidence when
    nothing executes. Front-matter `fixture_status: planned` makes the gap explicit and passes."""
    print("\n[fixtures] card-cited fixture paths resolve")
    pat = re.compile(r"evals/[A-Za-z0-9_./-]*?fixtures/([A-Za-z0-9._-]+)/")
    for subdir in ("vulns", "patterns", "techniques"):
        for name, path in list_cards(subdir):
            text = open(path).read()
            fm = front_matter(text) or ""
            planned = re.search(r"^fixture_status:\s*planned\s*$", fm, re.MULTILINE) is not None
            cited = sorted({m.group(0) for m in pat.finditer(text)})
            for rel in cited:
                exists = os.path.isdir(os.path.join(ROOT, rel.rstrip("/")))
                if exists:
                    record(True, f"{subdir}/{name}: cited fixture exists — {rel}")
                elif planned:
                    record(True, f"{subdir}/{name}: {rel} absent, declared fixture_status: planned")
                else:
                    record(False, f"{subdir}/{name}: cited fixture exists — {rel}",
                           "directory not found; build it or declare fixture_status: planned")


def main():
    pattern_ids = collect_pattern_ids()
    cap_ids = collect_capability_ids()
    print(f"known pattern ids: {sorted(pattern_ids)}")
    print(f"known capability ids: {sorted(cap_ids)}")
    for subdir in ("patterns", "vulns", "techniques"):
        check_cards(subdir, pattern_ids, cap_ids)
    check_capabilities()
    check_capability_classes()
    check_capability_scope_flags()
    check_capability_must_reject()
    check_tool_family_manifests()
    check_tool_family_must_reject()
    check_payload_proposals()
    check_oracles()
    check_casebooks(pattern_ids)
    check_secrets()
    check_finding_fixtures()
    check_decision5_record_schemas()
    check_false_discovery_corpus()
    check_adversarial_candidates()
    check_doctrine_mirror()
    check_cited_fixtures()
    check_ideation_mapper()
    check_ablation_fixtures()
    check_kb_entries()
    check_kernel_precondition()
    check_finding_traps()
    check_intervention_corpus()
    check_adjudication_audit()
    check_disposition_ledger()
    check_framing_probe()
    check_finding_lifecycle()
    check_g1_g6_attempt_resolution()
    check_gates_on_real_data()

    print(f"\n{CHECKS} checks, {len(FAILS)} failing")
    if FAILS:
        print("CONFORMANCE: FAIL")
        return 1
    print("CONFORMANCE: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
