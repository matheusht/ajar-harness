# Recovery v3 pre-implementation failure matrix

| Failure | Required check |
|---|---|
| Baseline arguments are invented | Baseline rows contain no received arguments and name zero invoked recovery interfaces when source inspection finds none. |
| Approval is mislabeled as cooperative cancellation | Cooperative pause must call streamed `cancel(mode="after_turn")` after a real tool output and resume a serialized `RunState`. |
| Correction is present from the first turn | First input contains v1 only; v2 is staged with `RunState.add_input()` after soft cancellation and must appear once in the next recorded model input. |
| Pause loses or repeats completed phase work | The phase-one tool effect count is one before and after restore/resume. |
| Lost receipt is simulated after model receipt | The local file append occurs before the tool returns; the first attempt raises a `BaseException`, so no function-call output enters a completed state. |
| Retry is claimed exactly once | Restore the same pre-effect snapshot, retry, record two physical file appends, and label exactly-once false. |
| Serialization is assumed | Save actual `RunState.to_json()` payloads, restore them with `RunState.from_json()`, and record SHA-256. |
| SDK drift changes behavior | Require exact SDK commit and lock hash before execution. |
| Trace export leaks data | Use `RunConfig(tracing_disabled=True)` and record it. |
