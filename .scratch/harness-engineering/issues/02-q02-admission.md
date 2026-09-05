# 02: Reject unsupported Q02 comparison inputs

**Tracker:** [Reject unsupported Q02 comparison inputs](https://github.com/matheusht/redteam-harness/issues/108)

**What to build:** The public Q02 comparison command explains whether the supplied evidence is malformed, incomplete or eligible for its existing narrow prompt-ablation decision. A readable file or nonempty folder cannot establish eligibility by itself.

**Blocked by:** None (can start immediately).

**Status:** ready-for-agent; approved 2026-09-05.

## Acceptance criteria

- [ ] One shared admission boundary covers the public verdict path and statically discovered callers. Require a supported version, typed explicit integrity answers, attributable adjudication, source/case/run binding and unique result identities.
- [ ] Malformed JSON/duplicate keys, wrong types, invalid count values, empty identities, duplicate package IDs, contradictory mappings, byte mismatches and a present-but-blank waste assertion produce a bounded input error, exit 1, no verdict/license and no traceback. This validation precedes incomplete-input handling.
- [ ] Missing or well-typed unsupported version, missing required identity, missing/null integrity answer, unavailable required references and unestablished unit compatibility produce an inconclusive result, exit 0, explicit reasons and the frozen inconclusive license. Explicit adverse integrity flags retain their existing blocker. Optional absent cost/waste retains branch-specific behavior and never becomes positive evidence.
- [ ] Keep inventory separate from a source-bound eligibility assessment. M1 counts admitted legacy packages once per package ID; M6 counts adjudicated root-cause equivalence groups with explicit package-to-group mapping. Do not collapse M1 by root cause or assume M6 group totals equal package counts. Unreviewed revisions and unsupported layouts cannot silently enter M1.
- [ ] Bind measurement, worksheet, source commitments, eligibility assessment, root-cause grouping and any asserted waste evidence to resolvable declared bytes/identities. A blinding declaration is never described as independent proof.
- [ ] Describe the supported legacy input interpretation explicitly. Old unbound input remains inspectable but cannot receive a new decisive verdict. Do not reinterpret the absent private preregistration or recompute historical results.
- [ ] Preserve the frozen checkpoint, threshold, decision branches, license, quarantine/source-identity checks and publication protections. Do not resolve the separate filing-authority contract here.
- [ ] Exercise the public command with a complete bound benign control and one-invalid-dimension variants. Missing integrity is inconclusive; wrong integrity/count types, scalar ID collection, duplicate IDs, duplicate JSON keys, contradictory overlap/group mapping and blank asserted waste are input errors. Test unsupported versions and unavailable/mismatched references separately.
- [ ] Include multiple admitted packages sharing one adjudicated root cause. Verify distinct M1/M6 units and preserve an inconclusive result when frozen-rule compatibility is unestablished. Check result, blockers, exit behavior and license; do not silently upgrade the old loose control into eligible evidence.
- [ ] Retain required quarantine and compatibility regression checks for touched paths. A passing pure helper or old self-test alone is insufficient acceptance.

## Review basis

This is a repair to a limited case-study tool. It does not make Q02 a general harness score or require a new study executor.
