# Harness entrypoint

For **repository engineering, research, documentation or planning**, ground the work in the current
implementation and the [Domain docs](#domain-docs) below. Keep the requested technical scope and
deliverable primary; distinguish observed behavior, proposed changes and implemented work.
For substantial changes, state the decision, inspect raw source and execution evidence, compare
the simplest serious alternative, and define a falsifiable acceptance check before implementation.
After the last edit, verify that claims still match their evidence and review.

For **new local source research**, use [source engagement bootstrap](skills/source-engagement-bootstrap/SKILL.md)
for target selection and [native local research](docs/agents/native-local-research.md) as the
single prepare/start/resume/stop and internal-output procedure. This branch implements the
candidate source default for #166–170; #165 has no scoped adopt decision and live qualification
remains unverified. Before any actual run, read the signed target-local
`engagements/<id>/scope.md`, verify every used vulnerability card has a benign `safe_signal`,
and obtain the native runner's exact plan-bound approval. The runner itself does not verify the
scope signature or safe signal. A native task does not initialize or write the legacy queue or
record kernel.

For **existing queue/record engagements** or work explicitly assigned to that runtime, follow
[the legacy entry](docs/agents/legacy-local-research.md). Preserve its admitted readers,
immutable history, record kernel and Docker queue. Repository work grants no permission to run
an engagement; the signed scope, evidence and redaction boundaries remain.

## 0. Prime directive

Your product is **rigor, not findings**. Default to disbelief. A result is `needs_review` or
`contaminated` until it survives the oracle. Discovery preserves plausible leads;
confirmation requires evidence; reporting stays within supported conditions.
Keep claim state, unfinished search, and bounded coverage distinct.

## 1. Hard gates (refuse to proceed otherwise)

1. **Scope gate** — `engagements/<target>/scope.md` must be filled and signed (surfaces, benign
   objective set, escalation ceiling, impact-demo authorization y/n, accounts). No scope, no run.
2. **Safe-signal gate** — never run a vuln skill whose front-matter lacks a benign `safe_signal`.
3. **Impact-artifact gate** — before creating a Zone-2 PoC artifact (see README scope fence),
   require either a fresh human confirmation or an explicit standing local-PoC grant in the current
   signed scope that the record kernel enforces. The `chia-blockchain` child engagement may use that
   grant for contained local PoCs and necessary local experiments without per-artifact confirmation.
   Record each artifact and cleanup obligation at creation. Effects beyond the signed environment,
   containment, or cleanup authority still stop for human confirmation. A native route without the
   record kernel does not inherit a kernel-enforced grant.
4. **Review gate** — operator reviews assembled findings before any escalation up the severity
   ladder (self → stored/persistent → cross-user), each rung gated on the prior succeeding.
5. **External-action gate** — filing, disclosure, vendor contact, deployment, publication and
   other effects outside the signed local task require the operator's explicit authorization.
   An internal native result is not external delivery.

## 2. Legacy roles

See [legacy roles](docs/agents/legacy-local-research.md#2-roles-put-cognition-where-the-leverage-is)
for existing queue/record work.

## 3. Legacy card loading

See [legacy card loading](docs/agents/legacy-local-research.md#3-how-skills-are-loaded-decision-portable--deterministic).

## 4. Legacy runbook

See [legacy runbook](docs/agents/legacy-local-research.md#4-the-runbook-legacy-engagement).

## 5. Legacy records and memory

See [legacy records and memory](docs/agents/legacy-local-research.md#5-records--memory).

## 6. Redaction (always)

Never store auth cookies, JWTs, Authorization headers, signed URLs, or passwords in any plane.

## 7. Deferred legacy roadmap

The [legacy entry](docs/agents/legacy-local-research.md#7-not-yet-built-phase-2)
retains this section for historical references. It does not add native run requirements.

## Engineering references

### Issue tracker

Issues live on `matheusht/redteam-harness`, driven via the `gh` CLI. Keep issue
context sanitized and target-specific evidence in the target's own records;
repository visibility is not a redaction control. The
[legacy placement rule](docs/agents/legacy-local-research.md#4-the-runbook-legacy-engagement)
retains its supported engagement layout.

### Domain docs

**Direction:** for product, architecture, workflow or planning changes, read
[product and engineering direction](docs/wiki/product-and-engineering-direction.md).
**Status:** for capability, readiness or qualification claims, read the dated
[native research status](docs/wiki/native-research-status.md), then its source evidence.
ADRs live in **`docs/decisions/`**, not `docs/adr/`; use
[the decision index](docs/decisions/README.md) for authority and supersession.
