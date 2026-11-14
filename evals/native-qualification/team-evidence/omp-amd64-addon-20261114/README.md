# OMP amd64 addon admission correction

The [second actual Linux workflow attempt](https://github.com/matheusht/redteam-harness/actions/runs/43593621942)
at `72c9f353eeb06d5ed7291008bec707b492d00fcb` stopped in the production OMP tool
installer with `native_bundle_platform_unavailable`, before native execution.
The unchanged original receipt is retained in the
[request diagnostic evidence](../linux-native-request-diagnostics-20261114/omp-hosted-before.json).

The pinned npm 18.20.0 metadata declares
`./pi_natives.linux-x64-baseline.node` for
[@oh-my-pi/pi-natives-linux-x64](https://registry.npmjs.org/@oh-my-pi/pi-natives-linux-x64/18.20.0).
The validator instead required `./pi_natives.linux-x64.node`.
[Arm64](https://registry.npmjs.org/@oh-my-pi/pi-natives-linux-arm64/18.20.0)
still declares `./pi_natives.linux-arm64.node`. Registry archive integrities match
the existing lock, as recorded in [source metadata](source-metadata.json).
Only small metadata JSON was fetched locally, never binaries.

Failure cases were added to the existing public installer scenario before the
production correction: amd64 baseline layout must install and pass preflight;
the incorrect plain x64 filename, missing baseline addon and wrong Bun ELF
architecture must fail without leaving an installation or receipt. The existing
arm64, integrity, archive-safety and mutation checks remain in the same workflow.
Fixtures contain inert headers and package files, so these checks establish
packaging admission only. They do not execute Bun, OMP, Docker or a provider.

The [before receipt](before.json) reproduces both errors: the official amd64
layout is rejected and the incorrect plain x64 layout is accepted. After the
exact filename correction, all [14 installer cases](after.json) and the existing
[seven offline preflight cases](preflight-regression.json) pass. The
[manifest](manifest.json) identifies the source bytes used. The package lock and
installer implementation are unchanged.

Repeat from the repository root:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 evals/native-qualification/smoke/check_native_tool_install_e2e.py \
  --output /tmp/omp-amd64-installer.json
```

Expected after correction: all 14 cases pass. The production validator must keep
exact addon name/version/main/file requirements, signed manifest verification,
supported SDK/Bun checks and Bun ELF architecture validation. Actual Linux native
startup remains subject to the next hosted workflow run.
