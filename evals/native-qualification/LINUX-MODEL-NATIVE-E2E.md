# Actual Linux native model workflow

Failure cases specified before the hosted scenario implementation. This workflow
uses the actual pinned Codex or OMP model and tool runtime, separate owned Docker
containers, the production controller/dispatch/boundary and an owned TLS server
that supplies deterministic model responses. It makes no live provider request
and does not assess research quality.

Required observations:

- Unsupported host/base/runtime setup fails with its actual error and cleanup
  status. Native assets are acquired only during an explicit Linux invocation.
- The image fixture verifies every model/helper file first. A signed disposable
  contract pins the model image, retained host executable, native tool bundle,
  local lab base, harmless source, owned provider origin and worker limits.
- Codex initializes and registers its isolated native executor; OMP initializes,
  negotiates RPC and registers its isolated SDK tool catalog. OMP's separately
  signed `model_catalog` supplies its normal models.yml input. Credentials enter
  through the private model bootstrap, never through image/config/Docker argv.
- Actual native tool calls read the harmless input and write a laboratory file.
  Model and tool containers have different identities and namespaces. Tools
  cannot read model config, host-only input or model-process credentials, and
  cannot reach the provider directly or through the lab route.
- The TLS provider receives only the synthetic credential expected for its owned
  origin. Tools and persisted public evidence never receive that credential.
  TLS trust uses an owned public CA through the host's standard trust setting;
  no external provider domain is remapped and no production transport is replaced.
  Its explicit `127.0.0.2/32` loopback route remains outside the proxy's
  `NO_PROXY` entries for the local bridge. The native probe reports whether its
  sandbox blocked the lab socket; a separate operation in the same tool container
  must also observe the real lab gateway's `403` for the provider route.
- A second invocation resumes the same native session and reads the first turn's
  artifact/context. Renewal extends both owners under the existing signed grant.
- Killing the exact model watcher leaves the model container and its detached
  child stopped within the short renewed owner lease. Exact receipt-based recovery
  proves namespace/cgroup absence. Revocation rejects a later invocation.
- Partial startup and every later failure attempt boundary cleanup, then image
  fixture cleanup. The final controller receipt releases only verified resources;
  unresolved model/lab cleanup stays visible. The model image and stopped probe
  are removed only after native resources settle. Retained build context and host
  executable remain in the explicit caller asset directory.

The CLI will take `--runtime`, `--platform`, `--base-image`, `--endpoint`,
`--directory` and `--output`, matching the image fixture. Upload only the explicit
result JSON and separately selected sanitized receipts. TLS keys, synthetic
credential state, runtime scratch and build context are not evidence uploads.
At this point no actual native Linux result has been recorded. Local refusal and
signed-input inspection are recorded in
[the fixture evidence](team-evidence/linux-model-native-20261114/README.md).
