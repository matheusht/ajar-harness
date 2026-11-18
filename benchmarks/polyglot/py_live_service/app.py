#!/usr/bin/env python3
"""Synthetic multi-tenant note HTTP service for LiveAdapter & SourceAdapter QA."""

from __future__ import annotations

import argparse
import http.server
import json
import sys
import urllib.parse

STORE: dict[tuple[str, str], str] = {
    ("tenant_a", "welcome"): "hello-tenant-a",
}


def get_note(tenant: str, note_id: str, requester: str) -> tuple[int, dict[str, str]]:
    if not requester:
        return 401, {"error": "unauthenticated"}
    # BUG: checks authentication (`not requester`) but omits `requester != tenant` authorization!
    key = (tenant, note_id)
    if key not in STORE:
        return 404, {"error": "not_found"}
    return 200, {"tenant": tenant, "note_id": note_id, "body": STORE[key]}


class NoteHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: object) -> None:
        return

    def _send(self, code: int, payload: dict[str, object]) -> None:
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        parsed = urllib.parse.urlsplit(self.path)
        qs = urllib.parse.parse_qs(parsed.query)
        if parsed.path == "/health":
            self._send(200, {"ok": True})
            return
        parts = [p for p in parsed.path.split("/") if p]
        if len(parts) == 3 and parts[0] == "notes":
            requester = (qs.get("requester") or [""])[0]
            code, payload = get_note(parts[1], parts[2], requester)
            self._send(code, payload)
            return
        self._send(404, {"error": "unknown_route"})

    def do_POST(self) -> None:
        parsed = urllib.parse.urlsplit(self.path)
        length = int(self.headers.get("Content-Length") or "0")
        body = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        if parsed.path == "/seed":
            tenant = str(body["tenant"])
            note_id = str(body["note_id"])
            STORE[(tenant, note_id)] = str(body["body"])
            self._send(200, {"seeded": True})
            return
        if parsed.path == "/teardown":
            tenant = str(body["tenant"])
            note_id = str(body["note_id"])
            STORE.pop((tenant, note_id), None)
            self._send(200, {"deleted": True})
            return
        self._send(404, {"error": "unknown_route"})


def run_selftest(mode: str) -> int:
    STORE[("tenant_b", "secret")] = "CANARY_SECRET_VALUE"
    if mode == "control":
        c1, p1 = get_note("tenant_a", "welcome", "tenant_a")
        c2, _ = get_note("tenant_a", "welcome", "")
        if c1 == 200 and p1.get("body") == "hello-tenant-a" and c2 == 401:
            print("CONTROL_OK")
            return 0
        return 1
    if mode == "poc":
        code, payload = get_note("tenant_b", "secret", "tenant_a")
        if code == 200 and "CANARY_SECRET_VALUE" in str(payload.get("body", "")):
            print("IDOR_LEAKED:" + str(payload["body"]))
            return 1
        print("IDOR_BLOCKED")
        return 0
    return 2


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--serve", type=int, default=0)
    parser.add_argument("--selftest", choices=["control", "poc"])
    args = parser.parse_args()
    if args.selftest:
        return run_selftest(args.selftest)
    if args.serve > 0:
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", args.serve), NoteHandler)
        srv.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
