# Streaming network checkpoint

The existing per-worker gate now forwards bounded request and response chunks.
Native proxy clients can transfer files larger than the previous 1 MiB buffer.
`maximum_bytes` remains the admitted per-body cap, separately applied to requests
and responses. The controller supplies that cap from the signed resource bounds;
this change does not introduce an independent lifetime accounting ledger.

The proxy preserves normal response headers, including repeated Set-Cookie and
Location, transiently in memory. It excludes hop-by-hop headers, headers named by
Connection, and upstream framing headers. Each next redirect request remains
subject to destination and resolved-address admission. Direct `fetch` retains
internal redirect following and strips authorization/cookies when the origin
changes; that convenience API remains capped at 1 MiB buffered data. The native
proxy returns redirects to the client so its normal session handling can operate.
No cookie, authorization value, body or TLS private key is written to these results.

Both directions use chunks of at most 16 KiB. Declared lengths are checked before
body forwarding; unknown/chunked bodies are checked cumulatively. An exceeded
response cap, incomplete upstream body or revoked authority closes the stream
without a clean chunk terminator. The bridge retains its fixed-size queue and now
applies backpressure instead of failing legitimate bursts. Request trailers,
protocol upgrades and Expect/100-continue remain unavailable. There is no raw-body
spool and no external package was fetched.

## Repeatable local workflow

From the repository, with Python 3 and local socket/process access:

```sh
python3 evals/native-qualification/smoke/check_environment_streaming_e2e.py --output /tmp/environment-streaming.json
python3 evals/native-qualification/smoke/check_research_environment_e2e.py --output /tmp/environment-controls.json
python3 evals/native-qualification/smoke/check_environment_tls_e2e.py --output /tmp/environment-tls.json
python3 evals/native-qualification/smoke/check_environment_proxy_bridge_e2e.py --output /tmp/environment-bridge.json
```

TLS checks also need OpenSSL. At this isolated branch checkpoint the controls
scenario imports `engagement_contract` through PYTHONPATH from the coordinator's
checkout; integration must rerun it with that dependency in the same tree.
All commands should exit zero and save `status: passed`. Fixtures are harmless
local HTTP servers, sockets, processes and temporary generated TLS materials.
They do not exercise Docker, SSH, a provider or a research target.

The 16 streaming checks include a generated 6,548,736-byte download whose receiver
waits for the client to read the first chunk before sending the remainder. This
causal condition fails with the old whole-response buffering. Its incremental hash
and byte count verify that the complete transfer actually occurred. Other checks
cover declared and chunked caps, incomplete bodies, ordinary headers and cookies,
cross-origin credential stripping, declared/chunked uploads and midstream revoke.

The saved peak allocation is one Python tracemalloc observation during the host
transfer, compared with the generated body size. It includes the local HTTP fixture,
gate and host relay code. It excludes the relay subprocess, native socket buffers,
and Python allocations made before tracing. It is a bounded-allocation control,
not a process-RSS measurement, throughput benchmark or comparative speed claim.

`before-streaming.json` was saved before implementation and fails the causal
streaming condition. The final scenario corrected the short-body check to use
HTTPResponse.read() so Python actually signals an incomplete Content-Length body.
The older controls scenario now parses HTTP responses instead of assuming raw
bytes end in the payload; unknown-length responses correctly use chunked framing.
Historical prior evidence files were not changed.

Local engineering evidence only: final16 streaming,18 existing local controls,
5 TLS and10 relay checks. Real container isolation, SSH, native model-client proxy
configuration, external acquisition and provider behavior remain unverified.
