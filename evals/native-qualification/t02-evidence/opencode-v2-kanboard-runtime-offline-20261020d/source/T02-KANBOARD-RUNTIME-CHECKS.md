# T02 Kanboard runtime prerequisite — checks frozen before offline application run

19 October 2026. This checks only whether the pinned #157 application can be
prepared, started, and observed from the existing V2 researcher boundary. It
does not clear the aggregate inference allowance gate or authorize a model run.

| Failure mode | Required offline check |
| --- | --- |
| Wrong or altered application source | Use only the pinned vulnerable archive with its recorded SHA-256. Verify the extracted file set and contents against that archive before copying. Keep the fixed archive, observer result, request traces, checks and patch outside the researcher mount. |
| Missing researcher runtime | Inspect the exact official V2 image and run the ordinary `php` and required extension checks inside a disposable, no-network researcher container. If absent, derive the smallest pinned V2 image with PHP CLI and the extensions the ordinary app path actually needs; pin the resulting image ID and recheck inside it. A host PHP or a separate prestarted PHP service does not satisfy this check. |
| Incomplete researcher workspace | Mount only an owned disposable copy of the vulnerable release app and isolated native config/data. Its pinned archive already includes `vendor/autoload.php`; check that file and lint representative PHP entrypoints from inside the researcher image. Confirm the app's writable data path remains inside that copy, with no host home, Docker socket, observer directory, credential or answer mount. |
| Synthetic output mistaken for application behavior | If the runtime is available, start the actual app from the researcher container. Capture readiness and an ordinary synthetic workflow with a separate host-owned client container sharing only the app's network namespace, with no source mount or external network. Save its redacted request/response summary and application state. An HTTP 200 alone is insufficient. |
| Workspace survives only while the first container lives | Stop and remove the first app and client containers, retain only the owned workspace, start replacements with the same image/config and verify the created project and private-project denial through the new app process. Then remove all owned containers and the workspace. |
| Native session is separate from application workspace | With the pinned read-only OpenCode request-observer plugin mounted, inspect the actual V2 version, config and empty session list inside the first researcher image. Follow native `session.list` cursors to exhaustion and reject repeats or duplicates. Create one native session through `opencode api --standalone` without inference and record its ID and storage path. After replacing the app/researcher container, the same ID and zero-cost metadata must be visible through native `session.list`/`session.get` while the host-owned client still sees the saved application project and denial. After both replacement containers stop, a host read of the native SQLite store must return `quick_check=ok` and the same session ID. Do not call `opencode run`. |
| Boundary or cleanup leak | Pin image/source/config hashes, record owned container and port IDs, and verify stop, closed port and removal of the disposable app database/workspace. Do not alter the pinned archive or existing #157 evidence. |

**Stop condition:** if PHP packaging or dependencies require a nontrivial
runtime change, record the exact failure and stop. Do not substitute a
host-started Kanboard app or build a new orchestration service. Keep all
provider/model calls disabled and the aggregate inference gate open.
