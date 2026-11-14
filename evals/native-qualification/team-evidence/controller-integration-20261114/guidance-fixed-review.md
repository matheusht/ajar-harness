# Frozen research guidance corrected review

Reviewer `/root/m1_fixed_review`; **PASS**, no unresolved findings.

Complete five-file scope, exact base/HEAD `6b364b55730b5e516634d56452f42a8128ea3bd7`; canonical capture `55690a0072e06975104928c4fc8914d1479f5429e58421fb18bd0db4fabc2e02`, snapshot `2cbc2de89bf2d916ec04b25df3c79cc50bd39dee88a2e9b9efa9db8e8164c60a`. Captured patches/bytes match after review. No product edits by reviewer.

Standards: pass. Spec: pass. Protocol now correctly distinguishes the digest in `ephemeral_read_view` from the runner's status-query `read_request`. The additional compatibility branch permits missing guidance only when the engagement is already non-active, allowing stop/recovery without inventing or rewriting a historical method. Active historical records still cannot dispatch without pinned guidance; present guidance remains digest verified. Existing authority checks prevent the cleanup-only path from restarting work.

All five signed local workflow cases pass independently, including historical stop (`guidance-fixed-independent.json`). Reviewed changed branch and documentation against the actual API. Hash bindings: `guidance-fixed-review-evidence.json`. Boundary bootstrap integration remains a separately owned unit. No model/provider/target, Docker daemon or SSH host contacted.
