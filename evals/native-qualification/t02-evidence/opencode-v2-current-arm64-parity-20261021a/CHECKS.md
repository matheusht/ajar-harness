# Current Dockerfile, local arm64 Kanboard parity

Freeze the current Dockerfile, local image ID, T01 observer source, ordinary
brief, T01 result and both Kanboard archive hashes before starting. Fail if
any pin differs, PHP 8.4.26 lacks GD/SQLite, or OpenCode V2 is absent.

Use the existing observer's source preparation and two application arms. Both
must start from clean pinned releases under the exact image. The normal admin
and Alice reads must work; Bob's unrelated private-project read must return
403 in both arms; Bob's created swimlane read must return the same metadata on
the vulnerable arm and 403 on the fixed arm. Compare these facts to T01 without
comparing PHP version or incidental container IDs.

Fail if either owned app container, loopback port, disposable run directory or
database remains. Saved traces and receipts must not contain credentials,
authorization values, tokens or local home paths. Keep the raw archives and
extracted copies private. This check uses no model/provider and cannot qualify
the different cloud amd64 image or researcher-originated observation.
