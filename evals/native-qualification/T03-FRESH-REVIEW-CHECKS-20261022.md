# T03 fresh native review: checks before implementation

22 October 2026. This is the #159 failure and E2E contract for a later managed
caller. No native review or unhinted application run is claimed here. Review is
needed before accepting a consequential claim or finally dismissing a material
lead as disproved or irrelevant. A lead explicitly deprioritized as **unfinished**
keeps its observation or reachable path, uncertain trust condition, and next
useful check; it needs no review before stopping. Do not create a reviewer turn
for every experiment, a fixed roster, or another allowance.

The existing [T02 capture bridge](T02-CAPTURE-REVIEW-BRIDGE-CHECKS-20261021.md)
validates a caller-supplied sealed capture and copies it into a fixed packet;
the [reviewer packet](T02-REVIEWER-PACKET-CHECKS-20261021.md) checks its read-only
mount and isolated native store. The managed caller in
`smoke/opencode_v2_managed_owned.py` still invokes the packet without a protected
capture or authoritative current run ID and uses a directed three-file PHP
exercise. Its owned responder cannot establish #159. The observation evaluator
in `experiments/native-observation-qualification/native_observation.py` validates
a capture projection; the caller must independently prove its source and process
origin. Keep the historical `T03-EXECUTABLE-HANDOFF-20261020/handoff.py` manifest
and empty actual-predecessor set as historical preparation, not a live input pin.

| Failure to inject or observe | Required result |
| --- | --- |
| Capture is absent, self-consistent but from another run/session/tool/claim/source, host replay is presented as the original test, or an application route bypasses observation | No original-effect claim and no review dispatch based on that capture. Bind the exact native dispatch, source and conditions to host-owned request/result/effect evidence; preserve the bypass or missing attribution as a limit. |
| A failed or contrary result, raw tool part, supported partial base, missing transition, or material lead basis is omitted or rewritten by the researcher | Refuse the packet or leave the affected conclusion unfinished. Freeze the actual claim version, raw ordered evidence and source conditions outside researcher write access; label operator help. A proposed relabeling cannot silently erase a distinct lead. |
| Reviewer shares researcher history/store or writable evidence, receives an answer/observer result, starts before packet freeze, or reads changed/extra packet bytes | No review dispatch. Preseal a fresh isolated context under the same NativeRun and allowance; verify only selected read-only source and packet mounts, empty native history, exact inventory, bind-root identity and hashes before and after review. |
| Reviewer supplies agreement or plausible tool prose but does not select and run a material causal/control check on a clean original application copy | No accepted review. Save its actual tool action and result, independently observed application effect and ordinary/causal control, and distinguish reviewer work from host-issued replay. A mock response remains plumbing evidence. |
| Review text, checked input, effect, or shared-allowance readback is missing; reviewer rejects one branch and drops another supported base or lead | Keep the affected work open. Save the reviewer's own conclusion and limits with session/context identity, exact packet/claim/source versions, files examined, check, host effect/control, assistance and shared-ledger usage; record unavailable provider cost as unavailable, not zero. |
| Source, claim, conditions, raw evidence, packet, or reviewer conclusion changes after review | Mark the affected review and dependent current conclusion stale. Retain the old reviewed bytes and valid observations; require a fresh bound review before accepting the changed conclusion. A prepared prior request is not a prior review. |
| User stop, deadline, or shared cap arrives before or during review | Stop new dispatch through the existing run boundary, preserve charged/in-flight usage and the lead as unfinished, and report review unavailable. Do not reset the pool, block stopping, or say the target is safe. |
| Packet, trace, or final artifact includes credentials, cookies, signed URLs, private key, capability, sensitive raw body, or host-only path; cleanup cannot prove exact owned resources stopped | Refuse retention of sensitive bytes, preserve only redacted diagnostic evidence, and leave final qualification unavailable until redaction and verified stop/cleanup. |

Use material unrelated to the hidden first research case for setup checks. The
existing public no-provider commands, from the repository root, are:

```sh
python3 experiments/native-review-qualification/T03-EXECUTABLE-HANDOFF-20261020/check_handoff.py
PYTHONDONTWRITEBYTECODE=1 python3 evals/native-qualification/smoke/check_v2_capture_review_bridge.py --output /absolute/absent/private-output
```

Both prepare or challenge synthetic bytes; neither performs native review. The
Docker-only `check_v2_reviewer_packet.py --output <new-private-dir> --image
<local-image-with-sh>` checks the mount, not inference. If the existing T06
strong-lead fixture is used for a native challenge, keep its
`AFTER-DROP-CHECK.json` observer-only: the historical handoff manifest currently
includes that outcome. Do not leak it to the reviewer or the later unhinted
researcher.

The first owned offline E2E freezes an answer-free synthetic claim and packet,
then challenges claim, source-byte, source-inventory and packet drift and a stop
before packet/review. It was written before the runner change. From the
repository root, create a unique private output directory:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 evals/native-qualification/smoke/check_t03_review_input_lifetime.py --output "/tmp/t03-review-input-lifetime-$(date +%s)-$$"
```

Expected: `PASS` and `result.json` with all checks true, `provider_calls: 0`
and `target_calls: 0`. Observed on 22 October 2026 at
`/tmp/t03-review-input-lifetime-20261022c`: PASS. The input gate rejects current
project files or note that differ from the frozen packet, changed project
inventory, absent packet, and mutated packet. The managed runner calls it after
its verified stop.
This only proves an owned input-lifetime boundary. It does not establish a
reviewer judgment, complete raw evidence, or an original application effect.

Later, after #158 and the provider/route hold clear, run one bounded unhinted application workflow:
fresh ordinary researcher input, protected original effect, clean original replay
and controls, one fresh reviewer-selected material check under the same allowance,
actual conclusion/version, #160 pause/resume, and exact cleanup.
Save the runnable command, frozen inputs, environment, expected/actual result,
native and host traces, cost/help, unfinished work and redacted output. If that
run produces no consequential claim or material dismissal, report #159 unobserved
and use a separate bounded native challenge; do not manufacture a claim.
