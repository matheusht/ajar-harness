# Unsigned v2 engagement templates

These examples grant no authority. They contain placeholders and no signature,
operator key, allowed-signers file or working account credential. Copy one access
mode into a private input directory and follow the [operator guide](../../docs/agents/engagement.md).
Every `REPLACE_` occurrence must be resolved before signing.

| Directory | Supplied access | Initial configuration |
| --- | --- | --- |
| `source/` | Read-only source tree, pinned by the complete file manifest | Codex; local Docker; offline native tools |
| `binary/` | Pinned Linux binary | Codex; local Docker; offline native tools |
| `application/` | Exact application URL/version, no account binding | Codex; local Docker; scoped target proxy |
| `combined/` | Source, binary and application access together | Codex; local Docker; scoped target proxy |

Each directory includes complete inputs, scope, goal, runtime, native config and
environment fields. The initial `read-inputs` effect covers every supplied input
in its selected environment, so the lead can receive the combined source/binary
assignment. Local execution is a separate effect. The sample authorizes neither
external writes nor an impact artifact. Add permitted setup/acquisition routes,
effects or a different scope ceiling only through the operator's signed decision.
For acquisition, update the signed routes, environment capabilities and native
network policy together; source/binary configs start with tool networking disabled.
For application access, replace the target host in the access identity, target
route and native domain allowlist together. Application configs allow local proxy
bindings and rely on the isolated lab's network namespace for containment.

Select the provider/model combination actually available in the pinned runtime.
The examples use the OpenAI API credential **reference** `env_OPENAI_API_KEY` and
its provider route; no value belongs in a template. Replace the model in both the
runtime profile and native config. Selecting a runtime does not establish model
availability, billing authority or provider qualification.

`optional/runtime-omp.json` and `optional/omp-settings.json` replace the Codex
profile/config when choosing OMP. Update `inputs.runtime_profiles`, its scope
profile hash, bundle reference and any provider/model routes together. One
engagement may admit either runtime or both; an unused profile is not required.
`optional/environment-ssh-docker.json` replaces the local Docker profile when
choosing an authorized SSH lab. Pin independently verified host keys and reference
the operator's private SSH identity; the input bundle contains no private key.

`linux/arm64` is a template choice. Match the binary identity, tool bundle and lab
platform to the selected environment. Replace all image, executable, config,
schema, source, profile, goal, signer and bundle pins with hashes of actual bytes.
The source manifest includes file modes and sizes as well as digests. Keep final
input files private and stable after signing.

These templates use no application account. For authenticated access, add the
account IDs to the signed access/effects and configure the private host reference
file described in [target account binding](../../docs/agents/engagement.md#bind-target-accounts-by-reference).
Preflight checks the references without target contact. Request observations bind
the configured logical account; a target-specific check must establish the user
the application actually recognizes. Application capture records remote reset as
unverified, so it cannot supply clean independent remote replay.

These profiles omit `model_host` and therefore select the macOS model owner with
an isolated Linux tool lab. For the implemented Linux owner, follow the
[operator host setup](../../docs/agents/engagement.md#prepare-the-host-and-tool-lab)
and add its exact signed `model_host` object before signing. OMP custom model
definitions may use the optional pinned `model_catalog`. Both runtimes passed actual Linux native
startup and joined source containment/recovery with controlled provider replies; see the
[fresh-target handoff](../../docs/agents/fresh-target-handoff.md). The
[dated delivery state](../../docs/wiki/oslit-v2-delivery-2026-11-14.md) separates
implementation, contained checks and qualification work.

The templates select `authority_policy: "initial-scope-v1"` and an explicit
`owned-lab-state-v2` creation effect for the owned tool/client lab. This covers
all artifact contents in that lab without per-file confirmation. The separate
execution grant starts tools/probes. Application resource IDs in this client-lab
grant do not grant remote writes; target effects remain explicit. Pin the complete
initial scope and sign once. Resume retains that signature and authority.
See the [class contract](../../docs/research/oslit-v2-contract-2026-11-14.md#candidate-owned-lab-state-class).

For an owned Docker application/database baseline, the [application contract](../../docs/research/oslit-v2-contract-2026-11-14.md)
defines v2 disposable state volumes and the optional `owned-application-state-v1`
artifact effect. The supplied templates omit target-state profiles; when an
initial-scope policy declares `application_states`, each reference must name its
exact `artifact_effect_id`. Set the real database command,
image baseline and state paths before pinning and signing; an external database
or existing volume is not reset by this descriptor.
