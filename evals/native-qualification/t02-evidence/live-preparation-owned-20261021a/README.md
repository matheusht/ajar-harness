# T02 fail-closed live preparation evidence

This directory contains sanitized OSLIT receipts for the 21 October 2026 source preparation. It intentionally excludes raw command logs, session and container identifiers, temporary paths, proxy values, CA bytes, and the full owned-run result.

- `source-check.json` records 25/25 benign offline parameter and source checks. A fake-Docker marker observes no invocation, and `strace -f -e trace=network -e signal=none` observes no network syscall in the checker child or descendants. The checks reject mixed valid/malformed bundles, verification-disable variables, and `SSLKEYLOGFILE`; they also confirm that ambient host key logging creates no file and a valid generated CA still stops at `cloud_live_route_not_qualified` before output creation.
- `runtime-build.json` records the pinned `linux/amd64` runtime build and offline image inspection. The final image contained the required OpenCode/PHP components, no critical image environment names, and no exact build-CA blob in its layers.
- `owned-regression.json` is a redacted projection of the private full receipt. It records 64/64 owned synthetic-response checks, native first/reviewer/resume success, limit and Stop behavior, owned-resource cleanup, and zero provider/live-model calls.

SHA-256:

```text
c4c7c1aa36391b6dba8442870015f09e393803809a38039d80b3450b81c24624  source-check.json
e21c872cbefc53022d6dd6f23b88795e873de93c1a183d7adcdb3883fbfc2c8c  runtime-build.json
dd0d048df9e9306b7d04ef998b61e0f95803fa184d0149994d13299a113798eb  owned-regression.json
```

These receipts do not prove a reachable managed sidecar, native TLS through that sidecar, a free-provider request, or #161 interruption/recovery on an enabled live route. They do not complete #158 or #161, unblock #159/#160/#162, or change the #165 no-go decision.
