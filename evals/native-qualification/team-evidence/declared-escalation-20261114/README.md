# Declared internal escalation admission — 14 November 2026

New environment and target-request intents now require an accepted current review
of the exact preceding claim before admitting a signed `stored` or `cross_user`
effect. Initial `source_only` and `self` effects retain their existing admission.
The lead requests `kind:escalation`, with the prior independently confirmed claim
as `subject_id` and the next signed effect as `next_effect_id`. The host derives
the protected predecessor, freezes the prior review, effect/control/replay,
instruments, contrary evidence, resource identities, environment and observed
accounts in the existing review packet. No new approval store is introduced.

A fresh reviewer must cite that material. Each new intent checks its current digest,
so a superseded instrument or reopened claim cannot retain authority through an
active worker. A new review request holds its exact prior-claim/next-effect
transition and marks older pending/accepted reviews stale. Their packet and result
remain intact; older late answers cannot restore admission, and unrelated
transitions retain their verdicts. Only adjacent self → stored → cross-user transitions qualify.
Matching late results and owned cleanup remain recordable after review invalidation
or authority revocation. Generic `artifact_create` admission is explicitly
unsupported; this change does not activate the human-gate exception.

Target requests may select a public signed ID with `X-OSLit-Effect`. Omission
requires exactly one compatible effect. The host removes this selector before
forwarding, and cross-origin redirects independently select their destination's
effect. The selector does not supply a credential or expand signed authority.

Repeat from the checkout with Python 3.11+ and `ssh-keygen`:

```sh
python3 evals/native-qualification/smoke/check_engagement_escalation_e2e.py --output /tmp/escalation.json
python3 evals/native-qualification/smoke/check_engagement_evidence_e2e.py --output /tmp/evidence.json
python3 evals/native-qualification/smoke/check_target_accounts_e2e.py --output /tmp/accounts.json
python3 evals/native-qualification/smoke/check_engagement_network_journal_e2e.py --output /tmp/network.json
python3 evals/native-qualification/smoke/check_engagement_admission_e2e.py --output /tmp/admission.json
python3 evals/native-qualification/smoke/check_engagement_guidance_e2e.py --output /tmp/guidance.json
```

Expected results are all pass: 19 escalation scenarios, 16 existing evidence
scenarios, 48 account HTTP checks, eight network journal scenarios, nine admission
scenarios and five guidance scenarios. `before.json` records the original failures;
`malformed-before.json` records the malformed new-field failure before its fix.
`review-before.json` records the two independent-review failures before their fix.
`after.json` records the final scenario result. The remaining JSON files retain the
regression results, and `manifest.json` binds the implementation and scenario bytes.

The signed controller/executor observations are explicitly simulated. Positive
adjacent transitions use isolated source fixtures with simulated clean replay;
they are not vulnerability findings. The target selector and redirect requests use
actual owned loopback HTTP receivers. No provider, external target, Docker daemon
or SSH host is contacted.

Shared application resources currently cannot claim `clean_start:true`, so they
cannot yet produce the independently confirmed predecessor needed to open a higher
rung. A fresh local client container does not establish remote reset. Generic native
shell/HTTP semantics, artifact classes and route activation remain unqualified.
Current root human gates stay active. The companion native-boundary unit supplies
resource-selected captures and its own integration evidence; this unit's protocol
update describes that composition without claiming its execution here.
