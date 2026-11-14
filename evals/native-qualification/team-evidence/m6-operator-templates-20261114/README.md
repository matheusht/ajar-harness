# Operator templates — 14 November 2026

The four complete unsigned access templates were materialized into private
fixtures, filled with real disposable file/profile/goal/source pins, signed with
an ephemeral operator key and accepted by the actual v2 contract loader. Source,
binary, application and combined modes all passed. Missing-template failures were
retained before authoring. The original templates still contain explicit
`REPLACE_` values and no signature, allowed-signers file or private credential.

```sh
python3 evals/native-qualification/smoke/check_engagement_templates_e2e.py \
  --output /private/results/engagement-templates.json
```

The optional OMP and SSH profile structures passed the same profile validators
after digest placeholders were replaced. All four Codex configs passed native
config validation. These are structure/packaging checks. No native executable,
model, provider, Docker/SSH lab or research target was run by this workflow.
The [operator guide](../../../../docs/agents/engagement.md) preserves those limits.
