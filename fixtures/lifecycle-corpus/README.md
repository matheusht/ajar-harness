
## Why this fixture carries events.jsonl

It did not, until 2026-08-23. It held `attempts.jsonl` with no kernel -- an engagement that cannot
exist, because the kernel writes both. When gate `GK` (the record kernel ran before the work) was
added, this fixture blocked on `GK` as well as `G4`, and the conformance check that asserts "G4 is
what blocks here" went red.

The fix was to make the fixture FAITHFUL, not to carve GK out. A fixture shaped to the code rather
than to the world is the failure recorded in `docs/engineering/004-gate-block-audit.md` and in the
G4 corpus-arm defect before it. One minimal `scope.attested` row is what a real engagement always
has on day zero.
