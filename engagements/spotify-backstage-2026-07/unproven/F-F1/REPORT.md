# Internal advisory — F-F1 revision 1

Claim state: **supported**

## Included claims

### claim-impact

Private-repo content disclosure with the integration credential, provenance forgery, and group-membership forgery that can flip a real permission decision.

Claim status: demonstrated
Evidence: attempt-F-F1-primary-225049, artifact-registration-sha256:968af856e, artifact-registration-sha256:60127f2b7, artifact-registration-sha256:aad32cf85
Controls: attempt-F-F1-neg-225053
Replays: attempt-F-F1-replay-225104

### claim-mechanism

parseGitUrlSafe decodes/rejects '..' in filepath only; owner/name concatenated raw into the fetch URL; CatalogRules.matchLocation minimatches the raw still-encoded target while the reader fetches a decoded interpretation, and the reader fetch precedes rule enforcement.

Claim status: mechanism_or_reachability
Evidence: attempt-F-F1-primary-225049, artifact-registration-sha256:968af856e, artifact-registration-sha256:60127f2b7, artifact-registration-sha256:aad32cf85
Controls: attempt-F-F1-neg-225053
Replays: attempt-F-F1-replay-225104

### claim-reach

Any authenticated user via POST /locations (allow-by-default); 6 of 8 SCM readers affected (GitHub/Bitbucket Cloud/Server narrow+broad; GitLab/Azure/BB-Server/Harness/Gerrit broad).

Claim status: mechanism_or_reachability
Evidence: attempt-F-F1-primary-225049, artifact-registration-sha256:968af856e, artifact-registration-sha256:60127f2b7, artifact-registration-sha256:aad32cf85
Controls: attempt-F-F1-neg-225053
Replays: attempt-F-F1-replay-225104

## Intentionally omitted claims

- None.

## Structured claim-to-proof matrix

# Claim-to-proof matrix — F-F1 revision 1

- Claim state: `supported`
- Claim tuple: `sha256:0f545f8ebcbe309b0b4946f460198101c141649f404579a4eacae8e91369c857`
- Renderer: `decision-0005-proof-v1`

| Claim | Status | Statement | Primary attempts | Artifacts | Controls | Replays |
| --- | --- | --- | --- | --- | --- | --- |
| claim-mechanism | mechanism_or_reachability | parseGitUrlSafe decodes/rejects '..' in filepath only; owner/name concatenated raw into the fetch URL; CatalogRules.matchLocation minimatches the raw still-encoded target while the reader fetches a decoded interpretation, and the reader fetch precedes rule enforcement. | attempt-F-F1-primary-225049 | artifact-registration-sha256:968af856e, artifact-registration-sha256:60127f2b7, artifact-registration-sha256:aad32cf85 | attempt-F-F1-neg-225053 | attempt-F-F1-replay-225104 |
| claim-reach | mechanism_or_reachability | Any authenticated user via POST /locations (allow-by-default); 6 of 8 SCM readers affected (GitHub/Bitbucket Cloud/Server narrow+broad; GitLab/Azure/BB-Server/Harness/Gerrit broad). | attempt-F-F1-primary-225049 | artifact-registration-sha256:968af856e, artifact-registration-sha256:60127f2b7, artifact-registration-sha256:aad32cf85 | attempt-F-F1-neg-225053 | attempt-F-F1-replay-225104 |
| claim-impact | demonstrated | Private-repo content disclosure with the integration credential, provenance forgery, and group-membership forgery that can flip a real permission decision. | attempt-F-F1-primary-225049 | artifact-registration-sha256:968af856e, artifact-registration-sha256:60127f2b7, artifact-registration-sha256:aad32cf85 | attempt-F-F1-neg-225053 | attempt-F-F1-replay-225104 |

## Uncertainty

- deployment prevalence / config-gating may vary
