# TCP relay host override: local E2E checks

Decision: let the trusted launcher set `HOST_GATEWAY_HOST` to an inspected,
literal RFC1918 IPv4 address (10/8, 172.16/12, or 192.168/16). Reject every
other explicit value before opening the relay listener. When it is unset or
empty, keep `host.docker.internal`. Keep
`HOST_GATEWAY_PORT` and the relay's TCP forwarding unchanged. This check does
not establish a cloud bridge address, listener exposure, or provider access.

Run `python3 experiments/native-network-preflight/tcp-relay-host-override/check.py
--private-host ASSIGNED_RFC1918_IPV4 --output /absolute/new/private-output-dir`
from the repository root. It needs Python 3, Go, an assigned private host IPv4,
and a free port 8080. It builds a disposable native relay and runs it against
an owned TCP receiver bound only to that address. The receiver accepts only
short markers from that same host address; it does not serve LAN peers. No Docker
or provider participates. The output contains `result.json` with source and
binary hashes, exact local addresses, response checks, and process cleanup.

| Failure condition | Required observation |
| --- | --- |
| Override ignored, wrong port, or broken forwarding | With `HOST_GATEWAY_HOST` set to the assigned private address and the receiver's ephemeral `HOST_GATEWAY_PORT`, a real client through relay port 8080 gets the receiver's exact reply; the receiver sees the exact marker once. |
| Public, hostname, wildcard, loopback or non-RFC1918 override accepted | Start a fresh compiled relay with each explicit value (`8.8.8.8`, `example.com`, `0.0.0.0`, `127.0.0.1`, `169.254.1.1`, `172.15.0.1`, `172.32.0.1`). Each must exit nonzero before opening port 8080; the receiver must see no marker. No DNS resolution or fallback is acceptable for these values. |
| Absent override accidentally reused | Launch a fresh relay with `HOST_GATEWAY_HOST` removed. A distinct marker must not reach the owned private receiver. First check that `host.docker.internal` does not resolve to the receiver's address here; otherwise report this negative check unavailable, not passed. Source review must still show the literal default. |
| Empty override changes Desktop default | Repeat the negative with `HOST_GATEWAY_HOST=`. The owned receiver must see no marker under the same DNS precondition. |
| Test interferes with another service or leaks a process | Fail before launch if port 8080 is occupied. Stop only relay PIDs started by this check; verify the port is free afterward and remove temporary binary. |

The default negatives only show that this local receiver was not contacted.
They do not prove where DNS routes `host.docker.internal` in Docker or cloud.
