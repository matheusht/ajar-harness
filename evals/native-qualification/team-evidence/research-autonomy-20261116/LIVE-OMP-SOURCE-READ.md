# Live OMP source-read observation

On commit `d075ca29219c9a961755f8960dd131cddeb1c4f2`, one bounded direct-boundary
run used a signed, harmless owned-source fixture, OMP 18.20.0 on macOS, a pinned
Linux ARM64 tool bundle and Docker lab, and Mistral `mistral-small-2603`. The
provider's authenticated model-list response and the pinned OMP catalog both
listed that model with function calling before the run. The actual OMP `read`
tool returned the fixture's expected source marker, the native turn completed,
and owned cleanup was verified. The [unaltered redacted receipt](live-omp-source-read-result.json)
has SHA-256 `287db8fbba6da28886fddf5d5362b952e345a654b9db55087b468e4aa69fc491`.

The receipt's `provider_calls: not_observed` was a static initial field that the
private scenario did not update. It is superseded for this observation by its
separately recorded three upstream HTTP 200 responses and three started provider
requests. The journal snapshot recorded two requests completed; it does not prove
all three accounting records had settled. No provider body, model text or
credential value is retained in the receipt.

This was one live-model source-read smoke through `NativeBoundary`; it did not
exercise the public Runner, helpers, independent review, closure or research
qualification. The complete original private scenario is
`/private/tmp/oslit-autonomy-e2e-20261116/live-smoke-9-source.py`, SHA-256
`96d6cfded19d85581a6c9031abec125faad80f08b42a4327d6126c16b6ad8d6c`.
The private discovery receipt has SHA-256
`20210be58bc3369226d3848b58ce159721ade742daa8beb2172f4a2b69629334`.

To repeat in this prepared environment, create a fresh scenario copy with a new
run suffix; this creates and signs a new owned fixture, and makes live provider
requests. Requirements are Python 3 with the private CI virtual environment,
`ssh-keygen`, OpenSSL, Docker Desktop, the retained pinned OMP Darwin executable,
ARM64 tool bundle and protocol schema under `/private/tmp/oslit-autonomy-e2e-20261116`,
the pinned base image ID, and a usable Mistral `omp_default` credential reference.
The scenario keeps its generated fixture and result in that private directory.
The original `-9` path is retained and must not be overwritten.

```sh
python3 - <<'PY'
from pathlib import Path
base = Path('/private/tmp/oslit-autonomy-e2e-20261116')
source = (base / 'live-smoke-9-source.py').read_text()
source = source.replace("root=base/('live-'+runtime+'-9')", "root=base/('live-'+runtime+'-replay-1')")
source = source.replace("output=base/'results'/('live-'+runtime+'-9.json')", "output=base/'results'/('live-'+runtime+'-replay-1.json')")
(base / 'live-smoke-replay.py').write_text(source)
PY
/private/tmp/oslit-autonomy-e2e-20261116/venv/bin/python \
  /private/tmp/oslit-autonomy-e2e-20261116/live-smoke-replay.py omp
```

Expected result: `native_completion` is `completed`, `native_tool_names` includes
`read`, `fixture_source_observed` is true, and `cleanup` is `verified`. A refusal,
provider error, missing marker or unresolved cleanup is a failed or incomplete run.
