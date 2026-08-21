#!/usr/bin/env python3
"""Cross-engagement knowledge base (Phase 8 / Workstream B).

There is no cross-engagement memory in this harness. `winners.md` exists once per engagement and
nothing reads it afterwards, so every engagement starts cold in both directions. This is the gap
BETWEEN engagements only -- `engine/multi-round-orchestration.md` already handles the within-run
family registry, and this does not rebuild it.

One mechanism, two entry kinds. Four rules, each answering a way this fails (B.1):

  1. A loss must NAME THE CONTROL that held. Enforced by the schema for kind=loser.
  2. Each entry declares its TRANSFER SCOPE. This is what stops a Backstage result from
     suppressing a Kubernetes route.
  3. BOUNDED and ABANDONED are different and must be said.
  4. It changes ORDER, never removal.

Rule 4 is the one with teeth. ZSec's version multiplies a hardened target's priority down, which
buries a target that later went soft. `route` here applies a BOUNDED delta and always annotates;
`_assert_never_removes` fails loudly if the output route set ever differs from the input set.

D-09: never kills. A loser entry records that WE failed to find something -- evidence about our
search, not about the target. Killing on it converts "we did not find it" into "it is not there",
which is the omission error Skitka measured as untrainable.

Commands:
  add       validate one entry against the schema and append it to memory/kb.jsonl
  query     structured (not fuzzy) lookup -- CLAUDE.md 3 chose determinism on purpose
  route     apply the KB to a base routing order; emits reordering + annotations
  ablate    the promotion gate (B.3): an entry must change a routing decision or it is not promoted
  --self-test
"""

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KB_PATH = os.path.join(ROOT, "memory", "kb.jsonl")
SCHEMA_PATH = os.path.join(ROOT, "schemas", "kb-entry.schema.json")

# Rule 4: the delta is bounded so repeated losses cannot bury a route.
DELTA = {"winner": +1, "loser": -1}
DELTA_FLOOR, DELTA_CEIL = -1, +1


def load_kb(path=KB_PATH):
    if not os.path.isfile(path):
        return []
    out = []
    for n, line in enumerate(open(path), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"{path}:{n}: {exc}")
    return out


def validate(entry):
    """Return a list of problems. Uses jsonschema when available, plus the rules it cannot express."""
    problems = []
    try:
        import jsonschema
        schema = json.load(open(SCHEMA_PATH))
        for err in sorted(jsonschema.Draft7Validator(schema).iter_errors(entry), key=str):
            problems.append(err.message)
    except ImportError:
        for field in ("schema_version", "id", "kind", "recorded_at", "mechanism_class",
                      "transfer_scope", "boundedness", "summary", "writer"):
            if field not in entry:
                problems.append(f"'{field}' is a required property")

    # Rule 1, restated here so it holds even without jsonschema installed.
    #
    # The first version of this check was `len(control) >= 20`, and the self-test caught it:
    # "we looked and found nothing" is 27 characters and sailed through. Length does not measure
    # whether a control was NAMED. Structure does -- a shrug cannot produce an evidence ref. Same
    # lesson as the attestable-vs-computable split in the promotion gates.
    if entry.get("kind") == "loser":
        control = entry.get("control")
        if not isinstance(control, dict):
            problems.append("kind=loser requires `control` as an object with `mechanism` and "
                            "`evidence`. A named control is evidenced; 'we looked and found "
                            "nothing' is an absence of work, not a loss.")
        else:
            if len(str(control.get("mechanism", "")).strip()) < 20:
                problems.append("control.mechanism must say HOW the control holds, in mechanism terms")
            if not control.get("evidence"):
                problems.append("control.evidence must carry at least one ref (file:line, record, "
                                "or attempt id). This is the gate a shrug cannot pass.")
    # Scrubbing: a mechanism_class carrying a target name defeats the whole point of transfer_scope.
    if entry.get("transfer_scope") == "this-mechanism-class" and entry.get("applies_to"):
        problems.append("transfer_scope=this-mechanism-class must not pin applies_to; that is a "
                        "narrower scope wearing a wider label")
    return problems


def matches(entry, ctx):
    """Does this entry bear on a target described by ctx? Structured and exact, never fuzzy."""
    scope = entry["transfer_scope"]
    at = entry.get("applies_to") or {}
    if scope == "this-mechanism-class":
        return True
    key = {"this-target": "target", "this-framework": "framework", "this-language": "language"}[scope]
    want, got = at.get(key), ctx.get(key)
    return want is not None and got is not None and want == got


def _assert_never_removes(base, out):
    """Rule 4 as an assertion, not a comment. Order may change; membership may not."""
    if {r["route"] for r in base} != {r["route"] for r in out}:
        raise SystemExit("BUG: routing output changed the route SET. The KB reorders, never removes.")


def route(base, ctx, kb):
    """Apply the KB to a base order.

    `base` is [{"route": str, "family": str, "priority": int}, ...] -- higher priority runs first.
    Returns the reordered list, each row carrying the annotations that moved it.
    """
    out = []
    for row in base:
        delta, notes = 0, []
        for e in kb:
            if not matches(e, ctx):
                continue
            fams, cards = set(e.get("family", [])), set(e.get("cards", []))
            if row["route"] not in cards and row.get("family") not in fams:
                continue
            delta += DELTA.get(e["kind"], 0)
            notes.append({
                "id": e["id"],
                "kind": e["kind"],
                "boundedness": e["boundedness"],
                "control_is_proven": bool(e.get("control_is_proven")),
                "summary": e["summary"],
                "reopen_on": e.get("reopen_on"),
            })
        delta = max(DELTA_FLOOR, min(DELTA_CEIL, delta))
        out.append({**row, "priority": row["priority"] + delta, "kb_delta": delta, "kb_notes": notes})
    # Stable: equal priority keeps the base order, so the KB only ever breaks ties it earned.
    out.sort(key=lambda r: -r["priority"])
    _assert_never_removes(base, out)
    return out


def order_of(rows):
    return [r["route"] for r in rows]


def ablate(entry, fixture, kb=None):
    """B.3 promotion gate: run routing with and without the entry. No order change -> not a lesson.

    Reuses the rule `tools/ablation.py` already encodes: a promoted lesson must change an outcome.
    """
    base, ctx = fixture["base"], fixture["context"]
    others = [e for e in (kb or []) if e["id"] != entry["id"]]
    without = order_of(route(base, ctx, others))
    with_ = order_of(route(base, ctx, others + [entry]))
    changed = with_ != without
    return changed, {"without": without, "with": with_}


def cmd_add(args):
    entry = json.load(open(args.file))
    problems = validate(entry)
    if problems:
        print("REJECTED:")
        for p in problems:
            print("  -", p)
        return 1
    kb = load_kb(args.kb)
    if any(e["id"] == entry["id"] for e in kb):
        print(f"REJECTED: {entry['id']} already exists. The KB is append-only.")
        return 1

    if args.fixture:
        fx = json.load(open(args.fixture))
        changed, detail = ablate(entry, fx, kb)
        if not changed:
            print("REJECTED by the ablation gate: the entry changes no routing decision.")
            print(f"  order without: {detail['without']}")
            print(f"  order with   : {detail['with']}")
            print("  An entry that changes nothing is noise. Drop it, or write a fixture that "
                  "shows what it actually moves.")
            return 1
        entry["ablation_fixture"] = os.path.relpath(args.fixture, ROOT)
        print(f"ablation gate: PASS  {detail['without']} -> {detail['with']}")
    elif not args.no_fixture:
        print("REJECTED: pass --fixture (the B.3 gate) or --no-fixture with a reason recorded "
              "in the entry's writer.note.")
        return 1

    os.makedirs(os.path.dirname(args.kb), exist_ok=True)
    with open(args.kb, "a") as fh:
        fh.write(json.dumps(entry, sort_keys=True) + "\n")
    print(f"added {entry['id']} ({entry['kind']}, {entry['transfer_scope']}, {entry['boundedness']})")
    return 0


def cmd_query(args):
    kb = load_kb(args.kb)
    ctx = {"target": args.target, "framework": args.framework, "language": args.language}
    hits = [e for e in kb if matches(e, ctx)]
    if args.family:
        hits = [e for e in hits if args.family in e.get("family", [])]
    if args.kind:
        hits = [e for e in hits if e["kind"] == args.kind]
    if args.json:
        print(json.dumps(hits, indent=2, sort_keys=True))
        return 0
    if not hits:
        print("no entries bear on this context")
        return 0
    for e in hits:
        proven = " [control proven]" if e.get("control_is_proven") else ""
        print(f"{e['id']}  {e['kind']:7s} {e['boundedness']:9s} {e['transfer_scope']}{proven}")
        print(f"    {e['summary']}")
        if e.get("control"):
            print(f"    control: {e['control']['mechanism']}")
            print(f"    evidence: {', '.join(e['control']['evidence'])}")
        if e.get("reopen_on"):
            print(f"    reopens on: {e['reopen_on']}")
    return 0


def cmd_route(args):
    fx = json.load(open(args.fixture))
    kb = load_kb(args.kb)
    rows = route(fx["base"], fx["context"], kb)
    if args.json:
        print(json.dumps(rows, indent=2, sort_keys=True))
        return 0
    print(f"base : {order_of(fx['base'])}")
    print(f"routed: {order_of(rows)}")
    for r in rows:
        if r["kb_notes"]:
            print(f"  {r['route']}  delta={r['kb_delta']:+d}")
            for n in r["kb_notes"]:
                print(f"     {n['id']} ({n['kind']}, {n['boundedness']}) {n['summary']}")
                if n["reopen_on"]:
                    print(f"        reopens on: {n['reopen_on']}")
    return 0


def cmd_ablate(args):
    entry = json.load(open(args.file))
    fx = json.load(open(args.fixture))
    changed, detail = ablate(entry, fx, load_kb(args.kb))
    print(f"without: {detail['without']}")
    print(f"with   : {detail['with']}")
    print("ABLATION:", "PASS (changes a routing decision)" if changed else "FAIL (changes nothing)")
    return 0 if changed else 1


# ---------------------------------------------------------------- self-test

def _fx():
    return {
        "context": {"target": "acme-api", "framework": "express", "language": "javascript"},
        "base": [
            {"route": "path-traversal", "family": "traversal", "priority": 5},
            {"route": "ssrf-egress", "family": "ssrf", "priority": 5},
            {"route": "deser-gadget", "family": "deserialization", "priority": 4},
        ],
    }


def _loser():
    return {
        "schema_version": 1, "id": "KB-20260821-selftest-loser", "kind": "loser",
        "recorded_at": "2026-08-21", "mechanism_class": "path traversal via normalise-before-guard",
        "family": ["traversal"], "transfer_scope": "this-framework",
        "applies_to": {"framework": "express"}, "boundedness": "bounded",
        "control": {
            "mechanism": "the router normalises the path before the allowlist guard runs, so the "
                         "traversal family cannot reach the sink",
            "evidence": ["router/dispatch.js:88", "att-selftest-traversal-control"],
        },
        "summary": "traversal bounded by normalise-before-guard", "writer": {"role": "operator"},
        "reopen_on": "a sink reached without passing the router normaliser",
    }


def self_test():
    ok = True

    def check(name, cond, detail=""):
        nonlocal ok
        ok &= bool(cond)
        print(f"  {'ok  ' if cond else 'FAIL'} {name}" + (f"  -> {detail}" if not cond and detail else ""))

    print("[self-test] rule 1 -- a loss must name the control")
    bare = {**_loser(), "control": {"mechanism": "we looked and found nothing", "evidence": []}}
    check("a shrug is rejected", validate(bare))
    unevidenced = {**_loser()}
    unevidenced["control"] = {**unevidenced["control"], "evidence": []}
    check("an unevidenced control is rejected", validate(unevidenced))
    check("a named control is accepted", not validate(_loser()), validate(_loser()))

    print("[self-test] rule 2 -- transfer scope stops false transfer")
    e = _loser()
    check("matches its own framework", matches(e, {"framework": "express"}))
    check("does NOT match another framework", not matches(e, {"framework": "django"}))
    check("does NOT match an absent framework", not matches(e, {"target": "other"}))
    wide = {**e, "transfer_scope": "this-mechanism-class", "applies_to": None}
    wide.pop("applies_to")
    check("mechanism-class transfers everywhere", matches(wide, {"framework": "django"}))

    print("[self-test] rule 4 -- reorders, never removes")
    fx, kb = _fx(), [_loser()]
    rows = route(fx["base"], fx["context"], kb)
    check("route set is unchanged", {r["route"] for r in rows} == {r["route"] for r in fx["base"]})
    check("the loser lost priority", [r for r in rows if r["route"] == "path-traversal"][0]["kb_delta"] == -1)
    check("it was demoted, not dropped", "path-traversal" in order_of(rows))
    moved = [r for r in rows if r["route"] == "path-traversal"][0]
    check("annotation carried", moved["kb_notes"] and moved["kb_notes"][0]["reopen_on"])
    check("order actually changed", order_of(rows) != order_of(fx["base"]))

    print("[self-test] delta is bounded -- repeated losses cannot bury a route")
    many = [{**_loser(), "id": f"KB-20260821-dup-{i}"} for i in range(9)]
    r2 = route(fx["base"], fx["context"], many)
    check("nine losers still move it by exactly -1",
          [r for r in r2 if r["route"] == "path-traversal"][0]["kb_delta"] == -1)

    print("[self-test] ablation gate")
    changed, _ = ablate(_loser(), _fx(), [])
    check("an entry that reorders PASSES", changed)
    inert = {**_loser(), "id": "KB-20260821-inert", "family": ["no-such-family"]}
    changed2, _ = ablate(inert, _fx(), [])
    check("an entry that changes nothing FAILS", not changed2)

    print("[self-test] D-09 -- it never kills")
    winner = {**_loser(), "id": "KB-20260821-w", "kind": "winner"}
    winner.pop("control")
    r3 = route(fx["base"], fx["context"], [winner])
    check("a winner promotes without removing anything",
          {r["route"] for r in r3} == {r["route"] for r in fx["base"]})

    print("\nSELF-TEST:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--self-test", action="store_true")
    sub = ap.add_subparsers(dest="cmd")

    def common(p):
        p.add_argument("--kb", default=KB_PATH)

    a = sub.add_parser("add"); common(a)
    a.add_argument("--file", required=True); a.add_argument("--fixture")
    a.add_argument("--no-fixture", action="store_true"); a.set_defaults(fn=cmd_add)

    q = sub.add_parser("query"); common(q)
    for f in ("target", "framework", "language", "family", "kind"):
        q.add_argument(f"--{f}")
    q.add_argument("--json", action="store_true"); q.set_defaults(fn=cmd_query)

    r = sub.add_parser("route"); common(r)
    r.add_argument("--fixture", required=True); r.add_argument("--json", action="store_true")
    r.set_defaults(fn=cmd_route)

    b = sub.add_parser("ablate"); common(b)
    b.add_argument("--file", required=True); b.add_argument("--fixture", required=True)
    b.set_defaults(fn=cmd_ablate)

    args = ap.parse_args()
    if args.self_test:
        return self_test()
    if not getattr(args, "fn", None):
        ap.print_help(); return 2
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
