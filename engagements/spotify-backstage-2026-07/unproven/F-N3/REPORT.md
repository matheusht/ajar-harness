# Internal advisory — F-N3 revision 1

Claim state: **supported**

## Included claims

### claim-impact

Victim-identity token issuance to the attacker (with the victim's subsequent approve); consent-flow DoS via reject.

Claim status: demonstrated
Evidence: attempt-F-N3-primary-225347, artifact-registration-sha256:cf15a88e1, artifact-registration-sha256:8fc120c5e
Controls: attempt-F-N3-neg-225353
Replays: attempt-F-N3-replay-225400

### claim-mechanism

POST /v1/sessions/:id/approve authenticates the caller but never checks the caller initiated the session; updateAuthorizationSession has no CAS, so concurrent approves mint multiple codes.

Claim status: mechanism_or_reachability
Evidence: attempt-F-N3-primary-225347, artifact-registration-sha256:cf15a88e1, artifact-registration-sha256:8fc120c5e
Controls: attempt-F-N3-neg-225353
Replays: attempt-F-N3-replay-225400

### claim-reach

Any authenticated user who learns a pending session id (attacker's own session id is sufficient) binds their identity; approve-race binds a victim identity to an attacker-held code.

Claim status: mechanism_or_reachability
Evidence: attempt-F-N3-primary-225347, artifact-registration-sha256:cf15a88e1, artifact-registration-sha256:8fc120c5e
Controls: attempt-F-N3-neg-225353
Replays: attempt-F-N3-replay-225400

## Intentionally omitted claims

- None.

## Structured claim-to-proof matrix

# Claim-to-proof matrix — F-N3 revision 1

- Claim state: `supported`
- Claim tuple: `sha256:c3d7a9cf2b7ea911ca2fb0dabc0de2a30d7b5b4e8fbf539491de02f1c2b8878b`
- Renderer: `decision-0005-proof-v1`

| Claim | Status | Statement | Primary attempts | Artifacts | Controls | Replays |
| --- | --- | --- | --- | --- | --- | --- |
| claim-mechanism | mechanism_or_reachability | POST /v1/sessions/:id/approve authenticates the caller but never checks the caller initiated the session; updateAuthorizationSession has no CAS, so concurrent approves mint multiple codes. | attempt-F-N3-primary-225347 | artifact-registration-sha256:cf15a88e1, artifact-registration-sha256:8fc120c5e | attempt-F-N3-neg-225353 | attempt-F-N3-replay-225400 |
| claim-reach | mechanism_or_reachability | Any authenticated user who learns a pending session id (attacker's own session id is sufficient) binds their identity; approve-race binds a victim identity to an attacker-held code. | attempt-F-N3-primary-225347 | artifact-registration-sha256:cf15a88e1, artifact-registration-sha256:8fc120c5e | attempt-F-N3-neg-225353 | attempt-F-N3-replay-225400 |
| claim-impact | demonstrated | Victim-identity token issuance to the attacker (with the victim's subsequent approve); consent-flow DoS via reject. | attempt-F-N3-primary-225347 | artifact-registration-sha256:cf15a88e1, artifact-registration-sha256:8fc120c5e | attempt-F-N3-neg-225353 | attempt-F-N3-replay-225400 |

## Uncertainty

- deployment prevalence / config-gating may vary
