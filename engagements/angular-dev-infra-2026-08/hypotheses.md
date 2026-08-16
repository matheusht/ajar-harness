# hypotheses.md — every hypothesis and its disposition

Append-only. A hypothesis that dies stays here **with the reason it died**. Logging every kill is a
hard requirement (`engine/whitebox-analysis.md` §3) — it is what lets a human audit whether a
candidate was dropped for a good reason or a lazy one.

Dispositions: `open` · `active` · `held` · `blocked` · `refuted` · `candidate` · `confirmed` ·
`real-but-capped` · `real-but-not-reportable`.

**`real-but-not-reportable` is a separate axis from truth.** Already public, already fixed, on a
roadmap, or attributable to a consumer rather than to dev-infra — all real, none reportable here.
Record both facts. Never collapse this into `refuted`.

**Kill discipline.** No single grading pass may retire a candidate. A kill requires multiple
genuinely independent rounds that each add **new** signal, and the row must name what new signal each
round added. "A second agent agreed" is not new signal.

| id | family | hypothesis (one line) | file:line evidence | disposition | rounds survived | what killed it, and what new signal that round added |
|---|---|---|---|---|---|---|
| hypothesis-f13 | F13 | The three committed *_token.data blobs decrypt with public-repo-only material (org-name-derived key, hardcoded IV, committed GCM tags); GCP SA private key recovered | github-actions/{bazel/configure-remote,browserstack,saucelabs}/(constants.ts|action.yml) | confirmed | 3 | CONFIRMED + PROMOTED to findings/F13 (gates G0-G6 clear; 3 independent reviews; liveness inferred HIGH via public run metadata 2026-08-13; RBE fork-PR execution absorbed as impact addendum). Operator: filing + novelty + kernel revise-finding. |

| hypothesis-r3-merge-toctou | R3 | ng-dev merge tool validates head once then merges without SHA pin; force-push in window lands unreviewed head | ng-dev/pr/merge/* | real-but-capped | 1 | refuter: tool behavior confirmed; end-to-end gated by out-of-tree branch protection (dismiss-stale OFF + no required checks). Cheap fix exists (--force-with-lease pattern in sibling pr rebase). |
| hypothesis-r3-releasenotes | R3 | merged commit messages forge release notes (revert-hide validation bypass + BREAKING CHANGE spoof) | ng-dev/commit-message/*, release/notes/* | confirmed-low | 1 | reproduced; versions unaffected; feeds angular/angular migration docs. Package at operator discretion. |
| hypothesis-r8-preview-race | R8 | preview pack metadata race -> attacker-chosen channelId/comment number in trusted deploy job | previews/* + consumer wiring | confirmed | 1 | PROMOTED findings/R8-preview-metadata-race (Low, CVSS 3.1, gates clear). Caps: dormant wiring, label precondition. |
