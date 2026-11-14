# Actual Docker environment workflow

This scenario exercises the production `Environment` against an explicitly
selected local Docker daemon. It uses harmless source files, an owned loopback
listener and a short-lived child process. It makes no model or external target
request. The caller supplies an already installed exact image ID; the scenario
does not pull images, restart the daemon or remove preexisting resources.

The required observations were specified before changing production behavior:

- Missing authority creates no container.
- Actual staged bytes run as UID/GID 1000 with an immutable input and root
  filesystem, dropped capabilities, no new privileges, no Docker socket and no
  direct network interface or access to the host's loopback listener.
- Container readback matches the admitted memory, CPU and process bounds.
- Artifact publication returns bytes from the actual worker filesystem; staging
  preserves the supplied source.
- Revocation stops the owned container and its detached child. Reconstructing
  the environment from its receipt cleans only its container and derived image.
  The base image and preexisting containers remain.
- A second container has a four-second lease and a detached child. Killing its
  owned host watcher must still leave the container stopped within six seconds.
  The result records the fault and final readback; cleanup runs even if it remains
  active. This case must fail before correcting a watcher-only lease mechanism.

Use Python 3.11+ and Docker on a disposable Linux host. The image must include
`/bin/sh` and `/usr/local/bin/python3`. The CI workflow resolves
`python:3.11-slim-bookworm` to an exact installed image ID before running. Its JSON
retains the image ID and registry digest; reuse that digest for an exact repeat.

```sh
python3 evals/native-qualification/smoke/check_environment_docker_e2e.py \
  --endpoint unix:///var/run/docker.sock \
  --image-id sha256:REPLACE_WITH_INSTALLED_IMAGE_ID \
  --output /tmp/oslit-docker/result.json
```

Expected: exit zero, `status: passed`, every check passes, and all cleanup receipts
are `clean`. Failure retains the available observations and exact cleanup
identities. Cleanup runs on either outcome. An unresolved cleanup remains a
failure and requires inspection of that exact owned resource.

The [workflow](../../../../.github/workflows/oslit-environment.yml) runs on a
GitHub-hosted Ubuntu runner and uploads the result under the checked Git revision.
Adding the workflow is not evidence that it passed. No hosted result is recorded
in this initial scenario commit. This scenario does not qualify the native model
host, the joined controller workflow, SSH transport, a live provider or research
acceptance.

## Loopback SSH scenario

The same lifecycle scenario can reach the selected daemon through an owned SSH
listener on the same disposable Linux host. This exercises actual OpenSSH,
strict host-key pinning, the remote watcher and Docker transport. It does not
establish operation on a separate host or behavior during a network partition.
The fault kills the local SSH client; the result identifies that process
separately from the local-Docker case's host watcher.

```sh
bash evals/native-qualification/smoke/run_environment_loopback_ssh_e2e.sh \
  sha256:REPLACE_WITH_INSTALLED_IMAGE_ID /tmp/oslit-ssh
```

The host needs OpenSSH client/server, Docker, Python 3.11+, a nonroot user and
passwordless `sudo`. The fixture creates temporary keys and a loopback-only
listener; it changes no user SSH configuration. Expected: exit zero, all checks
in `ssh-result.json` pass, every environment cleanup is `clean`, and
`ssh-listener-cleanup.json` records `listener_stopped:true` and
`fixture_removed:true`. The listener and
temporary keys are removed on exit. An unverified listener stop fails the run
and retains its fixture directory for inspection. This is an executable
scenario specification; its hosted result must be recorded separately.

## Hosted observations on 14 November 2026

The [lifecycle run](https://github.com/matheusht/redteam-harness/actions/runs/43586543880)
at `41a0be16` passed all 21 checks and both cleanup readbacks. This includes actual
staging, filesystem/network restrictions, artifact publication, a detached child,
revocation and receipt-based cleanup. Earlier runs exposed a fixture error:
`docker top` requires the PID column. The corrected fixture requests `pid,args`
and retains the child-process assertion.

The [watcher-loss run](https://github.com/matheusht/redteam-harness/actions/runs/43586949490)
at `fd8674b1` passed 24 checks and failed the required lease-expiry check. The
owned watcher exited with `-SIGKILL`, but its container was still running after
6.0799 seconds despite a four-second lease. All three final cleanup readbacks
were clean. This is a reproduced production lifetime-control defect, not a
passing lease test. Container-local enforcement remains to be implemented and
verified after this checkpoint.

The [manifest](hosted-manifest.json) binds these saved JSON observations to their
hosted run, exact commit and source hashes. Both runs used Docker 28.0.4 on the
GitHub-hosted Ubuntu 24.04 runner with image
`python@sha256:a83ba18aef0f865b1a4a611c2cf460fe446f2795673bbb9fe43be570439e3b39`.
These observations do not establish SSH transport, native model containment,
the joined controller workflow, live provider behavior or research acceptance.

The [guardian run](https://github.com/matheusht/redteam-harness/actions/runs/43588193742)
at `3d0df8a2` passed the unchanged 25-check lifecycle/watcher scenario after
container-local lease enforcement was added. The killed watcher exited with
`-SIGKILL`; the next observed stopped container was 0.1657 seconds after the
fault. All three cleanup readbacks were clean. The separate guardian scenario
passed 30 checks, including actual root PID 1 with no effective capabilities,
nonroot worker isolation from its signal/control channel, adopted-child reaping,
separate worker/lease pipes and container stop on expiry. Its container was
removed and observed absent. The [guardian manifest](guardian-manifest.json)
binds both unchanged hosted receipts to their exact sources. These establish the
bounded lease fix; they do not establish a joined model workflow or research
acceptance.
