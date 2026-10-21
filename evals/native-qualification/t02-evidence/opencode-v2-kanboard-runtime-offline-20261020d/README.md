# T02 offline Kanboard and native-session integration — 20 October 2026

This is a **local, no-provider prerequisite**, not a #158 qualification pass.
The host dispatched PHP and native API commands inside the researcher image;
no model chose tools or started the application. No provider, model, hosted CI,
or target engagement was called.

Run from the repository root with Python 3, Docker Desktop on arm64, and these
cached inputs:

- official OpenCode V2 base image
  `sha256:2fc782d346b0670c43378557cf8a2a9926a1f3d28e596180e7b21a0736d8cb7d`;
- derived local image `t02-kanboard-runtime:20261020a`, exact ID
  `sha256:31b7fa2b80f17bbddfeffd0577634257df40490f1b8d4c57f8507b40956cdf15`;
- pinned vulnerable Kanboard release archive at
  `/private/tmp/native-qualification-observer-20261019-final/vulnerable.tar.gz`,
  SHA-256 `3f24269475bf00137d4b0d957d97a2567a5249101dad89067a49d609f4df2edf`.

The frozen runner, Dockerfile, config, plugin, checks, and host observer helper
are under `source/`. Choose a new output directory:

```sh
python3 evals/native-qualification/t02-evidence/opencode-v2-kanboard-runtime-offline-20261020d/source/smoke/opencode_v2_kanboard_runtime_offline.py \
  --output /private/tmp/t02-kanboard-native-rerun-UNIQUE
```

Expected result: `offline_ordinary_app_pass` and 29 passing checks. If the
derived image was pruned, rebuild from `source/Dockerfile.opencode-kanboard-runtime`
and inspect its new ID; BuildKit can produce a different ID even with the same
Dockerfile, so make a **new** pinned receipt rather than changing this one.
The release archive includes `vendor/autoload.php`; no Composer or asset build
occurs. The runner verifies all 2,100 release files before copying them.

The accepted [result](result.json), SHA-256
`f7b3b93bee6e0524f1fd4dfff5418c7e57938f5802b9bd630da5df9ecaa56266`,
shows a clean source copy, five PHP lint checks, and the loaded OpenCode V2
version/model/config/plugin. A native session was created without inference in
the same persistent workspace as the app. The separate mount-free host client
observed a synthetic project, Alice's authorized read, and Bob's HTTP 403.
After replacing both containers, the exact native session ID, project and 403
remained. A host read after clean stop returned `PRAGMA quick_check=ok` and the
same zero-cost native session. All four owned containers and the temporary
workspace/database were removed; no host port was published. The source and
config hashes in the receipt match the frozen files under `source/`.

The failed `a` receipt records the pruned prior derived image. The failed `b`
receipt records an incomplete first-page assumption for `session.list`; `c`
passed after cursor pagination, and `d` added the stopped-store check. Those
diagnostics are retained without rewriting them.

This does not reproduce the earlier live-provider SQLite read failure. The
shared inference request/charge allowance, model-driven app start, review and
delegate coverage, and combined full-application E2E remain open.
