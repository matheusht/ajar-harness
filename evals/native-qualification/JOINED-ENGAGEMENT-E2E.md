# Checked native engagement: joined contained scenario

This scenario joins the checked setup package, research plan, agent source
action, fresh review, and internal closeout on **one** disposable run root.
It is a control-flow check, not a target or provider qualification.

## Failure checks before implementation

| Case | Expected result |
| --- | --- |
| Checked plan uses `/deps` rather than the ordinary `/modules` envelope | The agent source action and fresh review use the checked envelope under the same allowance. |
| Agent changes its final claim or coverage after review | Closeout requests fresh review; no accepted result. |
| User stops while a review is incomplete | Stop and read back cleanup before returning. |
| Setup package or signed research scope changes | The checked transition refuses before a research turn. |
| Source action or review receipt is missing or changed | Closeout stays incomplete; no security effect is confirmed. |
| Cleanup readback is absent | The result remains incomplete. |

Run from the repository root:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 \
  evals/native-qualification/smoke/check_native_engagement_joined_e2e.py \
  --output /tmp/native-engagement-joined-e2e.json
```

Requirements: Python 3, local Docker with `busybox:1.37`, Go, OpenSSL,
and `ssh-keygen`. The first phase uses the checked setup-to-research E2E
fixture. It uses a synthetic signing key and a local offline Docker build.
The next phase simulates model turns, host source execution output, fresh
reviewer output, and owner stop on the **same checked research root**. It runs
the real continuation, packet, protected receipt, closeout, and pin checks.
The JSON output saves exact script, plan, action, review, and closeout hashes,
observed statuses, and the limits. No provider, real target service, or real
owner teardown occurs. A fresh signed target and provider route are needed
for those checks.

The 2026-11-12 result is saved in
[JOINED-ENGAGEMENT-E2E-RESULT.json](JOINED-ENGAGEMENT-E2E-RESULT.json).
It observed 48 passing transition checks, one simulated source action, one
simulated fresh review, three simulated native turns, and one simulated stop.
The companion transition and closeout scenarios exercise the refusal cases.
