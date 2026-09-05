## Parent

[Spec: trustworthy offline engineering evidence](https://github.com/matheusht/redteam-harness/issues/106)

## What to build

An operator or independent reader can inspect one bounded dossier and understand what its records establish, what changed, what remains unknown and where each fact came from, without assembling several bare-ID indexes manually.

## Acceptance criteria

- [ ] Consume valid admitted authoritative inputs through existing identity/read protections and emit an ephemeral summary. Do not invoke writing reduce/render paths, create coordination state, repair inputs or dispatch work.
- [ ] Show reading basis, validation result, source identity/digests, last recorded state, stale projections and unavailable inputs. An invalid base state remains unavailable; stale projections can be explained without regenerating them.
- [ ] Distinguish source-document revision from claim-record revision and show the recorded change reason/event.
- [ ] Display typed review subject, inputs, rationale and recorded independence. Respect predecessor-adjudication versus filing/report-review relationships rather than assuming every review references the latest revision.
- [ ] Explain current report status and supersession from the recorded state/history, including why an immutable draft manifest can correspond to a currently accepted report.
- [ ] Keep optional supplied task intent and configuration observations attributed separately. Missing task context or loading observations stay unknown and are not inferred from scope or a queue.
- [ ] Preserve external outcome rows and their external report identifiers, provenance, available confidence and decision/recording times. Ambiguous revision mappings stay unmapped. Do not infer current validity, remediation or latest-row supersession.
- [ ] Distinguish absent, unreadable, invalid, unmapped and stale supplements. Graceful failure applies only to separately supplied inputs outside base admission. Malformed or colliding records already indexed by base admission retain that failure; do not filter them out to manufacture valid state. Retain human cleanup context and unique narrative.
- [ ] Exercise the public inspector on a harmless revisioned dossier containing the relationships above and the three presentation omissions. Include absent coordination, invalid indexed records, separately invalid supplements and rejection during final source-identity checks. A missing lock creates nothing; a subsequently rejected source emits no valid summary.
- [ ] Verify unchanged bytes and no created files or coordination state across the inspected source. Preserve existing generated-view compatibility, record authority and the separate filing-lifecycle issue.

## Blocked by

None (can start immediately).

## Review basis

The existing renderer demonstrably omits useful state. The new summary's semantic correctness can be tested now; operator-time savings require a later comparison and are not acceptance claims for this slice.

Approved on 2026-09-05 as part of the [six-ticket breakdown](https://github.com/matheusht/redteam-harness/issues/105#issuecomment-5553859692). This ticket is open implementation/preparation work; research checks are not completion evidence.
