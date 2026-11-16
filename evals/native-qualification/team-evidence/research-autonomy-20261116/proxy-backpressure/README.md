# Preserve bytes while a bridge consumer pauses

The private stdio bridge dropped a valid stream when its connected socket remained
backpressured for one second. `sendall` could deliver part of a frame before raising
its timeout; the bridge then closed the stream. The actual hosted provider fixture
reported bodies truncated to 64,155 bytes despite larger valid Content-Length values.
Those hosted errors motivated this separate failure-first IPC reproduction.

The scenario was defined and run before the product change. It uses the actual
ProxyBridge, an actual relay subprocess, owned Unix/TCP sockets and 200 KiB of fixed
bytes. A 4 KiB kernel send buffer makes pressure deterministic; the owned consumer
pauses for 1.4 seconds before reading. The second case revokes authority during that
pause. No provider, credentials, Docker, TLS or model is involved in this scenario.

- [Before](before.json): the consumer received only 4,096 of 204,800 bytes. The
  stream was already dropped before either draining or revocation.
- [After](after.json): all 204,800 bytes arrived with the expected digest after the
  pause. A separate still-backpressured stream stopped on revocation in the observed
  0.146 seconds; its partial bytes were not reported as a complete transfer. Both
  relay processes exited and sender work settled.
- [Existing proxy suite](existing-proxy-suite.json): all 10 cases passed, including
  ordinary/concurrent streams, actual local TLS, denied destinations/inner hosts,
  malformed-frame refusal, cancellation and authority revocation.

The product change clears the per-peer I/O timeout after connection. Existing
bounded frame queues provide backpressure; stop/revocation shuts down the owned
sockets and interrupts waiting reads/writes. Connection timeouts, frame sizes,
stream limits, policy checks and queue bounds are unchanged. Rebuilt runtime images
must include the changed bridge file. The next joined native run separately checks
that real provider request bodies remain intact.

## Repeat

Requirements: Python 3, local Unix/TCP sockets and subprocesses. The existing proxy
suite additionally uses OpenSSL. Run from the repository root:

```sh
python3 evals/native-qualification/smoke/check_proxy_backpressure_e2e.py --output /tmp/oslit-proxy-backpressure.json
python3 evals/native-qualification/smoke/check_environment_proxy_bridge_e2e.py --output /tmp/oslit-proxy-suite.json
```

Expected: both exit zero. The first records all three checks passing, an exact
204,800-byte transfer/digest and a revoked blocked stream stopping within two
seconds. The second records all ten checks passing. The saved before/after
backpressure receipts carry both scenario and bridge source hashes; the scenario
hash is identical across the pair. These are local transport checks, with no
container-isolation or research-efficacy claim. Original receipts are preserved.


## Large HTTPS upload and explicit cancellation

The [full TLS scenario](../../../smoke/check_network_upload_e2e.py) sends the same
652,488-byte size as the later public fixture request through actual ProxyBridge,
NetworkGate and an owned TLS receiver. On the current product source, fragmented
writes and a 1.4-second consumer pause preserved every byte and the expected digest;
the proxy recorded started then completed. A separate explicit authority revocation
preceded partial EOF and recorded started then unknown. Both owned relays stopped.
See the [result](network-upload.json), including the exact timing and source hashes.

```sh
python3 evals/native-qualification/smoke/check_network_upload_e2e.py --output /tmp/oslit-network-upload.json
```

Requirements are Python 3, OpenSSL and local sockets/subprocesses. Expected: all three
checks pass. This discriminator leaves production network timeouts unchanged. It
shows that intentional cancellation can produce a partial upstream body; it does
not retroactively classify a hosted failure. Hosted classification requires a
verified authority-ending event inside that exact request-read interval. Unexpected
active-authority truncation and malformed complete bodies remain failures.
