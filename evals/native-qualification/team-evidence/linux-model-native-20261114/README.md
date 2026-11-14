# Linux native workflow fixture

The [scenario](../../smoke/check_linux_model_native_e2e.py) composes the production
controller, worker context, native boundary, image installer and exact resource
cleanup. It runs the actual pinned Codex or OMP binary and tool executor against
an owned deterministic TLS provider. It does not call a real provider or assess
research quality. The [failure cases](../../LINUX-MODEL-NATIVE-E2E.md) were written
before the scenario implementation.

Current observations are limited to local syntax validation, a real macOS refusal
before asset creation or Docker invocation, and signed synthetic input freezing
through `load_inputs` and `Controller.initialize` for both runtime profiles.
The synthetic inputs contain inert fixture files; no native binary ran. See
[unsupported-host.json](unsupported-host.json) and
[contract-inspection.json](contract-inspection.json). Their source hashes identify
the exact inspected scenario. No actual Linux native result is claimed here.

Run on a disposable native Linux host with rootful local Docker, readable host
identity/cgroup data, OpenSSL, Python 3.11+, `ssh-keygen`, sufficient disk and
network access to the pinned public release assets. Install the pinned base
explicitly first. Use a new asset directory for each invocation:

```sh
docker --host unix:///var/run/docker.sock pull \
  python@sha256:a83ba18aef0f865b1a4a611c2cf460fe446f2795673bbb9fe43be570439e3b39
python3 evals/native-qualification/smoke/check_linux_model_native_e2e.py \
  --runtime codex --platform linux/amd64 \
  --base-image python@sha256:a83ba18aef0f865b1a4a611c2cf460fe446f2795673bbb9fe43be570439e3b39 \
  --endpoint unix:///var/run/docker.sock \
  --directory /tmp/oslit-native-assets-codex \
  --output /tmp/oslit-native-result-codex.json
```

Repeat with `--runtime omp` and new output/asset paths. A passing result requires
image readback, two actual native tool turns with retained context and artifact,
provider/tool separation, a real lab gateway denial, renewal, watcher-loss stop,
exact receipt recovery, revocation denial, released reservation and verified
model/lab/image cleanup. Failure preserves a failed status and the observed stage.
Image cleanup stays held if native cleanup is unresolved.
Before cleanup, the result preserves the latest public model-owner and lab
receipts. A failed readback is marked unavailable, so a partial startup keeps its
observed resource identities without claiming that unobserved resources are absent.

Upload only the explicit result JSON. TLS keys, synthetic credential state,
controller scratch and runtime state live in a temporary directory. The separate
caller asset directory retains the build context, pinned host executable and tool
bundle; it is not an evidence upload. Native request bodies stay in memory.
