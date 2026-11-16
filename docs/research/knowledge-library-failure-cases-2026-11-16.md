# Knowledge library failure cases

Defined before implementation for the research-autonomy plan. Luna owns focused
local verification; provider runs, full E2E and research comparisons are deferred.

| Scenario | Required observation |
| --- | --- |
| Select a version, update same-name source, interrupt delivery | Retrying the selected version reads its original bytes; discovery exposes both versions. |
| Reference exceeds 4 MiB | Retain as a file, return bounded text reads, preserve its full source digest. |
| Fetch succeeds, retention fails | Return permitted content with `not_retained`; durable delivery journal/export records the gap; later retrieval is a new observation. |
| Content contains credentials | Reject before delivery or retention fallback; public origin grants no exemption. |
| Catalog unavailable versus empty query | Report unavailable/partial separately from an available catalog with no matches. |
| Missing/corrupt source or extraction | Report the missing part; never call a summary the original source or imply complete extraction. |
| New experimental procedure | Discoverable without evaluation or successful execution; does not alter closure or authority. |
| Same author/session or same source case evaluates | Reject recommendation; a new runtime/session alone is not transfer. |
| Independent changed-case and counterexample review | Recommend only retained exact version, with trusted actor and resolved evidence references supplied by controller. |
| Changed procedure or applicability | New version starts experimental and inherits no earlier evaluation. |
| Contrary evidence narrows/withdraws | Later reads expose current status/reason; earlier bytes/evaluations remain available. |
| Path traversal, unsafe symlink or changed retained file | Reject rather than read arbitrary host material or silently accept altered bytes. |
| Export | Includes selected retained versions, provenance, evaluations and recorded retention gaps; absent bytes are explicit. |

Integration owns authority: the native boundary checks current signed permission,
binds actor/session/case and resolves evidence references before calling the host
library. It journals selected version before materialization and delivery outcome
afterwards. Library files and catalog content are reference data, never authority.

## Host delivery integration cases (defined before adapter implementation)

- A worker attempts to supply another author's/session's identity: the host derives
  author, session and source case from its current verified grant instead.
- A technique evaluator lacks a fresh assigned pending review, cites invented
  evidence or only supplies Boolean outcomes: reject recommendation.
- A measurement helper cites only a prose publication: require actual protected
  experiment evidence. A procedure's checkable decision can instead cite a fresh
  reviewer-authored observation with retained artifacts, bound to signed case inputs.
- A procedure's decision artifact is missing, modified, predates its review or has
  a different author: reject that evaluation reference.
- A fetch or materialization is interrupted: retry the host-selected version using
  the same injected call identity; no same-name re-fetch or premature delivery claim.
- Materialization targets a symlink or encounters a changed partial file: refuse
  unsafe replacement; restart a bounded temporary write and verify complete bytes.
- Shared-library retention succeeds but engagement-local pin fails: deliver permitted
  content with an engagement retention gap, preserving its actual archive limitation.
- New source bytes are readable but no durable record can be written: do not claim
  they are archived or recoverable. Partial delivery is separate from unknown target
  execution and leaves retained originals available for a later permitted retry.
