# Renewal bound regression

The hosted OMP public fixture failed when elapsed time between grant renewal and
owner renewal made a previously computed duration exceed the current grant. The
[before receipt](before.json) records failure-first checks. The [after receipt](after.json)
records the same controlled-clock scenario passing: model and tool owners each use
the currently admitted bound, while explicit over-grant, revoked and expired
requests remain refused. It exercises actual boundary and environment code with
owned mock owners; it does not prove a hosted native workflow.

The [regression summary](regression-summary.json) records affected local scenarios
and their source hashes. From the repository root with the pinned CI requirements:

```sh
python3 evals/native-qualification/smoke/check_native_renewal_bounds_e2e.py --output /tmp/renewal-bounds.json
```

Expected: four checks pass. The hosted workflow also runs this scenario; full
native requalification is recorded separately.
