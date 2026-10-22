# T02 integrated source admission checks

This addendum governs the PR #185 integrated entrypoint. The PR #180 same-image
controller and its historical checks remain byte-identical evidence. This
addendum changes only admission for a later owned offline rehearsal; it does not
authorize Docker, a provider, or a target run today.

Before the frozen controller can execute, the entrypoint must admit the frozen
controller hash and contract, the clean current source manifest including its
own bytes and this addendum, then run these no-provider negative checks from the
repository root with bytecode writes disabled:

```sh
python3 evals/native-qualification/smoke/check_v2_cloud_manifest_layout.py
python3 evals/native-qualification/smoke/check_v2_cloud_owned_source.py --current-manifest
```

The second check stages the exact current manifest and proves that the live
route and changed owned inputs fail before output or real Docker. A nonzero
exit, timeout, or unavailable check blocks the controller. Do not retain the
checks' raw output in a public receipt.

The focused failure checks must establish:

| Failure | Required result |
| --- | --- |
| Historical controller bytes or expected contract change | No controller or Docker command; a fixed-code `blocked` admission receipt at the supplied fresh output path. |
| Current source manifest is stale, omits or mispins the integrated entrypoint, test, or this addendum, or checkout is dirty | No controller or Docker command; a fixed-code `blocked` admission receipt. |
| Either no-provider preflight fails | No controller or Docker command; a fixed-code `blocked` admission receipt. |
| Both checks pass | Delegate to the frozen controller, which repeats source admission and enforces its own parity, build, run, receipt, and cleanup gates. |

The admission receipt records no raw command output, source path, credentials,
proxy values, or trust material. A previously existing output path must not be
overwritten. The caller still supplies `--source-commit`; the controller checks
that it equals current HEAD, but this is not independent reviewer provenance.
Before a new Docker rehearsal, an operator must separately pin the reviewed
source SHA outside this commit and retain the exact-SHA preflight and run
receipts. No result from this addendum qualifies live or native behavior.
