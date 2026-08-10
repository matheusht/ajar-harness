# unproven/ — the eleven findings, migrated 2026-08-10

These were registered into `findings/` on 2026-08-09 with a status the run set for itself, on fifteen
`claim_adjudication` reviews a script generated. See `../QUARANTINE-synthetic-adjudication.md`.

They are here because that is what they are: unproven. Not disproven. The research underneath may be
entirely right — nobody has re-checked it. What failed is the record.

## What I fixed, and what I deliberately did not

**Fixed — G5.** Every finding now carries a CVSS 3.1 vector that recomputes. There were none before,
so severity was unadjudicated on top of everything else.

The vectors are **mine, derived 2026-08-10, and not independently reviewed.** G5 only asks that a
vector exists and recomputes; the metric choices are judgement and belong to the review.

Scope rule applied consistently: `S:C` only where impact reaches a **different product's** security
authority through a leaked or abused credential — the secret-leak family reaching GitHub and cloud
providers, and F1 reaching private repositories with the integration credential. `S:U` everywhere the
impact stays inside the Backstage deployment.

Derived labels agree with the recorded labels on **10 of 11**. That was not fitted; the rule was
chosen first. The one disagreement is recorded below.

**Deliberately NOT fixed — G1, G2, G3.** I could have written the attestations and made these
promote. I did not, because the evidence does not support them, and writing them anyway is precisely
the failure this whole exercise exists to correct.

- **G1 real-path-exec.** The A2 keystone PoC calls `mockCredentials.service()`. It constructs the
  post-bypass state and asserts the real `ServerPermissionClient` allows it. That proves the
  **consumer** half against real code. The **producer** half — that a forward actually strips the
  restrictions — is source-verified at `DefaultAuthService.ts:171-175`, not executed. The run's own
  notes carried that distinction; the registration layer flattened it into "demonstrated".
- **G2 negative-control.** Control attempts are named in the records. I did not verify any of them
  ran, so I cannot attest them.
- **G3 privilege_context.** Every finding declares `proven: not-established`. That is a statement,
  not an omission: no PoC here was verified to run from the position the finding claims an attacker
  holds. This is the gate the harness never had, and it is doing its job on the first real use.

## The one severity disagreement

`F-OIDC3` — my derivation gives **7.4 High**; the record says **Medium**.

The likely reason for the lower record is the config gating (experimental DCR/CIMD flags, off by
default). That is a real reportability argument and it is **not** a CVSS base-metric adjustment.
Environmental metrics or a stated reporting decision are the right home for it, not a lower base
score. Flagged for the reviewer; I did not change either value to make them agree.

## What each finding needs to promote

| gate | what would satisfy it |
|---|---|
| G1 | run the decisive path end to end against the pinned build, or narrow the claim to what the mock PoC actually proves |
| G2 | re-run each named control and record its raw output |
| G3 | run the PoC from the claimed attacker position and record it, or narrow the claim |
| G4 | real independent reviewers, briefed to refute, blind to the prior verdict — the engagement corpus currently audits `synthetic`, so nothing resting on it can promote |
| G5 | **met** |

Check any package without moving it:

    ./.venv/bin/python tools/finding_lifecycle.py gates \
        engagements/spotify-backstage-2026-07/unproven/<ID> \
        --engagement engagements/spotify-backstage-2026-07
