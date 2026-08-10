# Internal advisory — F-F3 revision 1

Claim state: **supported**

## Included claims

### claim-impact

Multiple valid tokens from one authorization code / one session (amplification).

Claim status: demonstrated
Evidence: attempt-F-F3-primary-225505, artifact-registration-sha256:3465580da, artifact-registration-sha256:b8da26917, artifact-registration-sha256:85644a7be
Controls: attempt-F-F3-neg-225511
Replays: attempt-F-F3-replay-225518

### claim-mechanism

Code redemption is read-check-then-write with no WHERE used=false and no affected-rows check; concurrent redemptions of the same code mint multiple tokens.

Claim status: mechanism_or_reachability
Evidence: attempt-F-F3-primary-225505, artifact-registration-sha256:3465580da, artifact-registration-sha256:b8da26917, artifact-registration-sha256:85644a7be
Controls: attempt-F-F3-neg-225511
Replays: attempt-F-F3-replay-225518

### claim-reach

Concurrent POST /v1/token with the same code; observed 8/24 on MySQL; also approve-no-CAS mints multiple codes per session.

Claim status: mechanism_or_reachability
Evidence: attempt-F-F3-primary-225505, artifact-registration-sha256:3465580da, artifact-registration-sha256:b8da26917, artifact-registration-sha256:85644a7be
Controls: attempt-F-F3-neg-225511
Replays: attempt-F-F3-replay-225518

## Intentionally omitted claims

- None.

## Structured claim-to-proof matrix

# Claim-to-proof matrix — F-F3 revision 1

- Claim state: `supported`
- Claim tuple: `sha256:751a79e9c94cd4085a7e6f34f4fe66aad6991b899248d5d8be3f850f3a849903`
- Renderer: `decision-0005-proof-v1`

| Claim | Status | Statement | Primary attempts | Artifacts | Controls | Replays |
| --- | --- | --- | --- | --- | --- | --- |
| claim-mechanism | mechanism_or_reachability | Code redemption is read-check-then-write with no WHERE used=false and no affected-rows check; concurrent redemptions of the same code mint multiple tokens. | attempt-F-F3-primary-225505 | artifact-registration-sha256:3465580da, artifact-registration-sha256:b8da26917, artifact-registration-sha256:85644a7be | attempt-F-F3-neg-225511 | attempt-F-F3-replay-225518 |
| claim-reach | mechanism_or_reachability | Concurrent POST /v1/token with the same code; observed 8/24 on MySQL; also approve-no-CAS mints multiple codes per session. | attempt-F-F3-primary-225505 | artifact-registration-sha256:3465580da, artifact-registration-sha256:b8da26917, artifact-registration-sha256:85644a7be | attempt-F-F3-neg-225511 | attempt-F-F3-replay-225518 |
| claim-impact | demonstrated | Multiple valid tokens from one authorization code / one session (amplification). | attempt-F-F3-primary-225505 | artifact-registration-sha256:3465580da, artifact-registration-sha256:b8da26917, artifact-registration-sha256:85644a7be | attempt-F-F3-neg-225511 | attempt-F-F3-replay-225518 |

## Uncertainty

- deployment prevalence / config-gating may vary
