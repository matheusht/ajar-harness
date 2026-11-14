# Native UTF-8 transport check — 14 November 2026

A valid 453,000-byte multilingual prompt failed before dispatch because the wire
encoder expanded non-ASCII characters into JSON escapes. The encoder now uses
UTF-8 consistently for the outgoing wire, public payload validation, and pending
tool-result size checks. The one-MiB wire cap remains enforced on actual bytes.

Run from the integrated checkout with Python 3.11+:

```sh
python3 evals/native-qualification/smoke/check_native_utf8_transport_e2e.py --output /tmp/native-utf8.json
python3 evals/native-qualification/smoke/check_native_runtime_adapters.py --output /tmp/native-adapters.json
```

The first command starts controlled protocol subprocesses and expects four passed
checks: exact transport echo with oversized-message rejection, exact prompt hashes
through each Codex/OMP adapter, and accepted multilingual public/tool-result
payloads with secret rejection retained. `before.json` records all four failing
before the encoder change; `after.json` records all four passing. `regression.json`
records the existing two adapter groups passing. These are local transport and
adapter checks, with no model/provider call, container proof, or research qualification.

The authoring branch used the integrated checkout's `engagement_contract` module
via `PYTHONPATH`; runtime code and scenarios came from this branch. Neither the
contract nor the checked runtime adapters were replaced by test doubles; only the
native wire peers were controlled subprocess fixtures.
