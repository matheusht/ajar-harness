# Initial-scope autonomy and caller migration — 15 November 2026

[Decision 0015](../../../../docs/decisions/0015-initial-scope-autonomy.md) records
operator adoption. New signed scopes select `authority_policy: initial-scope-v1`.
Owned lab creation, contents and cleanup use one initial authority grant; already
signed internal escalation uses independent agent evidence review. No per-artifact
confirmation or refreshed signature is added. Historical scopes keep their policy.

The default public CLI and bootstrap now select v2; explicit v1 inputs and
state-only roots retain their driver. Required legacy primitives/readers remain.

## Repeat

With Python 3, OpenSSL, ssh-keygen and Unix sockets, from the repository root:

```sh
python3 evals/native-qualification/smoke/check_autonomy_policy_e2e.py --output /tmp/autonomy.json
python3 evals/native-qualification/smoke/check_native_caller_migration_e2e.py --output /tmp/callers.json
python3 evals/native-qualification/smoke/check_engagement_templates_e2e.py --output /tmp/templates.json
python3 tools/check-conformance.py
```

Expected: each command succeeds. Conformance additionally needs the repository's
existing CI Python requirements installed locally; this is not hosted CI.

- [Policy result](result.json): signed scope gating, source fake-lab startup through
  cleanup, no second approval event, persisted policy and historical defaults.
  The source/binary/application/combined row covers signed loading and effect
  selection only; the actual startup/readback fixture is source-only.
- [Policy before](before.json): the original missing-policy refusal did not exist.
- [Caller result](../caller-migration-20261115/after.json): eight CLI checks pass;
  [before](../caller-migration-20261115/before.json) retains the original failures.
  V1 fixtures prove dispatch/state initialization and readback, not a live v1 run.
- [Templates](templates.json): all four unsigned examples materialize and verify
  with fixture signatures. These keys authorize only disposable test inputs.
- [Conformance](conformance.json): 900 checks passed. The first run reported two
  stale policy pins in an unauthorized draft; the existing draft-only repin tool
  refreshed exactly those hashes. No executed study or engagement was rewritten. After the reviewer
  clarified the root scope wording, the affected mirror, pin and guidance gates
  [passed again](final-guidance.txt); the runtime source was unchanged.

The manifest pins the reviewed source and result bytes. These are local controlled
engineering checks: no physical Docker, SSH host, external provider, target or
fresh-target research was used. Pricing and hosted CI were excluded by request.
The policy/caller change does not establish runtime qualification or a multi-day run.
