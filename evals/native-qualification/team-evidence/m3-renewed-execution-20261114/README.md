# Execute across renewed short leases

Environment.execute(argv, timeout_seconds=...) now keeps the explicit operation
wall-clock deadline while the owner and controller grant renew independently.
It checks the current controller authorization during each bounded output poll.
Renewal does not extend the requested operation timeout. Expiry, revocation or
output overflow stops the local transport and records an unknown effect; the
independent owner and ordinary cleanup still own stopping the exact container.

Callers must renew both the controller reservation and Environment.renew before
expiry. The authorize callback must return the current grant or remaining time;
a longer execute timeout does not itself renew authority or resource allowance.
The public method signature is unchanged. Setup and cleanup command deadlines
retain their existing bounds.

The failure-first workflow before.json records premature interruption despite five
owner renewals, and delayed response to controller revocation. All five scenarios
passed after the repair: renewed execution, controller expiry, revocation, explicit
operation timeout, and independent owner expiry while the controller stays valid.
The 22 existing transport and 28 workspace-readback controls also passed.

Repeat from an integrated checkout with Python 3 and local process/filesystem access:

```sh
python3 evals/native-qualification/smoke/check_environment_renewed_execute_e2e.py --output /tmp/renewed-execution.json
python3 evals/native-qualification/smoke/check_environment_transport_e2e.py --output /tmp/environment-transport.json
python3 evals/native-qualification/smoke/check_environment_workspace_e2e.py --output /tmp/environment-workspace.json
```

Expect exit zero and status passed. This isolated environment branch used
PYTHONPATH pointing to the coordinator checkout tools directory for its existing
engagement_contract dependency. Integration must rerun in one tree. The fixture
uses a named simulated Docker CLI, actual local processes/clocks/files, and the
real independent process lease owner. No Docker daemon, SSH host, provider or
research target is contacted. Native containment and remote behavior remain
unverified; these results establish the command/lease workflow only.
