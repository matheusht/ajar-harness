# Native request diagnostic observation

The [second hosted attempt](https://github.com/matheusht/redteam-harness/actions/runs/43593621942)
at `72c9f353eeb06d5ed7291008bec707b492d00fcb` passed image packaging but failed
before a native session became ready. Original [Codex](codex-hosted-before.json)
and [OMP](omp-hosted-before.json) result bytes are retained, from jobs
`132443387968` and `132443387853` respectively.

Codex allocated the actual separate model and tool containers, then returned
`native_request_rejected`. Its cleanup verified both owners removed and the model
process/children absent. No provider request occurred. OMP stopped earlier with
`native_bundle_platform_unavailable` from the production tool installer; its
owned image/probe cleanup was clean. These are failed native workflow attempts.

The Linux engineering driver now observes Codex transport rejections through a
subclass of the unchanged production transport. It delegates all request and
receive behavior, records only operation names and error bodies, applies the
existing publication filter plus the fixture credential as a known secret, and
retains at most eight diagnostics of 2,048 characters each. It never retains
request parameters or changes responses, dispatch, permissions or cleanup.
The original transport binding is restored in the driver cleanup path.

The [failure-first scenario](diagnostic-e2e.py) sends requests to an actual inert
JSONL subprocess. Safe, sensitive, known-secret, oversized and successful replies
all failed before the observation helper existed and pass afterward. The
[before](before.json) and [after](after.json) receipts concern these five diagnostic
cases only; neither a native runtime nor Docker or an external provider ran.

Repeat from the repository root:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 evals/native-qualification/team-evidence/linux-native-request-diagnostics-20261114/diagnostic-e2e.py \
  --source evals/native-qualification/smoke/check_linux_model_native_e2e.py \
  --output /tmp/native-rejection-diagnostics.json
```

Expected: five passing checks, unchanged successful result or stable rejection
code, bounded safe error details, and no request parameter or synthetic secret in
the observations. The next actual hosted run must identify the Codex rejection;
this observer does not repair or qualify native startup.
