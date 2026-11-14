# Environment mechanics checkpoint

This checkpoint implements the environment adapter and host network gate. It is
not complete M3 delivery. The native tool process and container network bridge
still need integration. No real Docker daemon, SSH host, provider, or research
target was exercised here.

## Repeatable checks

Run from a checkout containing the v2 `engagement_contract` module and these files:

```sh
python3 evals/native-qualification/smoke/check_research_environment_e2e.py --output /tmp/environment-controls.json
python3 evals/native-qualification/smoke/check_environment_tls_e2e.py --output /tmp/environment-tls.json
python3 evals/native-qualification/smoke/check_environment_transport_e2e.py --output /tmp/environment-transport.json
```

The first two commands require Python 3, local Unix/TCP sockets, and process launch.
The TLS command also requires OpenSSL. It generates disposable certificates and
keys, uses an explicit test trust context, and changes no system trust store.
The third command uses a named Docker CLI simulation. It never invokes Docker.
All three should return exit code zero and `status: passed`. The scripts construct
their harmless inputs and remove their temporary directories.

At this isolated branch checkpoint, the contract module was imported through
`PYTHONPATH` from the coordinator's checkout, including its removal of the unused
`workspace_root` profile field. The manifest records the exact dependency bytes.
Integration must rerun the commands above with the contract in the same tree.

Saved results distinguish actual local controls from simulated Docker commands.
The `before-*.json` files retain initial failing runs for the missing adapter,
TLS support, and corrected Docker staging. The manifest binds current source and
result hashes; those initial script hashes intentionally differ from the final
scripts where additional failure scenarios were added.

## Adapter boundary

The host constructs `Environment(profile, limits, authorize, observe, grant=...,
dispatch_guard=...)`. The immutable dispatch grant supplies the absolute worker
lease deadline. `authorize` rechecks the current grant, and `dispatch_guard` binds
the actual command launch to the controller's admission lock. The callback must
be reentrant when the same controller thread already holds that lock. Missing
guard or expired authority refuses execution. The adapter keeps no journal;
`observe` submits intent/result observations to the controller's sole journal.

`prepare(accesses, access_files)` accepts already admitted source, binary,
application, or combined descriptors. It validates file identities, stages bytes
in a stopped owned container, creates an immutable derived image, removes the
staging container, creates the final read-only worker, and independently hashes
the prepared input archive before starting the worker. `/work` is a bounded
container tmpfs. There are no host mounts or administrative sockets. The runtime
image must already exist at its pinned digest and provide `/bin/sh` and `sleep`.
No image is pulled or installed by this adapter.

The staging image is necessary because Docker refuses `docker cp` to a read-only
root filesystem even when the container is stopped. This was checked against
[Moby's archive implementation](https://github.com/moby/moby/blob/master/daemon/archive_unix.go),
blob `a171587c4cbf0cd131e005019e508d00946f67c5`, specifically `checkWritablePath`.
The simulated CLI now reproduces that refusal. This source check is not live
Docker verification.

`execute` retains bounded, publication-checked stdout and stderr. An ordinary
nonzero command exit is a settled observation so the lead can repair setup.
Timeout, output overflow, or withheld unsafe output holds further execution.
`renew` cannot extend beyond the current grant. The independent owner expires on
lease or controller loss and checks the daemon ID, container ID, and ownership
nonce before stopping the container. Local process exit alone never claims all
descendants are absent.

`receipt()` includes exact stage/worker/image identities and unresolved creation
operations. A host can reconstruct with `receipt=...` for readback and cleanup
only. A lost create acknowledgment can bind its ID from the exact recorded name
and nonce. An unknown creation that remains absent stays unresolved. `cleanup`
checks the exact containers and owned derived image, preserving foreign objects;
the original image is never removed. Cleanup remains permitted after authority
ends. A stopped worker is not itself full resource cleanup.

SSH uses a pinned known-hosts file, explicit account/key references, batch mode,
strict host-key checking, no agent forwarding, finite calls, and the same remote
lease owner over a private stdio connection. No remote directory or new service
is provisioned. Remote clock/boot loss, disconnect, isolation, and cleanup still
need real-host verification.

## Network boundary and remaining work

`NetworkGate` admits exact protocol/host/port/address policies. It validates every
resolution and redirect, connects to the checked address, validates upstream
TLS certificates, and strips credentials when an origin changes. Its optional
Unix proxy terminates CONNECT with a host-only key and validates the inner host
and path. Plain HTTP and fragmented request bodies are supported. Lease loss
closes active sockets and permanently retires the capability. Endpoint cleanup
checks socket identity before unlinking.

The caller supplies a dispatch guard and provisions only the public CA inside
an isolated worker. No provider route belongs in this gate. Grant/account policy
and protected credential injection remain host responsibilities. At this
checkpoint the container has `network=none`; neither a native shell/browser
proxy route nor native tool IPC is connected to it. The pending bridge must
preserve native tools and enforce per-worker access before capability claims.

Real Docker, SSH, native network bypass controls, live provider behavior, sustained
operation, and the operator's fresh-target research test remain unverified.
