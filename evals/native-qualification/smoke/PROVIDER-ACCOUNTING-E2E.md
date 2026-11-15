# Provider accounting E2E

## Failure scenarios specified before implementation

1. A permitted upstream request is counted when it is sent through the provider gate. A separate retry is a separate attempt; denied/local requests do not count.
2. A response fully consumed through the gate is completed. If the upstream accepted a request but the stream is interrupted, preserve the attempt as unknown; do not report it as completed or infer a charge.
3. Replaying an identical terminal observation for a request ID is idempotent. A conflicting replay is rejected. Duplicate notifications cannot inflate controller totals.
4. Native token totals and provider-reported estimated cost flow through the public runner/controller path once. Estimated cost remains explicitly estimated. Billed/monetary cost remains unknown with a reason; absence of billed cost must never be replaced by an estimate.
5. Receipt settlement cannot charge provider/native usage a second time. An interrupted or missing usage observation remains incomplete rather than becoming zero.

## Boundaries

Use only an owned loopback fake provider, a temporary fixture engagement, the runner's native usage adapter, and public network-gate/controller APIs. No external provider, paid call, Docker environment, target research, or billing assertion. Persist the machine-readable result with request IDs or fixture details only (no credentials, request bodies, or target data).

## Repeat

From the repository root, run:

```sh
python3 evals/native-qualification/smoke/check_provider_accounting_e2e.py \
  --output evals/native-qualification/team-evidence/m5-provider-accounting-20261115/result.json
```

Requires Python 3 and local loopback socket access. It uses only temporary signed fixtures and an owned local HTTP server; it needs no model credentials, Docker daemon, target, or external network.
