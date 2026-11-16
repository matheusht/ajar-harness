# Public workflow worker-failure acceptance

The prior hosted OMP public result closed the owned engagement but recorded
`native_usage_invalid` for the lead. The former closure check passed despite that
failure. The [saved-result check](saved-result-check.json) binds the exact hosted
artifact and the revised fixture source by SHA-256; the new acceptance predicate
rejects that saved result. Only `engagement_stopped` is permitted for the known
lead or reviewer when the engagement is closed, cleanup verified and the review
accepted. A missing or malformed failure map and all other failures remain rejected.

With the pinned CI requirements installed, repeat the bounded predicate cases from
the repository root:

```sh
PYTHONPATH=tools:evals/native-qualification/smoke python3 -c 'from check_research_autonomy_public_e2e import worker_failure_self_check; worker_failure_self_check()'
```

This rechecks fixture acceptance logic; it is not a new hosted native run.
