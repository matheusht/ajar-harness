# T03 offline review-material gate

This is an owned PHP fixture check of the #159 review gate. It uses the three
checked-in PHP files, a frozen local packet, real host PHP execution, and a
synthetic native-tool record carrying that observed output. It does not run a
model, provider, target, or native reviewer.

From the repository root, with Python 3 and PHP CLI installed, use a new absent
output directory:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 evals/native-qualification/smoke/check_t03_review_input_lifetime.py --output /tmp/t03-material-gate-replay-1
```

Expected: `PASS`, 13 passing checks in `result.json`, and zero provider and
target calls. The checks preserve the contrary baseline and candidate output,
accept a direct completed PHP check of the frozen candidate, reject an `echo`
that merely mentions PHP, another session, a failed or result-free action, an
unbound path, changed claim/source/packet bytes, and stop before review.

Observed on 22 October 2026: 13/13 passed. Saved `result.json` has SHA-256
`f37858c10a868d6951aad9ebee4dad8ec922aae18c4c679fced08ae3fdd40029`.
The check does not establish the source or truth of any later model's tool
record. A real fresh reviewer, native cost, and an independent original
application effect remain unobserved while the provider/target route is held.
