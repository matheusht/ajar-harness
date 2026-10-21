# Owned T02 capture-review bridge check

`result.json` is the saved result of the no-Docker source check on 21 October 2026. It uses the checked-in PHP fixture, builds a synthetic evaluator-sealed capture, publishes it to the fixed reviewer packet, then emits a separate final receipt after supplied stop and cleanup projections. The check also exercises changed and malformed captures, mismatched source/run/session/claim bindings, host replay classification, packet drift, and the ordinary packet path.

From the repository root, with Python 3 and no provider credentials, run:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 evals/native-qualification/smoke/check_v2_capture_review_bridge.py --output /absolute/absent/private-output
```

Expect `PASS` and `result.json` in the new directory. The saved result names its source hashes and reports zero provider and target calls. Stop and cleanup projections in this check are synthetic. Its final receipt is limited to `capture_lifecycle_only` with review `not_observed`. This check proves only the local file-to-packet-to-receipt contract; it does not establish protected producer origin, a managed native capture or stop, a completed independent review, or live provider qualification. The packet keeps `original_observation.status` as `unavailable` even when an unqualified capture candidate is supplied.
