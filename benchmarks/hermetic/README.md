# Hermetic Web and API Benchmarks

Deterministic JSON target specifications for testing authorization, SSRF, and untrusted output/dispatch verification rules without live network dependencies or stochastic model calls.

## Rules

1. Every target specification in `targets/<name>/target.json` is deterministic and human-authored.
2. Confirmation requires all three conditions:
   - Primary exploit request crosses the authorization or sink boundary (`signal: true`).
   - Positive control confirms detector sensitivity.
   - Negative controls (benign principal, escaped sink, echoed property, or non-dispatched tool listing) remain clean (`signal: false`).

## Targets (`8`)

| Target | Defect Class | False-Positive Trap Tested |
| --- | --- | --- |
| `bola-legacy-route` | Legacy `v1` route trusts client owner selector while `v2` derives owner from session | Shared/public object readable on both routes |
| `api-bola-state-change` | Cross-principal mutation alters foreign canary state | HTTP `200`/`204` response without foreign state mutation |
| `api-bopla-property-authz` | Mass-assignment / unauthorized guarded property write persists on server | Request JSON echoed in response without server persistence |
| `api-graphql-global-id` | Chained GraphQL resolver returns foreign tenant canary object | Schema introspection or Base64 global ID decoding without data leak |
| `api-jwt-claim-validation` | Wrong-audience or wrong-algorithm JWT grants guarded privilege | Valid signature on unprivileged token with denied access |
| `api-ssrf-redirect-follow` | Server HTTP client follows redirect to internal canary endpoint | Supplied URL echoed or stored without server-side fetch |
| `llm05-render-escape` | Untrusted model output reaches an unescaped active HTML/script sink | Canary string rendered inside escaped HTML entities or inert text |
| `llm06-capability-dispatch` | Untrusted input invokes a server tool outside the caller's authorized capability set | Listing tool metadata without executing the ungranted tool |
