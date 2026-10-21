# Managed stop-owner source closure — checks before integration

The managed native runner imports an archived `native_run.py`, which starts
`_native_stop_owner.py` from that file's directory. The managed archive must
therefore contain and pin this new helper as well as the changed CONNECT,
native, producer, and Docker-runtime sources. Otherwise the owned Docker E2E
can pass while the managed run fails at owner startup or loads unrelated bytes.

Before implementation, the failure checks are:

1. A current source manifest without the helper, or one whose helper is absent
   from the staged tree, must fail before output creation or Docker invocation.
2. A modified staged helper must fail the reviewed source pin before output or
   Docker. A helper modified *during archive copying* must fail the archived
   control pin before Docker.
3. The successful archived path must report the helper's origin inside the
   private source tree, alongside CONNECT/native/producer/runtime origins.
4. `--live-free` remains denied before output or Docker, with no provider call.

Run `python3 evals/native-qualification/smoke/check_v2_cloud_owned_source.py
--current-manifest` for the no-Docker source check. This does not qualify a
managed native run or change the live denial.

Observed on 2026-10-21: the current-manifest command passed. It rejected a
missing or mutated staged helper before output and Docker, rejected a helper
corrupted during archive copying before Docker, reported the helper origin in
the archived tree, and preserved the live-free pre-output denial. The existing
live-preparation checker also completed its 25 offline checks via
`check_v2_live_preparation.py --unobserved-core`; its receipt explicitly says
`observation_complete: false`, so this is not a network-syscall observation.
