# Verify retained references in a v2 export

Run against an offline, stable export from the matching controller revision:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 tools/verify_engagement_export_references.py /absolute/path/to/bundle
```

The command validates the journal chain, replays its recorded transitions, checks
retained contract/evidence/publication/receipt bytes, and binds the manifest's
engagement identity and revision to that replay. It does not start an engagement,
contact a target or model, repair records, or change bundle files.

Use a private local directory owned by the current user, with the export's private
file modes preserved. Links on inspected paths and escaped contract paths are rejected. Do not run
against a directory that another process can change during verification.

Exit 0 reports journal reference closure. Exit 1 reports a failed check without
printing bundle contents. A referenced evidence object must exist even if somebody
removed both its file and its inventory entry.

Add `--check-result` to compare `result.json` with the matching controller's
replayed result projection, including claims, usage, cleanup and external-action
authority. Missing, changed or unrecognized fields fail; JSON whitespace does not
affect comparison. A successful report marks `result_consistency_verified: true`.
The default remains reference-only and reports that field as false.

This complements byte-inventory verification; it does not replace it. It does not
validate all manifest file entries,
verify the export's signer/provenance, or establish research acceptance. A rewritten
self-consistent journal is not authenticated by its hashes. An unsupported future
journal format must be checked with its matching controller, not converted here.

The test uses an actual Controller.export with simulated executor observations.
It is engineering evidence, not a native-agent or real-target acceptance test.
