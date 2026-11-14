# Frozen SSH host-key reference

`Environment(..., known_hosts_file=frozen_path)` optionally selects a host-owned
transport reference for an ssh-docker environment. The signed `profile` remains
unchanged, including its original path and digest. Every SSH launch bound-reads the
selected file, refuses symlinks/changed bytes, verifies the existing signed
known_hosts_sha256, and passes that exact path to UserKnownHostsFile. This option
adds no host, key or execution authority. Docker-only profiles refuse the override.

The caller must retain the frozen file privately for the whole environment lifetime
and supply the same override when reconstructing cleanup. A missing or changed pin
blocks SSH effects, including cleanup, until the exact pinned bytes are restored.
The original source path may disappear after freezing. The file is not copied into
the worker and the adapter does not rewrite signed profile identity.

Repeat from a checkout with the controller contract module available:

```sh
python3 evals/native-qualification/smoke/check_environment_known_hosts_e2e.py --output /tmp/environment-known-hosts.json
python3 evals/native-qualification/smoke/check_environment_transport_e2e.py --output /tmp/environment-transport.json
```

At this isolated branch checkpoint the contract dependency was supplied through
PYTHONPATH from the coordinator checkout; integration must rerun in one tree.
Both commands require Python 3 and local process/filesystem access, should exit
zero, and save status passed. No real SSH host or Docker daemon is contacted.

The six new controls use named fake SSH and Docker executables. They exercise
prepare, execute, changed pin, symlink pin and cleanup through the public adapter,
checking the actual argv received by the fake transport and unchanged raw-profile
digest. The22 existing Docker command controls passed again. before-known-hosts
records failure before the new constructor option existed. Source/dependency and
result hashes are in manifest.json. This is command-boundary simulation evidence,
not a remote identity, lease, isolation or cleanup qualification.
