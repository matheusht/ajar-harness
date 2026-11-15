# Initial-scope artifact autonomy check

This failure-first check covers an explicitly signed initial authority policy and the existing
owned-lab artifact journal. It does not change pricing, provider execution, external-target access,
or fresh-target qualification. A policy absence must preserve the historical confirmation model.

## Failure matrix

| Case | Required observation |
| --- | --- |
| Signed scope has `authority_policy: initial-scope-v1` and an exact `owned-lab-state-v2` effect | One initial scope signature authorizes only the listed artifact class/effect/resource/environment; intent, ready, and clean receipts use the existing journal. |
| Initial-scope policy is absent | Historical policy stays `legacy-confirmation`; v2 automatic artifact admission is unavailable. |
| Unknown policy value, mismatched access/environment/class, or missing cleanup obligation | Contract/controller refuses; no artifact allocation or ready receipt is recorded. |
| Supported source, binary, application, and combined tool resources | The v2 artifact selector binds only resources present in the signed effect; application-state ownership remains separate. |
| Status and export after a clean artifact run | Both report the selected policy. There is no second signature, manual confirmation event, or hidden authority expansion. |

Run only a disposable signed engineering fixture. The fixture's key signs that fixture scope once; it
does not simulate an external authorization service or activate a real engagement. The report must
label the run as simulation and leave research acceptance `not_run`.
