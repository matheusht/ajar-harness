# Source SDK adapter: checks written before implementation

Status: full matrix specified, not executed. Four offline input contracts passed;
they do not qualify Docker, TLS, credentials, a provider or a target.

Decision: extend the native owner with a source-only profile. Keep the existing
service profile unchanged. Use three owned offline executors for the initial
command and two clean replays. A dummy listener cannot establish source execution.
Use the existing shared provider allowance and stop owner. Do not expose a paid
provider key to native tools, source, configuration, traces or receipts.

Affected paths: prepare and plan verification; CLI arguments; container creation
and manifest; startup probes; model selection and effective provider policy;
execution capture; fresh review; stop and interrupted-dispatch handling; docs.

Before any live target run, execute these checks on a synthetic Go module. Save
the exact commands, source and dependency manifests, image IDs, toolchain,
stdout/stderr hashes, exit status, receipt hashes and cleanup result. Then repeat
the authorized target workflow. Synthetic success is not target qualification.

| Failure condition | Required observation |
| --- | --- |
| Source mode still needs HTTP | Prepare without target port/command; start without listener or TCP probe |
| Missing/wrong Go binary | Startup refuses before research dispatch |
| Dependency closure absent or changed | Preparation/start refuses; no automatic download |
| Source or declared command changed | Plan verification refuses |
| Agent changes protected input | Executor sees only host-frozen inputs; reviewer replays the same digest |
| Ambient credentials/config/toolchain download | Clean environment, GOTOOLCHAIN=local, GOPROXY=off, no inherited host HOME |
| Code attempts DNS/TCP | Docker inspect reports network none; synthetic connection fails |
| Build exits nonzero | Host receipt preserves exit status and both output hashes; no success claim |
| Command hangs or output exceeds limit | Stop the run, retain unknown execution; do not retry silently |
| Owner dies during execution | Existing producer stop kills all executors; unfinished receipt stays unknown |
| Child process outlives command | Executor is paused before hashing; a second protected batch is refused |
| Workspace changes during capture | Freeze researcher/resume before copying; verify the captured manifest |
| Replay uses modified first-run tree | Each executor starts from its own pinned clean source copy |
| Replay differs | Record mismatch; never emit confirmed |
| Review packet lacks execution evidence | Explicit needs_review / independent check unavailable |
| Wrong paid model/provider/path | Refuse; no fallback to free model or another endpoint |
| Provider credential reaches agent | Synthetic canary absent from mounts, env, config, DB, trace and receipts |
| Gateway receives arbitrary method/path/model/header | Reject before upstream request |
| Redirect or malformed/chunked request | Refuse; do not forward credentials to another origin |
| Stop/allowance exhausted while gateway active | No new provider dispatch; connection closed |
| Existing application-service run | Existing preparation, service probe, captures and stop semantics unchanged |

Acceptance: one source command plus two fresh replays produce host receipts over
the same pinned inputs, with offline container identity and exact Go version.
Paid route acceptance additionally needs a real authorized model response, loaded
policy readback and credential-canary containment checks. Neither result alone
confirms a security finding. Dependency retrieval and live calls need their own
existing authorization; this change grants neither.
