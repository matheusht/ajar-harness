# T02 sealed capture to reviewer packet checks

These failure checks precede the opt-in source bridge. The existing harmless
managed run still has no protected original observation and must keep saying so.
The bridge accepts a caller-supplied sealed capture. Its source must separately
establish producer independence; this bridge does not collect one, enable a
provider, or qualify a native reviewer.

| Failure | Required check |
| --- | --- |
| Missing, extra, changed, noncanonical, or symlinked member of the four-file capture | Reject before writing any `/handoff` packet file. Recheck copied bytes against the sealed capture manifest and refuse source drift. |
| Caller supplies the wrong capture, source manifest, scenario/run identity, researcher session, or claim digest | Compare each independently supplied expected value with the sealed capture and actual research note. Reject a mismatch before publication. |
| Candidate PHP changes after the capture, or the sealed source manifest omits, adds, or stales a candidate file | Require the capture source manifest's file map to equal the exact three candidate PHP hashes that `RAW-APP-CHECKS.json` and `REQUEST.json` bind. Reject before writing `/handoff`. |
| Native researcher tool records omit `sessionID` or belong to a different session than the sealed capture | Compare every parsed native tool record's session ID to the capture's expected researcher session. Reject before writing `/handoff`; leave the ordinary no-capture path unchanged. |
| The capture scenario is self-consistent but belongs to a different current NativeRun | Require a separate host-controlled current run ID for the opt-in bridge and compare it with the capture scenario. Reject an absent or mismatched ID before writing `/handoff`. The normal managed call has no capture and needs no run ID. |
| Capture includes a secret or changes its host-replay, bypass, contrary, or unfinished classifications | Reuse the observation evaluator's strict sealed-capture validation. Copy the exact four files without editing them and retain its nonfinal status in `REQUEST.json`. |
| Capture is called terminal before stop, or described as a qualified native result | `REQUEST.json.original_observation` stays `unavailable`; its separate `capture_candidate` says `observation_capture_ready_not_finalized` and `caller_supplied_unqualified`. No review success is inferred from packet preparation. |
| Packet or bind root changes before or after review | Existing exact inventory, directory identity, read-only mount, and hash checks still fail closed. The request binds the capture manifest and each copied file. |
| Global stop, producer freeze, observer cleanup, or private scratch removal is unverified | Emit no finalization receipt. Finalization uses the evaluator's six closed cleanup categories and writes a separate receipt only after the caller supplies verified stop and cleanup projections. |
| The ordinary harmless runner is affected | Its packet still declares protected original observation unavailable and its existing owned checks pass without a capture argument. |

Acceptance is a no-Docker, no-provider owned check that constructs a synthetic
pre-review capture, challenges all failures above, and proves a linked separate
post-stop receipt. Run `python3 evals/native-qualification/smoke/check_v2_capture_review_bridge.py --output /absolute/absent/private-output` from the repository root. Expect `PASS` and a saved `result.json` with zero provider and target calls. It proves a source handoff only. A later managed run must
independently establish the real application's capture, exact process binding,
source bytes, native review, allowance, and cleanup before adoption.

No managed caller currently supplies both a sealed capture and its authoritative
NativeRun ID to this opt-in bridge. The synthetic check supplies a fixture ID;
the bridge is source-ready but not integrated into a real managed run.

The owned check supplies synthetic stop and cleanup projections. Its
`observation_capture_finalized` receipt has `qualification_scope` set to
`capture_lifecycle_only` and `review_status` set to `not_observed`; it is not
evidence that a managed run stopped or a reviewer performed a fresh check.
