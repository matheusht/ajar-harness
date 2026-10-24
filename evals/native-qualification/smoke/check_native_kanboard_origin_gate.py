#!/usr/bin/env python3
"""Provider-free assertions for the negative-only Kanboard native origin gate."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "tools/native_kanboard_origin_gate.py"


def encoded(value: dict) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()


def fixture() -> tuple[dict, bytes, dict, bytes, dict]:
    dispatch_id = "a" * 32
    session_id = "ses_abc123"
    before = encoded({"kind": "native-dispatch-v1", "status": "unknown_effect",
                      "dispatch_id": dispatch_id, "role": "researcher",
                      "session_id": session_id, "prompt_sha256": "b" * 64})
    trace = encoded({"kind": "protected-native-event-trace-v1", "session_id": session_id,
                     "events": [{"line": 1, "part_type": "tool", "tool": "shell",
                                 "status": "completed", "session_matches": True,
                                 "input_sha256": "c" * 64,
                                 "output_sha256": "d" * 64}]})
    window = {"kind": "kanboard-native-window-v1", "dispatch_id": dispatch_id,
              "dispatch_sha256": hashlib.sha256(before).hexdigest(),
              "session_id": session_id, "role": "researcher", "target": "target",
              "credential_route": "unavailable", "native_origin": "unproven"}
    after = {"kind": "native-dispatch-v1", "status": "acknowledged",
             "dispatch_id": dispatch_id, "role": "researcher", "session_id": session_id,
             "native_trace_sha256": hashlib.sha256(trace).hexdigest()}
    audit = {"kind": "host-exec-audit-projection-v1", "complete": False,
             "unexpected_exec_count": 0}
    return window, before, after, trace, audit


def main() -> None:
    spec = importlib.util.spec_from_file_location("native_kanboard_origin_gate", SOURCE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    window, before, after, trace, audit = fixture()

    def held(expected: str, w=window, b=before, a=after, t=trace, x=audit) -> None:
        result = module.assess(w, b, a, t, x)
        assert result == {"status": "held", "reason": expected,
                          "dispatch_id": "a" * 32,
                          "native_request_attributable": False}

    held("native_credential_route_unavailable")
    held("binding_mismatch", {**window, "session_id": "ses_other"})
    held("binding_mismatch", {**window, "dispatch_sha256": "0" * 64})
    held("binding_mismatch", a={**after, "role": "reviewer-1"})
    held("dispatch_uncertain", a={**after, "status": "unknown_effect"})
    held("native_trace_unavailable", t=b"{}")
    held("native_trace_unavailable", t=encoded({"kind": "protected-native-event-trace-v1",
                                               "session_id": "ses_abc123", "events": []}))
    held("host_exec_overlap", x={**audit, "unexpected_exec_count": 1})
    held("native_credential_route_unavailable", x={**audit, "complete": True})
    held("invalid_evidence", {**window, "credential_route": "host_verified"})
    held("invalid_evidence", {**window, "Authorization": "fake"})
    held("invalid_evidence", b=b'{"kind":"native-dispatch-v1","kind":"native-dispatch-v1"}')
    held("invalid_evidence", x={**audit, "original_observation": "confirmed"})
    print("PASS: 13 provider-free origin holds; Docker/provider/target calls: 0")


if __name__ == "__main__":
    main()
