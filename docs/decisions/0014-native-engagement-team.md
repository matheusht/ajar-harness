# 0014 — One durable engagement controller with native research runtimes

**15 November policy successor:** [Decision 0015](0015-initial-scope-autonomy.md)
adopts the initial-scope v2 authority policy and new-work caller routing. The
implementation decision and historical evidence below retain their dated meaning.

**Status:** Accepted implementation direction, 14 November 2026. Runtime
activation remains conditional on the signed v2 contract and verified capability
enforcement. Existing route gates and historical signatures keep their meaning.

**Authority:** The operator approved Q1–Q30 and assigned the full
[M0–M6 engineering plan](../research/oslit-engineering-plan-2026-11-14.md) in the
`technical oslit` chat. This is an engineering assignment, not a research scope,
finding acceptance, deployment or disclosure authorization.

## Decision

Keep `tools/native_engagement.py` as the public entry. New
`native-engagement-inputs-v2` roots select one controller and one append-only
journal. Existing v1 roots retain their existing driver and receipt meanings;
neither route falls back to the other after a failure.

The lead owns research decisions, priorities and team expansion. Specialists own
their experiments and may propose follow-up work. Fresh reviewers challenge exact
evidence versions. Codex and OMP retain native execution, tools, sessions and
context management. The controller supplies engagement ownership, shared usage,
authority, review obligations, recovery and cleanup across runtime lifetimes.

Use [the concrete v2 contract](../research/oslit-v2-contract-2026-11-14.md) and
[failure-first scenarios](../../evals/native-qualification/TEAM-ENGAGEMENT-SCENARIOS.md).
The journal is the only authoritative state store. Immutable protected executor
receipts remain execution evidence; controller events cannot substitute for them.
Keep claim, search and cleanup states distinct.

## Enforcement before activation

An initial v2 signature may authorize bounded internal acquisition, setup, artifact
classes and escalation rungs across source, binary, application and SSH laboratory
access. It never widens an existing v1 signature. Unlisted effects, accounts,
destinations or resource capabilities are refused. Internal escalation needs the
prior effect and fresh independent evidence review within the signed ceiling.
External action remains separately authorized.

Native worker pooling is reusable only when caller identity, role limits, usage
and revocation are enforced. Otherwise use isolated native sessions with a private
host channel. A role prompt, copied worker ID, cancellation response or queue flag
does not prove isolation. Alternate spawn, direct provider calls and peer wake
paths must meet the same limits. An adapter missing those controls cannot activate
that capability, even if a harmless model call succeeds.

Overall expiry is optional. Short renewable worker leases bound disconnected
work; restart and replacement preserve authority, usage and uncertainty. There is
no fixed 24-hour investigation ceiling. Unsupported hard accounting dimensions
are refused rather than represented by transport counters.

Only a signed and enforced v2 route can use preauthorized internal artifact and
review permissions. Root documentation must route those exceptions explicitly
when implemented; this ADR alone does not bypass a current runtime gate.

## Alternatives and limits

Extending both the old phase driver and its continuation state with team ownership
would leave two mutable owners for each fact. A new scheduler over those unchanged
loops would keep global serialization and global uncertain-effect holds. Both were
rejected. Preserve useful effect primitives without their duplicate orchestration.

Do not build a universal model client, generic tool loop, second conversation
store, fixed swarm or cross-engagement optimizer. Task-local instruments and
scorers remain ordinary native research work with immutable measurement versions.
Scores do not confirm claims or replace the lead's priorities.

Engineering support requires observed capability evidence for each runtime and
environment. Unavailable Docker/SSH/provider checks remain unfinished. A sustained
harmless soak is distinct from accelerated clock tests. The operator owns the
future fresh-target research and native-agent comparison; engineering results
cannot supply their missing positive or comparative evidence.
