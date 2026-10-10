"""Test-only builders for signed network-scope fixtures."""

import json

from network_scope import POLICY_END, POLICY_START


def scope_with_network_policy(*, host: str, path: str, method: str) -> bytes:
    policy = {
        "schema_version": 1,
        "permissions": [{
            "operation": "target_fetch",
            "scheme": "https",
            "host": host,
            "port": 443,
            "path": path,
            "method": method,
        }],
    }
    return b"# signed scope fixture\n\n" + POLICY_START + json.dumps(
        policy, sort_keys=True, separators=(",", ":")
    ).encode("utf-8") + POLICY_END + b"\n"
