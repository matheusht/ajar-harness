# T06 observer preparation transfer checks

22 October 2026. This is a source transfer from the dirty main checkout into an
isolated branch. It is documentation and synthetic fixture preparation for #162,
not a native challenge or a reviewer result. Do not mount this file, the frozen
failure matrix, `EXPECTED-CHECKS.md`, `PREP-RECEIPT.json`, or `SHA256SUMS` in a
researcher or reviewer context.

Before copying, require these checks:

1. The frozen matrix's ten referenced input hashes match the main checkout and
   the transferred files. Existing tracked app, note, policy-v2, and v1/v2 packet
   manifests must stay byte-identical. Missing referenced fixtures or historical
   receipts make the transfer incomplete.
2. The two T06 preparation folders keep their exact source bytes. The printed
   transcript is explicitly fabricated claim material, while sanitized observer
   records are contrary evidence. The expected checks and preparation receipts
   stay observer-only. The copied `REVIEW-INPUTS.json` files describe historical
   preparation, not a current packet selection; do not mount either whole folder
   or reuse old output as the reviewer's independent check. No prepared packet
   is counted as a native review.
3. Transferred files contain no literal personal home path, credential, cookie,
   signed URL, private key, or hidden Kanboard answer. The redacted historical
   receipt may contain `<HOME>` and `<RUN>` aliases. Keep its raw original outside
   this branch.
4. The transfer changes no launcher, review code, agent brief, target source,
   packet selection, runtime configuration, or acceptance state. In particular,
   the current native runner copies only the explicitly supplied target source
   and pinned control files; this observer directory must not be that source.
5. The T06 inventory points to the frozen matrix and states which planned
   mutants, resource input, OS-privilege evidence, and actual native results are
   still absent. A later run freezes each challenge input and expected bounded
   disposition before native dispatch, then retains actual contrary evidence.

Static readback after copying: compare the matrix's pinned SHA-256 values with
`shasum -a 256` on their named files; compare the copied preparation files with
the main source; scan the transferred text for the literal home prefix and
credential patterns; inspect `git diff --check` and the exact changed-file list.
No provider, Docker, synthetic app, or real target is run by this transfer.
