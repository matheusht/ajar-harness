# Protected network journal corrected review

Reviewer `/root/m1_fixed_review`; **PASS**, no unresolved findings.

Exact base/HEAD `ade619df77aa535c08d6b02d5dbbdfcc86dc22cf`; canonical capture `88cd849f1fd6770fbdbde4f9098941a5d87390489db5d26d9317d6c73520c74d`, snapshot `b8870a6413bf1c8a70c025630eda8d5e86d3d4c15d8b67d7f9c89139ef3cf117`. Complete three-file scope matches before and after review. No reviewer product edits.

Standards: pass. Spec: pass. Both prior P2 findings are fixed. Anonymous observations require an account-free signed effect. New intents require an environment not stopped or cleaned and an environment observation connecting its nonce to the same dispatch ID. Matching historical results retain their old grant and remain admissible after cleanup/revocation.

Independently ran all eight signed workflow scenarios; all pass (`network-journal-fixed-independent.json`). Re-ran all three previously failing probes; all now reject with the expected network_effect_forbidden/network_environment_invalid codes (`network-journal-fixed-probes.json`). Reviewed the complete corrected delta, including positive anonymous attribution and late result after cleanup. Capture/check hash bindings are in `network-journal-fixed-review-evidence.json`. These are controller mechanics with simulated protected observations; no external provider, target, Docker daemon or SSH host contacted.
