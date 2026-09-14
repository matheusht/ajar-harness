## Parent

[Spec: trustworthy offline engineering evidence](https://github.com/matheusht/redteam-harness/issues/106)

## What to build

An operator can follow the active setup references and understand which architecture/status statements are current, without losing the dated decision record.

## Acceptance criteria

- [ ] Repair or remove the two absent setup-document references using the existing tracker and decision-index conventions; do not invent another instruction hierarchy.
- [ ] Provide a concise accurate current-status pointer where scaffold-era language presently appears current. Preserve historical engineering decisions as history.
- [ ] Keep the two entrypoints byte-identical according to the accepted mirror decision.
- [ ] Reuse documentation conformance and extend it only for the active references touched here. Do not add a generic Markdown crawler.
- [ ] Preserve the distinction between stale draft pins and invalidated authorized pins. Any draft update is explicit; authorized evidence is never silently repinned.
- [ ] Verify current pointers, mirror equality and relevant pin behavior through the existing public check boundary.
- [ ] Do not change operational instructions, gate semantics, settings, launch behavior, records or required generated views.

## Blocked by

None (can start immediately).

## Current baseline update

Local main advanced to `0d8fe0c4ffb57a3bf1cfd5d4db013113b51d8c8d` during publication. That commit separates repository engineering from engagement work, removes both broken setup references and refreshes the draft instruction pin. A direct check confirmed the two entrypoints are byte-identical, the references are absent, and the matching overlay remains `draft_not_authorized` with execution authorization false.

Reuse that completed work. The original research snapshot remains pinned to the earlier inspected source; do not repeat the reference-removal patch. Current-status navigation and any necessary focused conformance coverage remain to assess and complete. This observation does not establish the whole ticket complete, and no implementation or experiment was run by this publication task.

## Review basis

The engineering investigation established broken pointers and mixed temporal status. It did not establish a client-loading cause for repeated instructions. This slice fixes navigation only.

Approved on 2026-09-05 as part of the [six-ticket breakdown](https://github.com/matheusht/redteam-harness/issues/105#issuecomment-5553859692). This ticket is open implementation/preparation work; research checks are not completion evidence.
