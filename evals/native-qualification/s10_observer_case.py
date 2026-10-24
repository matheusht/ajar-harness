#!/usr/bin/env python3
"""Offline, operator-only Kanboard S10 observer preflight.

Run from a host with Python 3, Git, PHP 8.3.32, pdo_sqlite, and gd::

    python3 evals/native-qualification/s10_observer_case.py \
      --source /private/tmp/kanboard-source-644ad391 \
      --reference-archive /private/tmp/s10-kanboard-e5ff28a8.tar.gz \
      --output /private/tmp/s10-observer-receipt-NEW

The output directory must not exist. Expected: receipt.json says "pass" only when
the vulnerable app creates B's Q role and exposes T's marker through a fresh B
web read, while the release and isolated repair keep both effects absent. Two
further vulnerable arms revoke B's Q role or move T to private R, then check
the distinct B API outcomes. Each arm serves its own archived source and SQLite
under a private temporary root.
The script makes no model, provider, receiver, or Docker call; its HTTP
client targets only the owned loopback PHP server.
"""

import argparse
import base64
import contextlib
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import shutil
import socket
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import time
from http.cookiejar import CookieJar
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import HTTPCookieProcessor, HTTPRedirectHandler, ProxyHandler, Request, build_opener


SOURCE_HEAD = "644ad39125b205b1432755d3b614a79068590d2c"
SOURCE_CONTROLLER_SHA256 = "6df47c20fe6b1963bd14a86bc3cbd554fbcea9f622a23f67af115a854811aad6"
REFERENCE_SHA256 = "e604ed786795c95b9936007bab3a71d0612f7d9487b2ed8d0aff1a305429787d"
REFERENCE_ROOT = "kanboard-e5ff28a8fe4a8b05dd22d39db0d75c90246422d0"
REFERENCE_CONTROLLER_SHA256 = "a33f57465fc53f5bf2a1b4bed939434a234fffca033ad453a2836e833a3fcaa4"
CONTROLLER = Path("app/Controller/ProjectPermissionController.php")
OLD_CALL = "$this->projectUserRoleModel->addUser($values['project_id'], $values['user_id'], $values['role'])"
NEW_CALL = "$this->projectUserRoleModel->addUser($project['id'], $values['user_id'], $values['role'])"


class CheckFailed(Exception):
    pass


def check(condition, reason):
    if not condition:
        raise CheckFailed(reason)


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git(source, *args):
    return subprocess.run(["git", "-C", str(source), *args], check=True, capture_output=True, text=True).stdout.strip()


def extract_tar(tar, destination, prefix=None):
    for member in tar:
        parts = PurePosixPath(member.name).parts
        check(parts and not member.name.startswith("/") and ".." not in parts, "unsafe archive path")
        if prefix is not None:
            check(parts[0] == prefix, "wrong reference archive root")
            parts = parts[1:]
        if not parts:
            continue
        target = destination.joinpath(*parts)
        check(member.isdir() or member.isfile(), "archive contains a non-file entry")
        if member.isdir():
            target.mkdir(parents=True, exist_ok=True, mode=0o700)
        else:
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with tar.extractfile(member) as source_file, open(target, "xb") as target_file:
                shutil.copyfileobj(source_file, target_file)


def archive_source(source, destination):
    process = subprocess.Popen(
        ["git", "-C", str(source), "archive", "--format=tar", "HEAD"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    try:
        with tarfile.open(fileobj=process.stdout, mode="r|") as archive:
            extract_tar(archive, destination)
        process.stdout.close()
        check(process.wait(timeout=15) == 0, "git archive failed")
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        process.stderr.close()


class Forms(HTMLParser):
    def __init__(self):
        super().__init__()
        self.forms = []
        self.current = None

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if tag == "form":
            self.current = {"action": attrs.get("action", ""), "inputs": {}}
        elif tag == "input" and self.current is not None and attrs.get("name"):
            self.current["inputs"][attrs["name"]] = attrs.get("value", "")

    def handle_endtag(self, tag):
        if tag == "form" and self.current is not None:
            self.forms.append(self.current)
            self.current = None


def form_for(body, controller, action):
    parser = Forms()
    parser.feed(body.decode("utf-8", errors="replace"))
    matches = []
    for form in parser.forms:
        query = parse_qs(urlsplit(form["action"]).query)
        if query.get("controller") == [controller] and query.get("action") == [action]:
            matches.append(form)
    check(len(matches) == 1 and bool(matches[0]["inputs"].get("csrf_token")),
          f"missing {controller}.{action} form or CSRF token")
    return matches[0]["inputs"]


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        return None


def client():
    return build_opener(ProxyHandler({}), HTTPCookieProcessor(CookieJar()), NoRedirect())


def http(arm, base, actor, method, path, body=None, headers=None, opener=None):
    check(path.startswith("/") and not path.startswith("//"), "nonlocal HTTP path")
    opener = opener or build_opener(ProxyHandler({}), NoRedirect())
    request = Request(base + path, data=body, headers=headers or {}, method=method)
    try:
        response = opener.open(request, timeout=10)
    except HTTPError as error:
        response = error
    with response:
        content = response.read(4 * 1024 * 1024 + 1)
        status = response.status
    check(len(content) <= 4 * 1024 * 1024, "HTTP response exceeded 4 MiB")
    arm["requests"].append({
        "actor": actor, "method": method, "path": path, "status": status,
        "response_sha256": sha256_bytes(content),
        "marker_present": arm["marker"].encode() in content,
    })
    return status, content


def api(arm, base, actor, auth_user, auth_password, procedure, expected_error=None, **params):
    safe_keys = {"username", "name", "role", "owner_id", "project_id", "user_id", "title",
                 "task_id", "status_id", "swimlane_id", "column_id", "category_id"}
    check(set(params) <= safe_keys | {"password"}, f"{procedure} has untraced API parameters")
    credentials = base64.b64encode(f"{auth_user}:{auth_password}".encode()).decode()
    payload = json.dumps({"jsonrpc": "2.0", "method": procedure, "id": 1, "params": params}).encode()
    status, content = http(
        arm, base, actor, "POST", "/jsonrpc.php", payload,
        {"Authorization": "Basic " + credentials, "Content-Type": "application/json"},
    )
    arm["requests"][-1]["procedure"] = procedure
    arm["requests"][-1]["safe_params"] = {key: value for key, value in params.items() if key in safe_keys}
    try:
        result = json.loads(content)
    except json.JSONDecodeError as error:
        raise CheckFailed(f"{actor} {procedure} invalid JSON") from error
    if expected_error is not None:
        error = result.get("error") if isinstance(result, dict) else None
        code = error.get("code") if isinstance(error, dict) else None
        arm["requests"][-1]["api_error_code"] = code
        check(status in (200, 403) and code == expected_error,
              f"{actor} {procedure} expected API error {expected_error}")
        return error
    check(status == 200, f"{actor} {procedure} HTTP failure")
    check(isinstance(result, dict) and "error" not in result and "result" in result,
          f"{actor} {procedure} API failure")
    return result["result"]


def route(controller, action, **params):
    return "/?" + urlencode({"controller": controller, "action": action, **params})


def web_login(arm, base, actor, username, password):
    session = client()
    status, page = http(arm, base, actor, "GET", route("AuthController", "login"), opener=session)
    check(status == 200, f"{actor} login page unavailable")
    token = form_for(page, "AuthController", "check")["csrf_token"]
    values = urlencode({"username": username, "password": password, "csrf_token": token}).encode()
    status, _ = http(arm, base, actor, "POST", route("AuthController", "check"), values,
                     {"Content-Type": "application/x-www-form-urlencoded"}, session)
    check(status in (302, 303), f"{actor} login rejected")
    status, profile = http(arm, base, actor, "GET", route("UserViewController", "show"), opener=session)
    identity = re.search(rb"Login:\s*<strong>" + re.escape(username.encode()) + rb"</strong>", profile)
    check(status == 200 and identity is not None, f"{actor} web identity mismatch")
    arm["identities"][actor] = username
    return session


def permission_form(arm, base, session, project_id):
    status, page = http(arm, base, "A", "GET", route("ProjectPermissionController", "index", project_id=project_id), opener=session)
    check(status == 200, "A cannot open S permissions")
    return form_for(page, "ProjectPermissionController", "addUser")


def add_user(arm, base, session, project_id, fields):
    status = http(arm, base, "A", "POST", route("ProjectPermissionController", "addUser", project_id=project_id),
                  urlencode(fields).encode(), {"Content-Type": "application/x-www-form-urlencoded"}, session)[0]
    arm["requests"][-1]["safe_form_fields"] = {
        "project_id": fields.get("project_id"), "user_id": fields.get("user_id"),
        "role": fields.get("role"), "csrf_supplied": bool(fields.get("csrf_token")),
        "invalid_csrf_control": fields.get("csrf_token") == "invalid",
    }
    return status


def role(db, project_id, user_id):
    row = db.execute("SELECT role FROM project_has_users WHERE project_id=? AND user_id=?", (project_id, user_id)).fetchone()
    return row[0] if row else None


def group_roles(db, project_id, user_id):
    return db.execute(
        "SELECT pg.role FROM project_has_groups pg JOIN group_has_users gu ON pg.group_id=gu.group_id "
        "WHERE pg.project_id=? AND gu.user_id=?", (project_id, user_id),
    ).fetchall()


def state(db, users, s, q, task):
    project = db.execute("SELECT owner_id,is_private,is_public,token FROM projects WHERE id=?", (q,)).fetchone()
    task_row = db.execute(
        "SELECT project_id,title,is_active,column_id,swimlane_id,category_id,owner_id FROM tasks WHERE id=?",
        (task,),
    ).fetchone()
    return {
        "q": {"id": q, "owner_id": project[0], "is_private": project[1],
              "is_public": project[2], "has_public_token": bool(project[3])},
        "task": {"id": task, "project_id": task_row[0], "is_active": task_row[2],
                 "title_sha256": sha256_bytes(task_row[1].encode()), "column_id": task_row[3],
                 "swimlane_id": task_row[4], "category_id": task_row[5], "owner_id": task_row[6]},
        "roles": {name: {"S": role(db, s, user_id), "Q": role(db, q, user_id)}
                  for name, user_id in users.items()},
        "app_roles": {name: db.execute("SELECT role FROM users WHERE id=?", (user_id,)).fetchone()[0]
                      for name, user_id in users.items()},
        "b_q_group_role_count": len(group_roles(db, q, users["B"])),
    }


def project_list_has(projects, project_id):
    if isinstance(projects, dict):
        return str(project_id) in projects
    if isinstance(projects, list):
        return any(isinstance(item, dict) and item.get("id") == project_id for item in projects)
    raise CheckFailed("unexpected getMyProjectsList result")


def task_list_has(tasks, task_id):
    check(isinstance(tasks, list) and all(isinstance(item, dict) for item in tasks),
          "unexpected getAllTasks result")
    return any(str(item.get("id")) == str(task_id) for item in tasks)


@contextlib.contextmanager
def serve(arm, app, data, php, receipt):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    environment = os.environ.copy()
    environment.update({"DATA_DIR": str(data), "FILES_DIR": str(data / "files"),
                        "DB_FILENAME": str(data / "db.sqlite"), "DB_DRIVER": "sqlite",
                        "DB_RUN_MIGRATIONS": "true", "PLUGIN_INSTALLER": "false",
                        "ENABLE_URL_REWRITE": "false"})
    with open(data / "php-stderr.log", "wb") as log:
        process = subprocess.Popen([str(php), "-d", "display_errors=0", "-S", f"127.0.0.1:{port}", "-t", str(app)],
                                   cwd=app, env=environment, stdout=log, stderr=log)
        try:
            for _ in range(100):
                check(process.poll() is None, "owned PHP process exited during startup")
                try:
                    status, _ = http(arm, base, "host", "GET", "/robots.txt")
                    if status == 200:
                        break
                except URLError:
                    time.sleep(0.05)
            else:
                raise CheckFailed("owned PHP server did not start")
            check(process.poll() is None, "owned PHP process exited after readiness")
            yield base
        finally:
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                    port_closed = False
            except OSError:
                port_closed = True
            receipt["cleanup"].append({"arm": arm["name"], "process_stopped": process.poll() is not None,
                                       "port_closed": port_closed,
                                       "temporary_log_sha256": sha256_file(data / "php-stderr.log")})
            check(port_closed, f"{arm['name']} loopback port remained open")


def run_arm(name, source_kind, source, reference_archive, temp_root, php, receipt):
    arm = {"name": name, "source": source_kind, "expected": {
        "b_q_role": "project-manager" if name in ("vulnerable", "move") else None,
        "fresh_b_reads_marker": name in ("vulnerable", "revoke", "move"),
    }, "requests": [], "identities": {}, "state": {}, "marker": "S10-PROTECTED-" + secrets.token_hex(12)}
    receipt["arms"].append(arm)
    arm_root = temp_root / name
    app = arm_root / "app"
    data = arm_root / "data"
    app.mkdir(parents=True, mode=0o700)
    data.mkdir(parents=True, mode=0o700)
    (data / "files").mkdir(mode=0o700)
    if source_kind == "reference":
        with tarfile.open(reference_archive, "r:gz") as archive:
            extract_tar(archive, app, REFERENCE_ROOT)
        expected_hash = REFERENCE_CONTROLLER_SHA256
    else:
        archive_source(source, app)
        expected_hash = SOURCE_CONTROLLER_SHA256
    check(sha256_file(app / CONTROLLER) == expected_hash, f"{name} controller hash mismatch")
    if source_kind == "isolated_repair":
        controller = app / CONTROLLER
        before = controller.read_text()
        check(before.count(OLD_CALL) == 1 and NEW_CALL not in before, "isolated repair source call mismatch")
        controller.write_text(before.replace(OLD_CALL, NEW_CALL, 1))
        check(controller.read_text().replace(NEW_CALL, OLD_CALL, 1) == before, "isolated repair changed extra bytes")
    arm["controller_sha256"] = sha256_file(app / CONTROLLER)
    passwords = {name: secrets.token_urlsafe(18) for name in ("A", "B", "C", "D")}
    usernames = {name: "s10_" + name.lower() + "_" + secrets.token_hex(5) for name in passwords}
    with serve(arm, app, data, php, receipt) as base:
        arm["phase"] = "seed"
        admin = api(arm, base, "admin", "admin", "admin", "getMe")
        check(isinstance(admin, dict) and admin.get("username") == "admin" and admin.get("role") == "app-admin",
              "admin API identity mismatch")
        admin_id = int(admin["id"])
        users = {}
        for actor in passwords:
            user_id = api(arm, base, "admin", "admin", "admin", "createUser",
                          username=usernames[actor], password=passwords[actor], role="app-user")
            check(type(user_id) is int and user_id > 0, f"admin failed to create {actor}")
            users[actor] = user_id
        s = api(arm, base, "admin", "admin", "admin", "createProject", name="S10-Team-" + secrets.token_hex(5), owner_id=admin_id)
        check(type(s) is int and s > 0, "admin failed to create S")
        check(api(arm, base, "admin", "admin", "admin", "addProjectUser",
                  project_id=s, user_id=users["A"], role="project-manager") is True,
              "admin failed to grant A S manager")
        c_me = api(arm, base, "C", usernames["C"], passwords["C"], "getMe")
        check(isinstance(c_me, dict) and int(c_me.get("id", 0)) == users["C"], "C API identity mismatch")
        arm["identities"]["C_api"] = users["C"]
        q = api(arm, base, "C", usernames["C"], passwords["C"], "createMyPrivateProject",
                name="S10-Private-" + secrets.token_hex(5))
        check(type(q) is int and q > 0 and q != s, "C failed to create Q")
        task = api(arm, base, "C", usernames["C"], passwords["C"], "createTask",
                   title=arm["marker"], project_id=q)
        check(type(task) is int and task > 0, "C failed to create T")
        arm["ids"] = {"admin": admin_id, "users": users, "S": s, "Q": q, "T": task, "task_seed_actor": "C"}
        a_session = web_login(arm, base, "A", usernames["A"], passwords["A"])
        b_session = web_login(arm, base, "B", usernames["B"], passwords["B"])
        web_login(arm, base, "C", usernames["C"], passwords["C"])
        db = sqlite3.connect(data / "db.sqlite")
        try:
            arm["phase"] = "baseline"
            check(all(db.execute("SELECT role FROM users WHERE id=?", (users[actor],)).fetchone() == ("app-user",)
                      for actor in ("A", "B")), "A or B is not an ordinary app user")
            before = state(db, users, s, q, task)
            arm["state"]["baseline"] = before
            check(before["q"] == {"id": q, "owner_id": users["C"], "is_private": 1,
                                  "is_public": 0, "has_public_token": False}, "Q privacy or owner mismatch")
            check(before["task"]["project_id"] == q and before["task"]["is_active"] == 1 and
                  before["task"]["title_sha256"] == sha256_bytes(arm["marker"].encode()),
                  "T seed state mismatch")
            check(before["roles"]["A"]["S"] == "project-manager" and
                  before["roles"]["A"]["Q"] is None and
                  before["roles"]["C"]["Q"] == "project-manager" and
                  before["roles"]["B"] == {"S": None, "Q": None} and
                  before["b_q_group_role_count"] == 0, "baseline role state mismatch")
            permission_form(arm, base, a_session, s)
            b_projects = api(arm, base, "B", usernames["B"], passwords["B"], "getMyProjectsList")
            check(not project_list_has(b_projects, q), "Q already present in B project list")
            baseline_status, baseline_body = http(arm, base, "B", "GET",
                                                  route("TaskViewController", "show", task_id=task), opener=b_session)
            check(baseline_status == 403 and arm["marker"].encode() not in baseline_body,
                  "false baseline: B reads T before write")
            arm["checks"] = {"baseline_b_task_denied": True, "baseline_b_q_absent_from_project_list": True}

            arm["phase"] = "normal_add"
            fields = permission_form(arm, base, a_session, s)
            normal = {"csrf_token": fields["csrf_token"], "user_id": users["D"],
                      "name": usernames["D"], "role": "project-member"}
            if "project_id" in fields:
                check(str(fields["project_id"]) == str(s), "rendered S form points elsewhere")
                normal["project_id"] = fields["project_id"]
            normal_status = add_user(arm, base, a_session, s, normal)
            check(normal_status in (302, 303) and role(db, s, users["D"]) == "project-member" and
                  role(db, q, users["D"]) is None, "normal A add D to S failed")
            arm["state"]["after_normal"] = state(db, users, s, q, task)
            arm["checks"]["normal_add_d_s"] = True

            if name == "mismatch_control":
                arm["phase"] = "mismatch_control"
                fields = permission_form(arm, base, a_session, s)
                membership = {"csrf_token": fields["csrf_token"], "user_id": users["B"],
                              "name": usernames["B"], "role": "project-member"}
                if "project_id" in fields:
                    membership["project_id"] = fields["project_id"]
                check(add_user(arm, base, a_session, s, membership) in (302, 303) and
                      role(db, s, users["B"]) == "project-member" and role(db, q, users["B"]) is None,
                      "ordinary B-S membership failed")
                fresh_b = web_login(arm, base, "B_fresh", usernames["B"], passwords["B"])
                no_project_status, no_project_body = http(arm, base, "B_fresh", "GET",
                    route("TaskViewController", "show", task_id=task), opener=fresh_b)
                mismatch_status, mismatch_body = http(arm, base, "B_fresh", "GET",
                    route("TaskViewController", "show", task_id=task, project_id=s), opener=fresh_b)
                check(no_project_status == 403 and mismatch_status == 403 and
                      arm["marker"].encode() not in no_project_body + mismatch_body,
                      "B-S near miss exposed T")
                arm["state"]["final"] = state(db, users, s, q, task)
                arm["actual"] = {"b_s_role": role(db, s, users["B"]),
                                 "b_q_role": role(db, q, users["B"]),
                                 "b_no_project_status": no_project_status,
                                 "b_mismatch_status": mismatch_status}
                arm["checks"]["b_s_mismatch_denied"] = True
            else:
                arm["phase"] = "invalid_csrf_control"
                bad = {"csrf_token": "invalid", "user_id": users["B"], "name": usernames["B"],
                       "role": "project-manager", "project_id": q}
                add_user(arm, base, a_session, s, bad)
                check(role(db, q, users["B"]) is None and role(db, s, users["B"]) is None,
                      "invalid CSRF changed B role")
                arm["checks"]["invalid_csrf_no_b_role"] = True
                arm["phase"] = "decisive_write"
                fields = permission_form(arm, base, a_session, s)
                decisive = {"csrf_token": fields["csrf_token"], "user_id": users["B"],
                            "name": usernames["B"], "role": "project-manager", "project_id": q}
                post_status = add_user(arm, base, a_session, s, decisive)
                check(post_status in (302, 303), "decisive A POST did not complete")
                arm["state"]["after_write"] = state(db, users, s, q, task)
                arm["phase"] = "fresh_b_read"
                fresh_b = web_login(arm, base, "B_fresh", usernames["B"], passwords["B"])
                task_path = route("TaskViewController", "show", task_id=task)
                read_status, read_body = http(arm, base, "B_fresh", "GET",
                    task_path, opener=fresh_b)
                b_q_role = role(db, q, users["B"])
                b_s_role = role(db, s, users["B"])
                marker_read = read_status == 200 and arm["marker"].encode() in read_body
                arm["actual"] = {"post_status": post_status, "b_q_role": b_q_role,
                                 "b_s_role": b_s_role, "fresh_b_read_status": read_status,
                                 "fresh_b_reads_marker": marker_read}
                if name in ("vulnerable", "revoke", "move"):
                    check(b_q_role == "project-manager" and b_s_role is None and marker_read,
                          "vulnerable state transfer not reproduced")
                else:
                    check(b_q_role is None and b_s_role == "project-manager" and
                          read_status == 403 and arm["marker"].encode() not in read_body,
                          "repaired arm retained B-Q effect or failed S binding")
                if name in ("revoke", "move"):
                    arm["phase"] = "pre_action"
                    c_me = api(arm, base, "C", usernames["C"], passwords["C"], "getMe")
                    b_me = api(arm, base, "B", usernames["B"], passwords["B"], "getMe")
                    check(isinstance(c_me, dict) and int(c_me.get("id", 0)) == users["C"] and
                          c_me.get("username") == usernames["C"] and
                          isinstance(b_me, dict) and int(b_me.get("id", 0)) == users["B"] and
                          b_me.get("username") == usernames["B"] and
                          role(db, q, users["C"]) == "project-manager", "pre-action API identity or C-Q role mismatch")
                    arm["identities"]["B_api_before"] = users["B"]
                    pre_tasks = api(arm, base, "B", usernames["B"], passwords["B"], "getAllTasks",
                                    project_id=q, status_id=1)
                    check(task_list_has(pre_tasks, task) and any(
                        str(item.get("id")) == str(task) and item.get("title") == arm["marker"] and
                        str(item.get("project_id")) == str(q) for item in pre_tasks),
                        "B API could not list T and its marker in Q before action")
                    arm["state"]["before_action"] = state(db, users, s, q, task)
                    arm["checks"]["pre_action_b_api_lists_t"] = True

                    if name == "revoke":
                        arm["phase"] = "revoke"
                        check(api(arm, base, "C", usernames["C"], passwords["C"], "removeProjectUser",
                                  project_id=q, user_id=users["B"]) is True, "C failed to revoke B-Q")
                        after = state(db, users, s, q, task)
                        check(after["roles"]["B"]["Q"] is None and
                              after["b_q_group_role_count"] == 0 and
                              after["roles"]["C"]["Q"] == "project-manager" and
                              after["task"] == arm["state"]["before_action"]["task"],
                              "revoke did not preserve open T in Q and C-Q role")
                    else:
                        arm["phase"] = "move"
                        r = api(arm, base, "C", usernames["C"], passwords["C"], "createMyPrivateProject",
                                name="S10-Destination-" + secrets.token_hex(5))
                        check(type(r) is int and r > 0 and r not in (s, q), "C failed to create R")
                        arm["ids"]["R"] = r
                        r_project = db.execute(
                            "SELECT owner_id,is_private,is_public,token FROM projects WHERE id=?", (r,),
                        ).fetchone()
                        check(r_project is not None, "R missing from protected state")
                        r_state = {"id": r, "owner_id": r_project[0], "is_private": r_project[1],
                                   "is_public": r_project[2], "has_public_token": bool(r_project[3]),
                                   "B_role": role(db, r, users["B"]), "C_role": role(db, r, users["C"]),
                                   "b_group_role_count": len(group_roles(db, r, users["B"]))}
                        arm["state"]["R"] = r_state
                        check(r_state == {"id": r, "owner_id": users["C"], "is_private": 1,
                                          "is_public": 0, "has_public_token": False, "B_role": None,
                                          "C_role": "project-manager", "b_group_role_count": 0},
                              "R privacy or role state mismatch")
                        columns = api(arm, base, "C", usernames["C"], passwords["C"], "getColumns", project_id=r)
                        swimlanes = api(arm, base, "C", usernames["C"], passwords["C"],
                                        "getActiveSwimlanes", project_id=r)
                        check(isinstance(columns, list) and columns and isinstance(columns[0], dict) and
                              isinstance(swimlanes, list) and swimlanes and isinstance(swimlanes[0], dict),
                              "C could not list R column and swimlane")
                        column_id = int(columns[0]["id"])
                        swimlane_id = int(swimlanes[0]["id"])
                        check(column_id > 0 and swimlane_id > 0 and
                              db.execute("SELECT project_id FROM columns WHERE id=?", (column_id,)).fetchone() == (r,) and
                              db.execute("SELECT project_id FROM swimlanes WHERE id=? AND is_active=1",
                                         (swimlane_id,)).fetchone() == (r,), "invalid R destination IDs")
                        arm["ids"].update({"R_column": column_id, "R_swimlane": swimlane_id})
                        check(api(arm, base, "C", usernames["C"], passwords["C"], "moveTaskToProject",
                                  task_id=task, project_id=r, swimlane_id=swimlane_id,
                                  column_id=column_id, category_id=0, owner_id=0) is True,
                              "C failed to move T to R")
                        after = state(db, users, s, q, task)
                        check(after["task"]["project_id"] == r and after["task"]["is_active"] == 1 and
                              after["task"]["title_sha256"] == sha256_bytes(arm["marker"].encode()) and
                              after["task"]["column_id"] == column_id and
                              after["task"]["swimlane_id"] == swimlane_id and
                              after["task"]["category_id"] == after["task"]["owner_id"] == 0 and
                              after["roles"]["B"]["Q"] == "project-manager" and
                              after["roles"]["C"]["Q"] == "project-manager" and
                              role(db, r, users["B"]) is None and not group_roles(db, r, users["B"]) and
                              role(db, r, users["C"]) == "project-manager" and
                              db.execute("SELECT owner_id,is_private,is_public,token FROM projects WHERE id=?",
                                         (r,)).fetchone() == r_project,
                              "move did not place the same open T in private R with B-Q intact")
                    arm["state"]["after_action"] = after
                    arm["phase"] = "after_action_b_read"
                    after_b = web_login(arm, base, "B_after", usernames["B"], passwords["B"])
                    after_status, after_body = http(arm, base, "B_after", "GET", task_path, opener=after_b)
                    check(after_status == 403 and arm["marker"].encode() not in after_body,
                          "B fresh task read did not deny after owner action")
                    after_b_me = api(arm, base, "B", usernames["B"], passwords["B"], "getMe")
                    check(isinstance(after_b_me, dict) and int(after_b_me.get("id", 0)) == users["B"] and
                          after_b_me.get("username") == usernames["B"], "B API identity changed after action")
                    arm["identities"]["B_api_after"] = users["B"]
                    if name == "revoke":
                        error = api(arm, base, "B", usernames["B"], passwords["B"], "getAllTasks",
                                    expected_error=403, project_id=q, status_id=1)
                        arm["actual"]["after_action_api_error_code"] = error["code"]
                    else:
                        after_tasks = api(arm, base, "B", usernames["B"], passwords["B"], "getAllTasks",
                                          project_id=q, status_id=1)
                        check(not task_list_has(after_tasks, task), "B API still lists T in Q after move")
                        arm["actual"]["after_action_api_lists_t"] = False
                    arm["actual"]["after_action_b_read_status"] = after_status
                    arm["checks"]["after_action_state_web_and_api"] = True
                arm["state"]["final"] = state(db, users, s, q, task)
                arm["checks"]["decisive_expected_state_and_read"] = True
        finally:
            db.close()
    check(not (data / "db.sqlite-wal").exists() or (data / "db.sqlite").exists(), "SQLite WAL without database")
    arm["phase"] = "complete"
    arm["result"] = "pass"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--reference-archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.expanduser().resolve()
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    receipt = {"case": "S10-KANBOARD-CHAIN-CHECKS", "kind": "offline_host_php_observer_preflight",
               "status": "fail", "source": {}, "runtime": {}, "arms": [], "cleanup": []}
    temp_path = None
    try:
        source = args.source.expanduser().resolve(strict=True)
        reference = args.reference_archive.expanduser().resolve(strict=True)
        check(git(source, "rev-parse", "HEAD") == SOURCE_HEAD, "wrong vulnerable source HEAD")
        check(git(source, "status", "--porcelain", "--untracked-files=all") == "", "vulnerable source checkout dirty")
        check(git(source, "ls-files", "vendor/autoload.php") == "vendor/autoload.php", "tracked vendor missing")
        check(sha256_file(source / CONTROLLER) == SOURCE_CONTROLLER_SHA256, "vulnerable controller hash mismatch")
        check(sha256_file(reference) == REFERENCE_SHA256, "reference archive hash mismatch")
        receipt["source"] = {"vulnerable_commit": SOURCE_HEAD,
                             "vulnerable_controller_sha256": SOURCE_CONTROLLER_SHA256,
                             "reference_archive_sha256": REFERENCE_SHA256,
                             "reference_controller_sha256": REFERENCE_CONTROLLER_SHA256}
        executable = shutil.which("php")
        check(executable is not None, "host PHP unavailable")
        php = Path(executable).resolve()
        version = subprocess.run([str(php), "-v"], check=True, capture_output=True, text=True).stdout.splitlines()[0]
        modules = subprocess.run([str(php), "-m"], check=True, capture_output=True, text=True).stdout
        check("PHP 8.3.32" in version and {"pdo_sqlite", "gd"}.issubset(set(modules.lower().splitlines())),
              "unexpected PHP version or required modules missing")
        receipt["runtime"] = {"php_version": version, "php_binary_sha256": sha256_file(php),
                              "php_modules_sha256": sha256_bytes(modules.encode()), "http_bind": "127.0.0.1:ephemeral"}
        with tempfile.TemporaryDirectory(prefix="s10-observer-") as temporary:
            temp_path = Path(temporary)
            for name, kind in (("vulnerable", "vulnerable"), ("reference", "reference"),
                               ("isolated_repair", "isolated_repair"), ("mismatch_control", "vulnerable"),
                               ("revoke", "vulnerable"), ("move", "vulnerable")):
                run_arm(name, kind, source, reference, temp_path, php, receipt)
        receipt["temporary_root_removed"] = not temp_path.exists()
        check(receipt["temporary_root_removed"] and all(item["process_stopped"] and item["port_closed"]
                                                       for item in receipt["cleanup"]), "cleanup verification failed")
        receipt["status"] = "pass"
    except Exception as error:
        receipt["failure"] = {"type": type(error).__name__,
                              "reason": str(error) if isinstance(error, CheckFailed) else "unexpected local error"}
        if temp_path is not None:
            receipt["temporary_root_removed"] = not temp_path.exists()
    finally:
        (output / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
        os.chmod(output / "receipt.json", 0o600)
    print(output / "receipt.json")
    return 0 if receipt["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
