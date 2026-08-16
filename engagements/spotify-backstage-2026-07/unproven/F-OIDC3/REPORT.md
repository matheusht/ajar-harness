# Internal advisory — F-OIDC3 revision 1

Claim state: **supported**

## Included claims

### claim-impact

Full Backstage user token for the victim identity with no client authentication; stolen refresh token renewable for up to a year.

Claim status: demonstrated
Evidence: attempt-F-OIDC3-primary-225232, artifact-registration-sha256:39dce262a, artifact-registration-sha256:6f74cd793, artifact-registration-sha256:a380ba755, artifact-registration-sha256:6ccf19eba
Controls: attempt-F-OIDC3-neg-225238
Replays: attempt-F-OIDC3-replay-225244

### claim-mechanism

exchangeCodeForToken takes no client_id and never authenticates the DCR client; DCR registration sets requiresPkce:false; the server advertises client_secret_basic/post it never enforces.

Claim status: mechanism_or_reachability
Evidence: attempt-F-OIDC3-primary-225232, artifact-registration-sha256:39dce262a, artifact-registration-sha256:6f74cd793, artifact-registration-sha256:a380ba755, artifact-registration-sha256:6ccf19eba
Controls: attempt-F-OIDC3-neg-225238
Replays: attempt-F-OIDC3-replay-225244

### claim-reach

Any attacker holding a valid authorization code (or the victim's refresh token) redeems it with zero client credentials; refresh client auth is optional, renewable up to 1 year.

Claim status: mechanism_or_reachability
Evidence: attempt-F-OIDC3-primary-225232, artifact-registration-sha256:39dce262a, artifact-registration-sha256:6f74cd793, artifact-registration-sha256:a380ba755, artifact-registration-sha256:6ccf19eba
Controls: attempt-F-OIDC3-neg-225238
Replays: attempt-F-OIDC3-replay-225244

## Intentionally omitted claims

- None.

## Structured claim-to-proof matrix

# Claim-to-proof matrix — F-OIDC3 revision 1

- Claim state: `supported`
- Claim tuple: `sha256:8d26f53c8cdc4328befdb23527869d9d663d5da7a1ab7e5bf895c160eda3669f`
- Renderer: `decision-0005-proof-v1`

| Claim | Status | Statement | Primary attempts | Artifacts | Controls | Replays |
| --- | --- | --- | --- | --- | --- | --- |
| claim-mechanism | mechanism_or_reachability | exchangeCodeForToken takes no client_id and never authenticates the DCR client; DCR registration sets requiresPkce:false; the server advertises client_secret_basic/post it never enforces. | attempt-F-OIDC3-primary-225232 | artifact-registration-sha256:39dce262a, artifact-registration-sha256:6f74cd793, artifact-registration-sha256:a380ba755, artifact-registration-sha256:6ccf19eba | attempt-F-OIDC3-neg-225238 | attempt-F-OIDC3-replay-225244 |
| claim-reach | mechanism_or_reachability | Any attacker holding a valid authorization code (or the victim's refresh token) redeems it with zero client credentials; refresh client auth is optional, renewable up to 1 year. | attempt-F-OIDC3-primary-225232 | artifact-registration-sha256:39dce262a, artifact-registration-sha256:6f74cd793, artifact-registration-sha256:a380ba755, artifact-registration-sha256:6ccf19eba | attempt-F-OIDC3-neg-225238 | attempt-F-OIDC3-replay-225244 |
| claim-impact | demonstrated | Full Backstage user token for the victim identity with no client authentication; stolen refresh token renewable for up to a year. | attempt-F-OIDC3-primary-225232 | artifact-registration-sha256:39dce262a, artifact-registration-sha256:6f74cd793, artifact-registration-sha256:a380ba755, artifact-registration-sha256:6ccf19eba | attempt-F-OIDC3-neg-225238 | attempt-F-OIDC3-replay-225244 |

## Uncertainty

- deployment prevalence / config-gating may vary
