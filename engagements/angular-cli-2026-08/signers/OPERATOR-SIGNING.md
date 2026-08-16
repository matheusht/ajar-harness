# Canonical scope activation — angular-cli-2026-08

`scope.md` is marked `Signed: [x]` from Matheus's in-session approval on 2026-08-14. Decision 0006
still requires Matheus — not an agent — to sign the exact initialization challenge before the record
kernel becomes active.

Frozen values (verified against the record kernel's own parser, 2026-08-14):

- scope SHA256: `sha256:95971192631d012ce629d019725eeebd8055cd4274aebf27b9b003ea7d923a5e`
- allowed-signers SHA256: `sha256:ccd13b84d23e9f64b1cb96458b49cb0219ee6115453652e2fbc5e7bf0944b9cc`
- recorded-at: `2026-08-14T12:00:00Z`
- namespace: `llm-redteam-harness-operator-v1`
- operator id: `matheusht`
- record kernel: `decision-0006-v1`

Validated: signature checkbox recognised, all required sections present, exactly one record kernel
selected, Zone-2 field block accepted (`impact_demo_authorized: yes`, category
`zone2_artifact_creation`, ceiling `artifact_creation`, containment non-placeholder).

The challenge file `signers/init-challenge.json` is the byte-exact output of the kernel's own
canonical serializer (digest `sha256:a4aa647afb0f21368ca4d863cf0de46c5f774520e14a4caf52de05d74339211b`),
printed by `run-engagement.py init` on 2026-08-14. It was NOT copied from
`angular-dev-infra-2026-08`: a challenge signature covers one engagement's exact bytes, and reusing
the dev-infra one would assert an attestation never made over this scope.

> **Note on the scope bytes.** The first activation attempt (2026-08-14) failed at the
> signature gate because the scaffold had backticks around the allowed-signers SHA256 on the
> `Operator allowed signers SHA256:` line, which the kernel regex requires plain. An agent
> removed the backticks and froze the new scope hash above; the operator re-signed the
> regenerated challenge. The stale signature (`init-challenge.json.sig`) was moved aside to
> `init-challenge.json.sig.stale` for audit — it covers bytes that will never be attested.
>
> **Note on the scope bytes.** The scaffold's scope.md used numbered headings and a bolded signature
> line that the record kernel's parser rejects (required-section and `Signed: [x]` checks). An agent
> applied content-neutral conformance edits on 2026-08-14 (heading format, signature line format,
> `<pkg>` placeholder reword, plus the two parser-required sections — Benign safe-objective set and
> Accounts / fixtures — filled from the engagement's own escalation-ceiling language). Review the
> diff before signing; the hash above freezes exactly those bytes.

```sh
/usr/bin/ssh-keygen -Y sign \
  -f <operator-private-key> \
  -n llm-redteam-harness-operator-v1 \
  engagements/angular-cli-2026-08/signers/init-challenge.json

HARNESS_OPERATOR_SIGNATURE_FILE="engagements/angular-cli-2026-08/signers/init-challenge.json.sig" \
HARNESS_OPERATOR_ALLOWED_SIGNERS_FILE="engagements/angular-cli-2026-08/signers/operator.allowed_signers" \
  ./.venv/bin/python tools/run-engagement.py init \
    --engagement engagements/angular-cli-2026-08 \
    --recorded-at 2026-08-14T12:00:00Z
```

Refuse to sign if any frozen value differs. Preserve the signature and attestation for audit.

## One command to activate

```sh
! engagements/angular-cli-2026-08/signers/complete-initialization.zsh
```

It re-verifies both hashes, refuses on any drift, signs the challenge, and runs `init`. **Only the
operator runs it.** The private key never enters an agent context.

## Gate status

| Gate | State |
|---|---|
| Scope signed in session | done (2026-08-14) |
| Reviewer identity + allowed-signers | reviewer allowed-signers present; identity confirmation pending at first review |
| Disk | confirm before the run |
| Toolchain | see `progress.md` (preflight pending at Round 0) |
| Kernel attestation | **operator command above** |
| Wire-2 (private-fork Actions run) | deferred to the moment of the act; methods 1 and 2 autonomous |
