# Native stop-reason projection checks

Declared before the source change on 2026-10-22 for issue #169. The public
`status` output currently omits the first recorded stop trigger, although the
private native control already keeps it in `controls/native-state/STOP_REQUEST`.
Expose that observation without creating another lifecycle or changing stop,
cleanup, coverage, review, or authority decisions.

## Failure checks before implementation

- Public status, the final start receipt, and recovery expose `stop_reason`.
  Supported fixed native codes are preserved; no stop request yields JSON null.
- `STOP_REQUEST` wins over later `STOPPING` and old final/recovery displays.
  Do not infer a reason from deadlines, allowance, or a terminal status.
- Malformed JSON, duplicate keys, wrong fields or types, invalid/nonfinite/boolean
  monotonic values, over-32-KiB files, nonprivate files, symlinks, FIFOs, and
  directories yield the fixed `stop_reason_unavailable` code.
- A well-formed custom reason yields `stop_reason_unrecognized`; arbitrary
  reason text, credentials, paths, and exception text never enter this field.
- Read-only status preserves every file's bytes, mode and modification time,
  and does not create a control file or lock. Missing or invalid reasons cannot
  manufacture a successful user/budget stop, cleanup, coverage, or safety claim.
- Old receipts without the additive field remain readable. Startup failure and
  recovery keep their existing status and cleanup behavior.

## Focused check

Run `PYTHONDONTWRITEBYTECODE=1 python3
 evals/native-qualification/smoke/check_native_stop_reason.py --output
 /absolute/private/result.json` as one command from the repository root.
The script uses private synthetic roots through the public status CLI and
stubs runtime/cleanup boundaries for final/recovery caller checks. It executes
no native runtime, Docker, provider, or target. Expected: `PASS`, fixed reason
codes, unchanged inspection inputs, and zero runtime calls in the saved result.
These checks establish source behavior only, not E2E or native qualification.
