# UNSIGNED TEMPLATE — application access

Replace every `REPLACE_` value, review the authority and resource limits, then sign
the resulting challenge with the operator key. This file grants no authority until signed. The initial-scope policy then covers
all artifact types inside the named owned lab and permitted effects without
additional confirmations; remote application mutations need their own effects.

- Operator allowed signers SHA256: sha256:REPLACE_ALLOWED_SIGNERS_SHA256
- Signed: [ ] operator review and signature required

```native-engagement-scope-v2
{
  "kind": "native-engagement-scope-v2",
  "engagement_id": "example-application",
  "operator_id": "REPLACE_OPERATOR_ID",
  "issued_at": "REPLACE_ISSUED_AT_UTC",
  "expires_at": null,
  "goal_sha256": "sha256:REPLACE_GOAL_SHA256",
  "goal_mode": "broad",
  "patch_required": false,
  "access": [
    {
      "id": "application-main",
      "kind": "application",
      "identity": {
        "base_url": "https://target.example.invalid",
        "version": null
      },
      "account_refs": [],
      "permissions": [
        "read",
        "write",
        "execute"
      ]
    }
  ],
  "environments": [
    {
      "profile_id": "lab-main",
      "profile_sha256": "sha256:REPLACE_ENVIRONMENT_PROFILE_SHA256",
      "capabilities": [
        "application",
        "renewable_lease",
        "network_proxy"
      ],
      "limits": {
        "memory_bytes": 1073741824,
        "cpu_count": 1,
        "pids": 128,
        "workspace_bytes": 536870912,
        "lease_seconds": 600,
        "output_bytes": 1048576
      },
      "cleanup": {
        "owned_resources": true,
        "owned_workspace": true
      }
    }
  ],
  "network": {
    "provider": [
      {
        "protocol": "https",
        "host": "api.openai.com",
        "port": 443,
        "address_policy": {
          "public_only": true,
          "cidrs": []
        }
      }
    ],
    "acquisition": [],
    "target": [
      {
        "protocol": "https",
        "host": "target.example.invalid",
        "port": 443,
        "address_policy": {
          "public_only": true,
          "cidrs": []
        }
      }
    ]
  },
  "effects": [
    {
      "id": "read-inputs",
      "kind": "read",
      "access_ids": [
        "application-main"
      ],
      "environment_ids": [
        "lab-main"
      ],
      "account_refs": [],
      "rung": "self",
      "artifact_classes": [],
      "cleanup_required": false
    },
    {
      "id": "execute-local",
      "kind": "execute",
      "access_ids": [
        "application-main"
      ],
      "environment_ids": [
        "lab-main"
      ],
      "account_refs": [],
      "rung": "self",
      "artifact_classes": [],
      "cleanup_required": false
    },
    {
      "id": "create-owned-lab",
      "kind": "artifact_create",
      "access_ids": [
        "application-main"
      ],
      "environment_ids": [
        "lab-main"
      ],
      "account_refs": [],
      "rung": "self",
      "artifact_classes": [
        "owned-lab-state-v2"
      ],
      "cleanup_required": true
    }
  ],
  "escalation_ceiling": "self",
  "benign_objectives": [
    "Inspect only the signed inputs and preserve reproducible observations without changing external state."
  ],
  "runtime_assignments": [
    {
      "profile_id": "runtime-main",
      "profile_sha256": "sha256:REPLACE_RUNTIME_PROFILE_SHA256",
      "roles": [
        "lead",
        "specialist",
        "reviewer"
      ]
    }
  ],
  "limits": {
    "hard": {
      "invocations": "REPLACE_POSITIVE_INVOCATION_BUDGET",
      "worker_seconds": "REPLACE_POSITIVE_TOTAL_WORKER_SECONDS"
    },
    "max_workers": 3,
    "max_worker_lease_seconds": 600,
    "informational": {}
  },
  "revocation": {
    "operator_stop": true,
    "disconnected_worker": "lease_expiry"
  },
  "authority_policy": "initial-scope-v1"
}
```
