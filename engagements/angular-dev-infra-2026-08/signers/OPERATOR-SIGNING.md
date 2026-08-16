# Canonical scope activation — angular-dev-infra-2026-08

`scope.md` is marked `Signed: [x]` from Matheus's in-session approval on 2026-08-12. Decision 0006
still requires Matheus — not an agent — to sign the exact initialization challenge before the record
kernel becomes active.

Frozen values (verified against the record kernel's own parser, 2026-08-12):

- scope SHA256: `sha256:9feb17a37cf15bcfa170b3117e253dd5c7243e459225b038dea8b3917b75bf3c`
- allowed-signers SHA256: `sha256:ccd13b84d23e9f64b1cb96458b49cb0219ee6115453652e2fbc5e7bf0944b9cc`
- recorded-at: `2026-08-12T12:00:00Z`
- namespace: `llm-redteam-harness-operator-v1`
- operator id: `matheusht`
- record kernel: `decision-0006-v1`

Validated: signature checkbox recognised, all required sections present, exactly one record kernel
selected, Zone-2 field block accepted (`impact_demo_authorized: yes`, category
`zone2_artifact_creation`, ceiling `artifact_creation`, containment non-placeholder).

```sh
/usr/bin/ssh-keygen -Y sign \
  -f <operator-private-key> \
  -n llm-redteam-harness-operator-v1 \
  engagements/angular-dev-infra-2026-08/signers/init-challenge.json

HARNESS_OPERATOR_SIGNATURE_FILE="engagements/angular-dev-infra-2026-08/signers/init-challenge.json.sig" \
HARNESS_OPERATOR_ALLOWED_SIGNERS_FILE="engagements/angular-dev-infra-2026-08/signers/operator.allowed_signers" \
  ./.venv/bin/python tools/run-engagement.py init \
    --engagement engagements/angular-dev-infra-2026-08 \
    --recorded-at 2026-08-12T12:00:00Z
```

Refuse to sign if any frozen value differs. Preserve the signature and attestation for audit.

## One command to activate

```sh
! engagements/angular-dev-infra-2026-08/signers/complete-initialization.zsh
```

It re-verifies both hashes, refuses on any drift, signs the challenge, and runs `init`. **Only the
operator runs it.** The private key never enters an agent context.

## Gate status

| Gate | State |
|---|---|
| Scope signed in session | done |
| Reviewer identity + allowed-signers | **done** — `angular-dev-infra-reviewer`, sha256 `033a9853…4d32` |
| Disk | **done** — 46 GB free |
| Toolchain | see `progress.md` §2 |
| Kernel attestation | **operator command above** |
| Wire-2 (private-fork Actions run) | deferred to the moment of the act; methods 1 and 2 autonomous |
