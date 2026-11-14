# Target account request binding

The host gateway can use a signed application's named account without exposing
its credential to native tools. `TargetAccountResolver` reads a private reference
file and resolves only the accounts in the worker's current resource grant. The
file contains references, never credential values. Keep it outside engagement
records and worker inputs; the native boundary supplies its path.

```json
{
  "kind": "target-account-bindings-v1",
  "bindings": [{
    "access_id": "app-main",
    "account_ref": "owner-a",
    "origin": "https://target.example:443",
    "headers": {"Authorization": "env_TARGET_OWNER_A_AUTHORIZATION"}
  }]
}
```

`env_TARGET_OWNER_A_AUTHORIZATION` names the host environment variable
`TARGET_OWNER_A_AUTHORIZATION`. Its value is the complete header value, including
any authentication scheme. Credential references must exist at resolver startup.
An existing `Cookie` header can seed the private standard-library cookie jar.
Cookies subsequently issued by the server stay separate for each access/account
and exact origin. Anonymous requests do not reuse an account or issued cookie.

Workers select an account with `X-OSLit-Access` and `X-OSLit-Account`. Both selectors
are removed before dispatch. An omitted account means anonymous access; if more
than one granted access has the same origin, an explicit access selector is required.
The resolver checks the current resource grant and an effect covering that access,
account and environment. GET, HEAD and OPTIONS require a read effect; other admitted
HTTP methods require a write effect. A method alone does not establish that an
endpoint has no side effects. Provider origins and worker overrides of authentication
headers are rejected. Cross-origin redirects never inherit a host account binding.

The gateway strips Set-Cookie headers and withholds known credential/cookie values
in response header names, values and byte streams, including matches across chunks.
HTTP Latin-1 cookie bytes and their UTF-8 text form are both recognized. Cookie
updates are validated in a temporary jar and adopted only after all checks pass. It requests
identity content encoding and rejects other response encodings. This checks exact
known values; it does not recognize arbitrary transformations of a secret. Secret
reflection or interrupted transfer records an unknown result, even if an earlier
safe response prefix reached the worker. Cookie and known-secret storage are bounded.

## Integration contract

```python
resolver = TargetAccountResolver(
    private_reference_file, scope, grant_authorize, observe_callback,
    environment_profile_id=environment_profile_id,
)
gate = NetworkGate(routes, active, dispatch_guard=guard,
                   request_binder=resolver.bind)
```

`grant_authorize()` returns the current protected grant. The gate invokes binding
under its dispatch guard before opening the upstream socket. The observer receives
`target-network-observation-v1` intent/result records with an operation ID, selected
access/account/effect, exact origin, method and path/query digest. Results add HTTP
status, byte counts and settled/unknown status. No raw headers, bodies, query strings
or credential values enter that callback. Non-target acquisition skips account
observation. The native boundary must freeze the admitted grant at intent, supply
the actual environment profile/nonce to the controller observer, and use that same
grant for the result. Close the gate, then call the resolver's idempotent `close()`.

The controller remains the sole journal owner. The request binding does not create
a second history or infer target identity: it proves which configured logical
account was used. Target-specific identity checks are separate evidence.

## Repeatable local workflow

In the integrated tree, run with Python 3:

```sh
python3 evals/native-qualification/smoke/check_target_accounts_e2e.py --output /tmp/target-accounts.json
python3 evals/native-qualification/smoke/check_environment_streaming_e2e.py --output /tmp/target-streaming.json
python3 evals/native-qualification/smoke/check_environment_proxy_bridge_e2e.py --output /tmp/target-proxy.json
python3 evals/native-qualification/smoke/check_environment_tcp_gate_e2e.py --output /tmp/target-tcp.json
python3 evals/native-qualification/smoke/check_environment_tls_e2e.py --output /tmp/target-tls.json
```

The development lane imports the coordinator's existing `engagement_contract`
through `PYTHONPATH=/Users/matheusvsky/.codex/worktrees/setup-checked-adoption/llm-redteam-harness/tools`.
Its own tools directory is first on the scenario's import path. The integrated tree
needs no extra path. The TLS scenario also requires `openssl`; the other workflows
use Python and owned local processes only.

Expected: 48 target checks pass, plus the existing 16 streaming, 10 proxy, seven TCP
and five TLS checks. The target scenario runs real owned local HTTP receivers and
the actual gateway. Scope/grant/observer inputs are explicit engineering fixtures;
there is no model, Docker, SSH or external target. It covers two accounts, anonymous
access, initial and rotated cookies, exact origin/effect admission, override refusal,
redirect separation, secret reflection, interruption, unavailable references and
observer failure before connection. It removes the temporary reference files and
restores its fake credential environment after execution. Results contain no values.

`before-module.json`, `before-anonymous-cookie.json` and `before-hop-header.json`
retain failures before implementation or repair. `before-review.json` and
`before-review-probes.json` retain the independent review failures for header-name
reflection, Latin-1 cookie reflection and non-atomic cookie capacity checks. `after.json` and the regression
receipts retain successful results. `manifest.json` binds the scenario and source
bytes. No controller journal integration, native-boundary integration, Docker
containment, remote SSH, external provider or actual target identity is established
by these local results.
