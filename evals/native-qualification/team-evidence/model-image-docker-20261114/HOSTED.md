# Actual Linux model image packaging

The [hosted run](https://github.com/matheusht/redteam-harness/actions/runs/43591473203) at `029324f1` passed 16 checks for Codex and 16 for OMP on separate disposable Ubuntu amd64 runners. Each job acquired pinned assets through the production installer, built the model image from the explicit pinned Python base with build networking disabled, and read every runtime file from a never-started owned probe. Bytes, modes and root ownership matched the complete manifest. Exact owned probes and images were then removed with clean readback; the base and preexisting resources were preserved.

The [manifest](hosted-manifest.json) binds source hashes, run/job identities and byte-identical [Codex](hosted-codex.json) and [OMP](hosted-omp.json) receipts. The contexts and retained host executables stayed in the disposable runner assets; only these result receipts were uploaded. No model process, provider request or research target ran. This establishes actual packaging and image readback, not native startup or containment.

Repeat the commands in [the scenario guide](README.md) on the matching native Linux architecture. The [workflow](../../../../.github/workflows/oslit-environment.yml) selects the exact base digest and invokes the same driver. Later native integration uses its prepare/readback/cleanup functions around the actual runtime scenario.
