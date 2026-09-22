# Communication v3 pre-implementation failure matrix

| Failure | Required check |
|---|---|
| Source bytes drift | Verify the frozen manifest before the first call and after the last call. |
| Direct and board workers differ | Generate two independent notes once per case and deliver those exact note bytes to both arms. |
| Peers influence initial notes | Each worker sees one source only; both observations are complete before any notice is posted or forwarded. |
| Coordinator already has all primary sources | Direct and board final synthesizers receive only worker notices; serial alone receives all released primary sources. |
| Late correction is only claimed | Save a pre-correction draft for all three arms, post a predecessor-linked board correction, forward the same correction content directly, then save post-correction finals. |
| Board receipt is confused with use | Record projection receipt mechanically and grade use of released facts separately. |
| Direct gets fewer forwarding opportunities | Match empty read, initial sends, correction send, and final receive at the same logical ordinals. |
| Board bypasses canonical storage | Use the signed record kernel, `post_notice`, reduction, and `compile_hunter_notices`; save the ledger and compiled projection. |
| Grader calibration only echoes fields | Grade explicit correct, wrong, and ambiguous samples; require exact hidden gold labels before grading candidates. |
| Grader sees treatment labels | Save a private mapping separately and provide only anonymized outputs plus the current-case reference. |
| A failed call is favorably rerun | Retain the first call, stop qualification where required, and never rerun a candidate or grader. |
| Budget is exceeded | Reserve before every call against study and aggregate ceilings; unknown usage stops the run. |

