# Task-local observation board v1

Implemented 2026-09-22 as an optional notebook projection. It reuses authenticated
`observation.recorded` events; it is not another truth store, assignment queue, memory system, or
authority path.

## Failure contract

Before implementation, the E2E check fixed these failures:

- a notice without two distinct prior independent observations is rejected;
- the task must resolve to a prior `task_definition` observation in the same engagement;
- the source event must be prior, belong to that task, match the named source revision, and be
  authored by the named principal;
- the recorder principal is derived from the local broker process rather than CLI actor labels;
- extra/hidden fields, authority-shaped fields, cross-task sources, duplicate IDs, unknown
  predecessors, and more than five retained notices are rejected without a ledger write;
- corrections cite the predecessor event ID and retain both rows;
- the generic `append-event` command cannot post a notice;
- reads first reduce the authoritative ledger and return only the requested task and sequence range.

## Public workflow

Create the task boundary and two independent initial observations through the existing notebook
writer. Each source observation carries the same `task_id` plus its exact `source_revision`. Then:

```sh
python3 tools/task_board.py post \
  --engagement engagements/ID --notice notice.json \
  --recorded-at 2026-09-22T12:00:03Z
python3 tools/task_board.py read \
  --engagement engagements/ID --task-id TASK --after-sequence 0
python3 tools/task-board-test.py
```

The projection proves retention and read opportunity only. A notice remains advisory: it cannot
grant permission, settle a claim, assert completion, or enter portable memory. Source checking,
correct use, and practical benefit remain separate observations.
