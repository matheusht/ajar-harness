# One read-only workflow pilot

Frozen design, 2026-09-20; fixture constructor and baseline harness:
`5e366a32af299fead09180b5ef349310d674d7cd`.
Candidate harness is #99 commit `a263c8c56bb1ce69a29097b5d0be578d3e8e1aca`, pending
independent review before dispatch; merge is not required. This protocol prepares one fresh Astra Low candidate, not a production engagement.
No runtime implementation, benchmark framework or new provider integration is proposed.

## Inputs and preparation

Use the existing `tools/dossier-inspector-test.py::rich_static_dossier` constructor in a new
temporary Git repository. It directly writes invented workshop metadata, including stale views and
an outstanding review. Its synthetic signature is test metadata, never operational authorization.
Reuse this minimal setup from the pinned baseline checkout, with `PILOT_ROOT` set to a fresh path:

```sh
python3 - <<'PY'
import hashlib, importlib.util, json, os, subprocess, sys
from pathlib import Path
harness = Path.cwd()
root = Path(os.environ['PILOT_ROOT'])
root.mkdir()  # refuse reuse of an existing pilot
repo = root / 'candidate'
repo.mkdir()
sys.path.insert(0, str(harness / 'tools'))
spec = importlib.util.spec_from_file_location('fixture', harness / 'tools/dossier-inspector-test.py')
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
fixture.rich_static_dossier(repo / 'dossier')
goal = repo / 'dossier/goal-prompts/goal.md'
goal.parent.mkdir()
goal.write_text('# Synthetic workshop document review\n\n'
                'Explain the current supplied workshop documents without changing them.\n\n'
                'You cannot move coverage to `coverage_dry` while blocking work remains.\n'
                '`covered-dry` — the bounded space was enumerated AND adjudicated.\n')
subprocess.run(['git', 'init', '-q', str(repo)], check=True)
manifest = {str(p.relative_to(repo)): 'directory' if p.is_dir() else
            hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(repo.rglob('*'))}
(root / 'before.json').write_text(json.dumps(manifest, indent=2) + '\n')
PY
```

Before dispatch, freeze outside the candidate repository: full manifest and its digest, exact
baseline/candidate harness commits, exact candidate task and its digest, interpreter identity,
expected answer rubric and baseline command outputs. Candidate task gets only source locations,
not expected answers. Mechanical baseline/candidate controls use the same fixture and public reads;
record them separately from the fresh-agent trial. Compare source bytes/inventory after all reads.
This is instruction-only blindness, not filesystem isolation or a hidden benchmark.

## Candidate task and limits

Read the synthetic goal and the named shared procedure at
`skills/source-engagement-bootstrap/references/goal-template.md` in the pinned candidate harness.
Use public preflight, inspector, list, next and gate reads, plus
`tools/completion_claims.py --engagement <dossier>` to identify current claim/source revisions,
stale views, outstanding review reason/subject, next queue action and whether completion is allowed.
Preserve narrative, unknowns and human cleanup context; report command exit statuses.

One fresh Astra Low agent, one attempt, ten-minute ceiling. Read only the fixture and named
harness/interpreter needed for those commands. Do not inspect fixture construction tests, expected
answers, grading files or task history. Do not use `run-engagement reduce`: it writes snapshot/views. No reinitialization, rendering, repairs, hunting, target or
provider API invocation, provider runtime, Zone-2 artifact, extra agent or favorable-result retry.
Candidate model inference is real usage; billing is unknown. No fallback extraction exercise.

## Recording and acceptance

Keep full candidate output, including failure or unknown, outside the source. Compare answers with
the frozen rubric; record omissions without adjusting expected results. Record wall time, command
count/statuses and exact post-run byte/inventory comparison, including Git metadata. The critical
boundaries are source preservation, correct current-state reconstruction and refusal to infer
completion from misleading explanatory goal text. A failed trial remains a result, not a reason to
replace the candidate. Human-time savings, discovery efficacy and operational runtime viability
remain unknown. This document records protocol only; no candidate outcome is claimed.

Prepared task SHA-256: `26438c490b3243836c1e41d7c728e3a58312b8613d050d0036d7db99ac7285c6`.
Prepared manifest SHA-256: `4939031c37571e670744282335e1f576ddaf74bb778e1ed8aedfbab53e6de4f3`.
Baseline and candidate mechanical controls each returned preflight/inspector/list/next 0 and gate 3.
All ten reads preserved bytes/inventory. These are setup controls; the agent trial has not run.

The five original reads bypass completion-claim scanning; equal results are expected, not a patch
improvement. Added the public read-only completion-claims CLI before candidate dispatch: baseline
exited 1 (`completion_claims_unjustified`), candidate exited 0 (`completion_claims_clear`).
Both preserve source inventory. Clear text scanning does not clear the five queue blockers.
The revised task/grade are frozen externally; final reviewed #99 pin is still required before dispatch.

## Measured result — 2026-09-20

The preparation statements above are historical. The single candidate ran against independently
reviewed harness `2f5ad62eaf54fa7117273e38f56d3919fcaf439b` (Standards and Spec: PASS),
with runtime changes last made at `9919fba5e13485d43113e10a6ac235dd16556f81`.
The final externally frozen inputs were:

- Task SHA-256: `90707b3433bd96b7bf3d0541e357d37ccb5b12dcd8ab4781953497639f0ffd33`.
- Grade SHA-256: `a6aa7c85fa7c6dada8ce5f7a207e71812cbbfb316786081bc126d40945d0ea1f`.
- Source manifest SHA-256: `4939031c37571e670744282335e1f576ddaf74bb778e1ed8aedfbab53e6de4f3`.

One fresh Astra Low agent received no prior conversation (`fork_turns=none`). Dispatch was
22:26:17 UTC; its result was received at 22:27:54 UTC: **97 seconds orchestration elapsed**.
This is neither measured machine effort nor human working time. There was no user intervention
and no replacement trial. Actual model inference occurred; token usage and billing are unknown.

The parent independently compared the answer with the frozen grade. All requested dimensions
were correct:

- Current `document-claim` revision 3 is supported, not confirmed. Workshop v2 supersedes v1;
  the current time is 11:00 rather than 10:00, and the venue is unknown.
- Pending `citation-review-needed`, backed by regrade `citation-review`, concerns the missing
  venue citation for subject `document-claim`.
- Progress still describes revision 1, snapshot is `{}`, report index contains only report 2,
  and review index contains review 2; these projections are stale.
- Next queue action is `hypothesis_ran_unadjudicated` for `document-revision-question`, with
  operation `record_hypothesis_disposition`. Gate exit 3 retains five blockers; coverage is
  active and completion is not allowed. The paper-crane cleanup context was preserved.

The candidate reported six public checks: preflight 0, inspector 0, list 0, next 0, gate 3,
and completion-claims 0. These agree with independently run mechanical controls. The candidate
reported no state-changing operations. Its command list/statuses are self-reported; there is no
independent per-command trace or verified total command count. Independently, the parent recomputed
all **64 file and directory entries, including Git metadata**: exact equality, with zero added,
removed, or changed entries.

There were two frictions. The candidate reported an initial `cat` of
`<dossier>/source/goal-prompts/goal.md` exiting 1, then recovered through directory inspection and
reading the actual goal path with exit 0. The task's shorthand `source/goal...` was ambiguous.
Inspector display truncation also led to direct source reads. These are observable in the returned
account, not an independently captured tool trace. Recovery occurred within the same trial; this
was not a zero-retry or issue-free run. Future pilot briefs should name the exact goal path; the
frozen task was not rewritten. Neither friction warrants a runtime change on this evidence.

This result supports one read-only synthetic workflow: reconstructing current state, retaining
unknowns and blockers, and preserving source bytes despite explanatory completion tokens. It does
not establish actual-target performance, autonomous-hunter efficacy, general workflow reliability,
or human-time savings. There was no matched agent baseline. Mechanical before/after completion
checks isolate gate behavior; they do not supply that missing agent comparison.

All 62 completion-claim tests passed at `9919fba5` (the same runtime used here). Full kernel
self-test and 898-check structural conformance passed at prior head `a263c8c5`; these broader
checks were not repeated for the formatting-only correction. Final combined-head hosted CI
remains to be verified before merge.
