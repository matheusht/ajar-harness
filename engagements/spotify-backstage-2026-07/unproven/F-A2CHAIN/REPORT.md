# Internal advisory — F-A2CHAIN revision 1

Claim state: **supported**

## Included claims

### claim-impact

Persistent catalog integrity compromise: forged entities/groups survive legitimate resync (silent rejection), defeating operator detection.

Claim status: demonstrated
Evidence: attempt-F-A2CHAIN-primary-224749, artifact-registration-sha256:226bb7d2d, artifact-registration-sha256:b03cbe0c6, artifact-registration-sha256:f0d926634, artifact-registration-sha256:ec99d1b19
Controls: attempt-F-A2CHAIN-neg-224754
Replays: attempt-F-A2CHAIN-replay-224758

### claim-mechanism

A2 unrestricted service principal deletes an entity (freeing the entityRef), re-registers a forged version under a new location_key; the legitimate source's resync is silently REJECTED on location_key conflict (DefaultProviderDatabase.replaceUnprocessedEntities), persisting the forged entity.

Claim status: mechanism_or_reachability
Evidence: attempt-F-A2CHAIN-primary-224749, artifact-registration-sha256:226bb7d2d, artifact-registration-sha256:b03cbe0c6, artifact-registration-sha256:f0d926634, artifact-registration-sha256:ec99d1b19
Controls: attempt-F-A2CHAIN-neg-224754
Replays: attempt-F-A2CHAIN-replay-224758

### claim-reach

Reachable from the A2 link: a least-privilege external token → catalog delete + re-register on any entity/Group ref.

Claim status: mechanism_or_reachability
Evidence: attempt-F-A2CHAIN-primary-224749, artifact-registration-sha256:226bb7d2d, artifact-registration-sha256:b03cbe0c6, artifact-registration-sha256:f0d926634, artifact-registration-sha256:ec99d1b19
Controls: attempt-F-A2CHAIN-neg-224754
Replays: attempt-F-A2CHAIN-replay-224758

## Intentionally omitted claims

- None.

## Structured claim-to-proof matrix

# Claim-to-proof matrix — F-A2CHAIN revision 1

- Claim state: `supported`
- Claim tuple: `sha256:c70705e3f17f64ef25e5970398d119bc7de686b499a59a4dea0c40103edf65a6`
- Renderer: `decision-0005-proof-v1`

| Claim | Status | Statement | Primary attempts | Artifacts | Controls | Replays |
| --- | --- | --- | --- | --- | --- | --- |
| claim-mechanism | mechanism_or_reachability | A2 unrestricted service principal deletes an entity (freeing the entityRef), re-registers a forged version under a new location_key; the legitimate source's resync is silently REJECTED on location_key conflict (DefaultProviderDatabase.replaceUnprocessedEntities), persisting the forged entity. | attempt-F-A2CHAIN-primary-224749 | artifact-registration-sha256:226bb7d2d, artifact-registration-sha256:b03cbe0c6, artifact-registration-sha256:f0d926634, artifact-registration-sha256:ec99d1b19 | attempt-F-A2CHAIN-neg-224754 | attempt-F-A2CHAIN-replay-224758 |
| claim-reach | mechanism_or_reachability | Reachable from the A2 link: a least-privilege external token → catalog delete + re-register on any entity/Group ref. | attempt-F-A2CHAIN-primary-224749 | artifact-registration-sha256:226bb7d2d, artifact-registration-sha256:b03cbe0c6, artifact-registration-sha256:f0d926634, artifact-registration-sha256:ec99d1b19 | attempt-F-A2CHAIN-neg-224754 | attempt-F-A2CHAIN-replay-224758 |
| claim-impact | demonstrated | Persistent catalog integrity compromise: forged entities/groups survive legitimate resync (silent rejection), defeating operator detection. | attempt-F-A2CHAIN-primary-224749 | artifact-registration-sha256:226bb7d2d, artifact-registration-sha256:b03cbe0c6, artifact-registration-sha256:f0d926634, artifact-registration-sha256:ec99d1b19 | attempt-F-A2CHAIN-neg-224754 | attempt-F-A2CHAIN-replay-224758 |

## Uncertainty

- deployment prevalence / config-gating may vary
