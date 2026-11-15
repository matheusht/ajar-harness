# Actual Docker application reset

[Hosted run 43595436761](https://github.com/matheusht/redteam-harness/actions/runs/43595436761),
Docker job `132448803842` at `9bd4b6b5`, passed all nine application-owner checks.
The owned counter returned 0, then 1 after mutation, and stayed 1. Recreating it
from the pinned baseline produced a different container and nonce returning 0.
Wrong-origin access was rejected, revocation prevented a new connection, and
reopened cleanup removed the exact target and derived image after authority ended.
The supplied base image and all preexisting containers remained.

The original [result](hosted-application.json) is preserved byte for byte.
The [manifest](hosted-manifest.json) binds it to the run and seven source files.
Repeat with the explicit installed-image command in
[APPLICATION-RESET-SCENARIOS.md](../../APPLICATION-RESET-SCENARIOS.md).
This is actual owned Docker/HTTP lifecycle evidence. The signed controller/reviewer
workflow was checked separately with simulated native/container peers. The joined
Codex/OMP capture path, separate SSH host and research acceptance remain unverified.
The native jobs in this same run failed; the Docker success does not qualify them.
