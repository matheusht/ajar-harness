# Native host-client loopback gate

`NetworkGate.serve_tcp(certificate=..., private_key=...)` returns an ephemeral
127.0.0.1 port. It uses the same handler, admission, streaming limits and TLS
verification as the Unix gate. One gate owns one listener. Worker lab routes and
host provider routes remain separate gate instances; this method does not assign
routes or supply credentials. The caller owns the CA/private key and passes only
the public CA to the native model client. For a TCP gate `endpoint` is None.

```python
gate = NetworkGate(routes, authorize, dispatch_guard=guard)
port = gate.serve_tcp(certificate=public_ca_path, private_key=host_key_path)
proxy_url = f"http://127.0.0.1:{port}"
# Configure the intended native client's HTTPS proxy and public CA trust here.
# Keep the gate alive only while the controller grant remains active.
gate.close()
```

For a local self-signed TLS fixture only, tests supply
`upstream_context=ssl.create_default_context(cafile=str(fixture_certificate))`.
The constructor still requires CERT_REQUIRED and hostname validation; production
uses the standard verified context by default.

Run with Python 3, OpenSSL, local socket and process access:

```sh
python3 evals/native-qualification/smoke/check_environment_tcp_gate_e2e.py --output /tmp/environment-tcp.json
python3 evals/native-qualification/smoke/check_environment_streaming_e2e.py --output /tmp/environment-streaming.json
python3 evals/native-qualification/smoke/check_environment_proxy_bridge_e2e.py --output /tmp/environment-bridge.json
```

Expect exit zero and status passed. The TCP scenario generates disposable TLS
materials and starts a harmless local HTTPS server. Its7 checks cover loopback
binding, an ordinary Python HTTPS proxy client with both TLS legs verified,
duplicate listener refusal, denied destination, active bytes, midstream revocation
and cleanup. The 16 streaming and10 Unix relay checks passed again.
`before-tcp.json` records missing serve_tcp before implementation. Source and
result hashes are in manifest.json. No provider, native Codex/OMP client, OS
sandbox, Docker or SSH qualification is claimed by these local checks.
