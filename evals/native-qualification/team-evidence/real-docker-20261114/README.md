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
