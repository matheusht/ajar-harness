# Retained offline evaluation checks

Evidence for [the evaluation research note](../../evaluation.md), inspected at commit `6a47b64264b6bf8f1edf8923847cfc9952cd1ab8`. These are characterizations of existing behavior, including invalid inputs that receive favorable verdicts. Passing them does not demonstrate a repair, eligible experimental results, or harness efficacy.

## Reproduce the bounded checks

From the repository root, use an existing Python environment with `jsonschema` installed:

```sh
PYTHONDONTWRITEBYTECODE=1 python docs/research/harness-engineering-2026-09-05/checks/evaluation/probes.py
```

An optional positional argument selects a different repository checkout. [probes.py](probes.py) creates a new OS temporary directory, prints its path, and writes generated metadata, logs and `results.json` there. It does not overwrite the retained evidence. Exit 0 means all characterizations match the current assertions; a later repair should change some of these outcomes.

The script runs the public Q02 `measure`/`verdict` commands and Q02 self-test. Its measurement fixture contains only three empty coordination locks, three text-note folders, a minimal unreviewed revision object, and prose budget/use numbers. There is no valid ledger or target input. Its flow checks call only `normalize_generic`, `_coverage` and the conservative research `_sum_cost` helper. The small aggregation in the script mirrors four inspected export reductions; it does not exercise export source binding, the reducer or public flow export. No kernel initialization, lifecycle action, target, model/provider or network call is invoked by this reproducer.

## Evidence and coverage

| Artifact | What it retains |
|---|---|
| [canonical/results.json](canonical/results.json) and neighboring inputs/logs | Original batch: 15 synthetic characterization cases, Q02's 26 self-test assertions and flow's seven self-test assertions. Exact executable, arguments, source hashes and observed outcomes are retained. |
| [reproduction-results.json](reproduction-results.json) and [reproduction-logs.json](reproduction-logs.json) | One validation of the retained narrower script: 16 checks held. This includes Q02's self-test, 12 public Q02 cases, and three pure accounting-helper cases. Flow self-test/export were not repeated. |
| [source-hashes.json](source-hashes.json) | Original principal-module hashes, pinned commit and verification against that commit. The reproduction manifest also records hashes of loaded local Python files. |
| [retention.json](retention.json) | SHA-256 for every canonical file, omitted-directory inventory, and original synthetic bootstrap record counts/hashes. |
| [canonical/original-probes.py.txt](canonical/original-probes.py.txt) | Original executed script bytes, retained as non-entrypoint provenance. The supported reproduction command above uses the narrower `probes.py`. |

Original top-level evidence files were copied byte-for-byte; the original script was only renamed with a `.txt` suffix. Absolute paths in original logs identify the original run and are not links to required retained inputs. The generated measurement folders can be recreated by `probes.py`; they were not copied. Neither repeated characterization nor validation of a revised reproducer supplies an independent efficacy sample.

The **original** flow self-test and public-export checks did initialize a minimal, isolated synthetic record kernel. The export fixture contained one `scope.attested` event, zero attempts and zero artifacts. That was more than creating empty locks. It involved fabricated local metadata and no target, provider or model work. Generated scope attestations, ledgers, snapshots, views and other bootstrap scaffolding are omitted. The original flow CLI results remain observed historical evidence; the retained default command reproduces only the narrower helper semantics. Re-executing the original text archive is outside this command and its coverage claim.

Both batches used Python 3.14.6 and jsonschema 4.26.0. No broad conformance/quarantine suite, historical comparison recomputation, intervention fixture or target workflow was run for this retention step. Production files were not modified.
