# Native worker boundary composition

`tools/engagement_native_boundary.py` connects the engagement runner to the native
Codex/OMP adapters, the owned research environment, separate provider and worker
network gates, and protected evidence capture. It implements the v2 engineering
plan. These results establish local composition mechanics, not qualification or
research acceptance. No research target or external provider was contacted.

## Ownership and lifecycle

`NativeBoundary(context)` has no execution effects. It selects an environment
whose signed capabilities and platform fit the worker grant, and whose signed
effect covers that environment and every requested resource. It retains the raw
profile identity; a frozen SSH known-hosts path is only a transport override.

`start()` stages the signed native tool bundle and public bootstrap material in
the environment. Provider credentials stay in the host model binding. Model
traffic crosses the provider gate; uncredentialed tool traffic crosses the worker
gate and receives only acquisition routes plus the application's granted target
routes. Provider routes are excluded from the tool gate. Application account
references currently return `target_account_binding_unavailable`; the caller must
report the missing binding rather than reuse provider credentials.

Codex bridge and model process owners are recorded before readiness waits. The
journal retains all startup receipts and verifies that later receipts preserve
earlier process identities. A constructor failure can therefore recover the
exact recorded owner before a native session exists. `renew(seconds)` renews the
owned environment against the runner's latest controller grant.

`finish()` revokes new authority, cancels any auxiliary capture, closes gates and
native transports, and observes runtime stop plus exact environment cleanup.
Cleanup failures remain unresolved and retain unknown resource state. Recovery
uses frozen owner identities and the dispatch's recorded environment nonces;
missing identity never becomes a claim that no process ran. A preflight failure
returns `execution_admitted: false` only when it never reached Environment.prepare;
the controller's explicit cancellation record must settle this case separately.

## Native tools and captured experiments

Every native host-tool admission returns the runtime's `HostOperation` contract.
Status, typed submission and frozen-object reads have completed responses;
artifact reads and captures run asynchronously with cancellation. Reads require a
journal reference in `evidence_objects`; knowing an unpublished object digest does
not expose its bytes. Reads return byte ranges of at most 64 KiB with total size,
encoding and next-offset metadata. Status reduces its entry count to fit the
complete native response. A single larger entry becomes a clearly marked
`ephemeral_read_view`, held only in memory for the current worker. It is capped
at 4 MiB, has its own digest, and is replaced by the next status call. Chunked reads
can resolve that current view; it is not a publication or accepted evidence
reference, and no journal or object-store file is written. `engagement_artifact` freezes a bounded actual file at a path
relative to `/work` and creates an immutable host publication file.

`engagement_capture` reserves a separate auxiliary environment. It reads the
actual probe and candidate files, freezes their exact bytes with the registered
instrument, and runs the pinned probe directly or with an allowed named
interpreter. The instrument, candidate and subject paths are explicit arguments;
there is no host-selected shell command string. Source/binary captures start in a
fresh private environment. Application capture needs an actual reset mechanism
and is not claimed here.

Patch arms execute against `/input/patch-source`. Staging preserves exact frozen
paths, bytes and sizes and derives read-only modes 0444/0555. The evidence binding
accepts only that exact derivation; before/after inspection of a mutable working
tree is not used as execution proof.

The requested capture duration is distinct from its short reservation lease.
The boundary renews both the controller reservation and environment owner while
work continues, within the parent's current authority and signed budget. Each
operation retains its original admitted grant for late results; settlement uses
the latest reservation. Cancellation of an unstarted capture releases its known
unused reservation without revoking the parent worker. Certificates cover the
signed finite worker-seconds budget plus one day of clock margin, rather than
introducing an independent two-day runtime cutoff.

## Repeatable checks

Run on macOS with Python 3, `ssh-keygen`, `openssl` and `sandbox-exec`:

```sh
python3 evals/native-qualification/smoke/check_engagement_native_boundary_e2e.py --output /tmp/native-boundary.json
python3 evals/native-qualification/smoke/check_environment_renewed_execute_e2e.py --output /tmp/renewed-environment.json
```

Expected: both commands exit zero. The first reports all 20 scenarios passed; the
second reports all five scenarios passed. `after.json` and
`environment-integration.json` retain the exact exercised source digests. The
`before-*.json` receipts preserve failures observed before the corresponding
implementation or repair. They are intentionally not all from one historical
snapshot.

The boundary check uses real signed disposable inputs, journal/object storage,
actual local certificates, the macOS host network sandbox and a real local probe
process. Environment/native peers are explicitly simulated. It exercises the
real shared native host-tool admission implementation for status, submission and
publication reads. Additional tests use actual Codex/OMP reply handlers and
Transport.send to reassemble large text/binary objects, deliver multilingual and
escaped status pages, and expire a temporary read view. The single oversized
status-entry case uses an explicit host status fixture; normal directions and
paging use the real journal. The renewable environment workflow uses a named simulated
Docker CLI and the actual local process lease owner. Local temporary inputs are
removed by the scenarios; output receipts contain no credentials.

## Limits of this evidence

No Docker daemon, remote SSH execution, external provider inference, real target,
multiday soak or research acceptance was exercised by this artifact. The
four-second probe crossing short leases and a five-day certificate end-date check
are mechanics checks, not a five-day run. Production startup also requires the
portable `engine/native-engagement-method.md` supplied by the integrated runner;
the boundary scenario substitutes fixture methodology text.

The macOS policy check establishes selected outbound ports, refusal of another
outbound port, and the local listener permission needed by Codex. It does not
establish confinement of listener interfaces: the platform's localhost policy
also accepted a connection through another address on the same host in an
exploratory check. Tool execution still requires the Docker network-none
boundary; there is no uncontained host-tool fallback. Native Linux/Docker/SSH
containment must be qualified on the intended environment before adoption.
