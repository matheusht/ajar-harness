# Provider accounting and controlled adapter completion

The saved accounting result passed on 15 November 2026 using a signed temporary
fixture, real controller and NetworkGate, and an owned loopback HTTP provider.
Four requests reached that provider: three full responses (including an HTTP 503)
and one interrupted response. No external provider or target was contacted.

The journal retained retries, interruption after revocation, exact replay,
per-invocation tokens/estimated cost and incomplete history/usage. Billing stayed
unknown. The [scenario](../../smoke/PROVIDER-ACCOUNTING-E2E.md) gives the repeat
command and requirements. Its cases were specified before implementation;
there is no saved pre-fix failing execution.

`adapters.json` retains the controlled Codex/OMP protocol check after adding the
missing `HostOperation` fixture import. Repeat from the repository root:

```sh
python3 evals/native-qualification/smoke/check_native_runtime_adapters.py --output /tmp/native-adapters.json
```

Expected: each result has `status: passed`. These subprocess peers do not run
real inference. `manifest.json` binds source and result bytes. Local structural
conformance separately passed 900 checks with zero failures. CI, fresh-target
research and a full-day run were intentionally not performed in this pass.
