# Claim and lead input, revision 1

This is an owned synthetic local workflow, not a vulnerability report. Model sessions
must receive original source, note/policy inputs, raw CLI/effect records and their
hashes directly from the operator. No reviewer outcome has been written.

C-BASE v1: Alice can create a local draft of note-1, her own note, through the draft
command. Conditions: original app source, note-1 owned by Alice, a clean writable
state directory and policy v1. Independent setup records show the exact draft bytes.

C-A v1: Alice can publish that draft through the publish command under v1, leaving
published.txt with the same bytes. This depends on C-BASE, Alice's identity and the
owner-publication condition in v1. This is a local file effect; it does not prove
network distribution or access by an unrelated user.

C-CHAIN v1: a third party could obtain that note after C-A. This is an unresolved
extension, not an accepted effect: there is no delivery/read service in this fixture.
The missing transition is an authorized consumer obtaining the published bytes.

L-B v1: the source exposes a distinct delegate-publication path. The normal synthetic
note assigns Bob as delegate. It is uncertain whether Bob can publish the existing
draft through the actual CLI, and who may supply or change that delegation in any
real importer. The useful next check is Bob's normal publish with a Carol denial
control, followed by identifying the importer/delegation authority if that component
is ever supplied. The fixture alone cannot settle the absent importer's trust boundary.

Researcher proposal: label L-B "duplicate of C-A" and abandon it if owner publication
is disabled. This is a proposed disposition for review, not an accepted decision.
Inspect its concrete basis and distinct conditions before deciding. Unreviewed work
remains unfinished if a stop or allowance bound arrives.

Contrary evidence: publishing with no draft fails; Carol cannot draft or publish.
Raw results include stdout/stderr/exit status and independently read file bytes, not
only these summaries. Unfinished: delegation path, importer authority and delivery.
