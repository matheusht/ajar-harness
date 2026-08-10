# Internal advisory — F-A2LINK revision 1

Claim state: **supported**

## Included claims

### claim-impact

Privilege escalation: a token scoped to one plugin reaches arbitrary catalog/scaffolder operations as an unrestricted service principal.

Claim status: demonstrated
Evidence: attempt-F-A2LINK-primary-224659, artifact-registration-sha256:942dd517a
Controls: attempt-F-A2LINK-neg-224703
Replays: attempt-F-A2LINK-replay-224707

### claim-mechanism

DefaultAuthService.getPluginRequestToken case 'service' re-mints a plugin token with only pluginId/targetPluginId, dropping the incoming principal's accessRestrictions; ServerPermissionClient.#servicePrincipalDecision treats a service principal with no restrictions as unconditional ALLOW before the operator policy.

Claim status: mechanism_or_reachability
Evidence: attempt-F-A2LINK-primary-224659, artifact-registration-sha256:942dd517a
Controls: attempt-F-A2LINK-neg-224703
Replays: attempt-F-A2LINK-replay-224707

### claim-reach

Any least-privilege external-access token, forwarded plugin→plugin, becomes unrestricted; downstream authorize()/authorizeConditional() short-circuit to ALLOW.

Claim status: mechanism_or_reachability
Evidence: attempt-F-A2LINK-primary-224659, artifact-registration-sha256:942dd517a
Controls: attempt-F-A2LINK-neg-224703
Replays: attempt-F-A2LINK-replay-224707

## Intentionally omitted claims

- None.

## Structured claim-to-proof matrix

# Claim-to-proof matrix — F-A2LINK revision 1

- Claim state: `supported`
- Claim tuple: `sha256:8a60406049284891e83226930e59ce1ec146928a35e9336f7394d2b500639e12`
- Renderer: `decision-0005-proof-v1`

| Claim | Status | Statement | Primary attempts | Artifacts | Controls | Replays |
| --- | --- | --- | --- | --- | --- | --- |
| claim-mechanism | mechanism_or_reachability | DefaultAuthService.getPluginRequestToken case 'service' re-mints a plugin token with only pluginId/targetPluginId, dropping the incoming principal's accessRestrictions; ServerPermissionClient.#servicePrincipalDecision treats a service principal with no restrictions as unconditional ALLOW before the operator policy. | attempt-F-A2LINK-primary-224659 | artifact-registration-sha256:942dd517a | attempt-F-A2LINK-neg-224703 | attempt-F-A2LINK-replay-224707 |
| claim-reach | mechanism_or_reachability | Any least-privilege external-access token, forwarded plugin→plugin, becomes unrestricted; downstream authorize()/authorizeConditional() short-circuit to ALLOW. | attempt-F-A2LINK-primary-224659 | artifact-registration-sha256:942dd517a | attempt-F-A2LINK-neg-224703 | attempt-F-A2LINK-replay-224707 |
| claim-impact | demonstrated | Privilege escalation: a token scoped to one plugin reaches arbitrary catalog/scaffolder operations as an unrestricted service principal. | attempt-F-A2LINK-primary-224659 | artifact-registration-sha256:942dd517a | attempt-F-A2LINK-neg-224703 | attempt-F-A2LINK-replay-224707 |

## Uncertainty

- deployment prevalence / config-gating may vary
