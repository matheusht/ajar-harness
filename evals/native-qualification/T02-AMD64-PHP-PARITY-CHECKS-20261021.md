# Cloud amd64 Kanboard observer parity checks

21 October 2026. This is a bounded, no-provider replay of the existing T01
observer against the current cloud amd64 PHP image. It does not run OpenCode,
call a model, qualify a provider, or engage an external target.

Fail before the first application container if any precondition fails:

1. The work does not start from PR #174 commit
   `513b662eda0345d943eb0582f7bc39a8a6512617`, or the current observer,
   T01 result, original brief, this check file, Dockerfile, or runner cannot be
   hashed and recorded.
2. `t02-kanboard-runtime:amd64-live-prep` does not resolve locally, without a
   pull, to image ID
   `sha256:9ef722322521322a1288a18427ba5bf6ce1479085c97e0ac821982eec4f01769`
   on `linux/amd64`.
3. The Dockerfile SHA-256 is not
   `7a1ab9b257fb36a216fc1baafabc757436d0a15ffcb9498b6fbe697da3a9bf4b`,
   or the image does not report PHP 8.4.26 with `pdo_sqlite` and `gd`.
4. The repository T01 observer result SHA-256 is not
   `9db3bc220484a7a786729847f3c8fa8cc1d364a74b1e4a81d2bb78f80dc924fa`,
   or the original brief SHA-256 is not
   `8f2b5604870cf86719ae94ac180cb6cbe0c5c12cdd2356bc90f4104bb7179a5a`.
5. The vulnerable archive from commit
   `f0f7d27007f5a788f14416c548421efd740b7bce` does not have SHA-256
   `3f24269475bf00137d4b0d957d97a2567a5249101dad89067a49d609f4df2edf`,
   or the fixed archive from commit
   `a98bc5f855d4e7e47eb3425a6c7da6c6cc6748a3` does not have SHA-256
   `44db3df81a25bbd56c768c8b3180a1f05879e2c7fbaa6ac73707e7f3e9098f56`.
   Download each archive only from its pinned public codeload URL into a new
   private directory. Verify the archive before extraction, then verify every
   extracted file with `observer_case.prepare_source()`.

Fail the run if any behavior check fails:

1. Both arms must create two synthetic users and one private project, grant
   Alice project-manager access, allow Alice to read the exact project and
   swimlane, and deny Bob's project read with HTTP and JSON-RPC access denial.
2. Bob must read the exact created swimlane ID, project ID, and name in the
   vulnerable arm. The same read must return access denial in the fixed arm.
   A server error, wrong object, or unrelated denial is a failure.
3. Both arm summaries must match the pinned T01 semantics for release,
   ordinary controls, differentiated read, commit, and archive hash. Historical
   arm64 execution is only the comparator, not current-image evidence.
4. Each application container must use `--pull=never`, a read-only root,
   bounded memory, CPU, and PIDs, and one bind of its disposable application
   copy to `/app`. Do not create a researcher bundle or mount observer output,
   the fixed tree, checks, briefs, receipts, credentials, or Docker socket.
5. Saved traces must redact generated passwords and contain no Authorization
   value, cookie, token, access token, unredacted password, or private task
   path. A redacted public derivative may preserve IDs, methods, response
   semantics, image pins, and cleanup booleans.

Fail cleanup if any owned resource remains:

1. Stop only the exact container ID returned for each arm. Require that the
   container is absent, its loopback port is closed, and its disposable run
   directory and SQLite database are absent.
2. Compare containers, images, volumes, and networks with the frozen Docker
   baseline. If this task builds the pinned image into an initially empty
   daemon, remove only that recorded image after reading the receipt. Never
   prune or delete an unowned resource.
3. Preserve a failed check and its bounded diagnostic. Do not claim parity if
   the image, codeload route, archive, ordinary controls, causal split, or
   cleanup cannot be verified.

A pass requires a repeatable command, exact source and image pins, redacted
two-arm traces, a semantic comparison, independent review, and exact cleanup.
It does not authorize a provider call or a model-driven application run.
