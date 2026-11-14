# Persistent native tool pipe

This unit follows environment mechanics commit
`dadb5ea48b5738734de2fb84ceeabe7b2dbfd26f`. It adds
`Environment.launch_stdio(argv)`, which returns a private `subprocess.Popen`
handle for one persistent process inside the exact prepared container. Local
Docker and pinned SSH use the same command path. The native adapter owns framed
IPC, message bounds, native readiness, cancellation, and tool results; the
environment owns the container lease, grant checks, process tracking, and cleanup.

Run in an integrated checkout:

```sh
python3 evals/native-qualification/smoke/check_environment_stdio_e2e.py --output /tmp/environment-stdio.json
```

Expected result: exit zero, `status: passed`, six checks. This uses a simulated
Docker CLI with an actual private OS process pipe. It confirms persistent message
exchange, restricted host environment, durable launch attribution, one native
owner per environment, revocation, and stale-generation refusal. It does not
establish Docker isolation, SSH behavior, a Linux native SDK, or a network bridge.

`before.json` records the missing-API failure before implementation. The final
result and manifest bind the tested source, fixture, and contract dependency.
The private dispatch guard is mandatory. Guard acquisition precedes the local
process lock, keeping lock order consistent with callers already holding the
controller guard. No controller lock spans a long native tool operation.

The launch event says `dispatched`, not completed or accepted by the native
tool owner. The caller must observe its native ready frame before use. Process
stdout and stdin remain private; the environment writes no transcript or raw
tool payload to its event callback. Cleanup-only reconstruction still stops the
exact container and verifies resource absence, including any tool processes.

The available SDK was observed to be for macOS. No Linux SDK/image installation,
Docker execution, or SSH connection was attempted. The development volume was
reported below 400 MiB free; only small source and replay artifacts were created.
