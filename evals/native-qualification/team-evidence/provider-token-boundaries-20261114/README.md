# Provider token boundaries — 14 November 2026

The pinned OMP SDK includes `task-specialization-advisory.md` and
`task-coordination-advisory.md`. The previous scanner treated the `sk-` substring
inside each ordinary filename as a provider key, so a real SDK tool bundle could
not pass the shared source-manifest publication gate.

The scanner now requires a lexical start for an unlabeled `sk-` token. It still
rejects that format embedded inside an API key, token or secret assignment. GitHub
and AWS token patterns are unchanged. Known-secret matching and the other
redaction classes are unchanged; the scanner does not claim to identify arbitrary
unknown credentials hidden inside unrelated words.

The failure-first workflow copies both actual SDK files into a disposable source
tree and uses the real source-manifest admission path. Three failures were
observed before the fix. All 18 checks pass after it, including provider key
formats, punctuation/path/underscore boundaries, credential field embeddings,
JSON escaping, known-secret embeddings, and file-stream chunk boundaries. All
credential controls use synthetic markers. The receipts include hashes of the
actual SDK files. No provider inference, target access or historical record
rewrite occurred.

```sh
python3 evals/native-qualification/smoke/check_provider_token_boundaries_e2e.py \
  --omp-sdk /private/sdk/node_modules/@oh-my-pi/pi-coding-agent \
  --output /private/results/provider-token-boundaries.json
```

The shared scanner is read by legacy artifact registration, source/environment
preflight, operator signatures, telemetry and migration admission, and the v2
publication gate. Their existing immutable records are not modified or regraded.
