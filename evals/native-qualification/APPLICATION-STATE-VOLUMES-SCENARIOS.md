# Signed application state volume lifecycle scenarios

Failure-first contract for the optional `owned-application-state-v2` profile and
its disposable local Docker named volumes. The profile extends v1 with an exact
`state_volumes` list. Each entry contains only `path` and `bytes`; paths are
direct `/state/<id>` children, with at most eight entries. IDs are unique,
bytes are integers of at least 4096 and a multiple of 4096, and their total is
strictly less than the signed environment's `workspace_bytes` limit. The signed
profile and its digest bind the declarations. Existing v1 profile bytes and
semantics stay unchanged.

Volumes use Docker's local driver and bounded `tmpfs` options. They are created
empty, before the target starts, with unique names and exact engagement nonce,
environment profile digest, path, and byte-count labels. Docker's automatic
copy of image seed files into an empty named volume can allocate memory outside
the application's container cgroup; each target mount must set `NoCopy=true`.
The signed application command initializes the baseline from its pinned image
inside the memory-limited container. Only the matching signed paths are mounted.
Existing volumes, external databases, and unowned writers are outside this
contract.

## Required failure-first cases

| Case | Workflow and expected result |
| --- | --- |
| V1 compatibility | Load a valid signed v1 application profile and perform its existing reset workflow unchanged; its receipt and cleanup shape remain v2-compatible. |
| V2 success | Load a signed v2 profile with valid declarations. Observe one create intent/result per declared volume before target allocation; the target mount configuration sets `NoCopy=true`, labels, driver and bounded options match exactly, and daemon-side volume creation adds no seed files. The signed application initializes its baseline after start. The protected receipt lists each exact `{name,path,bytes,created_at}` identity. |
| Invalid declarations | Reject missing/extra entry keys, non-list, empty or >8 entries, duplicate IDs/paths, non-direct paths, relative/traversal paths, malformed IDs, bool/float/string/negative/small/non-page-aligned sizes, and total bytes equal to or greater than workspace limit. No volume or target is created. |
| Invalid pin or authority | Reject a changed profile digest, unknown method/version, unsupported reset effect or missing signed reset permission before allocation. |
| Fresh generation | Mutate the first generation's state, clean it, then recreate the same baseline. The second volume name and target nonce differ, the baseline comes from the pinned image, and prior state is absent. |
| Exact ownership | Reject a readback with another engagement/profile/path/size label, wrong driver/options, `NoCopy` absent or false, altered size/path, extra mount, reused name or changed `created_at`. Never mount, remove or relabel a pre-existing volume. |
| Interrupted create | After create intent but before a settled result, leave the resource unknown and held. Recovery may remove it only after exact name/label/options readback proves ownership; no blind create retry. Missing/ambiguous readback stays held. |
| Interrupted reset | If target setup or readiness fails after volume creation, do not return a clean-start receipt. Keep the resource held until exact container and volume cleanup is verified. |
| Cleanup uncertainty | Removal failure, lost connection, stale identity, or volume still present prevents `status: clean` and resource release. Recovery removes only the exact recorded owner volumes, then verifies absence. |
| Revocation | Expired/revoked authority prevents create, mount, connect, and cleanup mutation where authorization is required; uncertainty remains held until authorized readback/cleanup can settle it. |
| Unrelated preservation | Starting and finishing volume inventories show every pre-existing/unrelated volume unchanged; only names under this engagement's exact owner labels are removed. |
| Independent replay | A second signed capture uses a distinct target and fresh volume generation, reaches the same baseline, and produces comparable state evidence without reusing first-generation state. |

## Expected interfaces and evidence

- `ApplicationOwner.reset(baseline_id)` remains the capture entry. It consumes the
  signed v2 descriptors; workers do not choose volume names, options, mounts, or
  cleanup commands.
- `Environment` owns the fixed `create_state_volume` and
  `remove_state_volume` operations. Every mutation has an intent before dispatch
  and a result/readback bound to the immutable environment receipt.
- The new `research-environment-receipt-v3` adds
  `state_volumes: [{name, path, bytes, created_at}]`; `created_at` is null until
  observed and then pins identity against replacement. Existing v2 environment
  receipts keep their exact schema. Target readback verifies
  the actual volume labels, driver/options, `NoCopy=true`, and mounts rather than
  trusting requested config.
- Cleanup reports `clean` only after the exact target container is absent and each
  exact volume is absent. Journal settlement and hold release require that proof.
- The signed workflow check uses a fake Docker owner and real contract/controller/
  boundary code. It uses no Docker daemon, provider, public network, or research
  target. Optional physical Docker qualification remains a separate explicitly
  invoked workflow.

## Repeat

```sh
python3 evals/native-qualification/smoke/check_application_state_volumes_e2e.py \
  --output /tmp/application-state-volumes-e2e.json
```

Expected: all contract, lifecycle, interruption, cleanup, recovery, and replay
checks pass; the JSON result identifies the fake-Docker classification and records
all unverified physical/provider/target conditions.
