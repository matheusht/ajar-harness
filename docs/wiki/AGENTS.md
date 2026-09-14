# Engineering wiki maintenance

This directory is the maintained synthesis of engineering decisions, evidence and open questions. It inherits the repository instructions. Read [index.md](index.md) first and follow only the pages relevant to the task.

## Sources and authority

- Existing decision records, approved specifications, source code and research evidence remain in their original locations. Link to them; do not create a duplicate raw-source collection or rewrite historical evidence during wiki maintenance.
- A wiki summary does not approve a design, modify an accepted specification, change an operational gate or promote an experimental result. Record the approving source and distinguish accepted plans from implemented behavior.
- Attribute claims with the source URL/path and revision or observation date. Separate observations, hypotheses, recommendations, accepted decisions, implemented changes and verified results. If a source is mutable or only sampled, say so.
- When sources disagree, record the conflict and the applicable revisions. Follow an explicit superseding decision; never silently turn a newer note into authority or erase the old evidence.
- Keep repository engineering here. Link to other domain indexes when useful, but keep credentials, private engagement records and operational payloads out of this wiki.

## Updating the wiki

1. Read the relevant source and existing page. Follow source links before relying on a detail the summary does not establish.
2. Update the smallest relevant topic page with the new decision, evidence or unresolved question. Preserve the distinction between a past observation and the currently verified state. Create a page only when a distinct reusable topic has enough material to need one.
3. Link the source and related wiki pages; update [index.md](index.md) when navigation changes.
4. Append a dated entry to [log.md](log.md) naming what changed, why, the source/commit and the checks or limits. Keep prior entries; add a correction entry when one is needed.
5. Check the changed links, contradictory status claims and unsupported conclusions. Record any material gap rather than filling it with an assumption.

Use this process when a source is ingested, an engineering decision changes, a slice is implemented/tested, or a reusable answer adds evidence. Do not manufacture an update for every tool call. A question with no new durable information can be answered with citations to the existing page.

## Lightweight operation

The index, ordinary Markdown links, `rg` and Git cover the current need. Add no database, search service, embeddings, generated dashboard, background job or wiki-specific test framework without a demonstrated problem.

At the end of a meaningful work slice, check that changed pages are reachable, their source links resolve, dates/statuses agree and missing evidence remains explicit. This is a bounded content check, not a repository-wide ingestion campaign.

Implementation workers follow the model/effort and permission limits in the [implementation goal prompt](../research/harness-engineering-2026-09-05/implementation-goal-prompt.md). Wiki editing never grants additional execution authority.
