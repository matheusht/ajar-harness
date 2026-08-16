# Google OSS VRP — tier roster and coverage

Generated from the program's own tier file, not from our notes:
`github.com/google/bughunters` -> `oss-repository-tier/external_repositories.txtpb`,
fetched 2026-08-14.

This file exists because `engagements/google-oss-vrp-2026-07/scope.md:4` cites three research
documents that were never written to the repository — the target-selection work survived only
in untracked `.pi-subagents/` transcripts, so the roster had to be re-fetched from GitHub to
answer 'what else is in scope'. Regenerate this file rather than hand-editing it.

**73 tiered repositories: 26 OT0 (flagship), 47 OT1.**
**Worked: 8/26 OT0, 1/47 OT1.**

Reward bands: Supply-Chain Compromise up to **$31,337** on OT0; Product-Vulnerability
**$500-$7,500** on OT0. The SCC band is 4x the top PV band, so registry, release and CI
surfaces outrank library logic on expected value.

## OT0 — worked

| repo | engagement | outcome |
|---|---|---|
| `angular/dev-infra` | angular-dev-infra-2026-08 | 2 findings promoted (F13, R8) |
| `bazelbuild/bazel` | google-oss-vrp-2026-07 | covered-dry, 0 reportable |
| `bazelbuild/continuous-integration` | bazel-continuous-integration-2026-07 | 24-round adversarial; 0 confirmed |
| `golang/crypto` | google-oss-vrp-2026-07 | covered-dry; FI-CRYPTO-SSH-1 Low, capped |
| `golang/net` | google-oss-vrp-2026-07 | covered-dry, 0 reportable |
| `google/gson` | google-oss-vrp-2026-07 | covered-dry; write-side cap non-reportable |
| `google/gvisor` | gvisor-2026-07 | both candidates refuted (ring-3 by design) |
| `protocolbuffers/protobuf` | protocolbuffers-2026-07 | PB-002 already patched; PB-003 duplicate |

## OT0 — NOT yet touched (18)

| repo | scope |
|---|---|
| `GoogleContainerTools/distroless` | SCOPE_OSS_VRP |
| `angular/angular` | SCOPE_OSS_VRP |
| `angular/angular-cli` | SCOPE_OSS_VRP |
| `angular/components` | SCOPE_OSS_VRP |
| `bazelbuild/bazel-central-registry` | SCOPE_OSS_VRP |
| `flutter/flutter` | SCOPE_OSS_VRP |
| `golang/go` | SCOPE_OSS_VRP |
| `golang/image` | SCOPE_OSS_VRP |
| `golang/sync` | SCOPE_OSS_VRP |
| `golang/sys` | SCOPE_OSS_VRP |
| `golang/text` | SCOPE_OSS_VRP |
| `golang/tools` | SCOPE_OSS_VRP |
| `google/guava` | SCOPE_OSS_VRP |
| `https://fuchsia.googlesource.com/fuchsia` | SCOPE_OSS_VRP |
| `openthread/openthread` | SCOPE_OSS_VRP |
| `tink-crypto/tink-cc` | SCOPE_OSS_VRP |
| `tink-crypto/tink-go` | SCOPE_OSS_VRP |
| `tink-crypto/tink-java` | SCOPE_OSS_VRP |

## OT1

Worked: `google-gemini/gemini-cli`.
Remaining 46:

- `ChromeDevTools/chrome-devtools-mcp`
- `Polymer/polymer`
- `bazelbuild/remote-apis-sdks`
- `cdapio/cdap`
- `cdapio/cdap-ui`
- `dart-lang/build`
- `dart-lang/sdk`
- `dart-lang/test`
- `dart-lang/tools`
- `flutter/devtools`
- `golang/vscode-go`
- `google/XNNPACK`
- `google/adk-go`
- `google/adk-java`
- `google/adk-js`
- `google/adk-python`
- `google/benchmark`
- `google/brotli`
- `google/closure-compiler`
- `google/clusterfuzz`
- `google/filament`
- `google/flatbuffers`
- `google/fonts`
- `google/go-cloud`
- `google/go-github`
- `google/libphonenumber`
- `google/osv-scanner`
- `google/re2`
- `google/shaderc`
- `google/site-kit-wp`
- `google/zerocopy`
- `googlemaps/android-maps-utils`
- `https://fuchsia.googlesource.com/fuchsia/+/refs/heads/main/src/starnix/`
- `https://gerrit.googlesource.com/gerrit`
- `https://gerrit.googlesource.com/gerrit`
- `jax-ml/jax`
- `keras-team/keras`
- `keras-team/tf-keras`
- `openxla/xla`
- `project-oak/oak`
- `shaka-project/shaka-player`
- `tensorflow/models`
- `tensorflow/serving`
- `tensorflow/tensorflow`
- `tensorflow/tfjs`
- `tensorflow/tflite-micro`

## Notes that change routing

- **The post-March-2026 memory-safety gate.** On OT0/OT1 a memory-corruption report pays only
  with an exact OSS-Fuzz reproduction via an existing fuzz target, or a merged upstream patch.
  That makes `golang/go`, `openthread/openthread` and `fuchsia` poor value despite the tier.
- **`angular/angular-cli` and `angular/components` consume `angular/dev-infra`.** A defect in
  dev-infra's own code is dev-infra's finding, not the consumer's. Attribution has to be
  settled before filing or the same bug gets filed twice.
- **Four Angular repos are OT0**, one of which is done. The remaining three share build, CI
  and release machinery, so context carries between them.
