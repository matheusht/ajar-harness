# Owned lab state lifecycle — 14 November 2026

This candidate implements one explicitly signed `owned-lab-state-v1` artifact per
owned disposable source/binary lab. It records intent before allocation, verified
owner/configuration/storage readiness before native tools, and complete cleanup
before settlement or resource release. The artifact is the whole lab instance;
no per-file creation or semantic-safety claim is made. Current operator gates
remain active. Application reset and credentialed model ownership stay separate.

## Observed checks

- `failure-first.json`: the executable matrix existed before production edits;
  12 unsupported class/lifecycle families failed, and the no-class workflow passed.
- `reconciliation-before.json`: a pending artifact could still release its hold
  through resource reconciliation. The final controller requires full cleanup.
- `intent-retry-before.json`: exact intent retry failed after owner IDs evolved.
  The final transition is idempotent without re-creating authority.
- `contained-final.json`: all 14 families pass, including seven interruption
  paths, real journal reopen, main/capture ordering, separate execution authority,
  host staging inode/foreign-content checks, exact cleanup retry and retained
  specialist continuity. Container/model owners and their physical observations
  are simulated; signed inputs, controller, boundary and host staging are real.
- Existing adjacent workflows pass: boundary 23, preparation recovery 11,
  retained specialist 26, source capture 6, contract 75. Their source pins remain
  in the original JSON; `manifest.json` identifies the final candidate sources.

The default interpreter lacked the legacy `jsonschema==4.26.0` dependency, so its
structural run failed before completion. The existing pinned conformance virtual
environment produced `conformance.json` and `conformance.txt`: 900 checks, zero
failures. No package was installed. Final native class/boundary refinements are
covered by their separate final workflow receipts.

## Repeat and limits

Commands, inputs, expected results and the explicit physical Linux route are in
[OWNED-LAB-STATE-E2E.md](../../OWNED-LAB-STATE-E2E.md). The latter now supports
`check_environment_docker_e2e.py --owned-lab-state`; it saves actual mount and
configuration readback, writes inert state in the file stores, creates private
PTY/message-queue state, exercises revocation/owner loss and verifies complete
owned container/image absence. That command has **not been executed for this
candidate**. Simulated inventories do not establish Linux or SSH containment.

No provider, Docker, SSH, fresh-target research, impact payload, disclosure or
policy adoption occurred in this contained verification. These receipts do not
establish research quality or integrated acceptance. Root integration must preserve
the independent application lifecycle changes and obtain exact-snapshot review.
