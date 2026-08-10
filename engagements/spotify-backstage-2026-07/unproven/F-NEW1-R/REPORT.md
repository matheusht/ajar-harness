# Internal advisory — F-NEW1-R revision 1

Claim state: **supported**

## Included claims

### claim-impact

Exfiltration of org secrets and the initiator's live Backstage token (account/org takeover potential); whole-secrets-map dump via ${{ secrets | dump }}.

Claim status: demonstrated
Evidence: attempt-F-NEW1-primary-222050, artifact-registration-sha256:e7e02cd03
Controls: attempt-F-NEW1-neg-222106
Replays: attempt-F-NEW1-replay2-223055

### claim-mechanism

NunjucksWorkflowRunner.markFailed writes String(err.stack) directly to the task event log, bypassing the redacting taskLogger; StorageTaskBroker.emitLog is a raw passthrough to the cross-user-readable task_events store.

Claim status: mechanism_or_reachability
Evidence: attempt-F-NEW1-primary-222050, artifact-registration-sha256:e7e02cd03
Controls: attempt-F-NEW1-neg-222106
Replays: attempt-F-NEW1-replay2-223055

### claim-reach

Any authenticated user can register a template whose step throws; the failing step's rendered secrets (defaultEnvironment.secrets incl. GITHUB_TOKEN/cloud keys and secrets.backstageToken = the initiator's live token) land in the task event log, readable cross-user under the default allow-all policy.

Claim status: mechanism_or_reachability
Evidence: attempt-F-NEW1-primary-222050, artifact-registration-sha256:e7e02cd03
Controls: attempt-F-NEW1-neg-222106
Replays: attempt-F-NEW1-replay2-223055

## Intentionally omitted claims

- None.

## Structured claim-to-proof matrix

# Claim-to-proof matrix — F-NEW1-R revision 1

- Claim state: `supported`
- Claim tuple: `sha256:5070cb51645cfdd6b334bd037dccfef6e8c1f06ca2a09a3fb7c000a79e1f294c`
- Renderer: `decision-0005-proof-v1`

| Claim | Status | Statement | Primary attempts | Artifacts | Controls | Replays |
| --- | --- | --- | --- | --- | --- | --- |
| claim-mechanism | mechanism_or_reachability | NunjucksWorkflowRunner.markFailed writes String(err.stack) directly to the task event log, bypassing the redacting taskLogger; StorageTaskBroker.emitLog is a raw passthrough to the cross-user-readable task_events store. | attempt-F-NEW1-primary-222050 | artifact-registration-sha256:e7e02cd03 | attempt-F-NEW1-neg-222106 | attempt-F-NEW1-replay2-223055 |
| claim-reach | mechanism_or_reachability | Any authenticated user can register a template whose step throws; the failing step's rendered secrets (defaultEnvironment.secrets incl. GITHUB_TOKEN/cloud keys and secrets.backstageToken = the initiator's live token) land in the task event log, readable cross-user under the default allow-all policy. | attempt-F-NEW1-primary-222050 | artifact-registration-sha256:e7e02cd03 | attempt-F-NEW1-neg-222106 | attempt-F-NEW1-replay2-223055 |
| claim-impact | demonstrated | Exfiltration of org secrets and the initiator's live Backstage token (account/org takeover potential); whole-secrets-map dump via ${{ secrets \| dump }}. | attempt-F-NEW1-primary-222050 | artifact-registration-sha256:e7e02cd03 | attempt-F-NEW1-neg-222106 | attempt-F-NEW1-replay2-223055 |

## Uncertainty

- deployment prevalence / config-gating may vary
