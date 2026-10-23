# Scoped cleanup E2E contract (frozen before implementation)

From the repository root, with a virtual environment containing `requirements-ci.txt` (`jsonschema==4.26.0`), run:

```sh
./.venv/bin/python tools/scoped-cleanup-e2e.py > /tmp/scoped-cleanup-e2e-result.json
```

It also needs `/usr/bin/ssh-keygen`. The script creates a temporary target-local engagement and effect directory, signs its synthetic scope, and needs no provider, Docker, or live target. The JSON file is the saved E2E result; the temporary engagement and key are removed at exit.

Failure modes and checks:

1. Effect creation without an earlier open obligation, with a traversal filename, or over a pre-existing file (even one with the expected bytes) fails before file creation. A failed ledger append rolls back only the exact newly created inode.
2. Cleanup accepts only the exact scoped filename and content digest. A changed file or symlink remains untouched. An abort before creation can cancel the obligation only while the file is absent. A crash after unlink can resume with a truthful absence result.
3. The opening records the physical root device and inode. Creation, cleanup, and closure refuse a missing or replaced root, while historical ledger reduction still succeeds. A re-attested different signed root cannot settle the old opening; the E2E checks physical root replacement, not the re-attestation command.
4. The broker records the completed obligation with its opening and creation references, observed pre-revert digest, and fresh absence check. A separate process checks the target-local path again. A blocked obligation or missing cleanup record cannot pass closure.
5. Closure keeps the existing memory and report gates and requires terminal coverage with no blocking queue item. The E2E preserves a signed blocked terminal event and shows the exact unfinished candidate that prevents closure.
6. A fresh reducer process reproduces the cleanup state. Retrying committed creation or cleanup does not duplicate an event. The repository self-test separately checks historical approved-authority and budget-bounded closure paths.

Expected output is one JSON object with `valid: true`, each named case and its observed result. Any failed assertion exits nonzero. This is a synthetic local control check; it does not establish real target or provider behavior.
