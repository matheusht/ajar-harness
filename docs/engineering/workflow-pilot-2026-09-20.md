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
Use public preflight, inspector, list, next and gate reads to identify current claim/source revisions,
stale views, outstanding review reason/subject, next queue action and whether completion is allowed.
Preserve narrative, unknowns and human cleanup context; report command exit statuses.

One fresh Astra Low agent, one attempt, ten-minute ceiling. Read only the fixture and named
harness/interpreter needed for those commands. Do not inspect fixture construction tests, expected
answers, grading files or task history. No reinitialization, rendering, repairs, hunting, target or
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

Prepared task SHA-256: `b62cf4871b2bd9cab755ed927f0651a00400e02b7fad7701981e7739ffd51550`.
Prepared manifest SHA-256: `4939031c37571e670744282335e1f576ddaf74bb778e1ed8aedfbab53e6de4f3`.
Baseline and candidate mechanical controls each returned preflight/inspector/list/next 0 and gate 3.
All ten reads preserved bytes/inventory. These are setup controls; the agent trial has not run.
