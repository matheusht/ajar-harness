# Worker proxy bridge checkpoint

This unit follows `e748f4b93eb7f4a60063662ebf06baf797ec9cdc`. It connects ordinary
HTTP proxy clients to the existing per-worker host gate without giving the worker
a host network interface, mount, credential, or general tunnel destination.

Run in an integrated checkout:

```sh
python3 evals/native-qualification/smoke/check_environment_proxy_bridge_e2e.py --output /tmp/proxy-bridge.json
python3 evals/native-qualification/smoke/check_environment_stdio_e2e.py --output /tmp/support-pipes.json
python3 evals/native-qualification/smoke/check_environment_transport_e2e.py --output /tmp/environment-regression.json
```

Expected results are ten actual local socket/stdio bridge checks, nine simulated
environment support/pipe checks, and 22 simulated Docker command regression
checks. The bridge check needs Python 3, local TCP/Unix sockets and OpenSSL. It
uses disposable test certificates and controlled receivers. It exercises HTTP,
parallel connections, destination denial, cancellation, grant revocation,
malformed and oversized frames, HTTPS, and inner-host substitution. It changes
no system trust. The other two checks use a named Docker CLI simulation.

The first failing runs and final results are saved with source/dependency hashes.
As before, the isolated branch used the coordinator's current contract module
through `PYTHONPATH`; the final integration must rerun with that dependency in the
same tree.

## Host interface

`prepare(..., support_inputs={id: {path, manifest_sha256}})` stages pinned runtime
and bootstrap material at `/input/<id>`. Its receipt and result keep support trees
separate from target access identities. The host must admit each support pin from
the signed runtime profile or its own frozen safe bootstrap material. Only public
CA material belongs here; no provider credentials or controller journal. Image
and daemon inspection precede archive creation, so unavailable infrastructure does
not cause a large temporary SDK copy. Input readback verifies the support bytes
before the worker starts.

`launch_stdio(argv, role='native_tools')` also admits the fixed `network_proxy`
host role. Each role gets one persistent process. Model requests do not choose
roles or call this API. Revocation closes all tracked pipes and stops the exact
container.

The host creates the bridge with:

```python
bridge = ProxyBridge(
    lambda argv: environment.launch_stdio(argv, role='network_proxy'),
    ['/usr/bin/python3', '/input/bootstrap/engagement_network_bridge.py', 'relay'],
    gate, authorize, dispatch_guard=dispatch_guard,
)
proxy_environment = bridge.environment('/input/bootstrap/proxy-ca.pem')
```

The pinned worker image needs Python 3. The relay uses only its standard library.
It listens on an ephemeral worker loopback port. Native tools receive proxy and
CA environment variables; literal localhost destinations remain local to the
worker. Docker remains `network=none`, and direct external connections remain
outside the relay. Actual containment still needs a real Docker/SSH check.

Every relay stream is connected to the same fixed host Unix gate. Frames carry
only a stream identifier and bounded bytes, never a host path or destination for
the bridge to dial. The gate checks HTTP destinations and inner TLS authorities.
The protocol caps streams at eight, raw frames at 16 KiB, encoded lines at 24 KiB,
and the output queue at 64 frames. Invalid protocol, overflow, or lost authority
closes the capability. Private payloads are never journaled by the bridge.

`close()` reports host process exit and explicitly requires environment readback
for native exit. The runner must close the gate and revoke/read back the
environment on protocol loss or grant end. A failed request can have a target
effect; closed pipes or a failed client do not prove otherwise.

## Remaining integration

The local test is an actual transport/gate check, not native Docker/SSH execution.
Linux runtime bundles and provider behavior remain unavailable. Full M3 also
requires the next bounded streaming/header unit, native runner wiring, and real
isolation evidence. This checkpoint does not claim full package acquisition or
authenticated application support from the earlier buffered gateway alone.
