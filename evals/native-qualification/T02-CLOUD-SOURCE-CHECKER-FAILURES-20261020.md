# T02 cloud source-checker failure conditions — 20 October 2026

Before the checker stages inputs or invokes its fake Docker, select the manifest
at the extracted ZIP root (`SOURCE-MANIFEST.json`) when present. In the local
repository, fall back to `evals/native-qualification/t02-cloud-transfer-20261020/SOURCE-MANIFEST.json`.
If both exist, the ZIP-root manifest wins; an invalid present root manifest
must fail rather than silently fall back.

For every manifest-listed source file, require a safe relative path, regular
in-root file, exact byte length and SHA-256. Validate all listed files before
creating any staged copy. A changed byte, missing file, duplicate path, or
malformed manifest fails without staging; an executable relay retains its mode
after a valid copy. Copy from the validated bytes, not a second mutable read.

Exercise both layouts in disposable directories with a fake Docker executable:
a valid local sidecar and a valid ZIP-root manifest each stage exact bytes; a
present ZIP-root manifest overrides a conflicting sidecar. Mutate a listed
source file without changing the manifest and require rejection before any
staged file or fake Docker call. These are source-transfer checks, not cloud
Docker, policy, native model or provider qualification. Rebuild the real
transfer bundle only after the checker and its checks are reviewed.
