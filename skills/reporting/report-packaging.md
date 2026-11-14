---
id: reporting.report-packaging
name: Packaging a report and proof of concept
description: >
  The delivery contract for a vulnerability report: one paste-ready report, one impact field,
  a runnable PoC directory, verbatim output, evidence references, cleanup, hashes, and a zip
  that does not leak the audit trail. Use with `reporting.vulnerability-report-writing`.
type: reporting
owasp: "—"
atlas: "—"
---

## The package is the submission

A report is not done when the prose is good. It is done when a stranger can open one directory,
read one quick-start, run one command, see the claimed signal, and check the evidence without
asking you anything.

Minimum layout:

```text
report-package/
  report.md                 # Description field, paste-ready
  impact.md                 # Impact field, paste-ready
  metadata.json             # form fields and pins
  README.md                 # one-screen quick start
  chain.md                  # chain overview table + diagram source
  poc/
    README.md               # what this proves, prerequisites, run, expected
    run.sh                  # deterministic fast path
    expected-output.txt     # verbatim clean-run output
    src/ or tests/          # the actual proof
    stages/                 # optional per-stage entry points or nearest observable
    supporting-material/    # transcripts, captures, logs
  evidence/
    source-refs.md          # file:line, symbol, what it shows
    verify-output.txt       # raw run output
    reliability.txt         # raw per-stage run counts
    hashes.txt              # artifact and input hashes
  environment/              # optional chain inputs: build.sh, flags.txt, images.sha256
  cleanup.md
  manifest.sha256
```

One finding, one package. If two findings share a root cause, one report with a
`Related, supporting finding` subsection is usually better than two packages. If a chain has
several root causes on one path, keep one package and give each link its own anchor and stage
row; do not split the path into separate submissions. Two independent roots that reach the same
terminal primitive are two findings, not one chain.

For a chain, `chain.md` holds the stage table and the diagram source. `report.md` repeats the
table and references the diagram; the table must remain usable if the diagram is removed.

## report.md and impact.md

These are the two paste-ready artifacts. They must not contain operator instructions.

- `report.md` may start with a package `# Title`; the Description paste range begins at `## Summary`.
  It contains Summary, At a glance, Affected/tested, Root
  cause, Reproduction, Evidence, Boundaries, Novelty, Fix.
- `impact.md` starts at `## Impact`. It contains the full impact argument and severity rationale
  for platforms with a separate Impact field.
- Do not put `# Title`, `(paste this into the form)`, form-field notes, or author handles inside
  either file. Those belong in `metadata.json` or the package README.
- If the target is a vendor advisory with no separate Impact field, merge `impact.md` after
  Summary and keep the same wording. Do not duplicate it.

`metadata.json` example:

```json
{
  "title": "Missing redaction in persistAllKeyrings exposes GridPlus pairing credentials",
  "asset": "RabbyHub/Rabby",
  "cwe": "CWE-312",
  "cvss_version": "3.1",
  "cvss_vector": "CVSS:3.1/AV:L/AC:L/PR:L/UI:N/S:U/C:H/I:N/A:N",
  "cvss_score": 5.5,
  "severity": "medium",
  "affected_versions": ["rabby-extension 0.0.0"],
  "tested_versions": ["rabby-extension 0.0.0"],
  "commit": "c9ff0cc1a138b0deadc5ade5445a1b68ba43a8ba",
  "files": [
    "src/background/service/keyring/index.ts:57-60",
    "src/background/service/keyring/index.ts:964-992"
  ],
  "artifact": "report-package.zip",
  "artifact_hash_file": "artifact.sha256"
}
```

Do not claim a score in `metadata.json` that the prose does not match. If the platform computes
the score from a widget, put the vector and the computed result in the same record.

For a chain, add a `stages` array. It must contain the same IDs and count as the report's chain
overview, and the same IDs used in the stage walkthrough and evidence matrix:

```json
{
  "stages": [
    {"id": "S1", "primitive": "14-byte OOB write", "source_ref": "file.c:230",
     "marker": "S1", "control": "width below overflow threshold"},
    {"id": "S2", "primitive": "host memory read", "source_ref": "file.c:607",
     "marker": "S2", "control": "scanout reset to x=0"}
  ],
  "closed_at": "S2",
  "fragile_stage": "S2"
}
```

A mismatch between `metadata.stages`, the table, and the transcript is a package defect, not a
copyedit.

## PoC directory

The PoC is a small, boring, reproducible program. It is not a research notebook.

Required:

- `run.sh` (or one documented command) that a stranger can run without editing paths.
- Pinned dependencies: lockfile, exact versions, image digest, or commit.
- A `README.md` whose first 20 lines state affected version, one-command run, expected result,
  and cleanup.
- `expected-output.txt` copied from a clean run, not written by hand.
- The negative control or differential command.
- The pre-clean command for stale state.
- A note on every environment delta and what it masks.

Rules:

- No network access except the documented, pinned target and dependency source.
- No absolute local paths. Use relative paths from the package root.
- No interactive prompts.
- No credentials, cookies, tokens, signed URLs, or personal data.
- Do not ship `node_modules/`, `build/`, `.gradle/`, `target/`, `.venv/`, caches, or editor files.
- If the proof is nondeterministic, run it at least three times and report the rate. For a chain,
  report `n/N` per stage; a single global rate is not a chain rate.
- If the proof is a chain, ship one entry point per stage where the stage can be isolated, or the
  nearest observable, under `poc/stages/`. Add `evidence/reliability.txt` with the raw run
  counts.
- For a chain, split `## Requirements` into host, target runtime, and intermediate artifacts
  (guest kernel, container image, harness) with a digest or commit per plane.
- If the target must be patched to simulate an attacker, include the patch and say why the default
  masks the bug.
- If the proof changes host state, print the restore command before the irreversible act.

`poc/README.md` shape:

```markdown
# PoC: <short name>

Affected: <package@version, commit>
Primitive: <one line>
Demonstrated: <one line>
Not demonstrated: <one line>

## Requirements
- <OS, runtime, dependency source>

## Run
```sh
<one command>
```

Expected:
```text
<literal output>
```

## Control
```sh
<negative-control command>
```

## Stages
| Stage | Command | Success marker | n/N |
|---|---|---|---|
| S1 | `...` | `...` | 10/10 |
| S2 | `...` | `...` | 9/10 |

## Abort
```sh
<restore command>
```
<what a failed middle stage leaves behind; attempt cap>

## Cleanup
```sh
<undo command>
```
```

## Evidence directory

- `source-refs.md`: every file:line cited by the report, the symbol, and the observation.
- `verify-output.txt`: the raw output from the run that produced `expected-output.txt`.
- `hashes.txt`: SHA-256 of the PoC, inputs, and any generated payloads.
- If a piece of evidence is absent, say `absent` and what that means. Do not delete the slot.

The report may summarize this directory, but the package must contain it. A reviewer should not
have to reconstruct the proof from prose.

## Cleanup

`cleanup.md` records what the package creates, what it changes, and how to undo it. Use a radius:

| Radius | Meaning | Placement |
|---|---|---|
| process | killed when the process exits | one line in the PoC README |
| container | disposable Docker container/network | `## Cleanup` after the run |
| host | files, packages, accounts, kernel state | dedicated `## Cleanup` with undo command |
| persistent | survives reboot or affects another system | warning before the title |

For host or persistent effects, the undo command must be present before the proof runs. If the
proof cannot be undone by the acting identity, stop and obtain operator authorization.

## Zip hygiene

Create one top-level directory inside the zip:

```text
report-package/
  ...
```

Before zipping:

```sh
find report-package -name '.DS_Store' -delete
find report-package -name '*.pyc' -delete
find report-package -type d \( -name build -o -name .gradle -o -name node_modules -o -name target -o -name .venv \) -prune -exec rm -rf {} +
```

Then:

```sh
find report-package -type f -print0 | sort -z | xargs -0 shasum -a 256 > report-package/manifest.sha256
zip -r report-package.zip report-package
```

Do not include the zip inside itself. Do not include an absolute path in any script, log, or
manifest. Check the zip listing before upload; the first entry should be the top-level directory.

## Final package check

- [ ] `report.md`'s Description paste range begins at `## Summary`; `impact.md` starts at `## Impact`.
- [ ] No paste instructions, form-field notes, or internal paths in either.
- [ ] One command runs the fast path; expected output is verbatim.
- [ ] Control or differential is present.
- [ ] Tested environment and run count are present.
- [ ] `Will not work if` and environment deltas are present.
- [ ] Cleanup radius and undo command are present.
- [ ] Metadata matches the prose and the calculator.
- [ ] Zip has one top-level folder and no caches.
- [ ] `manifest.sha256` verifies before upload.

For a chain, also check:

- [ ] `metadata.stages[]`, `chain.md`, the report table, and the transcript use the same IDs and
      count.
- [ ] Every stage has a success marker findable in `expected-output.txt`; the order matches the
      stage IDs.
- [ ] `closed_at` equals the last proven stage; no title or summary claim goes past it.
- [ ] `evidence/reliability.txt` contains raw per-stage counts; no unquantified reliability.
- [ ] At least one intermediate stage has a local control; terminal control alone is labeled as
      terminal.
- [ ] Literal offsets or addresses are in the layout table and keyed to a build.
- [ ] A failed middle stage leaves a documented state and an abort/restore command.
