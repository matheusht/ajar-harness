# Check exported file integrity

Run the byte-inventory check after exporting an engagement:

```sh
python tools/check_engagement_export.py /absolute/path/to/export
```

Use an offline, access-controlled directory that nobody can change during verification. The checker reads the `engagement-result-bundle-v2` manifest written by `Controller.export`. It does not start a provider or runtime.

Exit 0 means every listed file matches its SHA-256 and no unlisted file was found. Exit 1 means verification failed. Argument errors exit 2. The JSON report always sets `authenticity` and `acceptance` to `not_assessed`.

The checker rejects duplicate manifest keys, malformed metadata or digests, missing or changed files, unlisted files, noncanonical paths, symlinks, and special files. Empty directories are allowed. It reads evidence hashes incrementally rather than loading whole evidence files into memory.

## What this does not establish

A matching file inventory does not authenticate a manifest. Someone able to replace both files and digests can create an internally consistent export. The checker does not replay the journal, verify embedded references to evidence objects, assess signatures, or determine claim acceptance, cleanup completion, evidence freshness, provider behavior or Linux qualification. It does not grant external-action authority.

It is not safe against an attacker changing the directory during verification. Large JSON manifests can consume memory; use ordinary bounded exports, not untrusted uploads. These checks cover one byte-integrity portion of E15, not completion of E15 or M6.

## Tests

```sh
python evals/native-qualification/smoke/check_engagement_export_e2e.py -v
```

The suite runs 18 CLI cases and one real `Controller.export` case with four outcomes: unchanged, changed, missing and unlisted files. It uses signed local engineering fixtures and a simulated worker-start receipt. No native runtime or provider runs. The basic export includes contracts and journal entries but no evidence objects; semantic evidence-reference verification is outside this checker.
