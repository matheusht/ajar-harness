# T03 post-stop review assessment: checks before implementation

This provider-free assessment consumes one completed native reviewer turn after
the run has stopped. It does not change `review()` or emit a finding. Its only
positive result is `candidate_for_operator_review`; an operator must still
review the underlying bytes and judgment.

| Failure | Required result |
| --- | --- |
| Run is active, uncertain, incompletely frozen, or exact-resource cleanup is missing | Hold; do not read or promote the review. |
| Role, reviewer dispatch, session, effect dispatch, or effect request differs from the immutable records | Hold with a bounded reason. |
| Review receipt, packet, selection identity, material projection, source pin, or protected trace is missing or changed | Hold; never accept a caller-supplied digest by itself. |
| Reviewer session differs from the fresh receipt, packet identity differs, or material contains no completed shell action | Hold. |
| Completed reviewer action is not tied to a same-role origin proof and exact native trace line | Hold; text and action hashes alone are not process attribution. |
| T01 semantic verifier is unavailable, does not report `effect_and_controls_observed`, or selects a different effect | Hold. S10 remains held without its own semantic verifier. |
| A decisive creation, ordinary, denial, or effect request has no unique process-origin proof on the original target | Hold. Origin transport alone is not semantic proof. |
| Reviewer origin proof lacks a decisive action's exact native tool line, or origin IDs do not match semantic IDs | Hold. |
| Reviewer has an unrelated attributed request but no independently observed effect/control chain on its isolated target | Hold. Require a second T01 semantic reconciliation keyed to the reviewer dispatch and review-effect request; every selected creation, ordinary, denial, and effect request must appear exactly once in that reviewer's origin proof and on a captured completed shell action line. |
| A secret or unsafe reviewer material would enter the durable receipt | Hold without persisting the unsafe projection. |
| Assessment is run twice or an existing receipt differs | Preserve the first immutable receipt and fail closed. |

Provider-free check: `PYTHONDONTWRITEBYTECODE=1 python3 evals/native-qualification/smoke/check_poststop_native_review_assessment.py --output /absolute/new/private-output`.
It uses synthetic receipts only and must report zero provider, Docker, and target
calls. It verifies composition and held cases; it is not native qualification.
