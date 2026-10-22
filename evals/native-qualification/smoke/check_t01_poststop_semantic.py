#!/usr/bin/env python3
"""Provider-free T01 frozen-receipt workflow checks; no application is started."""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3


ROOT = Path(__file__).resolve().parents[3]
CHECKER = ROOT / "tools/t01_semantic_reconcile.py"
FIRST = f"{1:032x}"
RESUME = f"{2:032x}"


def sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def fixture() -> tuple[list[dict], sqlite3.Connection]:
    db = sqlite3.connect(":memory:")
    db.executescript("""
        CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, role TEXT, is_active INTEGER);
        CREATE TABLE projects (id INTEGER PRIMARY KEY, owner_id INTEGER, name TEXT, is_private INTEGER, is_public INTEGER);
        CREATE TABLE swimlanes (id INTEGER PRIMARY KEY, project_id INTEGER, name TEXT);
        CREATE TABLE project_has_users (project_id INTEGER, user_id INTEGER, role TEXT);
        CREATE TABLE project_has_groups (project_id INTEGER, group_id INTEGER, role TEXT);
        CREATE TABLE group_has_users (group_id INTEGER, user_id INTEGER);
        INSERT INTO users VALUES (2, 'alice', 'app-user', 1), (3, 'bob', 'app-user', 1);
        INSERT INTO projects VALUES (7, 2, 'synthetic project', 0, 0);
        INSERT INTO swimlanes VALUES (8, 7, 'Default swimlane'), (9, 7, 'synthetic lane');
        INSERT INTO project_has_users VALUES (7, 2, 'project-manager');
    """)
    project = {"id": 7, "owner_id": 2, "is_private": 0, "is_public": 0,
               "actor_role": "project-manager", "actor_group_role_count": 0}
    denied = dict(project, actor_role=None)
    lane = {"id": 9, "project_id": 7, "name_sha256": sha("synthetic lane")}

    def row(index: int, method: str, actor: str, requested: int | None = None,
            *, result: str = "other_result", match: bool = False,
            status: int = 200, before: dict | None = None,
            operation: dict | None = None, dispatch: str = FIRST) -> dict:
        return {"row_id": index, "dispatch_id": dispatch, "joined": True,
                "receipt": {"kind": "t01-kanboard-jsonrpc-v1", "request_id": f"{index:032x}",
                            "actor": actor, "actor_user_id": 2 if actor == "A" else 3,
                            "actor_app_role": "app-user", "identity_control": True,
                            "method": method, "requested_id": requested,
                            "backend_status": status, "result_class": result,
                            "result_matches_db": match, "before": before, "after": before,
                            "operation": operation}}

    rows = [
        row(2, "createProject", "A", operation={"kind": "project_created", "result_id": 7,
            "input_name_sha256": sha("synthetic project"), "before_count": 0,
            "after_count": 1, "project": {"id": 7, "owner_id": 2, "is_private": 0,
                "is_public": 0, "name_sha256": sha("synthetic project"),
                "creator_role": "project-manager"}}),
        row(3, "addSwimlane", "A", operation={"kind": "swimlane_created", "result_id": 9,
            "input_project_id": 7, "input_name_sha256": sha("synthetic lane"),
            "before_count": 1, "after_count": 2, "swimlane": lane}),
        row(4, "getProjectById", "A", 7, result="project_result", match=True,
            before={"requested_id": 7, "swimlane": None, "project": project}),
        row(5, "getSwimlane", "A", 9, result="swimlane_result", match=True,
            before={"requested_id": 9, "swimlane": lane, "project": project}),
        row(6, "getProjectById", "B", 7, result="access_denied", status=403,
            before={"requested_id": 7, "swimlane": None, "project": denied}),
        row(7, "getSwimlane", "B", 9, result="swimlane_result", match=True,
            before={"requested_id": 9, "swimlane": lane, "project": denied}, dispatch=RESUME),
    ]
    return rows, db


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(mode=0o700, parents=False, exist_ok=False)
    spec = importlib.util.spec_from_file_location("t01_semantic_checker", CHECKER)
    if spec is None or spec.loader is None:
        raise RuntimeError("checker_unavailable")
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    rows, db = fixture()
    checks = {}

    def observed(candidate: list[dict], *, dispatch: str = RESUME) -> bool:
        try:
            result = checker.assess_chain(candidate, f"{7:032x}", dispatch, db)
            return result["status"] == "effect_and_controls_observed"
        except checker.SemanticHold:
            return False

    checks["original_chain"] = observed(rows)
    project_control_early = copy.deepcopy(rows)
    project_control_early[1]["row_id"] = 4
    project_control_early[2]["row_id"] = 3
    project_control_early.sort(key=lambda item: item["row_id"])
    checks["project_control_before_lane_creation"] = observed(project_control_early)
    unrelated = copy.deepcopy(rows)
    extra = copy.deepcopy(rows[0])
    extra["row_id"] = 35
    extra["receipt"]["request_id"] = f"{35:032x}"
    extra["receipt"]["method"] = "getMe"
    extra["receipt"]["operation"] = None
    extra["joined"] = False
    unrelated.append(extra)
    unrelated.sort(key=lambda item: item["row_id"])
    checks["unrelated_unjoined_allowed"] = observed(unrelated)
    for label, mutate in (
        ("creation_result_changed", lambda items: items[0]["receipt"]["operation"].__setitem__("result_id", 6)),
        ("default_lane_substituted", lambda items: items[1]["receipt"]["operation"].__setitem__("result_id", 8)),
        ("creation_actor_changed", lambda items: items[0]["receipt"].__setitem__("actor", "B")),
        ("missing_ordinary", lambda items: items.pop(3)),
        ("denial_unrelated", lambda items: items[4]["receipt"].__setitem__("backend_status", 500)),
        ("foreign_role_present", lambda items: items[-1]["receipt"]["before"]["project"].__setitem__("actor_role", "project-viewer")),
        ("effect_dispatch_changed", lambda items: items[-1].__setitem__("dispatch_id", f"{3:032x}")),
        ("effect_not_joined", lambda items: items[-1].__setitem__("joined", False)),
    ):
        changed = copy.deepcopy(rows)
        mutate(changed)
        checks[label] = not observed(changed)
    checks["same_semantics_for_reviewer_dispatch"] = observed(rows, dispatch=RESUME)
    report = {"classification": "synthetic_provider_free", "checks": checks,
              "status": "pass" if all(checks.values()) else "fail",
              "provider_calls": 0, "docker_calls": 0, "target_calls": 0}
    (args.output / "result.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": report["status"], "result": str(args.output / "result.json")}, sort_keys=True))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
