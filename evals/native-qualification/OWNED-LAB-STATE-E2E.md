# Owned lab state first-creation workflow

These failure cases precede implementation. `owned-lab-state-v1` explicitly
identifies one exact disposable lab instance and its writable namespace/filesystem
state as the artifact. It does not count each generated file or classify content.
The current artifact/operator gates remain active; all scenarios use inert bytes.

The contained executable workflow uses signed disposable inputs, the actual immutable
controller journal, existing boundary/runner fixtures and an opt-in actual Docker
route. It must distinguish simulated environment observations from actual Linux
mount/readback evidence. It must not use a live model provider or research target.

Failure-first matrix:

1. Persist the signed artifact intent before stage/main allocation and before
   native writes. Record readiness only after exact owner and storage readback.
   Native tools create inert files inside that already registered lab artifact.
2. Reject missing/unknown/ambiguous classes, wrong environment/resources,
   account/application resources, absent cleanup authority and unsupported rungs.
   Creation permission alone cannot start native tools or execute a probe.
3. Inventory `/work`, `/tmp`, `/dev/shm`, `/dev/pts`, `/dev/mqueue` and all other
   Docker-provided ephemeral/kernel mounts. Reject host/shared IPC/PID, devices,
   extra mounts, unbounded shared memory and writable host-control surfaces.
4. Interrupt after intent, stage create response loss, input-image creation,
   readiness and first native write. Reopen exact ownership; retain uncertainty.
5. Require container, stage, prepared-image and registered host-staging absence
   before releasing resources. Environment cleanup plus failed host staging
   cleanup remains held. Retry is idempotent and preserves unrelated data.
6. Renew and retain a specialist on the same artifact without new authority or
   allowance. Revocation denies new work; cleanup remains available after expiry.
   A replacement generation cannot replace the old artifact owner.
7. Reject worker-created readiness/cleanup claims and changed class/config/nonce
   or foreign dispatch receipts. Later publication cannot invent creation history.
8. Report lab-state artifact count, pending cleanup and retained immutable evidence
   separately. Preserve supplied originals and make no per-file creation claim.
9. Preserve main startup, source/patch capture, setup-only recovery, specialist
   retention and old records without this class. Application reset remains a
   separate mechanism and does not obtain authority from this artifact class.

The opt-in actual Docker workflow must run the production Environment on an
explicit already-installed image and local endpoint, retain the observed mount
inventory, create harmless bytes in each admitted storage area, revoke the owned
instance and verify exact complete cleanup. No image download or local Docker
operation is part of the default contained run.

## Run the contained workflow

Requires Python 3.11+, OpenSSH `ssh-keygen` and OpenSSL. From the repository root:

```sh
python3 evals/native-qualification/smoke/check_owned_lab_state_e2e.py \
  --output /tmp/owned-lab-state-contained.json
```

Expected: `passed:true` for all 14 families. The interruption family includes
seven distinct loss windows: initial intent, stage response, image response,
before readiness, after readiness, after a native operation and cleanup response
loss with exact retry. Signed inputs, journal replay, controller admission,
boundary capture/recovery, local capture subprocesses and host staging are real.
Container/model owners and mount/configuration observations are simulated.
The original failure-first run precedes production changes and records the
missing lifecycle. Later counterexamples retain the reconciliation-release and
intent-retry failures separately from the final passing result.

## Opt-in physical Linux workflow

Use only an explicitly authorized disposable Linux Docker endpoint and an
already-installed exact Linux image ID with `/bin/sh`, `/usr/local/bin/python3`,
standard `ctypes` and POSIX message-queue support. The command neither downloads
an image nor contacts a provider/target. The current controller/signature scenario
is covered separately above; this command verifies the production Environment:

```sh
python3 evals/native-qualification/smoke/check_environment_docker_e2e.py \
  --endpoint unix:///var/run/docker.sock \
  --image-id sha256:REPLACE_WITH_ALREADY_INSTALLED_IMAGE_ID \
  --owned-lab-state --output /tmp/owned-lab-state-linux.json
```

Expected: every check passes, both saved storage inventories name the exact
container, inert writes succeed in `/work`, `/tmp`, `/dev/shm`, private PTY and
private message queue, originals stay unchanged, revocation and watcher loss stop
descendants, and all owned containers/images are absent. The base image and all
preexisting containers remain. The JSON includes observed configuration, mount
inventory, loss/recovery facts and source digests. A failed or missing result
leaves physical Linux support unqualified. No physical run is claimed by the
contained receipt.
