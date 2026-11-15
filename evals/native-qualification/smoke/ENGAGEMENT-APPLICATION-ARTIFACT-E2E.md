# Application owner artifact lifecycle check

This is a failure-first local check over the existing application reset fixture and the shared
`lab_artifacts` journal. It uses a signed disposable application identity with no accounts, a
simulated environment, and the real controller/application-owner flow. No provider, Docker daemon,
remote host, or external target is required. The check must keep the source artifact class and
policy unchanged.

## Failure matrix

| Case | Required observation |
| --- | --- |
| Source or binary resource with one exact signed `artifact_create` effect | Existing `owned-lab-state-v1` effect selection remains available; the app check does not re-run the separate source artifact lifecycle. |
| Signed reference declares `artifact_effect_id`, but the matching journal intent is absent | Refuse before application/container allocation or app process launch. An omitted optional artifact reference retains the existing reset path. |
| Reference points to an absent/wrong effect, a multi-app effect, a source/binary-only effect, wrong class, accounts, or missing cleanup obligation | Refuse closed; no application process starts and no artifact receipt is written. |
| First valid capture | Journal intent before environment allocation; validate host-observed ready readback before signed application launch; then capture through the normal owned application reset. |
| Readiness missing, changed, or bound to another application/effect/environment | Refuse before launching the app or admitting its request; retain cleanup uncertainty if allocation already happened. |
| Application cleanup unresolved | Lab artifact remains pending, the shared resource stays held, and dispatch cannot settle as clean. |
| Normal cleanup and resumed recovery | Exact environment/volume removal is read back, artifact reaches clean, and reconstruction neither reallocates nor relaunches a completed effect. |

The fixture only attests to a synthetic local application with one disposable application identity.
It does not activate `artifact_policy` or broaden any engagement scope. Preserve the existing reset
effect and signed baseline checks separately from the artifact creation grant.

## Local result

Command: `python3 evals/native-qualification/smoke/check_application_artifact_e2e.py --output evals/native-qualification/team-evidence/application-artifact-20261115/result.json`

All six scenario groups passed against the real journal/controller and simulated Docker volume peer.
No Docker daemon, provider, or external target was contacted. The run is mechanics evidence only;
research acceptance remains `not_run`. The source/binary check covers artifact effect selection only.
See [saved results](../team-evidence/application-artifact-20261115/result.json).
