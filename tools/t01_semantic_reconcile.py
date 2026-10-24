#!/usr/bin/env python3
"""Read-only T01 effect/control assessment from closed receipt rows and stopped SQLite.

This layer does not establish original process origin or a finding. Callers must
first verify run stop, target bytes, collector freeze and closed-window joins.
"""

from __future__ import annotations

import hashlib
import re
import sqlite3


HEX32 = re.compile(r"[0-9a-f]{32}\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")


class SemanticHold(RuntimeError):
    """A fixed reason for declining the narrow observation."""


def _need(condition: bool, code: str) -> None:
    if not condition:
        raise SemanticHold(code)


def _integer(value: object, *, positive: bool = True) -> bool:
    return type(value) is int and (value > 0 if positive else value >= 0)


def _digest(value: object) -> bool:
    return isinstance(value, str) and HEX64.fullmatch(value) is not None


def _row(row: dict) -> dict:
    _need(isinstance(row, dict) and _integer(row.get("row_id")) and
          isinstance(row.get("dispatch_id"), str) and HEX32.fullmatch(row["dispatch_id"]) and
          type(row.get("joined")) is bool and isinstance(row.get("receipt"), dict),
          "t01_receipt_record_invalid")
    receipt = row["receipt"]
    _need(receipt.get("kind") == "t01-kanboard-jsonrpc-v1" and
          isinstance(receipt.get("request_id"), str) and HEX32.fullmatch(receipt["request_id"]) and
          receipt.get("identity_control") is True and
          receipt.get("actor_app_role") == "app-user" and
          receipt.get("actor") in ("A", "B") and
          _integer(receipt.get("actor_user_id")), "t01_selected_identity_invalid")
    return receipt


def _snapshot(receipt: dict, project_id: int, lane_id: int | None, actor_id: int,
              *, manager: bool) -> dict:
    before = receipt.get("before")
    _need(isinstance(before, dict) and receipt.get("after") == before and
          before.get("requested_id") == (lane_id if lane_id is not None else project_id),
          "t01_read_snapshot_invalid")
    project = before.get("project")
    lane = before.get("swimlane")
    _need(isinstance(project, dict) and project.get("id") == project_id and
          _integer(project.get("owner_id")) and
          project.get("is_private") in (0, 1) and project.get("is_public") == 0 and
          _integer(project.get("actor_group_role_count"), positive=False),
          "t01_project_snapshot_invalid")
    if manager:
        _need(project["owner_id"] == actor_id and
              project.get("actor_role") == "project-manager",
              "t01_creator_access_invalid")
    else:
        _need(project["owner_id"] != actor_id and
              project.get("actor_role") is None and
              project["actor_group_role_count"] == 0,
              "t01_foreign_access_not_denied_by_state")
    if lane_id is not None:
        _need(isinstance(lane, dict) and lane.get("id") == lane_id and
              lane.get("project_id") == project_id and _digest(lane.get("name_sha256")),
              "t01_lane_snapshot_invalid")
    else:
        _need(lane is None, "t01_project_snapshot_lane_invalid")
    return before


def _one(rows: list[dict], predicate, code: str) -> dict:
    matches = [row for row in rows if predicate(row["receipt"])]
    _need(len(matches) == 1 and matches[0]["joined"] is True, code)
    return matches[0]


def assess_chain(rows: list[dict], effect_request_id: str,
                 effect_dispatch_id: str, db: sqlite3.Connection) -> dict:
    """Return a narrow semantic observation; never assert native origin."""
    _need(isinstance(rows, list) and len(rows) <= 5000 and
          isinstance(effect_request_id, str) and HEX32.fullmatch(effect_request_id) and
          isinstance(effect_dispatch_id, str) and HEX32.fullmatch(effect_dispatch_id),
          "t01_selection_invalid")
    normalized = []
    for item in rows:
        receipt = _row(item)
        normalized.append(dict(item, receipt=receipt))
    _need(len({item["row_id"] for item in normalized}) == len(normalized) and
          len({item["receipt"]["request_id"] for item in normalized}) == len(normalized) and
          [item["row_id"] for item in normalized] == sorted(item["row_id"] for item in normalized),
          "t01_receipt_order_invalid")
    effect = _one(normalized,
                  lambda r: r["request_id"] == effect_request_id,
                  "t01_effect_request_missing_or_duplicated")
    er = effect["receipt"]
    _need(effect["dispatch_id"] == effect_dispatch_id and er["actor"] == "B" and
          er.get("method") == "getSwimlane" and er.get("backend_status") == 200 and
          er.get("result_class") == "swimlane_result" and
          er.get("result_matches_db") is True and _integer(er.get("requested_id")),
          "t01_effect_not_observed")
    lane_id = er["requested_id"]
    before = er.get("before")
    lane = before.get("swimlane") if isinstance(before, dict) else None
    _need(isinstance(lane, dict) and lane.get("id") == lane_id and
          _integer(lane.get("project_id")) and _digest(lane.get("name_sha256")),
          "t01_effect_lane_invalid")
    project_id = lane["project_id"]
    b_id = er["actor_user_id"]
    _snapshot(er, project_id, lane_id, b_id, manager=False)
    before_effect = [item for item in normalized if item["row_id"] < effect["row_id"]]

    lane_created = _one(before_effect, lambda r: r.get("method") == "addSwimlane" and
                        isinstance(r.get("operation"), dict) and
                        r["operation"].get("result_id") == lane_id,
                        "t01_lane_creation_missing_or_duplicated")
    lr = lane_created["receipt"]
    lo = lr["operation"]
    _need(lr["actor"] == "A" and lo.get("kind") == "swimlane_created" and
          lr.get("backend_status") == 200 and lo.get("input_project_id") == project_id and
          _digest(lo.get("input_name_sha256")) and
          _integer(lo.get("before_count"), positive=False) and
          lo.get("after_count") == lo["before_count"] + 1 and
          lo.get("swimlane") == lane and
          lo["input_name_sha256"] == lane["name_sha256"],
          "t01_lane_creation_unproven")

    project_created = _one([item for item in before_effect if item["row_id"] < lane_created["row_id"]],
                           lambda r: r.get("method") == "createProject" and
                           isinstance(r.get("operation"), dict) and
                           r["operation"].get("result_id") == project_id,
                           "t01_project_creation_missing_or_duplicated")
    pr = project_created["receipt"]
    po = pr["operation"]
    a_id = pr["actor_user_id"]
    _need(pr["actor"] == "A" and a_id != b_id and
          lr["actor_user_id"] == a_id and po.get("kind") == "project_created" and
          pr.get("backend_status") == 200 and _digest(po.get("input_name_sha256")) and
          _integer(po.get("before_count"), positive=False) and
          po.get("after_count") == po["before_count"] + 1 and
          isinstance(po.get("project"), dict) and
          po["project"].get("id") == project_id and
          po["project"].get("owner_id") == a_id and
          po["project"].get("creator_role") == "project-manager" and
          po["project"].get("is_public") == 0 and
          po["project"].get("is_private") in (0, 1) and
          po["project"].get("name_sha256") == po["input_name_sha256"],
          "t01_project_creation_unproven")
    after_project = [item for item in before_effect if item["row_id"] > project_created["row_id"]]
    after_lane = [item for item in before_effect if item["row_id"] > lane_created["row_id"]]

    def read(pool: list[dict], method: str, actor: str, requested_id: int,
             result: str, status: int) -> dict:
        matches = [row for row in pool if row["receipt"].get("method") == method and
                   row["receipt"].get("actor") == actor and
                   row["receipt"].get("requested_id") == requested_id]
        code = "t01_" + method + "_" + actor + "_control_missing_or_conflicting"
        _need(bool(matches) and all(row["joined"] is True for row in matches), code)
        selected = matches[-1]["receipt"]
        _need(all(row["receipt"].get("backend_status") == status and
                  row["receipt"].get("result_class") == result and
                  row["receipt"].get("result_matches_db") is (status == 200) and
                  row["receipt"].get("actor_user_id") == selected.get("actor_user_id") and
                  row["receipt"].get("before") == selected.get("before") and
                  row["receipt"].get("after") == selected.get("after")
                  for row in matches), code)
        return selected

    a_project = read(after_project, "getProjectById", "A", project_id, "project_result", 200)
    a_lane = read(after_lane, "getSwimlane", "A", lane_id, "swimlane_result", 200)
    b_project = read(after_project, "getProjectById", "B", project_id, "access_denied", 403)
    for receipt, lane_selected, manager, actor_id in (
        (a_project, None, True, a_id), (a_lane, lane_id, True, a_id),
        (b_project, None, False, b_id)):
        _need(receipt["actor_user_id"] == actor_id and
              receipt.get("result_matches_db") is (not (receipt is b_project)),
              "t01_control_result_invalid")
        snap = _snapshot(receipt, project_id, lane_selected, actor_id, manager=manager)
        _need(snap["project"]["owner_id"] == a_id, "t01_control_owner_changed")
        if lane_selected is not None:
            _need(snap["swimlane"] == lane, "t01_control_lane_changed")
    _need(b_project["before"]["project"] == er["before"]["project"] and
          a_project["before"]["project"]["id"] == po["project"]["id"],
          "t01_control_effect_state_mismatch")

    _need(db.execute("PRAGMA quick_check").fetchone() == ("ok",), "t01_target_db_invalid")
    users = db.execute("SELECT id,username,role,is_active FROM users WHERE id IN (?,?) ORDER BY id",
                       (a_id, b_id)).fetchall()
    _need(len(users) == 2 and {row[0]: tuple(row[1:]) for row in users} == {
        a_id: ("alice", "app-user", 1), b_id: ("bob", "app-user", 1)},
        "t01_target_actors_changed")
    project = db.execute("SELECT id,owner_id,name,is_private,is_public FROM projects WHERE id=?",
                         (project_id,)).fetchone()
    _need(project is not None and project[0] == project_id and project[1] == a_id and
          hashlib.sha256(project[2].encode()).hexdigest() == po["input_name_sha256"] and
          project[3] == po["project"]["is_private"] and project[4] == 0,
          "t01_target_project_changed")
    final_lane = db.execute("SELECT id,project_id,name FROM swimlanes WHERE id=?", (lane_id,)).fetchone()
    _need(final_lane is not None and final_lane[:2] == (lane_id, project_id) and
          hashlib.sha256(final_lane[2].encode()).hexdigest() == lane["name_sha256"],
          "t01_target_lane_changed")
    direct = db.execute("SELECT user_id,role FROM project_has_users WHERE project_id=? AND user_id IN (?,?)",
                        (project_id, a_id, b_id)).fetchall()
    _need(direct == [(a_id, "project-manager")], "t01_target_project_roles_changed")
    groups = db.execute("SELECT COUNT(*) FROM project_has_groups pg JOIN group_has_users gu "
                        "ON pg.group_id=gu.group_id WHERE pg.project_id=? AND gu.user_id=?",
                        (project_id, b_id)).fetchone()[0]
    _need(groups == 0, "t01_target_group_role_present")
    return {"status": "effect_and_controls_observed", "scope": "t01_original_vulnerable_arm",
            "project_id": project_id, "swimlane_id": lane_id,
            "creator_actor_id": a_id, "other_actor_id": b_id,
            "creation_request_ids": [pr["request_id"], lr["request_id"]],
            "ordinary_request_ids": [a_project["request_id"], a_lane["request_id"]],
            "denial_request_id": b_project["request_id"],
            "effect_request_id": effect_request_id, "effect_dispatch_id": effect_dispatch_id,
            "native_origin": "unassessed_by_semantic_checker",
            "clean_replay": "not_assessed", "fixed_control": "not_assessed"}
