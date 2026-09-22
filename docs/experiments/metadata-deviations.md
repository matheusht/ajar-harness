# Research metadata deviations

- `framing-v1`, `communication-v2`, and `recovery-v2` contain a
  `frozen_at` value of `2026-09-22T18:00:00Z`. Git records their protocol
  commit at `2026-09-22T14:46:26Z`, and inference began before 18:00Z. The
  timestamp was synthetic future metadata and is not evidence of a real
  preregistration boundary. Those outputs are retained as development or
  exploratory evidence and are not acceptance studies.
- Framing v2 records the actual clock before its freeze commit. Its manifest
  binds the executable runner, runtime config, fixtures, rubric, protocol, and
  failure matrix before candidate inference.
