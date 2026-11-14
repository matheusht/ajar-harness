# Declared source capture effects and initial setup

Native setup selects exactly one account-free `read` effect at the initial
`source_only` or `self` rung covering the environment and selected resources.
Declaring later stored/cross-user reads therefore does not make initial setup
ambiguous. Missing or multiple compatible initial reads still refuse setup.

A source/binary-only `engagement_capture` can name an optional signed `effect_id`.
The effect must cover every selected resource and the environment, have no account
references and not create an unsupported impact artifact. Invalid selectors fail
before an auxiliary reservation is created. An omitted selector uses the initial
read effect. The selected effect binds only the captured execute intent/result;
preparation, source reads and cleanup retain the initial mechanics permission.
The controller applies the current evidence-review gate before that execution.
An application or combined application capture rejects this local selector; its
actual target requests select their own effect through `X-OSLit-Effect`.

## Repeat

Python 3, OpenSSL and ssh-keygen are required. The boundary regression additionally
uses macOS sandbox-exec. Run from the repository root:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 evals/native-qualification/smoke/check_native_capture_effects_e2e.py --output /tmp/capture-effects.json
PYTHONDONTWRITEBYTECODE=1 python3 evals/native-qualification/smoke/check_native_application_capture_e2e.py --output /tmp/capture-applications.json
PYTHONDONTWRITEBYTECODE=1 python3 evals/native-qualification/smoke/check_engagement_native_boundary_e2e.py --output /tmp/capture-boundary.json
```

Expected: six capture-effect scenarios, six application scenarios and 23 boundary
scenarios pass. Receipts identify the exact exercised source hashes; the manifest
binds all saved files. The failure-first baseline `before.json` demonstrates the
composition gaps. Its invalid-selector case initially failed while constructing
the signed fixture; `invalid-selector-before.json` preserves the corrected
fixture rejecting the old implementation before the production change.

The new full-chain fixture records initial effect/control captures, a fresh
reviewer capture and accepted claim; accepts a separate transition review; then
records stored effect/control/fresh replay captures before the next reviewed
cross-user capture. Every capture uses NativeBoundary's pinned probe execution,
immutable controller observations and ordinary experiment/review requests.
The fixture does not patch the protected controller observation methods to inject
higher effects. Other cases cover invalid names/types, wrong resource/environment,
account-bearing and artifact effects, missing/ambiguous initial authority,
unapproved higher execution without a leaked reservation, explicit local execute
permission and application-selector refusal before any target contact.

The harmless probe runs as an owned local subprocess. Native model, container
ownership and semantic reviewer judgments are explicit engineering simulations;
declared fixture rungs are not evidence of a security effect. The application
regression additionally uses actual owned HTTP and the real stdio relay. No
external provider, external research target, Docker daemon or SSH host is called.
This establishes composition and admission mechanics, not live native behavior,
container isolation, application reset, research acceptance or a multiday soak.
